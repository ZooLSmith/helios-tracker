"""Borderlands 2's world (the base: every game's unless its profile has its own) - The level and the world: its map's name and key, whether it's paused, its map's source, its level names."""

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

    def area_name(self, area: Any) -> str:
        """A discovery area's name as the game shows it (a WorldDiscoveryArea: "Wreck Of The Ice Sickle"; empty for one
        that only clears the map's fog)."""
        return str(area.WorldAreaDisplayName or "")

    def travel_network(self) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """The ways between maps and the fast travel stations (travel.py), static game data: ([(from map, to map)],
        [(station name, its map)]). Every one loaded wherever the player is, every DLC's (tools/probes/probe_fast_travel.txt:
        75 stations in Thousand Cuts; probe_level_exits_VOGChamber_P.txt: 178 exits, 75 stations). The links: each exit
        (a LevelTravelStationDefinition in its StationLevelName, to its DestinationStationDefinition's) and the level
        lists' ConnectedPersistents - both: the exits have links the lists lack (Sanctuary <-> Control Core Angel, Dragon
        Keep's), the lists one the exits name wrong (Dragon Keep's exits to a "Dungeons_P" no list knows: Dungeon_P). A
        few find_all (every object walked): once."""
        import unrealsdk  # noqa: PLC0415

        def live(cls: str, exact: bool = True) -> list[Any]:
            return [o for o in unrealsdk.find_all(cls, exact=exact) if not o.Name.startswith("Default__")]

        links = []
        for exit_ in live("LevelTravelStationDefinition"):
            if (dest := exit_.DestinationStationDefinition) is not None:
                links.append((str(exit_.StationLevelName), str(dest.StationLevelName)))
        for level_list in live("LevelDependencyList", exact=False):
            for entry in level_list.LevelList:
                links.extend((str(entry.PersistentMap), str(c)) for c in entry.ConnectedPersistents)
        # (bSendOnly ignored: The Bunker's is, and it can be travelled to - the user; so are DamTop's and Wilhelm's, both
        # in the player's ActivatedTeleportersList)
        stations = [(str(s.Name), str(s.StationLevelName)) for s in live("FastTravelStationDefinition")]
        return links, stations

    def unlocked_stations(self, pc: Any) -> list[str]:
        """The fast travel stations the player activated, by their definitions' names (the controller's
        ActivatedTeleportersList: ['Sanctuary', 'TheFridge', ...] - probe_fast_travel.txt). Names only: the base game's
        and a DLC's Cliffs share one."""
        return [str(n) for n in pc.ActivatedTeleportersList]

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
    out of the level's package: files/tacmap.py)."""
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
    from .files.tacmap import load_fog, load_tactical_map  # noqa: PLC0415
    from ...util import log_error  # noqa: PLC0415

    images = load_tactical_map(package, movie)
    try:
        fog = load_fog(package, movie)
    except Exception as ex:  # noqa: BLE001 - the map still shows without its fog
        log_error("fog of war extraction", ex)
        fog = None
    return levelmap.MapResult(images, fog)
