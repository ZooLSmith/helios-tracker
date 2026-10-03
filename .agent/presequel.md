# Helios Tracker in the Pre-Sequel

What we know about the mod running in Borderlands: The Pre-Sequel (TPS). The mod is built and tested for BL2; this
file keeps what was seen in TPS - first as it is, with no changes made for it ("out of the box"), then after any
changes made for TPS ("patches"), so each finding says which build it was seen on.

## Setup

- The mod declares TPS: `helios_tracker/pyproject.toml` `supported_games = ["BL2", "TPS"]` (the mod manager marks it
  unsupported without it). Nothing else in the code changed for it.
- The Python SDK installs on its own in TPS (its own `sdk_mods/`, the same mods_base / unrealsdk / pyunrealsdk).
- Dev link: `project.json`'s optional `tps` entry (the TPS install), then `python tools/link_mod.py tps` - the same
  junction as for BL2 (`<tps>\sdk_mods\helios_tracker` -> `<repo>\helios_tracker`), so one checkout runs in both
  games.
- Both games write to the same log files (`helios_tracker/helios_tracker.log`, `helios_crash.log`) through the
  junction: a TPS session is told apart by its paths (`...\BorderlandsPreSequel\sdk_mods\...`) and times.
- `tools/offline_check.py` and the game file extraction use BL2 (`project.json`'s `game`); one Pre-Sequel map
  (ComFacility_P: its movie draws a part of its texture) is extracted too when `tps` is set.

## Out of the box (2026-09-26, first run)

### Works

- The mod loads and turns on; every hook it adds is found (the log's "usability hook works", "pickup spawn hook
  works"); the page is served (`live map at http://localhost:8777/`).
- The game files indexer runs on TPS's packages (9.7 s the first time, then from its cache in 0.1 s) and finds the
  game's fonts (WillowBody, Compacta Bd BT, Chintzy CPU BRK, DFGGothicP-W5, WillowHead, Arial, DFKGothic-Bd).
- The cutscene video hook (`ClientPlayBinkMovie`): `MegaIntro` seen, its length read from the Bink file (323.0 s),
  its end found when the frames came back (skipped after 13.7 s).
- In-engine cutscenes seen with their length (`ClaptrapInro.SeqAct_Interp_2`: 11.5 s).
- The health / shield check on enemies and the player reads (the player: health 98.1, shield 0, `bHasShieldVar`
  True - TPS starts without a shield).
- Ammo on the ground: hovering it shows the right name and the game's own icon (seen by the user).

### Crash (once, not seen again)

- **When**: the first launch, in a new game, 5 s into the `MegaIntro` video (2026-09-26 04:36:24).
- **What**: an access violation in the game's own code: `BorderlandsPreSequel.exe+0x5022b` reading address `0x60`
  (a field of a null pointer). Crash dump: `<tps>\Binaries\Win32\borderlandspresequel_2863302_crash_2026_9_26T2_36_24C0.mdmp`.
- **Thread**: a native game thread. The dump's stack for it holds only game code (no python314 / unrealsdk /
  pyunrealsdk address), and `helios_crash.log` (faulthandler) has no "Current thread", so no Python was running
  on it.
- **What the mod was doing then**: its HTTP threads were idle; its **game files indexer** (a subinterpreter
  thread, reading TPS's packages from disk) was still running.
- **Second launch, mod on**: the same intro, no crash. The only difference seen: the indexer read its cache (`0.1 s
  (not started)`), so it wasn't running during the intro.
- **Where it stands**: not shown to be the mod's. The indexer running at startup, while the game loads, is the one
  thing that differed between the two launches - worth a look if it happens again (another crash with the indexer
  running, i.e. after its cache is cleared or the game updated, would point to it; a crash without it would not).
  No BL2 crash like this is known.
- Reading a dump without tools: the exception stream (type 6) gives the thread, code and address, the module list
  (type 4) turns addresses into `module+offset`, the thread list (type 3) gives each stack's memory to scan for
  addresses into modules. A small `struct` script did it (not kept in the repo).

### Not checked yet

(Seen since, under "After patches": skills, card icons, oxygen, Oz kits / Moonstones, shop names, the Glitch rarity -
notes.md "The Pre-Sequel's rarity table"; a mission's objective order - notes.md "Mission log".)

- The world -> map fit on more of its maps, low gravity (jumps, heights), the Moonshot / Grinder.
- Loot odds (TPS item pools, not the BL2 `GD_Balance.Weighting.*` / `GD_Itempools` names).
- Gear cards for laser guns and cryo weapons in full.
- Co-op, and the TPS DLCs (Claptastic Voyage).

## After patches

### 2026-09-26: card icons, DLC skill icons, containers

- **Item card type icons** (the footer's right icon, the map's loot markers): TPS's card draws them as vector
  shapes (sprite 358 of SharedWillowComponents: a black outline, group 321 at 85 % alpha, under a white fill, 357 -
  solid fills, no strokes); only the pistol's outline is an atlas bitmap. Seen as: the pistol black (its outline
  alone), the others the HUD's weapon icons (yellow: the only full list with bitmaps). gamecards.py now indexes and
  draws solid-fill shapes too (_shape_rgba) - BL2 gained its sniper / shotgun / SMG / AR / launcher outlines (vectors
  too: only their fill showed). Seen right in game.
- **Weapon type names**: from the game (Typename) - TPS's Jakobs sniper type says `'sniper'` in lower case (its pistol
  and shotgun `'Pistol'`, `'Shotgun'`): the game's own data, shown as it is (tools/probes/probe_tps.txt).
- **Skills** (probe_tps.txt, Aurelia Lv 1): the tree reads as in BL2 - 4 branches (the action skill + The Huntress,
  Cold Money, Contractual Aristocracy), 19 tiers, 38 skills, names, grades, SkillIcon, the skill manager, the
  cooldown pool. The DLC characters' skill icons are in `DLC/<code>/Compat/Content/<Code>_<Class>_Streaming_SF.upk`
  (Crocus_Baroness_..., Quince_Doppel_...: no "GD_" as in BL2's DLCs): gameicons.icon_packages now takes any
  `*_Streaming_SF` there (only the classes' in both games).
  The page got the whole tree (read from the live server's `players` event) - but no icon for 37 of her 38 skills:
  their SkillIcon is one shared movie, `SharedSkillIcons_Cro_Aurelia.SkillIcon-Aurelia` (every icon one of its
  external images, SkillIcon-Markswoman.tga...), no texture of that name. TPS's SkillDefinition has a
  **SkillIconTextureName** (a name: "SkillIcon-Avalanche" - the base classes' 55, Aurelia's 65, the Doppelganger's
  61): the texture, in the movie's package. skills.skill_icon() = that, else the movie's path (BL2); used for the
  page's icons and for naming the hidden helpers by their icon (a shared movie would have named them all alike).
  Seen right in game.
- **Action skill before it's unlocked** (both games - never tested before: BL2 gives it at Lv 5): shown "ready"
  at Lv 1 (its cooldown still reads a length, its pool empty). The tree's action skill has Grade 0 until then
  (1 once there: BL2's probe_skill_layout.txt): skills.py sends no "ak" then - the page's "No action skill yet".
- **Nameless active effects** (the Info tab's "Active Effects": three "?" at Lv 1): not tree skills - definitions
  behaviours create, with no SkillName: `GD_PlayerShared.Behaviors.PlayerBehavior_LevelUp:Behavior_AttributeEffect_1.
  SkillDefinition_2` (4 s, twice), `PlayerBehavior_LevelUpNaturally:...` (30 s), `GD_JackCombatNPC.injured.
  JackInjuredDefinition:Behavior_AttributeEffect_4.SkillDefinition_1` (15 s). The game has no name for them; each one's path
  logged once ("timed skill without a name").
- **Health / shield numbers** (both games): the page showed shield 57 / health 108, the game 58 / 107.
  - Exact (the log's "vitals check"): health 107.89 (HealthVar exact), shield 57.70 - ShieldVar / ShieldMaxVar
    drop the fraction (57). A player's shield now comes from GetShieldStrength / GetMaxShieldStrength (ours, or
    everyone's on the host; a co-op client: the properties). They're the game's final values: bonuses (Badass Rank,
    skills...) included - the shield item's own 53 isn't.
  - Health rounded down: the HUD (107.89: 107), and StatusMenuExGFxMovie.SetCondensedHealthWidget's
    `FFloor(GetHealth()) $ " / " $ FCeil(GetMaxHealth())` (the only script rounding it; the same in both games'
    WillowGame.upk). The game shows no max anywhere (that widget is never seen): the page's "/ max" rounded down
    too, full reads full ("107 / 107").
  - Shield: the HUD's UpdateShield is native (no script to read). Readings: 57.70 -> 58, 108.25 -> 108 (BL2),
    54 / 54: to the nearest (Math.round) - inferred from those, not read in the game's code.
  - The page gets the current values truncated to a tenth (rounding one first changed the result: 57.96 -> 58.0),
    the max ones precise (collector.py _vital / _vital_max).
- **Vending machine names**: the page used the vending menu's titles - the Pre-Sequel's HealthShopTitle still says
  BL2's "Dr. Zed's Meds" (WillowGame.int), its map shows "Nina's Nursing". What the game's map shows on hover: the
  machine's InteractiveObjectDefinition.StatusMenuMapInfoBoxHeader (GD_Balance_Shopping.VendingMachines.*, cooked
  into the levels - the Pre-Sequel: "Bullets Etc.", "Nina's Nursing", "The Black Market", "SHiFT Vending Machine";
  BL2: "Ammo Dump Vending Machine", "Zed's Meds Machine"). shops.py names machines by it, else the menu title.
- **Oxygen objects' names** (a map object "Oxygen Cracks ?", "Air Dome Generator Off ?": no balance name, no target
  name): their definition's StatusMenuMapInfoBoxHeader, what the game's map shows on hover - "Oxygen Source" (IO_Oxygen
  Cracks, _Large, _NoMesh: "Replenishes Oz Kits."), "Air Dome Generator" (IO_AirDome_Generator_On / _Off). The
  collector names objects by it after the balance's DefaultDisplayName, before the target name.
- **Oz kits, Moonstones** (the page said "RELICS", "eridium"): Oz kits are BL2's relics' class (WillowArtifact - no
  other class), Moonstones its eridium. The game's words (WillowGame.int): [CategoryLabels] Artifact="OZ KITS" (BL2
  "RELICS"; FRA "KITS D'OXYGÈNE" / "RELIQUES"), [Training] EridiumTitle=Moonstones (BL2 Eridium; FRA "Pierres lunaires"
  / "Éridium"). Localize(Section, Key, "WillowGame") on Object's default object returns them in game
  (tools/probes/probe_tps2.txt) - but the page's labels stay ours, static (the user's call): each label that differs gets a
  ".tps" twin in i18n (group.relic.tps "OZ KITS", currency.eridium.tps, layer.pickup.eridium.tps...), taken when the
  level message says "game": "tps" (games.py's profile; game.js gameKey -> i18n.js setVariant).
- **The Oz meter** (the player's oxygen): `WillowPawn.OxygenPool` / `WillowPlayerReplicationInfo.OxygenPool` (the same
  pool: an OzOxygenResourcePool, CurrentValue / MaxValue 100 / 100, OnIdleRegenerationRate 50, delay 0.5 s -
  probe_tps2.txt). The collector sends "om" (its max, pawninfo) and "ox" (when not full, the state); the page: a white
  bar with a circle pattern scrolling left (img/patterns/oxygen.svg; grey, lighter at the top), under health, above XP (the user's design) -
  the Players list and the Info tab. The HUD's O2 rounding: not known (rounded to the nearest meanwhile).
- **Oxygen Canister** (a pickup, "other" on the page): GD_BuffDrinks.A_Item.BuffDrink_OxygenInstant (Startup.upk) -
  presentation GD_InventoryPresentations.Definitions.Oxygen (util.py PRESENTATION_KINDS "Oxygen": the page's pickup
  layer "oxygen"), icon fx_shared_items.Textures.OxygenCannister_Particle (grey: the game tints it). Its colour: the
  definition's LootBeamColorOverride #0096c8 (B G R A in the package: c8 96 00 00; alpha 0 - set on this one and
  Moxxi's oxygen Slammer only, no BL2 usable item has one) - the layer's colour. Any usable item's own icon (fi) is
  now sent, of a known kind or not.
- **No game name** (their object name as a guess, "?" - right by the rule): the air dome's bubble (IO_AirDome_Bubble_On
  / _Off: a mesh and behaviours, no text), the jump pads / geysers (GD_Co_JumpPads.Interactive.*: none). The
  generator has one ("Air Dome Generator"). The barrels do (GD_Explosives.Barrels.ExplodingBarrel*: "Cryo Barrel",
  "Incendiary Barrel"... on the page as in game) - their definitions carry no text, the name comes at run time (their
  balance / target name): a scan of definitions alone said otherwise, wrongly.
- **Where oxygen is** (built 2026-09-26: the "Oxygen sources" layer, the Pre-Sequel only - dark blue-grey; its domes on: filled, off:
  dashed; their generators and the oxygen fissures (IO_OxygenCracks*) a diamond with "O2"; collector.py _dome /
  _check_domes, re-read with the containers' check; the player's in air / in a vacuum
  right of the Oz meter: collector.py _in_vacuum - tools/probes/probe_oxygen.py, Deadsurface): an air dome's area is its bubble
  (IO_AirDome_Bubble_On, a WillowInteractiveObject): CollisionComponent a SphereComponent whose Bounds.BoxExtent is its
  radius, 1500 x the object's DrawScale (976 / 1687 / 2236 for 0.650 / 1.125 / 1.491; Bounds.SphereRadius is the box's
  corner, x sqrt 3). **On / off** (tools/probes/probe_dome_state.py, Moonsurface, a dome off -> its button pushed -> outside):
  the bubble's CollisionComponent.bAttached, False while off, True once on (the button gives it a new sphere:
  SphereComponent_3 -> _5); the definitions stay "_On" throughout (the name isn't the state), nothing else changes
  (timers, ticking). The player's side: OzVacuumComponent.State VS_InVacuum (off, outside) / VS_InAir (on) - their
  InOxygenTimer / InVacuumTimer count the time in each. The minimap's Icons_OxygenFissure / Icons_OxygenSpots: pools of
  HUD clips (minimap positions only, no object) - no use to find them.
- **Containers**: the page guessed an object's category from its name (chest, crate, box...): TPS's Hyperion ammo
  crate (`InteractiveObj_HyperionAmmo`, loot list AmmoCrateLoot_Hyp) came out "other". Anything with loot (the
  collector's `lootable`) is now a container, whatever its name (model.js objectCategory).
- **Slam switches** (the user found one, 2026-10-02; the Pre-Sequel's packages scanned offline - tacmap.Package, every
  export named like a switch / slam / lever / button, 2026-10-03): 5 definitions, one family -
  GD_GravitySlamSwitch.InteractiveObjects.IO_GravitySlamSwitch (Moonsurface, Outlands, Stanton's Liver, the Wreck, R&D
  Facility, Claptastic Voyage's right cluster), IO_GravitySlam_MoonShack (Moon), GD_EridianSlaughterData...
  IO_Pet_GravitySlamSwitch (the Holodome), GD_Ma_RightBrainCluster_Data...IO_Ma_CorruptionSlamSwitch /
  IO_Ma_AntiVirusNodeSlamSwitch (Claptastic Voyage). **What they share** (not their names): DefaultHitRegionDefinition
  gd_co_motivationdata.HitRegion.HR_GravitySlammer (the slam is damage: bCanTakeDirectDamage, Allegiance
  Allegiance_ExplosiveBarrel - BL2's fuse box's too), and a Behavior_CustomEvent GravitySlam_Used. Slammed, their
  behaviours: ChangeAllegiance -> Allegiance_Player, ChangeUsability, ChangeInstanceDataSwitch Light_Switch, the
  targetable unregistered - the state to read in game (the allegiance?), not probed yet. No Behavior_Explode: not drawn
  as explosives. **Names**: two balances, DefaultDisplayName "Gravity Slam Switch" (BD_GravitySlamSwitch), "Corruption
  Slam Switch" (BD_Ma_CorruptionSlamSwitch) - the collector reads them; the other three have none (a "?" guess, unless
  placed with one). On the page: "other" (model.js objectCategory).
- **The other switches** (both games): buttons, levers, switches on one template - GD_GenericSwitches.InteractiveObjects
  (GenericButton, GenericButtonHyperion, GenericFloorLever, GenericSwitch; BL2's DLCs their own copies,
  GD_<Dlc>_GenericSwitches) and the missions' own (ClaypigeonSwitch, Vent_Button, IO_BookLever...; BL2: ~45 in all).
  What they share: Behavior_CustomEvent Enabled_Used / Locked_Used / EnabledGlowing_Used / LockedGlowing_Used (the
  switch's state machine: enabled or locked, glowing or not). The engine's WillowInteractiveSwitch class: no placed
  instance in either game (its default object only).
