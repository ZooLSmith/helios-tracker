# Dev probe (in game), instant: the stats a skill's tooltip lists ("Gun Damage: +4%") - where they come from.
# Logs, for a few of your skills (one with points, a 1-rank one, a 5-rank one):
#  - the SkillDefinition: every property (name, description, max grade, its effects...);
#  - each SkillEffectDefinitions[] entry in full (the attribute it modifies, the modifier type, its base value
#    and per-grade scaling...), and the attribute's own fields;
#  - the attribute presentations naming that attribute (AttributePresentationDefinition: display text, as a
#    percentage?, sign...) - found by the attribute they point to;
#  - the SkillDefinition's functions named like description / effect / string / text / value (signatures),
#    and the few that only read (Get*Description / Get*Value with no out params) called for its grade.
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_skill_stats.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_skill_stats.py").read())
import enum
import re
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_skill_stats.txt")
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
        return f"{value:.4g}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:12]) + "]"
    return repr(value)


def _dump(obj, label: str, stop_at: str = "Object") -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != stop_at:
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property"):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _functions(obj) -> None:  # noqa: ANN001
    c = obj.Class
    while c is not None and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and re.search(r"descr|effect|string|text|value|stat|grade|format", str(f.Name), re.I):
                params = [f"{p.Name}:{p.Class.Name.replace('Property', '')}" for p in _try(lambda f=f: list(f._fields()), [])
                          if p.Class.Name.endswith("Property")]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
        c = c.SuperField


def main() -> None:
    pc = get_pc()
    tree = pc.PlayerSkillTree
    grades = []  # (definition, grade)
    for s in _try(lambda: list(tree.Skills), []) or []:  # (one flat array: inspector.py)
        sd = _try(lambda s=s: s.Definition, None) or _try(lambda s=s: s.SkillDefinition, None)
        if sd is not None and not isinstance(sd, str):
            grades.append((sd, _try(lambda s=s: int(s.Grade), 0)))
    lines.append(f"{len(grades)} skills in your tree")
    picks, seen = [], set()
    by_kind = [lambda d, g: g > 0, lambda d, g: _try(lambda: int(d.MaxGrade), 0) == 1, lambda d, g: _try(lambda: int(d.MaxGrade), 0) == 5]
    for test in by_kind:
        for sd, g in grades:
            if sd._path_name() not in seen and test(sd, g):
                picks.append((sd, g))
                seen.add(sd._path_name())
                break
    presentations = [p for p in _try(lambda: list(unrealsdk.find_all("AttributePresentationDefinition", exact=False)), []) or []
                     if not p.Name.startswith("Default__")]
    lines.append(f"{len(presentations)} AttributePresentationDefinition objects loaded")
    for sd, grade in picks:
        _dump(sd, f"SkillDefinition (grade {grade})")
        for i, eff in enumerate(_try(lambda sd=sd: list(sd.SkillEffectDefinitions), []) or []):
            lines.append(f"== effect {i}: {_brief(eff)}")
            attr = _try(lambda eff=eff: eff.AttributeToModify, None)
            if attr is not None and not isinstance(attr, str):
                _dump(attr, f"   its attribute {attr.Name}")
                for p in presentations:
                    if _try(lambda p=p: p.Attribute, None) is attr:
                        _dump(p, f"   its presentation {p.Name}")
        lines.append("== functions")
        _functions(sd)
        for name in ("GetSkillDescription", "GetDescription", "GetEffectsDescription"):
            fn = _try(lambda n=name, sd=sd: getattr(sd, n), None)
            if fn is not None and not isinstance(fn, str):
                lines.append(f"   {name}() -> {_try(lambda fn=fn: _brief(fn()))}")
    if presentations:
        _dump(presentations[0], "an AttributePresentationDefinition (any)")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_skill_stats: {len(lines)} lines -> {OUT}")
