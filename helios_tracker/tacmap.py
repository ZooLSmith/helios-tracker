"""
Reads a level's tactical map (the in-game map screen's image) straight from the game's cooked
packages on disk. Pure Python, no SDK: runs on a background thread, and offline in tests.

A level's persistent package (e.g. Sanctuary_P.upk) holds:
- SwfMovie UI_TacticalMap_<Level>.<Level>_P: a small Scaleform movie drawing the map image(s) as
  shapes, in movie px;
- Texture2D UI_TacticalMap_<Level>.<Level>_P_I1 (..._I2, ...): the images (DXT5, stored inline).
World -> movie px uses the WillowTacticalMapVolume (see collector.py); this module only returns
the images and where each sits in movie px.

Package format notes (UE3, BL2 = file version 832): either "fully compressed" (the whole file is a
sequence of compressed chunks) or a plain summary whose chunk table maps the rest of the file to
compressed chunks. Chunks: tag, block size, sizes, block table, then LZO1X blocks.
"""

import struct
import time
import threading
import zlib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

TAG = 0x9E2A83C1
FILE_VERSION = 832

# region LZO1X


def lzo1x_decompress(src: bytes, out_len: int) -> bytes:
    """LZO1X decompression (port of the reference lzo1x_decompress_safe logic)."""
    out = bytearray()
    ip = 0

    def run_len(t: int, base: int) -> int:
        nonlocal ip
        if t == 0:
            while src[ip] == 0:
                t += 255
                ip += 1
            t += base + src[ip]
            ip += 1
        return t

    def copy_match(m_pos: int, length: int) -> None:
        if m_pos < 0:
            raise ValueError("lzo: lookbehind overrun")
        if len(out) - m_pos >= length:  # no overlap: one slice
            out.extend(out[m_pos : m_pos + length])
            return
        for _ in range(length):  # overlapping match: byte by byte
            out.append(out[m_pos])
            m_pos += 1

    state = "start"
    t = 0
    if src[0] > 17:
        t = src[0] - 17
        ip = 1
        out += src[ip : ip + t]
        ip += t
        state = "match_next_after_literals" if t < 4 else "first_literal_run"

    while True:
        if state == "start":
            t = src[ip]
            ip += 1
            if t >= 16:
                state = "match"
                continue
            t = run_len(t, 15)
            out += src[ip : ip + t + 3]
            ip += t + 3
            state = "first_literal_run"
            continue

        if state == "first_literal_run":
            t = src[ip]
            ip += 1
            if t >= 16:
                state = "match"
                continue
            m_pos = len(out) - (1 + 0x0800) - (t >> 2) - (src[ip] << 2)
            ip += 1
            copy_match(m_pos, 3)
            state = "match_done"
            continue

        if state == "match":
            if t >= 64:  # M2
                m_pos = len(out) - 1 - ((t >> 2) & 7) - (src[ip] << 3)
                ip += 1
                copy_match(m_pos, (t >> 5) - 1 + 2)
            elif t >= 32:  # M3
                t = run_len(t & 31, 31)
                m_pos = len(out) - 1 - ((src[ip] >> 2) + (src[ip + 1] << 6))
                ip += 2
                copy_match(m_pos, t + 2)
            elif t >= 16:  # M4
                m_pos = len(out) - ((t & 8) << 11)
                t = run_len(t & 7, 7)
                m_pos -= (src[ip] >> 2) + (src[ip + 1] << 6)
                ip += 2
                if m_pos == len(out):
                    break  # end of stream
                copy_match(m_pos - 0x4000, t + 2)
            else:  # M1
                m_pos = len(out) - 1 - (t >> 2) - (src[ip] << 2)
                ip += 1
                copy_match(m_pos, 2)
            state = "match_done"
            continue

        if state == "match_done":
            t = src[ip - 2] & 3
            if t == 0:
                state = "start"
                continue
            state = "match_next"
            continue

        if state in ("match_next", "match_next_after_literals"):
            out += src[ip : ip + t]
            ip += t
            t = src[ip]
            ip += 1
            state = "match"
            continue

    if len(out) != out_len:
        raise ValueError(f"lzo: got {len(out)} bytes, expected {out_len}")
    return bytes(out)


def decompress_chunk(data: bytes, o: int = 0) -> bytes:
    """A whole compressed chunk held in memory (e.g. LZO-compressed bulk data)."""
    tag, block_size, _comp, uncomp_total = struct.unpack_from("<IIII", data, o)
    if tag != TAG:
        raise ValueError("not a compressed chunk")
    o += 16
    n = (uncomp_total + block_size - 1) // block_size
    sizes = [struct.unpack_from("<II", data, o + 8 * i) for i in range(n)]
    o += 8 * n
    out = bytearray()
    for comp, uncomp in sizes:
        out += lzo1x_decompress(data[o : o + comp], uncomp)
        o += comp
    return bytes(out)


# endregion
# region Package reading


_thread = threading.local()


def set_pause(seconds: float) -> None:
    """This thread's pause after each decompressed block (gamescan: the game thread gets Python's lock back
    between blocks); 0: none."""
    _thread.pause = seconds


class Package:
    """Lazy reader: only the blocks holding the requested byte ranges are decompressed."""

    def __init__(self, path: Path) -> None:
        self.f = path.open("rb")
        self.blocks: list[tuple[int, int, int, int]] = []  # (uncomp offset, uncomp size, file offset, comp size)
        self._cache: dict[int, bytes] = {}
        try:
            self._index_chunks()
            self._read_summary()
        except Exception:
            self.f.close()
            raise

    def close(self) -> None:
        self.f.close()

    def _index_chunks(self) -> None:
        f = self.f
        f.seek(0, 2)
        end = f.tell()
        f.seek(0)
        tag, ver = struct.unpack("<II", f.read(8))
        if tag == TAG and ver & 0xFFFF == FILE_VERSION:  # plain summary + chunk table
            chunks = self._summary_chunks()
            if not chunks:  # uncompressed package
                self.blocks.append((0, end, 0, -1))
                self.size = end
                return
            self.blocks.append((0, chunks[0][0], 0, -1))  # the summary itself is stored raw
            for uoff, _usize, coff, _csize in chunks:
                f.seek(coff)
                self._read_chunk(uoff)
            self.size = chunks[-1][0] + chunks[-1][1]
            return
        f.seek(0)  # fully compressed
        uoff = 0
        while f.tell() < end:
            uoff = self._read_chunk(uoff)
        self.size = uoff

    def _read_chunk(self, uoff: int) -> int:
        f = self.f
        tag, block_size, _comp_total, uncomp_total = struct.unpack("<IIII", f.read(16))
        if tag != TAG:
            raise ValueError(f"not a compressed chunk at {f.tell() - 16}")
        n = (uncomp_total + block_size - 1) // block_size
        sizes = [struct.unpack("<II", f.read(8)) for _ in range(n)]
        foff = f.tell()
        for comp, uncomp in sizes:
            self.blocks.append((uoff, uncomp, foff, comp))
            uoff += uncomp
            foff += comp
        f.seek(foff)
        return uoff

    def _summary_chunks(self) -> list[tuple[int, int, int, int]]:
        f = self.f
        f.seek(0)
        head = f.read(65536)
        o = 12  # tag, version, licensee, total header size
        n = struct.unpack_from("<i", head, o)[0]
        o += 4 + (n if n >= 0 else -2 * n)  # folder name
        o += 4 + 6 * 4 + 4  # package flags, name/export/import count+offset, depends offset
        o += 4 + 4 + 4 + 4  # import/export guids offset + counts, thumbnail table offset
        o += 16  # guid
        gens = struct.unpack_from("<i", head, o)[0]
        o += 4 + 12 * gens
        o += 4 + 4  # engine, cooker version
        _flags, count = struct.unpack_from("<ii", head, o)
        o += 8
        return [struct.unpack_from("<iiii", head, o + 16 * i) for i in range(count)]

    def _block(self, i: int) -> bytes:
        if i not in self._cache:
            _uoff, usize, foff, csize = self.blocks[i]
            self.f.seek(foff)
            raw = self.f.read(usize if csize < 0 else csize)
            self._cache[i] = raw if csize < 0 else lzo1x_decompress(raw, usize)
            if csize >= 0 and (pause := getattr(_thread, "pause", 0)):
                time.sleep(pause)
        return self._cache[i]

    def read(self, offset: int, size: int) -> bytes:
        out = bytearray()
        for i, (uoff, usize, _, _) in enumerate(self.blocks):
            if uoff + usize <= offset or uoff >= offset + size:
                continue
            b = self._block(i)
            lo, hi = max(offset, uoff) - uoff, min(offset + size, uoff + usize) - uoff
            out += b[lo:hi]
        return bytes(out)

    def _read_summary(self) -> None:
        head = self.read(0, 4096)
        tag, ver, _lic = struct.unpack_from("<IHH", head, 0)
        if tag != TAG or ver != FILE_VERSION:
            raise ValueError(f"unexpected package tag/version {tag:#x}/{ver}")
        o = 12
        n = struct.unpack_from("<i", head, o)[0]
        o += 4 + (n if n >= 0 else -2 * n)  # folder name
        o += 4  # package flags
        (name_count, name_offset, export_count, export_offset,
         import_count, import_offset) = struct.unpack_from("<6i", head, o)
        self._read_names(name_count, name_offset)
        self._read_imports(import_count, import_offset)
        self._read_exports(export_count, export_offset)

    def _read_names(self, count: int, offset: int) -> None:
        data = self.read(offset, 64 * count + 65536)
        o = 0
        self.names: list[str] = []
        for _ in range(count):
            n = struct.unpack_from("<i", data, o)[0]
            o += 4
            if n >= 0:
                s = data[o : o + n - 1].decode("latin1")
                o += n
            else:
                s = data[o : o - 2 * n - 2].decode("utf-16-le")
                o += -2 * n
            o += 8  # flags
            self.names.append(s)

    def _name(self, idx: int, number: int = 0) -> str:
        n = self.names[idx]
        return f"{n}_{number - 1}" if number else n

    def _read_imports(self, count: int, offset: int) -> None:
        data = self.read(offset, 28 * count)
        self.imports = []
        for i in range(count):
            _cpkg, _, _cname, _, outer, oname, onum = struct.unpack_from("<iiiiiii", data, i * 28)
            self.imports.append({"outer": outer, "name": self._name(oname, onum)})

    def _read_exports(self, count: int, offset: int) -> None:
        data = self.read(offset, 128 * count + 65536)
        o = 0
        self.exports = []
        for _ in range(count):
            cls, _sup, outer, oname, onum, _arch = struct.unpack_from("<iiiiii", data, o)
            o += 24 + 8  # + object flags
            ssize, soff = struct.unpack_from("<ii", data, o)
            o += 8 + 4  # + export flags
            net_count = struct.unpack_from("<i", data, o)[0]
            o += 4 + 4 * net_count + 16 + 4  # net objects, package guid, package flags
            self.exports.append({"class": cls, "outer": outer, "name": self._name(oname, onum),
                                 "size": ssize, "offset": soff})

    def class_name(self, idx: int) -> str:
        cls = self.exports[idx]["class"]
        if cls < 0:
            return self.imports[-cls - 1]["name"]
        return self.exports[cls - 1]["name"] if cls > 0 else "Class"

    def path(self, idx: int) -> str:
        parts = []
        ref = idx + 1
        while ref:
            item = self.exports[ref - 1] if ref > 0 else self.imports[-ref - 1]
            parts.append(item["name"])
            ref = item["outer"]
        return ".".join(reversed(parts))

    def find(self, path: str, cls: str) -> int | None:
        """Export index by path name (case-insensitive, like the engine)."""
        want = path.lower()
        name = want.rpartition(".")[2]
        for i, e in enumerate(self.exports):
            if e["name"].lower() == name and self.path(i).lower() == want and self.class_name(i) == cls:
                return i
        return None

    def export_data(self, idx: int) -> bytes:
        e = self.exports[idx]
        return self.read(e["offset"], e["size"])

    def properties(self, data: bytes, o: int = 4) -> tuple[dict[str, tuple[str, bytes]], int]:
        """Tagged properties (after the 4-byte NetIndex): {name: (type, value bytes)}, end offset."""
        props: dict[str, tuple[str, bytes]] = {}
        while o + 8 <= len(data):
            pname = self.names[struct.unpack_from("<i", data, o)[0]]
            o += 8
            if pname == "None":
                return props, o
            ptype = self.names[struct.unpack_from("<i", data, o)[0]]
            size = struct.unpack_from("<i", data, o + 8)[0]
            o += 16
            if ptype == "BoolProperty":
                props[pname] = (ptype, data[o : o + 1])
                o += 1
                continue
            if ptype in ("StructProperty", "ByteProperty"):
                o += 8  # struct / enum name
            props[pname] = (ptype, data[o : o + size])
            o += size
        raise ValueError("unterminated property list")

    def name_value(self, value: bytes) -> str:
        return self.names[struct.unpack_from("<i", value)[0]]


# endregion
# region Scaleform movie


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


def parse_map_movie(raw: bytes) -> list[tuple[str, tuple[float, float, float, float]]]:
    """[(image file name, (x0, x1, y0, y1) in movie px)] for each map image placed on the stage."""
    images: dict[int, str] = {}
    shapes: dict[int, tuple[tuple[float, float, float, float], int]] = {}
    out = []
    for code, body in _movie_tags(raw):
        if code == 1009:  # GFx DefineExternalImage2: id u32, format, target w/h, export name, file name
            cid = struct.unpack_from("<I", body)[0]
            p = 10
            p += 1 + body[p]  # export name
            images[cid] = body[p + 1 : p + 1 + body[p]].decode("latin1")
        elif code in (2, 22, 32, 83):
            if (s := _shape_bitmap(code, body)) is not None and s[2] in images:
                shapes[s[0]] = (s[1], s[2])
        elif code == 26:  # PlaceObject2
            flags = body[0]
            if not flags & 0x02:
                continue
            cid = struct.unpack_from("<H", body, 3)[0]
            if cid not in shapes:
                continue
            sx = sy = 1.0
            tx = ty = 0.0
            if flags & 0x04:
                sx, sy, tx, ty = _matrix(_Bits(body, 5))
            (x0, x1, y0, y1), bmp = shapes[cid]
            out.append((images[bmp], (x0 * sx + tx, x1 * sx + tx, y0 * sy + ty, y1 * sy + ty)))
    return out


FOG_BLOB = "fog of war blob"  # the fog piece SharedWillowTacMaps exports (tools/dump_tacmap_movie.txt)


def parse_fog_pieces(raw: bytes) -> list[tuple[str, tuple[float, ...]]]:
    """A level movie's fog of war (tools/dump_tacmap_movie.txt): the fog blob it imports from
    SharedWillowTacMaps, placed once per discovery area - named by the area's short name
    ("SOUTHERNSHELF_PWDA_1"), its matrix (as _affine, movie px) stretching the blob over it. The map
    screen hides an area's blob once it's discovered. -> [(name, matrix)]."""
    blobs: set[int] = set()
    out = []
    for code, body in _movie_tags(raw):
        if code == 71:  # ImportAssets2: url, 2 reserved bytes, count, (id, name)...
            _url, p = _cstr(body, 0)
            count = struct.unpack_from("<H", body, p + 2)[0]
            p += 4
            for _ in range(count):
                cid = struct.unpack_from("<H", body, p)[0]
                name, p = _cstr(body, p + 2)
                if name == FOG_BLOB:
                    blobs.add(cid)
        elif code == 26:
            cid, matrix, name = _place2(body)
            if cid in blobs and name and matrix:
                out.append((name, matrix))
    return out


def parse_fog_blob(raw: bytes) -> tuple[str, tuple[float, float, float, float]] | None:
    """SharedWillowTacMaps' fog blob: the image file its tactical map frame shows and that shape's
    bounds (movie px: -128..128 - its 64 x 64 texture declared 256 x 256). The export is a sprite
    ("tacMap" frame: the map screen's blob, "miniMap": the minimap's); its first placement is the
    tacMap one. None if it isn't there."""
    images: dict[int, str] = {}
    shapes: dict[int, tuple[tuple[float, float, float, float], int]] = {}
    sprites: dict[int, int] = {}  # sprite id -> the first character it places
    exports: dict[str, int] = {}
    for code, body in _movie_tags(raw):
        if code == 1009:
            cid = struct.unpack_from("<I", body)[0]
            p = 10
            p += 1 + body[p]
            images[cid] = body[p + 1 : p + 1 + body[p]].decode("latin1")
        elif code in (2, 22, 32, 83):
            if (s := _shape_bitmap(code, body)) is not None and s[2] in images:
                shapes[s[0]] = (s[1], s[2])
        elif code == 39:
            sid = struct.unpack_from("<H", body)[0]
            for sub, sbody in _tags(body, 4):
                if sub == 26 and (cid := _place2(sbody)[0]) is not None:
                    sprites[sid] = cid
                    break
        elif code == 56:  # ExportAssets: count, (id, name)...
            count, p = struct.unpack_from("<H", body)[0], 2
            for _ in range(count):
                cid = struct.unpack_from("<H", body, p)[0]
                name, p = _cstr(body, p + 2)
                exports[name] = cid
    cid = exports.get(FOG_BLOB)
    shape = shapes.get(sprites.get(cid, cid)) if cid is not None else None
    return (images[shape[1]], shape[0]) if shape else None


# endregion
# region Textures


@dataclass
class MapImage:
    name: str
    format: str  # EPixelFormat, e.g. "PF_DXT5" - decoded by the web page
    width: int
    height: int
    data: bytes  # top mip, as stored
    bounds: tuple[float, float, float, float]  # x0, x1, y0, y1 in movie px


BULK_SEPARATE_FILE = 0x01
BULK_ZLIB = 0x02
BULK_LZO = 0x10
BULK_UNUSED = 0x20


def _texture(pkg: Package, idx: int) -> tuple[str, int, int, bytes]:
    data = pkg.export_data(idx)
    props, end = pkg.properties(data)
    fmt = pkg.name_value(props["Format"][1]) if "Format" in props else "PF_A8R8G8B8"
    sx = struct.unpack("<i", props["SizeX"][1])[0]
    sy = struct.unpack("<i", props["SizeY"][1])[0]
    # Native tail: 16 bytes (BL2: source art / guid), mip count, then per mip a bulk data header
    # (flags, element count, size on disk, offset in file), the data, SizeX, SizeY.
    for skip in (16, 0):
        o = end + skip
        if o + 20 > len(data):
            continue
        mips = struct.unpack_from("<i", data, o)[0]
        flags, _count, size, _off = struct.unpack_from("<iiii", data, o + 4)
        if not 0 < mips < 16 or size < 0 or o + 20 + size + 8 > len(data):
            continue
        if flags & (BULK_SEPARATE_FILE | BULK_UNUSED):
            raise ValueError(f"texture data not stored inline (bulk flags {flags:#x})")
        body = data[o + 20 : o + 20 + size]
        w, h = struct.unpack_from("<ii", data, o + 20 + size)
        if (w, h) != (sx, sy):
            continue
        if flags & BULK_LZO:
            body = decompress_chunk(body)
        elif flags & BULK_ZLIB:
            raise ValueError("zlib-compressed texture data isn't supported")
        return fmt, w, h, body
    raise ValueError("couldn't find the texture's top mip")


_kept: dict | None = None  # gamework's worker: packages kept open between its jobs (path -> Package), oldest first
_textures: dict = {}  # and their textures' top mips ((path, export) -> _texture's), oldest first
KEEP_PACKAGES = 4  # (BL2's: 1.5 - 17 MB each)
KEEP_TEXTURES = 6  # (an atlas: 1024 x 1024 DXT5, 1 MB)


def keep_open(on: bool) -> None:
    """The worker's (a session long): opened packages and decoded top mips kept for the next jobs - an icon out
    of WillowGame.upk costs its header tables (~1.3 s of LZO) and its atlas once, not per icon."""
    global _kept  # noqa: PLW0603
    if not on and _kept:
        for pkg in _kept.values():
            pkg.close()
    _kept = {} if on else None
    _textures.clear()


@contextmanager
def opened(path: Path):  # noqa: ANN201
    """A package, closed after - or, in the worker (keep_open), kept for the next job."""
    if _kept is None:
        pkg = Package(path)
        try:
            yield pkg
        finally:
            pkg.close()
        return
    key = str(path)
    pkg = _kept.pop(key, None) or Package(path)
    _kept[key] = pkg  # (the most recent last)
    while len(_kept) > KEEP_PACKAGES:
        _kept.pop(next(iter(_kept))).close()
    yield pkg


def texture(path: Path, pkg: Package, idx: int) -> tuple[str, int, int, bytes]:
    """_texture, kept in the worker (the card icons: one atlas, many icons)."""
    if _kept is None:
        return _texture(pkg, idx)
    key = (str(path), idx)
    if key not in _textures:
        _textures[key] = _texture(pkg, idx)
        while len(_textures) > KEEP_TEXTURES:
            _textures.pop(next(iter(_textures)))
    return _textures[key]


@dataclass
class MapFog:
    blob: MapImage  # the fog piece (bounds: its shape's, around 0)
    pieces: list[tuple[str, tuple[float, ...]]]  # (area short name, matrix placing the blob: _affine)


SHARED_TACMAPS = "SharedWillowTacMaps.SharedWillowTacMaps"


def _movie_raw(pkg: Package, idx: int) -> bytes:
    props, _ = pkg.properties(pkg.export_data(idx))
    raw = props["RawData"][1]
    return raw[4 : 4 + struct.unpack_from("<i", raw)[0]]  # TArray<byte>: count + bytes


def load_fog(package_file: Path, movie_path: str) -> MapFog | None:
    """The level's fog of war: SharedWillowTacMaps' blob (its texture, cooked into the level's package
    with the movie) and where the level's movie places it. None if either is missing."""
    pkg = Package(package_file)
    try:
        idx, shared = pkg.find(movie_path, "SwfMovie"), pkg.find(SHARED_TACMAPS, "SwfMovie")
        if idx is None or shared is None:
            return None
        pieces = parse_fog_pieces(_movie_raw(pkg, idx))
        blob = parse_fog_blob(_movie_raw(pkg, shared))
        if not pieces or blob is None:
            return None
        file_name, bounds = blob
        stem = file_name.rpartition(".")[0] or file_name
        tex = pkg.find(f"{SHARED_TACMAPS.partition('.')[0]}.{stem}", "Texture2D")
        if tex is None:
            return None
        fmt, w, h, body = _texture(pkg, tex)
        return MapFog(MapImage(stem, fmt, w, h, body, bounds), pieces)
    finally:
        pkg.close()


def load_tactical_map(package_file: Path, movie_path: str) -> list[MapImage]:
    """The images of the tactical map movie `movie_path` (e.g. "UI_TacticalMap_Sanctuary.Sanctuary_P")."""
    pkg = Package(package_file)
    try:
        idx = pkg.find(movie_path, "SwfMovie")
        if idx is None:
            raise FileNotFoundError(f"{movie_path} not in {package_file.name}")
        raw = _movie_raw(pkg, idx)
        movie_pkg = movie_path.rpartition(".")[0]
        out = []
        for file_name, bounds in parse_map_movie(raw):
            stem = file_name.rpartition(".")[0] or file_name
            tex = pkg.find(f"{movie_pkg}.{stem}", "Texture2D")
            if tex is None:
                raise FileNotFoundError(f"texture {movie_pkg}.{stem} not in {package_file.name}")
            fmt, w, h, body = _texture(pkg, tex)
            out.append(MapImage(stem, fmt, w, h, body, bounds))
        return out
    finally:
        pkg.close()


# endregion
