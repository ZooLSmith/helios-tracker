# Dev probe (in game, the Pre-Sequel), instant: where TPS keeps the fast travel stations a player unlocked. BL2's
# controller has ActivatedTeleportersList (probe_fast_travel.txt); TPS's doesn't (the log: "WillowPlayerController has
# no attribute 'ActivatedTeleportersList'"), nor its replication info / pawn (probe_fast_travel_tps.txt). The fast travel
# menu's movie lists station names (LocationStationStrings) - from where?
# Logs:
#  - the loaded save game objects (classes named like *SaveGame, not the defaults): their fields about travel / stations;
#  - the controller's class chain: its FUNCTIONS named about teleporters / travel / stations, with their parameters
#    (signatures only - none called);
#  - the fast travel menu's movie if loaded: its fields in full.
# Reads properties and lists signatures only (no function called). The output is written after each section.
# Run it in TPS on a map with a few stations unlocked (the menu not needed).
# Writes tools/probes/probe_tps_stations.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_tps_stations.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_tps_stations.txt"
PATTERN = r"teleport|travel|station|visited"
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
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return "[" + ", ".join(_brief(v, depth + 1) for v in items[:80]) + (f", ... ({len(items)})" if len(items) > 80 else "") + "]"
    return repr(value)


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fields(obj, label: str, pattern: str | None) -> None:  # noqa: ANN001
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (pattern is None or re.search(pattern, str(f.Name), re.I)):
                lines.append(f"   {label} {c.Name}.{f.Name} ({f.Class.Name}) = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    lines.append("== save game objects")
    classes = sorted({str(o.Class.Name) for o in _try(lambda: list(unrealsdk.find_all("Object", exact=False)), [])
                      if "savegame" in str(o.Class.Name).lower()})
    lines.append(f"   classes: {classes}")
    for cls in classes:
        for o in _try(lambda cls=cls: list(unrealsdk.find_all(cls, exact=True)), []):
            if o.Name.startswith("Default__"):
                continue
            lines.append(f"  {_try(o._path_name)}")
            _fields(o, "   ", PATTERN)
    _flush()
    lines.append("== the controller's functions (signatures only)")
    pc = get_pc()
    c = _try(lambda: pc.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and re.search(PATTERN, str(f.Name), re.I):
                params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
        c = c.SuperField
    _flush()
    lines.append("== the fast travel menu's movie (if loaded)")
    for o in _try(lambda: list(unrealsdk.find_all("FastTravelStationGFxMovie", exact=False)), []):
        if not o.Name.startswith("Default__"):
            lines.append(f"  {_try(o._path_name)}")
            c = o.Class
            for f in _try(lambda c=c: list(c._fields()), []):  # (its own class's fields only)
                if f.Class.Name.endswith("Property"):
                    lines.append(f"   {f.Name} ({f.Class.Name}) = {_try(lambda f=f: _brief(o._get_field(f)))}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"[helios probe] probe_tps_stations: done - {OUT}")
