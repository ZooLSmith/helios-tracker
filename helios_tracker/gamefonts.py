"""
The game's own UI fonts as web fonts (files only: no SDK, no UObjects - run on a background thread).

BL2's Scaleform menus take their fonts from a font library movie: Startup.upk's SwfMovie
UI_FontsEn.FontsEn (tools/probes/find_fonts.txt) - WillowBody (menus, missions), Compacta Bd BT (headings, the
HUD), Chintzy CPU BRK - each a GFx DefineCompactedFont tag (1005): vector glyphs in Scaleform's compact
encoding (below, decoded from the data: tools/probes/find_fonts.py). They're rebuilt here as TrueType fonts
(the glyphs are quadratic curves already) and served to the page (/font/<slug>.ttf) - extracted at run
time from the player's install, never stored in the repo.

DefineCompactedFont (after the tag's font id, u16), offsets from the data's start:
    name (null-terminated), flags u16, em size u16 (256), ascent s16, descent s16, leading s16,
    glyph count u32, tables offset u32 (from the glyphs' start = the end of this header)
    glyphs: bounding box (4 x SInt15: x0 y0 x1 y1, y down), contour count (UInt15), per contour:
        move to (2 x SInt15, absolute), edge count (UInt30: count << 1 | shared - shared: the value >> 1
        is the offset of an earlier contour's count, its edges reused), edges (4-bit type in the low
        nibble, then packed signed deltas): H12 / H20 (dx), V12 / V20 (dy), L6 / L10 / L14 / L18
        (dx, dy), C5 ... C19 (control dx dy from the pen, anchor dx dy from the control); the last edge
        back to the move to is left out (closed implicitly)
    glyph table: glyph count x (code u16, advance s16, glyph offset u32)
    kerning: count (UInt30), then (code u16, code u16, adjustment s16) each
    SInt15 / UInt15: 1 byte (value << 1) or 2 bytes (value << 1 | 1); UInt30: the low 2 bits = extra bytes
"""

import re
import struct
import threading
import zlib
from dataclasses import dataclass
from pathlib import Path

from . import gamework
from .swf import _Bits, _rect, _tags
from .upk import Package, opened



# region Scaleform compacted fonts


@dataclass
class Glyph:
    code: int
    advance: int
    contours: list[list[tuple[str, int, int]]]  # per contour: ("on" / "off", x, y) points, y down (SWF)


@dataclass
class GameFont:
    name: str
    flags: int
    em: int
    ascent: int
    descent: int
    leading: int
    glyphs: list[Glyph]
    kerning: dict[tuple[int, int], int]  # (code, code) -> adjustment

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


def _sbits(v: int, n: int) -> int:
    return v - (1 << n) if v & (1 << (n - 1)) else v


# edge type -> (bytes, kind, bits per value)
_EDGES = {0: (2, "h", 12), 1: (3, "h", 20), 2: (2, "v", 12), 3: (3, "v", 20),
          4: (2, "l", 6), 5: (3, "l", 10), 6: (4, "l", 14), 7: (5, "l", 18)}
for _i, _bits in enumerate((5, 7, 9, 11, 13, 15, 17, 19)):
    _EDGES[8 + _i] = ((4 + 4 * _bits) // 8, "c", _bits)


class _Reader:
    def __init__(self, d: bytes) -> None:
        self.d = d

    def u15(self, o: int) -> tuple[int, int]:
        if self.d[o] & 1:
            return struct.unpack_from("<H", self.d, o)[0] >> 1, o + 2
        return self.d[o] >> 1, o + 1

    def s15(self, o: int) -> tuple[int, int]:
        if self.d[o] & 1:
            return _sbits(struct.unpack_from("<H", self.d, o)[0] >> 1, 15), o + 2
        return _sbits(self.d[o] >> 1, 7), o + 1

    def u30(self, o: int) -> tuple[int, int]:
        n = self.d[o] & 3
        return int.from_bytes(self.d[o : o + n + 1], "little") >> 2, o + n + 1

    def edges(self, o: int, x: int, y: int) -> list[tuple[str, int, int]]:
        """A contour's edges from its count field at o (the pen at x, y): its points after the move to."""
        count, o = self.u30(o)
        if count & 1:
            raise ValueError("a shared contour pointing at another shared one")
        pts = []
        for _ in range(count >> 1):
            size, kind, bits = _EDGES[self.d[o] & 0x0F]
            v = int.from_bytes(self.d[o : o + size], "little") >> 4
            o += size
            mask = (1 << bits) - 1
            if kind == "h":
                x += _sbits(v, bits)
            elif kind == "v":
                y += _sbits(v, bits)
            elif kind == "l":
                x, y = x + _sbits(v & mask, bits), y + _sbits((v >> bits) & mask, bits)
            else:
                cx, cy = x + _sbits(v & mask, bits), y + _sbits((v >> bits) & mask, bits)
                x, y = cx + _sbits((v >> 2 * bits) & mask, bits), cy + _sbits((v >> 3 * bits) & mask, bits)
                pts.append(("off", cx, cy))
            pts.append(("on", x, y))
        return pts

    def glyph(self, o: int) -> list[list[tuple[str, int, int]]]:
        for _ in range(4):  # its bounding box (recomputed from the points)
            _, o = self.s15(o)
        n, o = self.u15(o)
        contours = []
        for _ in range(n):
            mx, o = self.s15(o)
            my, o = self.s15(o)
            count, after = self.u30(o)
            if count & 1:  # shared: an earlier contour's edges (its count field's offset)
                pts = self.edges(count >> 1, mx, my)
                o = after
            else:
                pts = self.edges(o, mx, my)
                o = self._skip_edges(o)
            contour = [("on", mx, my), *pts]
            if len(contour) > 1 and contour[-1][0] == "on" and contour[-1][1:] == contour[0][1:]:
                contour.pop()  # (an explicit close)
            if len(contour) >= 3:
                contours.append(contour)
        return contours

    def _skip_edges(self, o: int) -> int:
        count, o = self.u30(o)
        for _ in range(count >> 1):
            o += _EDGES[self.d[o] & 0x0F][0]
        return o


def parse_compacted_font(body: bytes) -> GameFont:
    """A DefineCompactedFont tag's body (its font id first) -> the font (see the module's docstring)."""
    d = body[2:]
    r = _Reader(d)
    end = d.index(0)
    name = d[:end].decode("latin1")
    flags, em, ascent, descent, leading = struct.unpack_from("<HHhhh", d, end + 1)
    count, tables = struct.unpack_from("<II", d, end + 11)
    start = end + 19
    table = start + tables
    glyphs = []
    for i in range(count):
        code, advance, offset = struct.unpack_from("<HhI", d, table + 8 * i)
        glyphs.append(Glyph(code, advance, r.glyph(offset)))
    kerning: dict[tuple[int, int], int] = {}
    o = table + 8 * count
    if o < len(d):
        pairs, o = r.u30(o)
        for i in range(pairs):
            a, b, adj = struct.unpack_from("<HHh", d, o + 6 * i)
            kerning[(a, b)] = adj
    return GameFont(name, flags, em, ascent, descent, leading, glyphs, kerning)


def movie_fonts(raw: bytes) -> list[GameFont]:
    """Every compacted font of a Scaleform movie (its SwfMovie RawData)."""
    if raw[:3] == b"CFX":
        d = raw[:8] + zlib.decompress(raw[8:])
    elif raw[:3] == b"GFX":
        d = raw
    else:
        raise ValueError(f"not a Scaleform movie ({raw[:3]!r})")
    b = _Bits(d, 8)
    _rect(b)
    return [parse_compacted_font(body) for code, body in _tags(d, b.align() + 4) if code == 1005]


# endregion
# region TrueType


def _signed_area(pts: list[tuple[str, int, int]]) -> float:
    return sum(pts[i][1] * pts[(i + 1) % len(pts)][2] - pts[(i + 1) % len(pts)][1] * pts[i][2] for i in range(len(pts))) / 2


def _inside(x: float, y: float, pts: list[tuple[str, int, int]]) -> bool:
    hit, n = False, len(pts)
    for i in range(n):
        x1, y1, x2, y2 = pts[i][1], pts[i][2], pts[(i + 1) % n][1], pts[(i + 1) % n][2]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def _ttf_contours(contours: list[list[tuple[str, int, int]]]) -> list[list[tuple[str, int, int]]]:
    """The glyph's contours for TrueType: y up, oriented for the non-zero rule (Flash fills even-odd):
    an outline inside an even number of others clockwise, a hole (odd) counter-clockwise."""
    flipped = [[(k, x, -y) for k, x, y in c] for c in contours]
    out = []
    for i, c in enumerate(flipped):
        probe = next(((x, y) for k, x, y in c if k == "on"), (c[0][1], c[0][2]))
        # a point just off the contour's first on-curve point, tested against every other contour
        depth = sum(1 for j, other in enumerate(flipped) if j != i and _inside(probe[0] + 0.01, probe[1] + 0.01, other))
        clockwise = _signed_area(c) < 0
        if clockwise != (depth % 2 == 0):
            c = [c[0], *reversed(c[1:])]
        out.append(c)
    return out


def _checksum(data: bytes) -> int:
    data += b"\0" * (-len(data) % 4)
    return sum(struct.unpack(f">{len(data) // 4}I", data)) & 0xFFFFFFFF


def _name_table(family: str, style: str) -> bytes:
    records = {1: family, 2: style, 3: f"{family} {style} (Helios Tracker)", 4: f"{family} {style}".strip(),
               5: "Version 1.0", 6: re.sub(r"[^A-Za-z0-9-]", "", f"{family}-{style}")}
    strings, recs = b"", b""
    for nid, text in records.items():
        s = text.encode("utf-16-be")
        recs += struct.pack(">HHHHHH", 3, 1, 0x409, nid, len(s), len(strings))
        strings += s
    return struct.pack(">HHH", 0, len(records), 6 + 12 * len(records)) + recs + strings


def _cmap_table(codes: dict[int, int]) -> bytes:
    """Format 4 (the BMP), one subtable (Windows Unicode): code -> glyph index."""
    segs, keys = [], sorted(codes)
    i = 0
    while i < len(keys):  # runs of consecutive codes with consecutive glyph indices
        j = i
        while j + 1 < len(keys) and keys[j + 1] == keys[j] + 1 and codes[keys[j + 1]] == codes[keys[j]] + 1:
            j += 1
        segs.append((keys[i], keys[j], (codes[keys[i]] - keys[i]) & 0xFFFF))
        i = j + 1
    segs.append((0xFFFF, 0xFFFF, 1))
    n = len(segs)
    search = 2 * (1 << (n.bit_length() - 1))
    sub = struct.pack(f">{n}H", *(e for s, e, d in segs)) + b"\0\0" + struct.pack(f">{n}H", *(s for s, e, d in segs)) \
        + struct.pack(f">{n}H", *(d for s, e, d in segs)) + struct.pack(f">{n}H", *(0 for _ in segs))
    head = struct.pack(">HHHH", 2 * n, search, (search // 2).bit_length() - 1, 2 * n - search)
    body = head + sub
    fmt4 = struct.pack(">HHH", 4, 6 + len(body), 0) + body
    return struct.pack(">HHHHI", 0, 1, 3, 1, 12) + fmt4


def to_ttf(font: GameFont) -> bytes:
    """The font as a TrueType file: glyph 0 = an empty .notdef, then the game's in its table's order;
    its metrics, a Windows Unicode cmap, its kerning (a 'kern' table)."""
    bold = bool(font.flags & 1) or "bd" in font.name.lower().split() or "bold" in font.name.lower()
    glyphs = [Glyph(0, font.em // 2, []), *font.glyphs]
    glyf, loca, hmtx = b"", [], b""
    boxes, max_pts, max_contours = [], 0, 0
    for g in glyphs:
        loca.append(len(glyf))
        contours = _ttf_contours(g.contours)
        if not contours:
            boxes.append(None)
            hmtx += struct.pack(">Hh", max(0, g.advance), 0)
            continue
        xs = [x for c in contours for _, x, _ in c]
        ys = [y for c in contours for _, _, y in c]
        box = (min(xs), min(ys), max(xs), max(ys))
        boxes.append(box)
        ends, n = [], 0
        for c in contours:
            n += len(c)
            ends.append(n - 1)
        max_pts, max_contours = max(max_pts, n), max(max_contours, len(contours))
        flags = bytes(1 if k == "on" else 0 for c in contours for k, _, _ in c)
        pts = [(x, y) for c in contours for _, x, y in c]
        dx = [pts[0][0]] + [pts[i][0] - pts[i - 1][0] for i in range(1, len(pts))]
        dy = [pts[0][1]] + [pts[i][1] - pts[i - 1][1] for i in range(1, len(pts))]
        data = struct.pack(">hhhhh", len(contours), *box) + struct.pack(f">{len(ends)}H", *ends) + b"\0\0" + flags \
            + struct.pack(f">{len(dx)}h", *dx) + struct.pack(f">{len(dy)}h", *dy)
        glyf += data + b"\0" * (-len(data) % 4)
        hmtx += struct.pack(">Hh", max(0, g.advance), box[0])
    loca.append(len(glyf))
    real = [b for b in boxes if b]
    fbox = (min(b[0] for b in real), min(b[1] for b in real), max(b[2] for b in real), max(b[3] for b in real)) if real else (0, 0, 0, 0)
    advances = [max(0, g.advance) for g in glyphs]
    codes = {g.code: i for i, g in enumerate(glyphs) if i and g.code < 0xFFFF}
    lsbs = [b[0] for b in real] or [0]
    rsbs = [advances[i] - boxes[i][2] for i in range(len(glyphs)) if boxes[i]] or [0]
    tables = {
        "head": struct.pack(">IIIIHHQQhhhhHHhhh", 0x00010000, 0x00010000, 0, 0x5F0F3CF5, 0x000B, font.em, 0, 0,
                            *fbox, 1 if bold else 0, 8, 2, 1, 0) + b"",
        "hhea": struct.pack(">IhhhHhhhhhhhhhhhH", 0x00010000, font.ascent, -font.descent, font.leading, max(advances),
                            min(lsbs), min(rsbs), max(b[2] for b in real) if real else 0, 1, 0, 0, 0, 0, 0, 0, 0,
                            len(glyphs)),
        "maxp": struct.pack(">IHHHHHHHHHHHHHH", 0x00010000, len(glyphs), max_pts, max_contours, 0, 0, 2, 0, 0, 0, 0,
                            0, 0, 0, 0),
        "OS/2": struct.pack(">HhHHHhhhhhhhhhhh10sIIII4sHHHhhhHHII", 4, sum(advances) // max(1, len(advances)),
                            700 if bold else 400, 5, 0, font.em // 2, font.em // 2, 0, font.em // 8, font.em // 2,
                            font.em // 2, 0, font.em // 3, font.em // 16, font.em // 4, 0, b"\0" * 10,
                            0b11, 0, 0, 0, b"HLTR", 0x20 if bold else 0x40, min(codes) if codes else 0,
                            min(0xFFFF, max(codes)) if codes else 0, font.ascent, -font.descent, font.leading,
                            max(font.ascent, fbox[3]), max(font.descent, -fbox[1]), 1, 0)
                + struct.pack(">hhHHH", font.em // 2, int(font.em * 0.7), 0, 32, 2),
        "hmtx": hmtx,
        "cmap": _cmap_table(codes),
        "loca": struct.pack(f">{len(loca)}I", *loca),
        "glyf": glyf,
        "name": _name_table(font.name, "Bold" if bold else "Regular"),
        "post": struct.pack(">IIhhIIIII", 0x00030000, 0, -font.em // 10, font.em // 20, 0, 0, 0, 0, 0),
    }
    index = {g.code: i for i, g in enumerate(glyphs) if i}
    pairs = sorted((index[a], index[b], v) for (a, b), v in font.kerning.items() if a in index and b in index)
    if pairs:
        n = len(pairs)
        search = 6 * (1 << (n.bit_length() - 1))
        sub = struct.pack(">HHHHHHH", 0, 14 + 6 * n, 0x0001, n, search, (search // 6).bit_length() - 1, 6 * n - search)
        tables["kern"] = struct.pack(">HH", 0, 1) + sub + b"".join(struct.pack(">HHh", a, b, v) for a, b, v in pairs)
    # the file: the table directory (sorted tags), the tables (4-byte aligned), head's checksum adjustment
    tags = sorted(tables)
    n = len(tags)
    search = 16 * (1 << (n.bit_length() - 1))
    offset = 12 + 16 * n
    directory, body = b"", b""
    for tag in tags:
        data = tables[tag]
        directory += struct.pack(">4sIII", tag.encode(), _checksum(data), offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    out = bytearray(struct.pack(">IHHHH", 0x00010000, n, search, (search // 16).bit_length() - 1, 16 * n - search)
                    + directory + body)
    head_at = 12 + 16 * n + sum(len(tables[t]) + (-len(tables[t]) % 4) for t in tags[: tags.index("head")])
    struct.pack_into(">I", out, head_at + 8, (0xB1B0AFBA - _checksum(bytes(out))) & 0xFFFFFFFF)
    return bytes(out)


# endregion


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def movie_raw(pkg: Package, idx: int) -> bytes:
    props, _ = pkg.properties(pkg.export_data(idx))
    raw = props["RawData"][1]
    return raw[4 : 4 + struct.unpack_from("<i", raw)[0]]


def font_headers(raw: bytes) -> list[tuple[int, str, int]]:
    """A movie's compacted fonts, their headers only (cheap: no glyph decoded): [(the tag's index among its
    DefineCompactedFont tags, the font's name, its glyph count)]."""
    if raw[:3] == b"CFX":
        d = raw[:8] + zlib.decompress(raw[8:])
    elif raw[:3] == b"GFX":
        d = raw
    else:
        return []
    b = _Bits(d, 8)
    _rect(b)
    out, n = [], 0
    for code, body in _tags(d, b.align() + 4):
        if code == 1005:
            data = body[2:]
            end = data.index(0)
            count = struct.unpack_from("<I", data, end + 11)[0]
            out.append((n, data[:end].decode("latin1"), count))
            n += 1
    return out


# The game's font libraries, one per language (both games' DefaultEngine.ini load them all: UI_FontsEn / Jp / Kr and
# BL2's Twn, the Pre-Sequel's Ru) - the game's code picks its language's. The same font name is in each, drawn
# differently: the Pre-Sequel's UI_FontsRu WillowBody has narrower Latin letters than UI_FontsEn's (BL2's and the
# Pre-Sequel's English ones are the same). Its language (Object.GetLanguage: "INT", "RUS"...) -> its library; ours,
# no data says it (the user's call: follow the game's language - an item's name in its letters, no missing glyphs).
FONT_LIBRARIES = {"RUS": "UI_FontsRu", "JPN": "UI_FontsJp", "KOR": "UI_FontsKr", "TWN": "UI_FontsTwn"}
DEFAULT_LIBRARY = "UI_FontsEn"  # (the Latin languages': INT, FRA, DEU, ESN, ITA)


def font_library(language: str) -> str:
    """The font library the game uses in `language` (its GetLanguage: "INT", "RUS"...)."""
    return FONT_LIBRARIES.get(str(language or "").upper(), DEFAULT_LIBRARY)


class GameFonts:
    """The game's UI fonts, found cheaply, converted on demand: every compacted font of the packages' Scaleform
    movies (the engine config's packages: gamecards.engine_packages - no movie named: BL2's library is Startup.upk's
    UI_FontsEn.FontsEn, a Pre-Sequel's wherever its config says), each font name's fullest version (menus embed
    subsets of WillowBody: the font library has it all). Scanning reads only the fonts' headers (the Asian fonts'
    13,000+ glyphs: a minute to convert - only when asked for); get(slug) converts once. Thread-safe; dict-like
    for the server (get)."""

    def __init__(self, catalogue: dict | None = None) -> None:
        self._lock = threading.Lock()
        self._ttf: dict[str, bytes | None] = {}
        self.catalogue: dict[str, tuple[str, int, Path, int, int]] = catalogue or {}  # slug -> (name, glyphs, package, export, n)

    def set_catalogue(self, catalogue: dict) -> None:
        with self._lock:
            self.catalogue = catalogue
            self._ttf = {}

    def names(self) -> list[str]:
        return [name for name, *_ in self.catalogue.values()]

    def get(self, slug: str, default: bytes | None = None) -> bytes | None:
        """A font as TrueType: converted by gamework (its subinterpreter; cached on disk), kept."""
        with self._lock:
            if slug in self._ttf:
                return self._ttf[slug] if self._ttf[slug] is not None else default
            entry = self.catalogue.get(slug)
        data = None
        if entry is not None:
            _name, _count, path, idx, n = entry
            data = gamework.asset({"do": "font", "package": str(path), "export": idx, "n": n}, [path])
        with self._lock:
            self._ttf[slug] = data
        return data if data is not None else default


def font_ttf(path: Path, idx: int, n: int) -> bytes:
    """A movie's n-th compacted font as TrueType (gamework's job)."""
    with opened(path) as pkg:  # (the worker: kept open for the next job)
        return to_ttf(movie_fonts(movie_raw(pkg, idx))[n])


FONTS = GameFonts()  # the mod's: its catalogue from gamescan (the server serves it: /font/<slug>.ttf)


def set_catalogue(catalogue: dict) -> None:
    FONTS.set_catalogue(catalogue)
