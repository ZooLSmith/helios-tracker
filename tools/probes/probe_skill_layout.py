# Dev probe (in game), instant, read-only: every player's skill tree layout, as the game's skill menu
# would place it - the page's grid looked nothing like the game for a Krieg (skills in odd cells).
# Per branch (SkillTreeBranchDefinition): its tiers' Skills[] (in order), the layout's per-tier
# bCellIsOccupied[], every other field of Layout / tiers / the branch, and the player's grade in each.
# Writes tools/probes/probe_skill_layout.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_skill_layout.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_skill_layout.txt"  # the repo, through the mod's junction
lines: list[str] = ["#" * 70]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_type"):  # struct
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return str(_try(lambda: value.Name))
    if hasattr(value, "__len__"):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:12]) + "]"
    return str(value)


def _fields(obj) -> str:  # noqa: ANN001
    skip = {"Tiers", "Layout", "Outer", "Class", "Name", "ObjectArchetype", "ObjectFlags", "HashNext", "HashOuterNext",
            "StateFrame", "LinkerIndex", "ObjectInternalInteger", "NetIndex", "VfTableObject", "Linker"}
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []):
        if f.Class.Name.endswith("Property") and str(f.Name) not in skip:
            out.append(f"{f.Name}={_brief(_try(lambda f=f: obj._get_field(f)))[:200]}")
    return ", ".join(out)


for pc in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), []):
    if str(pc.Name).startswith("Default__"):
        continue
    tree = _try(lambda p=pc: p.PlayerSkillTree, None)
    if tree is None:
        continue
    player = _try(lambda p=pc: p.PlayerReplicationInfo.PlayerName, "?")
    lines.append(f"== {player} ({_try(lambda p=pc: p.PlayerClass.Name)})")
    grades = {}
    for s in _try(lambda: list(tree.Skills), []) or []:
        d = _try(lambda s=s: s.Definition, None)
        if d is not None:
            grades[_try(lambda d=d: d._get_address())] = _try(lambda s=s: s.Grade, "?")
    lines.append(f"   tree.Branches (the player's, by index): "
                 + ", ".join(f"{i}:{_brief(_try(lambda b=b: b.Definition, None))}(parent {_try(lambda b=b: b.ParentBranchIndex)})"
                             for i, b in enumerate(_try(lambda: list(tree.Branches), []) or [])))
    for b in _try(lambda: list(tree.Branches), []) or []:
        bd = _try(lambda b=b: b.Definition, None)
        if bd is None:
            continue
        lines.append(f"   -- branch {bd.Name} '{_try(lambda: bd.BranchName)}'")
        lines.append(f"      fields: {_fields(bd)}")
        layout = _try(lambda: bd.Layout, None)
        lines.append(f"      Layout: {_brief(layout)[:1500]}")
        for n, tier in enumerate(_try(lambda: list(bd.Tiers), []) or []):
            skills = [sk for sk in _try(lambda t=tier: list(t.Skills), []) or []]
            named = [f"{_try(lambda s=s: s.Name) if s is not None else 'None'}"
                     f"('{_try(lambda s=s: s.SkillName) if s is not None else ''}' g={grades.get(_try(lambda s=s: s._get_address()), '-') if s is not None else '-'})"
                     for s in skills]
            occupied = _try(lambda n=n: [int(bool(c)) for c in layout.Tiers[n].bCellIsOccupied], "?")
            others = {f.Name: _brief(_try(lambda f=f: tier._get_field(f))) for f in _try(lambda: list(tier._type._fields()), [])
                      if f.Class.Name.endswith("Property") and f.Name != "Skills"}
            lines.append(f"      tier {n + 1}: occupied={occupied} skills={named} {others}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_skill_layout: {len(lines)} lines -> {OUT}")
