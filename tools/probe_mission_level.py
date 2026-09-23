# Dev probe (in game), instant: a mission's effective level (the one the mission log shows) and how its
# XP scales with the player's level (outlevelled missions give less XP) - for a "do it soon" warning.
# Lists the level / game stage / XP functions on the likely classes (with their parameters), dumps the
# level-related fields of a few missions (tracked, available, done) and their regions, the globals'
# XP / level settings, and the reward the game computes now for each of those missions.
# Writes E:\Projects\python\borderlands-2\tools\probe_mission_level.txt (appends)
#   py exec(open(r"E:\Projects\python\borderlands-2\tools\probe_mission_level.py").read())
import enum
import re
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(r"E:\Projects\python\borderlands-2\tools\probe_mission_level.txt")
CLASSES = ("MissionDefinition", "MissionTracker", "WillowPlayerController", "WillowPlayerReplicationInfo",
           "WillowRegionDefinition", "WillowGameInfo", "GlobalsDefinition", "WillowGlobals", "AttributeInitializationDefinition")
FUNC_PATTERN = re.compile(r"level|gamestage|stage|exp|trivial|difficulty|scale|playthrough|awesome", re.I)
FIELD_PATTERN = re.compile(r"level|gamestage|stage|region|exp|trivial|difficulty|scale|playthrough|awesome|reward", re.I)
MISSIONS_EACH = 3  # missions of each status dumped
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
        return f"{type(value).__name__}.{value.name}"
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:10]) + (f", ... ({len(value)})" if len(value) > 10 else "") + "]"
    if isinstance(value, float):
        return f"{value:.4f}"
    return repr(value)


def _functions(class_name: str) -> None:
    cls = _try(lambda: unrealsdk.find_class(class_name), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"== {class_name}: not found")
        return
    lines.append(f"== functions: {class_name}")
    c = cls
    while c is not None and c.Name not in ("Object", "Actor"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and FUNC_PATTERN.search(str(f.Name)):
                params = [f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
        c = c.SuperField


def _fields(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"-- {label}: {_brief(obj)}")
    if obj is None or not hasattr(obj, "Class"):
        return
    c = obj.Class
    while c is not None and c.Name not in ("Object", "GBXDefinition"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and FIELD_PATTERN.search(str(f.Name)):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    lines.append("#" * 60)
    pc = get_pc()
    lines.append(f"player level {_try(lambda: pc.PlayerReplicationInfo.ExpLevel)}"
                 f" playthrough {_try(lambda: pc.GetCurrentPlaythrough())}")
    for name in CLASSES:
        _functions(name)
    tracker = next((t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")), None)
    active = _try(lambda: tracker.ActiveMission, None)
    by_status: dict[str, list] = {}
    for entry in list(_try(lambda: tracker.MissionList, []) or []):
        status = _try(lambda e=entry: e.Status.name, "?")
        mdef = _try(lambda e=entry: e.MissionDef, None)
        if mdef is not None and not isinstance(mdef, str) and len(by_status.setdefault(status, [])) < MISSIONS_EACH:
            by_status[status].append(mdef)
    picked = ([active] if active is not None and not isinstance(active, str) else []) + \
        [m for ms in by_status.values() for m in ms if m is not active]
    lines.append("== missions")
    for mdef in picked:
        _fields(mdef, f"{_try(lambda m=mdef: str(m.MissionName))!r} (status {_try(lambda m=mdef: tracker.GetMissionStatus(m))})")
        lines.append(f"   GetExperienceReward(pc) = {_try(lambda m=mdef: m.GetExperienceReward(pc, False))}")
        region = _try(lambda m=mdef: m.GameStageRegion, None)
        if region is not None and not isinstance(region, str):
            _fields(region, "   its region")
    globals_ = next((g for g in unrealsdk.find_all("GlobalsDefinition", exact=False) if not g.Name.startswith("Default__")), None)
    lines.append("== globals")
    _fields(globals_, "GlobalsDefinition")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_mission_level: {len(lines)} lines -> {OUT}")
