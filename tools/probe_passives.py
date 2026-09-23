# Dev probe (in game), instant: where passive skill cooldowns / durations live (a skill that, once
# triggered, can't trigger again for a while - e.g. one on cooldown right now). Dumps the skill
# managers (every active skill with its state / timers), the controller's skill / cooldown fields,
# and the definitions of the skills that are active.
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_passives.txt (appends)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_passives.py").read())
import enum
import re
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_passives.txt")
PATTERN = re.compile(r"skill|cooldown|duration|timer|remaining|active", re.I)
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
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:12]) + (f", ... ({len(value)})" if len(value) > 12 else "") + "]"
    if isinstance(value, float):
        return f"{value:.3f}"
    return repr(value)


def _fields(obj, label: str, only=None) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    if obj is None or not hasattr(obj, "Class"):
        return
    c = obj.Class
    while c is not None and c.Name not in ("Object", "Actor", "GBXDefinition"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if only is not None and not only.search(str(f.Name)):
                continue
            if f.Class.Name == "Function":
                if only is not None:
                    lines.append(f"   {c.Name}.{f.Name}({', '.join(str(p.Name) for p in _try(lambda f=f: list(f._fields()), []))})")
            elif f.Class.Name.endswith("Property"):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    lines.append("#" * 60)
    pc = get_pc()
    lines.append(f"time {_try(lambda: ENGINE.GetCurrentWorldInfo().TimeSeconds)}")
    _fields(pc, "controller (skill / cooldown fields)", PATTERN)
    lines.append(f"pc.Timers = {_try(lambda: _brief(pc.Timers))}")
    lines.append(f"melee pool = {_try(lambda: _brief(pc.MeleeSkillCooldownPool.Data))}")
    lines.append(f"melee: time {_try(lambda: pc.GetMeleeSkillCooldownTime())} remaining {_try(lambda: pc.GetMeleeSkillCooldownTimeRemaining())}"
                 f" on cooldown {_try(lambda: pc.IsMeleeSkillOnCooldown())}")
    manager = _try(lambda: pc.GetSkillManager(), None)
    managers = [manager] if manager is not None and not isinstance(manager, str) else []
    lines.append(f"GetSkillManager() = {_brief(manager)}")
    for m in managers:
        _fields(m, "skill manager")
        # its arrays of structs (active skills...) entry by entry, with more depth
        for f in m.Class._fields():
            v = _try(lambda f=f: m._get_field(f), None)
            if hasattr(v, "__len__") and not isinstance(v, str) and len(v) and hasattr(list(v)[0], "_type"):
                for i, entry in enumerate(list(v)[:40]):
                    lines.append(f"   {f.Name}[{i}] = {_brief(entry)}")
    # every active skill instance, field by field (its time left, its owner / instigator...)
    for m in managers:
        for sk in list(_try(lambda m=m: m.ActiveSkills, []) or [])[:12]:
            if hasattr(sk, "Class"):
                _fields(sk, f"active skill ({_try(lambda sk=sk: str(sk.Definition.Name), '?')})")
    # the definitions of every skill object referenced by the managers
    seen = set()
    for m in managers:
        for f in m.Class._fields():
            v = _try(lambda f=f: m._get_field(f), None)
            for item in (list(v) if hasattr(v, "__len__") and not isinstance(v, str) else [v]):
                for cand in ([item] + [_try(lambda i=item, n=n: getattr(i, n), None) for n in ("Definition", "SkillDefinition", "Skill")]):
                    if hasattr(cand, "Class") and "SkillDefinition" in str(cand.Class.Name) and cand._get_address() not in seen:
                        seen.add(cand._get_address())
                        _fields(cand, f"skill definition ({f.Name})", PATTERN)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_passives: {len(lines)} lines -> {OUT}")
