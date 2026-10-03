"""
Standard SWF fonts - DefineFont3 (tag 75) - as gamefonts' GameFont, for its TrueType writer (gamefonts.to_ttf). Files
only: no SDK, no UObjects. Borderlands 1's font library has them (bl1fonts.py); BL2's are Scaleform's compacted fonts
(gamefonts.py).

DefineFont3 (the SWF spec), its body:
    FontID u16, flags u8 (0x80 HasLayout, 0x08 WideOffsets, 0x04 WideCodes, 0x02 Italic, 0x01 Bold), language u8,
    name (u8 length, then the name), glyph count u16,
    offsets: one per glyph (u32 if WideOffsets, else u16) from the offsets' start, then the code table's offset (same),
    glyph shapes: SHAPE each - fill bits u4, line bits u4, shape records (bits): a style change (0, then 5 flags:
    new styles, line, fill 1, fill 0, move to; none: the end) - move to: 5 bits n, x, y (n bits, absolute) - or an
    edge (1): straight (1) / curved (0), 4 bits n - 2; straight: general (1: dx, dy) or vertical (1: dy) / horizontal
    (0: dx); curved: control dx dy, anchor dx dy (from the pen, then from the control),
    code table: u16 per glyph (WideCodes),
    layout (HasLayout): ascent u16, descent u16, leading s16, advances (s16 per glyph), bounds (a RECT per glyph,
    byte-aligned), kerning count u16, then (code u16, code u16, adjustment s16) each.
Its coordinates: an EM square of 1024 x 20 (twips) - divided by 20 here (TrueType's units per em: 1024).
"""

import struct

from .gamefonts import GameFont, Glyph
from .swf import _Bits

SCALE = 20  # (DefineFont3's units: 1/20 of its 1024 EM)
EM = 1024


def _glyph(d: bytes, o: int) -> list[list[tuple[str, int, int]]]:
    """A glyph's SHAPE at o -> its contours, ("on" / "off", x, y) points, y down (SWF) - a contour per move to."""
    b = _Bits(d, o)
    fill_bits, line_bits = b.u(4), b.u(4)
    contours: list[list[tuple[str, int, int]]] = []
    x = y = 0
    while True:
        if not b.u(1):  # a style change
            flags = b.u(5)
            if not flags:
                break  # (the end)
            if flags & 1:  # move to: a new contour
                n = b.u(5)
                x, y = b.s(n), b.s(n)
                contours.append([("on", x, y)])
            if flags & 2:
                b.u(fill_bits)
            if flags & 4:
                b.u(fill_bits)
            if flags & 8:
                b.u(line_bits)
            continue
        if not contours:
            contours.append([("on", x, y)])
        if b.u(1):  # straight
            n = b.u(4) + 2
            if b.u(1):
                x, y = x + b.s(n), y + b.s(n)
            elif b.u(1):
                y += b.s(n)
            else:
                x += b.s(n)
            contours[-1].append(("on", x, y))
        else:  # curved: control, then anchor
            n = b.u(4) + 2
            cx, cy = x + b.s(n), y + b.s(n)
            x, y = cx + b.s(n), cy + b.s(n)
            contours[-1] += [("off", cx, cy), ("on", x, y)]
    out = []
    for contour in contours:
        if len(contour) > 1 and contour[-1][0] == "on" and contour[-1][1:] == contour[0][1:]:
            contour.pop()  # (an explicit close)
        if len(contour) >= 3:
            out.append([(k, round(px / SCALE), round(py / SCALE)) for k, px, py in contour])
    return out


def parse_font3(body: bytes) -> GameFont:
    """A DefineFont3 tag's body -> the font (see the module's docstring), in units of 1/1024 EM."""
    flags = body[2]
    name_len = body[4]
    name = body[5 : 5 + name_len].rstrip(b"\0").decode("latin1")
    o = 5 + name_len
    count = struct.unpack_from("<H", body, o)[0]
    table = o + 2
    wide = bool(flags & 0x08)
    size, fmt = (4, "<I") if wide else (2, "<H")
    offsets = [struct.unpack_from(fmt, body, table + size * i)[0] for i in range(count)]
    code_table = table + struct.unpack_from(fmt, body, table + size * count)[0]
    codes = [struct.unpack_from("<H", body, code_table + 2 * i)[0] for i in range(count)]
    advances = [EM // 2] * count
    ascent, descent, leading = EM * 4 // 5, EM // 5, 0
    kerning: dict[tuple[int, int], int] = {}
    if flags & 0x80:  # its layout
        o = code_table + 2 * count
        ascent, descent, leading = struct.unpack_from("<HHh", body, o)
        ascent, descent, leading = round(ascent / SCALE), round(descent / SCALE), round(leading / SCALE)
        o += 6
        advances = [round(struct.unpack_from("<h", body, o + 2 * i)[0] / SCALE) for i in range(count)]
        o += 2 * count
        b = _Bits(body, o)
        for _ in range(count):  # (its bounds: recomputed from the points by the TrueType writer)
            n = b.u(5)
            b.u(4 * n)
            b.align()
        o = b.align()
        pairs = struct.unpack_from("<H", body, o)[0] if o + 2 <= len(body) else 0
        for i in range(pairs):
            a, c, adjust = struct.unpack_from("<HHh", body, o + 2 + 6 * i)
            kerning[(a, c)] = round(adjust / SCALE)
    glyphs = [Glyph(codes[i], advances[i], _glyph(body, table + offsets[i])) for i in range(count)]
    return GameFont(name, 1 if flags & 0x01 else 0, EM, ascent, descent, leading, glyphs, kerning)
