# Helios Tracker

A **live map of the current level in the web browser**: the mod runs a small local web server, the
page shows the game's own map image (the map screen's) with players, enemies, NPCs, vehicles, loot
and interactive objects on it, with zoom / pan. Read the root `AGENTS.md` first. File names here are the mod's, under `helios_tracker/`
(`tools/...`: the repo's).

It draws nothing in game: everything it shows is on the page.

## Spec

- Options: **Open Map in Browser** (button, `os.startfile(url)`), **Port** (default 8777),
  **Allow LAN Access** (binds 0.0.0.0 instead of 127.0.0.1; phones / other PCs), **Updates Per
  Second** (1-30, default 10). Port / LAN changes restart the server immediately.
- Page: full-window canvas, the level's map image(s), markers (the tracked player - "Who", else the host -
  = yellow arrow, drawn on top; other players = white arrows + names, enemies = red diamonds (like the game's minimap) + health bar when hurt, NPCs green
  hollow rings (not dots: the other pickups are dots of their kind's colour, cash a yellow "$" disc - their own icon, the
  game's PickupFlagIcon, in the tooltip / panel: unreadable as map markers, too detailed; their amount there too:
  amounts.py), vehicles purple, loot = its item card's type icon (a rifle, a shield... the game's art, its white fill in the rarity's
  colour; a triangle until loaded / without one) - clicked, its item's card (stats, parts: the backpack's own record,
  by the item's address - dropped / picked up, the same item), objects = squares by category). Follow me (F), fit (0),
  **Smooth movement** (on: interpolates between updates, redraws every frame; off: markers jump,
  frames are only requested on a change - data, view, input - for weak / integrated GPUs), tooltip (by the cursor -
  below right, else below left / above right / above left: the first clear of the panels and the window's edges)
  (name, kind, health, distance, height difference), world X/Y by the cursor (above it; Settings Show coordinates or C, off by default). Wheel / pinch zoom,
  drag pan (following: a drag lets go of the player only past 40 px - input.js FOLLOW_LET_GO; not following: at once;
  leaving Follow + Rotate - a drag, the box, F - turns the map back north around the player, at once: never eased on
  attach / detach, whatever the Refresh rate; they stay where they are on screen - view.js stopFollow).
  Settings remembered in localStorage. Areas without a map: a 10 m grid around the player.
- **Player inspector**: "Players" list in the panel (or click a player's marker) opens a drawer with
  Gear / Backpack / Skills tabs; items show the game's localized weapon type / item name and
  manufacturer, and expand to stats, rarity (name + `RarityLevel`; names confirmed in game, colours
  still ours - the game's table and the gear-only loot filter are in the backlog), parts (labelled by role, localized names where the game has them)
  and class. Map objects use the game's display name (balance `DefaultDisplayName`). The local player is
  labelled "Host" (the player running the tracker). Missing data (co-op client: other players'
  inventories / skill trees) shows a reason instead.
- **Quest markers** ("Objectives" layer): the game's active mission waypoints - area objectives as
  dashed circles (radius = the waypoint's AreaRadius), point objectives as the game's hollow diamonds (a thick frame, its middle open: _work/mission_objective.png); other missions'
  markers fainter than the tracked one's. Tooltip: objective, mission, area radius, distance. Read
  every 1 s from `MissionTracker.MissionWaypoints` (only `bActive` components), sent on change. A
  co-op client has none: its objective markers come from the level's `WillowWaypoint` actors (their
  linked objective + step restrictions vs the mission log).
- **Quest givers** (own layer, "Missions" - the "!" to pick up, the "?" to hand in): a yellow "!" alone like the game's (a straight bar, a block as wide
  under it, #fecb0d - sampled from the game's map; not a round badge: it read wide) on a dark disc (not the game's:
  the 3D view's stems read as its bar going on); one with a mission to hand in (its list's "end"): the game's
  green "?" instead (#00f800, blocky - a squared hook, its stem, a square dot: sampled, _work/return_questionmark.png);
  mission items, cyan (#3fd8ff - the user's cyan, picked, not sampled): one that starts a mission (its "ms" k
  "gives") the "!" on its disc, one part of a mission under way ("for") a diamond, drawn over their
  NPC. The game's directive waypoints, plus NPCs (`MissionDirectives`) and objects (the bounty board:
  `Directives`) whose lists give a mission that can be
  picked up now / take back one ready to hand in (`_npc_givers`: host and client - the host's
  waypoints missed givers, e.g. Marcus in Sanctuary). The "!" and point objectives ("Speak to...")
  are drawn over the NPC they're on and clicked before it (loot still first; area circles after the
  pawns). Panels link each other: a quest marker's mission(s) (the log; a giver's several, the ones to
  hand in marked), a "!"'s giver (its NPC / object panel, "by"), an objective point's "At" (the object
  / NPC within 3 m); an NPC's / board's panel: its missions and the objective points on it.
- **Mission log** (`missions.py`, the `missionlog` payload): every mission of the playthrough from
  `MissionTracker.MissionList` - status, objectives with progress, the current step
  (`ActiveObjectiveSet`), dependencies, texts (see notes). Definitions read once (cached forever); a
  full pass every 5 s (a heavy task; per entry only what can change: a done one's status, a
  not-started one's status + offered + level if doable, everything for active ones), a fast pass
  over the tracked / active missions every 1 s. Two payloads: `missiondefs` (the definitions:
  names, texts, objectives - only when the list changes) and `missionlog` (the live part:
  status, progress, levels, rewards - small, on every change); the page merges them by id. Panel "Mission" section: the tracked mission and every
  objective of its current step (done / to do, counts, optional); its name opens its details, "All
  missions" the tree. The tree (drawer): story missions in order with the side missions each one
  unlocks under it (`Dependencies`), done / active / available (every dependency done, offered:
  `bHeardKickoff`) / unknown (dependencies done, not offered yet: the game titles it "Inconnu") /
  locked (hidden unless asked); ready to turn in (`MS_ReadyToTurnIn` / `MS_RequiredObjectivesComplete`) in green, with the
  panel's tracked mission saying so (and the turn-in text). A mission's details: description, giver, turn in, base level,
  objectives done + current step, reward (XP, currency, items; alternative), requires / unlocks
  (neutral links with their state; Back walks the history). Rewards: `GetExperienceReward` /
  `GetCurrencyReward` (function calls: only active / available / tracked missions, cached per
  mission and player level). Story missions: yellow + a flag; side missions: grey. Two views (remembered): story chain, or
  by area (`TravelStation.StationDisplayName`, the game's text; areas in story order). Rewards are
  computed per player level (every player's controller on the host, only yours on a co-op client);
  the page shows the selected player's (Who).
- **Best now** (the log's third view, min-maxing): the missions doable now (active / available /
  unknown) + the locked ones a single step away ("after ..."; deeper ones left out), ranked by a
  goal: XP, cash (credits), both (each scaled to the best), per objective left; a mission's better
  reward (normal / alternative) counts. Top 10, "show all". XP shown as the number then its share
  of the selected player's level; the total available XP ≈ levels. `rankMissions` in missions.js.
  Rows (up to 4 lines): name + level; where to go ("Go to" the current step's station, "Turn in at",
  "Given at": `whereTo`); what's next (the step's objectives left, who to turn in to, who gives it);
  "after ..." / objectives left. Too high a level (the game's hard / impossible: 3+ above the
  player) left out and counted; a locked one with no level yet (region never visited) goes by the
  highest of the missions it waits on (a DLC's side missions under its Lv 30 first one).
- **Where you are** (see notes: stations' `StationLevelName` vs the current map): missions whose
  place to go is the current level get a green "You're here" badge (tree, areas, Best now; the text
  itself unchanged); the area view's heading for the current level too. The level's name is the
  game's (`LevelDependencyList.GetFriendlyLevelNameFromMapName`), else made up from the map (marked "?");
  under it the area's level (its missions' regions' game stage, see notes: "Area level 13" / "13-15").
- **Mission levels** (see notes: a mission's XP depends on its level only, locked when picked up):
  a badge per mission - "Lv 6" (picked up, locked) or dashed "→ Lv 8" (the level it would lock at if
  picked up now: its region's current stage), coloured by the game's difficulty thresholds for the
  selected player; a 5th goal, **Finish first**: picked-up missions, the furthest below the player
  first. GameStage / bGameStageLocked: two property reads per not-done mission per full pass.
- **Shops** (`shops.py`, see notes "Vending machines": each machine has its own stock, the timer is the game's):
  the `shops` payload (the level's machines: name = the vending menu's title, the game's; kind; position; stock
  and item of the day as inspector item records, "v" = the machine's price, `GetSellingPriceForInventory`) when it
  changes, `shoptimer` ({left, rate, paused?}: `WorldInfo.Game`, else the replicated GRI) when the page's countdown
  would be off by more than 1 s, or the game pauses / resumes (`Pauser`: its timer stands still, the page's holds; a
  restock sends both). Read every 2 s; new item records built a few ms per pass (a level's
  ~70: never one hitch). Ammo and health vials (`pickup_kind`: every machine always sells them) go apart as
  `basics` (name, price: no card). Info tab: a Shops section - its heading: the restock countdown by a timer icon
  (always, open or folded) and "All"; its body: the 2 closest machines (name, distance, their item of the day in its
  rarity's colour; a click: the list on it), kept current from the frames (the Refresh rate rule). The drawer: a tab
  per kind of machine (named by the vending menu's title, the remembered tab `ui.shopTab`; in the skill trees'
  colours: weapons red, ammo / grenades green, shields / health blue), in it its machines, the closest first, each
  its item of the day then its stock (the item cards), then the kind's "Always for sale" price list (the closest
  machine's); a machine's name opens its panel, which then has a back button to the list (on that machine), and whose
  "For sale" row links back to its tab. A machine's panel (clicked on the map too) shows its stock itself, as in the
  list (`machineStockHtml`; the item of the day's heading has the restock countdown at its right, like the game's
  vending screen), its loot pools ("Can contain": technical there) folded at the bottom like an item's
  parts. Names: the vending menu's localized titles (`VendingMachineExGFxMovie` defaults:
  `WeaponsShopTitle`... by `ShopType` - the pairing inferred from the names; not read: "Vending Machine ?"). Crazy Earl left out (no stock until opened, built per player: only his marker).
- **Info tab sections** (Mission, Shops, Players - meant to hold more of these panes): a heading row (fold chevron, title,
  what fits beside it - Shops' countdown; Players' count, folded only -, a small "All" link opening its drawer)
  whose click folds the section (`ui.closedInfo`,
  remembered). The look to be redone.
- The drawer closes when what it shows is gone (loot picked up, pawn dead, marker done).
- **Drawer restored on a refresh (F5)** (`ui/drawer.js`, `ui.drawer`): what it shows is remembered -
  a player (by name), a mission / the mission list, a map object (by id) - and reopened once its data
  arrives; gone: its category's list (a mission: the mission list; a player: the Players list), a map
  object: closed. Opening / closing by hand before then wins.
- Respawning players (see notes): drawn faded with a dashed ring at the New-U they'll come back at
  (follow goes there), never at the parked position; "Crippled" / "Respawning" over the bars in the
  Players list.
- **In a menu** (see notes: `PlayerReplicationInfo.bGFxMenuOpen` / the pawn's `bViewingStatusMenu`,
  `mn` 1): a "..." badge on their marker, "In menu" over the bars (neutral, when not down), in the
  tooltip and the Info tab's state.
- **Skills** (`skills.py`, see its docstring: verified with tools/probe_passives.txt): every player's
  action skill (ready / running, from the manager's `SKILL_TYPE_Action` skill instance / cooling down,
  from the pool), timed passive effects (a passive's triggered buff: `SKILL_TYPE_Passive` +
  `DURATION_Timed`) and melee skill cooldown. The skill manager is shared: read once per pass (every
  0.2 s) for everyone; definitions cached; full cooldowns every 5 s. By `SkillInstigator` (the
  player's controller): every player on the host, only yourself on a co-op client.
  Players list: an action skill chip right of the name. Player drawer **Info** tab (the default):
  state, vitals, action skill, melee skill, active effects - refreshed only when a game update
  arrived (at most every 250 ms), the DOM only written when it changed. Gear stats: both the card's
  value (the item's own: each attribute's *BaseValue) and the current one with the owner's bonuses (skills, class
  mod, relic), the difference in % - the tool is for the player's maths (the user's call; it once said pointless).
  Backpack items: card values only - the game applies the owner's bonuses to equipped items alone (an estimate from
  an equipped weapon's modifier stacks was considered and declined: the user's call).
- **Areas** (`area` / `fog` layers, the `areas` payload, see notes): the level's discovery areas' names (the
  game's, centred, not-yet-discovered ones dimmed) and a fog of war (off by default): the game's own - the
  level movie's fog blobs (`tacmap.load_fog`, extracted with the map, the `fog` part of the level payload)
  over the areas this player hasn't discovered (`pc.DiscoveredWorldAreas`, read every 1 s, sent as `seen`;
  none on a fully explored map).
- **Cutscenes** (see notes): a video (the `ClientPlayBinkMovie` hook, its length from the .bik file; the game
  renders no frame meanwhile) = the `cutscene` payload -> a CUTSCENE block at the top of the Info tab, a video
  player's bar (elapsed / total, counted by the page); a player in cinematic mode (`bCinematicMode` /
  `GRI.bAllInCinematicMode`, `ct`) = "In a cutscene" over their bars, like a menu.
- **Game fonts** (`gamefonts.py`, see notes): the game's own UI fonts (WillowBody, Compacta Bd BT, Chintzy CPU BRK)
  rebuilt as TrueType from the player's `Startup.upk` at run time (a thread, once per session), served at
  `/font/<slug>.ttf`; `@font-face` + `--font-body` / `--font-head` in base.css (WillowBody is the page's text; Compacta unused: too condensed
  for the small headings).
  Never committed (extracted game files).
- **Skill icons** (`gameicons.py`, see notes): the game's own, from the class packages at run time, served as
  PNGs (`/icon/<path>.png`, decoded on demand, never committed); on the Skills tab's tiles (greyed without points).
- **Item card icons** (`gamecards.py`, see notes): the manufacturer logo and the item type icon, the game's (atlas
  bitmaps of its item card movie), found from its data (the engine config's packages, the sprites labelled with the
  loaded definitions' keys, the element's: the damage types' enum) - no BL2 name hard-coded; served at
  `/cardicon/<manufacturer|element|type>/<key>.png`, **layered** (the lists placed together, by depth: a black outline
  under a white fill), the list nearest the manufacturer's in the movie's tree (the card's, not the ammo's); along the
  bottom of every item (smaller when folded): manufacturer left (its fill in the rarity's colour, 40 % pastel),
  element + type right (the user's order, not the game's; the element's art untouched), the type icon in the
  element's colour = its element card line's (the damage type's own
  `WeaponCardPresentations` line, marked `el`: its TextColor - shock's blue), else the damage type's HUDDamageColor (the
  hit markers': fire's line has no colour - the line gets it too), else the element art's measured colour. The
  element's stat tiles' values in that colour too (exact, not pastel), like the game's card. Non-weapons' type frame: the card's
  `IItemCardable.GetZippyFrame()` ("Artifact", "comm", "Customization_Head": tools/probe_zippy.txt; once per definition).
- **Gibbed code** (`inspector.py gibbed_code`, notes "Item serials"): every item record with a serial gets `gib`, its code
  for Gibbed's save editors (`BL2(...)`, the Pre-Sequel's `BLOZ(...)`, none in Assault on Dragon Keep) - the game's own
  serial (`CreateSerialNumber()`, once per record) finished as Gibbed's copy button does (unique id 0). In the item's
  Details fold: the code (one click selects it) and a Copy button (the clipboard; not a secure context - the page
  opened by another machine's address: the copy command, else the code left selected and "Ctrl+C" on the button).
  Only items with an object on our side: ours, the ground's, the machines' (not the others' backpacks).
- **Item header**: the name and type left; its level top right (red, with a hover tip, above its owner's level:
  the game won't let them equip it) and its price under it. **Effervescent** (the game's `RARITY_Rainbow`, 506):
  the item's rarity colour cycles through pastel hues (name, border, logo tint; the map's loot markers too,
  `model.js rainbowAt`) - stepped at the Refresh rate like the bars' patterns (`patternTiming` "rb"), never a frame
  of its own.
- **The game files' work off the game's Python** (`gamework.py`): the scan and every decode (fonts, icons) run in a
  **subinterpreter** (Python 3.14, its own GIL: beside the game thread, not in turns with it - a plain thread of ours
  froze / lagged the game), fed through a queue; results cached on disk (`.cache/assets`, gitignored). No
  subinterpreters: in process, politely (1 ms switch interval, a pause per decompressed block).
- **The game files' scan** (`gamescan.py`): the fonts, card icons and skill icons found in **one** pass over the packages
  (a gamework job), started when a page first connects (once per session), cached in `.cache/scan.json` (per package,
  by size + date: later sessions scan nothing). Font / icon requests wait for it (`SCAN_WAIT`).
- **Explosives** (Places, `explosive`): what explodes (a Behavior_Explode: barrels...) - a burst in its element's colour,
  its health bar when hurt, an exploded one's wreck left out (`kd`) - and the elemental plants (the game's
  Allegiance_ElementalPlant: Firemelon, Acidolus, Shock Cactus, Cryo Vine), which recharge: never left out, dimmed at 0
  health until they have.
- **Slot machines** (World, `slots`): what costs something to use (its bCostsToUse[0], CostsToUseAmount[0]: the
  collector's `cost`) and has no loot of its own - a tall box, its reels' window. Costing isn't "not a container": golden
  chests cost golden keys (lootable: still chests), bought Moxxtails too (buffs first).
- **Containers**: category from the game's loot list names - an "Epic" list = **Big chests** (red
  chests, orange-red, biggest), the golden chest among them drawn gold (its list EpicChestGoldenLoot: opened with a key), a "WeaponChest" list = **Weapon chests** (metal crates, bandit weapon
  chests, amber), else Containers sized by item slots (most items one opening spawns). **Looted**
  (the "Opened" animation's bit of SimpleAnimState + no longer usable - notes.md; checked round robin every second) =
  their own dimmed layer, off
  by default, same sizes. Contents = the item pools their loot rolls from (items only exist once
  opened), in the click panel.
- **Click panel**: clicking any marker opens a detail drawer (players: the inspector) - containers
  (status, slots, every pool), loot, pawns (level, shield, health), quest markers. **Loot odds** (`lootodds.py`,
  notes "Loot odds"): a container's `odds` - each loot configuration's chance and its pools ([key, how many]); the
  pools' entries and chances in the `lootpools` payload (static, sent when it grows); "Can contain" lists them, the
  likeliest first, a pool opening on its entries (`ui/odds.js`), "~" on every chance (rules inferred, not checked
  against real drops), "if low on health / ammo" beside a weight that depends on it, "Lv 7+" on a pool gated by
  game stage, "?" where the data gives no number (conditional / runtime-built weights). Designer attributes (common
  gear's weight modifier: 0.625 live, base 1): the host's live values (`lootodds.refresh` at each objects scan -
  changed: the odds again, in place, and the pools resent); a co-op client: the base values. The technical rows (loot lists,
  class, definition) in a "Details" fold at the bottom, closed until opened (remembered per object, as items'), their
  names exact (`WillowInteractiveObject`, the definition's full path `dp`; an item card's Details too). **Nearby**
  (right under the panel's rows): everything within 1.5 m of it on the map (and 3 m in height: a quest marker floats
  above its NPC - in 3D, Marcus under his "!" was out) (objects, loot, pawns, point objectives / givers), the
  closest first, each a link to its panel (a player: the inspector) - the markers stacked there one click away.
  Hover / click (`input.js` hitAt) pick what the pointer is ON first - among those by layer (loot > quest points /
  givers > pawns > area objectives > objects), then the last drawn; on none: the nearest centre within reach. (The
  layer used to come first: a pickup nearby beat the chest under the pointer - clicks landed off target; the page
  test checks it.) **Selection highlight** (`draw.js` drawSelection): what the drawer
  shows (an object, a marker, an inspected player - not the tracked one) gets corner brackets sized to its marker and
  a dashed line from the tracked player, both in the tracked colour, over every marker; the brackets breathe when
  the page animates (still with "Updates only"). Opening / closing the drawer redraws at once (`saveDrawer`).
- **Skills tab**: one tab per tree (default: the one with the most points), the game's grid layout
  (`SkillTreeBranchDefinition.Tiers` + `Layout.Tiers[].bCellIsOccupied`); the root / action skill
  branch hidden. Player vitals (shield then health bars, numbers inside) in the Players list;
  driving (the collector's `dv`: the vehicle's pawn id), shield and health side by side and the
  vehicle's health under them (orange). Faint patterns on the bars: shield hexagons, health columns,
  vehicle warning stripes (XP plain).
- **Layers tab**: categories (Characters, Loot, Missions, Services (vendors, slot machines, stations), Places (jump pads,
  explosives, oxygen sources, Vault symbols, other), Map (areas, fog) - one World heading before, too generic: plain
  headings that fold, no box), a row
  per layer (enabled, marker icon, count, ⚙) and its settings panel inline under it (several can
  be open). Buttons: All on / All off (every layer on the map) and Collapse (every category and
  folder folded, every settings panel closed). Players can't be hidden (no enabled box), only configured. Folder rows (a tri-state box
  turning their layers on / off, they fold): **Gear** (a layer per rarity; `misc` = rarity 0 /
  unknown), **Pickups** (not gear, a layer per kind: Ammo, Cash, Eridium, Health, Mission items (WillowMissionItem: ECHO logs, objective items; the objectives' green), Other - the collector's
  `pk`, from the item definition's inventory card `Presentation`, resolved once per definition:
  see notes; eridium not probed yet, so Other; and **Shrines** ("Moxxtails" in the Pre-Sequel; the layer id `buff`): interactive objects you use for a bonus for a while - the
  Pre-Sequel's Moxxtails, BL2's shrines: their behaviours activate a skill and none hands their own loot out, and they spawn an item of
  their own (the Moxxtails' drink) or have loot (a leftover chest list: other skill objects have neither), a pink disc;
  never containers, whatever loot list their balance has; once on sale, a Moxxtail's drink - a pickup you pay for, its
  Base the Moxxtail: the collector's `on` / `cost` - isn't drawn, its price in the Moxxtail's tooltip and Details),
  **Containers** (Big chests, Weapon
  chests, Other containers, Looted). Per-layer
  settings (`model.js` `LAYER_SETTINGS`, which apply per layer in `LAYERS[].settings`, in the panel's order):
  Names (its Name size slider on the same row, no label: 50-200 %, the labels' text; a name starts past its
  marker, whatever it is: every marker shape records its own size (shapes.js `drew`), label() and vitalBars() read
  it - a new shape calls drew too), Size (50-200 %), Other
  floors (show / dim / hide, > 6 m up / down from "Who"), Max distance (from "Who"), Tracked mission only
  (objectives). Counts = what passes the layer's filters, on or not.
  Faded markers (another floor, looted, an untracked quest, a respawning / dead player): drawn whole on a layer of
  their own, faded once (0.45 - draw.js markerLayer), under the others' layer: overlapping, the top one covers the
  rest (they used to blend into an unreadable mix), and one that isn't faded is always over them.
  No global names / floors / rarity settings any
  more - the loot filter will come back as a Loot setting (to design).
- **Turning the map**: right-drag / Shift+drag turns it (`view.spin`, degrees on top of its own turn - the level's north
  offset -, in 2D and tilted; vertically, tilted, it tilts) - around where the drag started, that spot staying under the
  cursor (following: around the player). While Follow + Rotate turn it to the heading, the heading
  owns the turn (the drag only tilts, the spin is set aside). On a touch screen: a two-finger twist (past 10 deg, so a
  pinch doesn't turn it by accident) turns it around the point between the fingers (view.js spinAt). Once turned - or
  while Follow + Rotate turn it to the heading (its click then: Rotate off) - a compass shows in the map's free corner (view.js refreshNorth: the largest area no panel covers, its arrow pointing north
  and an upright N orbiting on its border (the badge's centre there) at the arrow's tip, like a moon (never turned: a turned N read as a Z); bigger on a touch screen; beside the drawer, in the free area's corner - on a
  phone the drawer, an opaque page, covers it); a click or N turns it back.
- **Phones** (up to 520 px wide): the drawer (the right pane) is a solid page of its own over everything - the whole window,
  clear of the notch / home bar, its close button back to the map; room under its content while the status shows (the
  game paused, the connection lost); the mission list's filters always unfolded (their chevron gone); the left panel
  keeps the top 45 %.
- **Settings tab**, grouped by what it changes: **Who** (host / a player, saved by name) + Follow (F) / Rotate (R: map
  turns to their heading; only while following, greyed out otherwise) + Fit map (0); **Map**: Colours (the theme's tint,
  or the game's blue whatever the theme: `view.mapColors`), Background / Map opacity (`look.js`; 0 % background: in OBS
  via its browser source's "Interact"), Markers 50-200 % (every marker, its label and bars - times its layer's Size),
  Tilt (3: `view.threeD` - was "3D view"; the map tilted by an orthographic camera, `view.tilt3d` 0-80 deg, markers
  lifted by their height above the map's plane - the tracked player's height, the tooltips' "x m above / below" origin
  (nobody tracked: the level's typical ground, the median height of its objects) - with a stem down to it; quest areas as ellipses on the plane; toScreen(mx, my, h), toMap on the plane: pan / zoom / clicks
  / coordinates / the fog unchanged. The floors / walls from the level's collision were tried and parked on the
  `experimental/map_3d` branch: design.md), Coordinates (C: was "Show coordinates"); **Panels**: Theme (ECHO-2 - the
  default, id "default" -, Hyperion, Vladof, Dahl, Eridian:
  `css/themes.css` sets base.css's tokens under `<html data-theme>`; the canvas' colours read again on a change), their
  opacity, their size 70-200 %; **Refresh rate** (was "Movement": the page's redraws - markers, bars, their patterns):
  game updates only (the mod sends its rate, `hz`), a fps cap (default 30), or smooth; **Language**.
  A theme also sets the map images' tint (`--map-filter`: a CSS filter, the game's maps always the same blue - drawn
  through a tinted copy per image, `draw.js` mapCanvas; the fog of war's blob too, its bluer blue first turned onto the
  map's), the title's gradient and its "H"'s palette; story missions and
  the tracked player stay the game's yellow (`--story`, `--map-tracked`) whatever the accent.
- **Storage**: one `helios.settings` localStorage object (`js/settings.js`): `layers.<id>` (each
  layer's settings), `view`, `ui` (incl. `drawer`: what the drawer shows); validated against the defaults on load (unknown / invalid values
  dropped), the old one-key-per-setting storage migrated once.
- **Distances**: 100 uu per metre (1 uu = 1 cm), measured (`tools/probe_scale.py`).
- **Translations**: `web/i18n/<code>.js`, one catalog per language (en, fr; listed in
  `i18n/index.js`); static HTML uses
  `data-i18n` / `data-i18n-title`, JS uses `t("key", {vars})` (English fallback, numbers formatted
  per language). Language: browser's, or the Language menu. Python sends codes / raw numbers, never
  UI text; game strings (item, skill, level names) stay as the game gives them.
- Co-op: client side - works on clients too, showing what the host replicates to them.
- Page tech: plain HTML + native ES modules, no build, no external requests (see "The page" below).
  If the HTML panels get painful, Preact + htm (vendored, no build) would only replace `js/ui/`.

## How it works

- `collector.py` (game thread, from `WillowGameViewportClient:PostRender`, rate-limited):
  - level: every 1 s, `ENGINE.GetCurrentWorldInfo()` -> `GetStreamingPersistentMapName()`,
    `GetMapInfo()` -> `TacticalMapMovie` + `TacticalMapVolume`. A change publishes the `level`
    payload and starts the map extraction thread.
  - pawns: `WorldInfo.PawnList` / `NextPawn`, every update. Kind: me (`pc.MyWillowPawn`),
    `WillowPlayerPawn`, `WillowVehicle`, `IsEnemy(me)` -> enemy, else npc. Names: PRI.PlayerName
    / the balance's `PlayThroughs[].DisplayName` (a property: the name functions crashed the game) / AIClass. Health: `GetHealth()` / `GetMaxHealth()`.
  - pickups (`WillowPickup`) and interactive objects (`WillowInteractiveObject`): `find_all` every
    3 s (walks every object - never per update); pickups held as WeakPointers, positions read per
    update; objects are static (sent as their own `objects` payload on change).
  - Per-actor name / kind cached by address, re-resolved at each scan.
- `tacmap.py` (background thread, files only): reads the level's `<Map>_P.upk` from
  `WillowGame/CookedPCConsole` (LZO, both package layouts), the SwfMovie's image placements and the
  Texture2D top mips (raw DXT - the page decodes them). ~0.3-0.5 s per level, cached.
- `inspector.py` (game thread, every 2 s, only sent on change): each player pawn's gear
  (`InvManager.InventoryChain` / `ItemChain`), backpack (`InvManager.Backpack`) and skills
  (`pawn.Controller.PlayerSkillTree`); falls back to `pawn.Weapon` when there's no InvManager.
  Unverified in game - `tools/probe_inventory.py` checks what's really there (solo / host / client).
- The collector does nothing but follow the level while no page is connected (`Hub.clients`).
- `script.py`: an optional PowerShell script runs while the server runs (e.g. a tunnel for sharing the map on
  stream): the mod folder's `autoexec.ps1` (a folder install - the dev junction; gitignored), else
  `sdk_mods/helios_tracker.autoexec.ps1` beside the mod (the players' place: a `.sdkmod` is a zip). It gets
  `HELIOS_PORT`, runs hidden, and its output goes to `autoexec.log` / `helios_tracker.autoexec.log` beside it. It sits in a kill-on-close job object: server stop, port / LAN
  restart, mod disable, or the game exiting ends it along with its children.
- `skills.py`: the players' skills (action skill, timed effects, melee cooldown), per update.
- `shops.py`: the vending machines' stock, prices and the restock timer (`shops` / `shoptimer`), every 2 s.
- `util.py`: shared helpers (`try_`, `call_str`, `def_name`, `addr`, `log_error`, `field`).
- **Per-update / per-pass reads go through `util.field(obj, name)`** (the property looked up once per
  class, then `_get_field`: 1-2 us instead of 15-24 us by name - tools/probe_perf.txt); structs held
  in hand (`loc.X`) and `_get_address()` are cheap already. Function calls cost ~18 us: cache them.
  Slow tasks are logged every 30 s (`helios_tracker.log`), `state` with its parts (skills / pawns /
  pickups / json) and the counts.
- `server.py`: stdlib `ThreadingHTTPServer`; `/` (page, read from disk per request),
  `/<path>.js|css|png|svg|woff2` (any module / stylesheet / image / font under `web/`: `img/favicon.png` = the tab icon,
  64 x 64, the logo; `fonts/helios-h-*.woff2` = the panel title's "H", the logo as a font of one letter - see base.css;
  both built from the logo's sources, a local repo kept out of git in `_work/logo/`), `/events` (SSE: `level`, `state` - only what moves, sent only when something did: per pawn a row
  `[id, x, y, z, health?, {shield, players' yaw, flags...}?]`, full health / shield left out -, `pawninfo` - the pawns'
  kind / name / level / max health / max shield - and `pickups`, both on change, `objects`, `players`... Record
  channels (`state`, `pawninfo`, `pickups`, `items` - the gear pickups' item records, a few built per update -,
  `objects`, `players`, `missionlog`, `missiondefs`, `shops`:
  `Hub.publish_records`) send only what changed since the version the page has - records added / changed (a dict
  record: its changed fields, `-` the ones it lost), ids gone, the order when it changed; a page behind gets what it
  missed at once, a new one (or one too far behind) everything - data.js `keyed()` merges them back into the whole
  list its handlers get (a message out of step: a new stream). The other channels: their latest payload whole -
  `assets` {cards}: what the server can serve from the game's files now (the map's gear icons wait for it)),
  `/image/<level>/<n>`, `/texture/<path>.png` (an always-loaded texture by object path: a pickup's icon). Server changes need a mod reload; page / i18n edits only a
  browser refresh. The Hub holds
  the payloads; server threads never touch UObjects. The running server is kept on
  `sys._helios_tracker_server` so a reload can always stop the previous one.

## The page (`web/`)

```
index.html        markup only (data-i18n attributes); <script type="module"> calls main.js start()
css/              base.css (colours, canvas, tooltip) · panel.css (left panel) · drawer.css (inspector)
i18n/             en.js, fr.js (export default {key: text}) · index.js lists them
js/main.js        start(): every DOM hookup, in order
js/state.js       S (the one state object) + queries: frame, pawnPos, targetPawn, findPlayer, findDetail
js/settings.js    what's remembered (one object, validated, legacy migration)
js/i18n.js        t(), num(), applyI18n(), setLanguage()
js/geo.js         world <-> map, yaw (pure)        js/dxt.js    texture decoding (pure)
js/model.js       LAYERS / LAYER_GROUPS / LAYER_SETTINGS, rarity, names, object categories (pure)
js/data.js        SSE /events -> S (onLevel, onState, onObjects, onPlayers, onMissions)
js/scheduler.js   invalidate(): frame requests per the Movement setting
js/view.js        canvas, W/H, toScreen / toMap, fit, zoom, follow
js/draw.js        one frame (markers, S.hits, layer counts)  js/shapes.js  marker shapes, labels, COLORS
js/input.js       wheel / drag / pinch / click / keys, hitAt   js/tooltip.js  hover tooltip, coordinates
js/missions.js    the mission log: states, the tree, objective states (pure)
js/icons.js       the icons: inline SVGs (currentColor), icon(name) - no emoji / glyphs as icons
js/ui/            panel (tabs, Settings), layers (Layers tab), status, mission (Info panel), missionlog
                  (drawer: tree, details, back history), players, inspector, detail, items, skills,
                  shops (Info section + drawer: the vending machines), drawer (what the drawer shows:
                  remembered, restored on a refresh)
```

- Modules only define things at import time (no DOM access): the offline check imports every one of
  them under Node, which also catches broken import paths / names. DOM hookup goes in an `init*()`
  called from `main.js`.
- State changes: mutate `S`, then `invalidate()` for the canvas and the relevant `ui/` render function
  for the HTML. Circular imports are fine (only called at runtime).
- Per-frame code (draw, the Players list's bars / chips) only writes the DOM when a value changed;
  HTML panels that follow live data refresh at the game's update rate, not per frame. Whatever changes by itself
  (countdowns...) is refreshed from the frames, so it follows the Refresh rate setting - no timers of its own
  (AGENTS.md "Page refreshes follow the Refresh rate setting"; offline_check enforces it).
- **Colours are tokens** (`css/base.css` `:root`): a theme sets its inputs (`--bg`, `--tint`, `--text`,
  `--accent`; `css/themes.css`), the surfaces / edges / text shades are `color-mix()`es of them (any token can
  still be set by a theme). CSS uses `var(--...)` only; the canvas reads them at start through
  `look.js` `tokenColor` (a mix resolved to a plain colour) (`shapes.js` `initColors` -> `COLORS`, the layers' `--layer-<id>` via
  `model.js` `setLayerColors`); inline SVGs use `style="fill: var(--...)"` (not presentation attributes).
  Not tokens: the game's rarity colours, plain black / white shading and masks. A new colour: a token first.
- Pure logic (no DOM) goes in `geo.js` / `dxt.js` / `model.js` / `settings.js`, so it can be tested
  under Node.
- A new per-layer setting: an entry in `LAYER_SETTINGS` (the panel builds its control; `set.<key>`
  translation, plus `set.<key>.<option>` for a choice), its key in the layers' `settings`, and
  its use in `draw.js`'s `style()`. Stored values of a removed setting are dropped on load.

## World -> map (verified in game, see `notes.md`)

```
c = volume.BrushComponent.Bounds.Origin, upp = volume.UnrealUnitsPerPixel * 4   (32 * 4 = 128)
movie x = (Y - c.Y) / upp,  movie y = -(X - c.X) / upp        world +X = map up, +Y = right
image placed at its shape's bounds in movie px; yaw 0 = up, clockwise
```

## Dev

- `python tools/offline_check.py` covers it: real map extraction (Sanctuary, Southern Shelf), a
  fake level load through the collector, the server (page, image, SSE), and the page's JS under
  Node (DXT5 decode vs a reference decoder, world->map vs the probe samples).
- In game: `pyexec helios_tracker/reload.py`; page edits only need a browser refresh.
- Probes: `tools/probe_map.py` (level, map info, volume), `tools/probe_map2.py` (samples the
  minimap's MapClip against the player position, to fit the transform).
- Release: exclude the dev files (`reload.py`, `.cache/`, logs; see the root `AGENTS.md`).
