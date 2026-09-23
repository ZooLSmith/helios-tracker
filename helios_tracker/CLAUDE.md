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
  area radius, distance. Panel "Mission" section: tracked mission + its shown objectives. Read every
  1 s from `MissionTracker.MissionWaypoints` (only `bActive` components), sent on change.
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
  layer's settings), `view`, `ui`; validated against the defaults on load (unknown / invalid values
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
- `util.py`: shared helpers (`try_`, `call_str`, `def_name`, `addr`, `log_error`).
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
js/ui/            panel (tabs, Settings), layers (Layers tab), status, mission, players, inspector,
                  detail, items, skills (HTML panels)
```

- Modules only define things at import time (no DOM access): the offline check imports every one of
  them under Node, which also catches broken import paths / names. DOM hookup goes in an `init*()`
  called from `main.js`.
- State changes: mutate `S`, then `invalidate()` for the canvas and the relevant `ui/` render function
  for the HTML. Circular imports are fine (only called at runtime).
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
