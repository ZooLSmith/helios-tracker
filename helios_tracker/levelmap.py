"""
A level's map: where it sits in the world (the page's center / upp...) and how its images are read - what every game's
map source gives (games.GAME.world.map_source, each game's way): on the game thread, its placement read from the
level's objects; then MapSource.load, on the map thread: files only. No SDK here.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MapImage:
    name: str
    format: str  # EPixelFormat, e.g. "PF_DXT5" - decoded by the web page
    width: int
    height: int
    data: bytes  # top mip, as stored
    bounds: tuple[float, float, float, float]  # x0, x1, y0, y1 in movie px
    crop: tuple[int, int, int, int] | None = None  # the part drawn in bounds (x, y, w, h px: a sub-image), None all


@dataclass
class MapFog:
    blob: MapImage  # the fog piece (bounds: its shape's, around 0)
    pieces: list[tuple[str, tuple[float, ...]]]  # (area short name, matrix placing the blob: _affine)


@dataclass
class MapResult:
    images: list[MapImage]
    fog: MapFog | None = None
    placement: dict[str, Any] = field(default_factory=dict)  # what only the files tell (a map its files place: center, upp)


@dataclass
class MapSource:
    key: str  # the map: another one = a new level
    placement: dict[str, Any]  # what the game thread knows (BL2: center, upp, north, zmin, zmax; killz)
    load: Callable[[], MapResult]  # the map thread: files only


class _Cache:
    """Map results by key (a package file, its date, the movie...): revisiting a level is free."""

    def __init__(self, size: int = 4) -> None:
        self._size = size
        self._items: dict[tuple, MapResult] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple, make: Callable[[], MapResult]) -> MapResult:
        with self._lock:
            if key in self._items:
                return self._items[key]
        result = make()
        with self._lock:
            self._items[key] = result
            while len(self._items) > self._size:
                del self._items[next(iter(self._items))]
        return result


cache = _Cache()  # (the map sources': by their own key)
