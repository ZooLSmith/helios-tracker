# Dev probe (in game), instant: the game's own computation of a skill's tooltip stats -
# SkillDefinition.GetSkillEffectPresentations(SkillGrade, ContextSource, out EffectPresentations)
# (tools/probe_skill_stats.txt). For every skill of your tree: its grade, the call at that grade and the next
# (the out array's entries in full: presentation, value...), and its own SkillEffectPresentations[] (their
# Description and display flags).
# Writes tools/probe_skill_stats2.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_skill_stats2.py").read())
import enum
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_skill_stats2.txt"  # the repo, through the mod's junction
PRES_FIELDS = ("Description", "Prefix", "Suffix", "bDisplayAsPercentage", "bDisplayPercentAsFloat", "bDisplayAsInverse",
               "bDontDisplayNumber", "bDontDisplayPlusSign", "SignStyle", "RoundingMode", "FloatPrecision", "Attribute")
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
        desc = _try(lambda: value.Description, None) if value.Class.Name == "AttributePresentationDefinition" else None
        return f"{value.Class.Name}'{value.Name}'" + (f"({desc!r})" if desc not in (None, "<err>") else "")
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_brief(v, depth + 1) for v in value) + ")"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:12]) + "]"
    return repr(value)


def main() -> None:
    pc = get_pc()
    tree = pc.PlayerSkillTree
    for s in _try(lambda: list(tree.Skills), []) or []:
        sd = _try(lambda s=s: s.Definition, None)
        if sd is None or isinstance(sd, str):
            continue
        grade = _try(lambda s=s: int(s.Grade), 0)
        top = _try(lambda: int(sd.MaxGrade), 0)
        lines.append(f"== {sd.SkillName!s} ({sd.Name}) grade {grade} / {top}")
        for g in sorted({max(grade, 1), min(top, grade + 1)} - {0}):
            # pyunrealsdk: out params come back after the return value (a tuple), the out array passed as []
            lines.append(f"   GetSkillEffectPresentations({g}, pc) -> {_try(lambda g=g: _brief(sd.GetSkillEffectPresentations(g, pc, [])))}")
        for p in _try(lambda: list(sd.SkillEffectPresentations), []) or []:
            if p is not None:
                lines.append("   presentation: " + ", ".join(f"{k}={_try(lambda k=k, p=p: _brief(getattr(p, k)))}" for k in PRES_FIELDS))


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_skill_stats2: {len(lines)} lines -> {OUT}")
