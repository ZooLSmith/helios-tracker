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

import re
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
# a damage type's element icon learned from the weapons seen (inspector.learn_frame: their card frame next to their
# damage type) - else the profile's damage_type_frame
LEARNED_ELEMENTS = "learnedelements"

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
    features: frozenset[str] = frozenset({TACMAP, DISCOVERY, SCAN, MISSION_STEPS, LEARNED_ELEMENTS})

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

    def item_card_level(self, inv: Any, level: int) -> int:
        """The level an item's card shows, from its level (ExpLevel / GetExpLevel()): BL2's, as is."""
        return level

    def is_looted(self, io: Any, client: bool) -> bool:
        """A container looted: opened, and no longer usable (bCanBeUsed[0] 1 -> 0). Opened: its SimpleAnimState is a
        bitmask over its animations (SimpleAnimInfo[].AnimName - tools/probes/probe_prelooted.txt: Open, Open_Vacuum,
        Opened(_Idle), Closed(_Idle)), the "Opened..." one's bit set: closed 8 (Closed), just opened 14, looted and the
        level reloaded 12, spawned looted 4 (Opened alone), BL2's 7 - the state 7 alone (the first rule) missed all but
        the last. Without an "Opened" animation: the state 7. A co-op client (tools/probes/probe_client_containers.txt):
        the state (replicated) but bCanBeUsed stays 1 - it isn't sent: the state alone there."""
        from .util import try_  # noqa: PLC0415

        state = try_(lambda: int(io.SimpleAnimState), 0)
        anims = [try_(lambda a=a: str(a.AnimName), "") for a in try_(lambda: list(io.SimpleAnimInfo), []) or []]
        opened_bits = [n for n, name in enumerate(anims) if name.lower().startswith("opened")]
        opened = any(state >> n & 1 for n in opened_bits) if opened_bits else state == 7
        return opened and (client or not try_(lambda: io.bCanBeUsed[0], 1))

    def mission_home(self, mdef: Any) -> dict[str, str] | None:
        """A mission's area for the page ({"a": its name as the game shows it, "map": its map}): where its giver is -
        its TravelStation (missions.station: StationDisplayName, StationLevelName)."""
        from .missions import station  # noqa: PLC0415

        return station(mdef.TravelStation)

    def object_directives(self, io: Any) -> list[Any]:
        """An interactive object's missions it gives / takes back ({MissionDefinition, bBeginsMission, bEndsMission}):
        its Directives' (a MissionDirectivesDefinition - the bounty board, tools/probes/probe_bounty.txt)."""
        return list(io.Directives.MissionDirectives)

    def mission_offered(self, pc: Any, mission: Any, state: str, logged: bool) -> bool:
        """Whether a giver's mission can be picked up now (its "!"): the mission log's word (MissionLog.giver_states:
        not started, the missions it needs done) - `state` "begin"."""
        return state == "begin"

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

    def card_icon_png(self, kind: str, key: str) -> bytes | None:
        """An item card icon (/cardicon/<kind>/<key>.png) as a PNG, or None: the game's UI movies' (gamecards.py, from
        the files scan). The server's threads: no SDK."""
        from . import gamecards  # noqa: PLC0415

        return gamecards.card_png(kind, key)

    def card_icons_ready(self) -> bool:
        """Whether card_icon_png can find icons (the page asks only then): the scan done, the keys known."""
        from . import gamecards  # noqa: PLC0415

        return gamecards.ready()

    def selling_price(self, machine: Any, inv: Any, pc: Any) -> int:
        """What a vending machine asks for one of an item (the price its menu shows): GetSellingPriceForInventory(item,
        controller, quantity) - scaled to the player."""
        return int(machine.GetSellingPriceForInventory(inv, pc, 1))

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

    def read_skills(self, ctrl: Any, player: dict[str, Any], bonuses: dict[str, Any]) -> None:
        """A player's skill tree into their record ("skills": trees -> tiers -> cells, "skillPoints"): BL2's PlayerSkillTree
        (inspector._skills)."""
        from .inspector import _skills  # noqa: PLC0415

        _skills(ctrl, player, bonuses)

    def action_skill_locked(self, pc: Any) -> bool:
        """Whether the player's action skill isn't unlocked yet (its cooldown then reads "ready"): BL2's tree's
        SKILL_TYPE_Action skill at Grade 0 (skills._action_locked)."""
        from .skills import _action_locked  # noqa: PLC0415

        return _action_locked(pc)

    def card_line_value(self, entry: Any, pres: Any, item: Any) -> tuple[float, int] | None:
        """An item card line's number as the game shows it, (value, decimals) - None: the page works it out from the
        line's value and flags (BL2's: inspector._presentation_line, the page's skillStatParts)."""
        return None

    def shop_timer_source(self, world_info: Any) -> Any:
        """What the shops' restock timer is read from (SecondsUntilShopsReset, ShopTimerRate): the host's own count
        (WorldInfo.Game), else the replicated one (a co-op client: GRI)."""
        return world_info.Game if world_info.Game is not None else world_info.GRI

    def presented_decimals(self, pres: Any) -> int:
        """How many decimals an item card stat shows in ATTRROUNDING_Float (inspector._presented): its attribute
        presentation's FloatPrecision (its class default 1: the accuracy's 72.1; a shield's delay 2), 0-4."""
        return max(0, min(4, int(pres.FloatPrecision)))

    def shop_currency(self, machine: Any) -> str:
        """What a vending machine's prices are in, its enum's name (shops.py CURRENCIES: CURRENCY_Credits...):
        FormOfCurrency (Crazy Earl's: eridium)."""
        return str(getattr(machine.FormOfCurrency, "name", machine.FormOfCurrency))

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
BL1_CARD_KINDS = ("manufacturer", "type", "element")  # its card icons read (Borderlands1.card_icon_png)
# a weapon's element (its damage type's EDamageType) -> its frames' prefix in the card's element clip (bl1map
# ELEMENT_CLIP: exp0-4, shock0-4, fire0-4, corr0-4 - their art an explosion, a bolt, a flame, a biohazard; the enum's
# order isn't the clip's: Incindiary, Shock, Explosive, Corrosive)
BL1_ELEMENT_FRAMES = {"DAMAGE_TYPE_Explosive": "exp", "DAMAGE_TYPE_Shock": "shock", "DAMAGE_TYPE_Incindiary": "fire",
                      "DAMAGE_TYPE_Corrosive": "corr"}
# a tree branch -> the skill clip's text field naming it: tree1..3 sit under treeLeft / treeCenter / treeRight (the
# skill clip's placements, x 21.75 / 199.75 / 378.75 against 17.2 / 195.4 / 339.2 - its movie, offline)
BL1_BRANCH_TEXTS = {"SKILLBRANCH_Left": "tree1.text", "SKILLBRANCH_Middle": "tree2.text", "SKILLBRANCH_Right": "tree3.text"}
BL1_ALIAS = re.compile(r"\$<StringAliasMap:([^>]+)>")  # a Scaleform text naming an alias map entry
BL1_STRINGS = re.compile(r"<Strings:([^.>]+)\.([^.>]+)\.([^>]+)>")  # a localized text's markup: package.section.key


@profile("BL1")
class Borderlands1(Profile):
    """Borderlands 1, the original 2009 game (the Enhanced edition's SDK didn't run: not registered) - .agent/bl1.md."""

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
    # no WorldDiscoveryArea class (the log: "Couldn't find class"); its packages not indexed (gamescan reads BL2's)
    # (its element icons: its card clip's frames, its damage types' known - damage_type_frame: nothing to learn)
    features = (Profile.features - {DISCOVERY, SCAN, MISSION_STEPS, LEARNED_ELEMENTS}) | {WAYPOINT_MARKERS}

    def __init__(self) -> None:
        self._branch_names: dict[int, dict[str, str]] = {}  # CharacterName -> its branches' names (branch_names)
        self._skill_clips: dict[int, tuple[str, str]] = {}  # CharacterName -> (the skill clip, its frame) (_skill_clip)
        self._missions: list[Any] = []  # every MissionDefinition loaded (_mission_definitions)

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
        # The tracker's MissionList is bare definitions (its active one): the player's own, per playthrough -
        # WillowPlayerController.MissionPlaythroughData[] = MissionPlaythroughInfo {PlayThroughNumber, ActiveMission,
        # MissionList: [{MissionDef, Status, Objectives: [{StatId, CurrentAmount}]}]} - the one of the playthrough
        # played (WillowGameReplicationInfo.HostCurrentPlaythrough: the array's entries all said PlayThroughNumber 0 -
        # tools/probes/probe_bl1_missions.txt). Only the missions the player has picked up: then every other mission
        # the game has loaded, not started (BL2's log lists the whole playthrough so) - every MissionDefinition is
        # loaded, the base game's and the DLCs' (tools/probes/probe_bl1_tracker.txt: 218), each as a _NotPickedUp.
        from mods_base import ENGINE, get_pc  # noqa: PLC0415

        pc = get_pc()
        playthrough = int(ENGINE.GetCurrentWorldInfo().GRI.HostCurrentPlaythrough)
        log = list(pc.MissionPlaythroughData[playthrough].MissionList)
        picked = {e.MissionDef._get_address() for e in log if e.MissionDef is not None}
        return log + [_NotPickedUp(d, pc) for d in self._mission_definitions() if d._get_address() not in picked]

    def _mission_definitions(self) -> list[Any]:
        """Every MissionDefinition loaded - a find_all (it walks every object): once, kept (static game data)."""
        import unrealsdk  # noqa: PLC0415

        if not self._missions:
            self._missions = [d for d in unrealsdk.find_all("MissionDefinition", exact=False) if not d.Name.startswith("Default__")]
        return self._missions

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

    def is_looted(self, io: Any, client: bool) -> bool:
        # No SimpleAnimState / SimpleAnimInfo (WillowGame.u, offline), its bCanBeUsed a flag (BL2's an array): looted
        # = no longer usable (tools/probes/probe_bl1_looted.txt: the looted containers False, a toilet not searched
        # yet True). (A co-op client's: not seen.)
        return not bool(io.bCanBeUsed)

    def mission_home(self, mdef: Any) -> dict[str, str] | None:
        # No TravelStation (every mission fell in the page's "other" - the user): its waypoints' level - where it's
        # handed in (TurnInWaypointDefinition: usually its giver - T.K. Has More Work's WP_Al), else where it's done
        # (TargetWaypointDefinition) - their PersistentLevelName, named as the map's title is (the level lists' text:
        # collector.level_name). Its GameStageRegion has no name of its own (gd_GameStages.Arid.Arid__A). None: no
        # waypoint, or a level no list knows.
        from .collector import level_name  # noqa: PLC0415

        for waypoint in (mdef.TurnInWaypointDefinition, mdef.TargetWaypointDefinition):
            level = str(waypoint.PersistentLevelName) if waypoint is not None else ""
            if level and level.lower() != "none" and (name := level_name(level)):
                return {"a": name, "map": level}
        return None

    def object_directives(self, io: Any) -> list[Any]:
        # On the object itself: WillowInteractiveObject.MissionDirectives (tools/probes/probe_bl1_givers.txt: the bounty
        # board's 15, Dr. Zed's 11 - a WillowInteractiveNPC, an interactive object) - no Directives
        return list(io.MissionDirectives)

    def mission_offered(self, pc: Any, mission: Any, state: str, logged: bool) -> bool:
        # Its log has only the missions picked up (no "not started" ones): the game's own word - the controller's
        # GetMissionEligibility(mission) (script: its minimum level, dependencies, status) ME_Eligible, and not in the
        # log (a mission picked up is eligible too: the board's Bandit Presence, taken, ME_Eligible) - probe_bl1_givers:
        # the board's T.K. Has More Work, ME_Eligible, its AnnouncedMissions - the game's "!" (the user)
        return not logged and getattr(pc.GetMissionEligibility(mission), "name", "") == "ME_Eligible"

    def zippy_frame(self, inv: Any) -> str:
        # No GetZippyFrame: a property, WillowInventory.ZippyFrame (a name - Engine.u, offline)
        return str(inv.ZippyFrame)

    def card_icon_png(self, kind: str, key: str) -> bytes | None:
        # No files scan (its packages: version 584): its movies' sprites, drawn - the manufacturers' from its card's
        # movie (bl1map.card_icon), the type's: the item's icon, the menus' (bl1map.item_icon - not its card's
        # "zippy" art, a Claptrap holding it: the user); its elements' (frames "fire0".."shock4": the element and its
        # tech level, x2 / x4 drawn) not read yet
        from . import bl1map, gamecards, gamedir  # noqa: PLC0415

        cooked = gamedir.cooked_dir()
        if kind not in BL1_CARD_KINDS or cooked is None:
            return None
        if kind == "type":
            return bl1map.item_icon_png(cooked, key)
        if kind == "element":
            return bl1map.element_icon_png(cooked, key)
        return bl1map.card_icon_png(cooked, gamecards.keys(kind), key)

    def card_icons_ready(self) -> bool:
        # (the movie read on demand: once the keys are known - the first players' read; the elements need none)
        from . import gamecards  # noqa: PLC0415

        return all(gamecards.keys(kind) for kind in BL1_CARD_KINDS if kind != "element")

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

    def item_card_level(self, inv: Any, level: int) -> int:
        # Its card shows the level the item needs, not its ExpLevel (the user: weapons of ExpLevel 6, their cards 4 -
        # tools/probes/probe_bl1_levels.txt): WillowInventory.GetControllerPlayerExpLevelRequiredToUse(controller) - script
        # (Engine.u, offline): ExpLevel + FFloor(its definition's PlayerUseLevelBonus) if bUsesPlayerLevelRequirement
        from mods_base import get_pc  # noqa: PLC0415

        return int(inv.GetControllerPlayerExpLevelRequiredToUse(get_pc()))

    def selling_price(self, machine: Any, inv: Any, pc: Any) -> int:
        # GetSellingPriceForInventory(InventoryForSale, Quantity): no controller (WillowGame.u, offline) - BL2's call with
        # one failed (no price on the page)
        return int(machine.GetSellingPriceForInventory(inv, 1))

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

    def read_skills(self, ctrl: Any, player: dict[str, Any], bonuses: dict[str, Any]) -> None:
        # No PlayerSkillTree: the controller's PlayerSkills[] and SkillTreeBranches[] (tools/probes/probe_bl1_skills.txt) -
        # inspector._skills_from_player_skills; its branches' names: the skill menu's (branch_names)
        from .inspector import _skills_from_player_skills  # noqa: PLC0415

        _skills_from_player_skills(ctrl, player, bonuses, self.branch_names(ctrl), self.skill_icons(ctrl))

    def _skill_clip(self, ctrl: Any) -> tuple[str, str]:
        """The skill menu's clip and the player's frame of it: ("skills", "mordecai") - SkillTreeGFxDefinition
        .SkillMovieClip, and SkillTreeGFxHelper.GetCharacterName() (a switch on CurrentCharacter: the class's
        CharacterName - on one we construct; tools/probes/probe_bl1_branches.txt). Its Flash_SetCharacter's gotoAndStop."""
        import unrealsdk  # noqa: PLC0415

        character = ctrl.PlayerClass.CharacterName
        if (found := self._skill_clips.get(int(character))) is None:
            helper = unrealsdk.construct_object("SkillTreeGFxHelper", ctrl)
            helper.CurrentCharacter = character
            clip = str(unrealsdk.find_class("SkillTreeGFxDefinition").ClassDefaultObject.SkillMovieClip)
            found = self._skill_clips[int(character)] = (clip, str(helper.GetCharacterName()))
        return found

    def skill_icons(self, ctrl: Any) -> dict[tuple[str, int, int], str]:
        """The tree's cells' icons: (branch, tier, cell) -> a menu icon path ("menu.skills.mordecai.icon17.on.off":
        bl1map.MENU_ICON, served as /icon/<path>.png). No icon of their own on the skills (SkillDefinition
        .ScaleformFrameName: the HUD's popups, a few skills): the skill menu's cells - the class's SkillTreeLayout
        (ui_skill_tree.upk: <Branch>.Tiers[].Skills[], one SkillTreeNavDefinition per cell, in order) names each cell's
        clip (IconClipName, "icon17"), placed in the player's frame of the skill clip, drawn at its frame
        SkillTreeGFxDefinition.IconOnName ("on") - what its IconOffName frame shows too (its drawing, not the state's
        tile: bl1map.clip_icon) - offline, .agent/bl1.md."""
        import unrealsdk  # noqa: PLC0415

        from .inspector import BL1_BRANCHES  # noqa: PLC0415

        clip, frame = self._skill_clip(ctrl)
        layout = ctrl.PlayerClass.PlayerSkillSet.SkillTreeLayout
        movie_def = unrealsdk.find_class("SkillTreeGFxDefinition").ClassDefaultObject
        on, off = str(movie_def.IconOnName), str(movie_def.IconOffName)
        icons = {}
        for branch, field in BL1_BRANCHES.items():
            for tier, tier_data in enumerate(getattr(layout, field).Tiers):
                for cell, nav in enumerate(tier_data.Skills):
                    if nav is not None:
                        icons[(branch, tier, cell)] = f"menu.{clip}.{frame}.{nav.IconClipName}.{on}.{off}"
        return icons

    def branch_names(self, ctrl: Any) -> dict[str, str]:
        """The player's tree branches' names, as the skill menu shows them ("SNIPER"...: BL1_BRANCH_TEXTS' keys -> the
        game's text), {} until its movie is read. No branch definition has one: the menu's movie sets them, per
        character (tools/probes/probe_bl1_branches.txt; WillowGame.u, its movie, DefaultGame.ini - offline):
        SkillTreeGFxHelper.GetCharacterName() (a switch on its CurrentCharacter, the class's CharacterName: 1 ->
        "mordecai") is the frame its skill clip goes to (SkillTreeGFxDefinition.SkillMovieClip, "skills"); that frame's
        ActionScript sets tree1.text to "$<StringAliasMap:skills_hunter_branch1>"; the alias map
        (WillowUIDataStore_StringAliasMap.MenuInputMapArray, from DefaultGame.ini) has it as
        "<Strings:WillowGame.SkillTreeMovie.SkillsHunterBranch1String>", localized: SNIPER."""
        import unrealsdk  # noqa: PLC0415

        from . import bl1map, gamedir  # noqa: PLC0415

        cache_key = int(ctrl.PlayerClass.CharacterName)
        if (names := self._branch_names.get(cache_key)) is not None:
            return names
        cooked = gamedir.cooked_dir()
        if cooked is None:
            return {}
        clip, frame = self._skill_clip(ctrl)
        texts = bl1map.clip_texts_later(cooked, clip, frame)
        if texts is None:
            return {}  # (being read: asked again at the next read)
        aliases = {str(e.FieldName): str(e.MappedText)
                   for e in unrealsdk.find_class("WillowUIDataStore_StringAliasMap").ClassDefaultObject.MenuInputMapArray}
        localize = unrealsdk.find_class("Object").ClassDefaultObject.Localize
        names = {}
        for branch, field in BL1_BRANCH_TEXTS.items():
            alias = BL1_ALIAS.fullmatch(texts.get(field, ""))
            strings = BL1_STRINGS.fullmatch(aliases.get(alias.group(1), "")) if alias else None
            if strings:
                package, section, key = strings.groups()
                names[branch] = str(localize(section, key, package))
        self._branch_names[cache_key] = names
        return names

    def action_skill_locked(self, pc: Any) -> bool:
        # Its action skill: PlayerSkills[ActionSkillPlayerSkillIndex] (Bloodwing, index 36), Grade 0 until the first
        # skill point unlocks it (probe_bl1_skills.txt: Lv 5, 1 point unspent - the page said "ready")
        return int(pc.PlayerSkills[int(pc.ActionSkillPlayerSkillIndex)].Grade) == 0

    def card_line_value(self, entry: Any, pres: Any, item: Any) -> tuple[float, int] | None:
        # Its card shows the line's modifier, never its attribute's current value (tools/probes/probe_bl1_cards.txt: an
        # SG330's zoom -40, fire rate -0.4318, projectiles 1 -> "4.0x", "+43%", "+1"; the page showed the gun's 20, 0.45,
        # 8): remapped (bValueRemappingEnabled - the zoom's -100..0 onto -10..0), its sign flipped if bDisplayAsInverse
        # (not BL2's reciprocal), x 100 if a percentage, rounded by its RoundingMode - Float: one decimal, a percentage
        # a whole number (the fire rate's 43.18: "+43%").
        import math  # noqa: PLC0415

        from .inspector import _remapped  # noqa: PLC0415

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

    def shop_timer_source(self, world_info: Any) -> Any:
        # The replicated count, a whole number a little ahead of the host's (925 for its 922.85 - probe_bl1_vending.txt):
        # the game showed a few seconds more than the page reading the host's (the user)
        return world_info.GRI

    def presented_decimals(self, pres: Any) -> int:
        # its AttributePresentationDefinition has no FloatPrecision (WillowGame.u, offline): one decimal - the game's
        # SG330 accuracy 6.7 (the user; ours read 7 from the missing property)
        return 1

    def shop_currency(self, machine: Any) -> str:
        # no FormOfCurrency (one currency in the game): dollars - its prices showed bare numbers ("other")
        return "CURRENCY_Credits"

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


class _NotPickedUp:
    """A Borderlands 1 mission not in the player's log, read as a log entry not started (missions._live: Status,
    bHeardKickoff, no progress) - Borderlands1.mission_entries. Offered (the page's "kick", BL2's bHeardKickoff: its
    giver offered it): the game's word - it can be picked up now, the controller's GetMissionEligibility ME_Eligible
    (tools/probes/probe_bl1_tracker.txt: 16 of the 205 not picked up - T.K. Has More Work, each DLC's first...); read
    when asked (the log's full pass: not started ones)."""

    Status = "MS_NotStarted"
    Objectives = ()

    def __init__(self, mission: Any, pc: Any) -> None:
        self.MissionDef = mission
        self._pc = pc

    @property
    def bHeardKickoff(self) -> bool:  # noqa: N802 - (the log entry's field it stands in for)
        return getattr(self._pc.GetMissionEligibility(self.MissionDef), "name", "") == "ME_Eligible"


def make_profile(name: str) -> Profile:
    """The profile of a game, by mods_base's name for it ("BL2", "TPS"...)."""
    if (cls := _PROFILES.get(name)) is None:
        raise RuntimeError(f"Helios Tracker doesn't know the game {name!r}")
    return cls()


def _current() -> Profile:
    import mods_base  # noqa: PLC0415

    return make_profile(mods_base.Game.get_current().name)


GAME: Profile = _current()  # the game running (read as games.GAME, at the time: a test swaps it)
