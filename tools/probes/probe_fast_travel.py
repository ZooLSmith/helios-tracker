# Dev probe (in game), instant: which maps the fast travel network reaches - to tell how to get to a map without a
# station (Fink's Slaughterhouse: its own map, BanditSlaughter_P, reached only from Fridge_P - probe_station_maps.txt):
# the nearest map with one, through the level lists' ConnectedPersistents. Properties only (no blind calls).
# Logs: every FastTravelStationDefinition loaded (are they all, whatever the map? its map, name, sign, DLC,
# bInitiallyActive, bSendOnly); the level lists' maps without one; the player controller's / its replication info's
# fields that could hold the stations unlocked (travel / station / teleport); the fast travel menu's objects if any.
# Writes tools/probes/probe_fast_travel.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_fast_travel.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

import mods_base  # noqa: E402
_GAME = mods_base.Game.get_current().name  # (another game than BL2: its own file - probe_fast_travel_tps.txt)
OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / (
    "probe_fast_travel.txt" if _GAME == "BL2" else f"probe_fast_travel_{_GAME.lower()}.txt")
SCALARS = {"StrProperty", "NameProperty", "ObjectProperty", "ByteProperty", "IntProperty", "BoolProperty", "ArrayProperty",
           "StructProperty"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        if depth > 1:
            return "{...}"
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name in SCALARS) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return "[" + ", ".join(_brief(v, depth + 1) for v in items[:60]) + (f", ... ({len(items)})" if len(items) > 60 else "") + "]"
    return repr(value)


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fields(obj, label: str, pattern: str) -> None:  # noqa: ANN001
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name in SCALARS and re.search(pattern, str(f.Name), re.I):
                lines.append(f"   {label} {c.Name}.{f.Name} ({f.Class.Name}) = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    lines.append(f"map: {_try(lambda: str(wi.GetStreamingPersistentMapName()))}")
    stations = [s for s in _try(lambda: list(unrealsdk.find_all("FastTravelStationDefinition", exact=True)), [])
                if not s.Name.startswith("Default__")]
    lines.append(f"== {len(stations)} FastTravelStationDefinition loaded")
    with_station: set[str] = set()
    for s in sorted(stations, key=lambda s: _try(s._path_name, "")):
        level = str(_try(lambda s=s: s.StationLevelName, ""))
        with_station.add(level.lower())
        lines.append(f"   {_try(s._path_name)}: {_try(lambda s=s: str(s.StationDisplayName))!r} in {level!r}, "
                     f"sign {_try(lambda s=s: str(s.StationSign))!r}, dlc {_brief(_try(lambda s=s: s.DlcExpansion, None))}, "
                     f"initially active {_try(lambda s=s: bool(s.bInitiallyActive))}, send only {_try(lambda s=s: bool(s.bSendOnly))}")
    _flush()
    lines.append("== level list maps without a fast travel station")
    for lst in [o for o in _try(lambda: list(unrealsdk.find_all("LevelDependencyList", exact=False)), [])
                if not o.Name.startswith("Default__")]:
        for e in _try(lambda lst=lst: list(lst.LevelList), []) or []:
            level = str(_try(lambda e=e: e.PersistentMap, ""))
            if level.lower() not in with_station:
                lines.append(f"   {lst.Name}: {level} {_try(lambda e=e: str(e.LevelName))!r} -> "
                             f"{[str(c) for c in _try(lambda e=e: list(e.ConnectedPersistents), []) or []]}")
    _flush()
    lines.append("== the stations unlocked: the player's fields")
    pattern = r"travel|station|teleport|visited|discover"
    pc = get_pc()
    _fields(pc, "pc", pattern)
    _fields(_try(lambda: pc.PlayerReplicationInfo, None), "pri", pattern)
    _fields(_try(lambda: pc.Pawn, None), "pawn", pattern)
    _flush()
    lines.append("== other objects naming fast travel (classes)")
    for cls in ("FastTravelStation", "FastTravelStationGFxMovie", "FastTravelStationGFxObject", "TravelStationDefinitionList",
                "FastTravelStationsListOrder"):
        found = [o for o in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) if not o.Name.startswith("Default__")]
        lines.append(f"   {cls}: {len(found)} {[_try(o._path_name) for o in found[:10]]}")
        for o in found[:2]:
            _fields(o, f"  {o.Name}", pattern + r"|list|order|level")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"probe_fast_travel: {len(lines)} lines -> {OUT}")
