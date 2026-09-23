# Helios Tracker

A **live map of the current level in the web browser**: the mod runs a small local web server, the
page shows the game's own map image (the map screen's) with players, enemies, NPCs, vehicles, loot
and interactive objects on it, with zoom / pan. Read the root `../CLAUDE.md` first.

**Standalone: does not use `z_hud_overlay`** (it draws nothing in game - not a HUD widget).

## Spec

- Options: **Open Map in Browser** (button, `os.startfile(url)`), **Port** (default 8777),
  **Allow LAN Access** (binds 0.0.0.0 instead of 127.0.0.1; phones / other PCs), **Updates Per
  Second** (1-30, default 10). Port / LAN changes restart the server immediately.
- Page: full-window canvas, the level's map image(s), markers (me = yellow arrow, players = cyan
  arrows + names, enemies = red diamonds (like the game's minimap) + health bar when hurt, NPCs green
  dots, vehicles purple, loot = triangles in rarity colour, objects = squares by category). Layer toggles with counts, loot rarity
  filter, follow me (F), names (N), fit (0), dim markers on other floors (> 6 m up/down),
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
- **Settings**: Who (host / a player, saved by name) + Follow / Rotate (map turns to their heading);
  Movement: game updates only (the mod sends its rate, `hz`), a fps cap, or smooth; layer icons show
  the marker shapes; show all / hide all.
- **Distances**: 100 uu per metre (1 uu = 1 cm), measured (`tools/probe_scale.py`).
- **Translations**: `web/i18n.js` holds one catalog per language (en, fr); static HTML uses
  `data-i18n` / `data-i18n-title`, JS uses `t("key", {vars})` (English fallback, numbers formatted
  per language). Language: browser's, or the Language menu. Python sends codes / raw numbers, never
  UI text; game strings (item, skill, level names) stay as the game gives them.
- Co-op: client side - works on clients too, showing what the host replicates to them.
- Page tech: plain HTML/JS, no build. If the UI keeps growing, consider Preact + htm (vendored, no
  build) or Vue / Svelte with a Vite build into `web/`; the i18n catalogs carry over as-is.

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
- `util.py`: shared helpers (`try_`, `call_str`, `def_name`, `addr`, `log_error`).
- `server.py`: stdlib `ThreadingHTTPServer`; `/` (page, read from disk per request), `/<name>.js`
  (scripts next to it: `i18n.js`), `/events` (SSE: `level`, `state`, `objects`, `players`, latest
  payload each), `/image/<level>/<n>`. Server changes need a mod reload; page / i18n edits only a
  browser refresh. The Hub holds
  the payloads; server threads never touch UObjects. The running server is kept on
  `sys._helios_tracker_server` so a reload can always stop the previous one.
- `web/index.html`: one file, no build, no external requests.

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
