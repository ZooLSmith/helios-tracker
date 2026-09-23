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
| eridium | not seen yet (none on the ground) | ? | ? |

- Also consistent per kind: `PickupFlagIcon` (`fx_shared_items.Textures.ItemCards.Health` / `Credits` /
  `Ammo_<type>`), `DroppedImpact` (`GD_Impacts.Loot.Loot_Drop_Ammo` / `_Health` / `_Cash`),
  `ExternalAttributeEffects[].AttributeToModify` (ammo: the weapon's `D_Attributes.AmmoResource_*`
  pool; cash: `D_Attributes.Currency.CreditsOnHand`), `OnUseConstraints` (health: HealthCurrentValue).
- `ItemDefinition.ItemName` is localized ("Munitions pour mitraillette", "Argent", "Médecine
  d'urgence !") - `GetShortHumanReadableName` is empty for cash and sometimes for health.
- The made-up rarity levels: `ItemDefinition.BaseRarity.BaseValueConstant` (health 171, cash 181,
  ammo 0).
- A pickup lying in an opened container has `Base` = that `WillowInteractiveObject` (e.g. a Locker).

## Backlog

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

- **Player inspection** (gear, backpack, skills): `tools/probe_inventory.py` - waiting for in-game
  runs (solo, co-op host, co-op client). Candidates: `InvManager.Backpack` / `InventoryChain` /
  `ItemChain`, `pawn.EquippedItems` / `HolsteredWeaponSlots`, item `DefinitionData`, `RarityLevel`,
  `ExpLevel`, card stat modifiers; `pc.PlayerSkillTree.Skills` / `Branches`; replicated to everyone:
  `PlayerReplicationInfo.StandInGear`, `TrackedSkills`, `ClassModNamePart`.
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
