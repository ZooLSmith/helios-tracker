# Dev probe (in game), instant: how to tell which missions are from the current area - for the
# mission log (highlight that area's name). Run it in a level with a few of its missions in the log
# (ideally one tracked there).
# Logs: the current map; every travel station definition the missions point to (TravelStation /
# TurnInStation: class, name, every scalar property - a level / map name?), the first ones in full;
# the travel station actors in the level (class, their definition fields) - to match a mission's
# station to the level; the functions on the player controller / world info / tracker that map a
# region or mission to a level, and GetLevelForMission for the tracked mission; and the level's own
# name (LevelDependencyList.GetFriendlyLevelNameFromMapName, the map info, functions naming levels).
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_area.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_area.py").read())
import enum
import re
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_area.txt")
SCALARS = {"StrProperty", "NameProperty", "ObjectProperty", "ByteProperty", "IntProperty", "BoolProperty", "ArrayProperty"}
STOP = {"Object", "Actor", "GBXDefinition"}
FULL = 4  # station definitions dumped in full
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
        return "[" + ", ".join(_brief(v) for v in list(value)[:8]) + (f", ... ({len(value)})" if len(value) > 8 else "") + "]"
    return repr(value)


def _dump(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"   -- {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in STOP:
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name in SCALARS:
                lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    lines.append(f"map: {_try(lambda: str(wi.GetStreamingPersistentMapName()))}  (GetMapName: {_try(lambda: str(wi.GetMapName(False)))})")
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    tracker = trackers[0] if trackers else None
    tracked = _try(lambda: tracker.ActiveMission, None)
    lines.append(f"tracked: {_brief(tracked)}")
    stations: dict[str, object] = {}
    for e in _try(lambda: list(tracker.MissionList), []) or []:
        m = _try(lambda e=e: e.MissionDef, None)
        for field in ("TravelStation", "TurnInStation"):
            s = _try(lambda m=m, f=field: getattr(m, f), None)
            if s is not None and not isinstance(s, str):
                stations.setdefault(_try(s._path_name, "?"), s)
    lines.append(f"== {len(stations)} station definitions the missions point to")
    # the tracked mission's first, then a few more in full; the rest one line each
    first = _try(lambda: tracked.TravelStation._path_name(), None)
    order = sorted(stations, key=lambda p: (p != first, p))
    for n, path in enumerate(order):
        s = stations[path]
        if n < FULL:
            _dump(s, "station" + (" (tracked mission's)" if path == first else ""))
        else:
            lines.append(f"   {path}  {_try(lambda s=s: str(s.StationDisplayName))!r}")
    lines.append("== travel station actors in the level")
    for cls in ("TravelStation", "WillowTravelStation", "FastTravelStation", "LevelTravelStation", "ResurrectTravelStation"):
        for a in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=True)), []):
            if a.Name.startswith("Default__"):
                continue
            lines.append(f"   {cls} {_try(a._path_name)}")
            c = a.Class
            while c is not None and c.Name not in STOP:  # its fields that could name its definition / level
                for f in _try(lambda c=c: list(c._fields()), []):
                    if f.Class.Name in SCALARS and re.search(r"def|station|level|map|name|region", str(f.Name), re.I):
                        lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f, a=a: _brief(a._get_field(f)))}")
                c = c.SuperField
    lines.append("== functions mapping a region / mission / station to a level")
    pc = get_pc()
    for obj, label in ((pc, "pc"), (wi, "world info"), (tracker, "tracker")):
        c = _try(lambda o=obj: o.Class, None)
        while c is not None and not isinstance(c, str) and c.Name != "Object":
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name == "Function" and re.search(r"level|region|station|map", str(f.Name), re.I) \
                        and re.search(r"mission|region|station|travel", str(f.Name), re.I):
                    params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                    lines.append(f"   {label} {c.Name}.{f.Name}({', '.join(params)})")
            c = c.SuperField
    lines.append(f"pc.GetLevelForMission(tracked) = {_try(lambda: _brief(pc.GetLevelForMission(tracked)))}")

    # The level's own name, as the game shows it (the page builds one from the map file name for now)
    lines.append("== the level's name")
    map_name = _try(lambda: str(wi.GetStreamingPersistentMapName()), "")
    lists = [o for o in _try(lambda: list(unrealsdk.find_all("LevelDependencyList", exact=False)), [])
             if not o.Name.startswith("Default__")]
    lines.append(f"LevelDependencyList objects: {[_brief(o) for o in lists]}")
    for o in lists[:3]:
        for arg in (map_name, map_name.removesuffix("_P").removesuffix("_p")):
            lines.append(f"   {o.Name}.GetFriendlyLevelNameFromMapName({arg!r}) = "
                         f"{_try(lambda o=o, a=arg: _brief(o.GetFriendlyLevelNameFromMapName(a)))}")
        _dump(o, "level dependency list")
    default = _try(lambda: unrealsdk.find_class("LevelDependencyList").ClassDefaultObject, None)
    if default is not None and not isinstance(default, str):
        lines.append(f"   (class default).GetFriendlyLevelNameFromMapName({map_name!r}) = "
                     f"{_try(lambda: _brief(default.GetFriendlyLevelNameFromMapName(map_name)))}")
    info = _try(lambda: wi.GetMapInfo(), None)
    if info is not None and not isinstance(info, str):
        _dump(info, "map info")
    for label, obj in (("world info", wi), ("pc", pc)):  # functions that name the level
        c = _try(lambda o=obj: o.Class, None)
        while c is not None and not isinstance(c, str) and c.Name != "Object":
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name == "Function" and re.search(r"(friendly|display|localized|pretty).*(level|map)|(level|map).*(friendly|display|name)", str(f.Name), re.I):
                    params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                    lines.append(f"   {label} {c.Name}.{f.Name}({', '.join(params)})")
            c = c.SuperField


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_area: {len(lines)} lines -> {OUT}")
