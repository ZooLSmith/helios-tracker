# Dev probe (in game), instant: where quest markers (points and area circles) live - the mission
# tracker's waypoints, the waypoint actors / components in the level, and what the HUD minimap is
# drawing as objective icons. Run it with a mission tracked that shows BOTH a normal marker and an
# area ("somewhere in this circle") marker if you can; run it again for another mission.
# Writes E:\Projects\python\borderlands-2\tools\probe_missions.txt (appends)
#   py exec(open(r"E:\Projects\python\borderlands-2\tools\probe_missions.py").read())
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\borderlands-2\tools\probe_missions.txt")
MAX_EACH = 40
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    """Compact struct / object / array rendering (objects by path, structs field by field)."""
    if value is None:
        return "None"
    if isinstance(value, (str, bytes, int, float, bool)):
        return f"{value:.1f}" if isinstance(value, float) else repr(value)
    if depth > 3:  # every branch, not just structs: self-similar iterables recursed forever
        return f"<{type(value).__name__}>"
    if hasattr(value, "_type"):  # WrappedStruct
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if type(value).__name__ == "WrappedArray":
        items = [_brief(v, depth + 1) for v in list(value)[:8]]
        return "[" + ", ".join(items) + (f", ... ({len(value)} total)" if len(value) > 8 else "") + "]"
    return f"<{type(value).__name__}: {str(value)[:80]}>"


def _fields(obj, indent: str, match=None) -> None:  # noqa: ANN001
    """Simple properties of an object (bools, numbers, names, strings, object refs, small structs)."""
    c, seen = obj.Class, set()
    while c is not None and c.Name not in ("Actor", "ActorComponent", "Object", "Component"):
        for f in c._fields():
            kind = f.Class.Name
            if f.Name in seen or not kind.endswith("Property") or kind in ("DelegateProperty",):
                continue
            if match and not match(f.Name):
                continue
            seen.add(f.Name)
            lines.append(f"{indent}{c.Name}.{f.Name} = {_brief(_try(lambda f=f: obj._get_field(f)))[:300]}")
        c = c.SuperField


def _loc(actor) -> str:  # noqa: ANN001
    return _try(lambda: f"({actor.Location.X:.0f}, {actor.Location.Y:.0f}, {actor.Location.Z:.0f})")


wi = ENGINE.GetCurrentWorldInfo()
pc = get_pc()
lines.append("#" * 70)
lines.append(f"map {wi.GetStreamingPersistentMapName()}, player at {_loc(pc.Pawn)}")

lines.append("== MissionTracker")
for mt in unrealsdk.find_all("MissionTracker", exact=False):
    if mt.Name.startswith("Default__"):
        continue
    lines.append(f"  {mt._path_name()}")
    active = _try(lambda m=mt: m.ActiveMission, None)
    lines.append(f"  ActiveMission = {_brief(active)}  MissionName = {_try(lambda: active.MissionName)!r}")
    for entry in _try(lambda m=mt: list(m.MissionWaypoints), []):
        mission = _try(lambda e=entry: e.Mission, None)
        lines.append(f"  -- MissionWaypoints: {_brief(mission)} '{_try(lambda: mission.MissionName)}'")
        for wp in _try(lambda e=entry: list(e.Waypoints), [])[:MAX_EACH]:
            lines.append(f"     {_brief(wp)} at {_loc(wp) if hasattr(wp, 'Location') else '-'}")
            if hasattr(wp, "Class"):
                _fields(wp, "        ", lambda n: any(k in n.lower() for k in ("radius", "enabled", "active", "info", "objective", "mission", "owner", "base")))
    lines.append(f"  LevelTransitions = {_brief(_try(lambda m=mt: m.LevelTransitions))[:500]}")
    lines.append(f"  IconHelper_Directors = {_brief(_try(lambda m=mt: m.IconHelper_Directors))[:500]}")

lines.append("== WillowWaypoint actors")
for wp in list(unrealsdk.find_all("WillowWaypoint", exact=False))[:MAX_EACH]:
    if wp.Name.startswith("Default__"):
        continue
    lines.append(f"  {wp.Class.Name} {_try(wp._path_name)} at {_loc(wp)}")
    _fields(wp, "     ")
    for comp in _try(lambda w=wp: list(w.Components), []):
        if comp is not None and "Waypoint" in comp.Class.Name:
            lines.append(f"     component {comp.Class.Name} {comp.Name}")
            _fields(comp, "        ")

lines.append("== WaypointComponents anywhere (the owner actor is what the marker follows)")
for comp in list(unrealsdk.find_all("WaypointComponent", exact=False))[:MAX_EACH]:
    if comp.Name.startswith("Default__") or "Default__" in _try(comp._path_name, ""):
        continue
    owner = _try(lambda c=comp: c.Owner, None)
    lines.append(f"  {comp.Class.Name} {_try(comp._path_name)} owner={_brief(owner)} at {_loc(owner) if owner is not None else '-'}")
    _fields(comp, "     ")

lines.append("== HUD minimap objective icons (what the game draws right now)")
for w in unrealsdk.find_all("HUDWidget_Minimap", exact=False):
    if w.Name.startswith("Default__"):
        continue
    for arr in ("Icons_Objective", "Icons_AreaObjective", "Icons_AreaObjectiveSticky", "Icons_CustomObjective",
                "Icons_MissionEligible", "Icons_MissionRedeemable", "Icons_LevelTravelStations"):
        icons = _try(lambda a=arr: list(getattr(w, a)), [])
        used = [ic for ic in icons if _try(lambda i=ic: i.Object, None) is not None]
        lines.append(f"  {arr}: {len(icons)} slots, {len(used)} with an object")
        for ic in used[:MAX_EACH]:
            obj = ic.Object
            lines.append(f"     {_brief(obj)} at {_loc(obj)} MapPos={_brief(_try(lambda i=ic: i.MapPos))} visible={_try(lambda i=ic: i.bVisible)}")
            lines.append(f"        all: {_brief(ic)[:400]}")
            if "Waypoint" in obj.Class.Name:
                _fields(obj, "        ", lambda n: any(k in n.lower() for k in ("radius", "enabled", "active")))

lines.append("== HUD mission objectives list (the checklist under the tracked mission)")
for w in unrealsdk.find_all("HUDWidget_Missions", exact=False):
    if w.Name.startswith("Default__"):
        continue
    lines.append(f"  {w._path_name()}")
    _fields(w, "     ", lambda n: any(k in n.lower() for k in ("objective", "mission", "count", "tracked", "active")))

with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"[probe_missions] {len(lines)} lines -> {OUT}")
