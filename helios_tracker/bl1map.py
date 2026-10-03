"""
Borderlands 1's map, as an image like BL2's (tacmap.py): BL1 draws its map screen as vector shapes, one frame per area
in the menu movie (menus_ingame_redux.upk FlashMovies.status_menu: its map sprite's frames are labeled with the levels'
LevelLandmarkAnchor.MapFrame - "arid_arena", "newhaven"...). The frame's shapes are rendered here (swfshape.py) into
one image, placed in the map sprite's px - the page draws it like any map image. Files only, no SDK: the map thread.
.agent/bl1.md "The map screen".
"""

import math
import re
from collections import Counter
import struct
import threading
from dataclasses import dataclass
from pathlib import Path

from .swf import _movie_raw, _movie_tags, _cstr, _place2, _tags
from .swfshape import SHAPE_CODES, Affine, Shape, parse_shape, render
from .tacmap import MapImage
from .upk_bl1 import Bl1Package

MENU_PACKAGE = Path("Packages") / "Interface" / "menus_ingame_redux.upk"  # under WillowGame/CookedPC
MENU_MOVIE = "FlashMovies.status_menu"
SCALE = 2.0  # image px per movie px (Arid: 780 x 352 movie px -> 1560 x 704)
IDENTITY: Affine = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _compose(outer: Affine, inner: Affine) -> Affine:
    """inner, then outer."""
    a, b, c, d, e, f = outer
    a2, b2, c2, d2, e2, f2 = inner
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2, a * e2 + c * f2 + e, b * e2 + d * f2 + f)


class _Movie:
    """A movie's characters: its shapes' tag bodies and its sprites' tags, by id."""

    def __init__(self, raw: bytes) -> None:
        self.shapes: dict[int, tuple[int, bytes]] = {}
        self.sprites: dict[int, list[tuple[int, bytes]]] = {}
        self.root_named: dict[str, int] = {}  # the movie's own placements with a name: name -> character id
        self.root: list[tuple[int, Affine]] = []  # what the movie itself places (its first frame), by depth order
        for code, body in _movie_tags(raw):
            if code in SHAPE_CODES:
                self.shapes[struct.unpack_from("<H", body)[0]] = (code, body)
            elif code == 39:  # DefineSprite: id, frame count, its tags
                self.sprites[struct.unpack_from("<H", body)[0]] = list(_tags(body, 4))
            elif code == 26:
                cid, matrix, name = _place2(body)
                if name and cid is not None:
                    self.root_named.setdefault(name, cid)
                if cid is not None:
                    self.root.append((cid, matrix or IDENTITY))
        self._parsed: dict[int, Shape] = {}

    def shape(self, cid: int) -> Shape:
        if cid not in self._parsed:
            self._parsed[cid] = parse_shape(*self.shapes[cid])
        return self._parsed[cid]

    def has_labels(self, sid: int) -> bool:
        return any(code == 43 for code, _ in self.sprites[sid])

    def labeled(self, label: str) -> int | None:
        """The sprite with a frame of this label (case-insensitive, like the game's gotoAndStop)."""
        want = label.lower()
        for sid, tags in self.sprites.items():
            if any(code == 43 and _cstr(body, 0)[0].lower() == want for code, body in tags):
                return sid
        return None

    def display_list(self, sid: int, label: str | None = None, carried: bool = False) -> list[tuple[int, Affine]]:
        """What a sprite's frame `label` places itself (None: its first frame) - (character id, matrix) by depth. Not
        what earlier frames left there: the map sprite's "arid" frame places the markers' templates (objective,
        player...), still there in the frames after - the map tab's code moves them, they aren't the area's art."""
        shown: dict[int, tuple[int, Affine]] = {}
        own: set[int] = set()  # the depths the frame itself places
        at_label = label is None
        for code, body in self.sprites[sid]:
            if code == 43 and label is not None and _cstr(body, 0)[0].lower() == label.lower():
                at_label = True
            elif code == 26:  # PlaceObject2: a new character at a depth, or the one there moved
                depth = struct.unpack_from("<H", body, 1)[0]
                cid, matrix, _name = _place2(body)
                old = shown.get(depth)
                if cid is None and old is None:
                    continue
                shown[depth] = (cid if cid is not None else old[0], matrix or (old[1] if old and cid is None else IDENTITY))
                if at_label:
                    own.add(depth)
            elif code == 28:  # RemoveObject2
                shown.pop(struct.unpack_from("<H", body)[0], None)
            elif code == 1 and at_label:  # the frame's end
                break
        return [shown[d] for d in sorted(shown if carried else own) if d in shown]

    def frame_tags(self, sid: int, label: str) -> list[tuple[int, bytes]]:
        """A sprite's frame's own tags, by its label (case-insensitive) - a label it doesn't have: its first frame, where
        a gotoAndStop to it leaves the clip (the skill clip's first frame is "roland_combat": Roland's "roland" stays
        there)."""
        frames: list[list[tuple[int, bytes]]] = [[]]
        found = None
        for code, body in self.sprites[sid]:
            if code == 1:  # ShowFrame: the frame's end
                frames.append([])
                continue
            if code == 43 and found is None and _cstr(body, 0)[0].lower() == label.lower():
                found = len(frames) - 1
            frames[-1].append((code, body))
        return frames[found or 0]

    def layers(self, sid: int, label: str | None = None, m: Affine = IDENTITY, depth: int = 0) -> list[tuple[Affine, Shape]]:
        """The shapes a sprite's frame draws (its sprites' first frames, recursively), with their matrices."""
        out: list[tuple[Affine, Shape]] = []
        for cid, matrix in self.display_list(sid, label):
            placed = _compose(m, matrix)
            if cid in self.shapes:
                out.append((placed, self.shape(cid)))
            elif cid in self.sprites and depth < 8 and not self.has_labels(cid):
                # (a sprite with frame labels: a marker's template - "objective", "player"... - not the area's art)
                out += self.layers(cid, None, placed, depth + 1)
        return out


_movies: dict[tuple[str, str, float], _Movie] = {}  # (package file, movie, mtime) -> it parsed (the menu's, the card's)
_lock = threading.Lock()


def _menu_movie(cooked: Path) -> _Movie:
    return _movie(cooked / MENU_PACKAGE, MENU_MOVIE)


def _movie(path: Path, name: str) -> _Movie:
    """A package's Scaleform movie, parsed - kept (one per movie: a patched package, read again)."""
    key = (str(path), name, path.stat().st_mtime)
    with _lock:
        if key not in _movies:
            pkg = Bl1Package(path)
            try:
                idx = pkg.find(name, "GFxMovieInfo")
                if idx is None:
                    raise FileNotFoundError(f"{name} not in {path.name}")
                for old in [k for k in _movies if k[:2] == key[:2]]:
                    del _movies[old]
                _movies[key] = _Movie(_movie_raw(pkg, idx))
            finally:
                pkg.close()
        return _movies[key]


def _literal_sets(action: bytes) -> dict[str, str]:
    """A DoAction's literal member assignments - `tree1.text = "$<StringAliasMap:skills_hunter_branch1>"`, AVM1: push
    "tree1"; getVariable; push "text", "$<...>"; setMember (the skill clip's frames: their constant pool, Push, GetVariable,
    SetMember, Stop / Play only) -> {"tree1.text": "$<...>"}. Any other action: the reading stops there (what came before kept)."""
    pool: list[str] = []
    stack: list[str | None] = []
    out: dict[str, str] = {}
    o = 0
    while o < len(action) and action[o]:
        code = action[o]
        size = struct.unpack_from("<H", action, o + 1)[0] if code >= 0x80 else 0
        body = action[o + 3 : o + 3 + size]
        o += 3 + size if code >= 0x80 else 1
        if code == 0x88:  # ConstantPool
            pool, at = [], 2
            for _ in range(struct.unpack_from("<H", body)[0]):
                text, at = _cstr(body, at)
                pool.append(text)
        elif code == 0x96:  # Push: a string or a constant only (anything else: not a literal - None)
            at = 0
            while at < len(body):
                kind, at = body[at], at + 1
                if kind == 0:
                    text, at = _cstr(body, at)
                    stack.append(text)
                elif kind in (8, 9):
                    index = body[at] if kind == 8 else struct.unpack_from("<H", body, at)[0]
                    at += 1 if kind == 8 else 2
                    stack.append(pool[index] if index < len(pool) else None)
                else:
                    at += {1: 4, 2: 0, 3: 0, 4: 1, 5: 1, 6: 8, 7: 4}.get(kind, len(body))
                    stack.append(None)
        elif (code == 0x1C and stack) or code in (0x06, 0x07):  # GetVariable: the name stays (its path); Play, Stop
            pass
        elif code == 0x4F and len(stack) >= 3:  # SetMember: object, member, value
            value, member, obj = stack.pop(), stack.pop(), stack.pop()
            if None not in (obj, member, value):
                out[f"{obj}.{member}"] = value
        else:
            break
    return out


def clip_texts(cooked: Path, clip: str, frame: str) -> dict[str, str]:
    """What the menu movie's clip `clip` (the movie's placement of that name: the skill tree's "skills" -
    SkillTreeGFxDefinition.SkillMovieClip) sets in its frame `frame` (the character's: SkillTreeGFxHelper
    .GetCharacterName(), its Flash_SetCharacter's gotoAndStop) - {"tree1.text": "$<StringAliasMap:skills_hunter_branch1>",
    "charclass.text": ...}: the frame's ActionScript's literal assignments. {} if the movie has no such clip."""
    movie = _menu_movie(cooked)
    sprite = movie.root_named.get(clip)
    if sprite not in movie.sprites:
        return {}
    out: dict[str, str] = {}
    for code, body in movie.frame_tags(sprite, frame):
        if code == 12:  # DoAction
            out.update(_literal_sets(body))
    return out


_clip_texts: dict[tuple[str, str, str], dict[str, str] | None] = {}  # (cooked, clip, frame) -> its texts (None: being read)


def clip_texts_later(cooked: Path, clip: str, frame: str) -> dict[str, str] | None:
    """clip_texts without waiting (the game thread asks: the movie read on a thread of its own the first time) - None
    until it's read; {} if it failed."""
    key = (str(cooked), clip, frame.lower())
    with _lock:
        if key in _clip_texts:
            return _clip_texts[key]
        _clip_texts[key] = None

    def read() -> None:
        try:
            texts = clip_texts(cooked, clip, frame)
        except Exception:  # noqa: BLE001 - the movie unreadable: none (its fallback names)
            texts = {}
        with _lock:
            _clip_texts[key] = texts

    threading.Thread(target=read, name="helios_tracker menu movie", daemon=True).start()
    return None


# A menu clip's icon, as the skill tree's cells name them: "menu.<clip>.<frame>.<placement>.<label>.<other>" -
# "menu.skills.mordecai.icon17.on.off" (games.Borderlands1.skill_icons): the root's clip "skills", its frame
# "mordecai", the clip placed there as "icon17", drawn at its frame "on" - what its frame "off" shows too
MENU_ICON = re.compile(r"menu" + r"\.([A-Za-z0-9_]+)" * 5)
ICON_SIZE = 128  # px, the larger side (BL2's skill icons: 64 x 64 textures)


def clip_icon(cooked: Path, clip: str, frame: str, name: str, label: str, other: str) -> tuple[int, int, bytes] | None:
    """A menu icon (MENU_ICON's parts) drawn: (width, height, BGRA) - its shapes rendered (swfshape), ICON_SIZE on its
    larger side. Only what its frames `label` and `other` both place: a skill icon's clip has a tile per state under
    its drawing ("on": a dark tile notched at its bottom right - the cell's rank goes there -, "off": another; the
    page draws the cell's state itself, the user: "the background is strange") - the drawing, the same in both. None
    if the movie has no such clip / placement / frame (a frame it doesn't have: nothing drawn)."""
    movie = _menu_movie(cooked)
    sprite = movie.root_named.get(clip)
    if sprite not in movie.sprites:
        return None
    placed = None
    for code, body in movie.frame_tags(sprite, frame):
        if code == 26:
            cid, _matrix, placed_name = _place2(body)
            if placed_name == name and cid is not None:
                placed = cid
    if placed not in movie.sprites:
        return None
    shared = {cid for cid, _matrix in movie.display_list(placed, other)}
    layers: list[tuple[Affine, Shape]] = []
    for cid, matrix in movie.display_list(placed, label):
        if cid in shared and cid in movie.shapes:
            layers.append((matrix, movie.shape(cid)))
        elif cid in shared and cid in movie.sprites:
            layers += movie.layers(cid, None, matrix)
    if not layers:
        return None
    return _icon(layers)


def _icon(layers: list[tuple[Affine, Shape]]) -> tuple[int, int, bytes]:
    """Shapes drawn ICON_SIZE on their larger side: (width, height, BGRA)."""
    _w, _h, _bgra, (x0, x1, y0, y1) = render(layers, 1.0)
    w, h, bgra, _bounds = render(layers, ICON_SIZE / max(x1 - x0, y1 - y0, 1e-6))
    return w, h, bgra


# The item card's movie (the game's card, on the ground and in the menus: inworld_ui.upk weapon_card.weapon_card -
# its "inventory" clip): its icons as BL2's card's, one sprite per kind, a frame per key - the manufacturers' (frames
# "jakobs", "s_and_s"... = ManufacturerDefinition.FlashLabelName), vector shapes. (Its type art, the "zippy" - a
# Claptrap holding the gun / item - isn't the item's icon: item_icon.) .agent/bl1.md
CARD_PACKAGE = Path("Packages") / "Interface" / "inworld_ui.upk"  # under WillowGame/CookedPC
CARD_MOVIE = "weapon_card.weapon_card"


# An item's icon (its silhouette): the clip the game's scripts send to an item's frame - always placed as "inicon<N>":
# the inventory list's entries (inventory.selections.inicon1..14), the mission reward's (missions.reward_weap
# .inicon14.gotoAndStop - QuestAcceptGFxMovie.SetRewardCard), the vending machine's item of the day (topLevel_mc
# .inicon2 - VendingMachineGFxMovie) - in the menu movie; frames "repeater", "sniper"... (WeaponTypeDefinition
# .ScaleformFrameName), "shield", "grenade", "comm"... (WillowInventory.ZippyFrame)
ITEM_ICON = re.compile(r"inicon[0-9]+")


def item_icon(cooked: Path, label: str) -> tuple[int, int, bytes] | None:
    """An item's icon drawn (_icon): the menu movie's ITEM_ICON clip at its frame `label`. None if no such frame."""
    movie = _menu_movie(cooked)
    sprite = next((cid for tags in movie.sprites.values() for code, body in tags if code == 26
                   for cid, _matrix, name in [_place2(body)] if name and ITEM_ICON.fullmatch(name) and cid in movie.sprites), None)
    if sprite is None or not any(code == 43 and _cstr(body, 0)[0].lower() == label.lower() for code, body in movie.sprites[sprite]):
        return None
    # the item's own drawing: what its frame shows that no other frame does - not its kind's shape behind it (depth
    # 1, kept from frame to frame: a square behind the weapons, placed with the first, "repeater"; a diamond behind the
    # mods, class mods, shields; a burst behind the grenades, ammo; a circle, an octagon) - the user: no shape behind
    # (drawn as the frames place them, the pistol had its square, the sniper not)
    # (the frames placing something: one placing nothing - "instahealth" - shows the one before's, health's cross)
    labels = [_cstr(body, 0)[0] for code, body in movie.sprites[sprite] if code == 43]
    shown_in = Counter(cid for other in labels if movie.display_list(sprite, other)
                       for cid in {c for c, _m in movie.display_list(sprite, other, carried=True)})
    layers: list[tuple[Affine, Shape]] = []
    for cid, matrix in movie.display_list(sprite, label, carried=True):
        if shown_in[cid] > 1:
            continue
        if cid in movie.shapes:
            layers.append((matrix, movie.shape(cid)))
        elif cid in movie.sprites:
            layers += movie.layers(cid, None, matrix)
    return _icon(layers) if layers else None


def card_icon(cooked: Path, keys: list[str], label: str) -> tuple[int, int, bytes] | None:
    """An item card icon drawn (_icon): the card movie's sprite listing a kind's keys (the game's: `keys`) - the one
    whose frame labels hold the most of them, then the fewest others (the menus have lists alike with more: the
    shops', the pickups') - at its frame `label`. None if no sprite has one of them, or no such frame."""
    movie = _movie(cooked / CARD_PACKAGE, CARD_MOVIE)
    want = {k.lower() for k in keys}
    best, best_score = None, (0, 0)
    for sid, tags in movie.sprites.items():
        labels = {_cstr(body, 0)[0].lower() for code, body in tags if code == 43}
        score = (len(labels & want), -len(labels - want))
        if score[0] and score > best_score:
            best, best_score = sid, score
    if best is None:
        return None
    layers = movie.layers(best, label)
    return _icon(layers) if layers else None


def card_icon_png(cooked: Path, keys: set[str], label: str) -> bytes | None:
    """card_icon as a PNG, or None - rendered by gamework (cached on disk). The server's threads: no SDK."""
    from . import gamework  # noqa: PLC0415

    if not keys or not re.fullmatch(r"[A-Za-z0-9_]+", label or ""):
        return None
    return gamework.asset({"do": "cardicon", "cooked": str(cooked), "keys": sorted(keys), "label": label.lower()},
                          [cooked / CARD_PACKAGE])


# The card's element icon: its clip placed as "chemical" (its "manufacturer", "zippy", "protean" - the grenade's type -,
# "comm" beside it), 21 frames: "exp0".."exp4", "shock0".., "fire0".., "corr0".., "none" - the element and its tech
# level, drawn ("x2", "x4"...); an item's frame number: its FlashTechFrame (games.Borderlands1.element_frame)
ELEMENT_CLIP = "chemical"


def card_frame_icon(cooked: Path, clip: str, frame: int | str) -> tuple[int, int, bytes] | None:
    """The card movie's clip placed as `clip`, drawn at its frame `frame` - a number (1: its first - Flash's
    gotoAndStop) or a label ("fire1") - (_icon), or None: no such clip / frame, or nothing drawn."""
    movie = _movie(cooked / CARD_PACKAGE, CARD_MOVIE)
    sprite = next((cid for tags in movie.sprites.values() for code, body in tags if code == 26
                   for cid, _matrix, name in [_place2(body)] if name == clip and cid in movie.sprites), None)
    if sprite is None or (isinstance(frame, int) and frame < 1):
        return None
    labels: list[str | None] = [None]
    for code, body in movie.sprites[sprite]:
        if code == 43 and labels[-1] is None:
            labels[-1] = _cstr(body, 0)[0]
        elif code == 1:
            labels.append(None)
    if isinstance(frame, str):
        label = next((x for x in labels if x and x.lower() == frame.lower()), None)
    else:
        label = labels[frame - 1] if frame <= len(labels) else None
    # the element's mark alone: a level's frame adds its number ("x1") to what the frame before it showed - its
    # element's mark, placed with its first frame ("fire0"), kept (moved a little: room for the number) - its number
    # left out (the level: a stat of its own - the user: "as BL2, no number on it"); a frame keeping nothing of the
    # one before (an element's first: its mark): all it shows
    index = labels.index(label) if label else 0
    before = {cid for cid, _matrix in movie.display_list(sprite, labels[index - 1], carried=True)} if index and labels[index - 1] else set()
    shown = movie.display_list(sprite, label, carried=True) if label else []
    kept = [(cid, matrix) for cid, matrix in shown if cid in before]
    layers: list[tuple[Affine, Shape]] = []
    for cid, matrix in kept or shown:
        if cid in movie.shapes:
            layers.append((matrix, movie.shape(cid)))
        elif cid in movie.sprites:
            layers += movie.layers(cid, None, matrix)
    return _icon(layers) if layers else None


def element_icon_png(cooked: Path, frame: str) -> bytes | None:
    """The card's element icon at a frame - an item's number ("1": explosive, no level), a weapon's label ("fire1") -
    as a PNG, or None - rendered by gamework (cached on disk). The server's threads: no SDK."""
    from . import gamework  # noqa: PLC0415

    if not re.fullmatch(r"[A-Za-z0-9_]+", frame or ""):
        return None
    return gamework.asset({"do": "cardframe", "cooked": str(cooked), "clip": ELEMENT_CLIP,
                           "frame": int(frame) if frame.isdigit() else frame}, [cooked / CARD_PACKAGE])


def item_icon_png(cooked: Path, label: str) -> bytes | None:
    """item_icon as a PNG, or None - rendered by gamework (cached on disk). The server's threads: no SDK."""
    from . import gamework  # noqa: PLC0415

    if not re.fullmatch(r"[A-Za-z0-9_]+", label or ""):
        return None
    return gamework.asset({"do": "itemicon", "cooked": str(cooked), "label": label.lower()}, [cooked / MENU_PACKAGE])


def menu_icon_png(path: str) -> bytes | None:
    """A menu icon (its MENU_ICON path) as a PNG, or None - rendered by gamework (its subinterpreter; cached on disk).
    The server's threads: no SDK."""
    from . import gamedir, gamework  # noqa: PLC0415

    m = MENU_ICON.fullmatch(path)
    cooked = gamedir.cooked_dir()
    if m is None or cooked is None:
        return None
    return gamework.asset({"do": "menuicon", "cooked": str(cooked), "parts": list(m.groups())}, [cooked / MENU_PACKAGE])


@dataclass(frozen=True)
class Anchor:
    """A level's LevelLandmarkAnchor, what places its map: read on the game thread (levelmap.py)."""

    frame: str  # MapFrame: the menu movie's frame of the level's map
    x: float  # Location
    y: float
    yaw: int  # Rotation.Yaw (65536 a turn)
    scale_x: float  # DrawScale x DrawScale3D
    scale_y: float
    texture_x: int  # TextureSizeX / Y: the texture the shape was traced on
    texture_y: int
    dlc_map: str = ""  # DLCMap: a DLC area's own map movie ("dlc2_maps.dlcmap_lobby" - its MapFrame "dlcmap1", the menu's slot)


def placement(anchor: Anchor, clip: tuple[float, float]) -> tuple[list[float], float]:
    """Where the map sits in the world, as the page takes it (geo.js worldToMap: map x = (Y - center Y) / upp, map y =
    -(X - center X) / upp): (center, upp). `clip`: the map shape's size, movie px (the game's ClipSize).
    The anchor's texture is a quad centered on it, TextureSize x its scale in world units, its u along world +Y and its
    v along -X; the shape was traced on it from its top-left corner at k movie px per texel, k fitting the texture in
    the clip (the game's CoordScale = k / (clip / texture) per axis). Checked against the game's own placement of 27
    map objects in Arid (tools/probes/probe_bl1_map.txt): within 0.0005 of the map. Its yaw isn't in it (the page's map
    doesn't turn): Arid's is 32 (0.18 degrees)."""
    k = max(clip[0] / anchor.texture_x, clip[1] / anchor.texture_y)
    width = anchor.texture_y * anchor.scale_y  # world units along +Y = the texture's u
    height = anchor.texture_x * anchor.scale_x  # along -X = its v
    upp_x = width / (anchor.texture_x * k)
    upp_y = height / (anchor.texture_y * k)
    center = [anchor.x + height / 2, anchor.y - width / 2]  # the world spot at the texture's corner: movie (0, 0)
    return center, math.sqrt(upp_x * upp_y)  # (one scale: Arid's two differ by 0.15 %)


_rendered: dict[tuple[str, str, float], list[MapImage]] = {}  # (cooked, frame, mtime) -> its image (a few kept)
KEEP_RENDERED = 4


def load_map(cooked: Path, map_frame: str, dlc_map: str = "") -> list[MapImage]:
    """The level's map (its anchor's MapFrame) as one image, its bounds in the map sprite's px. [] when the menu movie
    has no such frame (a DLC's map: its own movie, not read yet)."""
    key = (str(cooked), (dlc_map or map_frame).lower(), (cooked / MENU_PACKAGE).stat().st_mtime)
    with _lock:
        if key in _rendered:
            return _rendered[key]
    images = _render_dlc(cooked, dlc_map) if dlc_map else _render(cooked, map_frame)
    with _lock:
        _rendered[key] = images
        while len(_rendered) > KEEP_RENDERED:
            del _rendered[next(iter(_rendered))]
    return images


def _render_dlc(cooked: Path, dlc_map: str) -> list[MapImage]:
    """A DLC area's map: its anchor's DLCMap, a movie of its own in the DLC's package ("dlc2_maps.dlcmap_lobby": its
    root places the area's clip, "themap" - the status menu loads it in its "dlcmap1" slot, the anchor's MapFrame) -
    what its root places, drawn like a base area's frame. [] if its package isn't found."""
    package, _, name = dlc_map.partition(".")
    path = next((cooked / "DLC").rglob(f"{package}.upk"), None) if (cooked / "DLC").is_dir() else None
    if path is None or not name:
        return []
    movie = _movie(path, name)
    layers: list[tuple[Affine, Shape]] = []
    for cid, matrix in movie.root:
        if cid in movie.shapes:
            layers.append((matrix, movie.shape(cid)))
        elif cid in movie.sprites:
            layers += movie.layers(cid, None, matrix)
    if not layers:
        return []
    w, h, bgra, bounds = render(layers, SCALE)
    return [MapImage(name, "PF_A8R8G8B8", w, h, bgra, bounds)]


def _render(cooked: Path, map_frame: str) -> list[MapImage]:
    movie = _menu_movie(cooked)
    sprite = movie.labeled(map_frame)
    if sprite is None:
        return []
    layers = movie.layers(sprite, map_frame)
    if not layers:
        return []
    w, h, bgra, bounds = render(layers, SCALE)
    return [MapImage(map_frame, "PF_A8R8G8B8", w, h, bgra, bounds)]
