# Dev probe (in game, Borderlands 1), instant: another player's gear on a co-op CLIENT. The game shows their gun in
# their hands; the mod's inspector shows no gear for them (inspector._inventory: no error logged - their InvManager not
# None with empty chains, or their pawn's Weapon None?). BL2 shows their equipped gear there (pawn.Weapon,
# HolsteredWeaponSlots, EquippedItems).
# Logs, per player pawn (ours and the others):
#  - its fields about weapons / inventory / items / equipment (their values: arrays in full);
#  - its InvManager: its fields about inventory / items / chains / weapons, its InventoryChain and ItemChain walked
#    (each item's class, name, definition);
#  - its Weapon (if any): class, name, definition data, owner, instigator;
#  - every WillowWeapon / WillowItem-like actor in the world whose Owner or Instigator is that pawn.
# Reads properties only (no function called). The output is written after each section.
# Run it in BL1 as a co-op CLIENT, the other player holding a gun.
# Writes tools/probes/probe_bl1_other_gear.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bl1_other_gear.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_other_gear.txt"  # the repo, through the mod's junction
FIELDS = re.compile(r"weapon|inv|item|equip|holster|slot|gear|artifact|shield|grenade|commdeck|classmod", re.I)
lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


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
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:40]) + "]"
    return repr(value)


def _fields(obj, pattern, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (pattern is None or pattern.search(str(f.Name))):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _item_line(inv) -> str:  # noqa: ANN001
    data = _try(lambda: inv.DefinitionData, None)
    definition = _try(lambda: data.WeaponTypeDefinition, None) or _try(lambda: data.ItemDefinition, None) \
        if data is not None and not isinstance(data, str) else None
    return (f"{_brief(inv)} owner={_brief(_try(lambda: inv.Owner))} instigator={_brief(_try(lambda: inv.Instigator))} "
            f"def={_brief(definition)} bDeleteMe={_try(lambda: inv.bDeleteMe)}")


def _chain(first, label: str) -> None:  # noqa: ANN001
    lines.append(f"   {label}:")
    inv, n = first, 0
    while inv is not None and not isinstance(inv, str) and n < 60:
        lines.append(f"      {_item_line(inv)}")
        inv, n = _try(lambda i=inv: i.Inventory, None), n + 1
    if n == 0:
        lines.append("      (empty)")


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    lines.append(f"map: {_try(lambda: wi.GetStreamingPersistentMapName())}  netmode: {_brief(_try(lambda: wi.NetMode))}  "
                 f"local pc: {_brief(pc)}  its pawn: {_brief(_try(lambda: pc.Pawn))}")
    _save()
    pawns = [p for p in _try(lambda: list(unrealsdk.find_all("WillowPlayerPawn", exact=False)), [])
             if not str(p.Name).startswith("Default__") and not p.bDeleteMe]
    lines.append(f"{len(pawns)} player pawns")
    _save()
    for pawn in pawns:
        pri = _try(lambda p=pawn: p.PlayerReplicationInfo, None)
        label = f"pawn {pawn.Name} ({_try(lambda: pri.PlayerName)}) controller={_brief(_try(lambda p=pawn: p.Controller))}"
        _fields(pawn, FIELDS, label)
        _save()
        mgr = _try(lambda p=pawn: p.InvManager, None)
        if mgr is None or isinstance(mgr, str):
            lines.append(f"== {pawn.Name}'s InvManager: {mgr}")
        else:
            _fields(mgr, re.compile(r"inv|item|chain|weapon|backpack|slot|equip", re.I), f"{pawn.Name}'s InvManager")
            _chain(_try(lambda: mgr.InventoryChain, None), "InventoryChain")
            _chain(_try(lambda: mgr.ItemChain, None), "ItemChain")
        _save()
        weapon = _try(lambda p=pawn: p.Weapon, None)
        lines.append(f"== {pawn.Name}'s Weapon: {_item_line(weapon) if weapon is not None and not isinstance(weapon, str) else weapon}")
        _save()
    # weapons / items in the world owned by a player pawn
    lines.append("== WillowWeapon / WillowItem / WillowEquipAbleItem actors owned by (or instigated by) a player pawn")
    addresses = {p._get_address(): p.Name for p in pawns}
    for cls in ("WillowWeapon", "WillowItem", "WillowEquipAbleItem"):
        for inv in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or []:
            if str(inv.Name).startswith("Default__"):
                continue
            owner = _try(lambda i=inv: i.Owner, None)
            instigator = _try(lambda i=inv: i.Instigator, None)
            mine = [addresses.get(o._get_address()) for o in (owner, instigator)
                    if o is not None and not isinstance(o, str) and o._get_address() in addresses]
            if mine:
                lines.append(f"   [{cls}] of {mine[0]}: {_item_line(inv)}")
        _save()


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
print(f"probe_bl1_other_gear: {len(lines)} lines -> {OUT}")
