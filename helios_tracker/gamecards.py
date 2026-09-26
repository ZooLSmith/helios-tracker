"""
The item card's icons - manufacturer logos, element icons, item type icons - from the game's own UI movies, as PNGs
(files only: no SDK, no UObjects - safe on the server's threads).

Nothing here names a BL2 movie, sprite or package: the game's data drives it (so another UE3 / Scaleform
Borderlands - the Pre-Sequel - should work as is):
- the packages searched: the always-loaded ones, from the engine's config (Engine/Config/BaseEngine.ini and
  <Game>/Config/DefaultEngine.ini: [Engine.ScriptPackages], [Engine.StartupPackages]) and the cooked Startup;
- the icons: every sprite of their Scaleform movies whose frames show an atlas bitmap, by frame label (a "list":
  BL2's item card has one per manufacturer - frames "maliwan", "jakobs"... -, per element, per item type);
- an icon is **layered**: the sprite placing a list may place several with the same labels (BL2's "manufacturer
  logos": a larger black one under, "bgdClip" - the outline -, a smaller one over it, "tintClip" - the fill the
  game tints; the weapon type the same), drawn in their depth order (the names aren't used);
- which list: the one whose labels best match the game's own keys, given by the mod from the loaded definitions
  (set_keys: ManufacturerDefinition.FlashLabelName, WeaponTypeDefinition.ScaleformFrameName, the damage types'
  enum); a type / element list also nearest the chosen manufacturer's in the movie's tree (BL2's "item card"
  places all three - other movies have type lists too: the ammo's, the vendors' tabs), then the largest;
- the art: a GFx DefineSubImage (tag 1008: bitmap id, atlas image, the rectangle) of a DefineExternalImage2 atlas
  (tag 1009: its texture, cooked next to the movie; its declared size vs the texture's: the scale).
Extracted from the player's install at run time (decoded by gamework, its subinterpreter; cached on disk), never
stored in the repo.
"""

import re
import struct
import threading
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import gamework
from .gameicons import decode_dxt, png
from .tacmap import _Bits, _matrix, _rect, _shape_bitmap, _tags, opened, texture

KINDS = ("manufacturer", "type", "element")
MIN_SCORE = 3  # a list must share this many labels with a kind's keys (a manufacturer / type list, not a stray frame)
FAR = 99  # the tree distance of lists in another movie than the manufacturer's

_lock = threading.Lock()
_keys: dict[str, set[str]] = {k: set() for k in KINDS}
_index: dict[str, list["Art"]] | None = None  # frame label (lower case) -> the arts showing it (gamescan's)
_pngs: dict[tuple[str, str], bytes | None] = {}
_anchor: list = []  # the chosen manufacturer list's art (the card: type / element lists nearest it)


@dataclass
class Art:
    label: str
    labels: frozenset[str]  # every label of its list (the choice: which kind of list it is)
    package: Path
    movie: str  # the movie's object path
    texture: str  # the atlas texture's object path
    rect: tuple[int, int, int, int]  # x0, y0, x1, y1 in the atlas as declared
    declared: tuple[int, int]  # the atlas' declared size (its texture may be smaller: packed / rescaled)
    group: int  # the sprite placing its list (the icon's layers: its lists), else the list itself
    depth: int  # its list's depth there (lower: drawn first)
    offset: tuple[float, float]  # its top left in the group's space (movie px)
    size: tuple[float, float]  # its shape's size (movie px)
    ancestry: dict[int, int]  # the group and its ancestors (sprite id -> distance)

    @property
    def area(self) -> int:
        return (self.rect[2] - self.rect[0]) * (self.rect[3] - self.rect[1])

    @classmethod
    def load(cls, package: Path, d: dict) -> "Art":
        """From gamescan's cache (movie_arts' dict + its movie)."""
        return cls(d["label"], frozenset(d["labels"]), package, d["movie"], d["texture"], tuple(d["rect"]),
                   tuple(d["declared"]), d["group"], d["depth"], tuple(d["offset"]), tuple(d["size"]),
                   {int(k): v for k, v in d["ancestry"].items()})


# Called (no arguments, any thread) when ready() may have changed: the mod publishes it ("assets") - the page asks
# for icons only once they can be found (asked before: a 404, and a map marker gave up on it)
listener: Any = None


def ready() -> bool:
    """Whether icons can be looked up: the game's files indexed (gamescan) and every kind's keys known (the first
    players' read)."""
    with _lock:
        return _index is not None and all(_keys[k] for k in KINDS)


def _changed() -> None:
    if listener is not None:
        try:
            listener()
        except Exception:  # noqa: BLE001, S110 - (the page's news: never breaks the index / the game thread)
            pass


def set_keys(kind: str, keys: set[str]) -> None:
    """The game's own keys for a kind (from the loaded definitions): what its icons' frames are labelled."""
    with _lock:
        _keys[kind] = {k.lower() for k in keys if k}
        _anchor.clear()
    _changed()


def set_index(index: dict[str, list[Art]]) -> None:
    """The arts by label, from gamescan's one pass (cached)."""
    global _index  # noqa: PLW0603
    with _lock:
        _index = index
        _pngs.clear()
        _anchor.clear()
    _changed()


# region The packages: the engine's config


def engine_packages(cooked: Path) -> list[Path]:
    """The always-loaded packages, in the engine's order: [Engine.ScriptPackages] (every *Packages entry but the
    editor's), [Engine.StartupPackages] (Package=), from Engine/Config/BaseEngine.ini then the game's
    Config/DefaultEngine.ini (+ entries), then the cooked Startup - only the files that exist."""
    game = cooked.parent.parent
    names: list[str] = []
    for ini in [game / "Engine" / "Config" / "BaseEngine.ini", *sorted(cooked.parent.glob("Config/DefaultEngine.ini"))]:
        try:
            text = ini.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        section = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line.strip("[]")
            elif "=" in line and not line.startswith(";"):
                key, value = (s.strip() for s in line.split("=", 1))
                key = key.lstrip("+.-!")
                if (section == "Engine.ScriptPackages" and key.endswith("Packages") and "Editor" not in key) or \
                        (section == "Engine.StartupPackages" and key == "Package"):
                    if value and value not in names:
                        names.append(value)
    names.append("Startup")
    out, seen = [], set()
    for name in names:
        path = cooked / f"{name}.upk"
        if path.is_file() and path not in seen:
            seen.add(path)
            out.append(path)
    return out


# endregion
# region The movies: lists of atlas bitmaps


def _movie_tags(raw: bytes):  # noqa: ANN202
    if raw[:3] == b"CFX":
        d = raw[:8] + zlib.decompress(raw[8:])
    elif raw[:3] == b"GFX":
        d = raw
    else:
        return iter(())
    b = _Bits(d, 8)
    _rect(b)
    return _tags(d, b.align() + 4)


def _placements(body: bytes) -> list[tuple[str | None, int, int, float, float]]:
    """A sprite's PlaceObject2 tags that place a character: (the frame's label, depth, character, translate x, y)."""
    out, label = [], None
    for code, sb in _tags(body, 4):
        if code == 43:
            label = sb[: sb.index(0)].decode("latin1", "replace") if 0 in sb else ""
        elif code == 26 and sb[0] & 0x02:
            flags, depth, cid = sb[0], *struct.unpack_from("<HH", sb, 1)
            tx = ty = 0.0
            if flags & 0x04:
                _sx, _sy, tx, ty = _matrix(_Bits(sb, 5))
            out.append((label, depth, cid, tx, ty))
        elif code == 1:
            label = None
    return out


def movie_arts(raw: bytes, movie_package: str) -> list[dict]:
    """A movie's list arts: [{label, labels (its list's), texture ("<movie package>.<the atlas' file name without
    .tga>"), rect, declared, group, depth, offset, size, ancestry}] - one per list frame showing an atlas bitmap,
    per sprite placing that list (see Art). The atlas: a DefineExternalImage2 (1009) whose id's low word is the image
    index DefineSubImage (1008) refers to."""
    images: dict[int, tuple[str, tuple[int, int]]] = {}  # atlas index -> (texture path, declared size)
    subs: dict[int, tuple[int, tuple[int, int, int, int]]] = {}  # bitmap id -> (atlas index, rect)
    shapes: dict[int, tuple[int, tuple[float, float, float, float]]] = {}  # shape id -> (its bitmap id, bounds)
    sprites: dict[int, bytes] = {}
    for code, body in _movie_tags(raw):
        if code == 1009 and len(body) > 12:  # id u32, format u16, declared w / h u16, export name, file name
            cid = struct.unpack_from("<I", body)[0]
            w, h = struct.unpack_from("<HH", body, 6)
            p = 10
            p += 1 + body[p]
            name = body[p + 1 : p + 1 + body[p]].decode("latin1")
            stem = name.rpartition(".")[0] or name
            # (an atlas' id has a high word - 0x9000n -, a plain image's not: SharedWillowComponents' 8 x 4 scanlines,
            # id 1, would take atlas 1's place)
            if cid >> 16 or (cid & 0xFFFF) not in images:
                images[cid & 0xFFFF] = (f"{movie_package}.{stem}", (w, h))
        elif code == 1008 and len(body) >= 12:  # bitmap id, atlas index, x0 y0 x1 y1
            sid, image, x0, y0, x1, y1 = struct.unpack_from("<6H", body)
            subs[sid] = (image, (x0, y0, x1, y1))
        elif code in (2, 22, 32, 83):
            if (s := _shape_bitmap(code, body)) is not None:
                shapes[s[0]] = (s[2], s[1])
        elif code == 39:
            sprites[struct.unpack_from("<H", body)[0]] = body

    placed = {sid: _placements(body) for sid, body in sprites.items()}
    parents: dict[int, list[tuple[int, int, float, float]]] = {}  # character -> [(sprite, depth, tx, ty)]
    for sid, places in placed.items():
        seen = set()
        for _lab, depth, cid, tx, ty in places:
            if (cid, depth) not in seen:
                seen.add((cid, depth))
                parents.setdefault(cid, []).append((sid, depth, tx, ty))

    def ancestry(sid: int) -> dict[int, int]:
        out, todo = {sid: 0}, [sid]
        while todo:
            cur = todo.pop(0)
            for par, *_ in parents.get(cur, []):
                if par not in out and out[cur] < 8:
                    out[par] = out[cur] + 1
                    todo.append(par)
        return out

    def frames(sid: int) -> list[tuple[str | None, list[int]]]:
        """A sprite's frames: (its label, the characters on it)."""
        out, shown, label = [], {}, None
        for code, sb in _tags(sprites[sid], 4):
            if code == 43:
                label = sb[: sb.index(0)].decode("latin1", "replace") if 0 in sb else ""
            elif code == 26:
                flags, depth = sb[0], struct.unpack_from("<H", sb, 1)[0]
                if flags & 0x02:
                    shown[depth] = struct.unpack_from("<H", sb, 3)[0]
            elif code == 28:
                shown.pop(struct.unpack_from("<H", sb)[0], None)
            elif code == 1:
                out.append((label, list(shown.values())))
                label = None
        return out

    def bitmap_of(cid: int, depth: int = 0) -> tuple[int, tuple[float, float, float, float]] | None:
        """A character's bitmap and its shape's bounds: a shape's fill, or a one-frame, one-character sprite's."""
        if cid in shapes:
            return shapes[cid]
        if cid in sprites and depth < 4:
            f = frames(cid)
            if len(f) == 1 and len(f[0][1]) == 1:
                return bitmap_of(f[0][1][0], depth + 1)
        return None

    out = []
    for sid in sprites:
        labelled = [(lab, chars) for lab, chars in frames(sid) if lab]
        arts = {}
        for lab, chars in labelled:
            if len(chars) != 1 or (found := bitmap_of(chars[0])) is None or found[0] not in subs:
                continue
            image, rect = subs[found[0]]
            if image in images and rect[2] <= images[image][1][0] and rect[3] <= images[image][1][1]:  # (inside its atlas)
                arts[lab.lower()] = (images[image][0], rect, images[image][1], found[1])
        if not arts:
            continue
        labels = sorted({lab.lower() for lab, _ in labelled})
        for group, depth, tx, ty in parents.get(sid) or [(sid, 0, 0.0, 0.0)]:
            anc = ancestry(group)
            for lab, (texture, rect, declared, (x0, x1, y0, y1)) in arts.items():
                out.append({"label": lab, "labels": labels, "texture": texture, "rect": list(rect), "declared": list(declared),
                            "group": group, "depth": depth, "offset": [tx + x0, ty + y0], "size": [x1 - x0, y1 - y0],
                            "ancestry": anc})
    return out


# endregion
# region The icons


def _decode_region(fmt: str, w: int, h: int, data: bytes, rect: tuple[int, int, int, int]) -> tuple[int, int, bytes]:
    """The rectangle of a texture as RGBA - only the 4 x 4 blocks it covers are decoded (DXT), or its texels (A8R8G8B8)."""
    x0, y0, x1, y1 = max(0, rect[0]), max(0, rect[1]), min(w, rect[2]), min(h, rect[3])
    rw, rh = max(0, x1 - x0), max(0, y1 - y0)
    if fmt == "PF_A8R8G8B8":  # BGRA
        out = bytearray()
        for y in range(y0, y1):
            row = data[(y * w + x0) * 4 : (y * w + x1) * 4]
            for i in range(0, len(row), 4):
                out += bytes((row[i + 2], row[i + 1], row[i], row[i + 3]))
        return rw, rh, bytes(out)
    size = 8 if fmt == "PF_DXT1" else 16
    bw = (w + 3) // 4
    bx0, by0, bx1, by1 = x0 // 4, y0 // 4, (x1 + 3) // 4, (y1 + 3) // 4
    # the blocks, as a small DXT texture of their own, decoded; then cut to the rectangle
    blocks = b"".join(data[(by * bw + bx) * size : (by * bw + bx + 1) * size] for by in range(by0, by1) for bx in range(bx0, bx1))
    sub_w, sub_h = (bx1 - bx0) * 4, (by1 - by0) * 4
    rgba = decode_dxt(fmt, sub_w, sub_h, blocks)
    ox, oy = x0 - bx0 * 4, y0 - by0 * 4
    out = b"".join(rgba[((oy + y) * sub_w + ox) * 4 : ((oy + y) * sub_w + ox + rw) * 4] for y in range(rh))
    return rw, rh, out


def layers_png(layers: list[list]) -> bytes:
    """An icon's layers - [[package, texture, rect, declared, offset, size]], bottom first - drawn over each other
    at their offsets (gamework's job) -> a PNG."""
    crops = []
    for package, texture_path, rect, declared, offset, size in layers:
        with opened(Path(package)) as pkg:  # (the worker: the package and its atlas kept for the next icons)
            idx = pkg.find(texture_path, "Texture2D")
            if idx is None:
                continue
            fmt, w, h, body = texture(Path(package), pkg, idx)
        sx, sy = w / declared[0] if declared[0] else 1, h / declared[1] if declared[1] else 1
        rw, rh, rgba = _decode_region(fmt, w, h, body, tuple(round(v * s) for v, s in zip(rect, (sx, sy, sx, sy))))
        if rw and rh:
            crops.append((rw, rh, rgba, offset, (rw / size[0] if size[0] else 1)))
    if not crops:
        raise ValueError("no layer decoded")
    scale = crops[0][4]  # (texels per movie px: the bottom layer's)
    x_min = min(c[3][0] for c in crops)
    y_min = min(c[3][1] for c in crops)
    places = [(round((c[3][0] - x_min) * scale), round((c[3][1] - y_min) * scale)) for c in crops]
    cw = max(px + c[0] for (px, _), c in zip(places, crops))
    ch = max(py + c[1] for (_, py), c in zip(places, crops))
    out = bytearray(cw * ch * 4)
    for (px, py), (rw, rh, rgba, _o, _s) in zip(places, crops):
        for y in range(rh):
            for x in range(rw):
                s = (y * rw + x) * 4
                a = rgba[s + 3]
                if not a:
                    continue
                d = ((py + y) * cw + px + x) * 4
                if a == 255 or not out[d + 3]:
                    out[d : d + 4] = rgba[s : s + 4]
                    continue
                # "over": the layer on what's under it
                da = out[d + 3] * (255 - a) // 255
                oa = a + da
                for k in range(3):
                    out[d + k] = (rgba[s + k] * a + out[d + k] * da) // oa
                out[d + 3] = oa
    return png(cw, ch, bytes(out))


def _groups(kind: str, label: str) -> dict[tuple, list[Art]]:
    keys = _keys[kind]
    by: dict[tuple, list[Art]] = {}
    for a in (_index or {}).get(label, []):
        if len(a.labels & keys) >= MIN_SCORE:
            by.setdefault((a.package, a.movie, a.group), []).append(a)
    return by


def _manufacturer_anchor() -> Art | None:
    """The manufacturer lists' art the card uses (the best overlap, the largest), for the type / element choice."""
    if not _anchor:
        keys = _keys["manufacturer"]
        best = None
        for key in keys:
            for arts in _groups("manufacturer", key).values():
                rank = (max(len(a.labels & keys) for a in arts), sum(a.area for a in arts))
                if best is None or rank > best[0]:
                    best = (rank, arts[0])
        _anchor.append(best[1] if best else None)
    return _anchor[0]


def _distance(arts: list[Art], anchor: Art | None) -> int:
    """How far a group is from the manufacturer's in the movie's tree (their nearest common ancestor)."""
    if anchor is None:
        return 0
    if (arts[0].package, arts[0].movie) != (anchor.package, anchor.movie):
        return FAR
    common = [d + anchor.ancestry[s] for s, d in arts[0].ancestry.items() if s in anchor.ancestry]
    return min(common) if common else FAR


def _choose(kind: str, label: str) -> list[Art]:
    """The icon's layers, bottom first: the group whose lists best fit (nearest the card's manufacturer logo for
    a type / an element, the best label overlap, the largest)."""
    groups = _groups(kind, label)
    if not groups:
        return []
    keys = _keys[kind]
    anchor = _manufacturer_anchor() if kind != "manufacturer" else None

    def rank(arts: list[Art]) -> tuple:
        return (-_distance(arts, anchor), max(len(a.labels & keys) for a in arts), sum(a.area for a in arts))

    return sorted(max(groups.values(), key=rank), key=lambda a: a.depth)


def card_png(kind: str, label: str) -> bytes | None:
    """An item card icon: `kind` "manufacturer" / "type" / "element", `label` the game's key ("maliwan", "pistol",
    "shock") -> a PNG (its layers drawn), or None (not found, the kind's keys / the index not known yet, or it won't
    decode). Decoded by gamework (its subinterpreter; cached on disk). Thread-safe; kept."""
    if kind not in KINDS or not re.fullmatch(r"[A-Za-z0-9_]+", label or ""):
        return None
    key = (kind, label.lower())
    with _lock:
        if key in _pngs:
            return _pngs[key]
        if not _keys[kind] or _index is None:
            return None  # (not kept: the keys come with the first players' read, the index with gamescan)
        layers = _choose(kind, key[1])
    data = None
    if layers:
        job = [[str(a.package), a.texture, list(a.rect), list(a.declared), list(a.offset), list(a.size)] for a in layers]
        data = gamework.asset({"do": "card", "layers": job}, sorted({a.package for a in layers}))
    with _lock:
        _pngs[key] = data
    return data


# endregion
