"""
A level's map: where it sits in the world (the page's center / upp...) and how its images are read - one kind per way
a game builds its map, the profile picking (games.py map_source):
- tactical: BL2's / the Pre-Sequel's - the map info's TacticalMapVolume (the placement) and TacticalMapMovie (its
  images and fog of war, out of the level's package: tacmap.py);
- landmark: Borderlands 1's - the area's LevelLandmarkAnchor (the placement, its map frame) and the menu movie's vector
  frame rendered (bl1map.py).
On the game thread: tactical() / landmark() read the level's objects. Then MapSource.load, on the map thread: files
only.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import unrealsdk

from . import bl1map, gamedir
from .tacmap import MapFog, MapImage, load_fog, load_tactical_map
from .util import log, log_error, try_

MOVIE_SCALE = 4  # movie px per volume "pixel": UnrealUnitsPerPixel is 32, the fit gave 128 uu / px


@dataclass
class MapResult:
    images: list[MapImage]
    fog: MapFog | None = None
    placement: dict[str, Any] = field(default_factory=dict)  # what only the files tell (BL1: center, upp)


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


_cache = _Cache()

# region Tactical map (BL2, the Pre-Sequel)


def tactical_key(wi: Any) -> str | None:
    """The level's map volume (a cheap read, every check): its path."""
    info = wi.GetMapInfo()
    vol = info.TacticalMapVolume if info is not None else None
    return vol._path_name() if vol is not None else None


def tactical(wi: Any, map_name: str) -> MapSource | None:
    info = wi.GetMapInfo()
    vol = info.TacticalMapVolume if info is not None else None
    movie = info.TacticalMapMovie if info is not None else None
    if vol is None or movie is None:
        log(f"no map for {map_name}: its map info {try_(lambda: info._path_name()) if info is not None else None},"
            f" TacticalMapVolume {vol is not None}, TacticalMapMovie {movie is not None}")
        return None
    bounds = vol.BrushComponent.Bounds
    c = bounds.Origin
    placement = {
        "center": [c.X, c.Y],
        "upp": vol.UnrealUnitsPerPixel * MOVIE_SCALE,
        "north": vol.NorthOffsetInDegreesClockwise,
        # The mapped level's vertical range (the volume's box): below it = fallen off the map
        # (the game only destroys what goes under KillZ, which can be far lower)
        "zmin": round(c.Z - bounds.BoxExtent.Z),
        "zmax": round(c.Z + bounds.BoxExtent.Z),
        "killz": try_(lambda: round(wi.KillZ)),
    }
    movie_path = movie._path_name()

    def load() -> MapResult:
        package = gamedir.package_path(f"{map_name}.upk")  # the base game's, or a DLC's
        if package is None:
            raise FileNotFoundError(f"couldn't find {map_name}.upk (WillowGame/CookedPCConsole, DLC/*/*/Content)")
        return _cache.get((str(package).lower(), package.stat().st_mtime, movie_path.lower()),
                          lambda: _tactical_files(package, movie_path))

    return MapSource(vol._path_name(), placement, load)


def _tactical_files(package: Path, movie: str) -> MapResult:
    images = load_tactical_map(package, movie)
    try:
        fog = load_fog(package, movie)
    except Exception as ex:  # noqa: BLE001 - the map still shows without its fog
        log_error("fog of war extraction", ex)
        fog = None
    return MapResult(images, fog)


# endregion
# region Landmark map (Borderlands 1)


def landmark(wi: Any, map_name: str) -> MapSource | None:
    """The area's map anchor (one LevelLandmarkAnchor per area, in its persistent level - tools/probes/probe_bl1.txt:
    arid_p's) - a find_all, at a level change only."""
    prefix = map_name.lower() + "."
    anchor = next((a for a in unrealsdk.find_all("LevelLandmarkAnchor", exact=True)
                   if a._path_name().lower().startswith(prefix)), None)
    if anchor is None:
        log(f"no map for {map_name}: no LevelLandmarkAnchor in it")
        return None
    scale = anchor.DrawScale
    numbers = bl1map.Anchor(str(anchor.MapFrame), anchor.Location.X, anchor.Location.Y, anchor.Rotation.Yaw,
                            scale * anchor.DrawScale3D.X, scale * anchor.DrawScale3D.Y,
                            anchor.TextureSizeX, anchor.TextureSizeY)
    if abs(numbers.yaw) > 182:  # (1 degree: the page's map doesn't turn - bl1map.placement)
        log(f"map anchor of {map_name} turned {numbers.yaw * 360 / 65536:.1f} degrees: its map placed unturned")
    cooked = gamedir.cooked_dir()

    def load() -> MapResult:
        if cooked is None:
            raise FileNotFoundError("couldn't find the game's WillowGame/CookedPC")
        images = bl1map.load_map(cooked, numbers.frame)
        if not images:
            return MapResult([])
        x0, x1, y0, y1 = images[0].bounds
        center, upp = bl1map.placement(numbers, (x1 - x0, y1 - y0))
        return MapResult(images, None, {"center": center, "upp": upp})

    return MapSource(anchor._path_name(), {"killz": try_(lambda: round(wi.KillZ))}, load)


# endregion
