# Dev probe (in game, Borderlands 1), instant: another player's skill tree as the HOST sees it - the page shows it broken
# (Bl1Skills.read: the controller's PlayerSkills[] and SkillTreeBranches[], the class's PlayerSkillSet / SkillTreeLayout,
# the branch names and icons from the skill menu's movie per CharacterName).
# Logs, per player controller (ours first, then the others):
#  - its class (PlayerClass, CharacterName), its player info's CharacterName, ActionSkillPlayerSkillIndex;
#  - PlayerSkills[]: each index, Definition, Grade (in full);
#  - SkillTreeBranches[]: BranchIndex, PointsSpentInBranch, each tier's TierIndex and PlayerSkillIndexList;
#  - its class's PlayerSkillSet and SkillTreeLayout (the branches' tiers' cells: IconClipName);
#  - LAST: the mod's own record for it (games.GAME.skills.read - what the page gets): each tree's name, points, its
#    tiers' cells (skill name, grade, icon).
# Reads properties; the last section runs the mod's reader (as the collector does every players pass).
# Run it in BL1 as the HOST, the other player connected (best: another class than yours, skill points spent).
# Writes tools/probes/probe_bl1_remote_skills.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bl1_remote_skills.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_remote_skills.txt"  # the repo, through the mod's junction
lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


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
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v) for v in list(value)) + "]"
    return repr(value)


def _controller(ctrl, local: bool) -> None:  # noqa: ANN001
    pri = _try(lambda: ctrl.PlayerReplicationInfo, None)
    cls = _try(lambda: ctrl.PlayerClass, None)
    lines.append(f"== controller {ctrl.Name} ({_try(lambda: pri.PlayerName)}) local={local} "
                 f"PlayerClass={_brief(cls)} CharacterName={_brief(_try(lambda: cls.CharacterName))} "
                 f"PRI.CharacterName={_brief(_try(lambda: pri.CharacterName))} "
                 f"ActionSkillPlayerSkillIndex={_try(lambda: ctrl.ActionSkillPlayerSkillIndex)}")
    skills = _try(lambda: list(ctrl.PlayerSkills), [])
    lines.append(f"   PlayerSkills: {len(skills) if isinstance(skills, list) else skills}")
    for n, s in enumerate(skills if isinstance(skills, list) else []):
        lines.append(f"      [{n}] {_brief(_try(lambda s=s: s.Definition))} Grade={_try(lambda s=s: s.Grade)}")
    _save()
    branches = _try(lambda: list(ctrl.SkillTreeBranches), [])
    lines.append(f"   SkillTreeBranches: {len(branches) if isinstance(branches, list) else branches}")
    for b in branches if isinstance(branches, list) else []:
        lines.append(f"      {_brief(_try(lambda b=b: b.BranchIndex))} spent={_try(lambda b=b: b.PointsSpentInBranch)}")
        for t in _try(lambda b=b: list(b.Tiers), []) or []:
            lines.append(f"         tier {_try(lambda t=t: t.TierIndex)}: {_brief(_try(lambda t=t: t.PlayerSkillIndexList))}")
    _save()
    skill_set = _try(lambda: cls.PlayerSkillSet, None)
    layout = _try(lambda: skill_set.SkillTreeLayout, None)
    lines.append(f"   PlayerSkillSet={_brief(skill_set)} SkillTreeLayout={_brief(layout)}")
    if layout is not None and not isinstance(layout, str):
        for field in ("Branch1", "Branch2", "Branch3", "LeftBranch", "MiddleBranch", "RightBranch", "FirstBranch"):
            branch = _try(lambda f=field: getattr(layout, f), None)
            if branch is None or isinstance(branch, str):
                continue
            for n, tier in enumerate(_try(lambda b=branch: list(b.Tiers), []) or []):
                cells = [_try(lambda c=c: str(c.IconClipName), "?") if c is not None else "-" for c in _try(lambda t=tier: list(t.Skills), []) or []]
                lines.append(f"      {field} tier {n}: {cells}")
    _save()


def _mod_record(ctrl, local: bool) -> None:  # noqa: ANN001
    from helios_tracker import games  # noqa: PLC0415

    player = {"local": local}
    lines.append(f"== the mod's record for {ctrl.Name}: {_try(lambda: games.GAME.skills.read(ctrl, player, {}))}")
    for k, v in player.items():
        if k != "skills":
            lines.append(f"   {k} = {v!r}")
    for tree in player.get("skills", []) or []:
        lines.append(f"   tree {tree.get('n')!r} pts={tree.get('pts')} root={tree.get('root', False)}")
        for t, tier in enumerate(tree.get("tiers", []) or []):
            cells = [{k: c[k] for k in list(c)[:6]} if isinstance(c, dict) else c for c in tier.get("cells", [])]
            lines.append(f"      tier {t} need={tier.get('need')}: {cells}")
    _save()


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    lines.append(f"netmode: {_brief(_try(lambda: wi.NetMode))}  local pc: {_brief(pc)}")
    _save()
    others = [c for c in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), []) or []
              if not str(c.Name).startswith("Default__") and c._get_address() != pc._get_address()]
    controllers = [(pc, True), *((c, False) for c in others)]
    for ctrl, local in controllers:
        _controller(ctrl, local)
    for ctrl, local in controllers:
        _mod_record(ctrl, local)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
print(f"probe_bl1_remote_skills: {len(lines)} lines -> {OUT}")
