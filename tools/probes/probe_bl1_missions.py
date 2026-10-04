# Dev probe (in game), instant, read-only: Borderlands 1's missions, for its mission reader (.agent/bl1.md "Missions").
# BL1 isn't BL2: no MissionWaypoints on the tracker; the player's missions in WillowPlayerController.MissionPlaythroughData
# = MissionPlaythroughInfo {PlayThroughNumber, ActiveMission, MissionList} (WillowGame.u, offline); a mission's objectives
# MissionDefinition.Objectives[] {StatId, ObjectiveCount, ProgressMessage}; its markers the level's WillowWaypoint actors
# of its TargetWaypointDefinition / TurnInWaypointDefinition (WaypointNumber...).
# 1. the player's mission data: every playthrough's active mission and missions (status, objectives' progress);
# 2. the active mission's definition: objectives, waypoint definitions (their level names), giver, chain;
# 3. every WillowWaypoint of the active mission's definitions: number, location, hidden / collision, its fields;
#    and how many waypoints each other definition has;
# 4. the HUD's tracked objective, the controller's waypoint flags.
# Run it mid-mission (part done: an objective 1 of 4...), then again after the next step (another item picked up, the
# mission ready to turn in) - what changes shows which waypoint the game marks. Properties only. Writes
# tools/probes/probe_bl1_missions.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_missions.py").read())
from enum import Enum
import math
import sys
import time
from collections import Counter
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_missions.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_missions.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70, f"run at {time.strftime('%H:%M:%S')}"]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.1f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:12]) + "]"
    if hasattr(value, "_type"):
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
me = _try(lambda: pc.Pawn, None)
here = _try(lambda: me.Location, None)
lines.append(f"player at {_brief(here)}")

# 1. the player's mission data
lines.append("== MissionPlaythroughData")
playthroughs = _try(lambda: list(pc.MissionPlaythroughData), [])
active = None
for pt in playthroughs if isinstance(playthroughs, list) else [playthroughs]:
    if isinstance(pt, str):
        lines.append(pt)
        continue
    lines.append(f"-- playthrough {_brief(_try(lambda p=pt: p.PlayThroughNumber))}: ActiveMission {_brief(_try(lambda p=pt: p.ActiveMission))}")
    active = active or _try(lambda p=pt: p.ActiveMission, None)
    missions = _try(lambda p=pt: list(p.MissionList), [])
    lines.append(f"   MissionList: {len(missions) if isinstance(missions, list) else missions}")
    for entry in missions if isinstance(missions, list) else []:
        lines.append(f"     {_brief(entry)[:600]}")
    lines.append(f"   UnloadableDlcMissionList: {_brief(_try(lambda p=pt: p.UnloadableDlcMissionList))[:300]}")
    _flush()
lines.append(f"controller: ServerPlotMission {_brief(_try(lambda: pc.ServerPlotMission))}, ServerObjectiveBitfield "
             f"{_brief(_try(lambda: pc.ServerObjectiveBitfield))}, bInsideWaypoint {_brief(_try(lambda: pc.bInsideWaypoint))}, "
             f"bNeedsUpdateWaypoints {_brief(_try(lambda: pc.bNeedsUpdateWaypoints))}, bWaypointsPulsing "
             f"{_brief(_try(lambda: pc.bWaypointsPulsing))}")
_flush()

# 2. the active mission's definition
mission = active if active is not None and not isinstance(active, str) else None
if mission is None:
    tracker = next((t for t in _try(lambda: list(unrealsdk.find_all("MissionTracker")), []) if not str(t.Name).startswith("Default__")), None)
    mission = _try(lambda: tracker.ActiveMission, None) if tracker is not None else None
lines.append(f"== active mission {_brief(mission)}")
targets = {}
if mission is not None and not isinstance(mission, str):
    for name in ("MissionName", "MissionGiver", "MissionSummary", "Objectives", "TargetWaypointDefinition", "TurnInWaypointDefinition",
                 "bDoNotResolveWaypoint", "PlotMissionNumber", "NextMissionInChain", "Dependencies", "ExpLevel", "GameStageRegion"):
        lines.append(f"   {name}: {_brief(_try(lambda n=name: getattr(mission, n)))[:500]}")
    for role in ("TargetWaypointDefinition", "TurnInWaypointDefinition"):
        wp_def = _try(lambda r=role: getattr(mission, r), None)
        if wp_def is not None and not isinstance(wp_def, str):
            targets[wp_def._path_name()] = role
            lines.append(f"   {role} {wp_def._path_name()}: PersistentLevelName {_brief(_try(lambda d=wp_def: d.PersistentLevelName))}, "
                         f"SubLevelName {_brief(_try(lambda d=wp_def: d.SubLevelName))}")
_flush()

# 3. the waypoints
lines.append("== waypoints")
waypoints = [w for w in _try(lambda: list(unrealsdk.find_all("WillowWaypoint", exact=False)), []) or []
             if not str(w.Name).startswith("Default__")]
per_def = Counter(_try(lambda w=w: w.WaypointDefinition._path_name(), "None") for w in waypoints)
lines.append(f"{len(waypoints)} live, by definition: {dict(per_def)}")
skip = ("VfTable", "Components", "AllComponents", "Timers", "Touching", "Children", "Attached", "SupportedEvents",
        "GeneratedEvents", "LatentActions")
for w in waypoints:
    definition = _try(lambda w=w: w.WaypointDefinition._path_name(), "None")
    if definition not in targets:
        continue
    loc = _try(lambda w=w: w.Location, None)
    dist = math.dist((here.X, here.Y), (loc.X, loc.Y)) if loc is not None and here is not None and not isinstance(here, str) else -1
    fields = []
    for f in _try(lambda w=w: list(w.Class._fields()), []) or []:
        if f.Class.Name in ("BoolProperty", "IntProperty", "FloatProperty", "ByteProperty", "NameProperty", "ObjectProperty", "StrProperty"):
            value = _brief(_try(lambda f=f, w=w: w._get_field(f)))
            if not str(f.Name).startswith(skip) and value not in ("False", "0", "0.0", "None", "''"):
                fields.append(f"{f.Name}={value[:120]}")
    lines.append(f"-- {targets[definition]} {w._path_name()}: number {_brief(_try(lambda w=w: w.WaypointNumber))}, at {_brief(loc)} "
                 f"({dist:.0f} uu), hidden {_brief(_try(lambda w=w: w.bHidden))}")
    lines.append(f"   {', '.join(fields)[:2500]}")
_flush()

# 4. the HUD
hud = _try(lambda: pc.myHUD, None)
lines.append(f"== HUD {_brief(hud)}")
for name in ("HUDMovie", "TrackedObjectiveCount", "CurrentWaypoint", "WaypointTarget"):
    lines.append(f"   {name}: {_brief(_try(lambda n=name: getattr(hud, n)))[:400]}")
movie = _try(lambda: hud.HUDMovie, None)
if movie is not None and not isinstance(movie, str):
    for f in _try(lambda: list(movie.Class._fields()), []) or []:
        if any(k in str(f.Name).lower() for k in ("objective", "mission", "waypoint", "compass", "tracked")):
            lines.append(f"   movie.{f.Name}: {_brief(_try(lambda f=f: movie._get_field(f)))[:300]}")
lines.append("== done")
_flush()
print(f"probe_bl1_missions: written to {OUT}")
