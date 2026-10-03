"""
Scaleform vector shapes -> images: a DefineShape's edges (straight and curved, each with the fill styles on its two
sides) filled in their solid colours, anti-aliased, as BGRA ("PF_A8R8G8B8": what the page's decodeTexture takes, like
the game's own textures). Borderlands 1's map is drawn this way (bl1map.py). Pure Python, no SDK.

Only what the maps use: solid fills, gradients as their colours' average (three BL1 maps have one: arid_bunker,
interlude2, trash - not drawn as gradients yet), no bitmaps, no line strokes.
"""

import math
import struct
from dataclasses import dataclass, field
from itertools import accumulate

from .swf import _Bits, _matrix, _rect

SUB = 4  # sub-scanlines per pixel row (the vertical anti-aliasing)
SHAPE_CODES = {2: "DefineShape", 22: "DefineShape2", 32: "DefineShape3", 83: "DefineShape4"}


@dataclass
class Shape:
    bounds: tuple[float, float, float, float]  # x0, x1, y0, y1 (movie px)
    fills: list[tuple[int, int, int, int] | None] = field(default_factory=list)  # style index - 1 -> RGBA (None: not solid)
    edges: list[tuple[int, int, list[tuple[float, float]]]] = field(default_factory=list)  # (fill0, fill1, points)


def _styles(code: int, body: bytes, o: int, fills: list) -> int:
    """A style list (fills, then lines) from `o`: its solid fills appended; the offset after it."""
    count = body[o]
    o += 1
    if count == 0xFF and code != 2:
        count = struct.unpack_from("<H", body, o)[0]
        o += 2
    rgba = code in (32, 83)
    for _ in range(count):
        kind = body[o]
        o += 1
        if kind == 0x00:
            n = 4 if rgba else 3
            fills.append(tuple(body[o:o + n]) + (() if rgba else (255,)))
            o += n
        elif 0x40 <= kind <= 0x43:  # bitmap: its id and matrix
            b = _Bits(body, o + 2)
            _matrix(b)
            o = b.align()
            fills.append(None)
        elif kind in (0x10, 0x12, 0x13):  # linear / radial / focal gradient: its matrix, then its records
            b = _Bits(body, o)
            _matrix(b)
            o = b.align()
            count = body[o] & 0x0F
            o += 1
            n = 4 if rgba else 3
            colours = [tuple(body[o + 1 + i * (1 + n):o + 1 + i * (1 + n) + n]) + (() if rgba else (255,)) for i in range(count)]
            o += count * (1 + n) + (2 if kind == 0x13 else 0)  # (ratio + colour each; focal: its focal point)
            fills.append(tuple(round(sum(c[k] for c in colours) / len(colours)) for k in range(4)) if colours else None)
        else:
            raise ValueError(f"fill style {kind:#x} not supported")
    lines = body[o]
    o += 1
    if lines == 0xFF and code != 2:
        lines = struct.unpack_from("<H", body, o)[0]
        o += 2
    for _ in range(lines):
        if code == 83:  # LINESTYLE2: width, flags (joins / caps / has fill...), [miter limit], colour or a fill
            flags = struct.unpack_from("<H", body, o + 2)[0]
            o += 4
            if (flags >> 4) & 3 == 2:
                o += 2
            if flags & 0x0800:
                raise ValueError("a line style with a fill: not supported")
            o += 4
        else:
            o += 2 + (4 if rgba else 3)
    return o


def _curve(x: float, y: float, cx: float, cy: float, ax: float, ay: float) -> list[tuple[float, float]]:
    """A quadratic curve's points after (x, y), flattened: about a point per 2 movie px of it."""
    n = max(2, min(32, math.ceil((math.hypot(cx - x, cy - y) + math.hypot(ax - cx, ay - cy)) / 2)))
    return [((1 - t) ** 2 * x + 2 * (1 - t) * t * cx + t * t * ax, (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t * t * ay)
            for t in (i / n for i in range(1, n + 1))]


def parse_shape(code: int, body: bytes) -> Shape:
    """A DefineShape(2/3/4) tag's body -> its bounds, solid fills and edges (curves flattened)."""
    b = _Bits(body, 2)
    shape = Shape(_rect(b))
    o = b.align()
    if code == 83:  # edge bounds, flags
        b = _Bits(body, o)
        _rect(b)
        o = b.align() + 1
    base = 0  # new style lists number from 1 again: their fills go after the ones before
    o = _styles(code, body, o, shape.fills)
    b = _Bits(body, o)
    fbits, lbits = b.u(4), b.u(4)
    x = y = 0.0
    f0 = f1 = 0
    run: list[tuple[float, float]] = [(x, y)]

    def close() -> None:
        if len(run) > 1 and (f0 or f1):
            shape.edges.append((f0, f1, run))

    while True:
        if not b.u(1):  # a style change record, or the end
            flags = b.u(5)
            if not flags:
                break
            close()
            if flags & 1:
                n = b.u(5)
                x, y = b.s(n) / 20, b.s(n) / 20
            if flags & 2:
                f0 = (v := b.u(fbits)) and v + base
            if flags & 4:
                f1 = (v := b.u(fbits)) and v + base
            if flags & 8:
                b.u(lbits)
            if flags & 16:  # new style lists
                base = len(shape.fills)
                o = _styles(code, body, b.align(), shape.fills)
                b = _Bits(body, o)
                fbits, lbits = b.u(4), b.u(4)
                f0 = f1 = 0
            run = [(x, y)]
        elif b.u(1):  # a straight edge
            n = b.u(4) + 2
            if b.u(1):
                x += b.s(n) / 20
                y += b.s(n) / 20
            elif b.u(1):
                y += b.s(n) / 20
            else:
                x += b.s(n) / 20
            run.append((x, y))
        else:  # a curved edge: control, anchor
            n = b.u(4) + 2
            cx, cy = x + b.s(n) / 20, y + b.s(n) / 20
            ax, ay = cx + b.s(n) / 20, cy + b.s(n) / 20
            run.extend(_curve(x, y, cx, cy, ax, ay))
            x, y = ax, ay
    close()
    return shape


Affine = tuple[float, float, float, float, float, float]  # a, b, c, d, e, f: x' = a x + c y + e, y' = b x + d y + f


def _coverage(segments: list[tuple[float, float, float, float]], w: int, h: int) -> bytearray:
    """Alpha (0-255) per pixel of the region the segments (in output px) border, even-odd: SUB sub-scanlines per
    row, each span's ends at their exact fraction of a pixel."""
    by_row: dict[int, list[int]] = {}  # the first sub-scanline a segment crosses -> segments
    for n, (x0, y0, x1, y1) in enumerate(segments):
        lo, hi = min(y0, y1), max(y0, y1)
        first = max(0, math.ceil(lo * SUB - 0.5))
        if first < hi * SUB - 0.5:
            by_row.setdefault(first, []).append(n)
    out = bytearray(w * h)
    active: list[int] = []
    full = 255 / SUB
    for row in range(h):
        acc = [0.0] * (w + 1)  # a difference array: coverage added at span starts, taken back at their ends
        touched = False
        for sub in range(row * SUB, row * SUB + SUB):
            active.extend(by_row.get(sub, ()))
            yc = (sub + 0.5) / SUB
            xs = []
            keep = []
            for n in active:
                x0, y0, x1, y1 = segments[n]
                if max(y0, y1) <= yc:
                    continue  # passed: dropped
                keep.append(n)
                if min(y0, y1) <= yc:
                    xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
            active = keep
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                a, z = max(0.0, xs[i]), min(float(w), xs[i + 1])
                if z <= a:
                    continue
                touched = True
                ia, iz = int(a), int(z)
                if ia == iz:
                    acc[ia] += (z - a) * full
                    acc[ia + 1] -= (z - a) * full
                    continue
                acc[ia] += (ia + 1 - a) * full  # the first pixel's part
                acc[ia + 1] -= (ia + 1 - a) * full
                acc[ia + 1] += full  # the whole ones between
                acc[iz] -= full
                acc[iz] += (z - iz) * full  # the last one's part
                acc[iz + 1 if iz < w else w] -= (z - iz) * full
        if touched:
            out[row * w:(row + 1) * w] = bytes(min(255, int(v + 0.5)) for v in accumulate(acc[:w]))
    return out


def render(layers: list[tuple[Affine, Shape]], scale: float) -> tuple[int, int, bytes, tuple[float, float, float, float]]:
    """Shapes placed by their matrices (drawn in order) -> (width, height, BGRA bytes, bounds in movie px: x0, x1, y0,
    y1), `scale` output px per movie px. Outside the fills: transparent."""
    def place(m: Affine, p: tuple[float, float]) -> tuple[float, float]:
        return m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5]

    corners = [place(m, (x, y)) for m, s in layers for x in s.bounds[:2] for y in s.bounds[2:]]
    x0, y0 = min(c[0] for c in corners), min(c[1] for c in corners)
    x1, y1 = max(c[0] for c in corners), max(c[1] for c in corners)
    w, h = max(1, math.ceil((x1 - x0) * scale)), max(1, math.ceil((y1 - y0) * scale))
    image = bytearray(w * h * 4)
    for m, shape in layers:
        for style, colour in enumerate(shape.fills, 1):
            if colour is None:
                continue
            # the style's borders: the edges with it on one side only (on both: inside it)
            segments = []
            for f0, f1, points in shape.edges:
                if (f0 == style) == (f1 == style):
                    continue
                pts = [place(m, p) for p in points]
                segments += [((ax - x0) * scale, (ay - y0) * scale, (bx - x0) * scale, (by - y0) * scale)
                             for (ax, ay), (bx, by) in zip(pts, pts[1:]) if ay != by]
            if not segments:
                continue
            alpha = _coverage(segments, w, h)
            r, g, b, a = colour
            for i, cover in enumerate(alpha):
                if not cover:
                    continue
                src = cover * a / 255
                o = i * 4
                dst = image[o + 3] / 255
                out_a = src / 255 + dst * (1 - src / 255)
                if src >= 255 or not dst:  # (the common cases: alone, or over nothing)
                    image[o:o + 4] = bytes((b, g, r, int(src + 0.5)))
                    continue
                k = (src / 255) / out_a
                image[o] = int(b * k + image[o] * (1 - k) + 0.5)
                image[o + 1] = int(g * k + image[o + 1] * (1 - k) + 0.5)
                image[o + 2] = int(r * k + image[o + 2] * (1 - k) + 0.5)
                image[o + 3] = int(out_a * 255 + 0.5)
    return w, h, bytes(image), (x0, x1, y0, y1)
