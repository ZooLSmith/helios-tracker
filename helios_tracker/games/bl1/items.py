"""Borderlands 1's items: what differs from Borderlands 2's (games/bl2/items.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.items import Items

BL1_EQUIP_KINDS = {"EQUIPLOC_Shield": "shield", "EQUIPLOC_MOD": "grenade", "EQUIPLOC_Deck": "classmod"}  # (com decks)
# a weapon's element (its damage type's EDamageType) -> its frames' prefix in the card's element clip (bl1map
# ELEMENT_CLIP: exp0-4, shock0-4, fire0-4, corr0-4 - their art an explosion, a bolt, a flame, a biohazard; the enum's
# order isn't the clip's: Incindiary, Shock, Explosive, Corrosive)
BL1_ELEMENT_FRAMES = {"DAMAGE_TYPE_Explosive": "exp", "DAMAGE_TYPE_Shock": "shock", "DAMAGE_TYPE_Incindiary": "fire",
                      "DAMAGE_TYPE_Corrosive": "corr"}


class Bl1Items(Items):
    """Borderlands 1's items."""

    def equip_kind(self, inv: Any) -> str | None:
        # One class for the equipped items (WillowEquipAbleItem): the slot its definition goes in - ItemDefinition
        # .EquipmentLocation, EEquipmentLoc (WillowGame.u, offline; a shield: gd_shields.A_Item.Item_Shield, its
        # UIStatModifiers BL2's - probe_bl1_pause.txt). Compared by name (unrealsdk's enums are int-based).
        slot = inv.DefinitionData.ItemDefinition.EquipmentLocation
        return BL1_EQUIP_KINDS.get(getattr(slot, "name", slot))

    def zippy_frame(self, inv: Any) -> str:
        # No GetZippyFrame: a property, WillowInventory.ZippyFrame (a name - Engine.u, offline)
        return str(inv.ZippyFrame)

    def learn_element(self, enum: str, frame: str) -> None:
        pass  # (its damage types' frames are known - damage_type_frame: nothing to learn from the weapons)

    def damage_type_frame(self, enum: str) -> str:
        # A damage type's element icon (a barrel's explosion - collector.py): its element's frames' first, the mark
        # alone ("exp0", "fire0": BL1_ELEMENT_FRAMES); "" for none. (Not learned from the weapons: their frames carry
        # their level - "fire1" - and the learned table is the other games' - the user saw BL2's 404s on BL1's barrels)
        prefix = BL1_ELEMENT_FRAMES.get(enum, "")
        return f"{prefix}0" if prefix else ""

    def element_level(self, inv: Any, kind: str) -> int:
        # Its card draws an element's tech level on its icon ("x1".."x4": the clip's level frames - element_frame); the
        # page draws the mark alone (bl1map.card_frame_icon) and the level as a stat (the user: "as BL2, no number on
        # it, but a stat"). A weapon's: StaticCalculateWeaponTechLevelForUI (The Clipper's 1: x1 - the user); an item's
        # (an element: its FlashTechFrame) CalculateItemTechLevel (its parts' TechLevelIncrease - an Explosive MIRV's 0,
        # no number on its card)
        if not self.element_frame(inv, kind):
            return 0
        if kind == "weapon":
            return int(inv.StaticCalculateWeaponTechLevelForUI(inv.DefinitionData)[0])
        return int(inv.CalculateItemTechLevel())

    def element_frame(self, inv: Any, kind: str) -> str:
        # No ElementalFrame: an item's card element is its frame number in the card's element clip (bl1map
        # ELEMENT_CLIP: 1-5 explosive, 6-10 shock, 11-15 fire, 16-20 corrosive - each tech level -, 21 none), its
        # instance data's FlashTechFrame - GetTechIconFrame() (WillowItem: script; tools/probes/probe_bl1_elements.txt:
        # an "Explosive MIRV" 1.0, the others 0 - none). A weapon's: its damage type and tech level
        # (StaticGetWeaponDamageType, StaticCalculateWeaponTechLevelForUI - static, its DefinitionData their input;
        # each returns (its value, that input)): the clip's frame "<element><level>" - The Clipper: Incendiary_Impact,
        # its DamageType DAMAGE_TYPE_Incindiary, level 1: "fire1", the flame and "x1", its card's (the user).
        if kind == "weapon":
            damage_type = inv.StaticGetWeaponDamageType(inv.DefinitionData)[0]
            element = getattr(damage_type.DamageType, "name", "") if damage_type is not None else ""
            if element not in BL1_ELEMENT_FRAMES:
                return ""
            level = int(inv.StaticCalculateWeaponTechLevelForUI(inv.DefinitionData)[0])
            return f"{BL1_ELEMENT_FRAMES[element]}{level}"
        frame = int(float(inv.GetTechIconFrame()))
        return str(frame) if frame > 0 else ""

    def card_level(self, inv: Any, level: int) -> int:
        # Its card shows the level the item needs, not its ExpLevel (the user: weapons of ExpLevel 6, their cards 4 -
        # tools/probes/probe_bl1_levels.txt): WillowInventory.GetControllerPlayerExpLevelRequiredToUse(controller) - script
        # (Engine.u, offline): ExpLevel + FFloor(its definition's PlayerUseLevelBonus) if bUsesPlayerLevelRequirement
        from mods_base import get_pc  # noqa: PLC0415

        return int(inv.GetControllerPlayerExpLevelRequiredToUse(get_pc()))

    def rarity_table(self, globals_def: Any) -> dict[str, list[Any]]:
        # No GetRarityLevelColorsIndexforLevel (only GetRarityColorForLevel): the table itself, RarityLevelColors[] =
        # {MinLevel, MaxLevel, Color} (gd_globals.upk, offline: 13 entries - -1..1 / 2..4 white, 5..10 green, 11..15 blue,
        # 16..49 purple, 50..60 / 61..65 / 66..100 yellow to orange, 170 green, 171 red, 180..190 gold, 500 cyan): each
        # level in an entry's range -> its index. (Its levels: up to 100, 170-190, 500 - not BL2's 0-15, 500-520.)
        out: dict[str, list[Any]] = {}
        for index, entry in enumerate(globals_def.RarityLevelColors):
            color = entry.Color
            rgb = (int(color.R), int(color.G), int(color.B))
            if rgb == (0, 0, 0):
                continue
            for level in range(max(0, int(entry.MinLevel)), int(entry.MaxLevel) + 1):
                out.setdefault(str(level), [index, "#{:02x}{:02x}{:02x}".format(*rgb)])
        return out

    def card_line_value(self, entry: Any, pres: Any, item: Any) -> tuple[float, int] | None:
        # Its card shows the line's modifier, never its attribute's current value (tools/probes/probe_bl1_cards.txt: an
        # SG330's zoom -40, fire rate -0.4318, projectiles 1 -> "4.0x", "+43%", "+1"; the page showed the gun's 20, 0.45,
        # 8): remapped (bValueRemappingEnabled - the zoom's -100..0 onto -10..0), its sign flipped if bDisplayAsInverse
        # (not BL2's reciprocal), x 100 if a percentage, rounded by its RoundingMode - Float: one decimal, a percentage
        # a whole number (the fire rate's 43.18: "+43%").
        import math  # noqa: PLC0415

        from ...inspector import _remapped  # noqa: PLC0415

        value = float(entry.ModifierValue)
        if bool(pres.bValueRemappingEnabled) and (remapped := _remapped(pres, value, item)) is not None:
            value = remapped
        if bool(pres.bDisplayAsInverse):
            value = -value
        percent = bool(pres.bDisplayAsPercentage)
        if percent:
            value *= 100
        mode = str(getattr(pres.RoundingMode, "name", pres.RoundingMode))
        if mode == "ATTRROUNDING_IntCeil":
            return float(math.ceil(value - 1e-9)), 0
        if mode == "ATTRROUNDING_IntFloor":
            return float(math.floor(value + 1e-9)), 0
        if mode == "ATTRROUNDING_IntRound" or percent:
            return float(math.floor(abs(value) + 0.5) * (1 if value >= 0 else -1)), 0
        return round(value, 1), 1

    def presented_decimals(self, pres: Any) -> int:
        # its AttributePresentationDefinition has no FloatPrecision (WillowGame.u, offline): one decimal - the game's
        # SG330 accuracy 6.7 (the user; ours read 7 from the missing property)
        return 1
