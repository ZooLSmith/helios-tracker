# Dev probe (in game), instant, read-only: why a map exit says "Map Exit" (the Pre-Sequel, 2026-10-04) where BL2's say
# "Exit to Frostburn Canyon" - collector._exit_text: the station's LevelTravelMapDisplayName ("Exit to %s") with its
# TravelDefinition.DestinationStationDefinition.DisplayName; else the map header ("Map Exit"). Stand by an exit, run it.
# For the nearest interactive object within NEAR_M whose class / definition / name says travel or exit:
# 1. that chain, link by link (each read, its value or why not);
# 2. every text property (strings, names) of the station, its definition, its TravelDefinition and the destination -
#    and of the objects the TravelDefinition points to, one level down.
# Writes tools/probes/probe_exit_text.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_exit_text.py").read())
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_exit_text.txt"  # the repo, through the mod's junction
NEAR_M = 30.0
WORDS = re.compile(r"travel|exit|transition", re.I)
TEXT = {"StrProperty", "NameProperty"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:150] if default == "<err>" else default


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _chain(cls):  # noqa: ANN001, ANN202
    out, c = [], cls
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        out.append(c)
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _texts(label: str, obj, follow: bool) -> None:  # noqa: ANN001
    if obj is None or isinstance(obj, str) or not hasattr(obj, "Class"):
        lines.append(f"== {label}: {obj!r}"[:200])
        return
    lines.append(f"== {label}: {obj.Class.Name}'{_try(obj._path_name, obj.Name)}'")
    linked = []
    for c in _chain(obj.Class):
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            kind = str(f.Class.Name)
            if kind in TEXT:
                value = str(_try(lambda f=f: obj._get_field(f), ""))
                lines.append(f"   {c.Name}.{f.Name} = {value!r}")
            elif follow and kind == "ObjectProperty" and str(f.Name) not in ("Outer", "Class", "ObjectArchetype"):
                target = _try(lambda f=f: obj._get_field(f), None)
                if target is not None and not isinstance(target, str) and hasattr(target, "Class"):
                    linked.append((f"{label}.{f.Name}", target))
    _flush()
    for sub_label, target in linked[:12]:
        _texts(sub_label, target, False)


OUT.write_text("", encoding="utf-8")
me = _try(lambda: get_pc().Pawn.Location, None)


def _dist(obj) -> float:  # noqa: ANN001
    loc = _try(lambda: obj.Location, None)
    if loc is None or isinstance(loc, str) or me is None or isinstance(me, str):
        return float("inf")
    return math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100


def _says_exit(io) -> bool:  # noqa: ANN001
    return bool(WORDS.search(f"{io.Class.Name} {io.Name} {_try(lambda: io.InteractiveObjectDefinition.Name, '')}"))


near = sorted((d, io) for io in unrealsdk.find_all("WillowInteractiveObject", exact=False)
              if not io.Name.startswith("Default__") and _says_exit(io) and (d := _dist(io)) <= NEAR_M)
if not near:
    lines.append(f"== no travel / exit object within {NEAR_M:.0f} m")
    _flush()
else:
    distance, station = near[0]
    lines.append(f"== the nearest: {station.Name} ({station.Class.Name}) at {distance:.1f} m; others: "
                 + ", ".join(f"{io.Name} ({io.Class.Name}) {d:.0f} m" for d, io in near[1:6]))
    # 1. the chain _exit_text reads
    lines.append("== the chain (collector._exit_text):")
    lines.append(f"   station.LevelTravelMapDisplayName = {_try(lambda: str(station.LevelTravelMapDisplayName))!r}")
    travel = _try(lambda: station.TravelDefinition, None)
    lines.append(f"   station.TravelDefinition = {_try(lambda: travel._path_name()) if travel is not None else None!r}")
    dest = _try(lambda: travel.DestinationStationDefinition, None) if travel is not None else None
    lines.append(f"   .DestinationStationDefinition = {_try(lambda: dest._path_name()) if dest is not None else None!r}")
    lines.append(f"   .DisplayName = {_try(lambda: str(dest.DisplayName)) if dest is not None else None!r}")
    lines.append(f"   the map header: {_try(lambda: str(station.InteractiveObjectDefinition.StatusMenuMapInfoBoxHeader))!r}")
    _flush()
    # 2. the texts around it
    _texts("station", station, False)
    _texts("definition", _try(lambda: station.InteractiveObjectDefinition, None), False)
    _texts("TravelDefinition", travel, True)
    _texts("destination", dest, False)
print(f"[probe_exit_text] -> {OUT}")
