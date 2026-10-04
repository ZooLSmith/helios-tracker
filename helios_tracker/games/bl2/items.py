"""Borderlands 2's items (the base: every game's unless its profile has its own) - Items and their cards: their kind, level, card frames, elements, stat lines, the rarity colours.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part


class Items(Part):
    """Items and their cards: their kind, level, card frames, elements, stat lines, the rarity colours."""

    def equip_kind(self, inv: Any) -> str | None:
        """An item's kind from its definition, for a class that doesn't tell it (inspector._kind): BL2's classes all do."""
        return None

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
