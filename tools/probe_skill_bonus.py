# Dev probe (in game), instant: where a skill's bonus ranks come from (a class mod's "+N", shown in blue in the
# skill screen - on the user's character: "Steady"). Run it with the class mod equipped.
# Logs, for the skill named SKILL (and one without a bonus, to compare):
#  - its entry in pc.PlayerSkillTree.Skills[] in full (every field of the struct);
#  - the functions of PlayerSkillTree / the controller / the skill manager named like grade / bonus / level /
#    modifier (signatures), and the read-only ones that take a SkillDefinition called with it;
#  - the equipped class mod: every property of it and of its definition named like skill / bonus / grade /
#    attribute / modifier (its skill boosts);
#  - GetSkillEffectPresentations at the base grade and grade + 1..3 (which values the blue text matches).
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_skill_bonus.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_skill_bonus.py").read())
import enum
import re
from pathlib import Path

import unrealsdk
from mods_base import get_pc

SKILL = "Steady"
OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_skill_bonus.txt")
PATTERN = re.compile(r"grade|bonus|skill|level|modif|attribute|slot|boost", re.I)
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
    if isinstance(value, tuple):
        return "(" + ", ".join(_brief(v, depth + 1) for v in value) + ")"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:10]) + "]"
    return repr(value)


def _signatures(obj, label: str):  # noqa: ANN001, ANN202
    lines.append(f"== {label} functions: {_brief(obj)}")
    found = []
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and re.search(r"grade|bonus|skilllevel|modif", str(f.Name), re.I):
                params = [p for p in _try(lambda f=f: list(f._fields()), []) if p.Class.Name.endswith("Property")]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(f'{p.Name}:{p.Class.Name}' for p in params)})")
                found.append((str(f.Name), params))
        c = c.SuperField
    return found


def _fields(obj, label: str, only_matching: bool = True) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in ("Object", "Actor"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (not only_matching or PATTERN.search(str(f.Name))):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    pc = get_pc()
    tree = pc.PlayerSkillTree
    entries = [(s, _try(lambda s=s: s.Definition, None)) for s in _try(lambda: list(tree.Skills), []) or []]
    target = next(((s, d) for s, d in entries if d is not None and str(_try(lambda d=d: d.SkillName, "")) == SKILL), None)
    other = next(((s, d) for s, d in entries if d is not None and target and d is not target[1] and _try(lambda s=s: int(s.Grade), 0) > 0), None)
    if target is None:
        lines.append(f"no skill named {SKILL!r}; names: {[str(_try(lambda d=d: d.SkillName, '?')) for _, d in entries if d]}")
        return
    for label, (entry, sd) in (("the skill", target), ("another invested skill", other or target)):
        lines.append(f"==== {label}: {sd.SkillName!s} ({sd._path_name()})")
        lines.append(f"   its tree entry: {_brief(entry)}")
        base = _try(lambda entry=entry: int(entry.Grade), 0)
        for g in range(max(1, base), base + 4):
            lines.append(f"   GetSkillEffectPresentations({g}) -> {_try(lambda g=g, sd=sd: _brief(sd.GetSkillEffectPresentations(g, pc, [])))}")
    sd = target[1]
    holders = {"PlayerSkillTree": tree, "controller": pc, "skill manager": _try(lambda: pc.GetSkillManager(), None)}
    for label, obj in holders.items():
        if obj is None or isinstance(obj, str):
            continue
        for name, params in _signatures(obj, label):
            # read-only looking getters taking just a SkillDefinition (and maybe the controller)
            kinds = [p.Class.Name for p in params if not (p.PropertyFlags & 0x400 if hasattr(p, "PropertyFlags") else False)]
            if name.startswith(("Get", "Is", "Has")) and len(kinds) <= 3:
                for args in ((sd,), (pc, sd), (sd, pc)):
                    res = _try(lambda name=name, args=args, obj=obj: getattr(obj, name)(*args), None)
                    if res is not None and not str(res).startswith("<"):
                        lines.append(f"      {name}{tuple(type(a).__name__ for a in args)} -> {_brief(res)}")
                        break
    # the equipped class mod
    inv = _try(lambda: pc.Pawn.InvManager, None)
    mods = []
    item = _try(lambda: inv.ItemChain, None)
    for _ in range(40):
        if item is None or isinstance(item, str):
            break
        if "ClassMod" in str(item.Class.Name):
            mods.append(item)
        item = _try(lambda item=item: item.Inventory, None)
    lines.append(f"== {len(mods)} class mods equipped")
    for m in mods[:2]:
        _fields(m, "class mod")
        d = _try(lambda m=m: m.DefinitionData.ItemDefinition, None)
        if d is not None and not isinstance(d, str):
            _fields(d, "   its definition")
            for n in ("AttributeSlotEffects", "AttributeSlotUpgrades", "ExternalAttributeEffects", "InventoryAttributeEffects"):
                v = _try(lambda d=d, n=n: getattr(d, n), None)
                if v is not None and not isinstance(v, str):
                    lines.append(f"   {n} = {_brief(v)}")
    # attributes named like this skill (a class mod boosts a skill through an attribute?)
    key = re.sub(r"\W", "", SKILL).lower()
    attrs = [a for a in _try(lambda: list(unrealsdk.find_all("AttributeDefinition", exact=False)), []) or []
             if key in str(a.Name).lower() or key in str(_try(a._path_name, "")).lower()]
    lines.append(f"== {len(attrs)} attributes named like {SKILL!r}")
    for a in attrs[:12]:
        lines.append(f"   {_brief(a)} value for pc: {_try(lambda a=a: _brief(a.GetValue(pc)))}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_skill_bonus: {len(lines)} lines -> {OUT}")
