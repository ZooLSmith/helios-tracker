# Dev probe (in game), instant: whether Loot Midget World's level merges took (its .blcm's "set ... LevelList" lines:
# other maps' persistent levels as secondary maps of every map - icecanyon_p, CraterLake_P... - a crash report with
# that mod). Lists the current map's entry in the level lists (its SecondaryMaps), the world's streaming levels (loaded?
# visible?), the interactive objects per level - whether that level is one of the world's - and the state of a few
# of those outside it (the crash: GetTargetName on one, building its record). Read-only (properties, no calls but
# GetCurrentWorldInfo). Run it in a map the mod changes (Three Horns - Divide: Ice_P). (Before collector._levels, Helios
# Tracker had to be off: it crashed there.)
# Writes probe_lmw_levels.txt in the mod's data folder (sdk_mods/.helios_tracker: works from a .sdkmod too;
# overwrites; after each section)
#   py exec(open(r"<repo>\tools\probes\probe_lmw_levels.py").read())
from collections import Counter

import unrealsdk
from mods_base import ENGINE

from helios_tracker.paths import DATA

OUT = DATA / "probe_lmw_levels.txt"
lines: list[str] = []


def _write() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


wi = ENGINE.GetCurrentWorldInfo()
current = str(_try(lambda: wi.GetStreamingPersistentMapName()))
lines.append(f"current map: {current}")
_write()

lines.append("\n== level lists: the current map's entry")
for lst in unrealsdk.find_all("LevelDependencyList", exact=False):
    if str(lst.Name).startswith("Default__"):
        continue
    for entry in lst.LevelList:
        if str(entry.PersistentMap).lower() == current.lower():
            lines.append(f"{lst._path_name()}: {entry.PersistentMap} \"{entry.LevelName}\"")
            lines.append(f"  SecondaryMaps: {[str(m) for m in entry.SecondaryMaps]}")
            lines.append(f"  ConnectedPersistents: {[str(m) for m in entry.ConnectedPersistents]}")
_write()

lines.append("\n== streaming levels")
for level in wi.StreamingLevels:
    if level is None:
        lines.append("None")
        continue
    loaded = _try(lambda level=level: level.LoadedLevel)
    lines.append(f"{level.Class.Name} {level.PackageName}: loaded {loaded is not None and not isinstance(loaded, str)}"
                 f", should be visible {_try(lambda level=level: level.bShouldBeVisible)}"
                 f", visible {_try(lambda level=level: level.bIsVisible)}"
                 f", should be loaded {_try(lambda level=level: level.bShouldBeLoaded)}")
_write()

# the world's levels: the persistent one (the world info's Outer) and the streaming levels' loaded ones
world_levels = {wi.Outer._get_address()} | {
    lvl._get_address() for s in wi.StreamingLevels if s is not None and (lvl := _try(lambda s=s: s.LoadedLevel, None)) is not None}
lines.append(f"\nworld levels: {len(world_levels)} (persistent {wi.Outer._path_name()})")

lines.append("\n== interactive objects per level (their Outer; [world] = one of the world's levels)")
ios = [io for io in unrealsdk.find_all("WillowInteractiveObject", exact=False) if not io.Name.startswith("Default__")]
per_level = Counter((str(_try(lambda io=io: io.Outer._path_name())),
                     _try(lambda io=io: io.Outer._get_address() in world_levels, False)) for io in ios)
lines.extend(f"{n:5} {'[world] ' if in_world else ''}{name}" for (name, in_world), n in per_level.most_common())
_write()

lines.append("\n== a few objects of each level outside the world: their state (properties only)")
shown = Counter()
for io in ios:
    outer = _try(lambda io=io: io.Outer, None)
    if outer is None or outer._get_address() in world_levels or shown[outer._get_address()] >= 3:
        continue
    shown[outer._get_address()] += 1
    lines.append(io._path_name())
    for prop in ("InteractiveObjectDefinition", "bDeleteMe", "bHidden", "bTickIsDisabled", "CollisionComponent",
                 "Location", "WorldInfo", "Owner", "CreationTime"):
        lines.append(f"  {prop}: {_try(lambda io=io, prop=prop: getattr(io, prop))}")
    lines.append(f"  balance: {_try(lambda io=io: io.BalanceDefinitionState.BalanceDefinition)}")
    _write()
lines.append("\ndone")
_write()
