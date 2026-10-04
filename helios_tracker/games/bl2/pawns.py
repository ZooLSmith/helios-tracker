"""Borderlands 2's pawns (the base: every game's unless its profile has its own) - Pawns: ours, their names, vehicles', the players' class / character."""

from typing import Any

from ..base import Part


class Pawns(Part):
    """Pawns: ours, their names, vehicles', the players' class / character."""

    def local(self, pc: Any) -> Any:
        """The local player's own pawn (the player, not the vehicle they drive): its MyWillowPawn."""
        return pc.MyWillowPawn

    def vehicle_name(self, pawn: Any) -> str:
        """A vehicle's name as the game shows it ("" for none): its VehicleClassDefinition's DisplayName (localized),
        else its GetCustomizableName()."""
        from ...util import call_str  # noqa: PLC0415

        return str(pawn.VehicleDef.DisplayName) or call_str(pawn.GetCustomizableName)

    def class_name(self, ctrl: Any, pri: Any) -> dict[str, Any]:
        """A player's class and character as the game names them ({"cls": "Gunzerker", "char": "Salvador"}, those it
        has): BL2's identifier definitions (inspector.class_identifiers)."""
        from ...inspector import class_identifiers  # noqa: PLC0415

        return class_identifiers(ctrl, pri)

    def name(self, pawn: Any) -> str:
        """An AI pawn's name as the game shows it ("" if none): BL2's balance names it per playthrough
        (collector.pawn_display_name - properties only: the name functions crashed the game)."""
        from ...collector import pawn_display_name  # noqa: PLC0415

        return pawn_display_name(pawn)

    def raw_name(self, pawn: Any) -> str:
        """An AI pawn's own technical name, for a made-up one when the game has none: its AI class's."""
        from ...util import def_name  # noqa: PLC0415

        return def_name(pawn.AIClass)
