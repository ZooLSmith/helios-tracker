# Dev probe (in game), instant, read-only: Borderlands 1's objective markers - the page marks every WillowWaypoint of a
# mission's waypoint definition (games/bl1/missions.py markers), the game one ("Digistruct Module:" twice - the user).
# WillowWaypoint (WillowGame.u, offline): bCompleted, WaypointNumber, TouchDistance, WaypointDefinition - a numbered
# path? For each mission picked up: its target / turn-in waypoint definitions; the level's WillowWaypoints of each -
# their number, bCompleted, TouchDistance, location, distance, bHidden, Tag. Writes probe_bl1_waypoints.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_waypoints.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_waypoints.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_waypoints.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _enum(value) -> str:  # noqa: ANN001
    return f"{value.name} ({int(value)})" if isinstance(value, Enum) else repr(value)


import math  # noqa: E402

import unrealsdk  # noqa: E402

mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
me = _try(lambda: pc.Pawn.Location, None)
wi = _try(lambda: mods_base.ENGINE.GetCurrentWorldInfo(), None)
playthrough = _try(lambda: int(wi.GRI.HostCurrentPlaythrough), 0)
log = _try(lambda: list(pc.MissionPlaythroughData[playthrough].MissionList), []) or []
waypoints = [w for w in _try(lambda: list(unrealsdk.find_all("WillowWaypoint", exact=False)), []) or []
             if "Default__" not in str(_try(lambda w=w: w.Name, ""))]
lines.append(f"== {len(log)} missions, {len(waypoints)} waypoints in the level")
_flush()
for entry in log:
    mission = _try(lambda e=entry: e.MissionDef, None)
    status = _enum(_try(lambda e=entry: e.Status))
    lines.append(f"-- {_try(lambda: str(mission.MissionName))!r} {status}, progress "
                 f"{[_try(lambda o=o: o.CurrentAmount) for o in (_try(lambda e=entry: list(e.Objectives), []) or [])]}")
    for which in ("TargetWaypointDefinition", "TurnInWaypointDefinition"):
        definition = _try(lambda w=which: getattr(mission, w), None)
        if definition is None or isinstance(definition, str):
            continue
        mine = [w for w in waypoints if _try(lambda w=w: w.WaypointDefinition, None) == definition]
        lines.append(f"   {which} {_try(lambda: definition._path_name())}: {len(mine)} waypoints")
        for w in sorted(mine, key=lambda w: _try(lambda w=w: int(w.WaypointNumber), 0)):
            loc = w.Location
            dist = math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100 if me is not None else -1
            lines.append(f"     #{_try(lambda: w.WaypointNumber)} bCompleted={_try(lambda: w.bCompleted)} "
                         f"TouchDistance={_try(lambda: w.TouchDistance)} at ({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f}) {dist:.1f} m "
                         f"bHidden={_try(lambda: w.bHidden)} Tag={_try(lambda: w.Tag)} {_try(lambda: w.Name)}")
    _flush()
