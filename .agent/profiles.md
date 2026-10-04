# Game profiles: the plan (bl1 branch)

The audit of how the mod handles different games, the `bl1` branch against `master` (2026-10-03), and what we want to
change. To discuss: nothing here is built yet. Once agreed and done, what stays true moves to `AGENTS.md` / `notes.md`
and this file goes.

## Where we are

`master` had game differences scattered around: `Game.get_current()` in `inspector.py`, a `GIBBED_PREFIXES` dict,
Pre-Sequel cases in `collector.py`, `hasattr` tests. The branch replaced that with `games.py`: one `Profile` class per
game (BL2 the base, TPS / AoDK / BL1 overriding what differs), picked once at import (`games.GAME = _current()`), plus
`web/js/game.js` on the page. That part is right and stays:

- Picked once, at import: no per-call game detection. Every call site reads `games.GAME` late (no
  `from .games import GAME`), so `offline_check` can swap it.
- Dispatch costs nothing that matters (a feature test in the per-pawn loop is ~100 ns).
- `game.js` (71 lines, pure) is fine as it is.

What doesn't scale: `games.py` is 825 lines, `Profile` ~50 methods across every domain (missions, item cards, shops,
skills, objects, pawns, the map, the UI), and BL1's class ~470 lines of real implementation (a level script search,
skill icons, localizing branch names, mission caches). Each new difference adds a method every game inherits; a
fourth game makes it unreadable. And BL1's code is split between `games.py`, `inspector.py`
(`_skills_from_player_skills`, `BL1_BRANCHES`), `levelmap.py` (`landmark`) and `bl1map.py` / `bl1fonts.py` /
`upk_bl1.py`.

## The target: a `games` package of components

A profile becomes a set of **parts**, one per domain, each a small class (by domain, not one module per game: the
user - else giant files again). A game overrides a part by subclassing that part only; the profile says which parts it
uses. A game close to BL2 stays **one file** (`tps.py`, `aodk.py`: its data and a few small overrides); a game gets
**its own folder**, one file per part it overrides, once that file stops being short or shares little with BL2 (BL1).

```
helios_tracker/
├── __init__.py              # builds the mod; boot: games.pick(), then GAME.assets.start() (no SCAN / FONT_LIBRARY)
├── collector.py             # the game thread's reads. _check_level → util.level_changed() (every cache reset)
│                            #   markers: GAME.missions.markers(...)       (no WAYPOINT_MARKERS branch)
│                            #   level load: GAME.missions.level_objects() (no WAYPOINT_MARKERS branch)
│                            #   map: GAME.world.map_source(...)           (no TACMAP test)
│                            #   oxygen / discovery: features - systems the game has or not
├── inspector.py             # item cards, players. Element icons: GAME.items.damage_type_frame / learn_element
│                            #   (no LEARNED_ELEMENTS); BL1's skill reading moved out ←
├── missions.py              # the mission log. Current objectives: GAME.missions.current_objectives
│                            #   (no MISSION_STEPS); hasattr(…, "ObjectiveDefs") gone into the part ←
├── shops.py                 # GAME.shops.timer_paused (no own Pauser read) ←
├── server.py                # its own routes (/, static, /events, map images); the game's files: GAME.assets.serve(path)
│                            #   (fonts, icons, card icons, textures - waits inside) - no bl1map, no gamescan ←
├── util.py                  # try_, field... + on_level_change / level_changed: the reset registry ←
├── levelmap.py              # MapSource only (the type both games' maps return); tactical → games/bl2/, landmark → games/bl1/ ←
├── gamework.py              # the worker: runs a job naming its own function ("games.bl1.files.bl1map:card_icon") -
│                            #   no table of jobs, no game's module imported by name ←
├── gamedir.py               # the game's folders (GAME.exe_depth, GAME.packages)
├── formats/                 ← the file formats, no game in them: what each game's decoders build on
│   ├── upk.py               #   UE3 packages (BL2's version 832 the base; BL1's subclass in games/bl1/files)
│   ├── swf.py, swfshape.py, swffont.py   #   Scaleform movies, shapes, DefineFont3
│   └── fonts.py             #   the web font catalogue (FONTS) and to_ttf: gamefonts' shared half
├── lootodds.py, amounts.py, i18n.py, updater.py, paths.py, script.py # (unchanged; per-level caches registered)
│
├── games/                   ← replaces games.py
│   ├── __init__.py          #   GAME (picked once at boot: pick()), make_profile, the registry - no SDK import
│   │                        #   features: OXYGEN, JUMPPADS, DISCOVERY - only systems a game has or not
│   ├── profile.py           #   Profile: its data (key, features, gibbed_prefix, packages, exe_depth...)
│   │                        #   + its parts (world, missions, items...); level_changed() → each part's,
│   │                        #   registered with util.on_level_change; failures logged once per method
│   │
│   ├── bl2/                 #   Borderlands 2: THE BASE - its parts are every game's default
│   │   ├── __init__.py      #     the BL2 profile: data + parts
│   │   ├── world.py         #     map_name, world_paused, level_key, map_source, level_name_in,
│   │   │                    #     local_pawn, movie_no_skip
│   │   ├── missions.py      #     entries, objectives, progress, status, number, home, offered,
│   │   │                    #     directives, current_objectives, level_objects, markers
│   │   │                    #     (co-op client: actors - a runtime test, inside)
│   │   ├── items.py         #     equip_kind, card_level, zippy_frame, element_frame/_level,
│   │   │                    #     learn_element, card_line_value, presented_decimals, rarity_table,
│   │   │                    #     card_icon_png, card_icons_ready
│   │   ├── objects.py       #     behaviors, is_looted, destination
│   │   ├── pawns.py         #     name, raw_name, vehicle_name
│   │   ├── shops.py         #     selling_price, timer_source, timer_paused, currency
│   │   ├── skills.py        #     read, action_locked
│   │   ├── assets.py        #     start (the scan when a page connects), serve(path): its fonts / icons /
│   │   │                    #     card icons / textures, waiting on the scan itself
│   │   ├── ui.py            #     show_message, hide_message
│   │   └── files/           #     ← its decoders: tacmap.py, gamescan.py, gamecards.py, gameicons.py,
│   │                        #     compacted fonts (gamefonts' BL2 half) - TPS / AoDK use them as BL2's
│   │
│   ├── tps.py               #   the Pre-Sequel: BL2's profile + its data (key, BLOZ, +OXYGEN, +JUMPPADS)
│   ├── aodk.py              #   Dragon Keep: BL2's profile + its data (no Gibbed prefix)
│   │
│   └── bl1/                 #   Borderlands 1: BL2's parts, except those it overrides
│       ├── __init__.py      #     the BL1 profile: data (CookedPC, depth 1...) + which parts are its own
│       ├── world.py         #     Bl1World(World): map_name from StreamingLevels, paused by status menus,
│       │                    #     landmark map ← (from levelmap.py)
│       ├── missions.py      #     Bl1Missions(Missions): playthrough log + _NotPickedUp, cached by missions
│       │                    #     picked up; eligibility read once per pass; waypoint-actor markers
│       ├── items.py         #     Bl1Items(Items): equip slots, tech level frames, card lines, rarity ranges
│       ├── objects.py       #     Bl1Objects(Objects): behavior sets, bCanBeUsed, map changers' exits
│       │                    #     (cleared by level_changed)
│       ├── pawns.py         #     Bl1Pawns(Pawns): grade names, AIPawnName, vehicle DisplayName
│       ├── shops.py         #     Bl1Shops(Shops): no controller in the price, GRI timer, dollars
│       ├── skills.py        #     Bl1Skills(Skills): PlayerSkills, branch names, skill icons
│       │                    #     ← (from inspector._skills_from_player_skills, BL1_BRANCHES)
│       ├── assets.py        #     Bl1Assets(Assets): its font library at boot, serve(path): its card / menu icons
│       ├── ui.py            #     Bl1Ui(Ui): the HUD message
│       └── files/           #     ← bl1map.py, bl1fonts.py, upk_bl1.py (no SDK: the worker imports them)
│
└── web/js/
    ├── game.js              # unchanged: gameKey, hasFeature (oxygen / jumppads / discovery), gameData()
    └── model.js ...         # layers: `needs` a feature, or the game's noLayers - as today
```

(`←`: new or moved.) Shared modules never ask which game it is nor test a "how" flag: one call,
`GAME.<part>.<method>()`. A fifth game: another folder, overriding only the parts that differ.

## The principle: SOLID's, no coupling, no hacks

What the user wants, by the names Java gave it - simplified for Python (the idea, not the ceremony):

- **Interface segregation**: small interfaces per domain (world, missions, items, assets...), not one 50-method
  `Profile`; who reads missions depends on the missions part only. (The split by domain.)
- **Dependency inversion**: the main code depends on the interface ("get the map"), never on a game's implementation.
- **Open / closed**: a new game or a new way of doing a job is a new class - no main code file changes (no `if`, no
  job added to `gamework`).
- **Liskov substitution**: any game's part stands in for BL2's - same inputs, same shapes returned, same contract; a
  caller never needs to know which one it got.

In Python: **BL2's part classes are the interfaces** - plain classes (`games/bl2/missions.py` `Missions`), their
docstrings the contract, the other games subclass them. No separate abstract classes (BL2 is the base anyway: they'd
only repeat it - worth it only for a game sharing nothing with BL2). The main code calls the part it's given and
never names a game's class.

The hacks this rules out (today's, to remove):

- **Stand-ins imitating game objects** - `_NotPickedUp` imitates a log entry (`Status`, `bHeardKickoff`), a
  property calling a game function behind the caller's back. A part returns the contract's records (the same shape
  BL2's does), not something shaped like another game's objects.
- **Callers that don't trust the contract** - `try_` / `getattr(x, ..., default)` around a part's call (failures
  logged by the parts instead - point 1 below).
- **Flags choosing a "how"** - the features table above.
- **Asking which implementation** - `isinstance` on a profile or part, a game's key tested in Python.

## The rule: the main code doesn't know other ways exist

The user: BL2 / the main code shouldn't even know that BL1 does it differently - it calls one function
(`GAME.world.map_source(wi, name)`: "get the map") and that resolves to the game's own. So, in the main code
(everything outside `games/<other game>/`, BL2's parts included):

- **No branch, no mention.** No `if` on a game or a "how" flag, and no comment naming another game's way ("BL1's:
  ...", "(Borderlands 1: its font library)") - today ~111 comment lines name a game in the shared modules (`inspector`
  22, `collector` 19, `gamework` 16, `levelmap` 11, `gamefonts` 7...; ~28 more in the page's JS). The why of a game's way (its probe, what was seen) is written in
  its override, in its folder.
- **One way in per job.** The main code names the job (`map_source`, `markers`, `serve`), never which of its
  versions; the base method's docstring says what it returns, not who overrides it.
- **Dependencies point one way.** `games/bl1/` imports BL2's parts and the shared modules; nothing outside it imports
  from it (the registry finds the profile by the game's name).
- **Checked.** `offline_check`: the main code's files (and `games/bl2/`) grepped for other games' names and their
  modules (`bl1`, `Borderlands 1`, `bl1map`...) - a hit fails, as its timer check does.

To look at: the Pre-Sequel's own systems in `collector.py`. Its oxygen pool / vacuum is read behind `OXYGEN`
(collector 537-555, 1311); but its air domes, dome generators and oxygen fissures are **not gated**: definition-name
tests (`"AirDome_Bubble"`, `"AirDome_Generator"`, `"OxygenCracks"` - collector 1069-1076) on every object in every
game, and `_check_domes` / `_domes` (957, 334...) ungated too. Systems a game has, not another way of doing BL2's job -
but they'd be cleaner as the TPS profile's (`tps.py` growing an objects part: `objects.extra_record(io)`), the main
code only asking "this game's extra records"; at the least, gated. (Jump pads: no Python - the page tests the class,
`model.js:206`.)

## File decoding: each game's own

How a game's files are decoded belongs to its profile; the shared code knows no game's decoders, BL2's included
(the user). Today it does: `gamework.run_job` has a `do` table naming BL1's jobs (`swffont`, `menuicon`, `cardicon`,
`cardframe`, `itemicon`: `from . import bl1map`), `server.py` imports `bl1map` for `/icon/menu.*`, `levelmap.py`
imports `bl1map` for its landmark map, and BL2's decoders (`gamescan`, `gamecards`, `gameicons`, `tacmap`) sit at
the top as if every game's.

- **Three layers.** `formats/`: the file formats, no game (UE3 packages, Scaleform). `games/<game>/files/`: a game's
  decoders, on those formats (BL2's scan, card layers, tactical maps; BL1's vector maps, font library, clip icons).
  The profile's parts: when and what to decode (`assets.start`, `assets.serve`, `world.map_source`).
- **The worker runs any job, knowing none.** A job names its function (`{"fn": "games.bl1.files.bl1map:card_icon",
  ...}`), the worker imports that module (as `helios_work.<module>`) and calls it: a new decoder needs no line in
  `gamework.py`. (Its modules: no SDK at module level - the worker has none.)
- **The server asks the profile.** `GAME.assets.serve(path)` -> (type, bytes) or None for the game's files (fonts,
  icons, card icons, textures: BL2's from its scan, BL1's from its movies) and does its own waiting; the server keeps
  the page, the events, the map images.
- **One map type, each game's source.** `levelmap.MapSource` stays shared (what the collector and the page get);
  BL2's tactical map and BL1's landmark map are their `world.map_source`, in their folders.

Call sites read the part: `games.GAME.missions.status(entry)`, `games.GAME.items.element_frame(inv, kind)`,
`games.GAME.shops.selling_price(...)`. Plain data stays on the profile (`GAME.key`, `GAME.features`,
`GAME.gibbed_prefix`, `GAME.packages`...).

What the parts give us besides the split:

- **State with an owner.** A part keeps its own caches (BL1's missions, exits, skill clips), and its per-level ones
  are cleared by the level reset (below, "Level changes": its `level_changed()` registered there) - no cache works
  out by itself that the level changed.
- **Failures seen, not swallowed** (below): parts are where the logging wrapper goes, once.
- **A new game** = a folder; a new difference = one method on one part, not on a 50-method class.

`AGENTS.md`'s rule becomes "game differences: in `games/` and `web/js/game.js`, nowhere else" - the same idea, a
package instead of a file.

## Features say *what* a game has, never *how* it's done

The real mess isn't the file's size: it's call sites branching on features - "no SCAN? then FONT_LIBRARY? then do
this". Features are used for two different things today:

- **A system the game has or not** (Oz oxygen, jump pads, discovery areas / fog): the work skipped, the page's layer
  hidden. That's a feature, and the page needs it.
- **Two ways of doing the same thing** (where fonts come from, where mission markers come from, how an element gets its
  icon): that's a choice between implementations, written as flags, so every call site re-decides it with
  `if / else`. That's what methods are for.

The test: **if the `else` branch does something (not just nothing), it's a method, not a feature.**

What that means for today's nine features (the page reads only `oxygen`, `jumppads`, `discovery` - `model.js` `needs`):

| Feature | What it really is | Becomes |
|---|---|---|
| `OXYGEN`, `JUMPPADS`, `DISCOVERY` | a system the game has | stay features (the page's `needs`; the work skipped) |
| `SCAN` + `FONT_LIBRARY` | where the game's fonts / icons come from - two flags for one choice, tested nested (`__init__._scan_game_files`, `server.do_GET`) | an **assets** part: `start()` (BL2: the scan when a page connects; BL1: its font library at boot), `wait_for(path)` (what the server waits on before serving `/font/`, `/icon/`...) |
| `WAYPOINT_MARKERS` | where mission markers come from: the tracker's waypoint components or the level's waypoint actors (`collector` 771-773, 1699) | the **missions** part: `level_objects()` (what to collect at a level load) and `markers(tracker, active)` - the co-op client case (actors, whatever the game) stays inside BL2's part: a runtime condition, not a game one |
| `MISSION_STEPS` | which objectives are current: the step's, or all of them (`missions.py` 239) | the **missions** part: `current_objectives(entry, index)` |
| `LEARNED_ELEMENTS` | how a damage type gets its element icon: learned from weapons seen, or the game's frames (`inspector` 387, 641) | the **items** part: `damage_type_frame(enum)` and `learn_element(enum, frame)` (BL1's: nothing to learn) |
| `TACMAP` | whether the level has a map - but `map_source` already returns `None` for none (`collector` 448) | dropped: the test is redundant |

What's left: three features, all page-visible, all "has it or not". A call site then reads as one line
(`markers = games.GAME.missions.markers(tracker, active)`), and BL1's way lives in BL1's folder instead of an `else`
in `collector.py`. Rules for `AGENTS.md`:

- A feature is a system a game has or lacks, only. Never two features for one choice, never `if feature: A else: B`.
- No nested feature tests: if one comes up, a method is missing.
- A runtime condition (co-op client, a menu open) is tested where it happens, inside the part - not mixed into the game
  test.

## What else the audit found

To fix during the move (each changes code the move touches anyway):

1. **Profile failures are swallowed.** About 55 call sites are `try_(lambda: games.GAME.x(...), default)`: a method
   wrong for a game returns the default, nothing logged - the "no `try_` to guess the game" rule broken one level
   down (BL1's accuracy 7 for the game's 6.7 was this). Fix: the parts' public methods wrapped so the first failure
   per (method, exception type) is logged; call sites keep their defaults.
2. **BL1's mission list rebuilt on every call.** `mission_entries` builds the log + ~218 `_NotPickedUp` wrappers +
   218 address reads each time, called by the fast pass (1 s), `_waypoint_markers` (1 s) and each slice of the full
   pass (60 entries a slice, ~5 slices every 5 s). Fix: the not-picked-up part cached, keyed on the set of missions
   picked up.
3. **Game function calls hidden in a property.** `_NotPickedUp.bHeardKickoff` calls `GetMissionEligibility` on each
   read (~200 calls per full pass); `mission_offered` one per giver mission per second. Function calls are the costly
   part of an update. Fix: read once per pass, kept by the missions part.
4. **BL1's exits cached by area name, not by level** (read in the code, not reproduced in game). `_destinations` keeps
   the map changers' destinations by object address (worked out from the level's script: costly, so cached) while the
   area name stays the same. Save & quit, continue: the menu has no interactive objects, nothing asks, the cache
   stays; back in the same area, the name matches - the old addresses are returned, the new objects miss (no
   "Exit to ...") or one at a reused address gets another's destination. BL2 hasn't this one: its exits are read from
   each travel station's own properties (`collector._exit_text`), nothing cached. Fix: the level reset (below).
5. **Game checks left outside the profile:**
   - `hasattr(mission, "ObjectiveDefs")` (`collector.py` waypoint components, `missions.py` objective dependency) -
     from `master`, but BL1's definitions have no `ObjectiveDefs`: those paths silently skip there. Into the missions
     part (BL1's: none of those paths).
   - The `/icon/menu.*` route (`server.py`) calls `bl1map.menu_icon_png` in every game: through the profile, like
     `card_icon_png`.
   - `shops.py` reads `Pauser` itself (on purpose: BL1's status menus stop the world, not its shops' timer) - a
     second "paused" next to `world_paused`: a `shops.timer_paused` of its own.
   - `rarity_table`: one `try_` around the whole table (it was one per level): one bad read loses every colour.
6. **"The game doesn't have X" in two places.** Python's features (oxygen, discovery...) and the page's `noLayers`
   (BL1: eridium, vault symbols, buffs, slot machines). Each makes sense; a new game needs both looked at - to say in
   the docs at least. (`TACMAP`: dropped - see the features table.)

## Performance

Still a concern (the user). What the restructure costs, and what costs for real:

- **Dispatch: nothing that shows.** `games.GAME.missions.status(e)` is one attribute lookup more than today's
  `games.GAME.mission_status(e)` (tens of ns). In a per-tick loop over pawns / entries, the part is read once before
  the loop (`missions = games.GAME.missions`) - a local, as the code already does with its caches.
- **The failure logging (point 1): one wrapper call per part method** (~0.1-0.2 us: a frame and a `try`). Hundreds of
  calls a second at most - nothing; but it's applied once, when the profile is built (not per call, no `__getattr__`
  magic), and a method the main code calls per pawn per tick can opt out if a measure ever says so.
- **What actually costs: the game's functions and `find_all`**, not Python's structure (the collector's own notes:
  "function calls: the costly part of an update"; `find_all` walks every object). So each part method's contract
  says what it does - property reads (cheap, per tick fine), a game function call (per record / per pass, never per
  tick), a `find_all` (once per level, cached) - and a part never hides a call behind something that looks like a
  read (`_NotPickedUp.bHeardKickoff`: a function call per property read).
- **The plan's BL1 fixes are performance fixes**: the mission list rebuilt several times a second (point 2), ~200
  eligibility calls per pass (point 3) - BL1 today is the slow game, not the structure.
- **The level reset**: clearing a cache costs its refill. Static game data stays (a `find_all`-built list rebuilt at
  every level would be a regression); the per-level ones refill as they're read, spread over the level's first
  seconds - next to the map extraction the level change already does.
- **The worker's jobs by name**: the module imported once in the worker, then a dict lookup - as today's `do` table.
- **Measured, not guessed**: the collector's slow-task report (`SLOW_MS`, every `SLOW_REPORT_EVERY`) before and after
  each step, in BL2 and BL1 (a few minutes in a busy area: Sanctuary, Fyrestone) - a step that shows up there is
  fixed before the next.

### Game-thread hitches: the baseline

The mod runs on the game thread: its work is the game's frame time - 10-100 ms hitches now and then, from the full
scans and others (the user). The restructure must not make it worse (the user): no step adds game-thread work, each
is measured against this baseline. From `helios_tracker.log`'s slow-task reports (> 4 ms, every 30 s), 2026-10-03:
75 BL2 / TPS sessions (older builds among them: rough), 7 BL1 ones - the median of each report's worst, how often:

| task | BL2 / TPS | BL1 |
|---|---|---|
| `missions` (every 1 s) | 6 ms, 17 of 30 s | **11 ms, 28 of 30 s** |
| `mission log` (the full pass, sliced) | 5.5 ms, 4x / 30 s | **7 ms, 38x / 30 s** |
| `scan objects` (every 120 s) | 38 ms | **116 ms** |
| `scan pickups` (every 120 s) | 12 ms | **27 ms** |
| `state` (every tick) | ~10 ms, ~3x a second | the same |
| `players` (every 2 s) | ~10 ms | ~9 ms |

- **BL1's missions: points 2-3** (the list rebuilt per call, eligibility calls) - near constant, every second.
- **BL1's scans: ~3x BL2's** - partly, likely, `collector._out_of_sight` (added on this branch for every game: each
  object's components listed, each mesh's `HiddenGame` read, at every full scan) - not measured apart yet.
- **Every game's baseline** (`state`'s 10-40 ms spikes, `scan objects`' 100+ ms): not this plan's, but its rules
  apply to new work: per-tick work is property reads only; a game function call per record or per pass, never per
  tick; a `find_all` (it walks every object) once per level or behind a long timer, its results processed under a
  time budget (as `object records`' `RECORDS_SECONDS`) - and never a new one in a part without saying so.
- Worth its own look, later (`design.md`): the 120 s full scans as safety nets - the spawn hooks already catch new
  objects; could they be rarer, or sliced over ticks?

## Level changes: one reset, every cache registered

What's behind point 4, and not BL1's only: nothing tells the mod's caches that the level changed. The collector knows
exactly when (`_check_level`: a new level key -> `_clear_contents`), but it clears its own state only, plus one
hard-coded `clear_fields()` (`util._fields`, whose comment says why: "a class freed, another one at its address, would
get a stale property"). Every other cache never resets, or guesses (BL1's area name).

The fix, small and independent of the package:

```python
# util.py
_level_resets: list[Callable[[], None]] = []

def on_level_change(reset):  # a per-level cache registers its clear, where it's defined
    _level_resets.append(reset)
    return reset

# collector._clear_contents
for reset in _level_resets:
    reset()
```

`on_level_change(_explosions.clear)` beside the cache; `clear_fields` becomes one of them; the profile (its parts
later) registers its `level_changed()` - BL1's exits first, then its mission caches (points 2, 3).

Each cache, one choice: **per level** (keyed by addresses of level objects, or of definitions that may be unloaded -
cleared: a refill at the next read) or **static** (game data that never changes - kept: BL1's `_missions`, a
`find_all` over every object; the files scan, on disk anyway). Unsure: clear - it costs a refill, not a wrong answer.

To check, then sort: the module caches keyed by address and called "static", never cleared, in every game -
`inspector._explosions`, `_buffs`, `_plants` (object definition addresses), `collector._loot_info`,
`missions._defs`, `_stations`, `skills._defs`, `_trees`, `util._pickup_kinds`, `lootodds._inits`, `_containers`...
Fine while their definitions stay loaded (most are `GD_*`, always loaded); not checked whether some live in a level's
own package (unloaded, their address reused: a stale answer). Not seen happening.

Not a problem: imports inside profile methods (a microsecond, against import cycles); an unknown game raising at
import (`supported_games` keeps the mod out of other games).

## Audit inventory (2026-10-03, branch `profiles`)

Five read-only sweeps before starting (the profile API, hidden game differences, file decoding, caches and costs,
tests / tools / page / docs). What they found that the sections above didn't have - each line to act on, or decide.

### The profile API

- **TPS and AoDK override data only** (`key`, `gibbed_prefix`, TPS's features). Every method override is BL1's.
- **Data attributes, placed**: `vending_class`, `vending_titles` -> shops; `ui_stat_kinds`, `gibbed_prefix` -> items;
  `damage_presentation` -> items, **as a method** (`items.card_damage(value)`: its `None` branch rounds - an "else
  that does something", inspector 170-174, 245-250); `packages`, `exe_depth`, `key`, `features` -> profile data;
  `tick_function` -> profile data, **read at import** (`__init__.py:309` `RELOAD_HOOK`): `pick()` runs before it -
  right after the imports at the top of `__init__.py`.
- **Liskov holes today**: `font_catalogue` and `damage_type_frame` exist only on BL1, called through the base type
  behind a flag (`__init__.py:495`, `inspector.py:641`). Absorbed: `assets.start()`; `items.damage_type_frame(enum)`
  with BL2's learned table (today's `inspector.element_frame`) as the base.
- **Name collision**: the features table's `items.element_frame(enum)` (now renamed there) clashed with today's
  `element_frame(inv, kind)` (an item card's element key). The damage type's one is `items.damage_type_frame(enum)`.
- **Card icons are assets, not items**: `card_icon_png`, `card_icons_ready` run on the server's threads, no SDK ->
  `assets.serve` / `assets.ready()`. `BL1_CARD_KINDS` goes with them.
- **`object_directives`** is called only from the objects pipeline (collector 827, 882): objects part, not missions.
- **`local_pawn`**: pawns part (the plan had it in world).
- **BL1-only helpers made private**: `skill_icons`, `branch_names` (public today, used only inside BL1 - and named in
  inspector, bl1map, offline_check comments).
- **Parts reach each other through their own profile, never `games.GAME`**: BL1's exits call `map_name` (objects ->
  world); `offline_check` patches `profile_bl1.map_name` then calls `object_destination` (1362-1369). A part gets its
  profile at construction (`self.profile.world.map_name(...)`) - else substitution and that test break.
- **BL2's code living in the main modules, called back by its parts**: `pawn_name` -> `collector.pawn_display_name`,
  `read_skills` -> `inspector._skills`, `action_skill_locked` -> `skills._action_locked`, `mission_home` ->
  `missions.station`; BL1's `card_line_value` -> `inspector._remapped`, `mission_home` -> `collector.level_name`. Each:
  moved into BL2's part, or the back-import accepted as "the main code's helper" (a function of no game) - per case.

### Game differences hidden outside the profile (besides those above)

| where | what it hides | becomes |
|---|---|---|
| `inspector.py:91-93` `_kind` | BL2's class table, then `or GAME.equip_kind(inv)` (BL1's one class): two ways chained | `items.kind(inv)` (BL2's: the class table) |
| `inspector.py:1159-1162` | no player info on the pawn -> `pc.PlayerReplicationInfo` (BL1's driver pawn) | `pawns.player_info(pawn, pc)` |
| `skills.py:58` | `try_(SkillIconTextureName)` - TPS's property, absorbed in BL2 and BL1 | `skills.icon(def)` |
| `missions.py:85` | `try_(def_name(o))` - BL1's objectives are structs, no name | `missions.objectives` returning the records |
| `util.py:231-234` | `bMissionItem` - BL1's mission pickups, read in every game | `items.pickup_kind` |
| `collector.py:1119-1128` + `1065` | `_exit_text` (BL2's travel stations) next to `object_destination` (BL1's map changers): one job, two ways | one `objects.exit(io)` -> (text, area) |
| `collector.py:1531`, `missions.py:180` | `hasattr(..., "ObjectiveDefs")` (known) | missions part |
| `collector.py:639` | `local_pawn(pc) or field(pc, "Pawn")` - a caller not trusting the contract | the part's contract |
| `model.js:206-207` | `o.c === "OzPlayerJumpPad"`, `"WillowInteractiveNPC"` - game classes on the page | a record flag from Python (the part's), or `gameData()` |

Runtime conditions, fine as they are: `collector.py:198, 568, 1470, 1794`, `inspector.py:308, 1132, 1167`,
`skills.py:181`, `util.py:268`, the enums' `getattr(v, "name", v)`.

The page's per-game **data** outside `game.js`, keyed by `gameKey()`: `base.css:156` (`--layer-pickup-eridium-tps`),
`base.css:181-191` (`:root[data-game="bl1"]`), 6 `*.tps` label keys in each of the 9 catalogs. Keyed data, not
branches - "To decide".

### File decoding

- **Mixed modules to split**:
  - `tacmap.py`: BL2's tactical map / fog decoding -> `games/bl2/files`; `MapImage`, `MapFog` (bl1map uses `MapImage`)
    -> next to `MapSource` (`levelmap`, made SDK-free: its `import unrealsdk` (line 18) is landmark's only, which
    leaves for `games/bl1/`).
  - `gamefonts.py`, four parts: `Glyph`, `GameFont`, `to_ttf`, `slug` -> `formats/fonts.py`; the compacted font
    reader (Scaleform's DefineCompactedFont) -> `formats/` too (a format, not BL2's); BL2's font libraries
    (`FONT_LIBRARIES`, `font_library`, its job) -> `games/bl2/files`; `GameFonts` / `FONTS` / `set_catalogue` (state
    calling gamework: glue, not a format) -> the assets side, outside `formats/`.
  - `gameicons.py`: `decode_dxt`, `png`, `_rgb565` -> `formats/image.py` (used by gamecards, BL1's jobs, a probe); the
    rest -> `games/bl2/files`.
  - `gamecards.py`: card art decoding -> `games/bl2/files`; **its key registry** (`set_keys` / `keys` / `listener` /
    `ready` - filled by the inspector for every game, read by BL1's profile, `__init__`) -> shared (the items / assets
    side); `engine_packages` (UE3 ini reading, used by the scan and fonts) -> `formats/`.
- **Duplicates to merge** into `formats/swf.py`: `gamefonts.movie_raw` = `swf._movie_raw`; `gamecards._movie_tags`
  repeats `swf._movie_tags`.
- **Cross-imports, after the splits**: BL1's decoders import formats only, never BL2's decoders (today: bl1map ->
  `tacmap.MapImage`, bl1fonts -> `gamefonts`, `gamework._bgra_png` -> `gameicons.png`); `formats/` imports no game
  (today `swffont` -> `gamefonts`). BL1 importing BL2's *parts* stays fine (the base).
- **The worker**:
  - its setup skips only the top `__init__.py`: importing `helios_work.games.bl1.files.bl1map` runs `games/__init__`,
    `games/bl1/__init__`, its parts, BL2's parts... Sturdier than "no SDK in `games/`": `WORKER_CODE` pre-registers
    bare stub packages (`helios_work.formats`, `.games`, `.games.<game>`, `.games.<game>.files`) so no package
    `__init__` runs there; and the registry maps a game's name to its module path (imported by `pick()` only).
  - GAME is never set in the worker: nothing it runs may read it (`gamedir.cooked_dir()` - the job carries paths).
  - `WORKER_CODE`'s `from helios_work import gamework, upk` -> `formats.upk`; `_polite` reads `gamescan.SWITCH_INTERVAL`
    / `PAUSE` (a BL2 decoder's constants in the generic worker) -> gamework's own.
  - jobs `{"fn": "games.bl1.files.bl1map:card_icon_png", ...}`: BL1's functions return BGRA today -> `*_png` worker
    functions encoding with `formats/image.png` (`_bgra_png` leaves gamework); the font catalogue's 6th field (the job
    kind, `"swffont"` from `bl1fonts.py:49`) -> the `fn`. **An `fn` is never built from a URL**: `serve(path)` maps a
    route to a function in code; the URL only fills arguments.
  - the disk cache's key includes the job: every asset decoded once more after the switch (harmless).
  - untested: subpackage imports through zipimport in the subinterpreter (a `.sdkmod`) - `offline_check` runs the
    worker from the junction only.
- **`__init__.py` names BL2's decoders**: `gamecards.listener = _publish_assets`, `gameicons.textures_ready()`
  (371, 380), module-level imports of gamecards / gamefonts / gameicons / gamescan (29) -> `assets.ready()` and a
  listener on the assets part.
- **Server routes** (`do_GET` 236-264): `/font/`, `/icon/` (BL2's textures), `/icon/menu.*` (BL1's - tested before
  `/icon/`: the order matters), `/cardicon/`, `/texture/` and their waits -> `assets.serve(path)`; the regexes
  (39-43) and `SCAN_WAIT` with them. The server keeps `/`, static files, `/events`, `/image/`.
- `swfshape` / `swffont` serve only BL1 today but are generic Scaleform: `formats/` (their comments made neutral).

### Caches

- **Correctness bugs, not staleness - fix first**: `inspector._skills_cache` (inspector 80) and `_class_names` (1109)
  are keyed by controller / PRI address, never cleared: a new controller at a reused address with the same points (0
  on a new character) gets the old one's tree; co-op and character switches the class names. Also `skills._trees`
  (50), and `inspector._zippy`'s fallback to `addr(inv)` (an item instance, 602). All per level.
- **Unsure (definition-keyed, never cleared)**: `_explosions`, `_buffs`, `_plants`, `collector._loot_info`,
  `lootodds._containers`, `_inits`, `util._pickup_kinds`, `inspector._base_chances`, `_static`, `_grids`,
  `_stats_cache` (function calls to refill: ~100 `GetSkillEffectPresentations` per player), `skills._defs`,
  `missions._defs`, `_stations`, `_rewards` (function calls). "Most are `GD_*`, always loaded" is unverified: UE3
  cooking copies objects not in the startup packages into each map's package, keeping their `GD_` path. Settled by a
  probe: WeakPointers to a sample of each cache's keys, checked after a level change and after save-quit-continue.
- **Instead of clearing, for the expensive ones**: a WeakPointer checked on each hit (as `_ItemCache` does) - no
  refill of function calls at every level (clearing them would add a hitch per level).
- **Raw UObjects held across levels**: BL1's `_missions`, `inspector._accuracy_pres`, `_damage_pres` -> WeakPointers.
- **The reset comes late**: `_check_level` polls every second, while the new level's spawn hooks fire during loading
  with the old level's caches (`_fields`' properties: a freed UProperty could crash). Reset from a load hook, or the
  hooks check the level is still the same.
- **Register in `pick()`, not in a constructor**: `offline_check` builds profiles 7+ times - each would pile up in
  the reset registry.

### Game-thread costs not in the plan

- BL1's `element_level` / `element_frame` (4 game function calls) on **every players pass (2 s), per equipped item**
  (inspector 190 via `_equipped_item`) - static per item: into the cached record.
- BL1's `skill_icons`: a `find_class` and the whole layout walked **every players pass, per player**, before the
  cache check (games.py 622, 652) - cache per CharacterName like `branch_names`.
- **Per-tick game function calls**: `GetShieldStrength` + `GetMaxShieldStrength` for each player with a shield
  (collector 1295, 10 Hz) - against the plan's own rule.
- `collector.level_name`: a `find_all("LevelDependencyList")` **per new map name** (collector 158) - BL1's
  `mission_home` asks one name per mission waypoint level: the first mission pass can run ~N `find_all`s, in slices
  whose budget is checked only between entries. The lists are static: found once.
- The 120 s scan resets `_info` (collector 600): the next tick rebuilds every pawn and pickup at once (`IsEnemy`,
  `GetExpLevel`, `GetShortHumanReadableName`...) - likely the `state` spikes after each scan.
- `object_spawned` builds a record synchronously in **two** hooks (`PostBeginPlay`, `InitializeBalanceDefinitionState`),
  outside the `RECORDS_SECONDS` budget.
- BL1's `map_name` (walks `StreamingLevels`) once per object record, via its exits (gone with the level reset).
- `inspector.py:852`: a `find_all("WillowDamageTypeDefinition")` only to get an enum type - `find_class` does it.
- BL1's `_mission_definitions`: its `find_all` runs again on every call while the result is empty.
- `inspector.py:315` `find_all("WeaponTypeDefinition")` once per session: a DLC loaded later is missed.
- **`_out_of_sight`** (~50-100 us per object: `list(io.Components)`, a `try_` and a class name per component, a
  by-name `HiddenGame` read per mesh at 15-24 us): likely much of BL1's 116 ms scans. Cheaper: `util.field` reads
  (~10x), `bDeleteMe` tested first, and only for definitions that can hide (a per-definition cache: their behaviours
  hold a `Behavior_ChangeVisibility`). And a hide after a scan (T.K.'s Food) shows only at the next scan, 120 s later:
  a hook on the visibility change, if one exists (a probe), would be cheaper and immediate.

### Tests, tools, docs

- **`offline_check`** (the SDK faked, `Game.get_current()` -> "BL2"; everything through `import helios_tracker`):
  - ~60 flat profile calls (1217-1436) -> part calls; the feature assertions (1216: the level message's list ->
    `["discovery"]`; 1221 TPS; 1222 BL1 -> `set()`; 1344-1345 the constants); the `_NotPickedUp` test (1393-1395)
    rewritten; the instance patches (2157, 2180, 2181: `GAME.mission_entries`, `GAME.map_name`) -> part attributes,
    bypassing the missions cache.
  - module paths that move: tacmap (460, 610...), gamecards (471, 709), gameicons (481, 669), gamefonts / gamescan /
    gamework (634), swfshape (754), bl1map / upk / upk_bl1 (778-779), bl1fonts (823), bl1map (1425); `run_job` with
    `"do"` jobs (818, 830, 859, 861, 865) -> `fn`.
  - its JS strings (196, 213: `setGame(..., ["tacmap"...])`) and comments (188, 804, 809, 833, 1215, 1217).
  - **new tests**: each registered profile's parts subclass BL2's with the same signatures (`inspect.signature`); the
    grep rule; the worker's imports without the SDK, the worker's way (stub packages), with no game files configured;
    `run_job` with an `fn` in a subpackage, an unknown one refused; the level reset (every registered reset run, the
    profile registered once); the failure logging (one line per method and exception type). AoDK is tested for its
    Gibbed prefix only.
- **Probes**: `dump_tacmap_movie.py`, `find_fonts.py` load `upk.py` / `swf.py` by file path (-> `formats/`, and they
  break once those use relative imports); `extract_pickup_icons.py` imports gamecards / gameicons / upk;
  `probe_bl1_exits.py:81` reads `helios_tracker.games`'s `GAME.map_name`; `check_navwalk.py` is **already broken**
  (`from tacmap import ...` with relative imports inside).
- **Fine as is**: `build_sdkmod.py` (git's files, subfolders included), `reload.py` / `updater.reload_mod` (drop every
  `helios_tracker.*`, nested too), `release.py` (loads `updater` - `util.py` must stay SDK-free at module level and
  import `games` only inside functions, as today).
- **The page**: no functional change - it reads only `oxygen`, `jumppads`, `discovery`; `setGame` sees the shorter
  list once. Comments naming `games.py` (`game.js` 1, 3, 64, 68; `model.js:60`; `ui/skills.js:21`), `gamecards`
  (`shapes.js`, `ui/items.js`), `gamefonts` (`base.css`).
- **Docs to update**: `AGENTS.md` (83-90 the rule; 18-39 the layout; 106 the grep rule next to the timer check; 135
  the bl1 line; the level reset); `.agent/spec.md` (159-193 the asset modules, 330-357 games / features / file
  readers, 438, 454); `.agent/bl1.md` (31 lines: `games.py` x23, `upk_bl1`, `bl1map`, `swfshape`, `bl1fonts`, the
  feature names); `notes.md` (822-844); `design.md` (5, 140); `presequel.md` (72, 125).
- **`pyproject.toml`**: `supported_games = ["BL2", "TPS", "BL1"]` leaves out `"AoDK"`, which has a profile and a
  test - add it, or say why not (before this refactor).

## How to get there

Each step leaves the mod working and `offline_check` passing:

0. *(mostly done, 2026-10-04 - tag `pre-profiles`: the controller caches, BL1's missions / eligibility / element levels /
   skill icons / exits, `_out_of_sight`'s reads, plus the stall work - architecture.md. Left: the per-tick shield calls,
   the air domes gated, `level_name`'s find_all per map name.)* **Correctness and cost fixes that need no restructure** (the inventory): the controller-keyed caches
   (`_skills_cache`, `_class_names`, `skills._trees`, `_zippy`'s fallback); BL1's mission list and eligibility
   (points 2-3), `element_level`, `skill_icons`; `level_name`'s `find_all` per map name; the per-tick shield calls;
   `_out_of_sight`'s cost; the air domes gated. Each measured against the baseline.
1. *(done: games.py `_logged` - each profile method's first failure of each exception type logged, then raised)*
   **Log failures** (point 1) - small, and the next steps benefit from it.
2. *(the registry done: util.on_level_change / level_changed - clear_fields, the target names, the profile's
   level_changed (BL1's exits) registered. Left: the reset at load time - a hook to find, a probe; the unsure caches -
   the WeakPointer probe.)* **The level reset** ("Level changes"): `on_level_change`, `clear_fields` and BL1's exits registered (point 4);
   reset from a load hook (or the hooks checking the level); the unsure caches settled by the WeakPointer probe.
3. *(done, 2026-10-04: learn_element / damage_type_frame, current_objectives, assets_job / wait_for_assets,
   level_lookups / mission_markers; the six flags gone - features: discovery, oxygen, jump pads. The docs naming the
   old flags - spec.md, bl1.md - follow in step 7.)* **Features into methods** (the table): the six "how" flags out, their call sites one line each. Doable in today's
   `games.py` before the package - the clearest win for the least churn.
4. **The package, same behaviour**: `games.py` -> `games/`, methods moved to parts, call sites and `offline_check`
   (~77 lines, ~60 flat method calls to make part calls) updated. No logic changes: a pure move, so its diff can be read as one.
5. **BL1's code gathered** into `games/bl1/`, **the decoders split** (the inventory's "File decoding": formats,
   each game's `files/`, the worker's stub packages and `fn` jobs, `assets.serve`); the inspector's skill reading,
   `levelmap.landmark`, the file readers; the probes' paths.
6. **The leftover checks** (point 5 and the inventory's hidden differences table), the new `offline_check` tests
   (contract, grep rule, worker imports, jobs, reset, logging).
7. **Docs**: the inventory's list (`AGENTS.md`, `spec.md`, `bl1.md`, `notes.md`, `design.md`, `presequel.md`);
   this file goes.

## Decided

- BL2 is the base (the user): `games/bl2/`, its parts every game's default; the others import from it.
- Split by domain (the user): one part per domain (world, missions, items...), each game overriding parts - not
  one module per game, which would grow back into giant files (BL1's ~500 lines already).
- A small game stays one file (the user): as long as it's short and shares most with BL2 (TPS, AoDK today); a folder
  when it outgrows that (BL1).
- BL1's file readers move to `games/bl1/files/` (the user: BL2 doesn't need them). It needs the next point.
- File decoding is the profile's (the user: "never BL2 should even know about it"): each game's decoders in its
  `files/`, the formats shared in `formats/`, the worker and the server knowing no game ("File decoding").
- `games` imports without the SDK: the profile is picked at the mod's boot (`games.pick()` in
  `helios_tracker/__init__.py`, before anything reads `GAME`), not as `games/__init__.py` is imported. Why: the
  subinterpreter worker (`gamework.py`) imports the file-only modules as `helios_work` with no SDK; a reader in
  `games/bl1/files/` first runs `games/__init__.py` and `games/bl1/__init__.py` - today's `GAME = _current()`
  (`import mods_base`) would fail there. So: no SDK import at module level anywhere in `games/` (the parts already
  import theirs inside methods); tests still swap `games.GAME`. Also answers the audit's first question - the factory
  runs once, explicitly, at boot.

## To decide

- **TPS in BL2's code**: TPS shares BL2's files and stays one file, so its quirks are handled inline in BL2's decoders
  (`gameicons.py:8`, `gamefonts.py:373-389`, `gamescan.py:158`, `tacmap.py:33`, `gamecards.py:6, 20`) - against "no
  mention, BL2's included" as written. Suggested: the rule is about games with **their own code** (a folder: BL1);
  a game sharing BL2's code (TPS, AoDK) may be named in it as context, never branched on.
- **The page's per-game data outside `game.js`** (CSS tokens, `*.tps` labels, keyed by the game's key): keep as keyed
  data (suggested - they're data, not branches), and does the grep rule cover the page?
- **`model.js`'s class tests** (`OzPlayerJumpPad`, `WillowInteractiveNPC`): a flag on the record from Python (the
  part decides what a thing is - suggested) or a `gameData()` table?
- **Step 0 now**: the controller-keyed caches are wrong answers today (in every game) - fix them right away,
  before the rest?

- Is it worth bringing to `master`'s BL2 / TPS before BL1 is merged, so the restructure isn't tied to the experimental
  branch?
