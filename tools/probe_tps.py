# Dev probe (in game), instant, read-only: what the Pre-Sequel gives the mod's skills and weapon type readers - the
# page showed no skills there, and a sniper's type name in lower case (.agent/presequel.md).
# 1. skills: every player controller's PlayerSkillTree, read as inspector._skills reads it (Branches / Tiers /
#    Skills, their fields), each failing read shown with its exception - the mod's try_ hides them.
# 2. weapon types: every weapon's DefinitionData.WeaponTypeDefinition (Typename, ScaleformFrameName, WeaponType,
#    its other fields) - the page's type name is its Typename.
# Properties only, one known mod call (GetSkillPointsSpentInTree: the mod calls it every read). Writes
# tools/probe_tps.txt after each section (appends).
#   py exec(open(r"<repo>\tools\probe_tps.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_tps.txt"  # the repo, through the mod's junction
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 2:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if hasattr(value, "_type"):  # struct
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "__len__"):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:6]) + "]"
    return str(value)


def _fields(obj, limit: int = 3000) -> str:  # noqa: ANN001
    skip = {"Outer", "Class", "Name", "ObjectArchetype", "ObjectFlags", "HashNext", "HashOuterNext", "StateFrame",
            "LinkerIndex", "ObjectInternalInteger", "NetIndex", "VfTableObject", "Linker"}
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if f.Class.Name.endswith("Property") and str(f.Name) not in skip:
            out.append(f"{f.Name}={_brief(_try(lambda f=f: obj._get_field(f)))[:300]}")
    return ", ".join(out)[:limit]


# 1. skills
lines.append("== skills")
for pc in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), []) or []:
    if str(pc.Name).startswith("Default__"):
        continue
    lines.append(f"-- controller {pc.Name} ({pc.Class.Name}), player {_try(lambda p=pc: p.PlayerReplicationInfo.PlayerName)}, "
                 f"class {_try(lambda p=pc: p.PlayerClass.Name)}, level {_try(lambda p=pc: p.PlayerReplicationInfo.ExpLevel)}")
    tree = _try(lambda p=pc: p.PlayerSkillTree)
    lines.append(f"   PlayerSkillTree: {_brief(tree)}")
    if tree is None or isinstance(tree, str):
        _flush()
        continue
    lines.append(f"   tree fields: {_fields(tree, 4000)}")
    lines.append(f"   GetSkillPointsSpentInTree: {_try(lambda: tree.GetSkillPointsSpentInTree())}")
    lines.append(f"   SkillTreeRootIndex: {_try(lambda: tree.SkillTreeRootIndex)}")
    for label in ("Branches", "Tiers", "Skills"):
        arr = _try(lambda a=label: list(getattr(tree, a)))
        if isinstance(arr, str):
            lines.append(f"   {label}: {arr}")
            continue
        lines.append(f"   {label}: {len(arr)}")
        for i, entry in enumerate(arr[:4]):
            lines.append(f"     [{i}] {_brief(entry)[:600]}")
    _flush()
    # the first skill's definition, field by field (SkillName, MaxGrade, SkillDescription, SkillIcon)
    first = next(iter(_try(lambda: list(tree.Skills), []) or []), None)
    sd = _try(lambda: first.Definition) if first is not None and not isinstance(first, str) else None
    if sd is not None and not isinstance(sd, str):
        lines.append(f"   first skill definition {_try(lambda: sd._path_name())}: SkillName={_try(lambda: sd.SkillName)!r}, "
                     f"MaxGrade={_try(lambda: sd.MaxGrade)}, SkillIcon={_brief(_try(lambda: sd.SkillIcon))}")
    # the branches' definitions (the grids: Tiers[].Skills, Layout)
    for b in (_try(lambda: list(tree.Branches), []) or [])[:4]:
        bd = _try(lambda b=b: b.Definition)
        if bd is None or isinstance(bd, str):
            lines.append(f"   branch without Definition: {_brief(b)[:400]}")
            continue
        lines.append(f"   branch {_try(lambda: bd._path_name())}: BranchName={_try(lambda: bd.BranchName)!r}, "
                     f"Tiers={len(_try(lambda: list(bd.Tiers), []) or [])}, Layout={_brief(_try(lambda: bd.Layout))[:400]}")
    lines.append(f"   GetSkillManager (the mod's call): {_brief(_try(lambda p=pc: p.GetSkillManager()))}")
    lines.append(f"   SkillCooldownPool: {_brief(_try(lambda p=pc: p.SkillCooldownPool))[:300]}")
    lines.append(f"   SavedSkillTreeSkill: {_brief(_try(lambda p=pc: p.SavedSkillTreeSkill))}")
    _flush()

# 2. weapon types
lines.append("== weapon types")
seen = set()
for w in _try(lambda: list(unrealsdk.find_all("WillowWeapon", exact=False)), []) or []:
    if str(w.Name).startswith("Default__"):
        continue
    wt = _try(lambda w=w: w.DefinitionData.WeaponTypeDefinition)
    if wt is None or isinstance(wt, str):
        lines.append(f"-- {w.Name}: WeaponTypeDefinition {wt}")
        continue
    key = _try(lambda: wt._path_name())
    if key in seen:
        continue
    seen.add(key)
    lines.append(f"-- {w.Name} ({_try(lambda w=w: w.Class.Name)}): {key}")
    lines.append(f"   Typename={_try(lambda: wt.Typename)!r}, ScaleformFrameName={_try(lambda: wt.ScaleformFrameName)!r}, "
                 f"WeaponType={_brief(_try(lambda: wt.WeaponType))}")
    lines.append(f"   fields: {_fields(wt, 2500)}")
_flush()
print(f"probe_tps: written to {OUT}")
