# Dev probe (in game, as a co-op CLIENT), instant: why the quest markers don't show on a client - the
# collector reads the first MissionTracker's MissionWaypoints (bActive components). Run it with a
# mission tracked whose marker the game's own HUD / map shows.
# Logs: every MissionTracker (its owner / outer, net role, ActiveMission, MissionList size, its
# MissionWaypoints: per mission, each component's class, bActive, owner, location, linked objective);
# every waypoint component in memory (MissionObjective / MissionDirective WaypointComponent) with the
# same, and whether a tracker lists it; the WillowWaypoint actors; the HUD minimap's icon lists.
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_client_markers.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_client_markers.py").read())
import enum
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_client_markers.txt")
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
    if isinstance(value, float):
        return f"{value:.0f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "X") and hasattr(value, "Y") and hasattr(value, "Z"):
        return f"({value.X:.0f}, {value.Y:.0f}, {value.Z:.0f})"
    return repr(value)


def _comp(c) -> str:  # noqa: ANN001
    return (f"{c.Class.Name} {c.Name} active={_try(lambda: c.bActive)} owner={_try(lambda: _brief(c.Owner))}"
            f" at={_try(lambda: _brief(c.Owner.Location))} radius={_try(lambda: c.Owner.AreaRadius, '-')}"
            f" objective={_try(lambda: _brief(c.WaypointInfo.LinkedObjective), '-')} mission={_try(lambda: _brief(c.LinkedMission), '-')}")


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    lines.append(f"map {_try(lambda: str(wi.GetStreamingPersistentMapName()))} netmode={_try(lambda: _brief(wi.NetMode))}"
                 f" role={_try(lambda: _brief(pc.Role))}")
    listed = set()
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    lines.append(f"== {len(trackers)} MissionTracker(s)")
    for t in trackers:
        lines.append(f"-- {_brief(t)} outer={_try(lambda t=t: _brief(t.Outer))} owner={_try(lambda t=t: _brief(t.Owner))}"
                     f" role={_try(lambda t=t: _brief(t.Role))} remote={_try(lambda t=t: _brief(t.RemoteRole))}"
                     f" hidden={_try(lambda t=t: t.bHidden)} deleteMe={_try(lambda t=t: t.bDeleteMe)}")
        lines.append(f"   ActiveMission={_try(lambda t=t: _brief(t.ActiveMission))} MissionList={_try(lambda t=t: len(t.MissionList))}")
        entries = _try(lambda t=t: list(t.MissionWaypoints), [])
        lines.append(f"   MissionWaypoints: {len(entries) if isinstance(entries, list) else entries}")
        for e in entries if isinstance(entries, list) else []:
            comps = _try(lambda e=e: list(e.Waypoints), [])
            lines.append(f"   * {_try(lambda e=e: _brief(e.Mission))}: {len(comps)} waypoint(s)")
            for c in comps if isinstance(comps, list) else []:
                if c is not None:
                    listed.add(_try(c._get_address, 0))
                    lines.append(f"       {_comp(c)}")
    for cls in ("MissionObjectiveWaypointComponent", "MissionDirectiveWaypointComponent"):
        comps = [c for c in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) if not c.Name.startswith("Default__")]
        active = [c for c in comps if _try(lambda c=c: bool(c.bActive), False)]
        lines.append(f"== {cls}: {len(comps)} in memory, {len(active)} active")
        for c in active[:40]:
            lines.append(f"   {'(listed) ' if _try(c._get_address, 0) in listed else '(NOT listed) '}{_comp(c)}")
    points = [w for w in _try(lambda: list(unrealsdk.find_all("WillowWaypoint", exact=False)), []) if not w.Name.startswith("Default__")]
    lines.append(f"== {len(points)} WillowWaypoint actors (first 20)")
    for w in points[:20]:
        lines.append(f"   {w.Name} at={_try(lambda w=w: _brief(w.Location))} radius={_try(lambda w=w: w.AreaRadius)}"
                     f" hidden={_try(lambda w=w: w.bHidden)}")
    for mm in [m for m in _try(lambda: list(unrealsdk.find_all("HUDWidget_Minimap", exact=False)), []) if not m.Name.startswith("Default__")][:2]:
        lines.append(f"== minimap {mm.Name}")
        for f in ("Icons_Objective", "Icons_AreaObjective", "Icons_AreaObjectiveSticky", "Icons_MissionEligible", "Icons_MissionRedeemable"):
            lines.append(f"   {f}: {_try(lambda m=mm, f=f: len(getattr(m, f)))}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_client_markers: {len(lines)} lines -> {OUT}")
