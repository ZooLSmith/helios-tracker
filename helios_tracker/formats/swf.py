"""
Scaleform (SWF / GFx) movies: the bit reader, rectangles, matrices, tags - what tacmap.py (the map movies), gamecards.py
(the item cards), gamefonts.py (the font libraries) and swfshape.py (vector shapes) read movies with. Pure Python.
"""

import struct
import zlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .upk import Package


class _Bits:
    def __init__(self, d: bytes, o: int) -> None:
        self.d, self.p = d, o * 8

    def u(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.d[self.p >> 3] >> (7 - (self.p & 7))) & 1)
            self.p += 1
        return v

    def s(self, n: int) -> int:
        v = self.u(n)
        return v - (1 << n) if n and v & (1 << (n - 1)) else v

    def align(self) -> int:
        self.p = (self.p + 7) // 8 * 8
        return self.p // 8


def _rect(b: _Bits) -> tuple[float, float, float, float]:
    n = b.u(5)
    x0, x1, y0, y1 = (b.s(n) / 20 for _ in range(4))  # twips -> px
    return x0, x1, y0, y1


def _matrix(b: _Bits) -> tuple[float, float, float, float]:
    """(scale x, scale y, translate x, translate y); rotation/skew is read but ignored."""
    sx = sy = 1.0
    if b.u(1):
        n = b.u(5)
        sx, sy = b.s(n) / 65536, b.s(n) / 65536
    if b.u(1):
        n = b.u(5)
        b.s(n), b.s(n)
    n = b.u(5)
    return sx, sy, b.s(n) / 20, b.s(n) / 20


def _affine(b: _Bits) -> tuple[float, float, float, float, float, float]:
    """The whole matrix, as a canvas transform (a, b, c, d, e, f): x' = a x + c y + e, y' = b x + d y + f
    (SWF: ScaleX, RotateSkew0, RotateSkew1, ScaleY, TranslateX / Y in px)."""
    sx = sy = 1.0
    r0 = r1 = 0.0
    if b.u(1):
        n = b.u(5)
        sx, sy = b.s(n) / 65536, b.s(n) / 65536
    if b.u(1):
        n = b.u(5)
        r0, r1 = b.s(n) / 65536, b.s(n) / 65536
    n = b.u(5)
    return sx, r0, r1, sy, b.s(n) / 20, b.s(n) / 20


def _cstr(d: bytes, o: int) -> tuple[str, int]:
    e = d.index(0, o)
    return d[o:e].decode("latin1"), e + 1


def _movie_tags(raw: bytes):  # noqa: ANN202
    """A movie's top level tags (CFX: zlib compressed, GFX: plain)."""
    if raw[:3] == b"CFX":
        d = raw[:8] + zlib.decompress(raw[8:])
    elif raw[:3] == b"GFX":
        d = raw
    else:
        raise ValueError(f"not a Scaleform movie ({raw[:3]!r})")
    b = _Bits(d, 8)
    _rect(b)
    return _tags(d, b.align() + 4)  # (after the stage: frame rate, frame count)


def _place2(body: bytes) -> tuple[int | None, tuple[float, ...] | None, str | None]:
    """A PlaceObject2's (character id, matrix as _affine, name) - None for what it doesn't have."""
    flags, o = body[0], 3
    cid = matrix = name = None
    if flags & 0x02:
        cid = struct.unpack_from("<H", body, o)[0]
        o += 2
    if flags & 0x04:
        b = _Bits(body, o)
        matrix = _affine(b)
        o = b.align()
    if flags & 0x08:  # colour transform with alpha: skipped
        b = _Bits(body, o)
        add, mul, n = b.u(1), b.u(1), b.u(4)
        b.u(n * 4 * (add + mul))
        o = b.align()
    if flags & 0x10:  # ratio
        o += 2
    if flags & 0x20:
        name, o = _cstr(body, o)
    return cid, matrix, name


def _tags(d: bytes, o: int):  # noqa: ANN202
    while o + 2 <= len(d):
        code_len = struct.unpack_from("<H", d, o)[0]
        o += 2
        code, ln = code_len >> 6, code_len & 0x3F
        if ln == 0x3F:
            ln = struct.unpack_from("<I", d, o)[0]
            o += 4
        yield code, d[o : o + ln]
        o += ln
        if code == 0:
            return


def _shape_bitmap(code: int, body: bytes) -> tuple[int, tuple[float, float, float, float], int] | None:
    """(shape id, bounds, bitmap id) of a DefineShape whose fill is a bitmap, else None."""
    cid = struct.unpack_from("<H", body)[0]
    b = _Bits(body, 2)
    bounds = _rect(b)
    o = b.align()
    if code == 83:  # DefineShape4: edge bounds + flags
        b = _Bits(body, o)
        _rect(b)
        o = b.align() + 1
    count = body[o]
    o += 1
    if count == 0xFF and code != 2:
        count = struct.unpack_from("<H", body, o)[0]
        o += 2
    for _ in range(count):
        kind = body[o]
        o += 1
        if kind == 0x00:  # solid
            o += 3 if code in (2, 22) else 4
        elif 0x40 <= kind <= 0x43:  # bitmap
            bmp = struct.unpack_from("<H", body, o)[0]
            b = _Bits(body, o + 2)
            _matrix(b)
            o = b.align()
            if bmp != 0xFFFF:  # 0xFFFF: Flash's placeholder "no bitmap" fill
                return cid, bounds, bmp
        else:  # gradients: not used by map movies
            return None
    return None


def _movie_raw(pkg: "Package", idx: int) -> bytes:
    """An SwfMovie export's movie (its RawData)."""
    props, _ = pkg.properties(pkg.export_data(idx))
    raw = props["RawData"][1]
    return raw[4 : 4 + struct.unpack_from("<i", raw)[0]]  # TArray<byte>: count + bytes
