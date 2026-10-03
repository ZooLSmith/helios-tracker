"""
The games the mod runs in, and what differs between them: one profile per game, picked once (GAME). Nothing else in
the mod names a game or probes the SDK to find out which one it's in (no hasattr / try_ to guess): it asks GAME.

- A system a game doesn't have is a feature it lacks (`"oxygen" in GAME.features`): the work for it doesn't run.
- An API spelled differently is a method the game's profile overrides (`GAME.map_name(wi)`).
- Profile is BL2, the reference; each other game overrides only what differs from it, each difference with what
  showed it (a probe, a log). A game's own objects (the Pre-Sequel's jump pads, oxygen cracks) need no entry: they're
  recognized from the game's data, and simply never met in another game.

The page gets the profile's key and features in the level message (collector.py) and follows them (web/js/game.js).
New game: its class here, registered under mods_base's name for it (Game.<NAME>); .agent/<game>.md for what was seen.
"""

from typing import Any

# The features (systems some games have, others don't); the page reads the same names (game.js)
TACMAP = "tacmap"  # the map screen's images, read from the game's packages (tacmap.py)
DISCOVERY = "discovery"  # the level's discovery areas and the map's fog of war (WorldDiscoveryArea, DiscoveredWorldAreas)
OXYGEN = "oxygen"  # the Oz meter: oxygen pools, air domes, oxygen sources
JUMPPADS = "jumppads"  # jump pads and geysers (OzPlayerJumpPad)
SCAN = "scan"  # the game files' index: fonts, item card / skill icons (gamescan.py: BL2's package layout)
MISSION_STEPS = "missionsteps"  # a mission's objectives come in steps (objective sets: ActiveObjectiveSet) - else all at once
# its objectives marked by the level's waypoint actors (WillowWaypoint: a mission's target / turn-in waypoint definition's
# - collector._waypoint_markers), not by the tracker's waypoint components (MissionWaypoints)
WAYPOINT_MARKERS = "waypointmarkers"

_PROFILES: dict[str, type["Profile"]] = {}


def profile(*names: str):  # noqa: ANN201
    """Registers a profile class for these games (mods_base's Game names: "BL2", "TPS"...)."""

    def register(cls: type["Profile"]) -> type["Profile"]:
        for name in names:
            _PROFILES[name] = cls
        return cls

    return register


@profile("BL2")
class Profile:
    """Borderlands 2: the reference - what the mod was built on."""

    key = "bl2"  # the page's name for it (the level message's "game": its label variants, its own data - game.js)
    packages = "CookedPCConsole"  # WillowGame/<this>: its cooked packages, the folder the mod reads (None: none read)
    exe_depth = 2  # the game's folder: this many up from its executable's (Binaries/Win32/Borderlands2.exe)
    gibbed_prefix = "BL2"  # a gear's code for Gibbed's save editor: "BL2(...)" ("": no editor)
    features: frozenset[str] = frozenset({TACMAP, DISCOVERY, SCAN, MISSION_STEPS})

    def map_name(self, wi: Any) -> str:
        """The persistent level's map name ("Sanctuary_P"), from the world info."""
        return str(wi.GetStreamingPersistentMapName())

    def world_paused(self, wi: Any) -> bool:
        """Whether the game's world stands still (its menu): WorldInfo.Pauser set. (Not every clock: shops.py.)"""
        return wi.Pauser is not None

    def equip_kind(self, inv: Any) -> str | None:
        """An item's kind from its definition, for a class that doesn't tell it (inspector._kind): BL2's classes all do."""
        return None

    def object_behaviors(self, definition: Any) -> list[Any]:
        """An interactive object definition's behaviours (inspector.explosion_info looks for a Behavior_Explode): its
        BehaviorProviderDefinition's BehaviorSequences[].BehaviorData2[].Behavior."""
        return [data.Behavior for seq in definition.BehaviorProviderDefinition.BehaviorSequences
                for data in seq.BehaviorData2 if data.Behavior is not None]

    def mission_entries(self, tracker: Any) -> Any:
        """The playthrough's missions, each {MissionDef, Status, its progress...} (missions.py MissionLog): the
        tracker's MissionList - every mission of the game, not started ones too."""
        return tracker.MissionList

    def mission_objectives(self, mdef: Any) -> list[tuple[int, Any]]:
        """A mission definition's objectives, in order: (its key - what objective_index maps to its index - , the
        objective: ProgressMessage, ObjectiveCount, bObjectiveIsOptional). ObjectiveDefs, keyed by address."""
        return [(o._get_address(), o) for o in mdef.ObjectiveDefs if o is not None]

    def mission_progress(self, entry: Any) -> tuple[int, ...]:
        """A mission entry's count per objective (its definition's order): ObjectivesProgress."""
        return tuple(int(v) for v in entry.ObjectivesProgress)

    def mission_status(self, entry: Any) -> str:
        """A mission entry's status, as the page names them (EMissionStatus without "MS_": Active, ReadyToTurnIn...)."""
        return str(getattr(entry.Status, "name", entry.Status)).removeprefix("MS_")

    def mission_number(self, mdef: Any) -> int:
        """Its number in the story (the page's order)."""
        return int(mdef.MissionNumber)

    def pawn_name(self, pawn: Any) -> str:
        """An AI pawn's name as the game shows it ("" if none): BL2's balance names it per playthrough
        (collector.pawn_display_name - properties only: the name functions crashed the game)."""
        from .collector import pawn_display_name  # noqa: PLC0415

        return pawn_display_name(pawn)

    def pawn_raw_name(self, pawn: Any) -> str:
        """An AI pawn's own technical name, for a made-up one when the game has none: its AI class's."""
        from .util import def_name  # noqa: PLC0415

        return def_name(pawn.AIClass)

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        """A map's name as the game shows it, from one of its level lists (a LevelDependencyList: the base game's
        GD_Globals.General.LevelList, one per DLC - each knowing only its own maps), "" if it doesn't know it."""
        return str(level_list.GetFriendlyLevelNameFromMapName(map_name))

    def level_key(self, wi: Any, map_name: str) -> tuple:
        """What tells levels apart, read every second (cheap): another one = a new level."""
        from . import levelmap  # noqa: PLC0415

        return map_name, levelmap.tactical_key(wi)

    def map_source(self, wi: Any, map_name: str) -> Any:
        """The level's map (levelmap.MapSource: its placement, how its images load), None without one - at a level
        change, on the game thread."""
        from . import levelmap  # noqa: PLC0415

        return levelmap.tactical(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        """ClientPlayBinkMovie's arguments: whether the video can't be skipped."""
        return bool(args.bForceNoSkip)

    def show_message(self, text: str, duration: float) -> None:
        """The game's bottom-left message (ui_utils' co-op one: it stays until hide_message)."""
        from ui_utils import show_coop_message  # noqa: PLC0415 (not in every game's ui_utils: BL1's)

        show_coop_message(text)

    def hide_message(self) -> None:
        from ui_utils import hide_coop_message  # noqa: PLC0415

        hide_coop_message()


@profile("TPS")
class PreSequel(Profile):
    """Borderlands: The Pre-Sequel (.agent/presequel.md)."""

    key = "tps"
    gibbed_prefix = "BLOZ"
    features = Profile.features | {OXYGEN, JUMPPADS}


@profile("AoDK")
class DragonKeep(Profile):
    """Tiny Tina's Assault on Dragon Keep, the standalone: BL2's engine and data."""

    key = "aodk"
    gibbed_prefix = ""  # no Gibbed editor for it


BL1_BEHAVIOR_ARRAYS = ("OnSpawn", "OnBehaviorSetEnabled", "OnBehaviorSetDisabled", "OnTouch", "OnUnTouch", "OnUsedBy",
                       "OnTakeDamage", "OnKilled")
BL1_REACTION_ARRAYS = ("CustomEvents", "TimerEvents", "CounterEvents")
BL1_EQUIP_KINDS = {"EQUIPLOC_Shield": "shield", "EQUIPLOC_MOD": "grenade", "EQUIPLOC_Deck": "classmod"}  # (com decks)


@profile("BL1")
class Borderlands1(Profile):
    """Borderlands 1, the original 2009 game (the Enhanced edition's SDK didn't run: not registered) - .agent/bl1.md."""

    key = "bl1"
    packages = "CookedPC"  # its packages: version 584 (BL2's 832) - read with upk_bl1.Bl1Package (its map: bl1map.py)
    exe_depth = 1  # Binaries/Borderlands.exe
    gibbed_prefix = ""
    # no WorldDiscoveryArea class (the log: "Couldn't find class"); its packages not indexed (gamescan reads BL2's)
    features = (Profile.features - {DISCOVERY, SCAN, MISSION_STEPS}) | {WAYPOINT_MARKERS}

    def map_name(self, wi: Any) -> str:
        # The world is "Loader" in every area (tools/probes/probe_bl1.txt): the area is streamed in, the first of its
        # StreamingLevels - a LevelStreamingPersistent ('arid_p'), the others its sublevels (LevelStreamingKismet). No
        # GetStreamingPersistentMapName (AttributeError). None streamed in (the main menu): the world's own package,
        # its path's first part ("menumap.TheWorld:PersistentLevel.WorldInfo_0").
        for level in wi.StreamingLevels:
            if level is not None and level.Class.Name == "LevelStreamingPersistent":
                return str(level.PackageName)
        return wi._path_name().split(".", 1)[0]

    def world_paused(self, wi: Any) -> bool:
        # The escape menu sets Pauser; the status menus (inventory, map, skills...) don't - they set
        # WorldInfo.bStatusMenuOnly, the world stopped all the same (tools/probes/probe_bl1_pause.txt) - but not the
        # shops' timer (the user): shops.py keeps Pauser
        return wi.Pauser is not None or bool(wi.bStatusMenuOnly)

    def equip_kind(self, inv: Any) -> str | None:
        # One class for the equipped items (WillowEquipAbleItem): the slot its definition goes in - ItemDefinition
        # .EquipmentLocation, EEquipmentLoc (WillowGame.u, offline; a shield: gd_shields.A_Item.Item_Shield, its
        # UIStatModifiers BL2's - probe_bl1_pause.txt). Compared by name (unrealsdk's enums are int-based).
        slot = inv.DefinitionData.ItemDefinition.EquipmentLocation
        return BL1_EQUIP_KINDS.get(getattr(slot, "name", slot))

    def object_behaviors(self, definition: Any) -> list[Any]:
        # No behaviour provider: behaviour sets - DefaultBehaviorSet and ExtraBehaviorSets[], InteractiveObjectBehaviorSet
        # (WillowGame.u, offline): event arrays of behaviours (OnKilled, OnTakeDamage...) and of reactions holding
        # Behaviors[] (CustomEvents, TimerEvents, CounterEvents). Its exploding barrels: a Behavior_Explode in them
        # (gd_Explosives.Barrels.ExplodingBarrel_Incendiary.Behavior_Explode_0)
        out: list[Any] = []
        for behavior_set in [definition.DefaultBehaviorSet, *definition.ExtraBehaviorSets]:
            for name in BL1_BEHAVIOR_ARRAYS:
                out += [b for b in getattr(behavior_set, name) if b is not None]
            for name in BL1_REACTION_ARRAYS:
                out += [b for reaction in getattr(behavior_set, name) for b in reaction.Behaviors if b is not None]
        return out

    def mission_entries(self, tracker: Any) -> Any:
        # The tracker's MissionList is bare definitions (its active ones): the player's own, per playthrough -
        # WillowPlayerController.MissionPlaythroughData[] = MissionPlaythroughInfo {PlayThroughNumber, ActiveMission,
        # MissionList: [{MissionDef, Status, Objectives: [{StatId, CurrentAmount}]}]} - the one of the playthrough
        # played (WillowGameReplicationInfo.HostCurrentPlaythrough: the array's entries all said PlayThroughNumber 0 -
        # tools/probes/probe_bl1_missions.txt). Only the missions the player has (no not started ones).
        from mods_base import ENGINE, get_pc  # noqa: PLC0415

        playthrough = int(ENGINE.GetCurrentWorldInfo().GRI.HostCurrentPlaythrough)
        return get_pc().MissionPlaythroughData[playthrough].MissionList

    def mission_objectives(self, mdef: Any) -> list[tuple[int, Any]]:
        # Objectives[] = MissionObjectiveData structs {StatId, ObjectiveCount, ProgressMessage}: keyed by their index
        return list(enumerate(mdef.Objectives))

    def mission_progress(self, entry: Any) -> tuple[int, ...]:
        return tuple(int(o.CurrentAmount) for o in entry.Objectives)

    def mission_status(self, entry: Any) -> str:
        # EMissionStatus: NotStarted, Active, ReadyToTurnIn, Complete, Redeemed - turned in: Redeemed (every done one
        # in the probe); Complete, BL2's "done", too
        name = str(getattr(entry.Status, "name", entry.Status)).removeprefix("MS_")
        return "Complete" if name in ("Complete", "Redeemed") else name

    def mission_number(self, mdef: Any) -> int:
        return int(mdef.PlotMissionNumber)

    def pawn_name(self, pawn: Any) -> str:
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

    def pawn_raw_name(self, pawn: Any) -> str:
        # no AIClass on its pawns: their own AIPawnName ('ClapTrap'; 'None' on most enemies)
        name = str(pawn.AIPawnName)
        return "" if name == "None" else name

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        # its lists' entries, read as properties: {PersistentMap 'arid_p', LevelName 'Arid Badlands' (the game's text,
        # localized)...} - gd_globals.General.LevelList, offline (.agent/bl1.md "Level names")
        want = map_name.lower()
        return next((str(entry.LevelName) for entry in level_list.LevelList if str(entry.PersistentMap).lower() == want), "")

    def level_key(self, wi: Any, map_name: str) -> tuple:
        return (map_name,)  # (one map anchor per area: found at the change - levelmap.landmark)

    def map_source(self, wi: Any, map_name: str) -> Any:
        from . import levelmap  # noqa: PLC0415

        return levelmap.landmark(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        return False  # no bForceNoSkip argument (the log: AttributeError)

    def show_message(self, text: str, duration: float) -> None:
        # BL1's ui_utils (1.3) has no co-op message: its HUD one, which goes away by itself
        from ui_utils import show_hud_message  # noqa: PLC0415

        from .i18n import t  # noqa: PLC0415

        show_hud_message(t("box.title"), text, duration)

    def hide_message(self) -> None:
        pass


def make_profile(name: str) -> Profile:
    """The profile of a game, by mods_base's name for it ("BL2", "TPS"...)."""
    if (cls := _PROFILES.get(name)) is None:
        raise RuntimeError(f"Helios Tracker doesn't know the game {name!r}")
    return cls()


def _current() -> Profile:
    import mods_base  # noqa: PLC0415

    return make_profile(mods_base.Game.get_current().name)


GAME: Profile = _current()  # the game running (read as games.GAME, at the time: a test swaps it)
