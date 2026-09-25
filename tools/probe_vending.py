# Dev probe (in game), read-only (calls only GetSellingPriceForInventory), instant: vending machines - what each one holds, and the shops' timer.
# Offline (WillowGame.upk / Startup.upk) we found:
#  - every WillowVendingMachine actor has its own ShopInventory, FeaturedItem (+ FeaturedItemPickup, the
#    one shown in the glass), LastInventoryResetTime, InventoryConfigurationName / FeaturedItemConfigurationName;
#    WillowVendingMachineBlackMarket (Crazy Earl) builds its items per player instead;
#  - the timer is global: WillowGameInfo.LastShopResetTime / SecondsUntilShopsReset / ShopTimerRate (host
#    only), replicated as WillowGameReplicationInfo.SecondsUntilShopsReset / ShopTimerRate (clients too);
#    GlobalsDefinition.MinutesBetweenShopResets = 20 (class default, GD_Globals.General.Globals keeps it).
# To check: are two machines' items distinct objects, does the reset change every machine at once, what a
# client sees. Run it, wait a minute (buy something?), run again; again after the timer hits 0; as a client.
# Writes tools/probe_vending.txt (appends, a section at a time)
#   py exec(open(r"<repo>\tools\probe_vending.py").read())
import math
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_vending.txt"  # the repo, through the mod's junction
lines: list[str] = []


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, (str, bytes, int, float, bool)):
        name = getattr(value, "name", None)  # game enums are int-based: show their name
        if name:
            return str(name)
        return f"{value:.2f}" if isinstance(value, float) else repr(value)
    if depth > 4:
        return f"<{type(value).__name__}>"
    if type(value).__name__ == "WrappedArray":
        items = [_brief(v, depth + 1) for v in list(value)[:12]]
        return "[" + ", ".join(items) + (f", ... ({len(value)} total)" if len(value) > 12 else "") + "]"
    if hasattr(value, "_type"):  # WrappedStruct
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    return f"<{type(value).__name__}: {str(value)[:80]}>"


def _fields(obj, indent: str, stop=("Actor", "Object"), skip_empty: bool = True) -> None:  # noqa: ANN001
    c, seen = obj.Class, set()
    while c is not None and c.Name not in stop:
        for f in c._fields():
            kind = f.Class.Name
            if f.Name in seen or not kind.endswith("Property") or kind == "DelegateProperty" or "VfTable" in f.Name:
                continue
            seen.add(f.Name)
            text = _brief(_try(lambda f=f: obj._get_field(f)))
            if skip_empty and text in ("None", "0", "0.00", "False", "''", "[]", "'None'"):
                continue
            lines.append(f"{indent}{c.Name}.{f.Name} = {text[:900]}")
        c = c.SuperField


def _signatures(cls, indent: str) -> None:  # noqa: ANN001
    for f in cls._fields():
        if f.Class.Name == "Function":
            params = [f"{p.Class.Name.replace('Property', '')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
            lines.append(f"{indent}{cls.Name}.{f.Name}({', '.join(params)})")


def _item(inv) -> str:  # noqa: ANN001
    if inv is None:
        return "None"
    name = _try(lambda: inv.GetShortHumanReadableName())
    dd = _try(lambda: inv.DefinitionData, None)
    balance = _try(lambda: dd.BalanceDefinition, None) if dd is not None else None
    level = _try(lambda: dd.ManufacturerGradeIndex, "?") if dd is not None else "?"
    return (f"{inv.Class.Name} {inv.Name} {name!r} rarity={_try(lambda: inv.RarityLevel)} level={level} "
            f"qty={_try(lambda: inv.Quantity, '?')} balance={_brief(balance)} owner={_brief(_try(lambda: inv.Owner, None))}")


pc = get_pc()
world = ENGINE.GetCurrentWorldInfo()
here = pc.Pawn.Location
lines.append("#" * 70)
lines.append(f"# {time.strftime('%H:%M:%S')}  map={_try(lambda: world.GetStreamingPersistentMapName())}  "
             f"TimeSeconds={_try(lambda: world.TimeSeconds)}  RealTimeSeconds={_try(lambda: world.RealTimeSeconds)}  "
             f"NetMode={_brief(_try(lambda: world.NetMode))}")

lines.append("== timer")
gri = _try(lambda: world.GRI, None)
lines.append(f"   GRI = {_brief(gri)}")
if gri is not None:
    for n in ("SecondsUntilShopsReset", "ShopTimerRate"):
        lines.append(f"   GRI.{n} = {_brief(_try(lambda n=n: getattr(gri, n)))}")
game = _try(lambda: world.Game, None)
lines.append(f"   Game = {_brief(game)}  (None on a client)")
if game is not None:
    for n in ("LastShopResetTime", "SecondsUntilShopsReset", "SecondsUntilShopTimerResend", "ShopTimerRate",
              "ShopTimerRateBaseValue", "ShopTimerRateModifierStack", "NewShopInventory", "NewShopInventoryDisplayTime"):
        lines.append(f"   Game.{n} = {_brief(_try(lambda n=n: getattr(game, n)))}")
globals_def = _try(lambda: unrealsdk.find_object("GlobalsDefinition", "GD_Globals.General.Globals"), None)
lines.append(f"   Globals.MinutesBetweenShopResets = {_brief(_try(lambda: globals_def.MinutesBetweenShopResets))}  "
             f"ShopResetCost = {_brief(_try(lambda: globals_def.ShopResetCost))}")
lines.append(f"   pc.bIsShopping = {_brief(_try(lambda: pc.bIsShopping))}  ActiveShop = {_brief(_try(lambda: pc.ActiveShop))}")
_flush()

machines = [m for m in unrealsdk.find_all("WillowVendingMachineBase", exact=False)
            if not m.Name.startswith("Default__") and m.Outer is not None and m.Outer.Class.Name == "Level"]
machines.sort(key=lambda m: _try(lambda: math.dist((m.Location.X, m.Location.Y), (here.X, here.Y)), 1e12))
lines.append(f"== {len(machines)} machines (closest first)")
owners: dict[str, list[str]] = {}  # item object -> machines holding it: distinct per machine or shared?
for m in machines:
    dist = _try(lambda m=m: math.dist((m.Location.X, m.Location.Y, m.Location.Z), (here.X, here.Y, here.Z)) / 100, -1)
    lines.append(f"-- {m.Class.Name} {m.Name}  {dist:.0f} m  at ({m.Location.X:.0f}, {m.Location.Y:.0f}, {m.Location.Z:.0f})")
    lines.append(f"   def = {_brief(_try(lambda m=m: m.InteractiveObjectDefinition, None))}  "
                 f"hidden={_brief(_try(lambda m=m: m.bHidden))}  mesh hidden={_brief(_try(lambda m=m: m.ObjectMesh.HiddenGame))}  "
                 f"canBeUsed={_brief(_try(lambda m=m: tuple(m.bCanBeUsed)))}  collide={_brief(_try(lambda m=m: m.bCollideActors))}  "
                 f"deleteMe={_brief(_try(lambda m=m: m.bDeleteMe))}  created={_brief(_try(lambda m=m: m.CreationTime))}")
    for n in ("ShopType", "FormOfCurrency", "LastInventoryResetTime", "InventoryConfigurationName",
              "FeaturedItemConfigurationName", "FixedItemCost", "FixedFeaturedItemCost", "bOverrideFormOfCurrency"):
        lines.append(f"   {n} = {_brief(_try(lambda m=m, n=n: getattr(m, n), '-'))}")
    featured = _try(lambda m=m: m.FeaturedItem, None)
    featured_price = _try(lambda m=m: m.GetSellingPriceForInventory(featured, pc, 1)) if featured is not None else ""
    lines.append(f"   FeaturedItem = {_item(featured)}  price={featured_price}")
    lines.append(f"   FeaturedItemPickup = {_brief(_try(lambda m=m: m.FeaturedItemPickup, None))}")
    inventory = _try(lambda m=m: list(m.ShopInventory), [])
    lines.append(f"   ShopInventory: {len(inventory) if isinstance(inventory, list) else inventory}")
    for inv in inventory if isinstance(inventory, list) else []:
        # the one function called: the price, (InventoryForSale, WPC, Quantity) -> int, signature from the last run
        price = _try(lambda m=m, inv=inv: m.GetSellingPriceForInventory(inv, pc, 1)) if inv is not None else ""
        lines.append(f"      {_item(inv)}  price={price}")
        if inv is not None:
            owners.setdefault(inv.Name, []).append(m.Name)
    _flush()
shared = {k: v for k, v in owners.items() if len(v) > 1}
lines.append(f"== items held by several machines: {shared or 'none'}")
_flush()

if machines:
    lines.append(f"== all non-empty fields of {machines[0].Name}")
    _fields(machines[0], "   ")
    _flush()
    lines.append("== function signatures (not called)")
    for cls_name in ("WillowVendingMachineBase", "WillowVendingMachine", "WillowVendingMachineBlackMarket"):
        cls = _try(lambda c=cls_name: unrealsdk.find_class(c), None)
        if cls is not None:
            _signatures(cls, "   ")
    _flush()
print(f"[probe_vending] {len(machines)} machines -> {OUT}")
