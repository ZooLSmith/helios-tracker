"""Borderlands 1's shops: what differs from Borderlands 2's (games/bl2/shops.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.shops import Shops


class Bl1Shops(Shops):
    """Borderlands 1's shops."""

    def selling_price(self, machine: Any, inv: Any, pc: Any) -> int:
        # GetSellingPriceForInventory(InventoryForSale, Quantity): no controller (WillowGame.u, offline) - BL2's call with
        # one failed (no price on the page)
        return int(machine.GetSellingPriceForInventory(inv, 1))

    def timer_source(self, world_info: Any) -> Any:
        # The replicated count, a whole number a little ahead of the host's (925 for its 922.85 - probe_bl1_vending.txt):
        # the game showed a few seconds more than the page reading the host's (the user)
        return world_info.GRI

    def currency(self, machine: Any) -> str:
        # no FormOfCurrency (one currency in the game): dollars - its prices showed bare numbers ("other")
        return "CURRENCY_Credits"
