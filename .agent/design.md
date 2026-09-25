# Helios Tracker - design wishes (not built yet)

Things the user wants the page to look like, decided but deliberately not done - with why, and what would
have to be true to do them. Leftovers of the retheme toward Borderlands 2's art style (done: gradients,
the game's own fonts - `gamefonts.py`).

## Chamfered corners (45° cuts)

**The wish** (the user, 2026-09-24): Borderlands' UI often cuts panel corners at a sharp 45° instead of
rounding them - most often the top left and the bottom right ("/ ... /"), sometimes other pairs, sometimes the
bottom right alone. The page's panels, cards, tabs, buttons and skill tiles could do the same.

**Not done: no technique is safe enough yet.**

- `clip-path: polygon(...)` (works everywhere): clips everything outside the shape - and the page draws
  outside its boxes on purpose in places: the boosted skill's blue outer ring (`.scell.boosted`, a 2 px
  box-shadow outside the tile), the tiles' drop shadows (`--tile-depth`), glows (the cutscene bar's lit end,
  the bars' outlines), focus outlines. The diagonal also gets no border line (a two-layer workaround exists, a
  clipped border-coloured layer under an inset clipped background one, but it multiplies elements and breaks
  every `border` / inset ring we already use). Too risky to roll out: the user's call.
- `corner-shape: bevel` with `border-radius` (CSS Borders 4): the right tool - borders, shadows and outlines
  follow the cut, nothing is clipped. But Chromium only (shipped 2025): no Firefox support yet, and OBS's
  embedded browser (CEF, an older Chromium) doesn't have it either - the page is shown in OBS.
- Gradient-cut backgrounds (`linear-gradient(135deg, transparent 8px, ...)`): the fill only - borders and
  shadows stay square. Not the look.

**When to revisit:** `corner-shape` supported in Firefox and in the CEF of the OBS versions people use (then
as a progressive enhancement: `@supports (corner-shape: bevel)`, square corners elsewhere - no clip-path
fallback). Build it then as a few shared utilities in `base.css` (`chamfer-tl-br`, `chamfer-br`,
`chamfer-tr-bl`, a `--chamfer` size), piloted on the panel header, the drawer, the tabs and the skill tiles
before anything else.

## Sharing the map over the internet (streamers, friends)

**The scope** (the user, 2026-09-25): sharing the live page through a tunnel is supported for up to **~50
viewers**. More than that isn't something the project provides: the docs give pointers (a relay), nothing we
host or build.

**Why that limit - measured** (a replica of server.py's SSE loop: a fake game thread doing 2 ms of Python work per
frame at 60 fps, 10 updates/s, real socket readers in another process; Python 3.14, 2026-09-25):

| update | viewers | game thread frame: mean / p99 / max | upload |
|---|---|---|---|
| 5 KB | 0 | 2.01 / 2.04 / 2.06 ms | 0 |
| 5 KB | 200 | 2.10 / 2.76 / 2.81 ms | 78 Mbit/s |
| 20 KB | 100 | 2.07 / 2.62 / 6.63 ms | 156 Mbit/s |
| 20 KB | 200 | 2.11 / 2.75 / 2.90 ms | 312 Mbit/s |

- Sending isn't on the game thread: it builds each update once (a JSON string in the Hub); one server thread per
  viewer encodes and writes it. They share the GIL, but the cost stays under 1 ms at p99 for 200 viewers (the
  ~6-7 ms maxima show at 10 viewers too: scheduling).
- **Upload is the wall**: update size x 10/s x viewers. At 20 KB, ~1.6 Mbit/s a viewer - a streamer's upload (also
  carrying the stream) runs out after a handful. 50 viewers is only realistic with the items below.
- Not measured yet: the real update size on a busy level (in game), a burst of page loads (45 files read from disk
  each, + the level's map images), contention with the engine running.

**What 50 needs (not built):** a read-only viewer mode (no inventories), a lower rate for viewers (2-4/s, the
streamer's own page at full rate), a viewer cap (default 50, the count shown to the streamer), maybe changes only
instead of the whole state. First: log the updates' sizes in game.

**Tunnels to document** (free, quick): Tailscale Funnel (the main one: stable HTTPS address, SSE works), ngrok
(free, but a warning page for browsers), SSH tunnels (localhost.run: nothing to install, changing addresses - not
pinggy: its free addresses contain the user's public IP), Cloudflare's quick tunnels (no account, no domain, a random address: tested in game 2026-09-25, the SSE
passes - ~8 updates/s; the first page load is slow: ~45 uncached files), a named tunnel for those with a domain. `sdk_mods/helios_tracker.autoexec.ps1` can start / stop the tunnel with the server. Allow LAN Access isn't needed.

**Pointers for more than 50** (docs only): a relay - the mod sends one stream to a server that fans it out (e.g. a
Cloudflare Worker), so the PC uploads once; a Twitch extension for an in-player map. Either means running a service,
and the map images / icons passing through it would be hosting extracted game art (positions only avoids it).

**Declined: sharing built into the mod** (the user, 2026-09-25) - not to be proposed again:
- the mod starting a tunnel itself (hidden `ssh` to localhost.run, or `cloudflared`) with a "Copy share link" option;
- peer-to-peer for friends: WebRTC in the game's Python isn't realistic (no DTLS / SCTP in the stdlib; aiortc needs
  PyAV, not built for 32-bit Windows), and the workarounds (a hidden headless Edge as the WebRTC host, or a GitHub
  Pages host / join page with a service worker carrying the page's requests over a data channel) all depend on a
  third-party signaling service, need a paid TURN relay for ~1 in 10 connections, and show the host's IP to peers.
Sharing stays the user's own tunnel, documented on the site (the questionnaire, `share.html`).

**Measured: Cloudflare's quick tunnels hold each new stream back for ~30 s** (2026-09-25, in game): the first ~30 s
after the page opens (or an F5) the updates arrive in ~1.5 s batches (gaps up to ~1.9 s), then evenly (~100 ms), like
localhost. Unchanged with `--protocol http2`, an HTTP/1.1 chunked reply with `Cache-Control: no-cache, no-transform` +
`X-Accel-Buffering: no`, or 64 KB of padding first: on Cloudflare's side, time-based. A named tunnel doesn't do it.
The page's reload after a dropped stream restarts it (a reconnect of the stream alone would, too).

## The site's /live/ page (built: a prototype)

**What it is** (2026-09-25): `https://helios-tracker.zoolsmith.com/live/?at=<a tunnel's host>` (the `documentation`
branch's `live/index.html`) opens a shared map from the site's stable address: it fetches the map page from the mod
through the tunnel, adds `<base href="https://<host>/">` and `document.write`s it - every address in the page then goes
to the mod, while the page runs on the site's origin. So the page's settings (localStorage, per origin) survive the
tunnel's changing addresses, and viewers get one recognisable kind of link (the questionnaire's link maker builds it).
The mod allows it: `server.py` `SITE_ORIGINS` (CORS; plus pages on this PC), tested in offline_check; the item icon
loads as CORS (`crossorigin`: `artColour` reads its pixels). Tested end to end through a quick tunnel.

**Open - a safety problem, to fix before it's advertised:** the shell runs whatever page the `?at=` address serves, on
the site's origin: a crafted link can show anyone's content under `helios-tracker.zoolsmith.com` (nothing to steal
there, but it's the user's name). The fix: the page's code from the site itself, per mod version - each release
publishes its `web/` to the `documentation` branch (`live/<version>/`), the mod answers its version (a small
`/version` reply, with CORS), the shell loads that version's page from the site; only data comes through the tunnel.
It fits the release tool (not written yet). Doesn't fix Cloudflare quick tunnels' ~30 s warm-up (in the data).

## Shop prices (the vending machines pane)

**The wish** (the user, 2026-09-25): "design something for prices, especially for the always there stuff". Built so
far: ammo and health vials (every machine has them) aren't item cards but one "Always for sale" price list per tab
(the closest machine's: the same kind sells the same basics); each item card shows the machine's price top right.
**Ideas, not built:** what the tracked player can afford - their cash isn't sent yet (the players payload has no
currency; `pc.PlayerReplicationInfo` / the inventory manager's currency to probe first, and a client's view of the
others'); then prices out of reach dimmed / red, a "you have $x" line in the drawer's heading, maybe a filter
(affordable only). Also: the price per ammo unit / per full refill (the game sells ammo by the pack), the item of the
day's markup vs a normal item. To go with the look rework.

## A 3D map (an optional view)

**The wish** (the user, 2026-09-25): a simplified 3D map in the style of Doom Eternal's - floors and slopes only,
several levels stacked - as an **optional alternative** to the 2D map, never a replacement. Built on **what blocks
the player** only (the user: "only base this on the player's collisions").

**Feasible - checked, not built.** The findings (formats, numbers, the in-game walks) are in notes.md, "Level geometry
for a 3D map". In short: every placed static mesh whose flags block the player (actor + component + Gearbox's
`bBlockPlayers`, resolved through archetypes / class defaults), its per-poly (kDOP) collision triangles, or its simple
collision where it has none; the faces up to UE3's `WalkableFloorZ` (0.7, ~45.6 deg); plus the terrain heightmaps.
Recorded walks: Sanctuary's rooftops 78 of 84 positions on such a surface (the pawn's footprint, within 30 uu),
Southern Shelf's structure 249 of 251 (all 251 with the nav mesh). Unreachable surfaces (Sanctuary's dome, an
invisible safety floor) go through a **reachability** filter: flood fill from the nav mesh - walk, step (<= 40 uu),
jump (<= 150 up), drop (<= 6 m).

**Where the work runs - proposed** (2026-09-25):
- **The mod, in gamework's subinterpreter** (pure Python, its own GIL, results cached in `.cache/`): parsing only - the
  loaded sublevels (live: `WorldInfo.StreamingLevels[i].LoadedLevel`, so the PhysX setting's `_Px` and any
  script-switched sublevel follow the game), placements (matrix / scale per component), each used mesh's collision
  triangles **once per mesh** (a roof mesh placed 43 times is sent once), terrain heights + hole flags, the nav mesh.
  Sent to the page as compact binary on request (like the map images): a few MB a level. Rebuilt when the loaded
  sublevel list changes.
- **The page, in a Web Worker**: placing the meshes, the walkable-face filter, reachability, simplification
  (Sanctuary keeps ~100k triangles, 42 % tiny; Southern Shelf 251k walkable before the filter) - then the WebGL view.
  Result cached per level in IndexedDB (keyed by the level + the loaded sublevels + the mod version).
- **Why not all in the mod**: the game's Python is an embedded 32-bit 3.14 without numpy / scipy. The study's numbers
  (collision extraction ~5 s, reachability 430 s as a naive loop - seconds vectorised) were numpy on a desktop
  Python; in pure Python the geometry would be 10-50x slower, and a million triangles as Python objects is hundreds of
  MB inside the 32-bit game process. A browser's JIT has neither limit, and a Worker keeps the page responsive.
- Nothing extracted is published: the data goes from the user's game files to the user's own browser, like the map
  images.

**The view (to design)**: floors coloured by height relative to "Who", the walkable area's outline edges raised as
low walls (the nav mesh's stored boundary edges - 65535 neighbours - or the filtered surface's own boundary), the
floors far above / below faded (the Floors setting: show / dim / hide > 6 m), markers at their real height. Refreshed
by the frames like the rest (the Refresh rate setting), redrawn only when something moves.

**Still open before building:**
- Other levels: Opportunity (vertical, north offset 325), a rotated map, a DLC level (DLC maps keep their tactical map
  movie elsewhere) - `tools/probe_navwalk.py` + `probe_streaming.py` there, scored like the first two.
- Gaps: brush geometry (`Model` / BSP, BlockingVolumes), `EngineMeshes.Cube` (the engine's own package), the last 5
  rooftop misses; movers are taken at their position in the file (the dome: blocking by its flags - whether it really
  is in game isn't known; reachability drops it anyway).
- The Worker's reachability and simplification, and the transfer format; the WebGL renderer (hand-written or a copy of
  a small library bundled with the page).
- Side finding for the 2D map: on 4 of the 5 levels with a `NorthOffsetInDegreesClockwise` the map image fits the
  world unrotated, while geo.js rotates by it (notes.md, the transform section) - to confirm in game (the rotated
  maps' probe_navwalk run does it) before changing geo.js.
