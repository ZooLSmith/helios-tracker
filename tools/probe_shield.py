# Dev probe (in game), instant, read-only: a shield's card stats - the page had none (inspector._stats reads weapons
# and grenades only). The game's card for the equipped one (the Pre-Sequel, a Dinky Shield): capacity 53, recharge
# rate 16, recharge delay 2.36 (CARD below - set it to what your shield's card shows).
# First run: no number property holds them (only ReplicatedAttributeSlotModifierValues -0.36 / 0.36 / -0.48). The
# packages (both games' WillowGame.upk) have WillowItem.UIStatModifiers[] = UIStatModifierData {AttributePresentation,
# ModifierTotal, CompareModifierTotal, AttributeStyle, StatCombinationMethod, Supplemental...}: dumped too, with
# ItemCardModifierStats[] (the card lines the mod reads) - each entry's fields, its presentation's text fields.
# Per shield (equipped, then the backpack's): every number property of the item (float / int / byte / bool), and of
# its ShieldDef; the ones matching a CARD value (after the game's rounding: to the nearest, a whole number or 2
# decimals) marked "<== card <value>" - the property that holds it. Properties only, and one known call: the item's
# GetShortHumanReadableName (probe_backpack / probe_zippy's).
# Writes tools/probe_shield.txt (overwrites), after each shield.
#   py exec(open(r"<repo>\tools\probe_shield.py").read())
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_shield.txt"  # the repo, through the mod's junction
CARD = (53, 16, 2.36)  # the equipped shield's card: capacity, recharge rate, recharge delay
NUMBER_PROPS = ("FloatProperty", "IntProperty", "ByteProperty", "BoolProperty")
lines: list[str] = []


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _matches(value) -> str:  # noqa: ANN001
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    hits = [c for c in CARD if round(value) == c or round(value, 2) == c]
    return f"   <== card {hits[0]}" if hits else ""


def _numbers(obj, indent: str) -> None:  # noqa: ANN001
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if str(f.Class.Name) not in NUMBER_PROPS:
            continue
        value = _try(lambda f=f: obj._get_field(f))
        if hasattr(value, "name"):  # an enum
            value = value.name
        lines.append(f"{indent}{f.Name} = {value!r}{_matches(value)}")


def _struct_fields(value) -> list[tuple[str, object]]:  # noqa: ANN001
    return [(str(f.Name), _try(lambda f=f: value._get_field(f)))
            for f in _try(lambda: list(value._type._fields()), []) or [] if str(f.Class.Name).endswith("Property")]


def _presentation(obj, indent: str) -> None:  # noqa: ANN001
    """An AttributePresentationDefinition: its path, its string / name / number properties."""
    lines.append(f"{indent}{_try(lambda: obj._path_name())}")
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if str(f.Class.Name) in ("StrProperty", "NameProperty", *NUMBER_PROPS):
            value = _try(lambda f=f: obj._get_field(f))
            if value not in ("", None, 0, 0.0, False):
                lines.append(f"{indent}  {f.Name} = {getattr(value, 'name', value)!r}")


def _entries(inv, prop: str) -> None:  # noqa: ANN001
    entries = _try(lambda: list(getattr(inv, prop)))
    lines.append(f"   -- {prop}: {len(entries) if isinstance(entries, list) else entries}")
    for n, entry in enumerate(entries if isinstance(entries, list) else []):
        lines.append(f"   [{n}]")
        for name, value in _struct_fields(entry):
            if hasattr(value, "_path_name"):
                lines.append(f"      {name}:")
                _presentation(value, "        ")
            else:
                value = getattr(value, "name", value)
                lines.append(f"      {name} = {value!r}{_matches(value)}")


def _shield(inv, where: str) -> None:  # noqa: ANN001
    lines.append(f"== {where}: {_try(lambda: inv.Class.Name)} {_try(lambda: inv.GetShortHumanReadableName())!r}")
    _entries(inv, "UIStatModifiers")
    _entries(inv, "ItemCardModifierStats")
    _flush()
    lines.append("   -- the item's properties")
    _numbers(inv, "   ")
    shield_def = _try(lambda: inv.ShieldDef, None)
    if shield_def is not None and not isinstance(shield_def, str):
        lines.append(f"   -- ShieldDef {_try(lambda: shield_def._path_name())}")
        _numbers(shield_def, "   ")
    _flush()


def main() -> None:
    inv_manager = get_pc().Pawn.InvManager
    seen = set()
    inv = _try(lambda: inv_manager.ItemChain, None)
    while inv is not None and not isinstance(inv, str) and id(inv) not in seen and len(seen) < 20:
        seen.add(id(inv))
        if _try(lambda i=inv: i.Class.Name) == "WillowShield":
            _shield(inv, "equipped")
        inv = _try(lambda i=inv: i.Inventory, None)
    for inv in list(_try(lambda: list(inv_manager.Backpack), []) or [])[:12]:
        if _try(lambda i=inv: i.Class.Name) == "WillowShield":
            _shield(inv, "backpack")
    lines.append("done")
    _flush()


main()
print(f"probe_shield: written to {OUT}")
