"""Borderlands 2's items (the base: every game's unless its profile has its own) - Items and their cards: their kind, level, card frames, elements, stat lines, the rarity colours."""

from typing import Any

from ..base import Part

ITEM_KINDS = {  # class (or a superclass) -> kind shown by the page
    "WillowWeapon": "weapon",
    "WillowShield": "shield",
    "WillowGrenadeMod": "grenade",
    "WillowClassMod": "classmod",
    "WillowArtifact": "relic",
    "WillowMissionItem": "mission",
    "WillowUsableItem": "usable",
}
# A usable item's kind, by its definition's inventory card (Presentation): the game's own grouping
# (probe_pickups.py: GD_InventoryPresentations.Definitions.Credits / Health / WeaponAmmo_* / GrenadeAmmo)
PRESENTATION_KINDS = {"Credits": "cash", "Health": "health", "GrenadeAmmo": "ammo", "Oxygen": "oxygen"}
# ("Oxygen": the Pre-Sequel's Oxygen Canister - GD_BuffDrinks.A_Item.BuffDrink_OxygenInstant, presentation
# GD_InventoryPresentations.Definitions.Oxygen, icon fx_shared_items.Textures.OxygenCannister_Particle - Startup.upk)
# The "Credits" presentation is shared by every currency: the definition's FormOfCurrency tells them
# apart (seen in game, tools/probes/probe_eridium.py: GD_Currency.A_Item.EridiumStick = CURRENCY_Eridium).
# Other currencies (not seen yet: Seraph crystals, Torgue tokens...) stay "other".
CURRENCY_KINDS = {"CURRENCY_Credits": "cash", "CURRENCY_Eridium": "eridium"}


class Items(Part):
    """Items and their cards: their kind, level, card frames, elements, stat lines, the rarity colours."""

    def __init__(self, profile: Any) -> None:
        super().__init__(profile)
        # Per item definition (static game data, set when the item spawns - never changes): its pickup kind. Never
        # cleared; keyed by definition, not by pickup (a destroyed pickup's address can be reused).
        self._pickup_kinds: dict[int, str] = {}

    def kind(self, inv: Any) -> str:
        """An item's kind as the page shows it ("weapon", "shield", "grenade"...; "item" if nothing tells): its class
        or a superclass's (ITEM_KINDS)."""
        cls = inv.Class
        while cls is not None:
            if (kind := ITEM_KINDS.get(str(cls.Name))) is not None:
                return kind
            cls = cls.SuperField
        return "item"

    def pickup_kind(self, inv: Any) -> str:
        """ "ammo" / "cash" / "eridium" / "health" / "oxygen" for a usable item (a non-gear pickup), "mission" for a
        mission item (WillowMissionItem: ECHO logs, Princess Fluffybutt... - tools/probes/probe_pickups.txt), ""
        for anything else. Weapons / gear aren't looked at; each definition is resolved once (_usable_kind)."""
        from ...util import try_  # noqa: PLC0415

        if inv is None:
            return ""
        if inv.Class.Name == "WillowMissionItem":
            return "mission"
        if inv.Class.Name != "WillowUsableItem":
            return ""
        item_def = try_(lambda: inv.DefinitionData.ItemDefinition)
        if item_def is None:
            return ""
        key = item_def._get_address()
        if (kind := self._pickup_kinds.get(key)) is None:
            kind = self._pickup_kinds[key] = self._usable_kind(item_def)
        return kind

    def _usable_kind(self, item_def: Any) -> str:
        """A usable item's kind from its definition: its inventory card (Presentation), a currency by its FormOfCurrency."""
        from ...util import try_  # noqa: PLC0415

        name = try_(lambda: str(item_def.Presentation.Name), "")
        kind = "ammo" if name.startswith("WeaponAmmo_") else PRESENTATION_KINDS.get(name, "")
        if kind == "cash":
            currency = getattr(try_(lambda: item_def.FormOfCurrency), "name", "CURRENCY_Credits")
            kind = CURRENCY_KINDS.get(currency, "")
        return kind

    def card_level(self, inv: Any, level: int) -> int:
        """The level an item's card shows, from its level (ExpLevel / GetExpLevel()): BL2's, as is."""
        return level

    def zippy_frame(self, inv: Any) -> str:
        """An item's card type frame ("Artifact", "comm"...): IItemCardable.GetZippyFrame() (a call -
        tools/probes/probe_zippy.txt)."""
        return str(inv.GetZippyFrame())

    def element_level(self, inv: Any, kind: str) -> int:
        """An elemental item's level, a stat of its own (0: none): BL2's has none - its element's strength is its
        attributes' (its card's lines)."""
        return 0

    def element_frame(self, inv: Any, kind: str) -> str:
        """An item's card element key ("el": /cardicon/element/<key>.png), "" for none: its ElementalFrame ("shock" -
        tools/probes/probe_weapon_card2.txt)."""
        element = str(inv.ElementalFrame)
        return "" if element.lower() == "none" else element

    def rarity_table(self, globals_def: Any) -> dict[str, list[Any]]:
        """{"level": [colour entry index, "#rrggbb"]} for the rarity levels the game colours (util.rarity_table) - BL2's
        (tools/probes/probe_rarity3.txt): GlobalsDefinition.GetRarityColorForLevel (the colour it draws) and
        GetRarityLevelColorsIndexforLevel (its colour entry: levels sharing one are one tier - 5 and 7-10 all legendary)
        for its levels 0-15, 500-520; the table itself (RarityLevelColors) reads empty there."""
        out: dict[str, list[Any]] = {}
        for level in (*range(0, 16), *range(500, 521)):
            index = int(globals_def.GetRarityLevelColorsIndexforLevel(level))
            color = globals_def.GetRarityColorForLevel(level)
            rgb = (int(color.R), int(color.G), int(color.B))
            if index >= 0 and rgb != (0, 0, 0):  # (-1: not a colour entry; black: an empty one)
                out[str(level)] = [index, "#{:02x}{:02x}{:02x}".format(*rgb)]
        return out

    def card_line_value(self, entry: Any, pres: Any, item: Any) -> tuple[float, int] | None:
        """An item card line's number as the game shows it, (value, decimals) - None: the page works it out from the
        line's value and flags (BL2's: inspector._presentation_line, the page's skillStatParts)."""
        return None

    def presented_decimals(self, pres: Any) -> int:
        """How many decimals an item card stat shows in ATTRROUNDING_Float (inspector._presented): its attribute
        presentation's FloatPrecision (its class default 1: the accuracy's 72.1; a shield's delay 2), 0-4."""
        return max(0, min(4, int(pres.FloatPrecision)))

    def learn_element(self, enum: str, frame: str) -> None:
        """A weapon's damage type seen next to its card's element frame (inspector.learn_frame: BL2's barrels' element
        icons come from the weapons seen - the damage types' frames aren't in its data)."""
        from ...inspector import learn_frame  # noqa: PLC0415

        learn_frame(enum, frame)

    def damage_type_frame(self, enum: str) -> str:
        """A damage type's element icon frame ("" for none) - an object's (a barrel's explosion): the one learned from
        the weapons seen, else its enum's name (inspector.learned_frame)."""
        from ...inspector import learned_frame  # noqa: PLC0415

        return learned_frame(enum)
