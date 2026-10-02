# Dev probe (in game), instant, read-only (no function calls): how the card's elemental chance ("16.8%" on a
# shock Maliwan pistol whose StatusEffectChanceModifier base is 1.4, BaseStatusEffectChanceModifier 0.6) is made -
# hold the gun. Dumps the weapon's status effect chance fields and its damage type's StatusEffect definition
# (every field: its base chance?), then that definition's nested chance data. Written after each section.
# Writes tools/probes/probe_element_chance.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_element_chance.py").read())
import enum
import re
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_element_chance.txt"  # the repo, through the mod's junction
SKIP = {"VfTableObject", "HashNext", "ObjectFlags", "HashOuterNext", "StateFrame", "Linker", "LinkerIndex",
        "ObjectInternalInteger", "NetIndex", "ObjectArchetype"}
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
    if depth > 4:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:10]) + "]"
    return repr(value)


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _all_fields(obj, label: str, pattern=None) -> None:  # noqa: ANN001
    _flush()
    lines.append(f"== {label}: {_brief(obj)}")
    seen, c = set(), _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            n = str(f.Name)
            if f.Class.Name.endswith("Property") and n not in seen and n not in SKIP and (pattern is None or pattern.search(n)):
                seen.add(n)
                lines.append(f"   {n} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    weapon = _try(lambda: get_pc().Pawn.Weapon, None)
    if weapon is None or isinstance(weapon, str):
        lines.append("no weapon in your hands")
        return
    _all_fields(weapon, "the weapon's status effect / chance fields", re.compile(r"status|chance|element|fire.?rate|interval", re.I))
    dt = next(iter(_try(lambda: list(weapon.InstantHitDamageTypeDefinitions), []) or []), None)
    se = _try(lambda: dt.StatusEffect, None) if dt is not None else None
    if se is not None and not isinstance(se, str):
        _all_fields(se, "the damage type's StatusEffect")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"probe_element_chance: {len(lines)} lines -> {OUT}")
