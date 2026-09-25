# Dev probe (in game, as a co-op CLIENT), instant: where a client learns which objective markers to show -
# it has no mission waypoint components (tools/probe_client_markers.txt) and the minimap's icons are only
# clamped screen positions (tools/probe_minimap_icons.txt). Run it with a mission tracked whose marker
# the HUD shows.
# Logs: every property of the client's MissionTracker (MissionList summarized), every property of the
# WillowWaypoint actors (the first 8 in full, then one line each: what links one to a mission /
# objective, what says it's shown), the controller's / HUD's / replication info's properties whose name
# looks waypoint / objective / mission related, and their functions of that kind.
# Writes tools/probe_client_waypoints.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_client_waypoints.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_client_waypoints.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"waypoint|objective|mission|marker|directive|compass", re.I)
STOP = {"Object"}
FULL = 8
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
    if isinstance(value, float):
        return f"{value:.1f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:6]) + (f", ... ({len(value)})" if len(value) > 6 else "") + "]"
    return repr(value)


def _all(obj, label: str, only_matching: bool = False, skip: tuple = ()) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in STOP:
        for f in _try(lambda c=c: list(c._fields()), []):
            name = str(f.Name)
            if name in skip or (only_matching and not PATTERN.search(name)):
                continue
            if f.Class.Name == "Function":
                if PATTERN.search(name):
                    params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                    lines.append(f"   {c.Name}.{name}({', '.join(params)})")
            elif f.Class.Name.endswith("Property"):
                lines.append(f"   {c.Name}.{name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    lines.append(f"map {_try(lambda: str(wi.GetStreamingPersistentMapName()))} netmode={_try(lambda: _brief(wi.NetMode))}")
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    for t in trackers[:1]:
        lines.append(f"(MissionList: {_try(lambda t=t: len(t.MissionList))} entries, not dumped)")
        _all(t, "mission tracker", skip=("MissionList",))
    points = [w for w in _try(lambda: list(unrealsdk.find_all("WillowWaypoint", exact=False)), []) if not w.Name.startswith("Default__")]
    lines.append(f"== {len(points)} WillowWaypoint actors")
    for n, w in enumerate(points):
        if n < FULL:
            _all(w, f"waypoint {n}")
        else:
            lines.append(f"   {w.Name} at={_try(lambda w=w: _brief(w.Location))} radius={_try(lambda w=w: w.AreaRadius)} hidden={_try(lambda w=w: w.bHidden)}")
    for obj, label in ((pc, "controller"), (_try(lambda: pc.MyHUD, None), "HUD"), (_try(lambda: pc.PlayerReplicationInfo, None), "player info"),
                       (_try(lambda: wi.GRI, None), "game replication info")):
        if obj is not None and not isinstance(obj, str):
            _all(obj, label, only_matching=True)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_client_waypoints: {len(lines)} lines -> {OUT}")
