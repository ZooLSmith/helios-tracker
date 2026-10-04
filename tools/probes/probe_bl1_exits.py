# Dev probe (in game), instant, read-only: Borderlands 1's exits and missions in another area (.agent/bl1.md) - the game
# marks a mission whose target waypoint is in another area on the exit leading there (a gd_MapChangeObjects
# .Default_MapChanger object, the user); the page marks none (it only has the loaded area's waypoint actors).
# 1. the tracked / active missions: their target and turn-in waypoint definitions, the level each names
#    (PersistentLevelName, SubLevelName), the current area;
# 2. every map change object (its definition's path holds "MapChange"): its class, definition, location, and its fields -
#    where it leads (a destination map / travel definition / station...), what it's linked to.
# Properties only. Writes tools/probes/probe_bl1_exits.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_exits.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_exits.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_exits.txt"
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
        return f"<{type(ex).__name__}: {ex}>"[:160] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.1f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 2:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:6]) + "]"
    if hasattr(value, "_type"):
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


SKIP = ("VfTable", "Components", "AllComponents", "Timers", "Touching", "Children", "Attached", "Net", "Collision", "Draw",
        "Rotation", "Physics", "Role", "Remote", "Tick", "Detach", "PrePivot", "Custom", "Replicated", "Last", "Latent",
        "Velocity", "Acceleration", "AngularVelocity", "Relative", "Desired", "Overlap", "Supported", "Generated")


def _fields(obj, limit: int = 3000) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        name = str(f.Name)
        if f.Class.Name.endswith("Property") and not name.startswith(SKIP) and not (name.startswith("b") and name[1:2].isupper()):
            value = _brief(_try(lambda f=f: obj._get_field(f)))
            if value not in ("None", "0", "0.0", "''", "[0: ]", "False"):
                out.append(f"{name}={value[:250]}")
    return ", ".join(out)[:limit]


mods_base = __import__("mods_base")
games = sys.modules.get("helios_tracker.games")
wi = _try(lambda: mods_base.ENGINE.GetCurrentWorldInfo(), None)
lines.append(f"current area: {_try(lambda: games.GAME.world.map_name(wi)) if games is not None else '-'}")

# 1. the missions
pc = _try(lambda: mods_base.get_pc(), None)
playthrough = _try(lambda: int(wi.GRI.HostCurrentPlaythrough), 0)
entries = _try(lambda: list(pc.MissionPlaythroughData[playthrough].MissionList), [])
lines.append("== missions picked up")
for entry in entries if isinstance(entries, list) else []:
    status = _brief(_try(lambda e=entry: e.Status))
    if status not in ("MS_Active", "MS_ReadyToTurnIn"):
        continue
    mission = _try(lambda e=entry: e.MissionDef, None)
    lines.append(f"-- {_brief(mission)} {_try(lambda m=mission: str(m.MissionName))!r}: {status}")
    for role in ("TargetWaypointDefinition", "TurnInWaypointDefinition"):
        wp = _try(lambda r=role, m=mission: getattr(m, r), None)
        if wp is not None and not isinstance(wp, str):
            lines.append(f"   {role} {wp._path_name()}: PersistentLevelName {_brief(_try(lambda w=wp: w.PersistentLevelName))}, "
                         f"SubLevelName {_brief(_try(lambda w=wp: w.SubLevelName))}")
_flush()

# 2. the map change objects
changers = [io for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []
            if "mapchange" in _try(lambda io=io: io.InteractiveObjectDefinition._path_name(), "").lower()]
lines.append(f"== map change objects: {len(changers)}")
for io in changers:
    lines.append(f"-- {io._path_name()} ({io.Class.Name}) definition {_brief(_try(lambda io=io: io.InteractiveObjectDefinition))} "
                 f"at {_brief(_try(lambda io=io: io.Location))}")
    lines.append(f"   {_fields(io)}")
    definition = _try(lambda io=io: io.InteractiveObjectDefinition, None)
    if definition is not None and not isinstance(definition, str):
        lines.append(f"   definition's: {_fields(definition, 1500)}")
    _flush()
# other objects that may lead somewhere (their class names)
others = {}
for cls in ("WillowMapChangeObject", "LevelTravelStation", "TravelStation", "WillowTeleporter", "MapChangeObject"):
    found = [o for o in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or [] if not str(o.Name).startswith("Default__")]
    others[cls] = len(found)
lines.append(f"other classes: {others}")
lines.append("== done")
_flush()
print(f"probe_bl1_exits: written to {OUT}")
