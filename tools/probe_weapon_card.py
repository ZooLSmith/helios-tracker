# Dev probe (in game), instant: what a weapon's item card shows - the red flavour text, its special lines
# ("+50% Critical Hit Damage"), the element's chance / damage - and where each comes from. Hold a gun (best: a
# unique / legendary one, with red text) and run it.
# Logs, for the weapon in your hands:
#  - the weapon's properties named like card / description / presentation / stat / flavor / modifier / element
#    / damage / chance / text (their values);
#  - its DefinitionData (every part) and, for each part: its fields named like presentation / description /
#    effect / attribute / title / flavor, its CustomPresentations / attribute effects in full;
#  - the weapon's functions named like card / description / string / text / stat / info (signatures only: calling
#    its parameterless getters crashed the game - the first version).
# The file is written after each section (a crash leaves what came before).
# Writes tools/probe_weapon_card.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_weapon_card.py").read())
import enum
import re
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_weapon_card.txt"  # the repo, through the mod's junction
WEAPON_FIELDS = re.compile(r"card|descr|present|stat|flavor|modif|element|damage|chance|text|title|unique|red", re.I)
PART_FIELDS = re.compile(r"present|descr|effect|attribute|title|flavor|text|unique|name", re.I)
FUNCS = re.compile(r"card|descr|string|text|stat|info|flavor|element", re.I)
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
        desc = _try(lambda: str(value.Description), None) if "Presentation" in str(value.Class.Name) else None
        return f"{value.Class.Name}'{_try(value._path_name)}'" + (f"({desc!r})" if desc and not desc.startswith("<") else "")
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


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _fields(obj, label: str, pattern) -> None:  # noqa: ANN001
    _flush()  # (what came before: kept if this section crashes)
    lines.append(f"== {label}: {_brief(obj)}")
    seen, c = set(), _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in ("Object", "Actor"):
        for f in _try(lambda c=c: list(c._fields()), []):
            n = str(f.Name)
            if f.Class.Name.endswith("Property") and pattern.search(n) and n not in seen:
                seen.add(n)
                lines.append(f"   {c.Name}.{n} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _functions(obj) -> None:  # noqa: ANN001
    _flush()
    lines.append("== the weapon's functions (signatures only)")
    seen, c = set(), obj.Class
    while c is not None and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            n = str(f.Name)
            if f.Class.Name == "Function" and FUNCS.search(n) and n not in seen:
                seen.add(n)
                params = [p for p in _try(lambda f=f: list(f._fields()), []) if p.Class.Name.endswith("Property")]
                lines.append(f"   {c.Name}.{n}({', '.join(f'{p.Name}:{p.Class.Name.replace(chr(80) + 'roperty', '')}' for p in params)})")
        c = c.SuperField


def main() -> None:
    pc = get_pc()
    weapon = _try(lambda: pc.Pawn.Weapon, None)
    if weapon is None or isinstance(weapon, str):
        lines.append("no weapon in your hands")
        return
    _fields(weapon, "the weapon", WEAPON_FIELDS)
    data = _try(lambda: weapon.DefinitionData, None)
    lines.append(f"== DefinitionData: {_brief(data)}")
    for f in _try(lambda: list(data._type._fields()), []) or []:
        part = _try(lambda f=f: data._get_field(f), None)
        if part is not None and hasattr(part, "Class") and not isinstance(part, str):
            _fields(part, f"part {f.Name}", PART_FIELDS)
    _functions(weapon)
    # the manufacturer's logo and the weapon type's icon on the card: what their definitions point to (a Flash
    # label / frame, an icon, a texture...)
    icons = re.compile(r"icon|flash|label|frame|image|texture|logo|symbol|name|card", re.I)
    for label, get in (("manufacturer", lambda: data.ManufacturerDefinition), ("weapon type", lambda: data.WeaponTypeDefinition),
                       ("balance", lambda: data.BalanceDefinition)):
        d = _try(get, None)
        if d is not None and not isinstance(d, str):
            _fields(d, f"{label} definition", icons)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_weapon_card: {len(lines)} lines -> {OUT}")
