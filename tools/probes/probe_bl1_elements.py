# Dev probe (in game), instant: Borderlands 1's item card element icons - its card movie's frames "corr0".."shock4",
# "exp0".."fire4", "none" (inworld_ui.upk weapon_card, sprite 98: the element and its tech level, drawn "x2", "x4"...).
# No ElementalFrame (BL2's). Script (WillowGame.u, offline): WillowItem.GetTechIconFrame (its instance data's unions),
# WillowItem.CalculateItemTechLevel (its parts' TechLevelIncrease), WillowWeapon.StaticCalculateWeaponTechLevelForUI /
# StaticGetWeaponDamageType (the definition data). For each of the player's items (equipped, backpack):
# 1. its class, name; those functions' signatures (each parameter's flags: out / return);
# 2. the calls: GetTechIconFrame / CalculateItemTechLevel when they take no input, the weapons' static ones with
#    their DefinitionData; its fields with "tech" / "element" / "damage" in their name.
# Writes tools/probes/probe_bl1_elements.txt (appends), after each item.
#   py exec(open(r"<repo>\tools\probes\probe_bl1_elements.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_elements.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_elements.txt"
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


def _enum(value) -> str:  # noqa: ANN001
    return f"{value.name} ({int(value)})" if isinstance(value, Enum) else repr(value)


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
pawn = _try(lambda: pc.Pawn, None)
inv_manager = _try(lambda: pawn.InvManager, None)
items = []
for getter in (lambda: inv_manager.InventoryChain, lambda: inv_manager.ItemChain):
    item = _try(getter, None)
    while item is not None and not isinstance(item, str) and len(items) < 40:
        items.append(item)
        item = _try(lambda i=item: i.Inventory, None)
items += list(_try(lambda: list(inv_manager.Backpack), []) or [])
# the vending machines' stock too (their item of the day, their ShopInventory - shops.py's), the level's
import unrealsdk  # noqa: E402

for machine in _try(lambda: list(unrealsdk.find_all("WillowVendingMachine", exact=False)), []) or []:
    if _try(lambda m=machine: m._path_name(), "").startswith("Default__") or "Default__" in str(_try(lambda m=machine: m.Name, "")):
        continue
    for stocked in [_try(lambda m=machine: m.FeaturedItem, None), *(_try(lambda m=machine: list(m.ShopInventory), []) or [])]:
        if stocked is not None and not isinstance(stocked, str) and stocked not in items:
            items.append(stocked)


def _signature(obj, name):  # noqa: ANN001, ANN202
    fn = _try(lambda: obj.Class._find(name), None)
    if fn is None or isinstance(fn, str):
        return None, f"{name}: <none>"
    params = []
    for p in _try(lambda: list(fn._fields()), []) or []:
        flags = int(_try(lambda p=p: p.PropertyFlags, 0) or 0)
        params.append((str(p.Name), flags & 0x80 != 0, flags & 0x100 != 0, flags & 0x400 != 0))  # (parm, out, return)
    text = ", ".join(f"{n}{' out' if out else ''}{' ret' if ret else ''}" for n, parm, out, ret in params if parm or out or ret)
    takes_input = any(parm and not out and not ret for n, parm, out, ret in params)
    return takes_input, f"{name}({text})"


lines.append(f"== {len(items)} items")
_flush()
for item in items:
    cls = str(_try(lambda: item.Class.Name))
    lines.append(f"-- {cls} {_try(lambda: item.GetShortHumanReadableName())!r}")
    for fname in ("GetTechIconFrame", "CalculateItemTechLevel", "StaticCalculateWeaponTechLevelForUI", "StaticGetWeaponDamageType"):
        takes_input, sig = _signature(item, fname)
        lines.append(f"   {sig}")
        if takes_input is None:
            continue
        if fname.startswith("Static"):  # (the weapon's own data: their one input - WillowGame.u, offline)
            result = _try(lambda f=fname: getattr(item, f)(item.DefinitionData))
            lines.append(f"     (DefinitionData) -> {getattr(result, '_path_name', lambda: result)()!r}")
            if fname == "StaticGetWeaponDamageType" and result is not None and not isinstance(result, str):
                lines.append(f"     DamageType {_enum(_try(lambda: result.DamageType))}, IconU {_try(lambda: result.IconU)}, "
                             f"IconV {_try(lambda: result.IconV)}, DamageColor {_try(lambda: result.DamageColor)}")
        else:
            lines.append(f"     -> {_try(lambda f=fname: getattr(item, f)())!r}")
    own = []
    for f in _try(lambda: list(item.Class._fields()), []) or []:
        name = str(f.Name)
        if f.Class.Name.endswith("Property") and any(k in name.lower() for k in ("tech", "element", "damagetype", "instancedata")):
            own.append(f"{name}={str(_try(lambda f=f: item._get_field(f)))[:300]}")
    lines.append("   fields: " + "; ".join(own))
    _flush()
