# Dev probe (in game), instant: what tells ground pickups apart (ammo, health, cash, eridium...).
# Stand near some drops (kill a few enemies, open ammo crates / a safe) and run it. Every pickup in
# the level is listed; each distinct item definition is dumped once, field by field (the pickup,
# its inventory item and the item's definition, up to the engine base classes).
# Writes E:\Projects\python\borderlands-2\tools\probe_pickups.txt (appends)
#   py exec(open(r"E:\Projects\python\borderlands-2\tools\probe_pickups.py").read())
import enum
from pathlib import Path

import unrealsdk

OUT = Path(r"E:\Projects\python\borderlands-2\tools\probe_pickups.txt")
SCALARS = ("StrProperty", "NameProperty", "ObjectProperty", "ClassProperty", "ByteProperty", "IntProperty",
           "FloatProperty", "BoolProperty", "EnumProperty", "StructProperty", "ArrayProperty")
STOP = {"Object", "Actor", "GBXDefinition", "Inventory", "DroppedPickup"}  # engine bases: not dumped

lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):  # before the array case: an IntFlag iterates to itself
        return f"{type(value).__name__}.{value.name}({int(value) if isinstance(value, int) else value.value})"
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):  # WrappedStruct
        if depth > 1:
            return "{...}"
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):  # UObject
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):  # WrappedArray
        items = [_brief(v, depth + 1) for v in list(value)[:4]]
        more = f", ... ({len(value)} total)" if len(value) > 4 else ""
        return "[" + ", ".join(items) + more + "]"
    if isinstance(value, float):
        return f"{value:.3f}"
    return repr(value)


def _fields(obj, label: str) -> None:  # noqa: ANN001
    """Every property of obj's own classes (down to the engine bases), one line each."""
    lines.append(f"   -- {label}: {_brief(obj)}")
    if obj is None or not hasattr(obj, "Class"):
        return
    c = obj.Class
    while c is not None and c.Name not in STOP:
        for f in c._fields():
            if f.Class.Name in SCALARS:
                # one bad field (whatever it is) mustn't lose the rest of the dump
                lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _name(inv) -> str:  # noqa: ANN001
    for args in ((), ("",)):
        try:
            r = inv.GetShortHumanReadableName(*args)
        except Exception:  # noqa: BLE001, S112
            continue
        if isinstance(r, tuple):
            r = next((v for v in r if isinstance(v, str) and v), "")
        return str(r)
    return "?"


def main() -> None:
    lines.append("#" * 60)
    pickups = [p for p in unrealsdk.find_all("WillowPickup", exact=False) if not p.Name.startswith("Default__")]
    lines.append(f"{len(pickups)} pickups")
    seen: dict[str, int] = {}
    dumped: set[str] = set()
    for p in pickups:
        inv = _try(lambda p=p: p.Inventory, None)
        item_def = _try(lambda: inv.DefinitionData.ItemDefinition, None) if inv is not None else None
        balance = _try(lambda: inv.DefinitionData.BalanceDefinition, None) if inv is not None else None
        key = _brief(item_def) if item_def is not None else f"{p.Class.Name} / {inv.Class.Name if inv else None}"
        seen[key] = seen.get(key, 0) + 1
        lines.append(
            f"- {p.Class.Name} rarity={_try(lambda p=p: p.InventoryRarityLevel)} pickupable={_try(lambda p=p: p.bPickupable)}"
            f" | inv {inv.Class.Name if inv else None} '{_name(inv) if inv else ''}'"
            f" | def {_brief(item_def)} | balance {_brief(balance)}")
        if key in dumped:
            continue
        dumped.add(key)
        _fields(p, "pickup")
        _fields(inv, "inventory")
        _fields(item_def, "item definition")
    lines.append("distinct definitions: " + ", ".join(f"{k} x{n}" for k, n in sorted(seen.items())))


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_pickups: {len(lines)} lines -> {OUT}")
