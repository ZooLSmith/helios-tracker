# Helios Tracker - research notes

## Tactical map data (on disk)

Per level, in the persistent package `<Map>_P.upk` (e.g. `Sanctuary_P.upk`, `SouthernShelf_P.upk`):

| Object | Notes |
|---|---|
| `SwfMovie UI_TacticalMap_<Level>.<Map>_P` | ~1 KB CFX movie: `DefineExternalImage2` (id u32, format, target w/h, export name, file name `<Map>_P_I1.tga`), a `DefineShape` with a clipped bitmap fill of that image, `PlaceObject2` at identity; fog-of-war blobs imported from `SharedWillowTacMaps`. `TextureRescale = Mult4`. |
| `Texture2D UI_TacticalMap_<Level>.<Map>_P_I1` | PF_DXT5, 1 mip, NeverStream, stored inline (bulk flags 0). Sanctuary 468x512 (declared 465x512), Southern Shelf 876x1024 (declared 874x1024). |
| `WillowTacticalMapVolume_0` (actor in `TheWorld.PersistentLevel`) | `UnrealUnitsPerPixel` (class default 32, not overridden), `NorthOffsetInDegreesClockwise` (default 0). Its brush bounds are much larger than the map image: only the bounds *centre* matters. |
| `SharedWillowTacMaps` | fog-of-war textures + movie, cooked into each level's package: the "fog of war blob" sprite (frame `tacMap`: a 256 px shape filled with `fog-of-war-blob t`, 64 x 64 A8R8G8B8, a soft dark blue-grey cloud; `miniMap`: the minimap's), registering itself with the map screen (`RegisterFogOfWarBlob`). |

Texture2D native tail after the tagged properties: 16 bytes (BL2 specific), mip count, then per
mip: bulk header (flags, element count, size on disk, offset in file), data, SizeX, SizeY.

Actor exports start with a 22-byte state frame before the NetIndex + tagged properties (plain
objects start with the 4-byte NetIndex).

## Runtime (probe_map.py, in game)

- `WorldInfo.GetStreamingPersistentMapName()` / `GetMapName(False)` -> `Sanctuary_P`.
- `WorldInfo.GetMapInfo()` -> `WillowMapInfo` (`MyMapInfo` is None): `TacticalMapMovie`,
  `TacticalMapVolume`, `FrontEndMovieDef`.
- Volume `BrushComponent.Bounds` = Origin (-3072, -10240, 4096), BoxExtent (23552, 22528, 8192)
  for Sanctuary; (48241, -30596) for Southern Shelf.
- `HUDWidget_Minimap`: `UnrealUnitsPerPixel = 128`, `WorldRadius 6000`, `bPlayerRelative` = the
  minimap rotation lock (True = rotates with the view), `MapClip` (GFxObject: `_x _y _rotation
  _xscale _yscale` readable with `GetFloat`; `GetDisplayInfo` needs an out param).

## Transform fit (probe_map2.py)

The minimap keeps the player at its origin: player movie px = S^-1 R(-rotation) (-(_x, _y)).
Least squares against world X/Y:

| Level | Minimap | Samples | Max residual | Scale | Origin vs volume bounds centre |
|---|---|---|---|---|---|
| Sanctuary | rotating | 79 | 0.065 px | 127.95 / 128.03 uu/px | matches |
| Southern Shelf | locked | 80 | 0.034 px | 127.97 / 127.99 uu/px | ~10 uu off |

=> `movie x = (Y - c.Y) / 128`, `movie y = -(X - c.X) / 128`; 128 = volume UnrealUnitsPerPixel (32)
x 4 (matches the movie's Mult4 rescale). The formula never reads the minimap.

**Non-zero `NorthOffsetInDegreesClockwise` - it doesn't turn the map: geo.js no longer uses it** (2026-09-25: the
user saw the markers all wrong in The Dust with the rotation; fixed - confirmed by the user on the page, The Dust). **What it's for**: the only script reading it is
`StatusMenuMapGFxObject.Init`, which copies it into the map screen's `MapYawOffset` - it turns the pause menu's map
view (cosmetic; the image stays world-aligned). **The page does the same** (2026-09-25, geo.js `mapTurn` -> view.js /
draw.js `S.view.rot`, never the positions): S.view.rot = +north, i.e. the image turns **counterclockwise** by the
offset on screen - the sign checked against the game's map screen in The Dust (the first guess, clockwise, was
backwards). Rotate-with-heading, while following, still overrides it. The evidence (offline: the nav
mesh fitted onto the map image at every angle, see "Level geometry for a 3D map"): 5 base game levels set one -
Grass_Cliffs_P 180, HyperionCity_P 325, Luckys_P -90, PandoraPark_P 170, Interlude_P 90. On the first four the image
fits the world **unrotated** (97-98 % of the nav mesh on drawn pixels; every other angle <= 72 %), while geo.js rotates
positions by it. Interlude_P fits best at 270-285 (92 % vs 73 % unrotated) - unclear. **The Dust in game**
(probe_navwalk 2026-09-25, runtime centre 8288, 13659, north 90, upp 32; tools/probe_navwalk_thedust.txt): with the
true centre the page's rotation (+90) is the worst fit (40.8 % of the nav mesh on drawn pixels) vs unrotated 68 %,
-90 71.5 %, best single angle 73 % (315) - no clean fit on this map (Sanctuary: 98 %), part of its nav mesh isn't
drawn; the movie places its image unrotated (no rotation in PlaceObject / the bitmap fill). 26 positions on foot
all on player collision or terrain; its streaming like Southern Shelf's (all Kismet loaded, `_Px` not). To confirm in game before
changing geo.js: tools/probe_navwalk.py + check_navwalk.py compare both with the runtime centre (the page rotates
clockwise by it - unverified), or several map images (`_I2`...; handled, unverified).

## Script API found in the packages (names only, verify in game)

- Pawn: `GetHealth`, `GetMaxHealth`, `IsEnemy`, `IsFriendly`, `GetOpinion`, `GetTargetName`,
  `bIsDead`, `Allegiance`; `WillowAIPawn.AIClass`.
- `WillowPickup.InventoryRarityLevel` (int), `bPickupable`, `.Inventory`;
  `WillowInventory.GetShortHumanReadableName`, `GetRarityLevel`, `RarityLevel`.
- `WillowInteractiveObject`: `GetHumanReadableName`, `GetTargetName`, `GetHealth`, `Allegiance`.
- `LevelDependencyList.GetFriendlyLevelNameFromMapName` (localized level names - not used yet).
- `StatusMenuMapGFxObject.PlaceCustomObjective` (map screen waypoint - possible page -> game feature).

## World scale (probe_scale.py, in game)

Player pawn (Salvador, the Gunzerker: 1.62 m tall per the wiki): collision cylinder half height 80
(160 uu tall), radius 42, BaseEyeHeight 56 (eyes 136 uu above the feet), mesh bounds 152 uu tall, run
speed 440 uu/s, JumpZ 630. 152-160 uu for 1.62 m: **~100 uu per metre, 1 uu = 1 cm** (not UE3's
usual 50 / 2 cm, which made heights look doubled). The page and the inspector use 100.

## Display names (localized properties)

Localized properties hold the game's text in its current language at runtime (on disk:
`WillowGame/Localization/<LANG>/*.<lang>`; the INT files mostly hold overrides, English is in the
packages). Used by the mod (unverified in game):

| Technical | Display text |
|---|---|
| world object (`IO_FireBarrel`) | `io.BalanceDefinitionState.BalanceDefinition.DefaultDisplayName` ("Incendiary Barrel") |
| weapon type (`WT_SMG_Hyperion`) | `WeaponTypeDefinition.Typename` |
| manufacturer | `ManufacturerDefinition.Grades[ManufacturerGradeIndex].DisplayName` |
| name parts (prefix / title) | `WeaponNamePartDefinition` / `ItemNamePartDefinition.PartName` |
| item types | `Shield/GrenadeMod/Artifact/ClassMod/UsableItemDefinition.ItemName` |
| skills | `SkillDefinition.SkillName` / `SkillDescription` |

Not used yet: `InteractiveObjectDefinition.StatusMenuMapInfoBoxHeader` / `...Description` (map
screen info box), `AttributePresentationDefinition.Description` / `Prefix` / `Suffix` (item card stat
lines, `$NUMBER$` placeholders) - the card stats idea (backlog).

Item parts have no display name: their package group names their role (`GD_GrenadeMods.
DamageRadius.DamageRadius_Normal`, `GD_Shields.Battery.Battery1_Tediore`, `GD_ClassMods.
Specialization...`, `GD_Artifacts.Upgrade...`); the page labels parts by it (`role.*` keys) and
tidies the name ("Normal", "Tediore").

## Ground pickups: what tells them apart (probe_pickups.py, in game, 2026-09-23)

58 pickups in Ice_P (Southern Shelf area). Non-gear pickups are all `WillowUsableItem` (ECHO logs:
`WillowMissionItem`, `WillowPickup.bIsMissionItem`, `bPickupable` False); the difference is in the
item's `DefinitionData.ItemDefinition` (a `UsableItemDefinition`):

| kind | definition (package) | `Presentation` (InventoryCardPresentationDefinition) | `inv.ItemFrame` |
|---|---|---|---|
| ammo | `GD_Ammodrops.Pickups.AmmoDrop_<type>` | `GD_InventoryPresentations.Definitions.WeaponAmmo_<Weapon>` / `GrenadeAmmo` | `ar` `smg` `pistol` `shotgun` `sniper` `grenade` |
| health | `GD_BuffDrinks.A_Item.BuffDrink_HealingInstant` | `...Definitions.Health` | `'0'` |
| cash | `GD_Currency.A_Item.Currency` / `Currency_Big` | `...Definitions.Credits` | `money` |
| eridium | `GD_Currency.A_Item.EridiumStick` | `...Definitions.Credits` (shared with cash!) | ? |

- Every currency shares the `Credits` presentation: the definition's `FormOfCurrency` tells them
  apart (`CURRENCY_Credits` / `CURRENCY_Eridium`; seen in game, tools/probe_eridium.py). Other
  currencies (Seraph crystals, Torgue tokens: not seen yet) go to "other".

- Also consistent per kind: `PickupFlagIcon` (`fx_shared_items.Textures.ItemCards.Health` / `Credits` /
  `Ammo_<type>`), `DroppedImpact` (`GD_Impacts.Loot.Loot_Drop_Ammo` / `_Health` / `_Cash`),
  `ExternalAttributeEffects[].AttributeToModify` (ammo: the weapon's `D_Attributes.AmmoResource_*`
  pool; cash: `D_Attributes.Currency.CreditsOnHand`), `OnUseConstraints` (health: HealthCurrentValue).
- `ItemDefinition.ItemName` is localized ("Munitions pour mitraillette", "Argent", "Médecine
  d'urgence !") - `GetShortHumanReadableName` is empty for cash and sometimes for health.
- The made-up rarity levels: `ItemDefinition.BaseRarity.BaseValueConstant` (health 171, cash 181,
  ammo 0).
- A pickup lying in an opened container has `Base` = that `WillowInteractiveObject` (e.g. a Locker).
- Mission items (2026-09-23, Tundra Express: an ECHO log dropped by a `PawnBalance_TundraPatrol`):
  `WillowMissionItem` with `MissionItemString` 'Mission Item' (what its short name gives - the page
  showed that), `ItemName` 'Data Log' (the real one), RarityLevel 500; its `MissionItemDefinition`:
  `MissionDirective` = the mission it gives (`M_NoHardFeelings`; the pickup has `bIsMissionDirector`),
  `AssociatedMissionObjective` (the objective it's for; None here), `bMissionWaypoint`. The collector:
  the definition's name, `ms` {mission id, name, "gives" / "for"} - tooltip + a link in the details.
- Mission items are placed ahead (user, 2026-09-23: pizzas, neither pickable nor visible yet, showed
  on the map): the page draws one only while it matters (missions.js missionItemWanted) - "for" (its
  objective `oi`): the mission picked up and that objective in the current step, not done; "gives":
  the mission not started. No link / mission not in the log: drawn. Seen right in game (the pizzas).
- Customization items (skins / heads) are gear: `WillowUsableCustomizationItem`, a real `RarityLevel`
  (2 on a vehicle skin), `ItemFrame` `customization_vehicle`, card `Customization_VehicleSkin`.

## Mission log (probe_quests.py, in game, 2026-09-23)

- `MissionTracker.MissionList` (287 entries in a normal-mode playthrough): `{MissionDef, Status,
  ObjectivesProgress, ActiveObjectiveSet, SubObjectiveSets, bInitialized, bHeardKickoff, bFiltered}`.
  `Status` = `EMissionStatus`: `MS_NotStarted` (0), `MS_Active` (1), `MS_RequiredObjectivesComplete`
  (2), `MS_ReadyToTurnIn` (3: seen, every objective done, its step `bCanCompleteMission`), `MS_Complete`
  (4) (tools/probe_turnin.txt); 5 (failed?) not seen - the page shows unknown names as the game's.
  2 and 3 = the page's "ready" (to turn in: green).
  `ObjectivesProgress[i]` = count of `MissionDef.ObjectiveDefs[i]` (empty before the mission starts).
- **The objectives' order** (the Pre-Sequel's "Marooned", 2026-09-26 - the user: "Throw breaker" first in game,
  "Pick up digistruct key" last; the page had ObjectiveDefs' order): each step orders its own. A step is a
  `MissionObjectiveSetDefinition` (InitialObjectiveSet, then each set's NextSet - bAutoEnableNextSet), its
  `ObjectiveDefinitions` in the game's order; the mission's standing goals are in every set (Marooned: KillDead,
  RetrievePart in all 12), so there's no one global order (a chain walk by first appearance gives ObjectiveDefs'
  order back - tried, dropped). The current step's order is the collector's "cur" (its sets' objectives, in order):
  missions.js objectiveStates puts the current ones in that order, in the slots they take.
- `MissionDefinition`: `MissionName`, `MissionDescription`, `MissionSummary`, `TurnInDescription`,
  `MissionGiver`, `MissionTurnInLocation` (localized; `[place]...[-place]` markup), `bPlotCritical`
  (story), `MissionNumber`, `GameStage`, `Dependencies` (missions), `NextMissionInChain`,
  `ObjectiveDefs`, `ObjectiveSetDefs`, `InitialObjectiveSet`, `bRepeatable`, `bCanBeFailed`,
  `Reward` / `AlternativeReward` (XP / cash as attribute-based multipliers, `RewardItems`,
  `RewardItemPools`; the numbers the game shows: `MissionDefinition.GetExperienceReward(pc, bAlt)` /
  `GetCurrencyReward(pc, bAlt)` / `GetCurrencyRewardType(bAlt)` - tools/probe_rewards.txt; the XP
  attribute's own `GetValue(pc)` gives the 0.1 multiplier, not the XP), `bEnableAltReward`,
  `TravelStation` / `TurnInStation` (FastTravelStationDefinition: the area, e.g. "Three Horns -
  Divide": `StationDisplayName` - tools/probe_mission_areas.txt; also `StationSign`, sometimes
  longer: "Windshear Waste - Claptrap's Place"; LevelTravelStationDefinition has it too; the
  regions (`GameStageRegion`) have no text), `DlcExpansion`.
- Besides `Dependencies`: `MissionDefinition.ObjectiveDependency = {Objective, Status}` (an objective of
  another mission; `EODS_Complete`: it must be done; None on the missions dumped). The collector sends
  `wait` (that objective's text + mission) for a not-started mission whose Dependencies are done while
  it isn't (that mission's progress, last pass: no function call); the page: locked. Why added: "Mine, All Mine" showed
  as unknown / doable with its Dependencies done, but couldn't be picked up (user, 2026-09-23) - that
  it's this field is NOT verified: if it still shows after a reload, dump that mission's definition.
  Also seen, unused: `SeasonalAvailabilityTime` (FTAT_Always), `MarketingUnlock`.
- `MissionList[].bHeardKickoff`: false on missions not started (probe); taken as "offered" (the
  game shows an undiscovered mission as "Inconnu") - to confirm in game.
- `MissionObjectiveSetDefinition`: `ObjectiveDefinitions`, `NextSet`, `bCanCompleteMission`.
  `MissionObjectiveDefinition`: `ProgressMessage` (localized), `ObjectiveCount`, `bObjectiveIsOptional`.
- `tracker.GetMissionStatus(mission)` works; `GetCurrentObjectives` / `GetObjectivesProgress` have
  out params (not needed: the list has it all).


## Respawning (probe_respawn.py, in game, 2026-09-23, during the New-U effect)

- The player pawn stays (same object), `bHidden` True, parked by the game somewhere (seen: Z -184462;
  the user has seen it high up too - never assume where), full health, `IsInjured()` False.
- `WillowPlayerPawn.bAwaitingInjuredRespawn` True (`bIsAwaitingRespawn` / `bAwaitingRespawn`
  False at that moment), `AwaitingRespawnResurrectLocation` = where they come back,
  `AwaitingRespawnTravelStation` = the `ResurrectTravelStation` (New-U); also the camera path
  (`AwaitingRespawnStart/EndCameraLoc`), `AwaitingRespawnLerpTime` (3 s).
- The collector: hidden + one of those flags = respawning; the spot sent instead of the parked
  position (`rs` 1), or `rs` 2 (no spot: not drawn / followed). The downed overlay says
  "Crippled" or "Respawning".
- Crippled (probe_respawn.txt, while down): `WillowPawn.InjuredState` = `INJURED_Targeted`
  (`INJURED_Not` otherwise, respawning too), `IsInjured()` True, `GetHealth()` 0; `InjuredStartTime`
  + `InjuredBaseDelay` (12 s): a countdown if wanted. The collector sends `dn` 1 when
  `InjuredState` isn't `INJURED_Not` (the page's empty-bars rule is only a fallback).
- Dead (after FFYL runs out, before the respawn): `InjuredState` still `INJURED_Targeted`, but
  `InjuredDeadState` = `INJUREDDEAD_InitRagdoll` (`INJUREDDEAD_None` while crippled),
  `bInjuredDeadCameraActive` True, the pawn visible where it died, `bIsDead` False. The collector
  sends `dd` 1 (dead: faded, grey ring, "Dead") instead of `dn` then.

## In a menu (probe_menu.py, in game, co-op host with 3 others, 2026-09-23)

- `PlayerReplicationInfo.bGFxMenuOpen` (a byte, 0 / 1): 1 while the player has any GFx menu open -
  seen flip for every player (host and the 3 others), so replicated to the host at least.
- `WillowPlayerPawn.bViewingStatusMenu` (+ `bViewingThirdPersonMenu`): True together with it while
  that menu is the status menu (inventory, map, skills...). One `bGFxMenuOpen` without it (another
  menu: vendor / pause? not identified).
- Only on your own controller: `QuickAccessScreen` (`CS_Inventory`...), `bViewingThirdPersonMenu`; the
  open movie `StatusMenuExGFxMovie`.
- The collector sends `mn` 1 when either is set (players only). Not verified yet: on a co-op client
  (both look replicated), and which menus besides the status menu set `bGFxMenuOpen` (pause, vendor,
  chat).

## Loading screens (probe_loading.py, in game, solo host, 2026-09-24)

One load seen (the main menu -> Sanctuary, `Loader` in between; no fast travel / level change in
co-op yet):
- **Start**: `WillowPlayerController:WillowClientShowLoadingMovie(MovieName='SanctuaryAir_P',
  bShowMovie=True, ...)` (-> `WillowShowLoadingMovie`), right after `ClientFindPlayMovie(LevelName=)`.
  `MovieName` = the map being loaded. Then the travel: `WorldInfo:ServerTravel('Loader?listen')`,
  `PreClientTravel(bIsSeamlessTravel=True)`, `SeamlessTravel`, `NotifyLoadedWorld('Loader')`,
  `ClientPrepareMapChange(<map>, bFirst..bLast)`, `RestartPlayer` / `Possess` (the pawn is back
  before the screen goes), `ClientCommitMapChange`, `PostCommitMapChange`.
- **End**: `WillowClientDisableLoadingMovie()`, then `WillowClientShowLoadingMovie(MovieName='',
  bShowMovie=False)`: ~2 s after the start here.
- The game renders **no frame** during it (a 2.2 s gap; PostRender stops): the collector can't send
  anything meanwhile, but a hook on the start can publish right away (server threads keep serving).
  The controller changes (new `WillowPlayerController_N`) and the PRI too (`SeamlessTravelTo`).
- PRI fields (`bReadyToPlay`, `bWaitingPlayer`, `bIsInactive`, `bOnlySpectator`...): none moved;
  `bSaveGameLoaded` False -> True (first load only?). `pc.bCinematicMode` True until ~4 s after.
- Others' loading (co-op): not seen. Those are `Client*` functions, so on the host they're probably
  also called on each remote player's controller (sent to their game): the same hook would see
  them, with `obj` = their controller. On a co-op client, probably only your own. To verify.

## Areas, level names, where to go (probe_area.py, in game, Ice_P, 2026-09-23)

- The level's name as the game shows it (the map screen's): `LevelDependencyList
  .GetFriendlyLevelNameFromMapName(map)` - `GD_Globals.General.LevelList` for the base game ("Ice_P" ->
  "Three Horns - Divide"; its `LevelList[]` = {PersistentMap, LevelName, ConnectedPersistents...}),
  one list per DLC (`GD_AlliumPackageDef.AlliumTG_LevelList`: Hunger_P "Gluttony Gulch"...), each
  answering "" for the others' maps; "Ice" (no _P) -> "". The collector asks each list (cached per
  map); none: the made-up name, marked raw.
- `TravelStationDefinition` (Fast / Level): `StationDisplayName`, `StationSign`, `StationLevelName` (its
  map: "Sanctuary_P", "Hunger_P"), `DlcExpansion`, `PreviousStation`. A mission's `TravelStation` is where
  it comes from (its giver's: Name Game -> Sanctuary, done in Three Horns), `TurnInStation` where to
  hand it in (None: back at its own). Level actors `FastTravelStation.TravelDefinition` (Ice_P: IceEast).
- Where a step is done: `MissionObjectiveSetDefinition.StationOverride` / `MissionObjectiveDefinition
  .StationOverride` (tools/probe_quests.txt: a "Go to Sanctuary" step -> Sanctuary, a later one ->
  IceEast; mostly None).
- `pc.GetLevelForMission(mission)` -> a map name: the tracked Name Game -> `Ice_P` (where it's done;
  its TravelStation is Sanctuary, its giver's). Seen once; for ready / not started not tried.
- **Game crash, 2026-09-23 22:28** (Tundra Express, ~8 min after a reload, right after an ECHO log
  that starts a mission was found): access violation writing 0x0 at `Borderlands2.exe+0x2582` (the
  engine's own fatal-error crash), called from Python in a hook (stack: unrealsdk hook > pyunrealsdk >
  python > pyunrealsdk > game). No Python error logged. The new per-pass function calls were
  `pc.GetLevelForMission` (every active mission, every pass incl. the 1 s fast one) and
  `tracker.IsMissionObjectiveComplete`: both removed (not proven the cause) - where to go now comes
  from station overrides only, objective dependencies from the log's progress data. It crashed again
  (22:34, same game stack, ~2.5 min after a reload without those two): not them. Still called:
  `GetFriendlyLevelNameFromMapName` (once per map); the area level (GetGameStageFromRegion, a few per
  full pass: removed, then back - innocent).
  Next: faulthandler (util.start_log) writes the Python traceback of a native crash to
  `helios_crash.log` - the line that called into the game.
  **Found (3rd crash, 22:41, helios_crash.log):** `_publish_state` > `_pawn_info` > `call_str` - the
  pawn name functions (`GetTargetName` / `GetMapDisplayName` / `GetTransformedName`, old code) on some
  pawn in Tundra Express. Now: the balance's `PlayThroughs[].DisplayName` read as a property
  (collector.pawn_display_name; the names seen right in game, user 2026-09-23). The two calls removed
  after the 1st crash were innocent.
  Rule: prefer property reads; a new function call in a loop = a crash risk, keep them rare and cached.
- The collector sends, for active missions, where to go (`go`): the step's objective / step station
  override (GetLevelForMission no longer: see the crash below); the page's whereTo: that (active; none:
  no place shown), the turn-in station (ready), its own station (not picked up: where to grab it).
- Not tried: `FindActiveStationsForLevel`.
- **The area's level** (probe_region.py, Tundra Express, player 14): no "current region" anywhere (pc,
  pawn, world / game / replication info). `pc.RegionGameStages[]` = {RegionDef, GameStage,
  PlaythroughIdx} (83: every region seen); `pc.GetGameStageFromRegion(region)` (-1: not visited). This
  map's 5 missions all use `GD_GameStages.Zone1.Tundra` -> 13; the enemies here 12-15 (mostly 14).
  Shown under the level's name ("Area level 13": the stages of this map's missions'
  `GameStageRegion`s, `lv` [min, max] in the level payload, after each full mission pass). Removed
  during the crash hunt, back once the crash was found elsewhere (the pawn name functions).

## Mission level (probe_mission_level.py, in game, 2026-09-23)

- A picked-up mission's level: `MissionDefinition.GameStage` with `bGameStageLocked` True (set then:
  "Cette ville est trop petite" 3, "En route vers Sanctuary" 6, player 8 -> 160 / 733 XP). Not picked up:
  `GameStage` 0, not locked - the game prices it at its region's stage meanwhile (an endgame zone's
  mission: 6548 XP at level 8): its reward isn't final until picked up.
- `GlobalsDefinition` (`GD_Globals.General.Globals`): `LevelDifference_Impossible 5 / Hard 3 / Tough 1 /
  Normal -3` (the mission log's difficulty: mission level - player's; below Normal: trivial).
  `ExpScaleByLevelDifference` (lower: 0.9 0.7 0.4 0.15 0.05 0.01 for 1..6) is the ENEMY kill XP
  scale - missions don't match it (160 XP at -5 would mean 3200 full). The mission curve:
  tools/probe_mission_xp_curve.py (below).
- **The XP curve** (probe_mission_xp_curve.txt, player level 8): a mission's XP (and cash) depends on
  its own level only - `GameStage` of a picked-up (locked) mission: 1: 53, 2: 132, 3: 241, 4: 378,
  5: 543, 6: 733, 7: 948, 8: 1187, 9: 1450, 10: 1736, 12: 2376, 14: 3104 (XPReward_04_Large) -
  smooth, no break around the player's level: NO penalty for outlevelling (unlike enemy kills).
  `ExpLevel` / `GetExpLevel()` unused (0). Not picked up: the level follows the region's (27 for an
  Eridium Blight one), writing GameStage does nothing (recomputed). So: a mission's XP is fixed once
  picked up (its share of the player's level shrinks as they level); a not-picked-up one keeps
  following its region (up to the region's max). Not verified: whether the PLAYER's level changes a
  locked mission's reward (only the mission's level was swept) - the co-op host comparison would.
- Functions: `MissionDefinition.GetExpLevel / GetGameStage / GetExpectedGameStage`,
  `pc.GetGameStageFromRegion(region)`, `pc.GetLevelForMission(mission)` (a map name?) - not called yet.

## Vending machines (offline, WillowGame.upk / Startup.upk + probe_vending.py in game, 2026-09-25)

- **Contents are per machine**: every `WillowVendingMachine` actor (base `WillowVendingMachineBase`, an
  interactive object) has its own `ShopInventory` (array of `WillowInventory`), `FeaturedItem` (the item of the
  day) + `FeaturedItemPickup` (the one shown in the glass), `LastInventoryResetTime`, and its own loot
  configurations (`InventoryConfigurationName`, `FeaturedItemConfigurationName`, `FeaturedItemGameStage` /
  `AwesomeLevel` / `CommerceMarkup`), set by its `PopulationFactoryVendingMachine`. `ShopType` (weapons, items,
  health, black market), `FormOfCurrency`. Crazy Earl is `WillowVendingMachineBlackMarket`: its items are built
  per player (`CreateNecessaryBlackMarketItems`, `BuildUpgradeItemForPlayer`).
- **The timer is global**: `WillowGameInfo.LastShopResetTime` / `SecondsUntilShopsReset` / `ShopTimerRate`
  (an attribute with a modifier stack) on the host, replicated as `WillowGameReplicationInfo.SecondsUntilShopsReset`
  / `ShopTimerRate` (`SecondsUntilShopTimerResend`, `SHOP_TIMER_RESEND_RATE`: the host resends it).
  `GlobalsDefinition.MinutesBetweenShopResets` = 20 (class default, `GD_Globals.General.Globals` keeps it).
  Paid resets exist in the script (`GetResetCost`, `ServerPlayerResetShop`, `Globals.ShopResetCost`).
- The menu (`VendingMachineExGFxMovie`) only shows it: `UpdateTimeRemaining` every `VendingMachineRefreshRate`
  = 0.5 s, "ITEM OF THE DAY" / "Time is running out!" labels.

In game (probe_vending.py, Sanctuary_P, solo listen server, 2026-09-25): **confirmed per machine**. 9 machines
(3 `SType_Items`, 2 `SType_Weapons`, 3 `SType_Health`, 1 black market, in 5 groups - all real, the user confirmed), every item a distinct object
(`Owner` = its machine), no item in two machines, each its own featured item. On the host:
- `ShopInventory` is a fixed 30-slot array: the items first (7-12 here), then `None`s - skip them. Items are the
  usual inventory objects (`WillowWeapon`, `WillowShield`, `WillowGrenadeMod`, `WillowClassMod`, `WillowUsableItem`
  = shop ammo `GD_ItemGrades.Ammo_Shop.*`), with `GetShortHumanReadableName`, `RarityLevel`, `DefinitionData`
  (`BalanceDefinition`, `ManufacturerGradeIndex` = the item level: 7-9 at game stage 9).
- `FeaturedItem` can be any inventory kind (a weapons machine featured a Mechromancer skin,
  `WillowUsableCustomizationItem`). `FeaturedItemPickup` read None (the glass display: not spawned / not near?).
- The black market has an empty `ShopInventory` and no `FeaturedItem` until opened (built per player).
- Timer: `GRI.SecondsUntilShopsReset` 1169 at `TimeSeconds` 139, the machines' `CreationTime` 108.85: it started at
  1200 (20 min) when the level loaded. `Game.LastShopResetTime` and every `LastInventoryResetTime` read 0 (no reset
  yet). `ShopTimerRate` 1, empty modifier stack. When it expires: "Shops have new inventory!" (`NewShopInventory`, 5 s).
- The timer stands still while the game is paused (`WorldInfo.Pauser`: the page's count went on, then jumped back
  at each resend - the user, 2026-09-25): the `shoptimer` payload says `paused`, the page holds it.
- Price: `GetSellingPriceForInventory(InventoryForSale, WPC, Quantity) -> int` (called since: the menu's prices); markup from
  `CommerceMarkup` (`GD_Economy.VendingMachine.Init_MarkupCalc_P1`).
- Not seen yet: the reset itself (every machine at once? the timer back to 1200?), a level reload, a co-op client
  (is `ShopInventory` replicated? the machines are `bAlwaysRelevant`).

## Loot odds (probe_loot_odds.py, in game, Sanctuary_P, 2026-09-25)

What "Can contain" could turn into percentages - read as properties only:
- A container picks **one loot configuration by weight** (`Loot[]` / its balance's `DefaultLoot` /
  `DefaultIncludedLootLists[].LootData`: each `Weight` an AttributeInitializationData = its value x
  `BaseValueScaleConstant`), then rolls each of its `ItemAttachments[].ItemPool` (`PoolProbability` 1 seen everywhere).
- A pool picks **one `BalancedItems[]` entry by weight** (`Probability`, the same struct): an item balance
  (`InvBalanceDefinition`) or a sub-pool (`ItmPoolDefinition`: e.g. `Pool_Weapons_Pistols` -> one pool per rarity).
  Pools also have `Quantity`, `bSupportsGameStageVariance`.
- The weights point to shared **`GD_Balance.Weighting.Weight_*`** (AttributeInitializationDefinition,
  `BASEVALUE_InitializationDefSetsBaseValue`): a `ValueFormula` Multiplier x Level^Power + Offset with Level 1, Power 1,
  Offset 0 - i.e. constants: VeryCommon 200, Common 100, Uncommon 10, Uncommoner 5, Rare 1, VeryRare 0.1,
  Legendary 0.01. The golden chest: configurations 300 / 150 / 90 / 80 / 80 / 80 / 50 (2 long guns 36 %, 2 pistols
  18 %, a launcher 11 %, shields / grenade mods / class mods 10 % each, relics 6 %). A pool's rarity sub-pools:
  Uncommon 10, Rare 1, VeryRare 0.1 (+ E-tech 0.1), Legendary 0.01.
- **Not constants** (only the game knows): `Weight_1_Common_RareMod` (common gear: its Multiplier is the designer
  attribute `GD_Balance.Weighting.GearDrops_CommonWeightModifier`, global scope - resolver chain not read yet);
  `GD_Itempools.DropWeights.DropODDS_Health` (an `AmmoDropWeightAttributeValueResolver`: most likely the player's
  current health - live); the vending pools' `Transient.AttributeInitializationDefinition_*` (built at runtime) and
  the item of the day's `Att_IOTD_Weighting_*` (a `ConstantAttributeValueResolver`: its value inside, not read yet).
- **The follow-up** (probe_loot_odds2.py, same day) - how each kind of value resolves, all as properties:
  - an AttributeInitializationData (`Weight`, `Probability`...): its InitializationDefinition's value, else its
    BaseValueAttribute's, else BaseValueConstant - times BaseValueScaleConstant (seen: 0 + Weight_* x 1.5; 1 +
    DropODDS_Health x 500). An InitializationDefinition: its `ValueFormula` Multiplier x Level^Power + Offset, each
    term the same struct (so `Weight_1_Common_RareMod` = GearDrops_CommonWeightModifier x Weight_1_Common (100)).
    These evaluation rules are inferred from the data (Gearbox's), not checked against the game's own result yet.
  - an AttributeDefinition's value: its `ValueResolverChain` - `ConstantAttributeValueResolver.ConstantValue` (item of
    the day weights: Uncommon 4, Rare 1.2, VeryRare 0.2, Legendary 0.0055; DropODDS_Money 0.25, BuffDrinks 0.05,
    EridiumStick 0.008, EridiumBar 0.0015, BossUniques 0.1, BossUniqueRares 0.33, RareDropSkin 0.002, VehicleSkins
    0.05); `AmmoDropWeightAttributeValueResolver` (live: the player's `Resource` - D_Resources.Health, an ammo pool -
    below `ResourceThreshold` (health 0.4, ammo 0.15, protean grenades 0.1) between Min/MaxBelowThresholdWeight
    (health 0.1-0.25, most ammo 0.3-0.5), above it `AboveThresholdWeight` (health 0.03, ammo 0); how it goes from min to
    max: inferred - lower = higher); `ConditionalAttributeValueResolver` (DropODDS_GunsAndGear: conditions, not read).
  - a `DesignerAttributeDefinition` (GearDrops_CommonWeightModifier, GearDrops_RareWeightModifier): global, `BaseValue`
    1; the live value an `InstancedDesignerAttribute.Value` in the host's `WorldInfo.Game.DesignerAttributes`, matched
    by its `DesignerAttributeDefinitionPathName` (probe_loot_odds3.py, Sanctuary, level 10, solo host): **the common
    modifier 0.625** (base 1, one AttributeModifier on its stack - what sets it not known: playthrough? player count?),
    the rare one 1.05 (named "Reference only - HAS NO EFFECT"). lootodds.py uses the live values (refresh() at each
    objects scan: changed - every odds worked out again); a co-op client has no game info: the base values there
    (its common gear then over-weighted).
  - **Game stage gating**: a pool's `MinGameStageRequirement` / `MaxGameStageRequirement` (AttributeDefinitions:
    `Pool_Weapons_Pistols_06_Legendary` needs `GD_Itempools.Scheduling.Gamestage_07` = 7: every `Gamestage_NN` /
    `GameStage_NN` a ConstantAttributeValueResolver of its number, probe_loot_odds3.py; class mods' own schedule:
    `LootSchedule_ClassMod_*` common 8, uncommon 10, rare 13, very rare 16, legendary 20); a balance's `Manufacturers[].Grades[].GameStageRequirement {MinGameStage, MaxGameStage}` and
    Min/MaxSpawnProbabilityModifier (a common Bandit pistol: 1-10000, x1). A legendary balance's own fields read empty
    (its data on its archetype / base definition?).
- **Open (the user, 2026-09-26): the odds on a co-op client.** The pools, weights, game stage gates and configurations
  are static data - the same on a client. What isn't: GearDrops_CommonWeightModifier's live value is in the host's
  WorldInfo.Game.DesignerAttributes (0.625 there, solo host, base 1): a client has no game info, lootodds.py uses the
  base - its commons over-weighted. Not tested on a client. To find out: what the host's value is in co-op (what sets
  it - playthrough? player count?), whether a client can read it (replicated anywhere?); and whose resources the "if
  low on health / ammo / oxygen" weights use in co-op (the host rolls the loot). Also not applied yet, for everyone:
  the level gates (a pool above the area's game stage can't roll - its weight still counts in the chances).
- **Open (the user, 2026-09-25): does it hold for the DLCs and the Pre-Sequel?** The DLCs use the same classes and
  structures (their own `GD_<DLC>_Itempools` / pools / weights - the probe reads whatever a chest points to, but their
  weights may be other objects than `GD_Balance.Weighting.*`, and seasonal / Pearl pools may be gated): to check with
  a DLC chest (a Pirate's Booty / Dragon Keep area). The Pre-Sequel is another game on the same engine (the SDK's
  willow2 side covers it) - the mod as a whole isn't known to run there; a question for the whole mod, not just this.
  2026-09-26: the manifest now lists it (`supported_games = ["BL2", "TPS"]`) to try it as-is; `python tools/link_mod.py tps`
  links it there (project.json's `tps`). What was seen there: `.agent/presequel.md`.

## Pickup amounts (probe_pickup_amounts*.py, in game, 2026-09-26)

How much a cash / ammo pickup gives: never a plain property (the item's `MonetaryValue` is 0 on cash, `Quantity` 1) -
worked out from the item definition by the attribute system, all of it readable as properties (amounts.py):
- **Cash** (`Currency` / `Currency_Big`, balance `ItemGrade_Currency_Money[_Big]`): its ExternalAttributeEffects adds
  `CreditsOnHand` + `AttrSlotValue_BaseCredits` (an AttributeSlotEffectAttributeValueResolver, slot "BaseCredits") **at
  scale 0**; the amount is its "external" AttributeSlotEffects (`bExternalSlot`, AttributeSlotEffectMode 2): slot
  BaseCredits, `CreditsOnHand` MT_PostAdd, `GD_Economy.CashPickups.Init_CashPickupCalc` x 10 (+ x 0.1 per grade above
  AttributeSlotBaseGrade 1: GradeIncrease 0 seen). Init_CashPickupCalc = `Att_CashPickups_BaseValue` (constant 1.25) x
  `Att_UniversalPriceIncreasePerLevelScaler` (1.12) ^ `CurrencyItemLevel` (an ObjectPropertyAttributeValueResolver: the
  item's `ExpLevel`) - level 5: 22.03, **credited rounded up: $23** (seen in game; plain `Currency` at level 6: scale 1,
  2.47 -> $3). `Currency_Big` has MonetaryValueModifierTotal 1.0 (plain: 0) - its role unknown.
- **Ammo** (`AmmoDrop_<type>_<Clip...>`): adds to the weapon's pool (`Ammo_<type>_CurrentValue`) the formula
  `Init_AmmoAmountShared_<type>`: Multiplier `AmmoAmount_<type>` (a ConditionalAttributeValueResolver: 36 if
  `PlayThroughCount` == 2, else 18 - repeater; `PlayThroughCountAttributeValueResolver` IncludePlaythroughThree 0: the
  third taken as 2, inferred; the playthrough: `WorldInfo.GRI.CurrentPlaythrough` + 1 - a property of the game
  replication info; the controller only has `GetCurrentPlaythrough()`, `pc.CurrentPlaythrough` fails) x Level `Init_AmmoAmountSharedPercentage_<type>` (a ConditionalInitialization: 0.5 -
  `Att_AmmoPercentageShared_<type>` - if the item's `ClonedForSharing` == 1, a co-op copy; else 1), ^1 + 0.
- **Their icons** (probe_pickup_icons.py; offline: tools/extract_pickup_icons.py -> _work/pickup_icons/): the item
  definition's `PickupFlagIcon`, a 128 x 128 DXT5 texture in Startup.upk - `fx_shared_items.Textures.ItemCards.`
  Credits, Eridium_Currency, Health, Ammo_Repeater / SMG / CombatRifle / Shotgun / RocketLauncher / Grenade, the
  sniper's `fx_shared_items.Textures.Ammo_Sniper_Dif`; navy and white (cash / health: a disc, ammo: a starburst badge;
  the user: "they're the right ones" - drawn as they are). Mission items: none. Eridium's pixels aren't in the
  package: bulk flags 0x11 (separate file + LZO) - in the texture file cache named by its `TextureFileCacheName`
  (`Textures` -> CookedPCConsole/Textures.tfc) at the mip header's offset, a compressed chunk (tacmap._texture).
- Not seen yet: eridium, health (the collector tries eridium the same way; health left out - its amount may be a share
  of max health). The picker's own bonuses (skills, relics) aren't counted.

## Level geometry for a 3D map (offline, the level's packages, 2026-09-25)

What a level's `<Map>_*.upk` packages hold (the persistent one + every sublevel: `_Dynamic`, `_Freighter`, `_Light`...;
Southern Shelf's `_P` alone: 404 `StaticMesh`, 4131 `StaticMeshComponent`, 11 `Terrain`, 355 `RB_BodySetup`, 135
`BlockingMeshActor`, 1 `GBXNavMesh`). All the StaticMeshes used are cooked into the level's packages (no imports).

- **`GBXNavMesh`** (Gearbox's nav mesh, an actor: tagged properties from offset 26, `BuildVersion` 4, `MeshID`,
  `ConnectedMeshes` = the other sublevels' meshes) - the walkable surface: floors and slopes, stacked levels included.
  Native tail after the properties: `int32 nverts`, `nverts x (f32 X, Y, Z)` in world units, `int32 ntris`,
  `ntris x 7 u16` = 3 vertex indices, 3 neighbour triangles (65535 = a boundary edge), 1 unknown (65535 or a small
  number). Checked on Southern Shelf and Sanctuary: every index in range, neighbours point back at each other, the
  top-down render matches the level (Sanctuary's fountain ring, streets). Then ~265 KB more (Southern Shelf `_P`) not
  decoded (connections / jump links?). One mesh per sublevel that has AI: merge them all (Southern Shelf: 6 meshes,
  59k vertices / 65k triangles, ~1.4 MB raw; Sanctuary: 27k / 30k). 82% of the triangles face up within 30°.
  Stacking (2 m cells, floors > 2.5 m apart): Sanctuary 4015 cells with 1 floor, 203 with 2, 38 with 3; Southern
  Shelf 11672 / 800 / 70.
- **Checked on every level** (82 persistent maps, base game + DLC, sublevels from the persistent level's
  `LevelStreaming*` exports' `PackageName` - never a name prefix: `Sanctuary_*` also matches `Sanctuary_Hole_*`):
  all parse, BuildVersion 4 everywhere, every vertex index in range, no NaN, <= 132k triangles a level (Caverns_P;
  all < 65535 per mesh), ~0.1-8 s a level in plain Python + numpy (a background thread's job, cached). Hunger_P
  lists 3 sublevels not installed.
- **The neighbours**: column 3 + e = the triangle across edge e (vertex e -> e + 1). Stored links are real
  adjacency, better than shared indices: Sanctuary_P 26269 share both vertices, 3404 overlap collinearly (tile seams /
  T-junctions: no shared vertex), 1255 touch within 35 cm; 4 one-way (drops?). So 65535 = the true outline (the
  walls to extrude). The 7th u16: set on few triangles (Sanctuary_P: 205, all distinct, <= 204) - an index into the
  undecoded rest, presumably special links.
- **Alignment with the 2D map**: with the runtime centre (Sanctuary), 100 % of the nav mesh inside the image, 98 % on
  drawn pixels - the street outlines sit on the map's edges. A fitted centre lands within ~1 m of the measured ones.
- **Coverage - the real limit**: it's where the AI walks. Share of each map image's drawn pixels under nav mesh:
  12-81 %, mostly 50-70 % (Sanctuary_P 29 %: the big lower area has none; Southern Shelf 51 %). Part is borders /
  decoration; whether the player walks in the rest isn't knowable offline: tools/probe_navwalk.py records the
  player's positions in game, tools/check_navwalk.py scores them (nav under the feet, holes grouped). A 3D view is
  an optional alternative to the 2D map (the user, 2026-09-25): where it's thin, the page stays 2D.
- Not checked yet: the undecoded rest, spots only reachable by jumping, sublevels that load per mission (merged
  anyway). Most DLC levels' map movie isn't in their `_P` package (the runtime `TacticalMapMovie` gives it).
- **`Terrain` - decoded** (2026-09-25): an actor (properties from offset 26). Native tail: `int32 n` = (NumPatchesX + 1)
  x (NumPatchesY + 1), n u16 heights (row by row, X fastest), `int32 n` + n u8 info flags (bit 0 = a hole, not drawn;
  bit 1 seen - orientation flip in UE3), then the rest (alpha maps...). Vertex (i, j): X = Location.X + i x
  DrawScale3D.X x DrawScale, Y likewise, Z = Location.Z + (h - 32768) / 128 x DrawScale3D.Z x DrawScale.
  DrawScale3D not stored = the class default **256** (Southern Shelf: median nav-to-terrain gap 0-2 uu with it).
  Checked: where nav mesh lies over a terrain, 63-100 % of its vertices within 64 uu of the surface (the rest: on
  buildings / rocks above). Some terrains carry `Rotation` (patches 768 uu, Z up to 12000+: background scenery) - not
  handled; the huge far ones (Sanctuary `Terrain_0`, 1.3 km) have to be clipped to the map's drawn pixels.
- **Coverage, nav + terrain** (runtime centres, share of the map image's drawn pixels): Sanctuary_P nav 27 % ->
  78 % (terrain fills the lower area, the part without NPCs); Southern Shelf 50 % -> 66 % - its big central area has
  neither (static meshes? not walkable?), left for the in-game walk (probe_navwalk) to tell. What's still missing is
  meshes: rocks, buildings, bridges, ice - the static meshes' own geometry (not decoded).
- **In game, rooftops** (probe_navwalk, Sanctuary_P, 2026-09-25, ~2 min running over roofs): 84 positions on foot
  (+110 in the air): nav mesh under the feet 49, terrain 3, **neither 32 (38 %)** - 1.4-9 m above the terrain, or over
  none: roofs are static meshes. The probe's runtime centre / north matched the notes (-3072, -10240, 0). A 3D map
  with roofs / ledges needs the static meshes; nav + terrain only gives the AI's streets and the ground.
- **Static mesh placement - decoded** (2026-09-25): `StaticMeshCollectionActor` (properties from offset 4:
  `StaticMeshComponents`, n refs) + native tail of 84 bytes a component: FMatrix (16 f32, rows = axes then translation,
  unit axes: rotation + translation only), then Scale3D (3 f32), Scale (f32), an int (1). World = (local x scale) .
  matrix (row vectors). Components' properties from offset 8 (`StaticMesh`, `Scale3D`, collision flags
  `CollideActors` / `BlockActors` / `BlockNonZeroExtent`: stored only where they differ from the archetype - see
  "Player collision only"). `StaticMeshActor` /
  `BlockingMeshActor` / `InterpActor`: the actor's Location / Rotation (UE3 rotator, 65536 = 360) / DrawScale(3D) and
  its component's Scale3D / Translation / Rotation. A StaticMesh's native tail starts with its bounds (origin,
  extent, radius: 7 f32). Sanctuary_P + sublevels: 3542 placed meshes with a mesh in the same package, 363 whose
  mesh is in another package (imports, not followed yet), 1758 components not blocking pawns.
- **Simplified collision** (`RB_BodySetup.AggGeom`, tagged: `ConvexElems[]` = `VertexData` raw FVectors +
  `FaceTriData` int triangles; `BoxElems[]` = `TM` FMatrix + full X / Y / Z; also Sphere / Sphyl elems) - read and
  placed, walkable faces kept (normal Z >= 0.7, UE3's WalkableFloorZ default ~45.6 deg). Only 264 of Sanctuary_P's
  363 StaticMeshes have one; on 3542 placements: 1880 with simple collision, 448 per-poly.
- **Roofs are per-poly collision** (the rooftop walk): simple collision faces lie 63-142 uu *under* the feet there
  (slabs / blockers inside), while for 46 of 84 positions a placed mesh's bounds top is within 40 uu of the feet -
  per-poly meshes for 32 of them (+14 mixed). The feet themselves are right: 6 uu above nav mesh and terrain (the
  pawn's floor distance). So the walkable-top-faces idea needs the meshes' own triangles (the kDOP collision tree +
  the LOD's position vertex buffer, native - not decoded; UE Viewer / umodel reads BL2 static meshes: a reference).
- **Per-poly collision - decoded** (2026-09-25): a StaticMesh's native tail (after its tagged properties, which may be
  empty: then only "None" at offset 4): bounds (7 f32), BodySetup ref (i32), kDOP tree = root bound (6 f32), nodes
  (i32 element size 6, i32 count, data), triangles (i32 element size 8, i32 count, u16 v0 v1 v2 material), i32 version
  (18), 4 i32 (0, 0, 0, LOD count), then LOD 0: raw-triangles bulk header (16 bytes, empty when cooked), i32 section
  count, per section 9 i32 (material, bEnableCollision, old, shadow, first index, triangles, min / max vertex,
  material index) + i32 fragment count + 8 bytes each + **1 byte**, then the position buffer: i32 stride 12, i32 count,
  i32 element size 12, i32 count, count x 3 f32. All 363 of Sanctuary_P's StaticMeshes parse (vertices inside their
  bounds, kDOP indices in range); 278 have kDOP triangles. **Winding: the kDOP triangles are the other way round**
  (clockwise seen from their front): flip them before taking normals. Imports: an import's outer can be an export
  (e.g. `Prop_SancBuildings.Meshes` exported in the level) - the path continues there; the meshes are cooked into
  the level's packages. Not found: `EngineMeshes.Cube` (14 in Sanctuary_Px), an FX decal plane.
- **Collision top faces vs the rooftop walk** (kDOP where a mesh has it, else simple collision; blocking components
  only; normal Z >= 0.7): 643k collision triangles, 129k walkable (Sanctuary_P + sublevels, 4.4 s). Testing the pawn's
  footprint (radius 42 - it stands on anything under its cylinder: step edges): 79 of 84 positions on foot have a
  surface within 30 uu (collision median 4 uu); collision + terrain alone 78. 77 % of nav mesh vertices lie on a
  walkable collision face (simple collision alone: 10 %).
- **Not everything walkable-looking is a floor**: Sanctuary's dome (`FX_ENV_Sanctuary.Meshes.SantuaryDome_Smesh`, an
  InterpActor, Z 1824-14922: in the files the actor stores bCollideActors / bBlockActors 1 and its component no flags
  (template defaults: blocking) - but it's a mover driven by the level's script, and the user knows it as a dynamic,
  non-solid object: the files don't tell a mover's runtime state - a probe reading it live would settle it) and a
  safety floor (`Common_Meshes.CollisionCube` with `Mat_Collision`, ~670 m wide at Z
  ~2580 under the town). Invisible collision can't be dropped blindly (ramps over stairs use it), InterpActors are
  also lifts. **Reachability works as the filter**: 64 uu cells of walkable surface (collision + terrain), flood fill
  from the nav mesh's cells - walk (neighbour cell, <= 40 up), jump (<= 150 up within 320), drop (<= 6 m). All 74
  recorded positions that sit on a surface cell were reached (roofs from the streets, the positions weren't seeds);
  the dome drops to 0 %. The render reads as Sanctuary (fountain rings, roofs, streets, the lower area).
  Costs to fix before building: the flood fill took 430 s in plain Python (vectorise: scipy.sparse.csgraph over
  pairs), 100k triangles kept (42 % tiny) - simplify before sending. Not tested yet: other levels / DLC, the safety
  floor's removal (cropped out in the test), BSP brushes (`Model`), SkeletalMesh / other actor classes as floors.
- **Player collision only** (the user, 2026-09-25: base the 3D map on what blocks the player, nothing else). A mesh
  counts when its actor has `bCollideActors` + `bBlockActors`, its component `CollideActors` + `BlockActors` +
  `BlockNonZeroExtent` (pawns are non-zero extent), and Gearbox's `bBlockPlayers` isn't off (BlockingMesh classes
  also carry bBlockEnemyPawns / bBlockFriendlyPawns / bBlockPlayerVehicles / bBlockTossedItems...). Values not stored
  come from the object's **archetype** (the export table's 6th int, e.g. `Engine.Default__InterpActor.
  StaticMeshComponent0`), then the class default object (`<package>.Default__<Class>`, in Engine / GearboxFramework /
  WillowGame.upk, each with its own chain); stored nowhere = off (UnrealScript's default). A value inherited from
  another package (e.g. the template's `StaticMesh`) is an index into *that* package. `InterpActor`'s class default
  doesn't collide (71 of Sanctuary's 117 don't; 41 block the player - the rooftop walk stood on two of them, so movers
  can't be left out: they're taken at their position in the file). Sanctuary: 2592 placements block the player, 1728
  don't. Coverage unchanged (78 / 84 with terrain, 60 from collision); 77 % of nav vertices on a player-collision face.
- **Southern Shelf, climbing the structure** (probe_navwalk, 2026-09-25, saved as tools/probe_navwalk_southernshelf.txt;
  Sanctuary's as probe_navwalk_sanctuary_roofs.txt): 251 positions on foot, **all** with a surface under the footprint,
  collision + terrain alone 249 (collision median 6.5 uu). Player-blocking collision: 1.22 M triangles, 251k walkable.
- **What's loaded** (tools/probe_streaming.py, Southern Shelf, two places ~50 m apart): no distance / volume
  streaming in BL2 - every map's sublevels are `LevelStreamingAlwaysLoaded` (237 over all maps) or
  `LevelStreamingKismet` (378, loaded by the level's script); all 9 Kismet ones loaded + visible both times.
  **`SouthernShelf_Px` - "AlwaysLoaded" - is NOT loaded**: `_Px` = PhysX extras, loaded by the PhysX setting (the user's is Low; not re-checked on High - the rule
  below doesn't depend on it) (34
  player-blocking meshes there, 1 in Sanctuary_Px; no recorded position stands on them). Rule: extract only the
  sublevels the game has loaded (`WorldInfo.StreamingLevels[i].LoadedLevel` not None, read live - cheap), rebuild
  when that list changes: covers the PhysX setting and any script-switched (story state) sublevel. Not seen yet: a
  Kismet sublevel switching during play.
- The other geometry, if ever needed: the
  StaticMeshes' vertex buffers (native, bigger work), `RB_BodySetup.AggGeom` (collision hulls), `BlockingMeshActor`s.
- Scripts: the session's scratch `navall.py` (reads every sublevel with `tacmap.Package`, renders PNGs) - not kept;
  the format above is enough to rebuild it.

## Item card stats (probe_shield.py / probe_accuracy.py in the Pre-Sequel, offline packages, 2026-09-26)

- **Items' top stats** (a shield's Capacity 53, Recharge Rate 16, Recharge Delay 2.36): no number property holds
  them (the shield only has ReplicatedAttributeSlotModifierValues). `WillowItem.UIStatModifiers[]` =
  UIStatModifierData {AttributePresentation, ModifierTotal (53.0588), CompareModifierTotal (53.0), AttributeStyle,
  StatCombinationMethod SCM_Multiply, Supplemental...}: the presentation's Description the label ("Capacity"), its
  RoundingMode / FloatPrecision the rounding (ATTRROUNDING_IntRound: 53.06 -> 53, 15.70 -> 16; the delay: precision
  2, 2.3649 -> 2.36). The same in both games' WillowGame.upk. The card is filled natively (InventoryCardGFx.
  SetShieldCard: a stub; ItemCardGFxObject.SetCardUIStats only gets formatted TopStatData). inspector._ui_stats, for
  shields (other items: not checked). CompareModifierTotal: what it holds for a backpack item not checked.
- **A weapon's Accuracy** (72.1 for a shotgun's Spread 4.186, 95.6 for a sniper's 0.667): WillowWeapon has no
  UIStatModifiers. The "Accuracy" presentation, `GD_AttributePresentation.Weapons.AttrPresent_WeaponSpread`
  (Startup.upk, both games): bValueRemappingEnabled, RemappingData InputValueMn..Mx 0..15 onto OutputValueMn..Mx
  100..0 (each an AttributeInitializationData: BaseValueConstant; the unset ones default 0), RoundingMode
  ATTRROUNDING_Float, FloatPrecision the class default 1 -> 100 - Spread x 100 / 15. inspector._accuracy (card:
  SpreadBaseValue, with bonuses: Spread). Whether the game clamps a spread over 15: not known (not clamped).
- Health on the game's text: StatusMenuExGFxMovie.SetCondensedHealthWidget = `FFloor(GetHealth()) $ " / " $
  FCeil(GetMaxHealth())` - the only script rounding health (both games); the HUD's UpdateHealth / UpdateShield native.

## Objects with health, explosives (offline packages + the page's data, the Pre-Sequel, 2026-09-26)

- **Health**: WillowInteractiveObject.Health (float) / MaxHealth (an int attribute, MaxHealthBaseValue), bHasBeenKilled;
  whether it takes damage: its InteractiveObjectDefinition's bCanTakeDirectDamage / bCanTakeRadiusDamage (bCanBeKilled,
  bDestroyWhenKilled...) - both games. Aiming at one shows a health bar like an enemy's (IIDamageable / IITargetable).
  An exploded barrel stays (its wreck, another model): bHasBeenKilled / health 0 - the page leaves it out ("kd").
- **Buffs, not containers** (the Pre-Sequel's Moxxtails - GD_Moxxtails, BL2's Tiny Tina shrines GD_Aster_Shrines: the same
  design, both "ShrineEffect"): their balance can carry a chest's loot list (ObjectGrade_SpeedMoxxtail's own
  DefaultIncludedLootLists: EpicChestRedLoot - a leftover: the page took them for epic chests), never handed out. Their
  definition's behaviours: Behavior_ActivateSkill (Skill_Moxxtail_SpeedBoost...), DeactivateSkill, a Behavior_SpawnItems of
  their own (the glass: its own ItemPoolList, bDisablePickups) - and no AttachItems / DropItems / SpawnLootAroundPoint /
  SpawnLootAtPoints, what containers hand their loot out with. Of the definitions activating a skill (15 TPS, 12 BL2: all
  packages scanned) only Isaiah's strongbox hands loot out. Not their price: bCostsToUse / CostsToUseAmount read 0 on
  them (not unlocked yet: bought later - GD_Moxxtails.Misc.Init_MoxxtailCost), golden chests cost golden keys, the slot
  machine 85 credits (tools/probe_moxxtail.txt). Some real containers have no loot behaviour of their own either (the
  Dice chest, meteorite loot piles, Claptrap's stash): not a test for "container". The rule also needs loot (that
  leftover list) or an item of its own (Behavior_SpawnItems: the Moxxtails' drink - the Ammo Moxxtail's balance has no
  loot list, the only one of the 8; nothing else activating a skill spawns anything): the other objects activating a
  skill have neither - the Pre-Sequel's IO_ComputerConsole_A, IO_ScreenFX,
  IO_SpaceHurp / IO_InnerHull_SpaceHurpManager, BL2's whiskey barrel (Wedding Day), the Splinter Group's pizza, the
  raids' worm ooze / shaman orb, a test spike trap. BL2's shrines: 6 of 7 carry a list (the Ammo shrine none: not a
  buff on the page), and every one's balance DefaultDisplayName is "Health Shrine" (the game's copy-paste).
- **Tactical map movies drawing a part of their texture**: the Pre-Sequel's ComFacility_P ("No map for this area"
  before): its DefineExternalImage2 (1009) id 0 (its first 4 bytes 00 00 09 00 - the id a u16, not a u32: other maps'
  01 00 00 00), then a GFx DefineSubImage (1008: id, image id, x1 y1 x2 y2 px) - 743 x 644 of its 1024 x 1024 texture
  - which the shape fills with. tacmap.parse_map_movie: the crop, the page draws that part.
- **Moxxtails on sale** (unlocked): each spawns its drink, a WillowPickup of a GD_Moxxtails.Pickups.PickupDummy_*
  (UsableItemDefinition, no name: the page's "Usable Item"), bought - bCostsToPickUp, CostsToPickUpType CURRENCY_Eridium
  (moonstones), CostsToPickUpAmount 10 (the only pickups that cost: tools/probe_moxxtail_pickup.txt). Tied to its
  Moxxtail both ways: the pickup's Base = the Moxxtail's WillowInteractiveObject, the Moxxtail's Attached = [the pickup]
  (tools/probe_moxxtail_link.txt, all 8). The page shows the Moxxtail with the drink's price, not the drink.
- **Mission waypoints on a map exit** (the objective in another map): a LevelTransitionWaypointComponent on the
  LevelTravelStation - no LinkedObjective, no WaypointInfo (the page had no name for it). The game's text for it: the
  station's LevelTravelMapDisplayName "Exit to %s", %s its TravelDefinition (LevelTravelStationDefinition
  GD_LevelTravelStations.Zone1.IceToIceCanyon) -> DestinationStationDefinition -> DisplayName ("Frostburn Canyon"; also
  StationDisplayName, StationLevelName icecanyon_p) - tools/probe_waypoint_exit.txt, Three Horns Divide.
- **Elemental plants** (BL2's Firemelon, Acidolus, Shock Cactus; the Pre-Sequel's Cryo Vine _Normal / _Medium / _Large -
  GD_ElementalPlants): the game groups them - their definition's Allegiance GD_AI_Allegiance.Allegiance_ElementalPlant,
  no other object's (both games' packages). Like barrels, but shot empty they recharge (bDestroyWhenKilled False). Their
  element, each its own way: the Firemelon's Behavior_Explode (Explosion_Firemelon), the Shock Cactus's Behavior_FireBeam
  .DamageTypeDefinition (DmgType_Shock_Impact), the Acidolus's Behavior_SpawnProjectile -> AcidolusSack's own
  Behavior_Explode (Explosion_CorrosiveMaster), the Cryo Vine's WillowDamageArea objects inside its definition
  (DmgType_Ice_Impact - its behaviours, in the shared GD_ElementalPlants.Behaviors.Be_Cryovine_Shared, do no damage).
- **What explodes**: its definition's behaviours hold a Behavior_Explode (BehaviorProviderDefinition.BehaviorSequences[]
  .BehaviorData2[].Behavior; the Pre-Sequel's barrels: bBarrelSource, DamageFormula / DamageRadiusFormula,
  Definition an ExplosionDefinition - its DamageTypeDef the element). The air dome generator: health, no behaviours.
- **The game's typo**: its DamageType enum spells DAMAGE_TYPE_Incindiary (both games), its text the key Incendiary
  (WillowMenu.int [DamageTypes]) and its card frame "fire" - every other element's frame is its enum's name in lower
  case. inspector.py _ENUM_TEXT_KEYS / _ENUM_FRAMES correct it (the user's call); a frame learned from a weapon's
  ElementalFrame goes first (remembered: .cache/element_frames.json). The card's element sprite isn't in the enum's
  order (ice, shock, fire, corrosive, explosive, amp, none): no index to go by. Before the fix fire weapons had no
  element name on the page either.

## A weapon type without a name (offline packages, the Pre-Sequel, 2026-09-26)

- Every laser weapon type has Typename "Laser" but the Pre-Sequel's WT_Tediore_Laser: none (its ScaleformFrameName
  "Laser": its icon works). An unset name reads "None" - `_localized` took it for a name (the page: "None"); now it's
  no name. Then `_type_name`: the name the game's other loaded weapon types of the same WeaponType give (WT_Laser:
  Dahl / Hyperion / Maliwan, Startup.upk; not the full-named vehicle guns), the most common - "Laser". An exception
  to "a thing's own name only" (AGENTS.md), the user's call (2026-09-26: offered "Laser ?", "Weapon" or this) - not a
  precedent for other names.

## Bosses (offline packages + in game, the Pre-Sequel, 2026-09-26)

- `AIClassDefinition.bBoss` (both games) marks only a few: the Pre-Sequel's 7 of 266 AI classes (CharClass_ColZ,
  _ColZMech, _FBCBig..., _Kelly, _MetaGuardian) - not Deadlift (CharClass_SpacemanDeadlift), a boss in game (its boss
  bar). The boss bar's own data: `WillowGameReplicationInfo.BossPawn` / `BossName` / `BossLevel` / `bHasBossBar` /
  `ReplicatedBossHealth` / `ReplicatedBossShield` (replicated: a co-op client's too) - set while the bar is up.
  collector.py: a boss = bBoss, or a pawn that's been the BossPawn this level (`_note_boss`, kept per level). Before
  its fight starts (no bar yet) a boss without bBoss isn't known. Also: `WillowAIPawn.IsBoss()` (native; not called).

## Item serials / Gibbed codes (probe_serial.py + probe_serial2.py, in game, both games, 2026-09-26)

- A Gibbed code (`BL2(hwAAAAAB...)`, the Pre-Sequel's `BLOZ(...)`) is the **game's own item serial** - what a save
  holds (`PackedWeaponData.InventorySerialNumber`) - base64'd, in Gibbed's wrapper. Gibbed re-implements the packing
  (`references.gibbed`: `Gibbed.Borderlands2.FileFormats\Items\PackedDataHelper.cs`, `PackedWeapon.cs` /
  `PackedItem.cs`, `AssetLibraryManagerHelpers.cs`) with a dumped asset table; we don't need it: the game packs.
- Layout (≤ 40 bytes, bits read lowest first): version 7 bits (BL2 7, the Pre-Sequel 10), is-weapon 1, unique id 32,
  check 16 (bytes 5-6), DLC asset set id 8, then type / balance / manufacturer (asset refs), manufacturer grade 7, game
  stage 7, 11 parts (weapon: body grip barrel sight stock elemental acc1 acc2 material prefix title; item: alpha...theta
  material prefix title). An asset ref = sublibrary index << asset bits | asset index, its top bit "the item's DLC set,
  not the base game's", all ones = None; widths per group in `AssetLibraryManager.LibraryConfigs` (the same in both
  games: weapon types 7+6, weapon parts 6+11, item types 9+8, item parts 6+10, manufacturers 4+7, balances 10+10).
  Check = CRC32 of the 40 bytes (0xFF-padded, 0xFFFF in the check's place), its halves xored. Then the bytes after the
  5th are scrambled, seeded by bytes 1-4 (the unique id): a rotation + an xor stream - nothing with id 0, which is why
  Gibbed's copies (id cleared) all start `hwAAAAA` (weapons) / `BwAAAAA` (items). Trailing 0xFF bytes dropped.
- The game's functions (native): `WillowInventory.CreateSerialNumber()` -> `InventorySerialNumber` {`Buffer` (40
  bytes, a tuple in Python), `State` (`SerialNumberState.SNS_Full` = 2), `RunningCounter` (the bits used: 309 for a
  weapon), `EncryptedLength` (garbage)}: the Buffer holds the plain packed bits, check still 0xFFFF, not scrambled.
  `GetSerialNumberString()`: the finished serial, base64 (with its unique id: scrambled - Gibbed takes it too, and
  gives a pasted item a new id anyway). Also `WillowWeapon` / `WillowItem.PackSerialNumber(Def)`,
  `UnpackSerialNumber`, `CreateWeaponFromSerialNumber` / `CreateItemFromSerialNumber`,
  `WillowInventory.CreateInventoryFromSerialNumberString(str, source)` (static: pasting a code in game - not tried).
- The asset library itself: `GD_Globals.General.Globals`.`AssetLibraries` (6 `PackageAssetLibrary`, one per group),
  each DLC a `DownloadableAssetLibraryDefinition` (its own 6), 423 `PackageAssetSublibrary` (`Assets`, `AssetPaths`,
  `CachedPackageName`) in the Pre-Sequel - not needed since the game packs.
- Checked: codes built from the Buffer (a BL2 Law, a Tenderbox, a BanditTech skin) decode with Gibbed's format and
  table - every part right, check ok; the Pre-Sequel's Bullpup code (a user's, from Gibbed) decodes with
  `references.gibbed_oz`'s table. A code from the page (the Pre-Sequel's, `BLOZ`) pasted into Gibbed's editor: accepted (the user, 2026-09-26);
  BL2's goes through the same code (its codes checked against Gibbed's table above).

## Backlog

- **Game-thread spikes, not reproduced** (the log, co-op host with 3 others, Wildlife Exploitation Preserve, 2026-09-30):
  "players" (every 2 s, usually 10-18 ms) once 557 ms, "state.pickups" up to 135 ms, "state.pawns" 102 ms, "scan
  objects" 132 ms - none in two 20 s runs of tools/probe_profile.py (state and players both wrapped). A guess, not
  checked: item cards built when loot rains (ground_item, ITEMS_PER_UPDATE), or Python's GC. Fixed meanwhile: failed
  property lookups cached (util._prop - the Pre-Sequel's OxygenPool looked up in BL2 every update, 12 % of the state
  update), the pickups read through reader(): the state update 6.0 -> 4.8 ms on average (174 updates / 20 s).

- **The Electrical Fuse Box is a switch, not an explosive** (tools/probe_io.txt, Wildlife Exploitation Preserve,
  2026-09-30; GD_ElectricFence.InteractiveObjects.IO_ElectricalFenceBox, BL2) - TO FIX: the page draws it as a shock
  explosive (inspector.py explosion_info: any Behavior_Explode). Its definition's sequence Active: OnUsedBy (pressed)
  and OnHealthDepleted (shot out) run the same chain - Behavior_CustomEvent (the fence off), ChangeUsability,
  ChangeAllegiance, ChangeInstanceDataSwitch x2; OnHealthDepleted puts a Behavior_Explode first whose DamageFormula,
  DamageRadiusFormula and MomentumFormula are all 0 (constant 0, no attribute / initialization): an effect only
  (Explosion_ElectricalBox, DmgType_Shock_Impact_NoDoT). Its definition: bCanBeKilled False, Allegiance
  Allegiance_ExplosiveBarrel (the barrels' own: not a test either), MaxHealth from Init_BaseInteractiveObjectHealth.
  Shot out it reads Health 0 (max 203 here) and the page drops it as killed ("kd"), though it stays. The likely
  rule: an explosive's Behavior_Explode does damage (DamageFormula / DamageRadiusFormula not 0) - check a barrel's
  formulas first (the Pre-Sequel's: DamageFormula / DamageRadiusFormula set). Then a category for switches?

- **Mission log cost** (user, 2026-09-23: 20-40 ms often) - (1) and (3) DONE, to measure in game; (2) if still needed:
  the full pass reads ~10 properties for each of ~290 entries in one tick. Plan: (1) read per entry
  only what can change - not started: status + bHeardKickoff; done: status only (progress final);
  a locked level once; full reads only for active ones (the fast pass has them anyway); (2) spread
  the pass over ticks (~50 entries each); (3) split the payload: static definitions once, the live
  part on change (less JSON on the game thread). Measure with the collector's slow-task timings.

- **Best now: first version DONE** (2026-09-23: ranking + XP share). Still open: mission level vs the
  player's (XP drops when outlevelled: "do it soon"), item reward rarity, other currencies (eridium
  / seraph), best area (rewards summed per area), unlock value.

- **Background / map opacity: DONE** (2026-09-24, js/look.js): Settings tab "See-through" -
  Background (the canvas fill `COLORS.bg` + the page's `--page-bg`), Map (the image) 0-100 %,
  Panels (`--panel`: the panel, the drawer, the tooltips, the status) 20-100 %. No URL parameters
  (dropped, user: OBS's "Interact" window reaches the Settings tab). OBS renders a transparent page
  see-through - a normal browser tab never does.
  The map textures are cut out already (checked on the game files, DXT5 alpha): Southern Shelf 75 %
  / Sanctuary 55 % fully transparent (outside the playable area), 4-7 % partial (the edges), and no
  baked background in the opaque part (none near #0b1116, none very dark; average #2d5365, cyan):
  background 0 % leaves only the level's shape.

- **Loot rarity only for real gear** (user, 2026-09-23): rarity colours, the bigger marker for high
  rarity, and the loot filter must only apply to pickups that go into the inventory (weapons,
  shields, grenade mods, class mods, relics). ECHO logs, ammo, cash, health, mission items etc. get a
  neutral style and aren't filtered by rarity. Classify by the pickup's inventory class (as the
  inspector's `ITEM_KINDS` does: `WillowWeapon` / `WillowShield` / `WillowGrenadeMod` /
  `WillowClassMod` / `WillowArtifact` vs `WillowUsableItem` / `WillowMissionItem`), and check the
  real `RarityLevel` values of each tier in game (the page's tier names were confirmed correct by the
  user for inventory items, 2026-09-23; the colours are still ours).
  **Use the game's own rarity colours** (user): `GlobalsDefinition.RarityLevelColors` (array of
  `RarityLevelColor`: `RarityRating` + colour, probably a RarityLevel range) - send them with the
  level payload, colour loot / items from it, drop the page's guessed palette. Also
  `GlobalsDefinition.MissionItemRarityLevel` (mission items' fixed rarity level: likely why ECHO logs
  looked "legendary"), and `ReceivedAmmoMessage.AmmoFakedRarityLevelForItemColor` /
  `ReceivedCreditsMessage.CreditsFakedRarityLevelForItemColor`. Probe the struct fields first.

- **Item card stats from the game**: `ItemCardModifierStats` / `ReplicatedWeaponCardModifierValues`
  -> `AttributePresentationDefinition` text + value, instead of the hand-picked stat list. Probe first.

- **Player inspection, co-op client: DONE** (seen in game, tools/probe_coop.py, 2026-09-23). The
  others have no controller and no `InvManager` on a client. Replicated anyway: their pawn's
  `Weapon`, `HolsteredWeaponSlots` and `EquippedItems` (shield, grenade, class mod, relic: the Gear
  tab shows them), their player info's `ExpLevel`, `ClassModNamePart`, `bClassModIsBuffingTeam*`,
  `Currency`. Not replicated: backpack, skill tree (`TrackedSkills` empty), XP (the player info's
  `ExpPointsNextLevelAt` = 0, no `ExpPool`), cooldowns. The pawn's
  `NextActionSkillActiveAbilityTime` (= `...CooldownAbilityTime`) is the world time of their last
  action skill use (tools/probe_coop_skill.py: jumps to the current time on use, nothing when ready
  again): the Info tab shows "last used N s ago".
- **Player inspection, co-op host: DONE** (seen in game, 2026-09-23). The host has every player's
  controller and inventory manager: skill tree, XP (ExpPool), equipped gear, cooldowns, passives.
  Not their backpack: `Backpack` empty and no item objects of theirs besides the equipped ones
  (tools/probe_backpack.py); their `BackpackInventoryCount` isn't their count (24 one session, 0 then
  negative after a drop in another) - nothing of it is shown. Who hosts: NetMode 3 = client, then the
  party leader (`PlayerReplicationInfo.bIsPartyLeader`); the page names players, the host marked.
- **Action skill of the others, on the host** (tools/probe_action_skill.txt, 2026-09-23, 3 others):
  their controller's `SavedSkillTreeSkill` is None (the name: their tree's `SKILL_TYPE_Action` skill -
  "Gunzerking", "Phaselock"); the running skill shows in the skill manager with them as instigator
  (+ `pawn.MyActionSkill`, `pc.ActionSkillTime` 0 -> 1 while running, -1 otherwise; the pawn's
  `NextActionSkillActiveAbilityTime` = the world time of the use). Its `Duration` isn't its real length
  (Phaselock: 120, ended after ~1 s; Gunzerking 26, ran 26). `GetSkillCooldownTime()` works (42 / 13).
  Their cooldown pool read empty in the collector (the page showed "ready" all along; the probe logged
  the pool object, not its value - fixed for a re-run). skills.py: the full cooldown from when the skill
  was last seen running (the local player keeps the pool's real value, cooldown boosts included).
- **Skill tree extras** (tools/probe_skill_layout.py, probe_child_skill.py): a branch tier's `Skills[]`
  can list hidden helpers after the real ones (Krieg: `_Bloodlust`, `FireStatusDetector`...), more
  than the layout's occupied cells - left out of the grid. Timed effects can run as helpers in no
  tree, with dev text for a name ("BloodOverdriveChild - If you are reading this please bug it!");
  a helper shares its skill's `SkillIcon` (unique per tree skill): shown under that skill's name.
- **On a turret / gunner seat** (user, 2026-09-24): the player's `DrivenVehicle` is the seat pawn
  (WillowWeaponPawn - not on the map), not the vehicle: the page's vehicle bar found no marker. The
  collector (`_seat_vehicle`) takes the seat's vehicle - UE3's `MyVehicle`, else its `Base`, else its
  `Owner`, the first that's a WillowVehicle. Which one BL2 fills: not verified in game.
- **Driving** (a player in a vehicle): the controller possesses the vehicle (`pawn.Controller` None:
  through `DrivenVehicle.Controller`), and the pawn's health properties went wrong (max = health):
  the functions then, both logged once ("vitals check (player driving)") - to confirm in the log.
- **Rarity: the game's** (tools/probe_rarity*.py): `GlobalsDefinition.RarityLevelColors` reads empty,
  but `GetRarityColorForLevel(level)` / `GetRarityLevelColorsIndexforLevel(level)` work: levels sharing
  a colour entry are one tier (5 and 7-10 legendary; 6 E-tech; 500 pearl, 501 Seraph, 506 "Rainbow"
  = effervescent; `GetRarityForLevel` gives EItemRarity but files E-tech under VeryRare). Sent with
  the level payload (`rarity`); the page names tiers by colour entry, colours are the game's.
- **The Pre-Sequel's rarity table** (offline: Startup.upk, GD_Globals.General.Globals RarityLevelColors - its
  MinLevel / MaxLevel / Color, BGRA): 19 entries, BL2's 18 plus 505's (entry 17: a peach) - so 506 is its entry 18 (the
  legendary orange), not 17. 500 cyan (entry 12), 501 pink (13: BL2's Seraph colour - the Pre-Sequel's Glitch, the
  user), 503 a purple (15). The page names the Pre-Sequel's tiers from its own entries (model.js TIER_BY_ENTRY_TPS).
  What uses the levels (offline, every definition's BaseRarity / Rarity - AttributeInitializationData: its
  BaseValueConstant, or an attribute's ConstantAttributeValueResolver): gear 1-5 (GD_Balance_Inventory.Rarity_Item
  .ItemRarity1_Common..5_Legendary: 1..5), Glitch = a glitch attachment's +497 (GD_Ma_Weapons.Rarity
  .Marigold_WeaponRarity6_Glitch) - on an epic 501. Pickups' own colour levels: 171 / 176 buff drinks, 181 currency
  (moonstone crystals...), 500 mission items (GlobalsDefinition.MissionItemRarityLevel), 502 ECHO logs, 504
  moonstones / shield boosters, 505 the instant oxygen drinks (Moxxi's Slammer), 506 PickupDummy_Excalibastard; 503
  none. Not gear tiers: left unnamed.
- **Every coloured level** (tools/probe_rarity4.txt, levels 0-2000, 2026-09-24): 18 colour entries
  (0-17), all within 0-506. 11, 505 and 507+: none. Entries 8-11 are not gear tiers, just the
  pickups' made-up levels: 12-170 (entry 8: black, alpha 0 = no colour), 171-175 (9: red `#cf4747`,
  health: "Health Now!" is 171), 176-180 (10: peach `#ffc7a7`, unknown kind), 181-499 (11: yellow,
  cash). Still unnamed: 502 (14: white), 503 (15: purple `#9132c8`), 504 (16: cyan, as pearl's 500).
  The wiki's Gemstone (Dragon Keep: its balances are grade `_4_`) and Cursed (Pirate's Booty) tiers
  may be among those three: not tied to an item yet (probe_rarity4 with one near).
- (history) Player inspection candidates, before the probes: `InvManager.Backpack` / `InventoryChain` /
  `ItemChain`, `pawn.EquippedItems` / `HolsteredWeaponSlots`, item `DefinitionData`, `RarityLevel`,
  `ExpLevel`, card stat modifiers; `pc.PlayerSkillTree.Skills` / `Branches`; replicated to everyone:
  `PlayerReplicationInfo.StandInGear`, `TrackedSkills`, `ClassModNamePart`.
- **Opened containers on a co-op client** (tools/probe_client_containers.py, Outwash, 2026-09-23):
  opened ones `SimpleAnimState` / `RepSimpleAnimState` 7, unopened 4 - but `bCanBeUsed` stays (1, 0)
  on both (not sent to clients): the host's test (7 + no longer usable) never fired. A client: the
  state alone (`_is_looted(io, client)`; `_client` from the NetMode at each objects scan). Seen
  working in game (user: containers and all their kinds right, as a client).
- **A container's opened state is a bitmask** (tools/probe_prelooted.py, the Pre-Sequel's Moonsurface, 2026-09-26 - the
  user: looted containers "Not looted yet" again after leaving and coming back, some spawned looted):
  `SimpleAnimState` = one bit per entry of the object's `SimpleAnimInfo[]` ({Tree, AnimName, Nodes} - here Open,
  Open_Vacuum, Opened(_Idle), Closed(_Idle)): closed 8 (Closed), just opened 14 (Open_Vacuum + Opened + Closed),
  looted then the level reloaded 12 (Opened + Closed), spawned looted 4 (Opened alone); BL2's 7 opened / 4 closed fit it
  if its lists are Open, Opened, Closed (not read - to check in BL2). Looted = the "Opened..." animation's bit set (+ not usable, the host) -
  collector.py `_is_looted`; the state 7 alone only when there's no "Opened" animation.
- **Objects shown as "Interactive Object ?"** (user, 2026-09-23): a record built before the object had
  its `InteractiveObjectDefinition` (it arrives after the object, on a client at least): made-up
  class name, "Other", not a container. Such records are built again every second until the
  definition is there (`_incomplete`, INCOMPLETE_EVERY) - first tied to the full objects scan, which
  is every 120 s (OBJECTS_EVERY: a safety net, the hooks do the rest): "2 min to sync" (user). The
  host too after a level load, not only a client. Seen fixed in game (the chests show).
- **Quest givers on a co-op client** (tools/probe_directors.py, Sanctuary, 2026-09-24): NPCs have
  `MissionDirectives` (a `MissionDirectivesDefinition`: `MissionDirectives[]` = {MissionDefinition,
  bBeginsMission, bEndsMission, BranchEnding}; Scooter: Poetic License, Swallowed Whole, Cold
  Shoulder...; Crimson Raiders: empty) and a `MissionDirectorParticle` (template
  `Part_Dynamic_Mission_Select`: the "!"; read inactive both runs - not relied on). The collector
  (`_npc_givers`: on the host too - its MissionWaypoints had no giver at all in Sanctuary, 2026-09-24,
  only the tracked objective, Marcus offering Rock, Paper, Genocide; NPCs with a game marker skipped)
  makes a giver marker per NPC with a
  mission it gives that can be picked up / takes back that's ready (MissionLog.giver_states). Not
  verified in game yet. **Bounty board** (tools/probe_bounty.txt, Sanctuary, 2026-09-25): a plain
  `WillowInteractiveObject` (no class of its own), definition `GD_GameSystemMachines.InteractiveObjects
  .BountyBoard` (`StatusMenuMapInfoBoxHeader` 'Bounty Board', `CompassIcon` RadarIconType_BountyBoard);
  its missions: `WillowInteractiveObject.Directives` (a MissionDirectivesDefinition, like an NPC's
  `MissionDirectives`), `bSetPrimaryUsabilityByMissionDirectives`, a `MissionDirectorParticle` and a
  `MissionDirectiveWaypointComponent`. `MissionTracker.MissionDirectors` lists every giver (NPCs, the
  board, an ECHO recorder `MO_Ep5_MissionDirectorRecorder`). The collector reads `Directives` with
  the object's record (`_note_giver`).
- **Vault symbols** (`IO_VaultRoy`, `InteractionIconOverride` = `Icon_DefaultDiscover`: the Cult of
  the Vault challenge, clicked to discover): two dumped in full, identical but for DrawScale (1 / 0.5)
  - nothing on the object says discovered (likely the player's challenge progress). Own map layer
  ("Vault symbols", a pink ring + dot, on by default), discovered ones not told apart (user's call).
- **Mission markers on a co-op client** (tools/probe_client_markers.py / probe_minimap_icons.py /
  probe_client_waypoints.py, 2026-09-23): the client's MissionTracker has the full MissionList and
  ActiveMission but an empty `MissionWaypoints`, and no waypoint components exist at all (the host
  registers them: `RegisterWaypoint(component, mission)`). The HUD minimap's `Icons_*` are fixed pools
  of GFx clips {Object, bVisible, MapPos (minimap px, player-relative)}: clamped to its ~60 m rim, no
  mission / radius - unusable. The level's `WillowWaypoint` actors are there (hidden) and each has
  `WaypointInfo = {LinkedObjective, ObjectiveSetRestrictions}` + `AreaRadius`: the collector
  (`_client_markers`, client only, actors listed at each objects scan) shows one when its objective's
  mission is picked up, the objective isn't done, and it's in the current step (a restriction = a
  current set, or none and the objective in one). Quest givers ("!"): none on a client. Seen working
  in game (user, 2026-09-23: markers with their radius).
- **Mission markers: DONE** (verified in game, Southern Shelf, tools/probe_missions.txt):
  `MissionTracker` (find_all, one instance) `.MissionWaypoints[] = {Mission, Waypoints[]}`; waypoints
  are `MissionObjectiveWaypointComponent` (objective marker: `WaypointInfo.LinkedObjective`,
  `WaypointRadius`, `bActive`) or `MissionDirectiveWaypointComponent` (quest giver / turn-in, on an
  NPC: `LinkedMission`). Only displayed markers are `bActive` (exactly 1 in the level: the tracked
  mission's current objective). Position = `comp.Owner` (a `WillowWaypoint`, or an NPC);
  `WillowWaypoint.AreaRadius` > 0 = area circle (uu; equals the component's WaypointRadius), 0 = point.
  Texts (localized): `MissionDefinition.MissionName`, `MissionObjectiveDefinition.ProgressMessage`.
  `ActiveMission` = the tracked one. The HUD minimap icon lists came back empty in that run (why?).
  Next: the HUD's objective checklist (checkboxes / counts): `HUDWidget_Missions` - the probe now
  dumps it. Original research notes:
- Mission areas / objectives. Names found in WillowGame:
  - `MissionTracker` (`MissionWaypoints`, `MissionList`, `MissionDirectors`, `LevelTransitions`,
    `GetActiveMission`, `GetCurrentObjectives`, `GetObjectivesProgress`) - probably reachable from
    the GameReplicationInfo;
  - `WillowWaypoint.AreaRadius`, `MissionObjectiveWaypointComponent.WaypointRadius` +
    `MissionObjectiveWaypointData`, `WaypointComponent.bActive`;
  - `IMissionDirector.GetMissionDirectorLocation` / `GetEligibleMissions` / `GetRedeemableMissions`
    (quest givers with available / turn-in missions);
  - `MissionObjectiveDefinition.GetObjectiveName` / `GetMissionName`, `ObjectiveCount`;
  - what the HUD shows: `HUDWidget_Minimap.Icons_Objective` / `Icons_AreaObjective` /
    `Icons_AreaObjectiveSticky` / `Icons_MissionEligible` / `Icons_MissionRedeemable`, and the map
    screen's `StatusMenuMapGFxObject.MapObjects` (`MapObjectData`).
  - `WorldDiscoveryArea.bWorldAreaRadius` (discoverable areas, maybe for fog of war).
- **Area names / fog of war** (probe_discovery.py, Southern Shelf): `WorldDiscoveryArea` actors (6 there,
  bNoDelete): `WorldAreaDisplayName` (the game's name: "Wreck Of The Ice Sickle", "Gateway Harbor"; empty for
  `bForFogOfWarOnly` ones - they only clear fog), `DefaultWorldAreaShortName` ("SOUTHERNSHELF_PWDA_4"; or
  `CustomName` if `bUseCustomName`), `DetectionRadius` (uu), `Location`; some also `DetectionVolumes`.
  The player's: `pc.DiscoveredWorldAreas[]` = {DiscoveryName (the short name), HasBeenUncovered} (51 in
  that save, every level seen). Being listed = discovered (probe_fog.py: HasBeenUncovered False on all 51,
  a fully explored level's too; Southern Shelf's 5 visited areas listed, the unreached one absent), `pc.FullyExploredAreas[]` (map names: "Glacial_P"). No fog state
  elsewhere (pawn, PRI, HUD, world / game / replication info).
  **The fog itself** (tools/dump_tacmap_movie.py): the level's map movie imports the blob and places it
  once per area, named by the area's short name, a matrix stretching it (ellipses: Southern Shelf 5 pieces,
  none for the Wreck; Sanctuary 2; Sage Underground 22 `..._DYNAMICWDA_n`) - the map screen hides a
  discovered area's piece; outside every piece nothing is ever fogged. A first try (the map darkened
  outside DetectionRadius circles) left blind spots between discovered areas.
  Not verified: that the list updates the moment an area is found (vs on save), a co-op client's list,
  what HasBeenUncovered means.
- **Cutscenes** (probe_cutscene_watch.py, Orchid_OasisTown_P's intro): the level script's
  `SeqAct_ToggleCinematicMode` -> `WillowPlayerController.SetCinematicMode(True...)` (pc.bCinematicMode,
  bKismetEnabledCinematicMode, bCinematicModeHidePlayer, bIgnoreMove/LookInput 2, HUD bShowHUD False, pawn
  hidden), then a video: `ClientPlayBinkMovie(MovieName='Orchid_Intro', bStreamed, bLooping, bForceNoSkip)`
  - and **not one frame (PostRender) for its whole length** (65 s): nothing runs on the frames meanwhile.
  The `MovieName` comes with or without its extension: 'Orchid_Intro', 'MegaIntro', but 'TC_Marcus.bik' (the log,
  2026-09-24/25: its length read None - looked for 'TC_Marcus.bik.bik'; `movie_length` drops a ".bik" now).
  Its length: the .bik header (frames at 8, frame rate numerator / denominator at 28 / 32: 1948 frames,
  5000000 / 166833 = 29.97 fps = 65.0 s, exactly the gap); files in WillowGame/Movies or
  DLC/<code>/<Lic>/Movies. After it: cinematic mode off, the HUD reopened. `GRI.bAllInCinematicMode`: every
  player (False here, solo). Not seen yet: an in-engine (Matinee) cutscene without a video, a co-op client.
- **Skill tree colours** (the user's picks from the game; base.css `--tree-N-hi/main/shadow`): every class's
  left tree green, middle blue, right red, each a highlight (top) -> main -> shadow (bottom) ramp:

  | tree | highlight | main | shadow |
  |---|---|---|---|
  | 0 green | #369341 (OKLCH L .589 C .148 h 145) | #426122 (.454 .098 131) | #363d20 (.345 .047 120) |
  | 1 blue | #249ccc (.651 .122 231) | #3f597d (.459 .067 257) | #292946 (.296 .052 283) |
  | 2 red | #a13837 (.491 .140 24) | #552b19 (.341 .068 43) | #231614 (.216 .022 29) |

  The pattern (OKLCH: lightness / chroma as seen): main = the highlight's lightness x 0.70-0.77, chroma x
  0.49-0.66; shadow = lightness x 0.44-0.59, chroma x 0.16-0.43 - darker and much greyer. The hue drifts as it
  darkens, toward the colour's darker neighbour: green -> olive (-14 deg, -25), blue -> indigo (+26, +52), red
  -> orange-brown (+19, +4). Not one tint over them all (tested: the best shared mix colour, #281c18, misses
  by 13/255 rms and turns blue's main teal). A new ramp from a highlight colour H: main ~ oklch(L*0.73
  C*0.57 h+drift), shadow ~ oklch(L*0.5 C*0.3 h+2*drift), drift ~ 15-25 deg toward the darker neighbour.
  The Skills tab (like the game's, a screenshot the user shared): the tree's background is that ramp (top to
  bottom), coloured from the top down by the tree's **points / the points that unlock its last tier** (the sum
  of the earlier tiers' need: 25 in BL2 - full when the capstone opens), like the game's, matched 1:1 in game
  (6 rows: 5 points = just past row 1, 8 = 2, 11 ~ 3, 12 = the bottom of row 3, 26 = all). Spent points only:
  a class mod's bonus ranks don't count (the user). Not by tiers unlocked (5 points open tier 2: two rows),
  nor per row toward the next tier (12 showed mid-row 3), nor points / max ranks (~90 a tree); none with no
  point in it, greyscale below, framed in the highlight; a tile's outline +
  rank dots #04cc04 maxed, #d46a00 in progress (the game: "5/5" badges - the user prefers the dots).
- **The game's UI fonts** (tools/find_fonts.py, gamefonts.py): Startup_LOC_INT.upk has UE3 bitmap fonts
  (`UI_Fonts.Font_Willowbody_18pt`, `Font_Willowhead_8pt`, `Font_Hud_Medium`: texture pages, canvas text);
  the Scaleform menus use vector ones from a font library movie, Startup.upk's `UI_FontsEn.FontsEn`
  (`UI_FontsJp/Kr/Twn` for Asian scripts): GFx `DefineCompactedFont` tags (1005) - WillowBody (293 glyphs,
  Latin-1 + some punctuation / currency), Compacta Bd BT (232), Chintzy CPU BRK (40: only what the game
  prints with it). Other movies embed small subsets (UI_StatusMenu: WillowBody; UI_HUD: WillowHead;
  UI_Trading: Arial). The format (decoded from the data, verified by rendering): see gamefonts.py's
  docstring - em 256, y down, shared contours (a count with its low bit set = an earlier contour's
  offset), the closing edge implicit, Flash's even-odd fill (TrueType's non-zero: contours re-oriented by
  nesting). Rebuilt as TrueType at run time (~1 s, a thread), served at /font/<slug>.ttf.
- **Skill icons** (gameicons.py): `SkillDefinition.SkillIcon` = a small Scaleform movie
  ("SharedSkillIcons_Soldier.SkillIcon-Able"); its texture: the same path, or "<movie>_I1" (the importer's
  first image: some, and the DLC classes') - in the class's streaming package: WillowGame/CookedPCConsole
  `GD_<Class>_Streaming_SF.upk` (Soldier / Siren / Assassin / Mercenary: 31-34 each), DLC/Lilac and DLC/Tulip
  `.../Content/GD_Lilac_Psycho_* / GD_Tulip_Mechro_Streaming_SF.upk` (named `UI_Lilac_SharedSkillIcons_Psyc.*`,
  `UI_Tulip_SharedSkillIcons_Mech.*`): 205 in all, DXT5, 64 x 64 (the action skill's banner 256 x 128). Startup.upk
  holds a couple too. Indexed once, decoded to PNG on demand (/icon/<path>.png).
- **Skill stats** (probe_skill_stats*.py): `SkillDefinition.GetSkillEffectPresentations(grade, controller, out
  lines)` -> {AttributePresentation (Description: "Gun Damage: $NUMBER$", display flags), ModifierValue} - the
  tooltip's lines, computed. **Bonus ranks** (probe_skill_bonus.py): not in the tree (Grade / GetSkillGrade: the
  points spent) - the equipped items' `ItemCardModifierStats` (a class mod: AttrPresent_Steady 2.02 -> +2, its
  presentation in GD_AttributePresentation.Skills_<class>); they only count with a point in the skill.
- **Item card icons** (gamecards.py): the manufacturer logos and item type icons are **atlas bitmaps** in the item
  card's Scaleform component movie (BL2: WillowGame.upk's SharedWillowComponents - found, not named): a sprite
  per list, a frame per key (the game's: ManufacturerDefinition.FlashLabelName "maliwan", WeaponTypeDefinition
  .ScaleformFrameName "pistol"), each frame a one-shape wrapper whose bitmap fill is a GFx DefineSubImage (tag 1008:
  bitmap id u16, atlas index u16, x0 y0 x1 y1 u16) of a DefineExternalImage2 atlas (1009: id u32 - its low word is
  that index -, format, declared w / h, export name, file name; the texture "<movie package>.<file name>").
  An atlas' id has a high word (0x90000, 0x90001); a plain image's not - SharedWillowComponents' 8 x 4 "scanlines-
  independent -nopack" is id 1 and collided with atlas 1 (I38, the small variants) until atlases won.
  The "two variants" are **layers**: the card's "item card" sprite places "manufacturer logos" (which places two
  logo lists: depth 1 "bgdClip" - larger, black: the outline -, depth 3 "tintClip" - smaller, white: the fill, tinted
  by the game), "item card - weapon type" (two type lists, the same way) and the element list, instance names
  `manufacturer`, `typeIcon`, `elementalIcon`. Drawn by depth, one over the other (centred shapes: the placements'
  translates + the shapes' bounds). Some layers are vector (Eridian's outline: a solid fill; a few type outlines):
  that layer's missing. Other movies have type lists too (the ammo's 30 x 41 icons, the vendors' tabs) - the one
  nearest the manufacturer's in the tree is the card's. The element list's labels: amp (slag), corrosive, explosive,
  fire, shock, none = the DamageType enum's names without DAMAGE_TYPE_ (lower case; Incendiary's frame is "fire"). The
  "item icons" sprite (quest, sdu, artifacts) is vector (drawn since 2026-09-26: gamecards._shape_rgba, solid fills
  without strokes - the Pre-Sequel's card type icons, BL2's weapon outlines). Everything found from the game's data: the
  packages from the engine config ([Engine.ScriptPackages], [Engine.StartupPackages], + the cooked Startup), the
  lists by their labels vs the keys (nearest the manufacturer's, the best overlap, the largest) - for the Pre-Sequel
  as is. The fonts the same way now (any movie's compacted fonts in those
  packages, each name's fullest). Still named: the skill icons' packages (GD_*_Streaming_SF, any *_Streaming_SF in a
  DLC's Content - the Pre-Sequel's DLC classes have no "GD_" -, + Startup).
