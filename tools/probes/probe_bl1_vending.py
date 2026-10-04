# Dev probe (in game), instant, read-only: Borderlands 1's vending machines (.agent/bl1.md) - the page shows them but
# not their stock. BL1's WillowVendingMachine (no WillowVendingMachineBase - shops.py's MACHINE_CLASS): ShopType,
# FeaturedItem, and ShopInventory - an object, not BL2's 30-slot array (WillowGame.u, offline). What it is:
# 1. every machine: ShopType, CommerceMarkup, FeaturedItem, its definition's names; ShopInventory's class and fields,
#    and of what it holds (an array / a chain of inventory: the first items' class, name, price fields);
# 2. the shops' timer: WorldInfo.Game.SecondsUntilShopsReset / LastShopResetTime, the GRI's shop fields;
# 3. the vending menu's titles: VendingMachineGFxMovie's default object (PersonOrShopLabels...).
# Properties only. Writes tools/probes/probe_bl1_vending.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_vending.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_vending.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_vending.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:10]) + "]"
    if hasattr(value, "_type"):
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


SKIP = ("VfTable", "Components", "AllComponents", "Timers", "Touching", "Children", "Attached", "Net", "Collision", "Draw",
        "Rotation", "Physics", "Role", "Remote", "Tick", "Detach", "PrePivot", "Custom", "Replicated", "Last", "Latent")


def _fields(obj, limit: int = 3000) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if f.Class.Name.endswith("Property") and not str(f.Name).startswith(SKIP) and not str(f.Name).startswith("b"):
            value = _brief(_try(lambda f=f: obj._get_field(f)))
            if value not in ("None", "0", "0.00", "''", "[0: ]"):
                out.append(f"{f.Name}={value[:250]}")
    return ", ".join(out)[:limit]


def _item(inv) -> str:  # noqa: ANN001
    return (f"{_brief(inv)} ItemName {_brief(_try(lambda: inv.ItemName))}, "
            f"MonetaryValue {_brief(_try(lambda: inv.MonetaryValue))}, RarityLevel {_brief(_try(lambda: inv.RarityLevel))}, "
            f"Quantity {_brief(_try(lambda: inv.Quantity))}, definition {_brief(_try(lambda: inv.DefinitionData.ItemDefinition) or _try(lambda: inv.DefinitionData.WeaponTypeDefinition))}")


# 1. the machines
machines = [m for m in _try(lambda: list(unrealsdk.find_all("WillowVendingMachine", exact=False)), []) or []
            if not str(m.Name).startswith("Default__")]
lines.append(f"== machines: {len(machines)}")
for m in machines:
    lines.append(f"-- {m._path_name()} ({m.Class.Name}, super {_try(lambda m=m: m.Class.SuperField.Name)}): ShopType "
                 f"{_brief(_try(lambda m=m: m.ShopType))}, CommerceMarkup {_brief(_try(lambda m=m: m.CommerceMarkup))}, "
                 f"InventoryConfigurationName {_brief(_try(lambda m=m: m.InventoryConfigurationName))}")
    definition = _try(lambda m=m: m.InteractiveObjectDefinition, None)
    lines.append(f"   definition {_brief(definition)}: "
                 + (_fields(definition, 800) if definition is not None and not isinstance(definition, str) else ""))
    featured = _try(lambda m=m: m.FeaturedItem, None)
    lines.append(f"   FeaturedItem: {_item(featured) if featured is not None and not isinstance(featured, str) else _brief(featured)}")
    shop = _try(lambda m=m: m.ShopInventory, None)
    lines.append(f"   ShopInventory: {_brief(shop)}")
    if shop is not None and not isinstance(shop, str):
        lines.append(f"   its fields: {_fields(shop)}")
        for name in ("InventoryChain", "ItemChain", "Inventory", "Items", "InventoryList", "Backpack", "Contents"):
            value = _try(lambda n=name, s=shop: getattr(s, n), None)
            if value is None or isinstance(value, str):
                continue
            lines.append(f"   .{name}: {_brief(value)[:400]}")
            first = next(iter(value), None) if hasattr(value, "__len__") and not hasattr(value, "Class") else value
            n = 0
            while first is not None and n < 6:  # an array's first items, or a chain's (Inventory.Inventory)
                lines.append(f"     item {_item(first)}")
                first = _try(lambda f=first: f.Inventory, None) if hasattr(value, "Class") else None
                n += 1
    owned = [i for i in _try(lambda: list(unrealsdk.find_all("WillowInventory", exact=False)), []) or []
             if _try(lambda i=i, m=m: i.Owner == m or i.Owner == shop, False)]
    lines.append(f"   inventory objects owned by it / its ShopInventory: {len(owned)}")
    for inv in owned[:8]:
        lines.append(f"     {_item(inv)}")
    _flush()

# 2. the timer
wi = _try(lambda: __import__("mods_base").ENGINE.GetCurrentWorldInfo(), None)
game = _try(lambda: wi.Game, None)
lines.append(f"== timer: Game {_brief(game)}: SecondsUntilShopsReset {_brief(_try(lambda: game.SecondsUntilShopsReset))}, "
             f"LastShopResetTime {_brief(_try(lambda: game.LastShopResetTime))}, ShopTimerRate {_brief(_try(lambda: game.ShopTimerRate))}")
gri = _try(lambda: wi.GRI, None)
lines.append(f"   GRI: " + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: gri._get_field(f)))}" for f in (_try(lambda: list(gri.Class._fields()), []) or [])
                                     if "shop" in str(f.Name).lower()))
_flush()

# 3. the vending menu's titles
movie = _try(lambda: unrealsdk.find_class("VendingMachineGFxMovie").ClassDefaultObject, None)
lines.append(f"== VendingMachineGFxMovie default: PersonOrShopLabels {_brief(_try(lambda: movie.PersonOrShopLabels))[:600]}, "
             f"ItemOfTheDayLabel {_brief(_try(lambda: movie.ItemOfTheDayLabel))}")
lines.append("== done")
_flush()
print(f"probe_bl1_vending: written to {OUT}")
