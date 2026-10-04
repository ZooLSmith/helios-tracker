"""
The games the mod runs in, and what differs between them: one profile per game, picked once at the mod's boot
(pick() -> GAME). Nothing else in the mod names a game or probes the SDK to find out which one it's in (no hasattr /
try_ to guess): it asks GAME - its parts (GAME.missions.status(entry), GAME.world.map_name(wi)...) and its data
(GAME.key, GAME.features, GAME.packages...).

- A system a game doesn't have is a feature it lacks (`"oxygen" in GAME.features`): the work for it doesn't run.
  Another way of doing a job is a method of a part, never a feature (profiles.md).
- A profile is a set of parts, one per domain (base.py: world, missions, items, objects, pawns, shops, skills, assets,
  ui). Borderlands 2's are the base (bl2/); another game subclasses only the parts that differ (bl1/), a small one is a
  file of data (tps.py, aodk.py) - each difference with what showed it (a probe, a log).
- Importing this package needs no SDK (the files worker, tools): the profile is picked by pick(), at the mod's boot.

The page gets the profile's key and features in the level message (collector.py) and follows them (web/js/game.js).
New game: its profile here (a file, or a folder of its parts), registered under mods_base's name for it (Game.<NAME>);
.agent/<game>.md for what was seen. .agent/profiles.md: the plan this follows.
"""

import functools
import inspect
from typing import Any

# The features: systems some games have, others don't - only those (the page reads the same names: game.js). Another way
# of doing a job is a method, never a feature (profiles.md: "if the else does something, it's a method").
DISCOVERY = "discovery"  # the level's discovery areas and the map's fog of war (WorldDiscoveryArea, DiscoveredWorldAreas)
OXYGEN = "oxygen"  # the Oz meter: oxygen pools, air domes, oxygen sources
JUMPPADS = "jumppads"  # jump pads and geysers (OzPlayerJumpPad)

_PROFILES: dict[str, type[Any]] = {}


def profile(*names: str):  # noqa: ANN201
    """Registers a profile class for these games (mods_base's Game names: "BL2", "TPS"...)."""

    def register(cls: type[Any]) -> type[Any]:
        for name in names:
            _PROFILES[name] = cls
        return cls

    return register


def make_profile(name: str) -> Any:
    """The profile of a game, by mods_base's name for it ("BL2", "TPS"...): its parts' public methods logging their
    failures (_logged)."""
    if (cls := _PROFILES.get(name)) is None:
        raise RuntimeError(f"Helios Tracker doesn't know the game {name!r}")
    made = cls()
    for part in made.parts.values():
        for attr in dir(type(part)):
            if not attr.startswith("_") and attr != "level_changed" and inspect.ismethod(method := getattr(part, attr)):
                setattr(part, attr, _logged(f"games.{type(part).__name__}.{attr}", method))
    return made


def _logged(where: str, method: Any) -> Any:
    """A profile method that logs its first failure of each exception type (util.log_error: with its traceback), then
    raises it as before. Its callers keep their defaults (try_(lambda: games.GAME.x(...), default)) - but a method wrong
    for a game no longer fails silently: BL1's card accuracy once read 7 for the game's 6.7, a property it doesn't have
    quietly read as the default (profiles.md, point 1). Once per type: the same failure on every object isn't a flood."""
    seen: set[type] = set()

    @functools.wraps(method)
    def call(*args: Any, **kwargs: Any) -> Any:
        try:
            return method(*args, **kwargs)
        except Exception as ex:
            if type(ex) not in seen:
                seen.add(type(ex))
                from ..util import log_error  # noqa: PLC0415 - (games: imported before util's log is set up)

                log_error(where, ex)
            raise

    return call


GAME: Any = None  # the game running (pick(), at the mod's boot - read as games.GAME, at the time: a test swaps it)


def pick() -> Any:
    """The game running's profile, once at the mod's boot (__init__.py): GAME."""
    global GAME  # noqa: PLW0603
    import mods_base  # noqa: PLC0415

    GAME = make_profile(mods_base.Game.get_current().name)
    return GAME


def _level_changed() -> None:
    if GAME is not None:
        GAME.level_changed()  # (the profile in use when the level changes: read at the time)


from ..util import on_level_change  # noqa: E402 - (util: no SDK, no games import at module level)

on_level_change(_level_changed)

from . import aodk, bl1, bl2, tps  # noqa: E402, F401 - (the profiles, registered)
