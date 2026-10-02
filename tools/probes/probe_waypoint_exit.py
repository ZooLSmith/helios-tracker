# Dev probe (in game), instant, read-only: a mission waypoint with no objective of its own (the page draws it, unnamed -
# the user: one sitting on a teleporter to another map). For each active waypoint of the MissionTracker's
# MissionWaypoints: its component's class, its mission, its WaypointInfo (every field), whether it links an objective;
# then, for those without one, the actor it's on - its class, its name, and every property whose name has
# Travel / Dest / Station / Level / Map / Name / Objective / Mission / Target (arrays and structs shown).
# Properties only, no calls. Writes tools/probes/probe_waypoint_exit.txt (appends), after each waypoint.
#   py exec(open(r"<repo>\tools\probes\probe_waypoint_exit.py").read())
import re
import sys
import time
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_waypoint_exit.txt"
WORDS = re.compile(r"travel|dest|station|level|map|name|objective|mission|target", re.I)
lines: list[str] = []


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _show(v, depth: int = 0) -> str:  # noqa: ANN001
    if hasattr(v, "name") and not hasattr(v, "_path_name"):
        return str(v.name)
    if hasattr(v, "_path_name"):
        return f"{_try(lambda: v.Class.Name)} {_try(lambda: v._path_name())}"
    if hasattr(v, "_type") and depth < 2:
        return "{" + ", ".join(f"{f.Name}={_show(_try(lambda f=f: v._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(v._type._fields()), []) or []
                               if str(f.Class.Name).endswith("Property")) + "}"
    if hasattr(v, "__len__") and not isinstance(v, str):
        return "[" + ", ".join(_show(x, depth + 1) for x in list(v)[:6]) + "]"
    return repr(v)


def main() -> None:
    lines.append("#" * 70)
    lines.append(f"run at {time.strftime('%H:%M:%S')}")
    _flush()
    tracker = next((t for t in _try(lambda: list(unrealsdk.find_all("MissionTracker", exact=False)), []) or []
                    if not str(t.Name).startswith("Default__")), None)
    if tracker is None:
        lines.append("no MissionTracker")
        _flush()
        return
    for entry in _try(lambda: list(tracker.MissionWaypoints), []) or []:
        mission = _try(lambda e=entry: e.Mission, None)
        for comp in _try(lambda e=entry: list(e.Waypoints), []) or []:
            if comp is None or not _try(lambda c=comp: bool(c.bActive), False):
                continue
            info = _try(lambda c=comp: c.WaypointInfo, None)
            linked = _try(lambda i=info: i.LinkedObjective, None) if info is not None else None
            owner = _try(lambda c=comp: c.Owner, None)
            lines.append(f"== {comp.Class.Name} {_try(lambda: comp._path_name())} mission {_show(mission)}")
            lines.append(f"   LinkedObjective {_show(linked)}")
            lines.append(f"   WaypointInfo {_show(info)[:800]}")
            if linked is None and owner is not None:
                loc = _try(lambda o=owner: o.Location, None)
                lines.append(f"   owner {_show(owner)} at {_show(loc)}")
                for f in _try(lambda o=owner: list(o.Class._fields()), []) or []:
                    if str(f.Class.Name).endswith("Property") and WORDS.search(str(f.Name)) and not str(f.Name).startswith("VfTable"):
                        lines.append(f"   owner.{f.Name} [{f.Class.Name}] = {_show(_try(lambda f=f, o=owner: o._get_field(f)))[:300]}")
            _flush()
    lines.append("done")
    _flush()


main()
print(f"probe_waypoint_exit: written to {OUT}")
