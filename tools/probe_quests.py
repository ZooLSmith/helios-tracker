# Dev probe (in game), instant: the mission list, statuses, objectives and progress, and how
# missions depend on each other - for a quest panel (all objectives of the tracked mission with
# their status / counts) and a mission tree (available / done). Run it mid-playthrough with a
# mission tracked, ideally one with several objectives, some done.
# Writes tools/probe_quests.txt (appends)
#   py exec(open(r"<repo>\tools\probe_quests.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_quests.txt"  # the repo, through the mod's junction
SCALARS = ("StrProperty", "NameProperty", "ObjectProperty", "ClassProperty", "ByteProperty", "IntProperty",
           "FloatProperty", "BoolProperty", "EnumProperty", "StructProperty", "ArrayProperty")
STOP = {"Object", "Actor", "Info", "ReplicationInfo", "GBXDefinition"}  # engine bases: not dumped
FULL_ENTRIES = 3  # MissionList entries dumped field by field (the others: one line each)
FULL_DEFS = 3  # MissionDefinitions dumped field by field (the tracked one first)

lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0, struct_depth: int = 1) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):  # before the array case: an IntFlag iterates to itself
        return f"{type(value).__name__}.{value.name}({int(value) if isinstance(value, int) else value.value})"
    if depth > 4:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):  # WrappedStruct
        if depth > struct_depth:
            return "{...}"
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1, struct_depth))}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):  # UObject
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):  # WrappedArray
        items = [_brief(v, depth + 1, struct_depth) for v in list(value)[:8]]
        more = f", ... ({len(value)} total)" if len(value) > 8 else ""
        return "[" + ", ".join(items) + more + "]"
    if isinstance(value, float):
        return f"{value:.3f}"
    return repr(value)


def _fields(obj, label: str, struct_depth: int = 1) -> None:  # noqa: ANN001
    """Every property of obj's own classes (down to the engine bases), one line each."""
    lines.append(f"   -- {label}: {_brief(obj)}")
    if obj is None or not hasattr(obj, "Class"):
        return
    c = obj.Class
    while c is not None and c.Name not in STOP:
        for f in c._fields():
            if f.Class.Name in SCALARS:
                lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f), 0, struct_depth))}")
        c = c.SuperField


def _struct_fields(value, label: str) -> None:  # noqa: ANN001
    """A struct's fields one per line, nested structs / arrays two levels deep."""
    lines.append(f"   -- {label}")
    for f in _try(lambda: list(value._type._fields()), []):
        if f.Class.Name.endswith("Property"):
            lines.append(f"      .{f.Name} = {_try(lambda f=f: _brief(value._get_field(f), 0, 2))}")


def _field(struct, *names):  # noqa: ANN001, ANN202
    """The first of these fields the struct has (names unverified: the probe tries a few)."""
    for n in names:
        v = _try(lambda n=n: getattr(struct, n), None)
        if v is not None:
            return v
    return None


def main() -> None:
    lines.append("#" * 60)
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    lines.append(f"{len(trackers)} MissionTracker(s): {[_brief(t) for t in trackers]}")
    if not trackers:
        return
    tracker = trackers[0]
    _fields(tracker, "tracker")

    active = _try(lambda: tracker.ActiveMission, None)
    lines.append(f"ActiveMission = {_brief(active)}")
    for fn in ("GetActiveMission", "GetCurrentObjectives", "GetObjectivesProgress", "GetMissionStatus"):
        for args in ((), (active,)):
            r = _try(lambda fn=fn, args=args: getattr(tracker, fn)(*args))
            lines.append(f"tracker.{fn}{'(active)' if args else '()'} = {_try(lambda r=r: _brief(r, 0, 2))}")

    entries = list(_try(lambda: tracker.MissionList, []) or [])
    lines.append(f"MissionList: {len(entries)} entries")
    defs = []
    for i, entry in enumerate(entries):
        mdef = _field(entry, "MissionDef", "Mission", "MissionDefinition")
        if i < FULL_ENTRIES:
            _struct_fields(entry, f"MissionList[{i}]")
        else:
            status = _field(entry, "Status", "MissionStatus")
            lines.append(f"   [{i}] {_brief(mdef)} status={_brief(status)}"
                         f" name={_try(lambda m=mdef: str(m.MissionName), '?')!r}"
                         f" number={_try(lambda m=mdef: m.MissionNumber, '?')} plot={_try(lambda m=mdef: m.bPlotCritical, '?')}"
                         f" progress={_try(lambda e=entry: _brief(e.ObjectivesProgress), '?')}")
        if mdef is not None:
            defs.append(mdef)

    # a few MissionDefinitions in full, the tracked one first; then its objectives
    picked = ([active] if active is not None else []) + [d for d in defs if d is not active][: FULL_DEFS - 1]
    for mdef in picked:
        _fields(mdef, f"MissionDefinition {_try(lambda m=mdef: str(m.MissionName), '?')!r}", struct_depth=2)
    if active is not None:
        seen = set()
        for f in active.Class._fields():  # every object held by the tracked mission that looks like an objective
            v = _try(lambda f=f: active._get_field(f), None)
            for obj in (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else [v]):
                if hasattr(obj, "Class") and "Objective" in obj.Class.Name and obj._get_address() not in seen:
                    seen.add(obj._get_address())
                    _fields(obj, f"{f.Name} -> {obj.Class.Name}", struct_depth=2)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_quests: {len(lines)} lines -> {OUT}")
