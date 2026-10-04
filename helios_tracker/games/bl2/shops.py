"""Borderlands 2's shops (the base: every game's unless its profile has its own) - Vending machines: their prices, currency, restock timer."""

from typing import Any

from ..base import Part


class Shops(Part):
    """Vending machines: their prices, currency, restock timer."""

    def selling_price(self, machine: Any, inv: Any, pc: Any) -> int:
        """What a vending machine asks for one of an item (the price its menu shows): GetSellingPriceForInventory(item,
        controller, quantity) - scaled to the player."""
        return int(machine.GetSellingPriceForInventory(inv, pc, 1))

    def timer_source(self, world_info: Any) -> Any:
        """What the shops' restock timer is read from (SecondsUntilShopsReset, ShopTimerRate): the host's own count
        (WorldInfo.Game), else the replicated one (a co-op client: GRI)."""
        return world_info.Game if world_info.Game is not None else world_info.GRI

    def currency(self, machine: Any) -> str:
        """What a vending machine's prices are in, its enum's name (shops.py CURRENCIES: CURRENCY_Credits...):
        FormOfCurrency (Crazy Earl's: eridium)."""
        return str(getattr(machine.FormOfCurrency, "name", machine.FormOfCurrency))
