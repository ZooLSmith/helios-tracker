# Dev probe (in game), at once: where a pickup's amount lives - the cash / eridium tooltip reads the item's MonetaryValue
# (to check against what's picked up), ammo / health have no amount yet. For each non-gear pickup in the level (a few
# per kind): its item's numeric properties (non-zero), its definition's ExternalAttributeEffects (what it gives: the
# attribute, the modifier type, the base value's constant / scale / attribute / initialization) and the pickup's own
# numeric properties. Property reads only (no game calls). Stand near some cash, eridium, ammo and health drops.
# Writes tools/probe_pickup_amounts.txt (overwrites; after each pickup)
#   py exec(open(r"<repo>\tools\probe_pickup_amounts.py").read())
import sys
from pathlib import Path

MOD = sys.modules["helios_tracker"]
OUT = Path(MOD.__file__).resolve().parents[1] / "tools" / "probe_pickup_amounts.txt"
PER_KIND = 4
col = MOD._collector  # noqa: SLF001
util = MOD.util
lines: list[str] = []


def _write() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _get(obj, name):  # noqa: ANN001, ANN202
    try:
        return getattr(obj, name)
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>"


def _numbers(obj) -> str:  # noqa: ANN001
    """Its numeric properties (int / float / bool true), by the class's own list - reads only."""
    out = []
    try:
        props = list(obj.Class._fields())
    except Exception as ex:  # noqa: BLE001
        return f"<fields: {type(ex).__name__}>"
    for prop in props:
        kind = str(_get(_get(prop, "Class"), "Name"))
        if kind not in ("IntProperty", "FloatProperty", "ByteProperty", "BoolProperty"):
            continue
        name = str(_get(prop, "Name"))
        value = _get(obj, name)
        if isinstance(value, (int, float)) and value:
            out.append(f"{name}={round(value, 3) if isinstance(value, float) else value}")
    return ", ".join(out)


def _init(data) -> str:  # noqa: ANN001
    """An AttributeInitializationData's fields."""
    return (f"const {_get(data, 'BaseValueConstant')} attr {_get(_get(data, 'BaseValueAttribute'), 'Name')} "
            f"init {_get(_get(data, 'InitializationDefinition'), 'Name')} scale {_get(data, 'BaseValueScaleConstant')}")


seen: dict[str, int] = {}
lines.append(f"{len(col._pickups)} pickups")  # noqa: SLF001
for key, ptr in list(col._pickups.items()):  # noqa: SLF001
    p = ptr()
    if p is None:
        continue
    inv = _get(p, "Inventory")
    if inv is None or isinstance(inv, str):
        continue
    kind = util.pickup_kind(inv) or "?"
    if kind == "?" or seen.get(kind, 0) >= PER_KIND:
        continue
    seen[kind] = seen.get(kind, 0) + 1
    definition = _get(_get(inv, "DefinitionData"), "ItemDefinition")
    lines.append(f"\n== {kind}: {_get(inv, 'Name')} [{_get(_get(inv, 'Class'), 'Name')}] def {_get(definition, 'Name')}")
    lines.append(f"  MonetaryValue {_get(inv, 'MonetaryValue')}; item numbers: {_numbers(inv)}")
    for n, effect in enumerate(_get(definition, "ExternalAttributeEffects") or []):
        lines.append(f"  effect {n}: {_get(_get(effect, 'AttributeToModify'), 'Name')} {getattr(_get(effect, 'ModifierType'), 'name', '?')} "
                     f"base [{_init(_get(effect, 'BaseModifierValue'))}]")
    lines.append(f"  pickup numbers: {_numbers(p)}")
    _write()
_write()
print(f"probe_pickup_amounts: written {OUT}")
