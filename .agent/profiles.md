# Game profiles: how the mod handles each game

The mod runs in Borderlands 2, the Pre-Sequel, Tiny Tina's Assault on Dragon Keep and Borderlands 1. What differs
between them lives in one place - a **profile** per game, picked once at the mod's boot - and nowhere else (built
2026-10-03/04 on the `profiles` branch: tag `pre-profiles` is the commit before; its history, step by step, in git).
On the page: `web/js/game.js`. `AGENTS.md` has the rule in short; this is the why and the how.

## The layout

```
helios_tracker/
├── games/                    # the profiles - nothing else in the mod names a game
│   ├── __init__.py           #   GAME (pick(): the mod's boot), make_profile, the registry, the features; no SDK import
│   ├── base.py               #   Part, Profile: a profile is its data + one part per domain
│   ├── bl2/                  #   Borderlands 2: THE BASE - its parts are every game's default, their docstrings the
│   │   ├── __init__.py       #     contract; its data (key, packages, exe_depth, gibbed_prefix, features...)
│   │   ├── world.py ...      #     world, missions, items, objects, pawns, shops, skills, assets, ui
│   │   └── files/            #     its decoders: tacmap, gamescan, gamecards, gameicons, gamefonts (its font libraries)
│   ├── tps.py                #   the Pre-Sequel: BL2's + its data, its few methods (exits' names, skill icons, oxygen objects)
│   ├── aodk.py               #   Dragon Keep: BL2's + its data
│   └── bl1/                  #   Borderlands 1: BL2's parts, its own where its way differs (one file per part)
│       └── files/            #     its decoders: bl1map (vector map, menu / card icons), bl1fonts, bl1textures, upk_bl1
├── formats/                  # the file formats, no game: upk, swf, swfshape, swffont, fonts, image, engine
├── assets.py                 # what every game's assets fill: the fonts' catalogue, the item card icons' keys
├── levelmap.py               # the map types every game's map source returns (MapSource, MapResult, MapImage, MapFog)
├── gamework.py               # the worker (a subinterpreter): runs a job naming its *_job function - knows no job, no game
└── collector.py, inspector.py, missions.py, server.py ...   # the main code: calls games.GAME.<part>.<method>()
```

A game close to BL2 stays one file (data and a few small overrides); a game whose way differs a lot gets a folder, one
file per part it overrides (the user: split by domain, not one module per game - else giant files again).

## The rules

**The main code doesn't know other ways exist** (the user: "BL2 / the main code shouldn't even know that BL1 has a
different way of doing it" - it calls one function and that resolves to the game's own). In the main code - everything
outside a game's own folder, BL2's parts included:

- **No branch, no mention.** No `if` on a game, no comment naming another game's way: the why of a game's way (its
  probe, what was seen) is written in its override. Evidence stays (a probe file's name, a measurement). A game sharing
  BL2's code (the Pre-Sequel, Dragon Keep) may be named as context, never branched on. `offline_check`
  `check_shared_names` greps for Borderlands 1 and its modules.
- **One way in per job.** The main code names the job (`games.GAME.world.map_source(wi, name)`, `objects.exit(io)`,
  `assets.serve(path)`), never which version; a part's docstring says what it returns, not who overrides it.
- **Dependencies point one way.** A game's folder imports BL2's parts and the shared modules; nothing imports from it
  (`games/__init__.py` registers the profiles: the one place naming them).

**BL2's parts are the interfaces** (interface segregation, dependency inversion, substitution - "the idea, not the
ceremony"): plain classes, the other games subclass them. Every game's part has BL2's public methods with the same
parameters and none of its own (`offline_check` `check_parts_contract`): a helper only one game needs is private.
Plain data stays on the profile (`GAME.key`, `GAME.features`, `GAME.packages`...).

**Features say *what* a game has, never *how*.** A feature is a system a game has or lacks (`games.DISCOVERY`,
`OXYGEN`, `JUMPPADS` - the page reads the same names: a layer's `needs`); the work for a missing one is skipped. Two
ways of doing a job is a method, never a feature: **if the `else` does something, it's a method.** No nested feature
tests (a method is missing), no two features for one choice.

**Runtime conditions** (a co-op client, a menu open, our own pawn without player info) are tested where they happen,
inside the part or the main code - not a game difference.

**No hacks**: no `hasattr` / `try_` / `getattr(x, ..., default)` to guess which game it is; no stand-in object
imitating a game's (its fields, a property calling a game function); no `isinstance` on a profile, no game key tested
in Python.

**Failures are seen, not swallowed.** `make_profile` wraps each part's public methods: the first failure of each
exception type is logged (`games.<Part>.<method>: ...` with its traceback), then raised - the callers keep their
defaults (`try_(lambda: games.GAME.x(...), default)`). A property a game lacks no longer reads silently as the default.

**`games` imports without the SDK**: the profile is picked by `games.pick()` at the mod's boot (`__init__.py`, before
anything reads `GAME`); every module reads `games.GAME` at call time (tests swap it). The parts import the SDK inside
their methods.

## Adding a difference, a game

- **A game does a job another way**: the job's method in BL2's part (if the main code still does it inline, move it
  there first - its docstring the contract), the game's override in its part, the main code calling the part. The
  override says what showed the difference (a probe, a log).
- **A system only some games have**: a feature if the page shows or hides something for it; the work in the game's
  part (BL2's base method doing nothing - `objects.extra_fields`, `dome`).
- **A new game**: its profile under mods_base's name for it (`@profile("NAME")`), a file (data, a few overrides) or a
  folder (its parts, its `files/`); `.agent/<game>.md` for what was seen; on the page, its `gameData()` and the layers
  it lacks (`noLayers`) - a game lacking a system needs both Python's features and the page's list looked at.

## The game's files

Three layers: **formats** (no game: UE3 packages, Scaleform movies and shapes, fonts, images); each **game's decoders**
(`games/<game>/files/`, on the formats); the **profile's parts** deciding when and what (`assets.job(boot)`: BL2's files
scan when a page connects, BL1's font library at boot; `world.map_source`; `assets.serve(path)`).

- **The worker runs any job, knowing none.** A job names its function - a `*_job` of a file-only module, built in code
  with `gamework.fn(texture_job)` ("games.bl2.files.gameicons:texture_job"), never from what a page asks (a URL only
  fills arguments); the worker imports it (as `helios_work.<module>`, the subpackages stubbed so no package `__init__`
  runs there - checked from a `.sdkmod` by hand) and calls it. A function not ending in `_job` is refused. Results are
  cached on disk, keyed by the job and its files' stamps.
- **The server knows no game's images**: `/font/` from `assets.FONTS` (each game's catalogue), the rest from
  `games.GAME.assets.serve(path)` (BL2: skill icons, card icons, textures by path; BL1: its menu icons, card icons,
  textures by path), after `assets.wait_for(path)`.
- **Files only** in `formats/` and `files/`: no SDK at module level (the worker has none), `GAME` never read there
  (a job carries its paths).

## Level changes

Nothing works out by itself that the level changed: a cache kept per level registers its reset where it's defined
(`util.on_level_change(reset)`), the collector's level change runs them all (`util.level_changed`); a part's per-level
state is cleared by its `level_changed()` (the profile's, registered in `games/__init__`). Each cache is **per level**
(keyed by level objects' addresses - registered) or **static** (game data - says why, kept); unsure: cleared (a refill
costs less than a wrong answer). `util.PerObject` keeps values with a WeakPointer to their object (a reused address
misses instead of answering for another).

## Performance

The structure costs nothing that shows (one attribute lookup more per call; the logging wrapper ~0.1 us). What costs is
the game's functions and `find_all` (it walks every object): a part's docstring says which it does - property reads
(per tick fine), a game function call (per record / per pass, never per tick), a `find_all` (once per level, kept) - and
never hides a call behind a read. Measured, not guessed: the debug slow-task report and frame times
(`architecture.md` 0).

## Still open

- **The reset comes late**: the level check polls each second while a new level's spawn hooks already run on the old
  caches - a load hook to find (a probe), or the hooks checking the level. And the definition-keyed caches never
  cleared ("static": `_explosions`, `_buffs`, `_plants`, `collector._loot_info`, `lootodds._containers` / `_inits`,
  `missions._defs` / `_stations` / `_rewards`, `skills._defs`...) - fine while their definitions stay loaded, unverified
  (UE3 cooking copies objects into maps' packages, keeping their path): a WeakPointer probe after a level change and a
  save-quit-continue. Raw UObjects held across levels (BL1's `_missions`, `inspector._accuracy_pres` / `_damage_pres`)
  -> WeakPointers.
- **BL1's `_NotPickedUp`**: a stand-in imitating a log entry (`Status`, `bHeardKickoff` calling the eligibility, cached)
  - against "no stand-ins": the missions part returning its own records instead.
- **Parts calling back into the main modules** (`pawns.name` -> `collector`, `skills.read` -> `inspector._skills`,
  BL1's `missions.home` -> `collector.level_name`, `items.card_line_value` -> `inspector._remapped`): each a helper of
  no game (accepted) or moved into BL2's part - per case.
- **Data on the profile that's a domain's**: `vending_class` / `vending_titles` (shops), `ui_stat_kinds` /
  `gibbed_prefix` (items), `damage_presentation` (items - and a method: its `None` branch rounds).
- **The page's per-game data** outside `game.js` (CSS tokens `:root[data-game="bl1"]`, `*.tps` label keys - keyed
  data, not branches: kept?) and `model.js`'s class tests (`OzPlayerJumpPad`, `WillowInteractiveNPC`: a flag on the
  record from Python, the part deciding what a thing is?) - to decide.
- **`supported_games`** (`pyproject.toml`) leaves out `"AoDK"`, which has a profile.
- **Towards `master`**: the restructure brought to BL2 / TPS before BL1 is merged, so it isn't tied to the experimental
  branch? To decide.
