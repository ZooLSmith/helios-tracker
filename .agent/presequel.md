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
  games. On this machine: `E:/SteamLibrary/steamapps/common/BorderlandsPreSequel`.
- Both games write to the same log files (`helios_tracker/helios_tracker.log`, `helios_crash.log`) through the
  junction: a TPS session is told apart by its paths (`...\BorderlandsPreSequel\sdk_mods\...`) and times.
- `tools/offline_check.py` and the game file extraction still use BL2 (`project.json`'s `game`) only.

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

- The map itself: TPS's tactical maps (their objects and textures, the world -> map fit), levels with low gravity /
  oxygen (Elpis), the Moonshot / Grinder / oxygen-kit things (TPS-only object classes).
- The panels: missions, skills (TPS characters' trees), shops, loot odds (TPS item pools, not the BL2
  `GD_Balance.Weighting.*` / `GD_Itempools` names).
- Gear cards for TPS-only types (Oz kits, laser guns, cryo / ice elements, Glitch rarity).
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
  and shotgun `'Pistol'`, `'Shotgun'`): the game's own data, shown as it is (tools/probe_tps.txt).
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
- **Containers**: the page guessed an object's category from its name (chest, crate, box...): TPS's Hyperion ammo
  crate (`InteractiveObj_HyperionAmmo`, loot list AmmoCrateLoot_Hyp) came out "other". Anything with loot (the
  collector's `lootable`) is now a container, whatever its name (model.js objectCategory).
