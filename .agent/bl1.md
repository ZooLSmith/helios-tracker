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
  the shared marker symbols (objective, rstation, poi, transition, player, buddy). The DLCs: `dlcmap1` here, and
  their own `dlcN_maps.upk` / `dlcN_TacticalMaps.upk` (not looked at).
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
  drawn in their colours' average for now.
- **Wired in** (`levelmap.landmark`, the BL1 profile's `map_source`): at an area change, its anchor (a find_all), the
  frame rendered on the map thread, its placement from the anchor and the shape's size - the page's level message as
  BL2's (center, upp, one PF_A8R8G8B8 image).

## Not checked yet

- No `WillowTacticalMapVolume` / `WillowMapInfo` (`GetMapInfo()` None) - BL1 places its map with its anchor.
- From `probe_bl1.txt`, not looked at yet: hooks missing (`WillowScrollingList:HandlePopList`,
  `WillowInteractiveObject:InitializeBalanceDefinitionState`); classes missing (`PlayerSkillTree`,
  `SkillTreeBranchDefinition`, `WillowDamageArea`, `VendingMachineExGFxMovie`, `WillowScrollingList`); the level
  lists (`LevelDependencyList.LevelList`) empty - no level names from them.
- Everything the probe lists: the classes the mod reads (pickups, interactive objects, missions, skills, shops) and
  their fields - so far only the level check, the object scan and the video hook have run into differences.
- **Missions**: built differently from BL2's (the user) - to look at after the map.
- Rarity: BL1 colours gear by level, not BL2's tiers (the page shows the common tiers only for now: game.js `bl1`).
