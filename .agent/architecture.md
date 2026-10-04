# Architecture: what's wrong beyond the game profiles

Found while auditing the game handling (2026-10-03, branch `profiles` - the game profiles: `.agent/profiles.md`), but
not about games: how the mod's work is shaped, its caches, its modules. Each point: what's wrong, why it matters, the
direction - what's been built since is said where it is.

## The goal

The user: **lightweight on the collection, lightweight on the sending - responsive and cost efficient.** The mod
lives inside someone's game: every millisecond it takes is the game's frame, every byte it sends is a page's (and a
tunnel's, a phone's) work. Each point below is measured against that, and so is anything new: what it costs on the
game thread, what it costs to send, and whether a page needs it.

## 0. The stalls: the real issue today

The user: avoid hitches and frame losses; **the stalls are the real issue today**. Where they come from:

1. **Our own work, in one go, on the game thread** - the full scans (`scan objects` 38 ms in BL2, 116 ms in BL1, every
   120 s), `object records` (up to 270 ms), `players` (up to 550 ms), the `_info` rebuild burst after each scan, records
   built inside spawn hooks (sections 1, 1b).
2. **The GIL, held by our other threads.** The HTTP server (`server.TrackerServer`, a `ThreadingHTTPServer`: a thread
   per connection) runs in the game's interpreter: while one of its threads holds the GIL, every hook the game calls
   waits for it - `PostRender` each frame, each spawn hook (`PostBeginPlay`, `InitializeBalanceDefinitionState`,
   `SetUsability`...). Python hands the GIL over every 5 ms by default: each hook can wait that long, several per frame.
   When it bites: a page loading (30+ files at once - `server.py` 322), a page (re)connecting (its full snapshot built on
   a stream thread, every record's JSON), every stream's writes. `spec.md` already measured it for the file scan: "a
   plain thread of ours froze / lagged the game" - why `gamework` moved to a subinterpreter.
3. **The hub's lock**: the collector's `publish_records` waits while a stream thread builds a catch-up message under it
   (1b).

### Can collecting move to another thread?

- **The reads: no.** UObjects belong to the game thread: the engine edits and frees them during its frame, nothing
  locks them, unrealsdk promises no thread safety - a read from another thread races the garbage collector (a crash,
  or garbage). The rule stays: only the game thread touches UObjects. And a plain Python thread of ours couldn't help
  anyway: same GIL, it would only add waits (point 2).
- **Everything after the reads: yes - into a subinterpreter** (Python 3.14, its own GIL - as `gamework` already does
  for the files). The game thread reads properties into plain values and hands them over; the diffing, JSON, the hub
  and the HTTP server (static files, streams, catch-up snapshots) all run there, beside the game, never in turns with
  it. Then the game's interpreter holds nothing of ours but the hooks: no GIL contention, no lock contention.
  - The handoff is the cost to watch: `concurrent.interpreters` queues pass str / bytes / numbers / tuples cheaply,
    other objects pickled. So the game thread's output becomes compact (tuples or one encoded blob per tick) - measured
    against today's diff + JSON before choosing.
  - Fallback without subinterpreters (older Python): as `gamework` does - in process, politely (a short switch
    interval while our threads work).
- **What stays on the game thread is made small**: property reads only per tick (`util.field` / readers), function
  calls per record or pass and cached, `find_all` per level or behind a long timer and processed under a budget across
  ticks, hooks only queueing work (section 1).

### Measure the stalls themselves

The slow-task report times our tasks, not what the game feels: a frame lost to a GIL wait, or to the game's own
loading, doesn't show. First instrument: the time between `PostRender` calls (the frame time) - spikes logged with
what ran in that frame (our tasks, the server's activity: requests, streams, snapshots). It tells ours-in-task from
GIL waits from the game's own, and it's the number every change is judged by.

## 1. Work on the game thread has no shape

The mod runs on the game thread (unrealsdk: UObjects only there) - its work is the game's frame time. Today's hitches,
from `helios_tracker.log`'s slow-task reports: `scan objects` 38 ms (BL2) / 116 ms (BL1) every 120 s, `state` 10-40 ms
spikes ~3 times a second, `players` ~10 ms every 2 s, peaks of 100-550 ms. The baseline, 2026-10-03 (75 BL2 / TPS
sessions - older builds among them: rough -, 7 BL1 ones; the median of each 30 s report's worst, how often) - before
the stall work (section 0: steady play now 0-3 spikes of ours per 30 s):

| task | BL2 / TPS | BL1 |
|---|---|---|
| `missions` (every 1 s) | 6 ms, 17 of 30 s | 11 ms, 28 of 30 s |
| `mission log` (the full pass, sliced) | 5.5 ms, 4x / 30 s | 7 ms, 38x / 30 s |
| `scan objects` (every 120 s) | 38 ms | 116 ms |
| `scan pickups` (every 120 s) | 12 ms | 27 ms |
| `state` (every tick) | ~10 ms, ~3x a second | the same |
| `players` (every 2 s) | ~10 ms | ~9 ms |

What's wrong:

- **Full scans as safety nets.** Every 120 s, `find_all` over pickups and interactive objects (it walks every object
  of the game), plus waypoints, exits, discovery areas - though the spawn hooks already catch what's new. A whole
  scan in one tick.
- **Bursts after resets.** The scan resets `_info` (collector 600): the next tick rebuilds every pawn and pickup at
  once (`IsEnemy`, `GetExpLevel`, `GetShortHumanReadableName`... function calls) - likely the `state` spikes after
  each scan.
- **Work inside hooks, outside any budget.** `object_spawned` builds a record synchronously in two hooks
  (`PostBeginPlay`, `InitializeBalanceDefinitionState`) - during the game's own loading, uncounted.
- **Budgets checked between items only.** The mission pass's slices and `RECORDS_SECONDS` stop between entries: one
  slow entry (BL1's `mission_home` -> `level_name` -> a `find_all` per map name) blows the slice.
- **Per-tick function calls.** `GetShieldStrength` / `GetMaxShieldStrength` per player with a shield, every tick
  (collector 1295) - function calls are the costly part of an update (the collector's own notes).
- **No rule says what may run when.** Timers (`*_EVERY`) and budgets grew one by one; nothing states the cost classes.

Direction: one model for game-thread work, written down -

- per tick: property reads only (`util.field` / readers);
- per record / per pass: game function calls, cached on the record;
- per level, or behind a long timer: `find_all`, its results processed under a time budget across ticks;
- hooks only note what to do (a queue), the budgeted step does it;
- resets refill lazily, spread (never "everything on the next tick");
- the full scans reconsidered: rarer, sliced, or gone where the hooks are known to catch everything (a probe:
  compare a scan's finds with the hooks' over a session).

## 1b. Sending runs on the game thread, under a shared lock

The hub already sends only what changed (`server._Records`: records compared as objects, a changed record's changed
fields only, versions so a page catches up). But:

- **Diffing and JSON on the game thread.** `publish_records` - the comparison, a copy of every record, the JSON of
  the changed ones - is called by the collector itself, at the end of each state tick, for four channels (`items`,
  `pickups`, `pawninfo`, `state`): that's the log's `state.json` (up to 51 ms). Same for `missions`, `areas`,
  `level` (`json.dumps` in the collector).
- **The hub's lock is held while the page streams build their messages.** `Hub.wait` calls `since()` inside
  `with self._cond`: for a page that's new or fell behind, that's every record's JSON (a full snapshot). Meanwhile the
  collector's next `publish_records` waits for the lock - a page connecting (or a tunnel reconnecting) stalls the
  game thread.
- **The GIL.** The server's threads share the game's Python: their work (JSON, writes) is time the game thread's
  hooks can't run. Fine when the game thread is in native code, felt when it's in ours.

Direction: the game thread only **hands off** what it read (a snapshot: the records as they are - copied, since the
collector edits some in place) and returns; a sender thread diffs, encodes, and updates the hub. The hub's lock
guards the swap of a finished message, never the building of one (a page's catch-up message built outside it, from
an immutable version). And what's encoded once is sent to every page (already true for the step message).

## 1c. Collecting what nobody looks at

The collector stops when no page is open (`hub.clients`), but with one open it collects everything: the mission
log's full passes, shops, loot odds, every player's gear and skills, discovery areas - whether or not that page
shows them (a layer off, a panel closed). Direction, to weigh: the page says what it shows (its visible layers, its
open panels - a small message when it changes), the collector skips the work nobody asked for and the hub what
nobody listens to. Not everything can wait (a panel opened wants its data now: a first read on demand), and several
pages may want different things (the union) - a design question, not a fix; worth it for the costly ones (players'
cards, the mission log, shops).

## 2. Caches have no lifecycle

Dozens of caches, each deciding alone when it's stale - most never: keyed by UObject address (reused after a level
change), some holding raw UObjects across levels. Two are wrong answers today, in every game: `inspector._skills_cache`
and `_class_names` (keyed by controller / PRI address - a new controller at a reused address gets the old one's skill
tree, class name). The level reset runs late (`_check_level` polls each second, while the new level's spawn hooks
already run on the old caches).

Built (2026-10-04): the controller-keyed caches fixed (`util.PerObject`: a WeakPointer to the object), one reset
registry (`util.on_level_change` - `profiles.md` "Level changes"). Left (`profiles.md` "Still open"): the unsure
definition-keyed caches classified (a WeakPointer probe), the reset from a load hook. Beyond it, the rule
for any new cache: **its key and its lifetime are stated where it's defined** (per level - registered; static - says
why; never a raw UObject held across levels).

## 3. `try_` everywhere: failures are silent

~600 `try_(lambda: ..., default)` in the package (collector ~210, inspector ~186, missions ~60, lootodds ~42,
amounts ~39, skills ~32...). It started as protection against the game's object graph (None in a chain, an object
unloaded mid-read) - real and fine. But it's used the same way around calls that should never fail, so a broken
read becomes a default value with nothing logged: a missing property on one game read as "0" (BL1's accuracy 7 for
the game's 6.7 was this), a bug reads as "no data". It also costs: a lambda and a call frame per read, in hot loops.

Direction:

- `try_` for **runtime conditions** only (None in a chain, an object gone), said in the call's comment or by a
  narrower helper (`field`, a reader returning None).
- A failure that means a bug or a game difference is **logged once** (per site and exception type) - the profile's
  parts have it (`games._logged`, built 2026-10-03); the same helper for the rest.
- Hot loops read through `util.field` / readers, not lambdas.

## 4. Modules too big, responsibilities mixed

- `collector.py` (1816 lines): the game thread's scheduler, level changes, scans, every record kind (pawns, pickups,
  objects, players, missions markers, shops glue, domes), the hub's payloads. `inspector.py` (1193): item cards,
  players, skills, element names, explosions, plants, buffs. Each a grab bag: any change reads half the file.
  Direction: the scheduler apart from the records; one module per record kind (pawns, pickups, objects, markers),
  the collector calling them.
- *(done, 2026-10-04: `formats/`, `games/<game>/files/`, `assets.py`, `levelmap` the shared map types without the
  SDK - `profiles.md` "The game's files")* Mixed file modules (`gamefonts`, `gamecards`, `gameicons`, `tacmap`,
  `levelmap`). Left: `gamecards._movie_tags` repeats `formats/swf._movie_tags` (not quite: it yields nothing for a
  non-movie where swf's raises - merged with a flag, or kept).

## 5. Coupling through private functions and late imports

- Function-level imports (`# noqa: PLC0415` - 52 on 2026-10-03, most in the profile) - most to dodge import cycles
  between modules that call each other's privates: the profile's parts call `collector.pawn_display_name`,
  `inspector._skills`, `inspector._remapped`, `skills._action_locked` (`profiles.md` "Still open"). *(fixed,
  2026-10-04: `bl1map` importing `tacmap`'s `MapImage`, `swffont` - a format - importing `gamefonts` - a decoder.)*
- A private function used from another module is a missing public one, or a misplaced one. Direction: dependencies
  point one way (formats <- decoders <- parts / records <- the collector / server), a function used across modules is
  public in the module that owns it, and a cycle is a sign something lives in the wrong place - not a reason for a
  late import.

## 6. Stand-ins and hidden calls

- `_NotPickedUp` imitates a game log entry (its field names, `Status`, `bHeardKickoff`), and its property calls a game
  function behind the reader's back (its calls cached since). The general rule: code returns its own records, never
  objects shaped like the game's; a property never hides a call (`profiles.md` "The rules", "Still open").

## 7. Tests: one giant function, and the gaps

- `offline_check.py`'s `check_helios_tracker()` is one very long function (2875-line file): every block shares its
  scope - names reused far below broke asserts twice (`AGENTS.md` already warns). Direction: test blocks as functions
  (their own scope), the shared setup (fakes, the imported mod) passed in.
- It patches instance methods (`GAME.mission_entries = lambda`, `GAME.map_name`) - tests built on implementation
  details; the parts give them seams.
- Untested in `offline_check`: the worker importing from a `.sdkmod` (zipimport in the subinterpreter - checked by
  hand, 2026-10-04: its subpackages stubbed, a BL2 texture job from the zip), AoDK beyond its Gibbed prefix. Tested
  since: the profiles' contract (`check_parts_contract`), the shared code naming no other game (`check_shared_names`),
  `games` importing without the SDK (`check_games_import`).
- *(fixed, 2026-10-04)* `check_navwalk.py` and the probes loading modules by file path (`formats/`).

## 8. Small ones

- `supported_games` (`pyproject.toml`) leaves out `"AoDK"`, which has a profile and a test.
- `inspector.py:852`: a `find_all("WillowDamageTypeDefinition")` only to get an enum type (`find_class` does it);
  `inspector.py:315`: `find_all("WeaponTypeDefinition")` once per session - a DLC loaded later is missed.
- `_out_of_sight` (~50-100 us per object, every scan - its reads made cheaper 2026-10-04) - only for definitions that
  can hide, a hook on the visibility change if one exists (a probe): a hide after a scan shows only at the next one.
- From the profiles' audit, game-thread costs left: `GetShieldStrength` + `GetMaxShieldStrength` per player with a
  shield every tick (against the rule: no game function per tick); `collector.level_name`'s `find_all
  ("LevelDependencyList")` per new map name (the lists are static: found once); the 120 s scan resetting `_info` (the
  next tick rebuilds every pawn and pickup at once - the `state` spikes after a scan?); `object_spawned` building a
  record in two hooks, outside the records' budget; BL1's `_mission_definitions` `find_all` again on every call while
  its result is empty.

## 9. The mod folder: code and what it writes, mixed (the user, 2026-10-04) - the data part done

*(done, 2026-10-04: DATA is `sdk_mods/.helios_tracker/` for both installs - the user: "we shouldn't have two methods
based on if it's sdkmod or a folder". The files a folder install left in the package stay there, gitignored, until
moved by hand.)*

A folder install's DATA is the package itself (paths.py): its modules sit next to the logs (`helios_tracker_<game>.log`,
`helios_crash_<game>.log`, the old unsuffixed ones), the user's `autoexec.ps1`, `.cache/`, a `diagnostics` file - "not a
big fan" (the user). To do now the profiles' moves are done:
- what the mod writes in a folder of its own, the .sdkmod's way (`sdk_mods/.helios_tracker/`: already apart) - e.g.
  DATA = `<package>/.data/` or the same `sdk_mods/.helios_tracker/` for both installs (the dev's logs then outside the
  repo: the tools reading them follow paths.DATA); the old files moved once (or left: gitignored);
- maybe the package's ~20 top modules grouped too (collecting, the page's server, the mod's shell: settings, updater,
  script) - the same kind of split as games/ and formats/; its own decision.

## Known, accepted for now (2026-10-04)

- **A freeze when the mod loads into a level**: the first level check (`level`) ~870 ms, once - BL2, twice measured
  (`helios_tracker_bl2.log`). The user: acceptable for now. Its parts not broken down yet (the level message: language,
  level name, rarity table, the map's source...).
- **The first players pass of a level / page** (~115 ms in BL2: the skill tree's first read 92 ms - the cards are
  spread, the tree isn't) and **the 120 s object scan** (~36 ms: `_out_of_sight` 18) - one-offs, measured
  2026-10-04 after the stall work; steady play: 0-3 spikes of ours per 30 s.

## Order

The stalls lead (the user):

1. **See them**: the frame-time instrument (section 0) - the number every change is judged by.
2. *(done, 2026-10-04)* **The correctness bugs** (the controller-keyed caches): wrong answers, small fixes.
3. **The cheap game-thread wins** (sections 0, 1): the scans sliced or rarer, the `_info` burst spread, hooks only
   queueing, the per-tick function calls gone, BL1's per-pass costs (mostly done 2026-10-04: section 8's list left).
4. **The server and the sending into a subinterpreter** (sections 0, 1b): no more GIL or lock contention with the game.
5. **Collecting only what's looked at** (1c), designed with the page.
6. **The rest** (the game profiles done: the failure logging, the file modules split); the collector / inspector
   split last (the largest churn, the least risk to put off).
