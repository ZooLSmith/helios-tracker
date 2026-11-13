# Dev probe (in game), instant, read-only: an objective whose progress isn't a count - Hunter's Grotto's "Egg on Your
# Face", "Collect drifter eggs" (23): ObjectivesProgress read 6422588 = 0b11000100000000000111100, 23 bits wide, 7 set
# (one bit per egg collected?) - the page took it for done and hid the eggs (2026-11-13, the user). What says so:
# 1. the mission's objective definitions: every property (each type, read; objects by name) - the eggs' against
#    "Kill Arizona" (a plain count), the fields that differ listed first;
# 2. the local player's status of the mission: ObjectivesProgress, its bits counted.
# Run anywhere with the mission picked up. Writes tools/probes/probe_objective_bits.txt (overwrites; section by section)
#   py exec(open(r"<repo>\tools\probes\probe_objective_bits.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_objective_bits.txt"  # the repo, through the mod's junction
MISSION = "GD_Sage_SM_EggOnFace.M_Sage_EggOnFace"
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
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value._path_name()}"
    return repr(value)[:200]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _props(obj) -> dict[str, str]:  # noqa: ANN001
    """Every property of obj (its class chain up to Object), by name -> its value, read (type in front)."""
    out: dict[str, str] = {}
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            if str(f.Class.Name) == "Function" or str(f.Name) in out:
                continue
            out[str(f.Name)] = f"{f.Class.Name} = " + _try(lambda f=f: _brief(obj._get_field(f)))
        c = _try(lambda c=c: c.SuperField, None)
    return out


OUT.write_text("", encoding="utf-8")
mission = _try(lambda: unrealsdk.find_object("MissionDefinition", MISSION), None)
lines.append(f"== 1. {MISSION}: {mission}")
objs = list(_try(lambda: list(mission.ObjectiveDefs), []) or []) if mission else []
dumps = [(_try(lambda o=o: str(o.ObjectiveName)), _props(o)) for o in objs]
if len(dumps) >= 2:
    a, b = dumps[0][1], dumps[1][1]
    lines.append(f"-- differ ({dumps[0][0]!r} | {dumps[1][0]!r}):")
    lines += [f"   {k}: {a.get(k)} | {b.get(k)}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]
for name, props in dumps:
    lines.append(f"-- {name!r}:")
    lines += [f"   {k}: {v}" for k, v in sorted(props.items())]
_flush()

lines.append("== 2. the local player's status")
tracker = next((t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")), None)
lines.append(f"tracker: {tracker}")
for entry in _try(lambda: list(tracker.MissionList), []) or []:
    if _try(lambda e=entry: e.MissionDef._path_name(), "") != MISSION:
        continue
    progress = [int(v) for v in entry.ObjectivesProgress]
    lines.append(f"status {_brief(entry.Status)}; progress {progress}; bits {[bin(v).count('1') for v in progress]}")
    lines.append(f"active set: {_brief(_try(lambda e=entry: e.ActiveObjectiveSet))}")
_flush()
