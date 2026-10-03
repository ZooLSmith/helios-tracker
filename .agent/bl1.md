# Helios Tracker in Borderlands 1

What we know about the mod running in Borderlands 1 - the **original 2009 game** (Steam's "Borderlands", 32-bit
`Binaries/Borderlands.exe`), with the same Python SDK as BL2 (its willow1 build). Like `presequel.md`: each finding
says when it was seen.

## Setup

- The Game of the Year **Enhanced** edition (64-bit, `Binaries/Win64`) was tried first: the user couldn't get the SDK
  running there (2026-10-03). Not registered in `games.py` (mods_base's `BL1E`): the mod refuses to load there.
- The mod declares BL1: `helios_tracker/pyproject.toml` `supported_games` (without it: "incompatible", enabling
  locked). Its profile: `games.py` `Borderlands1`.
- Dev link: `project.json`'s optional `bl1` entry (the install), then `python tools/link_mod.py bl1`. Loading it
  after the game started: `pyexec helios_tracker/reload.py`.
- The SDK's own log: `<bl1>/Binaries/Plugins/unrealsdk.log` (pyunrealsdk v1.10.0 seen); the mod's log is the shared
  one (`helios_tracker/helios_tracker.log`, through the junction: a BL1 session's paths say `...\Borderlands\sdk_mods\...`).
- Probe: `tools/probes/probe_bl1.py` (read-only: env, the hooked functions, the classes the mod uses, the level's map
  info, the player, the main classes' fields, samples) -> `probe_bl1.txt`. Not run yet.

## Differences found (2026-10-03, first runs) - each one in `games.py`

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

- `WillowGame/CookedPC` (BL2: `CookedPCConsole`), the same package tag, **file version 584** (BL2: 832; Enhanced: 594).
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
  (levelmap.landmark), upright. Its placement on the page: the base game's maths - right, the right way up (the user).
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
- **Wired in** (`levelmap.landmark`, the BL1 profile's `map_source`): at an area change, its anchor (a find_all), the
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
  properties (games.py `level_name_in`; BL2 calls GetFriendlyLevelNameFromMapName). The DLCs' lists:
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
  - read as properties (games.py `pawn_name`). No `AIClass` on the pawns.
- **NPCs** (Claptrap): no balance (`BalanceDefinition` None); their own `AIPawnName` ('ClapTrap'; 'None' on most
  enemies) - the made-up name's source (`pawn_raw_name`). Their game name: not found yet.
- **Shields**: no WillowShield class - a `WillowEquipAbleItem`, its definition a plain `ItemDefinition`
  (`gd_shields.A_Item.Item_Shield`); its slot: `ItemDefinition.EquipmentLocation` (`EEquipmentLoc`: EQUIPLOC_Shield,
  EQUIPLOC_MOD - grenade mods, EQUIPLOC_Deck - com decks) -> the inspector's kind (`equip_kind`). Its card stats as
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
  (`mission_entries`, `_objectives`, `_progress`, `_status`, `_number`; no `missionsteps` feature: every objective
  current). The page's mission panel and log.
- **Its waypoints** (5 probe runs: turning one in, picking the next): every WillowWaypoint is bHidden (markers, not
  things). Ready to turn in: its `TurnInWaypointDefinition`'s (WP_Al: 1, at T.K.'s); active: its
  `TargetWaypointDefinition`'s (Buy Grenades, Grenade purchased 0/1 -> WP_WeaponVendor: 1, at the weapon vendor). The
  HUD follows the tracked one (`HUDMovie.CachedTrackedMission`). Built: `collector._waypoint_markers` (feature
  `waypointmarkers`: the waypoint actors collected, as a BL2 co-op client's) - every picked-up mission's, flagged
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
  (VendingMachineGFxMovie) has no shop titles. games.py `vending_class` / `vending_titles`.
  No name of theirs anywhere in its text (the vending menu's: tabs and prompts only; no map header) - the name is on
  their texture: they're named by their definition, as guessed ("Vending Machine Grenades And Ammo ?" - shops.py
  `_named`; the class's gave every machine "Vending Machine ?").
- **Exploding barrels**: no BehaviorProviderDefinition - behaviour sets (`DefaultBehaviorSet`, `ExtraBehaviorSets[]`:
  `InteractiveObjectBehaviorSet` - OnKilled, OnTakeDamage... arrays of behaviours, CustomEvents / TimerEvents /
  CounterEvents of reactions with `Behaviors[]`); the barrel's `Behavior_Explode` (its `Definition.DamageTypeDef` as
  BL2's) is there - games.py `object_behaviors`.

## Item cards, rarities, exits (2026-10-03: probe_bl1_cards.txt, probe_bl1_exits.txt, offline)

- **Rarities**: GlobalsDefinition has only GetRarityColorForLevel (no GetRarityLevelColorsIndexforLevel): its
  `RarityLevelColors[] {MinLevel, MaxLevel, Color}` read as properties (games.py `rarity_table`) - 13 entries: -1..1 /
  2..4 white, 5..10 green, 11..15 blue, 16..49 purple, 50..60 / 61..65 / 66..100 legendary shades, 170 / 171 / 180-190
  the pickups', 500 pearl. game.js `bl1.tierByEntry` - checked against the wiki (common 0-4, uncommon 5-10, rare
  11-15, epic 16-49, legendary 50-60 / 61-65 / 66-100): entry 0 (-1..1) is common, white like entry 1 (a rarity 0
  Tediore shield; it had been BL2's "misc"). The wiki's pearlescent "101+": the table has 500 only (101-169: no
  entry, no tier).
- **Card lines** (WeaponCardModifierStats): the game shows the line's modifier, never its attribute's current value -
  remapped (`bValueRemappingEnabled`: the zoom's -100..0 onto -10..0), its sign flipped if `bDisplayAsInverse` (BL2's:
  a reciprocal), x 100 if a percentage, rounded by its RoundingMode (Float: one decimal, a percentage whole). An SG330:
  zoom -40, fire rate -0.4318, projectiles 1 -> "4.0x", "+43%", "+1" (checked by the user). games.py `card_line_value`
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
  `_skills_from_player_skills`); the action skill locked at Grade 0 (`PlayerSkills[ActionSkillPlayerSkillIndex]`).
  Two columns per branch, the last tier one skill (centered on the page). Its colors (base.css `data-game="bl1"`):
  left slate blue, middle red-brown, right green - the status menu's treeLeft / treeCenter / treeRight fills; their
  greyed part's dims (`--tree-N-dim`) bring each to BL2's grey (~52).
- **Branch names** (games.py `branch_names`): no definition has one - the menu's movie sets them per character.
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
  FFloor(PlayerUseLevelBonus) if the definition's bUsesPlayerLevelRequirement) - games.py `item_card_level`.
  `ManufacturerGradeIndex`: 0 on every item.
- **Skill icons** (games.py `skill_icons`, bl1map `clip_icon`, served as /icon/menu....png): vector clips in the status menu movie - in the skill clip's character frame, each
  cell's clip by the layout's name (ui_skill_tree.upk `SkillTreeLayout`'s SkillTreeNavDefinitions: `IconClipName`
  "icon17" = Left tier 2 entry 1...), its frames "off" / "on" / "none" (`IconOnName`...); the elemental cell (icon1)
  has frames per element. Rendered with swfshape - only what the "on" and "off" frames both place: the drawing (each state has its own
  tile under it, "on"'s notched at the bottom right for the rank - the user: "the background is strange"). `SkillDefinition.ScaleformFrameName`
  is the HUD's popup icons only (GfxHUD.upk sprite 147, 19 skills).
- **Card icons** (games.py `card_icon_png`, bl1map `card_icon`, /cardicon/<kind>/<key>.png as BL2's): no files scan -
  the item card's movie (inworld_ui.upk `weapon_card.weapon_card`), vector sprites, a frame per key: the
  manufacturers' (`FlashLabelName`: "jakobs", "s_and_s"...; Corazza has no frame), its "zippy" (a Claptrap holding
  the gun / item - not used: the user wants the item's icon), the elements' per tech level ("fire0".."shock4": not
  read yet), grenade types, com deck classes. The sprite: the one whose labels hold the most of the kind's keys, then
  the fewest others. The type's icon: the item's silhouette - the clip the game's scripts send to an item's frame,
  always placed as `inicon<N>` (the inventory list's `inventory.selections.inicon1..14`, the mission reward's
  `missions.reward_weap.inicon14`, the vending item of the day's `topLevel_mc.inicon2`), in the menu movie (bl1map
  `item_icon`): frames `WeaponTypeDefinition.ScaleformFrameName` ("repeater"...), items' `WillowInventory.ZippyFrame`
  ("shield", "grenade", "comm" - a property, no GetZippyFrame: games.py `zippy_frame`). Behind each, its kind's shape
  (depth 1, kept from frame to frame: a square behind the weapons - placed with the first frame, "repeater" -, a
  diamond behind mods / class mods / shields, a burst behind grenades / ammo, a circle, an octagon): not drawn, the
  user's call - only what the frame shows that no other frame does (drawn as the frames place them, the pistol had
  its square, the sniper not).
- **Element icons** (games.py `element_frame`, bl1map `card_frame_icon`): no ElementalFrame - the card's clip placed as
  "chemical" (beside "manufacturer", "zippy", "protean" - the grenade's type -, "comm"), 21 frames: exp0-4, shock0-4,
  fire0-4, corr0-4, none (the element, its tech level: "x2", "x4" - a level's frame places only that, the mark kept
  from the element's first: drawn with what earlier frames left). An item's frame number: its instance data's
  `FlashTechFrame` (`GetTechIconFrame()`, script - probe_bl1_elements.txt: an Explosive MIRV 1.0 = exp0, others 0 =
  none). A weapon's: no instance data - its damage type's `DamageType` (EDamageType: Unknown, Incindiary [sic], Shock,
  Explosive, Corrosive, Impact, Healing - not the clip's order: games.py `BL1_ELEMENT_FRAMES`, by the frames' art)
  and its tech level (`StaticGetWeaponDamageType` / `StaticCalculateWeaponTechLevelForUI`, static, its DefinitionData
  their input - each returns (value, that input)): the frame "<element><level>" - The Clipper "fire1", its card's
  flame and x1 (the user). The number: a layer the level frames add over the mark (an explosive grenade, exp0: none)
  - left out of the page's icon (the mark alone: what the frame keeps from its element's first), the level a stat
  of its own instead, "Element level x1" (games.py `element_level`: the weapon's tech level, an item's
  CalculateItemTechLevel) - the user: as BL2, no number on it.
- **Looted containers** (games.py `is_looted`): no SimpleAnimState / SimpleAnimInfo; `bCanBeUsed` a flag (BL2's an
  array: `bCanBeUsed[0]` failed, never looted) - False once looted (probe_bl1_looted.txt; a toilet not searched: True).
- **Quest givers' "!"** (probe_bl1_givers.txt; games.py `object_directives`, `mission_offered`): a giver's missions
  are on the object itself, `WillowInteractiveObject.MissionDirectives` (BL2's: `io.Directives.MissionDirectives`) -
  the bounty board's 15, Dr. Zed's 11 (a WillowInteractiveNPC). Its log has only the missions picked up, so "can be
  picked up" is the game's word: the controller's `GetMissionEligibility(mission)` ME_Eligible (script: minimum
  level, dependencies, status) and not in the log (a mission taken is eligible too: the board's Bandit Presence).
  The board's T.K. Has More Work: eligible, in its `AnnouncedMissions` - the game's "!". Turn-ins: the log, as BL2's.
- **Barrels' element icons**: a damage type's icon is its element's mark (`damage_type_frame`: "exp0") - not
  learned from the weapons (BL2's `.cache/element_frames.json`: a BL1 weapon's "fire1" had been saved as Incindiary's,
  the BL2 barrels' table - the feature `learnedelements`, not BL1's).
- **Missions not picked up** (probe_bl1_tracker.txt; games.py `mission_entries`, `_NotPickedUp`): the log has only
  the missions picked up, the tracker's MissionList only the active one (its 166 MissionObservers: the level's
  mission objects) - but every MissionDefinition is loaded (218: base game and the four DLCs). The log reads the
  player's entries then every other one, not started (BL2's log lists the whole playthrough so): dependencies,
  the mission tree, "available" as BL2's; its giver the game's `MissionGiver` text. Offered (`kick`): the game's
  `GetMissionEligibility` (16 eligible of 205: T.K. Has More Work, Keep Your Insides Inside, each DLC's first...).
  The "!" stays the game's word alone (mission_offered), not the log's dependencies.
- **A mission's area** (games.py `mission_home`): no TravelStation (all fell in "other" - the user) - its waypoints'
  level: the turn-in's (`TurnInWaypointDefinition.PersistentLevelName`, usually its giver: T.K. Has More Work's
  WP_Al), else the target's, named by the level lists (as the map's title). `GameStageRegion`: a technical name only.
- **Objective markers: a path** (probe_bl1_waypoints.txt): a waypoint definition's WillowWaypoints are numbered
  (`WaypointNumber`, 0 a single one) and passed (`bCompleted`) - the game shows the next one, the lowest number not
  done (Bone Head's Theft's WP_Checkpoint: #1 done, #2 shown; the page had both - "Digistruct Module:" twice, the
  user). The same number twice: alternatives, both (T.K.'s Food's two #3).
