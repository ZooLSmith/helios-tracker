"""Borderlands 1, the original 2009 game (the Enhanced edition's SDK didn't run: not registered) - .agent/bl1.md.
Borderlands 2's profile, its own parts where its way differs (this folder)."""

from .. import DISCOVERY, profile
from ..bl2 import Borderlands2
from .assets import Bl1Assets
from .items import Bl1Items
from .missions import Bl1Missions
from .objects import Bl1Objects
from .pawns import Bl1Pawns
from .shops import Bl1Shops
from .skills import Bl1Skills
from .ui import Bl1Ui
from .world import Bl1World


@profile("BL1")
class Borderlands1(Borderlands2):
    """Borderlands 1, the original 2009 game (the Enhanced edition's SDK didn't run: not registered) - .agent/bl1.md."""

    PARTS = {"world": Bl1World, "missions": Bl1Missions, "items": Bl1Items, "objects": Bl1Objects, "pawns": Bl1Pawns,
             "shops": Bl1Shops, "skills": Bl1Skills, "assets": Bl1Assets, "ui": Bl1Ui}

    key = "bl1"
    packages = "CookedPC"  # its packages: version 584 (BL2's 832) - read with upk_bl1.Bl1Package (its map: bl1map.py)
    exe_depth = 1  # Binaries/Borderlands.exe
    gibbed_prefix = ""
    # its machines: WillowVendingMachine, right under WillowInteractiveObject - BL2's stock as is (ShopInventory: 30
    # slots, FeaturedItem, ShopType, the game's SecondsUntilShopsReset; no ShopTimerRate) - tools/probes/probe_bl1_vending.txt
    vending_class = "WillowVendingMachine"
    # its WillowGameViewportClient has no Tick of its own (WillowGame.u, offline: PostRender only) - the engine's
    # (Engine.u's GameViewportClient:Tick): the updater's reload never ran there
    tick_function = "Engine.GameViewportClient:Tick"
    vending_titles = None  # its menu (VendingMachineGFxMovie): no shop titles (PersonOrShopLabels empty)
    # its equipped items: one class (WillowEquipAbleItem) - the shield's card stats in UIStatModifiers as BL2's (probe_bl1_pause:
    # ShieldMaxValue 50, ShieldOnIdleRegenerationRate 7.5); its grenade mods' and com decks': theirs too (the same class)
    ui_stat_kinds = frozenset({"shield", "grenade", "classmod"})
    # its card's damage: AttrPresent_WeaponDamage, ATTRROUNDING_IntCeil (gd_AttributePresentation, offline) - the GGN9's
    # 86 in game, 85 rounded (the user)
    damage_presentation = "gd_AttributePresentation.Weapons.AttrPresent_WeaponDamage"
    # no WorldDiscoveryArea class (the log: "Couldn't find class")
    features = Borderlands2.features - {DISCOVERY}
