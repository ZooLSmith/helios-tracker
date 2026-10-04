"""
Scaleform vector shapes -> images: a DefineShape's edges (straight and curved, each with the fill styles on its two
sides and the line style stroking it) filled and stroked in their solid colours, anti-aliased, as BGRA ("PF_A8R8G8B8":
what the page's decodeTexture takes, like the game's own textures) - a game's vector map, its menus' icons.
Pure Python, no SDK.

Drawn as Flash layers them: style list by style list (a shape may start new ones mid-way: some maps keep their lines
in them), each list's fills, then its lines. Only what the maps use: solid fills, gradients as their colours' average
(three maps have one: arid_bunker, interlude2, trash - not drawn as gradients yet), no bitmaps; lines solid, round
joins and caps (Flash's default).
"""

import math
import struct
from dataclasses import dataclass, field
from itertools import accumulate

from .swf import _Bits, _matrix, _rect

SUB = 4  # sub-scanlines per pixel row (the vertical anti-aliasing)
SHAPE_CODES = {2: "DefineShape", 22: "DefineShape2", 32: "DefineShape3", 83: "DefineShape4"}
JOIN_SIDES = 8  # a round join / cap: a polygon of this many sides

RGBA = tuple[int, int, int, int]


@dataclass
class Shape:
    bounds: tuple[float, float, float, float]  # x0, x1, y0, y1 (movie px)
    fills: list[tuple[int, RGBA | None]] = field(default_factory=list)  # style index - 1 -> (its list, RGBA; None: not solid)
    lines: list[tuple[int, float, RGBA]] = field(default_factory=list)  # style index - 1 -> (its list, width px, RGBA)
    # (fill0, fill1, line, points): the styles on its left / right, the line stroking it (0: none)
    edges: list[tuple[int, int, int, list[tuple[float, float]]]] = field(default_factory=list)


def _styles(code: int, body: bytes, o: int, shape: Shape, layer: int) -> int:
    """A style list (fills, then lines) from `o`: its styles appended to the shape's; the offset after it."""
    count = body[o]
    o += 1
    if count == 0xFF and code != 2:
        count = struct.unpack_from("<H", body, o)[0]
        o += 2
    rgba = code in (32, 83)
    n = 4 if rgba else 3

    def colour(at: int) -> RGBA:
        return tuple(body[at:at + n]) + (() if rgba else (255,))  # type: ignore[return-value]

    for _ in range(count):
        kind = body[o]
        o += 1
        if kind == 0x00:
            shape.fills.append((layer, colour(o)))
            o += n
        elif 0x40 <= kind <= 0x43:  # bitmap: its id and matrix
            b = _Bits(body, o + 2)
            _matrix(b)
            o = b.align()
            shape.fills.append((layer, None))
        elif kind in (0x10, 0x12, 0x13):  # linear / radial / focal gradient: its matrix, then its records
            b = _Bits(body, o)
            _matrix(b)
            o = b.align()
            records = body[o] & 0x0F
            o += 1
            colours = [colour(o + 1 + i * (1 + n)) for i in range(records)]
            o += records * (1 + n) + (2 if kind == 0x13 else 0)  # (ratio + colour each; focal: its focal point)
            average = tuple(round(sum(c[k] for c in colours) / len(colours)) for k in range(4)) if colours else None
            shape.fills.append((layer, average))  # type: ignore[arg-type]
        else:
            raise ValueError(f"fill style {kind:#x} not supported")
    count = body[o]
    o += 1
    if count == 0xFF and code != 2:
        count = struct.unpack_from("<H", body, o)[0]
        o += 2
    for _ in range(count):
        width = struct.unpack_from("<H", body, o)[0] / 20
        if code == 83:  # LINESTYLE2: width, flags (joins / caps / has fill...), [miter limit], colour or a fill
            flags = struct.unpack_from("<H", body, o + 2)[0]
            o += 4
            if (flags >> 4) & 3 == 2:
                o += 2
            if flags & 0x0800:
                raise ValueError("a line style with a fill: not supported")
            shape.lines.append((layer, width, colour(o)))
            o += 4
        else:
            shape.lines.append((layer, width, colour(o + 2)))
            o += 2 + n
    return o


def _curve(x: float, y: float, cx: float, cy: float, ax: float, ay: float) -> list[tuple[float, float]]:
    """A quadratic curve's points after (x, y), flattened: about a point per 2 movie px of it."""
    n = max(2, min(32, math.ceil((math.hypot(cx - x, cy - y) + math.hypot(ax - cx, ay - cy)) / 2)))
    return [((1 - t) ** 2 * x + 2 * (1 - t) * t * cx + t * t * ax, (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t * t * ay)
            for t in (i / n for i in range(1, n + 1))]


def parse_shape(code: int, body: bytes) -> Shape:
    """A DefineShape(2/3/4) tag's body -> its bounds, styles and edges (curves flattened)."""
    b = _Bits(body, 2)
    shape = Shape(_rect(b))
    o = b.align()
    if code == 83:  # edge bounds, flags
        b = _Bits(body, o)
        _rect(b)
        o = b.align() + 1
    layer = 0  # the style list: a new one numbers its styles from 1 again - they go after the ones before
    fill_base = line_base = 0
    o = _styles(code, body, o, shape, layer)
    b = _Bits(body, o)
    fbits, lbits = b.u(4), b.u(4)
    x = y = 0.0
    f0 = f1 = ln = 0
    run: list[tuple[float, float]] = [(x, y)]

    def close() -> None:
        if len(run) > 1 and (f0 or f1 or ln):
            shape.edges.append((f0, f1, ln, run))

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
                f0 = (v := b.u(fbits)) and v + fill_base
            if flags & 4:
                f1 = (v := b.u(fbits)) and v + fill_base
            if flags & 8:
                ln = (v := b.u(lbits)) and v + line_base
            if flags & 16:  # new style lists
                layer += 1
                fill_base, line_base = len(shape.fills), len(shape.lines)
                o = _styles(code, body, b.align(), shape, layer)
                b = _Bits(body, o)
                fbits, lbits = b.u(4), b.u(4)
                f0 = f1 = ln = 0
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
Segment = tuple[float, float, float, float]  # x0, y0, x1, y1 (output px), from (x0, y0) to (x1, y1)


def _coverage(segments: list[Segment], w: int, h: int, nonzero: bool = False) -> bytearray:
    """Alpha (0-255) per pixel of the region the segments (in output px) border - even-odd, or nonzero (the union of
    the polygons they close, all turning the same way: a stroke's pieces overlap) - SUB sub-scanlines per row, each
    span's ends at their exact fraction of a pixel."""
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
            xs: list[tuple[float, int]] = []
            keep = []
            for n in active:
                x0, y0, x1, y1 = segments[n]
                if max(y0, y1) <= yc:
                    continue  # passed: dropped
                keep.append(n)
                if min(y0, y1) <= yc:
                    xs.append((x0 + (yc - y0) * (x1 - x0) / (y1 - y0), 1 if y1 > y0 else -1))
            active = keep
            xs.sort()
            spans = []
            if nonzero:
                wind, start = 0, 0.0
                for x, d in xs:
                    if wind == 0:
                        start = x
                    wind += d
                    if wind == 0:
                        spans.append((start, x))
            else:
                spans = [(xs[i][0], xs[i + 1][0]) for i in range(0, len(xs) - 1, 2)]
            for a, z in spans:
                a, z = max(0.0, a), min(float(w), z)
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


def _stroke(points: list[tuple[float, float]], half: float) -> list[Segment]:
    """A polyline stroked `half` px either side (output px): a quad per piece and a round join / cap at each point - as
    closed polygons all turning the same way (for a nonzero fill: their union)."""
    out: list[Segment] = []

    def polygon(pts: list[tuple[float, float]]) -> None:
        out.extend((ax, ay, bx, by) for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]) if ay != by)

    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        nx, ny = -dy / length * half, dx / length * half
        polygon([(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)])
    if half >= 0.5:  # (thinner: the quads alone)
        # the quads turn clockwise (their signed area < 0, y down): the joins too - angles going down
        for px, py in points:
            polygon([(px + half * math.cos(-2 * math.pi * i / JOIN_SIDES), py + half * math.sin(-2 * math.pi * i / JOIN_SIDES))
                     for i in range(JOIN_SIDES)])
    return out


def _paint(image: bytearray, alpha: bytearray, colour: RGBA) -> None:
    """`colour` over the image (BGRA), by its coverage."""
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


def render(layers: list[tuple[Affine, Shape]], scale: float) -> tuple[int, int, bytes, tuple[float, float, float, float]]:
    """Shapes placed by their matrices (drawn in order) -> (width, height, BGRA bytes, bounds in movie px: x0, x1, y0,
    y1), `scale` output px per movie px. Outside the shapes: transparent."""
    def place(m: Affine, p: tuple[float, float]) -> tuple[float, float]:
        return m[0] * p[0] + m[2] * p[1] + m[4], m[1] * p[0] + m[3] * p[1] + m[5]

    corners = [place(m, (x, y)) for m, s in layers for x in s.bounds[:2] for y in s.bounds[2:]]
    x0, y0 = min(c[0] for c in corners), min(c[1] for c in corners)
    x1, y1 = max(c[0] for c in corners), max(c[1] for c in corners)
    w, h = max(1, math.ceil((x1 - x0) * scale)), max(1, math.ceil((y1 - y0) * scale))
    image = bytearray(w * h * 4)

    def out_px(m: Affine, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [((px - x0) * scale, (py - y0) * scale) for px, py in (place(m, p) for p in points)]

    for m, shape in layers:
        line_scale = math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) * scale  # (a line's width: by the matrix's scale)
        for layer in sorted({f[0] for f in shape.fills} | {ln[0] for ln in shape.lines}):
            for style, (style_layer, colour) in enumerate(shape.fills, 1):
                if style_layer != layer or colour is None:
                    continue
                # the style's borders: the edges with it on one side only (on both: inside it)
                segments: list[Segment] = []
                for f0, f1, _ln, points in shape.edges:
                    if (f0 == style) == (f1 == style):
                        continue
                    pts = out_px(m, points)
                    segments += [(ax, ay, bx, by) for (ax, ay), (bx, by) in zip(pts, pts[1:]) if ay != by]
                if segments:
                    _paint(image, _coverage(segments, w, h), colour)
            for style, (style_layer, width, colour) in enumerate(shape.lines, 1):
                if style_layer != layer:
                    continue
                half = max(width * line_scale, 1.0) / 2  # (a hairline, width 0: one px)
                segments = []
                for _f0, _f1, ln, points in shape.edges:
                    if ln == style:
                        segments += _stroke(out_px(m, points), half)
                if segments:
                    _paint(image, _coverage(segments, w, h, nonzero=True), colour)
    return w, h, bytes(image), (x0, x1, y0, y1)
