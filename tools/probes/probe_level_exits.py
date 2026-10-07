# Dev probe (in game), instant: the maps' real exits, for "via" (the nearest map fast travel reaches, for a map without a
# station - Fink's Slaughterhouse: via The Fridge). probe_fast_travel.txt read the links from the level lists'
# ConnectedPersistents, which list maps as their own neighbours (VOGChamber_P, Sanctuary_Hole_P) - streaming, maybe not
# exits. The exits: every LevelTravelStationDefinition (its map: StationLevelName; where it leads: its
# DestinationStationDefinition's). Properties only (no blind calls).
# Logs: the current map; every LevelTravelStationDefinition loaded (are they all, whatever the map?); the links they make
# against ConnectedPersistents' (in one only, either way); the fast travel stations count (all loaded here too?); the
# Sanctuary maps (Sanctuary_P / SanctuaryAir_P: which one is the current map when in Sanctuary late in the story).
# Run it on two maps - one of them Sanctuary after it lifts off, if the save is there.
# Writes tools/probes/probe_level_exits_<map>.txt (one per map: overwrites that map's)
#   py exec(open(r"<repo>\tools\probes\probe_level_exits.py").read())
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _live(cls: str) -> list:
    return [o for o in _try(lambda: list(unrealsdk.find_all(cls, exact=True)), []) if not o.Name.startswith("Default__")]


wi = ENGINE.GetCurrentWorldInfo()
MAP = str(_try(lambda: wi.GetStreamingPersistentMapName(), "unknown"))
OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / f"probe_level_exits_{MAP}.txt"


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    lines.append(f"map: {MAP}  (GetMapName: {_try(lambda: str(wi.GetMapName(False)))})")
    exits = _live("LevelTravelStationDefinition")
    lines.append(f"== {len(exits)} LevelTravelStationDefinition loaded")
    by_exits: set[tuple[str, str]] = set()
    for s in sorted(exits, key=lambda s: _try(s._path_name, "")):
        here = str(_try(lambda s=s: s.StationLevelName, ""))
        dest = _try(lambda s=s: s.DestinationStationDefinition, None)
        there = str(_try(lambda d=dest: d.StationLevelName, "")) if dest is not None and not isinstance(dest, str) else ""
        lines.append(f"   {_try(s._path_name)}: {here!r} -> {there!r} "
                     f"({_try(lambda s=s: str(s.StationDisplayName))!r}, dest {_try(lambda d=dest: d._path_name(), dest)}, "
                     f"dlc {_try(lambda s=s: s.DlcExpansion._path_name(), None)})")
        if here and there:
            by_exits.add((here.lower(), there.lower()))
    _flush()

    lists = [o for o in _try(lambda: list(unrealsdk.find_all("LevelDependencyList", exact=False)), [])
             if not o.Name.startswith("Default__")]
    by_lists: set[tuple[str, str]] = set()
    titles: dict[str, str] = {}
    for lst in lists:
        for e in _try(lambda lst=lst: list(lst.LevelList), []) or []:
            here = str(_try(lambda e=e: e.PersistentMap, "")).lower()
            titles[here] = str(_try(lambda e=e: e.LevelName, ""))
            for c in _try(lambda e=e: list(e.ConnectedPersistents), []) or []:
                by_lists.add((here, str(c).lower()))
    lines.append(f"== links: {len(by_exits)} from the exits, {len(by_lists)} from ConnectedPersistents")
    lines.append("   -- exits only (an exit, not in the level list):")
    lines.extend(f"      {a} ({titles.get(a, '?')}) -> {b} ({titles.get(b, '?')})" for a, b in sorted(by_exits - by_lists))
    lines.append("   -- level list only (no exit makes it):")
    lines.extend(f"      {a} ({titles.get(a, '?')}) -> {b} ({titles.get(b, '?')})" for a, b in sorted(by_lists - by_exits))
    lines.append("   -- one way in the exits (a -> b, no b -> a):")
    lines.extend(f"      {a} -> {b}" for a, b in sorted(by_exits) if (b, a) not in by_exits)
    _flush()

    stations = _live("FastTravelStationDefinition")
    lines.append(f"== {len(stations)} FastTravelStationDefinition loaded")
    activated = [str(n) for n in _try(lambda: list(get_pc().ActivatedTeleportersList), []) or []]
    lines.append(f"== ActivatedTeleportersList: {len(activated)} {activated}")
    lines.append("== Sanctuary")
    for key in ("sanctuary_p", "sanctuaryair_p", "sanctuary_hole_p"):
        lines.append(f"   {key}: in the level list as {titles.get(key, '(none)')!r}")
    for s in stations:
        if "sanctuary" in str(_try(lambda s=s: s.StationLevelName, "")).lower():
            lines.append(f"   station {_try(s._path_name)}: in {str(_try(lambda s=s: s.StationLevelName))!r}, "
                         f"inaccessible at {_try(lambda s=s: s.InaccessibleObjective._path_name(), None)}, "
                         f"accessible at {_try(lambda s=s: s.AccessibleObjective._path_name(), None)}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"probe_level_exits: {len(lines)} lines -> {OUT}")
