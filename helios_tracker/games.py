"""
The games the mod runs in, and what differs between them: one profile per game, picked once (GAME). Nothing else in
the mod names a game or probes the SDK to find out which one it's in (no hasattr / try_ to guess): it asks GAME.

- A system a game doesn't have is a feature it lacks (`"oxygen" in GAME.features`): the work for it doesn't run.
- An API spelled differently is a method the game's profile overrides (`GAME.map_name(wi)`).
- Profile is BL2, the reference; each other game overrides only what differs from it, each difference with what
  showed it (a probe, a log). A game's own objects (the Pre-Sequel's jump pads, oxygen cracks) need no entry: they're
  recognized from the game's data, and simply never met in another game.

The page gets the profile's key and features in the level message (collector.py) and follows them (web/js/game.js).
New game: its class here, registered under mods_base's name for it (Game.<NAME>); .agent/<game>.md for what was seen.
"""

from typing import Any

# The features (systems some games have, others don't); the page reads the same names (game.js)
TACMAP = "tacmap"  # the map screen's images, read from the game's packages (tacmap.py)
DISCOVERY = "discovery"  # the level's discovery areas and the map's fog of war (WorldDiscoveryArea, DiscoveredWorldAreas)
OXYGEN = "oxygen"  # the Oz meter: oxygen pools, air domes, oxygen sources
JUMPPADS = "jumppads"  # jump pads and geysers (OzPlayerJumpPad)
SCAN = "scan"  # the game files' index: fonts, item card / skill icons (gamescan.py: BL2's package layout)

_PROFILES: dict[str, type["Profile"]] = {}


def profile(*names: str):  # noqa: ANN201
    """Registers a profile class for these games (mods_base's Game names: "BL2", "TPS"...)."""

    def register(cls: type["Profile"]) -> type["Profile"]:
        for name in names:
            _PROFILES[name] = cls
        return cls

    return register


@profile("BL2")
class Profile:
    """Borderlands 2: the reference - what the mod was built on."""

    key = "bl2"  # the page's name for it (the level message's "game": its label variants, its own data - game.js)
    packages = "CookedPCConsole"  # WillowGame/<this>: its cooked packages, the folder the mod reads (None: none read)
    exe_depth = 2  # the game's folder: this many up from its executable's (Binaries/Win32/Borderlands2.exe)
    gibbed_prefix = "BL2"  # a gear's code for Gibbed's save editor: "BL2(...)" ("": no editor)
    features: frozenset[str] = frozenset({TACMAP, DISCOVERY, SCAN})

    def map_name(self, wi: Any) -> str:
        """The persistent level's map name ("Sanctuary_P"), from the world info."""
        return str(wi.GetStreamingPersistentMapName())

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        """A map's name as the game shows it, from one of its level lists (a LevelDependencyList: the base game's
        GD_Globals.General.LevelList, one per DLC - each knowing only its own maps), "" if it doesn't know it."""
        return str(level_list.GetFriendlyLevelNameFromMapName(map_name))

    def level_key(self, wi: Any, map_name: str) -> tuple:
        """What tells levels apart, read every second (cheap): another one = a new level."""
        from . import levelmap  # noqa: PLC0415

        return map_name, levelmap.tactical_key(wi)

    def map_source(self, wi: Any, map_name: str) -> Any:
        """The level's map (levelmap.MapSource: its placement, how its images load), None without one - at a level
        change, on the game thread."""
        from . import levelmap  # noqa: PLC0415

        return levelmap.tactical(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        """ClientPlayBinkMovie's arguments: whether the video can't be skipped."""
        return bool(args.bForceNoSkip)

    def show_message(self, text: str, duration: float) -> None:
        """The game's bottom-left message (ui_utils' co-op one: it stays until hide_message)."""
        from ui_utils import show_coop_message  # noqa: PLC0415 (not in every game's ui_utils: BL1's)

        show_coop_message(text)

    def hide_message(self) -> None:
        from ui_utils import hide_coop_message  # noqa: PLC0415

        hide_coop_message()


@profile("TPS")
class PreSequel(Profile):
    """Borderlands: The Pre-Sequel (.agent/presequel.md)."""

    key = "tps"
    gibbed_prefix = "BLOZ"
    features = Profile.features | {OXYGEN, JUMPPADS}


@profile("AoDK")
class DragonKeep(Profile):
    """Tiny Tina's Assault on Dragon Keep, the standalone: BL2's engine and data."""

    key = "aodk"
    gibbed_prefix = ""  # no Gibbed editor for it


@profile("BL1")
class Borderlands1(Profile):
    """Borderlands 1, the original 2009 game (the Enhanced edition's SDK didn't run: not registered) - .agent/bl1.md."""

    key = "bl1"
    packages = "CookedPC"  # its packages: version 584 (BL2's 832) - read with upk_bl1.Bl1Package (its map: bl1map.py)
    exe_depth = 1  # Binaries/Borderlands.exe
    gibbed_prefix = ""
    # no WorldDiscoveryArea class (the log: "Couldn't find class"); its packages not indexed (gamescan reads BL2's)
    features = Profile.features - {DISCOVERY, SCAN}

    def map_name(self, wi: Any) -> str:
        # The world is "Loader" in every area (tools/probes/probe_bl1.txt): the area is streamed in, the first of its
        # StreamingLevels - a LevelStreamingPersistent ('arid_p'), the others its sublevels (LevelStreamingKismet). No
        # GetStreamingPersistentMapName (AttributeError). None streamed in (the main menu): the world's own package,
        # its path's first part ("menumap.TheWorld:PersistentLevel.WorldInfo_0").
        for level in wi.StreamingLevels:
            if level is not None and level.Class.Name == "LevelStreamingPersistent":
                return str(level.PackageName)
        return wi._path_name().split(".", 1)[0]

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        # its lists' entries, read as properties: {PersistentMap 'arid_p', LevelName 'Arid Badlands' (the game's text,
        # localized)...} - gd_globals.General.LevelList, offline (.agent/bl1.md "Level names")
        want = map_name.lower()
        return next((str(entry.LevelName) for entry in level_list.LevelList if str(entry.PersistentMap).lower() == want), "")

    def level_key(self, wi: Any, map_name: str) -> tuple:
        return (map_name,)  # (one map anchor per area: found at the change - levelmap.landmark)

    def map_source(self, wi: Any, map_name: str) -> Any:
        from . import levelmap  # noqa: PLC0415

        return levelmap.landmark(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        return False  # no bForceNoSkip argument (the log: AttributeError)

    def show_message(self, text: str, duration: float) -> None:
        # BL1's ui_utils (1.3) has no co-op message: its HUD one, which goes away by itself
        from ui_utils import show_hud_message  # noqa: PLC0415

        from .i18n import t  # noqa: PLC0415

        show_hud_message(t("box.title"), text, duration)

    def hide_message(self) -> None:
        pass


def make_profile(name: str) -> Profile:
    """The profile of a game, by mods_base's name for it ("BL2", "TPS"...)."""
    if (cls := _PROFILES.get(name)) is None:
        raise RuntimeError(f"Helios Tracker doesn't know the game {name!r}")
    return cls()


def _current() -> Profile:
    import mods_base  # noqa: PLC0415

    return make_profile(mods_base.Game.get_current().name)


GAME: Profile = _current()  # the game running (read as games.GAME, at the time: a test swaps it)
