"""Borderlands 1's pawns: what differs from Borderlands 2's (games/bl2/pawns.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.pawns import Pawns


class Bl1Pawns(Pawns):
    """Borderlands 1's pawns."""

    def local(self, pc: Any) -> Any:
        # In a vehicle its MyWillowPawn is None, its Pawn the vehicle (driving) or its seat (a turret: a
        # WillowWeaponPawn) - tools/probes/probe_bl1_driving.txt: the page lost track of the player meanwhile, listed
        # their pawn as another player ("Player", then twice getting out). Then: that pawn's Driver (UE3's
        # Vehicle.Driver - the player's pawn)
        if (pawn := pc.MyWillowPawn) is not None:
            return pawn
        return pc.Pawn.Driver if pc.Pawn is not None else None

    def vehicle_name(self, pawn: Any) -> str:
        # No VehicleDef, no GetCustomizableName (the log: "no attribute 'GetCustomizableName'" - its record failed, its
        # vehicles never on the page; tools/probes/probe_bl1_vehicles.txt: WillowVehicle_WheeledVehicle, in PawnList, not
        # hidden): WillowVehicle's DisplayName, else its VehicleNameString (WillowGame.u, offline - both "" in its .int
        # defaults: likely none, the page's "?" then)
        return str(pawn.DisplayName) or str(pawn.VehicleNameString)

    def class_name(self, ctrl: Any, pri: Any) -> dict[str, Any]:
        # No identifier definitions (the page said "Mordecai ?": the class definition's name - tools/probes/
        # probe_player_text.txt): the globals' PlayerCharacters[] = {CharacterClassName "Hunter", DefaultCharacterName
        # "Mordecai"} - localized (WillowGame/Localization/INT/gd_globals.INT, [General.Globals GlobalsDefinition]; the
        # load character menu's "Hunter", "Soldier", "Berserker" - the user), by the class's CharacterName (Mordecai's 1 -
        # its entry 1; the file's order Roland 0, Mordecai 1, Lilith 2, Brick 3). The controller's class: ours / the host's
        import unrealsdk  # noqa: PLC0415

        entry = unrealsdk.find_object("GlobalsDefinition", "GD_Globals.General.Globals").PlayerCharacters[
            int(ctrl.PlayerClass.CharacterName)]
        return {k: v for k, v in (("cls", str(entry.CharacterClassName)), ("char", str(entry.DefaultCharacterName))) if v}

    def name(self, pawn: Any) -> str:
        # Its balance names it per grade (tools/probes/probe_bl1_names.txt): BalanceDefinitionState {BalanceDefinition,
        # GradeIndex}, the balance's Grades[] = AIPawnGameStageGradeWeightData {GradeModifiers: {ExpLevel, DisplayName...}}
        # - what WillowAIPawn.GetTargetName reads (its bytecode: GetDisplayNameAtGrade(GradeIndex)), read as properties.
        # No balance (Claptrap, the other NPCs): "".
        state = pawn.BalanceDefinitionState
        balance = state.BalanceDefinition
        if balance is None:
            return ""
        grades = list(balance.Grades)
        if not grades:
            return ""
        grade = grades[state.GradeIndex] if 0 <= state.GradeIndex < len(grades) else grades[0]
        return str(grade.GradeModifiers.DisplayName)

    def raw_name(self, pawn: Any) -> str:
        # no AIClass on its pawns: their own AIPawnName ('ClapTrap'; 'None' on most enemies)
        name = str(pawn.AIPawnName)
        return "" if name == "None" else name
