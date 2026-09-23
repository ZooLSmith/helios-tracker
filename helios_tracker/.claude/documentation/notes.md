# Helios Tracker - research notes

## Tactical map data (on disk)

Per level, in the persistent package `<Map>_P.upk` (e.g. `Sanctuary_P.upk`, `SouthernShelf_P.upk`):

| Object | Notes |
|---|---|
| `SwfMovie UI_TacticalMap_<Level>.<Map>_P` | ~1 KB CFX movie: `DefineExternalImage2` (id u32, format, target w/h, export name, file name `<Map>_P_I1.tga`), a `DefineShape` with a clipped bitmap fill of that image, `PlaceObject2` at identity; fog-of-war blobs imported from `SharedWillowTacMaps`. `TextureRescale = Mult4`. |
| `Texture2D UI_TacticalMap_<Level>.<Map>_P_I1` | PF_DXT5, 1 mip, NeverStream, stored inline (bulk flags 0). Sanctuary 468x512 (declared 465x512), Southern Shelf 876x1024 (declared 874x1024). |
| `WillowTacticalMapVolume_0` (actor in `TheWorld.PersistentLevel`) | `UnrealUnitsPerPixel` (class default 32, not overridden), `NorthOffsetInDegreesClockwise` (default 0). Its brush bounds are much larger than the map image: only the bounds *centre* matters. |
| `SharedWillowTacMaps` | fog-of-war textures + movie (not used). |

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

Not yet seen: a level with a non-zero `NorthOffsetInDegreesClockwise` (the page rotates clockwise
by it - unverified), or several map images (`_I2`...; handled, unverified).

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

## Backlog

- **Mission log cost** (user, 2026-09-23: 20-40 ms often) - (1) and (3) DONE, to measure in game; (2) if still needed:
  the full pass reads ~10 properties for each of ~290 entries in one tick. Plan: (1) read per entry
  only what can change - not started: status + bHeardKickoff; done: status only (progress final);
  a locked level once; full reads only for active ones (the fast pass has them anyway); (2) spread
  the pass over ticks (~50 entries each); (3) split the payload: static definitions once, the live
  part on change (less JSON on the game thread). Measure with the collector's slow-task timings.

- **Best now: first version DONE** (2026-09-23: ranking + XP share). Still open: mission level vs the
  player's (XP drops when outlevelled: "do it soon"), item reward rarity, other currencies (eridium
  / seraph), best area (rewards summed per area), unlock value.

- **Background opacity** (user, 2026-09-23, "later"): for OBS / overlays - the map's background
  (the canvas fill `COLORS.bg` + the page's `--bg`, `#0b1116`) with an opacity setting down to
  transparent (OBS browser sources render a transparent page see-through); also as a URL parameter
  (e.g. `?bg=0`): OBS's browser source keeps its own localStorage, apart from the user's browser.

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
- **Driving** (a player in a vehicle): the controller possesses the vehicle (`pawn.Controller` None:
  through `DrivenVehicle.Controller`), and the pawn's health properties went wrong (max = health):
  the functions then, both logged once ("vitals check (player driving)") - to confirm in the log.
- **Rarity: the game's** (tools/probe_rarity*.py): `GlobalsDefinition.RarityLevelColors` reads empty,
  but `GetRarityColorForLevel(level)` / `GetRarityLevelColorsIndexforLevel(level)` work: levels sharing
  a colour entry are one tier (5 and 7-10 legendary; 6 E-tech; 500 pearl, 501 Seraph, 506 "Rainbow"
  = effervescent; `GetRarityForLevel` gives EItemRarity but files E-tech under VeryRare). Sent with
  the level payload (`rarity`); the page names tiers by colour entry, colours are the game's.
- (history) Player inspection candidates, before the probes: `InvManager.Backpack` / `InventoryChain` /
  `ItemChain`, `pawn.EquippedItems` / `HolsteredWeaponSlots`, item `DefinitionData`, `RarityLevel`,
  `ExpLevel`, card stat modifiers; `pc.PlayerSkillTree.Skills` / `Branches`; replicated to everyone:
  `PlayerReplicationInfo.StandInGear`, `TrackedSkills`, `ClassModNamePart`.
- **Opened containers on a co-op client** (tools/probe_client_containers.py, Outwash, 2026-09-23):
  opened ones `SimpleAnimState` / `RepSimpleAnimState` 7, unopened 4 - but `bCanBeUsed` stays (1, 0)
  on both (not sent to clients): the host's test (7 + no longer usable) never fired. A client: the
  state alone (`_is_looted(io, client)`; `_client` from the NetMode at each objects scan). Seen
  working in game (user: containers and all their kinds right, as a client).
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
  (`_client_givers`, client only, no host "directive" markers) makes a giver marker per NPC with a
  mission it gives that can be picked up / takes back that's ready (MissionLog.giver_states). Not
  verified in game yet. Bounty boards (`BountyBoard`, several missions in a submenu: also a
  `MissionDirectorParticle`): still to probe in full (none in range in the 2nd run).
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
