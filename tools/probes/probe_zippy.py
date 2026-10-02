# Dev probe (in game), instant: where the item card's type / element icons come from for non-weapons (shields,
# grenade mods, class mods, relics). Equip a few (and carry some in the backpack).
# Per item: its class, name, then a few NAMED calls only (no pattern calls - probes-no-blind-calls), each written
# before it runs (a crash leaves the last line: the culprit):
#  - IItemCardable.GetZippyFrame() -> str   (the type icon's frame? compare a weapon's with its
#    WeaponTypeDefinition.ScaleformFrameName)
#  - IItemCardable.GetElementalFrame() -> str
#  - WillowClassMod.GetClassModIconLabel(out FrameLabel) -> bool   (class mods only)
#  - WillowItem.GetRainGrenadeIcon(out RainGrenadeFrame) -> str   (grenade mods only)
# plus properties: ShieldDef.ShieldTypeFlashFrameName / PrimedFlashFrameName (shields), the grenade's
# projectile's FlashIconName, the definition's ManufacturerDefinition.FlashLabelName.
# Writes tools/probes/probe_zippy.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_zippy.py").read())
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_zippy.txt"  # the repo, through the mod's junction
lines: list[str] = []


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _step(label: str, fn) -> None:  # noqa: ANN001
    lines.append(f"   {label} ...")
    _flush()
    lines[-1] = f"   {label} = {_try(fn)!r}"
    _flush()


def _item(inv, where: str) -> None:  # noqa: ANN001
    cls = _try(lambda: inv.Class.Name)
    lines.append(f"== {where}: {cls} {_try(lambda: inv.GetShortHumanReadableName())!r}")
    _flush()
    data = _try(lambda: inv.DefinitionData, None)
    _step("manufacturer FlashLabelName", lambda: str(data.ManufacturerDefinition.FlashLabelName))
    if cls == "WillowWeapon":
        _step("WeaponTypeDefinition.ScaleformFrameName", lambda: str(data.WeaponTypeDefinition.ScaleformFrameName))
    _step("ElementalFrame (property)", lambda: str(inv.ElementalFrame))
    if cls == "WillowShield":
        _step("ShieldDef.ShieldTypeFlashFrameName", lambda: str(inv.ShieldDef.ShieldTypeFlashFrameName))
        _step("ShieldDef.PrimedFlashFrameName", lambda: str(inv.ShieldDef.PrimedFlashFrameName))
    if cls == "WillowGrenadeMod":
        _step("DefaultProjectileDefinition.FlashIconName",
              lambda: str(inv.DefinitionData.ItemDefinition.DefaultProjectileDefinition.FlashIconName))
    _step("GetZippyFrame()", lambda: inv.GetZippyFrame())
    _step("GetElementalFrame()", lambda: inv.GetElementalFrame())
    if cls == "WillowClassMod":
        _step("GetClassModIconLabel()", lambda: inv.GetClassModIconLabel())
    if cls == "WillowGrenadeMod":
        _step("GetRainGrenadeIcon()", lambda: inv.GetRainGrenadeIcon())


def main() -> None:
    pawn = get_pc().Pawn
    inv_manager = pawn.InvManager
    seen = set()
    for chain, where in ((inv_manager.InventoryChain, "equipped weapon"), (inv_manager.ItemChain, "equipped item")):
        inv = chain
        while inv is not None and id(inv) not in seen and len(seen) < 20:
            seen.add(id(inv))
            _item(inv, where)
            inv = _try(lambda i=inv: i.Inventory, None)
    for inv in list(_try(lambda: list(inv_manager.Backpack), []))[:12]:
        _item(inv, "backpack")
    lines.append("done")
    _flush()


main()
