"""
Borderlands 1's map, as an image like BL2's (tacmap.py): BL1 draws its map screen as vector shapes, one frame per area
in the menu movie (menus_ingame_redux.upk FlashMovies.status_menu: its map sprite's frames are labeled with the levels'
LevelLandmarkAnchor.MapFrame - "arid_arena", "newhaven"...). The frame's shapes are rendered here (swfshape.py) into
one image, placed in the map sprite's px - the page draws it like any map image. Files only, no SDK: the map thread.
.agent/bl1.md "The map screen".
"""

import math
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
        for code, body in _movie_tags(raw):
            if code in SHAPE_CODES:
                self.shapes[struct.unpack_from("<H", body)[0]] = (code, body)
            elif code == 39:  # DefineSprite: id, frame count, its tags
                self.sprites[struct.unpack_from("<H", body)[0]] = list(_tags(body, 4))
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

    def display_list(self, sid: int, label: str | None = None) -> list[tuple[int, Affine]]:
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
        return [shown[d] for d in sorted(own) if d in shown]

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


_movies: dict[tuple[str, float], _Movie] = {}  # (package file, mtime) -> its parsed menu movie (one: kept)
_lock = threading.Lock()


def _menu_movie(cooked: Path) -> _Movie:
    path = cooked / MENU_PACKAGE
    key = (str(path), path.stat().st_mtime)
    with _lock:
        if key not in _movies:
            pkg = Bl1Package(path)
            try:
                idx = pkg.find(MENU_MOVIE, "GFxMovieInfo")
                if idx is None:
                    raise FileNotFoundError(f"{MENU_MOVIE} not in {path.name}")
                _movies.clear()
                _movies[key] = _Movie(_movie_raw(pkg, idx))
            finally:
                pkg.close()
        return _movies[key]


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


def load_map(cooked: Path, map_frame: str) -> list[MapImage]:
    """The level's map (its anchor's MapFrame) as one image, its bounds in the map sprite's px. [] when the menu movie
    has no such frame (a DLC's map: its own movie, not read yet)."""
    key = (str(cooked), map_frame.lower(), (cooked / MENU_PACKAGE).stat().st_mtime)
    with _lock:
        if key in _rendered:
            return _rendered[key]
    images = _render(cooked, map_frame)
    with _lock:
        _rendered[key] = images
        while len(_rendered) > KEEP_RENDERED:
            del _rendered[next(iter(_rendered))]
    return images


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
