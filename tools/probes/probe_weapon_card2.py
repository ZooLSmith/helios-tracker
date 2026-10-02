# Dev probe (in game), instant, read-only (no function calls): the rest of a weapon's card - hold the gun.
#  - every field of each WeaponCardModifierStats[] presentation (the "Consumes 2 ammo per shot" line has no
#    Description: where its text comes from - prefix / suffix / custom placement / a base value...);
#  - its damage type definitions (InstantHitDamageTypeDefinitions[]) and its elemental part: every field - the
#    element's name as the game writes it, if any.
# Written after each section.
# Writes tools/probes/probe_weapon_card2.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_weapon_card2.py").read())
import enum
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_weapon_card2.txt"  # the repo, through the mod's junction
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
    if depth > 3:
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


def _all_fields(obj, label: str) -> None:  # noqa: ANN001
    _flush()
    lines.append(f"== {label}: {_brief(obj)}")
    seen, c = set(), _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            n = str(f.Name)
            if f.Class.Name.endswith("Property") and n not in seen and n not in SKIP:
                seen.add(n)
                lines.append(f"   {n} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    weapon = _try(lambda: get_pc().Pawn.Weapon, None)
    if weapon is None or isinstance(weapon, str):
        lines.append("no weapon in your hands")
        return
    lines.append(f"weapon: {_brief(weapon)} ElementalFrame={_try(lambda: weapon.ElementalFrame)}")
    for n, entry in enumerate(_try(lambda: list(weapon.WeaponCardModifierStats), []) or []):
        lines.append(f"== card line {n}: value {_try(lambda e=entry: _brief(e.ModifierValue))}, shown {_try(lambda e=entry: e.bShouldDisplay)}")
        p = _try(lambda e=entry: e.AttributePresentation, None)
        if p is not None and not isinstance(p, str):
            _all_fields(p, f"card line {n}'s presentation")
    for n, dt in enumerate(_try(lambda: list(weapon.InstantHitDamageTypeDefinitions), []) or []):
        if dt is not None and not isinstance(dt, str):
            _all_fields(dt, f"damage type {n}")
    part = _try(lambda: weapon.DefinitionData.ElementalPartDefinition, None)
    if part is not None and not isinstance(part, str):
        _all_fields(part, "elemental part")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"probe_weapon_card2: {len(lines)} lines -> {OUT}")
