"""
Images: DXT1 / DXT5 textures decoded to RGBA, RGBA (or BGRA) encoded as a PNG. Pure Python, no SDK.
"""

import struct
import zlib


def _rgb565(c: int) -> tuple[int, int, int]:
    return (c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31


def _colour_block(blk: bytes, o: int, dxt1: bool) -> list[tuple[int, int, int, int]]:
    c0, c1, bits = struct.unpack_from("<HHI", blk, o)
    a, b = _rgb565(c0), _rgb565(c1)
    if dxt1 and c0 <= c1:
        cols = [(*a, 255), (*b, 255), (*((x + y) // 2 for x, y in zip(a, b)), 255), (0, 0, 0, 0)]
    else:
        cols = [(*a, 255), (*b, 255), (*((2 * x + y) // 3 for x, y in zip(a, b)), 255),
                (*((x + 2 * y) // 3 for x, y in zip(a, b)), 255)]
    return [cols[bits >> (2 * i) & 3] for i in range(16)]


def decode_dxt(fmt: str, w: int, h: int, data: bytes) -> bytes:
    """DXT1 / DXT5 (the icons') -> RGBA bytes, row by row."""
    dxt1 = fmt == "PF_DXT1"
    if fmt not in ("PF_DXT1", "PF_DXT5"):
        raise ValueError(f"unsupported icon format {fmt}")
    size = 8 if dxt1 else 16
    out = bytearray(w * h * 4)
    bw = (w + 3) // 4
    for n in range(len(data) // size):
        bx, by = n % bw, n // bw
        if by * 4 >= h:
            break
        o = n * size
        alpha = None
        if not dxt1:
            a0, a1 = data[o], data[o + 1]
            abits = int.from_bytes(data[o + 2 : o + 8], "little")
            table = [a0, a1] + ([((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)] if a0 > a1
                                else [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255])
            alpha = [table[abits >> (3 * i) & 7] for i in range(16)]
            o += 8
        texels = _colour_block(data, o, dxt1)
        for i, (r, g, b, a) in enumerate(texels):
            x, y = bx * 4 + i % 4, by * 4 + i // 4
            if x < w and y < h:
                p = (y * w + x) * 4
                out[p : p + 4] = bytes((r, g, b, alpha[i] if alpha is not None else a))
    return bytes(out)


def png(w: int, h: int, rgba: bytes) -> bytes:
    """RGBA bytes -> a PNG (8-bit RGBA, no filter)."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + rgba[y * w * 4 : (y + 1) * w * 4] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def bgra_png(drawn: tuple[int, int, bytes] | None) -> bytes:
    """A drawing (width, height, BGRA - swfshape.render's) as a PNG - b"" for none."""
    if drawn is None:
        return b""
    w, h, bgra = drawn
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    return png(w, h, bytes(rgba))
