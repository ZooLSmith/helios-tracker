# Dev probe (in game), instant, read-only: where a weapon card's Accuracy comes from - the page doesn't show it
# (inspector._stats: damage, fire rate, magazine, reload, element chance). WillowWeapon has no UIStatModifiers (the
# items' card stats: WillowItem only) and no property named like accuracy (both games' WillowGame.upk): dumped here,
# every non-zero number of each equipped weapon (float / int / byte / bool, and the attribute properties: Float / Int
# / ByteAttributeProperty, with their ...BaseValue twins), and its WeaponCardModifierStats - to find the card's number
# among them. Tell the agent each weapon's card Accuracy (and name) alongside.
# Properties only, and one known call: the weapon's GetShortHumanReadableName (probe_backpack / probe_zippy's).
# Writes tools/probe_accuracy.txt (overwrites), after each weapon.
#   py exec(open(r"<repo>\tools\probe_accuracy.py").read())
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_accuracy.txt"  # the repo, through the mod's junction
NUMBER_PROPS = ("FloatProperty", "IntProperty", "ByteProperty", "BoolProperty",
                "FloatAttributeProperty", "IntAttributeProperty", "ByteAttributeProperty")
SKIP = {"ObjectInternalInteger", "NetIndex", "NetUpdateFrequency", "NetPriority", "CreationTime", "DrawScale",
        "CustomTimeDilation", "LastRenderTime", "LastNetUpdateTime"}
lines: list[str] = []


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _numbers(obj, indent: str) -> None:  # noqa: ANN001
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if str(f.Class.Name) not in NUMBER_PROPS or str(f.Name) in SKIP:
            continue
        value = _try(lambda f=f: obj._get_field(f))
        value = getattr(value, "name", value)  # (an enum: its name)
        if value in (0, 0.0, False, None):
            continue
        lines.append(f"{indent}{f.Name} = {value!r}  [{f.Class.Name}]")


def _card_stats(weapon) -> None:  # noqa: ANN001
    stats = _try(lambda: list(weapon.WeaponCardModifierStats), [])
    lines.append(f"   -- WeaponCardModifierStats: {len(stats) if isinstance(stats, list) else stats}")
    for n, stat in enumerate(stats if isinstance(stats, list) else []):
        pres = _try(lambda s=stat: s.AttributePresentation, None)
        lines.append(f"   [{n}] {_try(lambda p=pres: p._path_name()) if pres is not None else None}"
                     f" '{_try(lambda p=pres: p.Description) if pres is not None else ''}' ModifierValue={_try(lambda s=stat: s.ModifierValue)!r}")


def _weapon(weapon) -> None:  # noqa: ANN001
    lines.append(f"== {_try(lambda: weapon.GetShortHumanReadableName())!r} ({_try(lambda: weapon.Class.Name)})")
    _card_stats(weapon)
    lines.append("   -- the weapon's numbers")
    _numbers(weapon, "   ")
    _flush()


def main() -> None:
    inv_manager = get_pc().Pawn.InvManager
    seen = set()
    weapon = _try(lambda: inv_manager.InventoryChain, None)
    while weapon is not None and not isinstance(weapon, str) and id(weapon) not in seen and len(seen) < 8:
        seen.add(id(weapon))
        if _try(lambda w=weapon: w.Class.Name) == "WillowWeapon":
            _weapon(weapon)
        weapon = _try(lambda w=weapon: w.Inventory, None)
    lines.append("done")
    _flush()


main()
print(f"probe_accuracy: written to {OUT}")
