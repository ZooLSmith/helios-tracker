# Dev probe (in game), instant, read-only: Borderlands 1's skills, for its skill reader (.agent/bl1.md) - no PlayerSkillTree
# there (BL2's): the page shows no tree, and the action skill "ready" before it's unlocked. WillowGame.u (offline):
# pc.PlayerSkills[] = PlayerSkill {Definition, Grade, GradePoints, SkillTreeBranch, SkillTreeTierIndex, SkillTreeEntryIndex,
# Type, bReadied...}; pc.SkillTreeBranches[] = PlayerSkillBranchData {BranchIndex, PointsSpentInBranch, bUnlocked, Tiers[]:
# {TierIndex, bUnlocked, PointsSpentInTier, BranchPointsNeededToUnlockNextTier, PlayerSkillIndexList}};
# pc.ActionSkillPlayerSkillIndex, SkillCooldownPool; PRI GeneralSkillPoints / SpecialistSkillPoints; the class's
# PlayerSkillSet (PlayerSkillSetDefinition: branches -> tiers -> skills); SkillTreeLayoutDefinition (the menu's layout).
# 1. the controller's skill fields; every PlayerSkills entry (its definition's name, type, max grade, icon fields);
# 2. SkillTreeBranches in full;
# 3. the class (PlayerClass) and its PlayerSkillSet's fields; any SkillTreeLayoutDefinition / SkillTreeGFxDefinition.
# Properties only. Writes tools/probes/probe_bl1_skills.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_skills.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_skills.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_skills.txt"
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
        return f"{value:.2f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:40]) + "]"
    if hasattr(value, "_type"):
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


def _fields(obj, limit: int = 5000, only=None) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        name = str(f.Name)
        if f.Class.Name.endswith("Property") and (only is None or only(name)):
            out.append(f"{name}={_brief(_try(lambda f=f: obj._get_field(f)))[:600]}")
    return ", ".join(out)[:limit]


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
pri = _try(lambda: pc.PlayerReplicationInfo, None)

# 1. the controller's skills
lines.append(f"== controller: level {_brief(_try(lambda: pri.ExpLevel))}, GeneralSkillPoints {_brief(_try(lambda: pri.GeneralSkillPoints))}, "
             f"SpecialistSkillPoints {_brief(_try(lambda: pri.SpecialistSkillPoints))}")
lines.append("   " + _fields(pc, 4000, lambda n: any(k in n.lower() for k in ("skill", "actionskill", "instinct", "proficiency", "cooldown"))
                                and not n.startswith("__")))
skills = _try(lambda: list(pc.PlayerSkills), [])
lines.append(f"-- PlayerSkills: {len(skills) if isinstance(skills, list) else skills}")
for n, s in enumerate(skills if isinstance(skills, list) else []):
    d = _try(lambda s=s: s.Definition, None)
    info = (f"{_brief(_try(lambda d=d: d.SkillName))}, type {_brief(_try(lambda d=d: d.SkillType))}, max {_brief(_try(lambda d=d: d.MaxGrade))}, "
            f"level req {_brief(_try(lambda d=d: d.PlayerLevelRequirement))}, frame {_brief(_try(lambda d=d: d.ScaleformFrameName))}, "
            f"icon {_brief(_try(lambda d=d: d.IconU))},{_brief(_try(lambda d=d: d.IconV))}") if d is not None and not isinstance(d, str) else ""
    rest = ", ".join(f"{f.Name}={_brief(_try(lambda f=f, s=s: s._get_field(f)))}" for f in (_try(lambda s=s: list(s._type._fields()), []) or [])
                     if f.Class.Name.endswith("Property") and str(f.Name) != "Definition")
    lines.append(f"   [{n}] {_brief(d)} {info}; {rest}")
_flush()

# 2. the branches
branches = _try(lambda: list(pc.SkillTreeBranches), [])
lines.append(f"== SkillTreeBranches: {len(branches) if isinstance(branches, list) else branches}")
for b in branches if isinstance(branches, list) else []:
    lines.append(f"   {_brief(b)[:2000]}")
_flush()

# 3. the class, its skill set, the layouts
klass = _try(lambda: pc.PlayerClass, None)
lines.append(f"== PlayerClass {_brief(klass)}: " + (_fields(klass, 3000) if klass is not None and not isinstance(klass, str) else ""))
skill_set = _try(lambda: klass.PlayerSkillSet, None)
if skill_set is not None and not isinstance(skill_set, str):
    lines.append(f"-- PlayerSkillSet {_brief(skill_set)}: {_fields(skill_set, 8000)}")
for cls in ("SkillTreeLayoutDefinition", "SkillTreeGFxDefinition", "SkillTreeNavDefinition"):
    found = [o for o in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or [] if not str(o.Name).startswith("Default__")]
    lines.append(f"-- {cls}: {len(found)}")
    for o in found[:4]:
        lines.append(f"   {_brief(o)}: {_fields(o, 4000)}")
_flush()

lines.append("== done")
_flush()
print(f"probe_bl1_skills: written to {OUT}")
