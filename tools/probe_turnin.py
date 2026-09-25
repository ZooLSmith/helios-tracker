# Dev probe (in game), instant: what tells a mission is ready to turn in (every required objective
# done, not handed in yet) - for the mission log (show those green). Run it with a few missions ready
# to turn in and a few still in progress (say which in chat).
# Logs: the EMissionStatus values; every mission not NotStarted / Complete: its status (name + number),
# objective counts vs progress (optional marked), the current step (ActiveObjectiveSet: can it complete
# the mission, next set); the tracker's functions about turning in / completing (names + params), and
# the read-only ones (Is* / Get* / Can* / Has*) taking a mission called on each of those missions.
# Writes tools/probe_turnin.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_turnin.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_turnin.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"turn|redeem|ready|complet|finish|reward|status", re.I)
READ_ONLY = re.compile(r"^(Is|Get|Can|Has)")
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
        return f"{value.name}({value.value})"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{value.Name}'"
    if isinstance(value, tuple):
        return "(" + ", ".join(_brief(v) for v in value) + ")"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v) for v in list(value)[:12]) + "]"
    return repr(value)


def _set_brief(s) -> str:  # noqa: ANN001
    if s is None:
        return "None"
    objs = [f"{_try(lambda o=o: str(o.ProgressMessage), '?')!r}" for o in _try(lambda: list(s.ObjectiveDefinitions), [])]
    return (f"{s.Name} canComplete={_try(lambda: s.bCanCompleteMission)} next={_try(lambda: _brief(s.NextSet))}"
            f" objectives={objs}")


def main() -> None:
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    if not trackers:
        lines.append("no MissionTracker")
        return
    tracker = trackers[0]
    entries = list(_try(lambda: tracker.MissionList, []) or [])
    status_type = next((type(e.Status) for e in entries if isinstance(_try(lambda e=e: e.Status, None), enum.Enum)), None)
    if status_type is not None:
        lines.append(f"{status_type.__name__}: " + ", ".join(f"{m.name}={m.value}" for m in status_type))
    lines.append(f"ActiveMission (tracked) = {_brief(_try(lambda: tracker.ActiveMission, None))}")

    # the tracker's functions about turning in / completing
    funcs, c = [], tracker.Class
    while c is not None and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and PATTERN.search(str(f.Name)):
                params = [(str(p.Name), p.Class.Name) for p in _try(lambda f=f: list(f._fields()), [])]
                funcs.append((str(f.Name), params))
                lines.append(f"   {c.Name}.{f.Name}({', '.join(f'{n}:{k}' for n, k in params)})")
        c = c.SuperField
    # read-only ones whose first param is an object (the mission): called per mission below
    callable_ = [n for n, params in funcs if READ_ONLY.match(n) and params and params[0][1] == "ObjectProperty"
                 and sum(1 for n, _ in params if n != "ReturnValue") == 1]

    lines.append("== missions underway (not NotStarted / Complete)")
    for i, e in enumerate(entries):
        status = _try(lambda e=e: e.Status, None)
        name = getattr(status, "name", str(status))
        if name in ("MS_NotStarted", "MS_Complete"):
            continue
        m = _try(lambda e=e: e.MissionDef, None)
        lines.append(f"[{i}] {_try(lambda: str(m.MissionName), '?')!r} status={_brief(status)}"
                     f" heardKickoff={_try(lambda e=e: e.bHeardKickoff)} plot={_try(lambda: m.bPlotCritical)}")
        progress = list(_try(lambda e=e: e.ObjectivesProgress, []) or [])
        for k, o in enumerate(_try(lambda: list(m.ObjectiveDefs), [])):
            lines.append(f"      obj {k}: {_try(lambda o=o: progress[k] if k < len(progress) else '-')}"
                         f" / {_try(lambda o=o: o.ObjectiveCount)} optional={_try(lambda o=o: o.bObjectiveIsOptional)}"
                         f" {_try(lambda o=o: str(o.ProgressMessage), '?')!r}")
        lines.append(f"      step: {_try(lambda e=e: _set_brief(e.ActiveObjectiveSet))}")
        lines.append(f"      sub steps: {_try(lambda e=e: [_set_brief(s) for s in e.SubObjectiveSets])}")
        lines.append(f"      turn in: {_try(lambda: str(m.TurnInDescription), '?')!r}")
        for fn in callable_:
            lines.append(f"      tracker.{fn}(mission) = {_try(lambda fn=fn: _brief(getattr(tracker, fn)(m)))}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_turnin: {len(lines)} lines -> {OUT}")
