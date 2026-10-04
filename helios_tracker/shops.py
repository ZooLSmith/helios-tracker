"""
Vending machines: every machine's stock, its item of the day and their prices, and the shops' restock timer - the
page's Shops pane (the `shops` payload).

Game thread only (the collector calls read() every SHOPS_EVERY). Seen in game (tools/probes/probe_vending.txt, .agent/notes.md
"Vending machines"; Sanctuary, solo host):
- each machine (WillowVendingMachine) has its own stock: `ShopInventory`, a fixed 30-slot array (the items, then
  None), and `FeaturedItem` (the item of the day); every item a distinct inventory object owned by it;
- `GetSellingPriceForInventory(item, controller, quantity)` gives the price the menu asks;
- the timer is the game's, not a machine's: `WorldInfo.Game.SecondsUntilShopsReset` (the host), replicated as
  `GRI.SecondsUntilShopsReset` (a co-op client: whether the stock reaches one isn't known yet), counting down at
  `ShopTimerRate` from GlobalsDefinition.MinutesBetweenShopResets (20 min) since the level loaded;
- Crazy Earl (WillowVendingMachineBlackMarket) has no stock until a player opens him (built per player): left out
  (the user's call - only his map marker, the objects layer's).
The machines' names: what the game's map shows on hover - the machine's InteractiveObjectDefinition's
StatusMenuMapInfoBoxHeader (the Pre-Sequel's "Bullets Etc.", "Nina's Nursing"; BL2's "Ammo Dump Vending Machine",
"Zed's Meds Machine" - GD_Balance_Shopping.VendingMachines.*, cooked into the levels), else the vending menu's
titles (VendingMachineExGFxMovie's localized WeaponsShopTitle...: "Marcus Munitions" - the Pre-Sequel's
HealthShopTitle still says BL2's "Dr. Zed's Meds"). The game's text either way.
"""

import json
import time
from typing import Any

import unrealsdk
from unrealsdk.unreal import WeakPointer

from .inspector import _item
from . import games
from .util import addr, def_name, field, item_name, log_error, named, try_

KINDS = {"SType_Weapons": "weapons", "SType_Items": "items", "SType_Health": "health", "SType_BlackMarket": "blackmarket"}
TITLES = {"weapons": "WeaponsShopTitle", "items": "ItemsShopTitle", "health": "HealthShopTitle"}
LEFT_OUT = ("blackmarket",)  # Crazy Earl: nothing to list (his stock is per player, made when opened)
CURRENCIES = {"CURRENCY_Credits": "cash", "CURRENCY_Eridium": "eridium"}
BUILD_SECONDS = 0.003  # per pass, building new item records (a level's first pass has ~70: one hitch otherwise)
TIMER_DRIFT = 1.0  # s: the page's countdown this far from the game's - sent again
ALWAYS_SOLD = ("ammo", "health")  # every machine always has them (ammo, health vials): a price list, not item cards


def _enum_name(value: Any) -> str:
    return str(getattr(value, "name", value) or "")


def is_machine(obj: Any) -> bool:
    cls = try_(lambda: obj.Class)
    while cls is not None:
        if str(try_(lambda c=cls: c.Name, "")) == games.GAME.vending_class:  # (each game's: games.py)
            return True
        cls = try_(lambda c=cls: c.SuperField)  # (never raises: the collector's object scan calls it on everything)
    return False


class ShopReader:
    """The level's vending machines (from the collector's object scan and spawn hook) and what they sell."""

    def __init__(self) -> None:
        self._machines: dict[tuple[int, str], WeakPointer] = {}
        self._machine_classes: dict[int, bool] = {}  # class address -> a vending machine's (the reader: one per level)
        # item records by (address, name): an item never changes while it's for sale (sold / restocked: a new object)
        self._items: dict[tuple[int, str], dict[str, Any]] = {}
        self._titles: dict[str, str] | None = None
        # (stock json, seconds left, rate, when: the collector's clock, the game paused)
        self._sent: tuple[str, float, float, float, bool] | None = None
        self.pending = False  # item records left to build: read again soon

    def note(self, io: Any) -> None:
        # (per class, once a level: is_machine walks the class chain - every object of every full scan, 3-14 ms)
        cls_key = try_(lambda: io.Class._get_address())
        if (machine := self._machine_classes.get(cls_key)) is None:
            machine = is_machine(io)
            if cls_key is not None:
                self._machine_classes[cls_key] = machine
        if machine:
            self._machines[(io._get_address(), str(io.Name))] = WeakPointer(io)

    def forget(self, key: tuple[int, str]) -> None:
        self._machines.pop(key, None)

    def resend(self) -> None:
        self._sent = None

    def _title(self, kind: str) -> str:
        if self._titles is None:  # the vending menu's localized titles (static; games.py: its class, if it has them)
            title_class = games.GAME.vending_titles
            cls = try_(lambda: unrealsdk.find_class(title_class)) if title_class else None
            cdo = try_(lambda: cls.ClassDefaultObject) if cls is not None else None
            self._titles = {k: str(try_(lambda f=f: getattr(cdo, f), "") or "") for k, f in TITLES.items()} if cdo is not None else {}
        return self._titles.get(kind, "")

    def _named(self, io: Any, kind: str) -> dict[str, Any]:
        """A machine's name record (util.named): the game's (_name) - else its definition's own name, as the map object's
        ("VendingMachine GrenadesAndAmmo": what it sells - BL1's machines have no map header, no shop titles; their name
        is on their texture only), not its class's (every machine "Vending Machine ?" - the user)."""
        return named(self._name(io, kind), def_name(try_(lambda: io.InteractiveObjectDefinition)), str(io.Class.Name))

    def _name(self, io: Any, kind: str) -> str:
        """A machine's name: its map hover's (its definition's StatusMenuMapInfoBoxHeader), else its menu's title."""
        return try_(lambda: str(io.InteractiveObjectDefinition.StatusMenuMapInfoBoxHeader), "") or self._title(kind)

    def _record(self, inv: Any, machine: Any, pc: Any, deadline: float) -> dict[str, Any] | None:
        """An item's record (inspector.py's, as in a backpack) with the machine's price as its value ("v"), or None
        if it isn't built yet and this pass has no time left."""
        key = (inv._get_address(), str(inv.Name))
        if key not in self._items:
            if time.perf_counter() > deadline:
                return None
            item = _item(inv, False, pc)
            price = try_(lambda: games.GAME.shops.selling_price(machine, inv, pc))  # (each game's call: games.py)
            if price is not None and price >= 0:
                item["v"] = price
            self._items[key] = item
        return self._items[key]

    def _basic(self, inv: Any, kind: str, machine: Any, pc: Any) -> dict[str, Any]:
        """An always-sold item (ammo, a health vial): its name, kind and the machine's price only - cheap, no card."""
        key = (inv._get_address(), str(inv.Name))
        if key not in self._items:
            record = {**named(item_name(inv), str(inv.Name)), "k": kind}
            price = try_(lambda: games.GAME.shops.selling_price(machine, inv, pc))  # (each game's call: games.py)
            if price is not None and price >= 0:
                record["v"] = price
            self._items[key] = record
        return self._items[key]

    def read(self, world_info: Any, pc: Any, level_id: int, client: bool, now: float) -> tuple[str | None, str | None]:
        """(the machines' JSON when their stock changed, the timer's JSON when it drifted from the page's count) -
        None for what's unchanged, or not complete yet (records left to build: `pending`, the next pass). `now`: the
        collector's clock (s)."""
        deadline = time.perf_counter() + BUILD_SECONDS
        machines, seen, complete = [], set(), True
        for key, ptr in list(self._machines.items()):
            io = ptr()
            if io is None or try_(lambda io=io: io.bDeleteMe, False):
                del self._machines[key]
                continue
            try:
                kind = KINDS.get(_enum_name(try_(lambda io=io: io.ShopType)), "other")
                if kind in LEFT_OUT:
                    continue
                loc = io.Location
                machine: dict[str, Any] = {"i": addr(io), **self._named(io, kind), "k": kind,
                                           "x": round(loc.X), "y": round(loc.Y), "z": round(loc.Z)}
                currency = CURRENCIES.get(try_(lambda io=io: games.GAME.shops.currency(io), "") or "", "other")  # (games.py)
                if currency != "cash":
                    machine["cur"] = currency
                items, basics = [], []
                for inv in try_(lambda io=io: list(io.ShopInventory), []) or []:
                    if inv is None:
                        continue
                    seen.add((inv._get_address(), str(inv.Name)))
                    if (always := games.GAME.items.pickup_kind(inv)) in ALWAYS_SOLD:
                        basics.append(self._basic(inv, always, io, pc))
                        continue
                    if (record := self._record(inv, io, pc, deadline)) is None:
                        complete = False
                        break
                    items.append(record)
                machine["items"] = items
                if basics:
                    machine["basics"] = basics
                featured = try_(lambda io=io: io.FeaturedItem)
                if featured is not None and games.GAME.items.pickup_kind(featured) not in ALWAYS_SOLD:
                    seen.add((featured._get_address(), str(featured.Name)))
                    if (record := self._record(featured, io, pc, deadline)) is None:
                        complete = False
                    else:
                        machine["feat"] = record
                machines.append(machine)
            except Exception as ex:  # noqa: BLE001
                log_error("vending machine", ex)
            if not complete:
                break
        self.pending = not complete
        if not complete:
            return None, None
        for key in [k for k in self._items if k not in seen]:  # sold / restocked
            del self._items[key]
        machines.sort(key=lambda m: m["i"])
        stock = json.dumps({"level": level_id, "client": int(client), "machines": machines}, separators=(",", ":"))
        # the timer: the game's count (games.py shop_timer_source - BL2's host: its own, a client: the replicated one)
        source = try_(lambda: games.GAME.shops.timer_source(world_info))
        left = try_(lambda: float(source.SecondsUntilShopsReset))
        rate = try_(lambda: float(source.ShopTimerRate), 1.0)
        # the game paused (WorldInfo.Pauser, as the state's "paused"): its timer stands still - the page's count too
        # (it went on, then jumped back at each resend: the user saw it)
        # (Pauser only, not games.py world_paused: BL1's status menus stop the world, but its shops' timer runs on -
        # the user saw it count down in the inventory, not in the escape menu)
        paused = try_(lambda: field(world_info, "Pauser") is not None, False)
        sent = self._sent
        stock_out = stock if sent is None or stock != sent[0] else None
        timer_out = None
        # where the page's count is now: what was sent, counted down since unless paused then
        expected = None if sent is None else sent[1] if sent[4] else sent[1] - (now - sent[3]) * sent[2]
        # (a restock: new stock and the timer back up - both sent together; a pause / its end: sent at once)
        if left is not None and (stock_out is not None or sent is None or rate != sent[2] or paused != sent[4]
                                 or abs(expected - left) > TIMER_DRIFT):
            timer_out = json.dumps({"level": level_id, "left": round(left, 1), "rate": rate, **({"paused": 1} if paused else {})},
                                   separators=(",", ":"))
            self._sent = (stock, left, rate, now, paused)
        elif stock_out is not None:
            self._sent = (stock, *sent[1:]) if sent is not None else (stock, 0.0, 1.0, now, False)
        return stock_out, timer_out
