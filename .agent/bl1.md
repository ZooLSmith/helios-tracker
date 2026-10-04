# Helios Tracker in Borderlands 1

What we know about the mod running in Borderlands 1 - the **original 2009 game** (Steam's "Borderlands", 32-bit
`Binaries/Borderlands.exe`), with the same Python SDK as BL2 (its willow1 build). Like `presequel.md`: each finding
says when it was seen.

## Setup

- The Game of the Year **Enhanced** edition (64-bit, `Binaries/Win64/BorderlandsGOTY.exe` - mods_base's `BL1E`) was
  tried first: the user couldn't get the SDK running there (2026-10-03: the SDK's issue). Supported since 2026-10-04 -
  BL1's profile (`Borderlands1Enhanced`: its executable a folder deeper): checked offline first, BL1's decoders on its
  files (offline_check with project.json's `bl1e`) - the same layout (`WillowGame/CookedPC`, `Maps/`), the same maps
  (Arid's frame 463 x 906 as the original's), fonts, menu / card / item icons; its packages' version 594 (licensee 58)
  read by BL1's reader - one difference: an enum property's tag names its enum, as BL2's (its HD textures: the
  pickup icons 2048 x 2048, ~7 s to decode once, cached). In game (the user got the SDK running, 2026-10-04): it
  works exactly as the original, with higher-res assets.
- The mod declares BL1: `helios_tracker/pyproject.toml` `supported_games` (without it: "incompatible", enabling
  locked). Its profile: `games/bl1/` (`Borderlands1`: BL2's parts, its own where its way differs - `profiles.md`).
- Dev link: `project.json`'s optional `bl1` entry (the install), then `python tools/link_mod.py bl1`. Loading it
  after the game started: `pyexec helios_tracker/reload.py`.
- The SDK's own log: `<bl1>/Binaries/Plugins/unrealsdk.log` (pyunrealsdk v1.10.0 seen); the mod's log is its own
  (`helios_tracker/helios_tracker_bl1.log`, `helios_crash_bl1.log` - one per game since 2026-10-03; before, the shared
  `helios_tracker.log`: a BL1 session's paths say `...\Borderlands\sdk_mods\...`).
- Probe: `tools/probes/probe_bl1.py` (read-only: env, the hooked functions, the classes the mod uses, the level's map
  info, the player, the main classes' fields, samples) -> `probe_bl1.txt`. Not run yet.

## Differences found (2026-10-03, first runs) - each one in its profile (`games/bl1/`)

- **ui_utils 1.3**: no `show_coop_message` / `hide_coop_message` (the mod's import failed: "cannot import name
  'hide_coop_message'"). The updater's bottom-left message: its `show_hud_message` instead (goes away by itself).
- **WorldInfo**: no `GetStreamingPersistentMapName` (AttributeError). The map name: the world info's path's first part
  (`menumap.TheWorld:PersistentLevel.WorldInfo_0`).
- **ClientPlayBinkMovie**: hooked fine, no `bForceNoSkip` argument (AttributeError). The video seen
  (`VoG_Transition_Movie`, 70.2 s from its Bink header - the same header as BL2's) and shown on the page.
- **No `WorldDiscoveryArea` class** ("Couldn't find class"): no discovery areas, no fog of war (the `discovery`
  feature off).
- **Game folder**: `Binaries/Borderlands.exe` (one level up to the game, BL2's `Binaries/Win32/` two):
  collector.py `game_dir()` looks at both.

## Game files

- `WillowGame/CookedPC` (BL2: `CookedPCConsole`), the same package tag, **file version 584** (BL2: 832; Enhanced: 594,
  read too - Setup).
  Levels are `.umap` files (`Maps/<area>/..._P.umap`), not `.upk`. Read by `upk_bl1.py` (`Bl1Package`); the
  profile's `packages` still None until the map is wired in (no fonts / icons scan on BL1).
- **Packages (offline, 2026-10-03)**: the summary as BL2's minus the import / export GUID fields (no
  `ImportExportGuidsOffset` / counts before 623, the thumbnail table offset kept); compression flags 2 = LZO, the
  same chunk format - but a chunk not worth compressing is **stored raw** (its compressed size = its size, no chunk
  tag): BL2 never does. Tagged properties: a BoolProperty's value is 4 bytes (1 from 673), a ByteProperty has no enum
  name (from 633). An actor's data starts with its state frame (two refs, an 8-byte probe mask, a 2-byte latent
  action, an empty state stack, a code offset: 26 bytes) then its NetIndex - properties at 30. (All of it:
  `upk_bl1.py`, tested by offline_check when `bl1` is set.)

## The map screen (offline, 2026-10-03)

- **Where a level says its map**: one `LevelLandmarkAnchor` actor per persistent level (27 in the base game's
  `W_*_P` / arena levels), properties `Texture` (`Env_TacticalMaps.Arid.arid-arena`), `TextureSizeX` / `Y` (1024),
  `Opacity` (0.005-0.2), **`MapFrame`** (`"arid_arena"`), `DLCMap`, and its `Location` / `DrawScale` / `DrawScale3D`
  (scales all over the place: 13, 115, (58.2, 233.1, 161) - not the map's scale as such). `LevelLandmark` /
  `SubLevelLandmark` actors: the map's points of interest.
- **What's drawn - vector shapes**: the menu movie `menus_ingame_redux.upk` `FlashMovies.status_menu` (GFx, 700 KB,
  uncompressed package): sprite 1132 has one frame per area, labeled with the anchors' `MapFrame`s ("none", "arid",
  "arid_arena", ... "trash", "dlcmap1"), each placing that area's sprite: **one DefineShape4, a solid `#294d5d` fill**
  (the walkable area's silhouette - Arid: 780 x 352 movie px, 523 edge runs; New Haven 545 x 503 + a `#82adca` line).
  Rasterized, its edges are the texture's painted lines (magenta borders, yellow buildings, the cyan road): the
  textures are the top-down renders the shapes were traced on, at a low opacity at most. The "arid" frame also places
  the shared marker symbols (objective, rstation, poi, transition, player, buddy). The DLCs: their anchors'
  `MapFrame` is "dlcmap1" (the menu's slot) and their `DLCMap` a movie of its own (`dlc2_maps.dlcmap_lobby`, in
  `DLC/DLCn/...`): its root places the area's clip ("themap") - drawn the same way (bl1map `_render_dlc`). The
  Underdome lobby's anchor is turned 179.5 degrees with DrawScale3D -7.0: a half turn = the scale's signs flipped
  (its world part's map_source), upright. Its placement on the page: the base game's maths - right, the right way up (the user).
- **Map textures**: `Packages/Environments/Env_TacticalMaps.upk` (27 Texture2D, DXT1, 1024 x 512 / 1024, the top mip
  inline as an LZO chunk - bulk flag 0x10).
- **World -> map**: the map tab's code, `WillowGFxHelperMap` (WillowGame.u): `Anchor` (the level's anchor),
  `CoordScale`, `Transform`, `AnchorSize`, `ViewSize`, `MapObjects[]` ({TransformedLocation, Angle, Landmark,
  Player...}), set up by `InitMapFrameVars` / `InitMapFrame`.
- **Arid, measured** (`tools/probes/probe_bl1_map.txt`, the map open once, 2026-10-03): 27 map objects with their world
  spot and `TransformedLocation` (0-1 across the map). A least-squares fit is exact (max error 0.0006):
  `u = 8.377e-6 Y + 0.5834`, `v = -1.857e-5 X + 0.0256` (cross terms ~2e-8: the anchor's yaw 32). So the map is the
  world turned 90 degrees (map x = world +Y, map y = world -X), **~153 uu per movie px** on both axes (u x ClipSize.X,
  v x ClipSize.Y; `ClipSize` 779.5 x 352.2 = the area shape's bounds: the rendered image is that 0-1 frame).
  The anchor (Location -28388.7, -10012.0; DrawScale3D 58.2, 233.131; texture 1024 x 512) fits partly: the map's width
  = 512 x 233.131 (exact), its height = 1024 x 58.2 / CoordScale.Y (1.107 = ClipSize's aspect / AnchorSize's), the
  anchor at u 0.5 - but v 0.553, not 0.5.
- **The placement, modeled** (`bl1map.placement`, no fitting): the anchor's texture is a quad centered on it,
  TextureSize x DrawScale x DrawScale3D world units, u along +Y, v along -X; the shape was traced on it from its
  top-left corner at k = max(clip / texture size) movie px per texel (that also gives the game's CoordScale: 1, 1.1066
  for its 1.107; and the 0.553). Against the 27 objects: within 0.0005 of the map; through the page's one `upp` and
  no yaw, 1.2 movie px. offline_check checks it on five of them.
- **Which area**: the world is `Loader` in every area (`tools/probes/probe_bl1.txt`): the area is streamed in, the
  first of the world info's `StreamingLevels` a `LevelStreamingPersistent` (`PackageName` 'arid_p'), then its
  sublevels (`LevelStreamingKismet`: arid_env, Arid_Firestone...). Its one LevelLandmarkAnchor is in it
  (`arid_p.TheWorld:PersistentLevel.LevelLandmarkAnchor_0`). `WorldInfo.GetMapName` / `GetPersistentMapName` exist
  (not called).
- **Drawn as an image like BL2's** (the user's call: the page's map layer unchanged): `bl1map.py` renders the frame's
  shapes (`swfshape.py`: each fill style's border = the edges with it on one side only - the raw edge runs, filled
  even-odd as they come, came out striped) into one BGRA image in the map sprite's px. All 26 base-game frames render
  (0.3-1.4 s). What a frame shows = what it places itself: the "arid" frame also places the markers' templates
  (labeled sprites), and they stay in the frames after it - skipped. Gradient fills (arid_bunker, interlude2, trash)
  drawn in their colours' average for now (Not checked yet: never seen in game).
- **Its lines** (the user: "it seems to lack lines"): the shapes start new style lists mid-way, their lines in them -
  Fyrestone Coliseum's 1081: 126 of its 217 edges stroked (2 px #294d5d, 0.75 px #4a8bb5, 1.25 px #82adca: the
  outlines, the inner details); Arid's 1045: 1384, and a second fill (#346376). A first look at a shape's styles only
  read its first list (fills only). swfshape.py draws them as Flash layers them: list by list, its fills then its
  lines (a quad per piece, round joins: a nonzero fill - their union). 0.5-1.7 s a map.
- **Wired in** (its world part's `map_source`, `games/bl1/world.py`): at an area change, its anchor (a find_all), the
  frame rendered on the map thread, its placement from the anchor and the shape's size - the page's level message as
  BL2's (center, upp, one PF_A8R8G8B8 image).

## Not checked yet

- **The maps with gradient fills** (arid_bunker, interlude2, trash - 3 of the 26 base-game frames): not seen in game
  yet, so what they should look like isn't known. swfshape.py reads their gradient records (linear / radial / focal:
  a matrix, colour stops) but fills each shape with its stops' average colour - a flat tone where the game may
  show a fade. Look at one of those areas in game (its map screen) before drawing real gradients (each pixel's
  colour from the gradient's matrix and stops) - it may not be worth it. Deferred (the user's call: to revisit later).
- No `WillowTacticalMapVolume` / `WillowMapInfo` (`GetMapInfo()` None) - BL1 places its map with its anchor.
- From `probe_bl1.txt`, not looked at yet: hooks missing (`WillowScrollingList:HandlePopList`,
  `WillowInteractiveObject:InitializeBalanceDefinitionState`); classes missing (`PlayerSkillTree`,
  `SkillTreeBranchDefinition`, `WillowDamageArea`, `VendingMachineExGFxMovie`, `WillowScrollingList`). (Its
  "LevelList={}" was the probe's printer: an unrealsdk array has a `_type` - printed as an empty struct.)

## Level names (offline, 2026-10-03)

- `gd_globals.General.LevelList` (a LevelDependencyList, `gd_globals.upk`): `LevelList[]` = 28 entries {PersistentMap
  'arid_p', LevelName 'Arid Badlands', SecondaryMaps, ConnectedPersistents, LoadingMovieName 'loading_arid',
  CompletedQuestStat...} - Skag Gully, Headstone Mine, New Haven, ... ('arid_intro_p' is 'Arid Badlands' too). Read as
  properties (`world.level_name_in`; BL2 calls GetFriendlyLevelNameFromMapName). The DLCs' lists:
  `dlcN_PackageDefinition.Levels.LevelList`.
- The map screen's "THE ARID BADLANDS": the menu movie's own ActionScript (`_parent.zone = "THE ARID BADLANDS"` in its
  "themap" frames) - hard-coded English; the level list's is the game's localized text.
- Everything the probe lists: the classes the mod reads (pickups, interactive objects, missions, skills, shops) and
  their fields - so far only the level check, the object scan and the video hook have run into differences.
- **Missions**: built differently from BL2's (the user) - to look at after the map.
- Rarity: BL1 colours gear by level, not BL2's tiers (the page shows the common tiers only for now: game.js `bl1`).

## Pawns, items, pause, missions (2026-10-03: tools/probes/probe_bl1_names.txt, probe_bl1_pause.txt)

- **Enemy names**: `BalanceDefinitionState {BalanceDefinition, GradeIndex}`; the AIPawnBalanceDefinition's `Grades[]` =
  `AIPawnGameStageGradeWeightData {GradeModifiers: AIPawnGradeModifierData {ExpLevel, DisplayName...}}` - no BL2
  PlayThroughs. `WillowAIPawn.GetTargetName` (script: its bytecode reads BalanceDefinitionState, calls
  GetDisplayNameAtGrade(GradeIndex), "(none)", the mastered form `MasteredDisplayName` "%s's %n" with PlayerMasterPRI)
  - read as properties (`pawns.name`). No `AIClass` on the pawns.
- **NPCs** (Claptrap): no balance (`BalanceDefinition` None); their own `AIPawnName` ('ClapTrap'; 'None' on most
  enemies) - the made-up name's source (`pawn_raw_name`). Their game name: not found yet.
- **Shields**: no WillowShield class - a `WillowEquipAbleItem`, its definition a plain `ItemDefinition`
  (`gd_shields.A_Item.Item_Shield`); its slot: `ItemDefinition.EquipmentLocation` (`EEquipmentLoc`: EQUIPLOC_Shield,
  EQUIPLOC_MOD - grenade mods, EQUIPLOC_Deck - com decks) -> the inspector's kind (its items part's `kind`). Its card stats as
  BL2's: `UIStatModifiers` = [ShieldMaxValue 50, ShieldOnIdleRegenerationRate 7.5] (gd_AttributePresentation.Shields).
  `ItemCardModifierStats` empty.
- **Pause**: the escape menu sets `WorldInfo.Pauser` (the PRI); the status menus (inventory, map, skills) don't - they
  set `WorldInfo.bStatusMenuOnly` (and the controller's `bStatusMenuOpen`, `QuickAccessScreen` CS_Inventory / CS_Map /
  CS_Skills): the world stops (`world_paused`). The shops' timer runs on in them (the user) - shops.py keeps Pauser.
- **Missions**: the tracker's `MissionList` = MissionDefinitions (the active ones), `ActiveMission`; no BL2
  MissionWaypoints. A MissionDefinition: MissionName, MissionSummary, MissionDescription, `MissionGiver` (a string:
  'T.K. Baha'), `Objectives[] {StatId, ObjectiveCount, ProgressMessage}`, `TargetWaypointDefinition`,
  `TurnInWaypointDefinition`, Dependencies, NextMissionInChain, PlotMissionNumber, bPlotCritical. The markers: the
  level's `WillowWaypoint` actors, each a `WaypointDefinition` (WP_SkagPearls...) and a `WaypointNumber` - the active
  mission's target / turn-in definition's.
- **The player's missions** (probe_bl1_missions.txt, a mission ready to turn in): `pc.MissionPlaythroughData[]` =
  `MissionPlaythroughInfo {PlayThroughNumber, ActiveMission, MissionList}` - 3 entries (all PlayThroughNumber 0: the
  playthrough played is `GRI.HostCurrentPlaythrough`); its MissionList: only the missions the player has,
  `{MissionDef, Status, Objectives: [{StatId, CurrentAmount}]}` (a done one: Objectives empty). `EMissionStatus`:
  NotStarted, Active, ReadyToTurnIn, Complete, **Redeemed** (turned in). No objective steps: the HUD lists them all
  ("Stolen Food: 4/4", then "Turn in" - the user). Read by missions.py's MissionLog, unchanged, through the profile
  (`mission_entries`, `_objectives`, `_progress`, `_status`, `_number`; its `current_objectives`: every objective
  current). The page's mission panel and log.
- **Its waypoints** (5 probe runs: turning one in, picking the next): every WillowWaypoint is bHidden (markers, not
  things). Ready to turn in: its `TurnInWaypointDefinition`'s (WP_Al: 1, at T.K.'s); active: its
  `TargetWaypointDefinition`'s (Buy Grenades, Grenade purchased 0/1 -> WP_WeaponVendor: 1, at the weapon vendor). The
  HUD follows the tracked one (`HUDMovie.CachedTrackedMission`). Built: its missions part's `markers` (its
  `level_lookups`: the waypoint actors collected, as a BL2 co-op client's) - every picked-up mission's, flagged
  tracked. A definition with several (the food's 4 WP_SkagPearls, numbers 1, 2, 3, 3): all of them - which the game
  shows while in progress: not seen.
- **Hooks**: `WillowGameViewportClient:Tick` doesn't exist (BL1: `Engine.GameViewportClient:Tick`) - the updater's
  one-shot reload (`RELOAD_HOOK`) takes the profile's `tick_function` - an update installed and reloaded by itself
  (the user: `use_sdkmod.bat bl1`, `fake_release.py bl1`).

## Objects (2026-10-03: probe_bl1_npc.txt, offline)

- **NPCs you talk to are objects**: `WillowInteractiveNPC` (Dr. Zed `gd_MissionNPCs.DrZed`, T.K. Baha, the villagers)
  - an `InteractiveNPCDefinition`, its `DisplayName` empty even at run time (and the bounty boards'): the game has no
  name on them ("Dr Zed ?" is the rule's guess). The page's NPC layer, drawn as the NPC pawns' ring (model.js
  objectCategory: their class). Claptrap's "talk" object's definition (`gd_ClapTrap.NPC.NPC_ClapTrapFirestone`) has
  one, "Claptrap"; its pawns (4 in Arid: `gd_ClapTrap.Character.Pawn_NPCClapTrap`) none. The one not seen in game
  (the user: near X -5231, Y 44076): the bus stop's, `Arid_BusStop...WillowAIPawn_9`, **bHidden True** - parked for a
  later scene. The collector now skips hidden pawns, every game's (not a player: hidden while respawning). (Firestone's
  two, both seen: the one following the player - a matinee group, on the navigation network - and a settler parked up
  on a mesh with no collision, Z 744: `probe_bl1_hidden.txt`.) That settler is a **green Claptrap inside a wall** (the
  user, with noclip: drawn, its LastRenderTime fresh; its own body material) - a leftover in the level, really there:
  the map shows it, rightly.
- **Chests**: their balances `gd_Balance_Treasure.ChestGrades.ObjectGrade_TreasureChest` (3 grades) / `_Awesome` /
  `_Custom` / `_Custom_Rider`, `ObjectGrade_StrongBox*`, `ObjectGrade_Crate_Metal*`, lootables (Cashbox, Dumpster,
  Toilet...); no DisplayName stored in their grades. The big red chest: `InteractiveObj_TreasureChest` (up to 6 items:
  Chest Weapons Pistols / Long Guns, Chest Ammo) - its tier from its definition (game.js `chestByDefinition`; BL2's are
  in its loot lists' names). StrongBox / Crate_Metal: not seen yet.
- **Loot on the ground appears late** (the user, 2026-10-03): BL1 spawns an area's pickups when the player comes near
  (its sublevels streamed in - Arid_Firestone, arid_tunnel... - and their spawners), BL2 has more of them with the
  level. The map shows what exists (the scan, the pickup spawn hook): not a bug. Showing them earlier would be guessing
  the game's rolls - no.
- **Vending machines** (probe_bl1_vending.txt, Fyrestone's 3): `WillowVendingMachine`, right under
  WillowInteractiveObject - no WillowVendingMachineBase (shops.py looked for it: not a shop, the page's container view).
  The rest is BL2's: `ShopInventory` a 30-slot array (items, then None - an offline read had shown its element type),
  `FeaturedItem`, `ShopType` SType_Items / SType_Health / SType_Weapons, `GetSellingPriceForInventory`; the timer
  `Game.SecondsUntilShopsReset` (922 s) / `GRI.SecondsUntilShopsReset`, no `ShopTimerRate` (1). Its menu
  (VendingMachineGFxMovie) has no shop titles. Its profile's `vending_class` / `vending_titles`.
  No name of theirs anywhere in its text (the vending menu's: tabs and prompts only; no map header) - the name is on
  their texture: they're named by their definition, as guessed ("Vending Machine Grenades And Ammo ?" - shops.py
  `_named`; the class's gave every machine "Vending Machine ?").
- **Exploding barrels**: no BehaviorProviderDefinition - behaviour sets (`DefaultBehaviorSet`, `ExtraBehaviorSets[]`:
  `InteractiveObjectBehaviorSet` - OnKilled, OnTakeDamage... arrays of behaviours, CustomEvents / TimerEvents /
  CounterEvents of reactions with `Behaviors[]`); the barrel's `Behavior_Explode` (its `Definition.DamageTypeDef` as
  BL2's) is there - `objects.behaviors`.
- **New-U / fast travel stations** (tools/probes/probe_object_text.txt, 2026-10-04): `EmergencyTeleportOutpost` objects -
  definitions `gd_emergencyteleportoutpost.OutpostDefinition`, `CheckpointOutpostDefinition` (two kinds, likely: fast
  travel, New-U checkpoint). No name of theirs in the game's data: the object's `OutpostName` empty, the definition's
  `DisplayName` empty, no function of their own for one (only every interactive object's - `GetTargetName`, called:
  nothing). Named by their definition, as guessed ("Outpost Definition ?"); shown as stations by their class (game.js
  `stationClasses` - no station word in their names).
- **The player's class name** (probe_player_text.txt, probe_bl1_class_alias.txt, its localization files - 2026-10-04): no
  identifier definitions (BL2's player info -> CharacterNameIdDef -> CharacterClassId): the page said "Mordecai ?". The
  globals' `GD_Globals.General.Globals.PlayerCharacters[]` = {CharacterClassName "Hunter", DefaultCharacterName
  "Mordecai"}, localized (gd_globals.INT `[General.Globals GlobalsDefinition]`: Roland 0 Soldier, Mordecai 1 Hunter,
  Lilith 2 Siren, Brick 3 Berserker - the load character menu's words, the user), by the class's `CharacterName` (1 for
  Mordecai) - `pawns.class_name`. (The skill menu's "HUNTER": the alias map's skills_hunter_class - its capitals.)

## Item cards, rarities, exits (2026-10-03: probe_bl1_cards.txt, probe_bl1_exits.txt, offline)

- **Rarities**: GlobalsDefinition has only GetRarityColorForLevel (no GetRarityLevelColorsIndexforLevel): its
  `RarityLevelColors[] {MinLevel, MaxLevel, Color}` read as properties (`items.rarity_table`) - 13 entries: -1..1 /
  2..4 white, 5..10 green, 11..15 blue, 16..49 purple, 50..60 / 61..65 / 66..100 legendary shades, 170 / 171 / 180-190
  the pickups', 500 pearl. game.js `bl1.tierByEntry` - checked against the wiki (common 0-4, uncommon 5-10, rare
  11-15, epic 16-49, legendary 50-60 / 61-65 / 66-100): entry 0 (-1..1) is common, white like entry 1 (a rarity 0
  Tediore shield; it had been BL2's "misc"). The wiki's pearlescent "101+": the table has 500 only (101-169: no
  entry, no tier).
- **Card lines** (WeaponCardModifierStats): the game shows the line's modifier, never its attribute's current value -
  remapped (`bValueRemappingEnabled`: the zoom's -100..0 onto -10..0), its sign flipped if `bDisplayAsInverse` (BL2's:
  a reciprocal), x 100 if a percentage, rounded by its RoundingMode (Float: one decimal, a percentage whole). An SG330:
  zoom -40, fire rate -0.4318, projectiles 1 -> "4.0x", "+43%", "+1" (checked by the user). `items.card_line_value`
  (the line's "dv" / "dp": the page shows them as is).
- **Rounding**: its presentations have no FloatPrecision (one decimal: the accuracy's 6.7); `ATTRROUNDING_IntCeil` (its
  damage: AttrPresent_WeaponDamage - 85.2 shows 86), `ATTRROUNDING_IntFloor` (magazine, projectiles).
- **Game text**: HTML entities in it ("S&amp;S Munitions"): decoded (inspector._localized).
- **Exits**: `PersistentTransitionLandmark {FromMapName, ToMapName}` (Engine.u), one by each map changer
  (gd_MapChangeObjects.Default_MapChanger - no destination of its own: the level's scripting). A mission whose
  waypoint definition is in another area (its PersistentLevelName) is marked on the exit leading there (the user: the
  game's marker on the map changer).

## Skills, item levels, icons (2026-10-03: probe_bl1_skills.txt, probe_bl1_branches.txt, probe_bl1_levels.txt, offline)

- **Tree**: no PlayerSkillTree - the controller's `PlayerSkills[]` and `SkillTreeBranches[]` (inspector
  its skills part's `_player_skills`); the action skill locked at Grade 0 (`PlayerSkills[ActionSkillPlayerSkillIndex]`).
  Two columns per branch, the last tier one skill (centered on the page). Its colors (base.css `data-game="bl1"`):
  left slate blue, middle red-brown, right green - the status menu's treeLeft / treeCenter / treeRight fills; their
  greyed part's dims (`--tree-N-dim`) bring each to BL2's grey (~52).
- **Branch names** (`skills._read_branch_names`): no definition has one - the menu's movie sets them per character.
  `SkillTreeGFxHelper.GetCharacterName()` (script: a switch on CurrentCharacter, a CharacterNames like
  `PlayerClass.CharacterName` - 0 roland, 1 mordecai, 2 lilith, 3 brick; called on one we construct) is the frame
  its clip (`SkillTreeGFxDefinition.SkillMovieClip`: "skills", the status menu's sprite 934) goes to; that frame's
  ActionScript sets `tree1.text = "$<StringAliasMap:skills_hunter_branch1>"` (bl1map `clip_texts`: the frame's literal
  assignments); `WillowUIDataStore_StringAliasMap.MenuInputMapArray` (DefaultGame.ini) maps it to
  `<Strings:WillowGame.SkillTreeMovie.SkillsHunterBranch1String>`, `Object.Localize` gives SNIPER (DEU SCHARFSCH.,
  ESN TIRADOR...). tree1 / 2 / 3 sit under treeLeft / Center / Right. The clip's first frame is "roland_combat"
  (no "roland": Roland's gotoAndStop leaves it there, soldier keys).
- **Item levels**: the card shows the level the item needs, not its ExpLevel (6 -> 4):
  `WillowInventory.GetControllerPlayerExpLevelRequiredToUse(controller)` (Engine.u, script: ExpLevel +
  FFloor(PlayerUseLevelBonus) if the definition's bUsesPlayerLevelRequirement) - `items.card_level`.
  `ManufacturerGradeIndex`: 0 on every item.
- **Skill icons** (`skills._read_skill_icons`, bl1map `clip_icon`, served as /icon/menu....png): vector clips in the status menu movie - in the skill clip's character frame, each
  cell's clip by the layout's name (ui_skill_tree.upk `SkillTreeLayout`'s SkillTreeNavDefinitions: `IconClipName`
  "icon17" = Left tier 2 entry 1...), its frames "off" / "on" / "none" (`IconOnName`...); the elemental cell (icon1)
  has frames per element. Rendered with swfshape - only what the "on" and "off" frames both place: the drawing (each state has its own
  tile under it, "on"'s notched at the bottom right for the rank - the user: "the background is strange"). `SkillDefinition.ScaleformFrameName`
  is the HUD's popup icons only (GfxHUD.upk sprite 147, 19 skills).
- **Card icons** (`assets.card_icon_png`, bl1map `card_icon`, /cardicon/<kind>/<key>.png as BL2's): no files scan -
  the item card's movie (inworld_ui.upk `weapon_card.weapon_card`), vector sprites, a frame per key: the
  manufacturers' (`FlashLabelName`: "jakobs", "s_and_s"...; Corazza has no frame), its "zippy" (a Claptrap holding
  the gun / item - not used: the user wants the item's icon), the elements' per tech level ("fire0".."shock4": not
  read yet), grenade types, com deck classes. The sprite: the one whose labels hold the most of the kind's keys, then
  the fewest others. The type's icon: the item's silhouette - the clip the game's scripts send to an item's frame,
  always placed as `inicon<N>` (the inventory list's `inventory.selections.inicon1..14`, the mission reward's
  `missions.reward_weap.inicon14`, the vending item of the day's `topLevel_mc.inicon2`), in the menu movie (bl1map
  `item_icon`): frames `WeaponTypeDefinition.ScaleformFrameName` ("repeater"...), items' `WillowInventory.ZippyFrame`
  ("shield", "grenade", "comm" - a property, no GetZippyFrame: `items.zippy_frame`). Behind each, its kind's shape
  (depth 1, kept from frame to frame: a square behind the weapons - placed with the first frame, "repeater" -, a
  diamond behind mods / class mods / shields, a burst behind grenades / ammo, a circle, an octagon): not drawn, the
  user's call - only what the frame shows that no other frame does (drawn as the frames place them, the pistol had
  its square, the sniper not).
- **Element icons** (`items.element_frame`, bl1map `card_frame_icon`): no ElementalFrame - the card's clip placed as
  "chemical" (beside "manufacturer", "zippy", "protean" - the grenade's type -, "comm"), 21 frames: exp0-4, shock0-4,
  fire0-4, corr0-4, none (the element, its tech level: "x2", "x4" - a level's frame places only that, the mark kept
  from the element's first: drawn with what earlier frames left). An item's frame number: its instance data's
  `FlashTechFrame` (`GetTechIconFrame()`, script - probe_bl1_elements.txt: an Explosive MIRV 1.0 = exp0, others 0 =
  none). A weapon's: no instance data - its damage type's `DamageType` (EDamageType: Unknown, Incindiary [sic], Shock,
  Explosive, Corrosive, Impact, Healing - not the clip's order: `items.BL1_ELEMENT_FRAMES`, by the frames' art)
  and its tech level (`StaticGetWeaponDamageType` / `StaticCalculateWeaponTechLevelForUI`, static, its DefinitionData
  their input - each returns (value, that input)): the frame "<element><level>" - The Clipper "fire1", its card's
  flame and x1 (the user). The number: a layer the level frames add over the mark (an explosive grenade, exp0: none)
  - left out of the page's icon (the mark alone: what the frame keeps from its element's first), the level a stat
  of its own instead, "Element level x1" (`items.element_level`: the weapon's tech level, an item's
  CalculateItemTechLevel) - the user: as BL2, no number on it.
- **Looted containers** (`objects.is_looted`): no SimpleAnimState / SimpleAnimInfo; `bCanBeUsed` a flag (BL2's an
  array: `bCanBeUsed[0]` failed, never looted) - False once looted (probe_bl1_looted.txt; a toilet not searched: True).
- **Quest givers' "!"** (probe_bl1_givers.txt; `objects.directives`, `mission_offered`): a giver's missions
  are on the object itself, `WillowInteractiveObject.MissionDirectives` (BL2's: `io.Directives.MissionDirectives`) -
  the bounty board's 15, Dr. Zed's 11 (a WillowInteractiveNPC). Its log has only the missions picked up, so "can be
  picked up" is the game's word: the controller's `GetMissionEligibility(mission)` ME_Eligible (script: minimum
  level, dependencies, status) and not in the log (a mission taken is eligible too: the board's Bandit Presence).
  The board's T.K. Has More Work: eligible, in its `AnnouncedMissions` - the game's "!". Turn-ins: the log, as BL2's.
- **Barrels' element icons**: a damage type's icon is its element's mark (`damage_type_frame`: "exp0") - not
  learned from the weapons (BL2's `.cache/element_frames.json`: a BL1 weapon's "fire1" had been saved as Incindiary's,
  the BL2 barrels' table - its items part's `learn_element` does nothing).
- **Missions not picked up** (probe_bl1_tracker.txt; `missions.entries`, `_NotPickedUp`): the log has only
  the missions picked up, the tracker's MissionList only the active one (its 166 MissionObservers: the level's
  mission objects) - but every MissionDefinition is loaded (218: base game and the four DLCs). The log reads the
  player's entries then every other one, not started (BL2's log lists the whole playthrough so): dependencies,
  the mission tree, "available" as BL2's; its giver the game's `MissionGiver` text. Offered (`kick`): the game's
  `GetMissionEligibility` (16 eligible of 205: T.K. Has More Work, Keep Your Insides Inside, each DLC's first...).
  The "!" stays the game's word alone (mission_offered), not the log's dependencies.
- **A mission's area** (`missions.home`): no TravelStation (all fell in "other" - the user) - its waypoints'
  level: the turn-in's (`TurnInWaypointDefinition.PersistentLevelName`, usually its giver: T.K. Has More Work's
  WP_Al), else the target's, named by the level lists (as the map's title). `GameStageRegion`: a technical name only.
- **Objective markers: a path** (probe_bl1_waypoints.txt): a waypoint definition's WillowWaypoints are numbered
  (`WaypointNumber`, 0 a single one) and passed (`bCompleted`) - the game shows the next one, the lowest number not
  done (Bone Head's Theft's WP_Checkpoint: #1 done, #2 shown; the page had both - "Digistruct Module:" twice, the
  user). The same number twice: alternatives, both (T.K.'s Food's two #3).
- **Gear on the ground**: the page's gear test goes by class (model.js `isGear`) - BL1's shields, grenade mods, com
  decks are one class, `WillowEquipAbleItem` (game.js `bl1.gearClasses`; its `WillowUsableItem`: ammo, health, not
  gear). Without it an "Explosive Bouncing Bettie" showed as "Equip Able Item ?", no rarity, no card (the user). The
  collector's own test (inspector.is_gear) goes by kind: its items part's `kind` already made it gear.
- **Fonts** (files/bl1fonts.py, formats/swffont.py; its assets part's job, at boot): the menus' movies import their fonts (their own
  DefineFont3 tags: 0 glyphs) from a library, `Packages/Fonts/Fonts_en.upk`'s movie `Fonts_en`: WillowBody (the
  page's text font, BL2's too), WillowHead (its headings), Brush Script Std - 1284 glyphs each, standard SWF
  DefineFont3 (tag 75; BL2's: Scaleform's compacted 1005) - read by swffont.py (twips: / 20, EM 1024), written as
  TrueType by gamefonts.to_ttf, by gamework's "swffont" job (cached on disk); the catalogue set when a page
  connects (no scan). Fonts_en only (no other language's library in the install).
- **In a vehicle** (probe_bl1_driving.txt; `pawns.local`, `vehicle_name`): the controller's `MyWillowPawn` is
  None, its `Pawn` the vehicle (`WillowVehicle_WheeledVehicle`) or the seat (a turret: `WillowWeaponPawn`) - the
  local player is that pawn's `Driver`; their pawn has no player info meanwhile: the controller's (inspector
  read_players). Before: the page lost track of the player, listed them as "Player", twice getting out. Its
  vehicles: no VehicleDef / GetCustomizableName (their record failed: none on the page) - `DisplayName` /
  `VehicleNameString`, both "" in its .int: the "?" name.
- **Map exits** (`objects.exit`; the record's `exit`, the page's "Exit to {area}" - model.js nameText):
  its map changers (`gd_MapChangeObjects.Default_MapChanger`, `Vehicle_MapChanger_Arid`) carry no destination - the
  level's script does: an event of theirs (SeqEvent_Used / Touch, its `Originator` the changer) leads through its
  output links to a `WillowSeqAct_PrepareMapChangeFromDefinition`, its `DefaultMap` the map (W_Arid_P.umap,
  offline: 6 - Dry_P, Arid_SkagGully_P, Arid_Mine_P, interlude_1_p with bAllowVehicles, Arid_Arena_Coliseum_P,
  Arid_Cave_P); named by the level lists. No "Exit to" text in BL1: the page's words. Its
  PersistentTransitionLandmarks (FromMapName / ToMapName) stand by the changers: the missions' exit markers.
- **Shop restock timing (open)**: the game said "shop has new inventory" while the page's countdown showed 0:05
  (the user) - 5 s late; BL2's is off by about a second either way. Not looked into - notes.md "Restock: not exact".
- **Layers** (game.js `bl1.noLayers`; model.js layerInGame): what BL1 doesn't have, from its script and packages
  (offline): no eridium (no such currency), no vault symbols (IO_VaultRoy), no buffs (shrines, buff drinks,
  Moxxtails), no slot machines (the user: none) - their layers hidden. Area names, fog of war: the feature
  `discovery`, not BL1's (no WorldDiscoveryArea). Its mission items are usable items (`WillowUsableItem`, no
  WillowMissionItem class) whose definition says `bMissionItem` (Z0_MissionData's ID_SpareVendingPart "Power
  Coupling", presentation MissionObject): util.pickup_kind reads the flag - the mission pickups' layer, not "other".
- **Objects switched off without being hidden** (collector._out_of_sight): an object's behaviours can hide its mesh
  (Behavior_ChangeVisibility: its components' `HiddenGame`) and leave the actor's `bHidden` False - BL1's T.K.'s Food
  (Z0_MissionData.MissionObjects.MO_TKsFood, its MissionItemDefinition ID_TKsFood: used, the food picked up; then
  unusable, its StaticMeshComponent hidden - tools/probes/probe_bl1_mission_objects.txt). Out of sight: hidden, or
  every mesh component hidden in game (an object without a mesh: as its actor) - at the object scan (every 120 s).
  Related: BL2's mission items placed ahead (notes.md, the pizzas: missions.js missionItemWanted - drawn only
  while their objective / mission matters). Open: BL1's mission pickups (bMissionItem, no MissionItemDefinition's
  MissionDirective / AssociatedMissionObjective seen) may not carry what missionItemWanted reads - ones placed
  ahead would show early; not seen yet.

## Pickup icons (2026-10-04: probe_bl1_pickup_icons.txt, offline)

- **The same as BL2's**: a pickup's `ItemDefinition.PickupFlagIcon` (`WillowInventoryDefinition`'s) - `FX_Items.Textures.Credits`,
  `.Health`, `.Ammo_SMG`, `.Ammo_Repeater`... (47 textures, DXT5 128 x 128) in `Packages/effects/FX_Items.upk`. The
  collector sent their paths all along (`fi`); with no files scan nothing served them (the page showed no symbol).
  `games/bl1/files/bl1textures.py`: a texture by path - its package found by the path's first part anywhere under
  CookedPC, the export by the rest (a package names its exports without itself: `Textures.Credits`) - served at
  `/texture/<path>.png` like BL2's (`Bl1Assets.serve`). A weapon's pickup has no `ItemDefinition` (its
  `DefinitionData` is a weapon's): no flag icon, as in BL2.
