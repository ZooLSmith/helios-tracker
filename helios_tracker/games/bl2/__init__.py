"""Borderlands 2: the reference - what the mod was built on. Its parts (this folder) are every game's unless the game's
profile has its own."""

from .. import CHALLENGES, DISCOVERY, profile
from ..base import Profile
from .assets import Assets
from .items import Items
from .missions import Missions
from .objects import Objects
from .pawns import Pawns
from .shops import Shops
from .skills import Skills
from .ui import Ui
from .world import World


@profile("BL2")
class Borderlands2(Profile):
    """Borderlands 2: the reference - what the mod was built on."""

    PARTS = {"world": World, "missions": Missions, "items": Items, "objects": Objects, "pawns": Pawns, "shops": Shops,
             "skills": Skills, "assets": Assets, "ui": Ui}

    key = "bl2"  # the page's name for it (the level message's "game": its label variants, its own data - game.js)
    packages = "CookedPCConsole"  # WillowGame/<this>: its cooked packages, the folder the mod reads (None: none read)
    exe_depth = 2  # the game's folder: this many up from its executable's (Binaries/Win32/Borderlands2.exe)
    gibbed_prefix = "BL2"  # a gear's code for Gibbed's save editor: "BL2(...)" ("": no editor)
    vending_class = "WillowVendingMachineBase"  # what a vending machine is (shops.py: the class or a superclass)
    # a function the game calls every frame, for the updater's one-shot reload (__init__.RELOAD_HOOK: not from inside
    # the mod's own PostRender hook, which the reload removes)
    tick_function = "WillowGame.WillowGameViewportClient:Tick"
    vending_titles = "VendingMachineExGFxMovie"  # the vending menu, its default object's shop titles (None: none)
    # the item kinds whose card stats are the game's list (WillowItem.UIStatModifiers: inspector._ui_stats) - BL2's other
    # kinds are worked out from their own properties (inspector._stats)
    ui_stat_kinds: frozenset[str] = frozenset({"shield"})
    # the attribute presentation a weapon card's damage is shown with (its rounding: inspector._presented) - None: a
    # whole number, rounded (BL2's cards, checked)
    damage_presentation: str | None = None
    features: frozenset[str] = frozenset({DISCOVERY, CHALLENGES})
