# Helios Tracker

A **live map of the current level in the web browser**: the mod runs a small local web server, the
page shows the game's own map image (the map screen's) with players, enemies, NPCs, vehicles, loot
and interactive objects on it, with zoom / pan. Read the root `../CLAUDE.md` first.

**Standalone: does not use `z_hud_overlay`** (it draws nothing in game - not a HUD widget).

## Spec

- Options: **Open Map in Browser** (button, `os.startfile(url)`), **Port** (default 8777),
  **Allow LAN Access** (binds 0.0.0.0 instead of 127.0.0.1; phones / other PCs), **Updates Per
  Second** (1-30, default 10). Port / LAN changes restart the server immediately.
- Page: full-window canvas, the level's map image(s), markers (the tracked player - "Who", else the host -
  = yellow arrow, drawn on top; other players = white arrows + names, enemies = red diamonds (like the game's minimap) + health bar when hurt, NPCs green
  dots, vehicles purple, loot = triangles in rarity colour, objects = squares by category). Follow me (F), fit (0),
  **Smooth movement** (on: interpolates between updates, redraws every frame; off: markers jump,
  frames are only requested on a change - data, view, input - for weak / integrated GPUs), tooltip
  (name, kind, health, distance, height difference), world X/Y under the cursor. Wheel / pinch zoom,
  drag pan. Settings remembered in localStorage. Areas without a map: a 10 m grid around the player.
- **Player inspector**: "Players" list in the panel (or click a player's marker) opens a drawer with
  Gear / Backpack / Skills tabs; items show the game's localized weapon type / item name and
  manufacturer, and expand to stats, rarity (name + `RarityLevel`; names confirmed in game, colours
  still ours - the game's table and the gear-only loot filter are in the backlog), parts (labelled by role, localized names where the game has them)
  and class. Map objects use the game's display name (balance `DefaultDisplayName`). The local player is
  labelled "Host" (the player running the tracker). Missing data (co-op client: other players'
  inventories / skill trees) shows a reason instead.
- **Quest markers** ("Objectives" layer): the game's active mission waypoints - area objectives as
  dashed circles (radius = the waypoint's AreaRadius), point objectives as diamonds, quest givers as
  "!" badges; other missions' markers fainter than the tracked one's. Tooltip: objective, mission,
  area radius, distance. Read every 1 s from `MissionTracker.MissionWaypoints` (only `bActive`
  components), sent on change.
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
- **Mission levels** (see notes: a mission's XP depends on its level only, locked when picked up):
  a badge per mission - "Lv 6" (picked up, locked) or dashed "→ Lv 8" (the level it would lock at if
  picked up now: its region's current stage), coloured by the game's difficulty thresholds for the
  selected player; a 5th goal, **Finish first**: picked-up missions, the furthest below the player
  first. GameStage / bGameStageLocked: two property reads per not-done mission per full pass.
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
  arrived (at most every 250 ms), the DOM only written when it changed. Gear stats are the live
  item's (buffs included): no base / buffed split (the user: pointless).
- **Containers**: category from the game's loot list names - an "Epic" list = **Big chests** (red
  chests, orange-red, biggest), a "WeaponChest" list = **Weapon chests** (metal crates, bandit weapon
  chests, amber), else Containers sized by item slots (most items one opening spawns). **Looted**
  (anim state 7 + no longer usable; checked round robin every second) = their own dimmed layer, off
  by default, same sizes. Contents = the item pools their loot rolls from (items only exist once
  opened), in the click panel.
- **Click panel**: clicking any marker opens a detail drawer (players: the inspector) - containers
  (status, slots, loot lists, every pool), loot, pawns (level, shield, health), quest markers.
  Hover / click pick the marker drawn on top (loot > pawns > quest markers > objects; inside the
  marker, last drawn; objects drawn by height).
- **Skills tab**: one tab per tree (default: the one with the most points), the game's grid layout
  (`SkillTreeBranchDefinition.Tiers` + `Layout.Tiers[].bCellIsOccupied`); the root / action skill
  branch hidden. Player vitals (shield then health bars, numbers inside) in the Players list.
- **Layers tab**: categories (Characters, Loot, World: plain headings that fold, no box), a row
  per layer (enabled, marker icon, count, ⚙) and its settings panel inline under it (several can
  be open; Close all). Players can't be hidden (no enabled box), only configured. Folder rows (a tri-state box
  turning their layers on / off, they fold): **Gear** (a layer per rarity; `misc` = rarity 0 /
  unknown), **Pickups** (not gear, a layer per kind: Ammo, Cash, Health, Other - the collector's
  `pk`, from the item definition's inventory card `Presentation`, resolved once per definition:
  see notes; eridium not probed yet, so Other), **Containers** (Big chests, Weapon
  chests, Other containers, Looted). Per-layer
  settings (`model.js` `LAYER_SETTINGS`, which apply per layer in `LAYERS[].settings`): Names,
  Other floors (show / dim / hide, > 6 m up / down from "Who"), Size (50-200 %), Max distance (from
  "Who"), Tracked mission only (objectives). Counts = what passes the layer's filters, on or not.
  No global names / floors / rarity settings any
  more - the loot filter will come back as a Loot setting (to design).
- **Settings tab**: Who (host / a player, saved by name) + Follow / Rotate (map turns to their
  heading; only while following, greyed out otherwise); Movement: game updates only (the mod sends its rate, `hz`), a fps cap, or smooth.
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
    / `GetTargetName()` / AIClass. Health: `GetHealth()` / `GetMaxHealth()`.
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
- `script.py`: an optional, gitignored `autoexec.ps1` next to `__init__.py` runs while the server
  runs (e.g. a Cloudflare tunnel for sharing the map on stream). It gets `HELIOS_PORT`, runs hidden, and its
  output goes to `autoexec.log`. It sits in a kill-on-close job object: server stop, port / LAN
  restart, mod disable, or the game exiting ends it along with its children.
- `skills.py`: the players' skills (action skill, timed effects, melee cooldown), per update.
- `util.py`: shared helpers (`try_`, `call_str`, `def_name`, `addr`, `log_error`, `field`).
- **Per-update / per-pass reads go through `util.field(obj, name)`** (the property looked up once per
  class, then `_get_field`: 1-2 us instead of 15-24 us by name - tools/probe_perf.txt); structs held
  in hand (`loc.X`) and `_get_address()` are cheap already. Function calls cost ~18 us: cache them.
  Slow tasks are logged every 30 s (`helios_tracker.log`), `state` with its parts (skills / pawns /
  pickups / json) and the counts.
- `server.py`: stdlib `ThreadingHTTPServer`; `/` (page, read from disk per request),
  `/<path>.js|css` (any module / stylesheet under `web/`), `/events` (SSE: `level`, `state`, `objects`, `players`, latest
  payload each), `/image/<level>/<n>`. Server changes need a mod reload; page / i18n edits only a
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
                  drawer (what the drawer shows: remembered, restored on a refresh)
```

- Modules only define things at import time (no DOM access): the offline check imports every one of
  them under Node, which also catches broken import paths / names. DOM hookup goes in an `init*()`
  called from `main.js`.
- State changes: mutate `S`, then `invalidate()` for the canvas and the relevant `ui/` render function
  for the HTML. Circular imports are fine (only called at runtime).
- Per-frame code (draw, the Players list's bars / chips) only writes the DOM when a value changed;
  HTML panels that follow live data refresh at the game's update rate, not per frame.
- Pure logic (no DOM) goes in `geo.js` / `dxt.js` / `model.js` / `settings.js`, so it can be tested
  under Node.
- A new per-layer setting: an entry in `LAYER_SETTINGS` (the panel builds its control; `set.<key>`
  translation, plus `set.<key>.<option>` for a choice), its key in the layers' `settings`, and
  its use in `draw.js`'s `style()`. Stored values of a removed setting are dropped on load.

## World -> map (verified in game, see `.claude/documentation/notes.md`)

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
- Release: exclude `reload.py`.
