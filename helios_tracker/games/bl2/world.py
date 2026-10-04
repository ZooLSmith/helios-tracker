"""Borderlands 2's world (the base: every game's unless its profile has its own) - The level and the world: its map's name and key, whether it's paused, its map's source, its level names.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part

MOVIE_SCALE = 4  # tactical map movie px per volume "pixel": UnrealUnitsPerPixel is 32, the fit gave 128 uu / px


class World(Part):
    """The level and the world: its map's name and key, whether it's paused, its map's source, its level names."""

    def map_name(self, wi: Any) -> str:
        """The persistent level's map name ("Sanctuary_P"), from the world info."""
        return str(wi.GetStreamingPersistentMapName())

    def paused(self, wi: Any) -> bool:
        """Whether the game's world stands still (its menu): WorldInfo.Pauser set. (Not every clock: shops.py.)"""
        return wi.Pauser is not None

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        """A map's name as the game shows it, from one of its level lists (a LevelDependencyList: the base game's
        GD_Globals.General.LevelList, one per DLC - each knowing only its own maps), "" if it doesn't know it."""
        return str(level_list.GetFriendlyLevelNameFromMapName(map_name))

    def level_key(self, wi: Any, map_name: str) -> tuple:
        """What tells levels apart, read every second (cheap): another one = a new level."""
        return map_name, _tactical_key(wi)

    def map_source(self, wi: Any, map_name: str) -> Any:
        """The level's map (levelmap.MapSource: its placement, how its images load), None without one - at a level
        change, on the game thread."""
        return _tactical(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        """ClientPlayBinkMovie's arguments: whether the video can't be skipped."""
        return bool(args.bForceNoSkip)


def _tactical_key(wi: Any) -> str | None:
    """The level's map volume (a cheap read, every check): its path."""
    info = wi.GetMapInfo()
    vol = info.TacticalMapVolume if info is not None else None
    return vol._path_name() if vol is not None else None


def _tactical(wi: Any, map_name: str) -> Any:
    """The level's map: its map info's TacticalMapVolume (the placement) and TacticalMapMovie (its images and fog of war,
    out of the level's package: tacmap.py)."""
    from ... import gamedir, levelmap  # noqa: PLC0415
    from ...util import log, try_  # noqa: PLC0415

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

    def load() -> Any:  # (a levelmap.MapResult)
        package = gamedir.package_path(f"{map_name}.upk")  # the base game's, or a DLC's
        if package is None:
            raise FileNotFoundError(f"couldn't find {map_name}.upk (WillowGame/CookedPCConsole, DLC/*/*/Content)")
        return levelmap.cache.get((str(package).lower(), package.stat().st_mtime, movie_path.lower()),
                                  lambda: _tactical_files(package, movie_path))

    return levelmap.MapSource(vol._path_name(), placement, load)


def _tactical_files(package: Any, movie: str) -> Any:
    from ... import levelmap  # noqa: PLC0415
    from ...tacmap import load_fog, load_tactical_map  # noqa: PLC0415
    from ...util import log_error  # noqa: PLC0415

    images = load_tactical_map(package, movie)
    try:
        fog = load_fog(package, movie)
    except Exception as ex:  # noqa: BLE001 - the map still shows without its fog
        log_error("fog of war extraction", ex)
        fog = None
    return levelmap.MapResult(images, fog)
