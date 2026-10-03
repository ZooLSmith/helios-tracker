"""
Reads Unreal Engine 3 packages (.upk / .umap / .u) straight from disk: the summary, names, imports, exports, tagged
properties, textures' top mips. Pure Python, no SDK: on background threads, in gamework's worker, offline in tests.

This is BL2's format (file version 832; the Pre-Sequel's too). Another game's format is a subclass in its own file
(upk_bl1.py: Borderlands 1), overriding only what differs - its code opens its packages with it; nothing here asks
which game it is.

Package format notes (UE3, BL2 = file version 832): either "fully compressed" (the whole file is a
sequence of compressed chunks) or a plain summary whose chunk table maps the rest of the file to
compressed chunks. Chunks: tag, block size, sizes, block table, then LZO1X blocks.
"""

import struct
import threading
import time
from contextlib import contextmanager
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

    VERSION = FILE_VERSION  # the file version this reader reads (a subclass: its own format's)
    # a texture's native data after its properties, before its mip count: BL2's 16 (source art / guid), or none
    TEXTURE_HEADS: tuple[int, ...] = (16, 0)
    SUMMARY_TABLES = 16  # the summary's bytes after the depends offset: import / export guids offset + counts, thumbnails
    BOOL_SIZE = 1  # a BoolProperty's value
    NAMED_TYPES = ("StructProperty", "ByteProperty")  # the property types whose tag carries a name (struct / enum)

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
        if tag == TAG and ver & 0xFFFF == self.VERSION:  # plain summary + chunk table
            chunks = self._summary_chunks()
            if not chunks:  # uncompressed package
                self.blocks.append((0, end, 0, -1))
                self.size = end
                return
            self.blocks.append((0, chunks[0][0], 0, -1))  # the summary itself is stored raw
            for uoff, usize, coff, csize in chunks:
                self._index_chunk(uoff, usize, coff, csize)
            self.size = chunks[-1][0] + chunks[-1][1]
            return
        f.seek(0)  # fully compressed
        uoff = 0
        while f.tell() < end:
            uoff = self._read_chunk(uoff)
        self.size = uoff

    def _index_chunk(self, uoff: int, _usize: int, coff: int, _csize: int) -> None:
        """One entry of the summary's chunk table: a compressed chunk at `coff` (its blocks indexed)."""
        self.f.seek(coff)
        self._read_chunk(uoff)

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
        o += self.SUMMARY_TABLES  # import/export guids offset + counts, thumbnail table offset
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
        if tag != TAG or ver != self.VERSION:
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
        return self.ref_path(idx + 1)

    def ref_path(self, ref: int) -> str:
        """An object reference's path (an ObjectProperty's value: > 0 an export, its index + 1; < 0 an import - another
        package's object, its path as the engine resolves it: "SharedSkillIcons_Soldier.Skillicon-willing")."""
        parts = []
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
                props[pname] = (ptype, data[o : o + self.BOOL_SIZE])
                o += self.BOOL_SIZE
                continue
            if ptype in self.NAMED_TYPES:
                o += 8  # struct / enum name
            props[pname] = (ptype, data[o : o + size])
            o += size
        raise ValueError("unterminated property list")

    def name_value(self, value: bytes) -> str:
        return self.names[struct.unpack_from("<i", value)[0]]


# endregion
# region Textures


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
    for skip in pkg.TEXTURE_HEADS:
        o = end + skip
        if o + 20 > len(data):
            continue
        mips = struct.unpack_from("<i", data, o)[0]
        flags, _count, size, offset = struct.unpack_from("<iiii", data, o + 4)
        if flags & BULK_SEPARATE_FILE and not flags & BULK_UNUSED and 0 < mips < 16 and size > 0 and o + 28 <= len(data):
            # its pixels in the texture file cache (TextureFileCacheName + ".tfc", next to the package: the eridium
            # pickup icon's, in Startup.upk's Textures.tfc) at `offset`, `size` bytes (LZO: a compressed chunk)
            w, h = struct.unpack_from("<ii", data, o + 20)
            if (w, h) != (sx, sy) or "TextureFileCacheName" not in props:
                continue
            cache = Path(pkg.f.name).with_name(pkg.name_value(props["TextureFileCacheName"][1]) + ".tfc")
            with cache.open("rb") as f:
                f.seek(offset)
                body = f.read(size)
            if flags & BULK_LZO:
                body = decompress_chunk(body)
            elif flags & BULK_ZLIB:
                raise ValueError("zlib-compressed texture data isn't supported")
            return fmt, w, h, body
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


# endregion
