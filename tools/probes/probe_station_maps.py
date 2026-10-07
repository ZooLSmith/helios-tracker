# Dev probe (in game), instant: where a mission's station is, for "Given at" - a level travel station like Fink's
# Slaughterhouse's (GD_LevelTravelStations.Zone2.BanditSlaughterToFridge, probe_area.txt) names a map the user sees as
# part of another (The Fridge): is it its own map, and what links it to the other? Properties only (no blind calls).
# Logs: every station the log's missions point to (TravelStation / TurnInStation): class, StationDisplayName,
# StationLevelName, its map's name (LevelDependencyList.GetFriendlyLevelNameFromMapName - the collector's), and a
# LevelTravelStationDefinition's own fields in full; then each station map's level list entry (ConnectedPersistents,
# SecondaryMaps).
# Writes tools/probes/probe_station_maps.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_station_maps.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_station_maps.txt"
SCALARS = {"StrProperty", "NameProperty", "ObjectProperty", "ByteProperty", "IntProperty", "BoolProperty", "ArrayProperty"}
STOP = {"Object", "GBXDefinition"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f)))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name in SCALARS) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v) for v in list(value)[:12]) + (f", ... ({len(value)})" if len(value) > 12 else "") + "]"
    return repr(value)


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    lists = [o for o in _try(lambda: list(unrealsdk.find_all("LevelDependencyList", exact=False)), [])
             if not o.Name.startswith("Default__")]
    entries: dict[str, object] = {}
    for lst in lists:
        for e in _try(lambda lst=lst: list(lst.LevelList), []) or []:
            entries.setdefault(str(_try(lambda e=e: e.PersistentMap, "")).lower(), e)

    def friendly(map_name: str) -> str:
        for lst in lists:
            if name := _try(lambda lst=lst: str(lst.GetFriendlyLevelNameFromMapName(map_name)), ""):
                return name
        return ""

    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    stations: dict[str, object] = {}
    for e in _try(lambda: list(trackers[0].MissionList), []) or []:
        m = _try(lambda e=e: e.MissionDef, None)
        for field in ("TravelStation", "TurnInStation"):
            s = _try(lambda m=m, f=field: getattr(m, f), None)
            if s is not None and not isinstance(s, str):
                stations.setdefault(_try(s._path_name, "?"), s)
    lines.append(f"== {len(stations)} station definitions the missions point to")
    maps: set[str] = set()
    for path in sorted(stations):
        s = stations[path]
        level = str(_try(lambda s=s: s.StationLevelName, ""))
        maps.add(level.lower())
        lines.append(f"   {s.Class.Name} {path}: {_try(lambda s=s: str(s.StationDisplayName))!r} in {level!r} "
                     f"= {friendly(level)!r}")
    _flush()
    lines.append("== level travel stations in full")
    for path in sorted(stations):
        s = stations[path]
        if s.Class.Name != "LevelTravelStationDefinition":
            continue
        lines.append(f"   -- {path}")
        c = s.Class
        while c is not None and c.Name not in STOP:
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name in SCALARS:
                    lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f, s=s: _brief(s._get_field(f)))}")
            c = c.SuperField
    _flush()
    lines.append("== the station maps' level list entries")
    for level in sorted(maps):
        e = entries.get(level)
        lines.append(f"   {level}: {_brief(e) if e is not None else 'no entry'}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"probe_station_maps: {len(lines)} lines -> {OUT}")
