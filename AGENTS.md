# Helios Tracker (Borderlands 2 mod)

This repo holds **Helios Tracker**, a live web map mod for Borderlands 2, built with the
[Python SDK](https://bl-sdk.github.io/developing/) (unrealsdk / pyunrealsdk + `mods_base` mod manager).
The mod itself is the `helios_tracker/` package: read `.agent/spec.md` (the spec) and
`.agent/notes.md` when working on it
(`.agent/design.md`: design wishes not built yet, and why). See
`.agent/references.md` for the game's layout, installed SDK version, APIs and
useful links.

Machine paths live in `project.json` (repo root, gitignored; from `project.example.json`): never
hard-code one. What needs a path names its key; `<game>` in the docs is `game.path`, `<repo>` this
repo's root.

Helios Tracker draws nothing in game: everything it shows is on the page.

## Layout

```
bl2-helios-tracker/
├── AGENTS.md                             # this file (CLAUDE.md: a pointer to it, for Claude Code)
├── project.example.json                  # template of project.json: this machine's paths
├── .agent/                               # everything for agents / devs (never in the mod folder):
│   ├── spec.md                           #   the mod's spec
│   ├── notes.md                          #   findings about the game's objects
│   ├── design.md                         #   design wishes not built yet, and why
│   └── references.md                     #   game layout, SDK facts, API notes
├── tools/                                # offline_check.py, project.py (reads project.json),
│                                         # link_mod.py + in-game probes (probe_*.py)
└── helios_tracker/                       # the mod (Python package + web/ page)
    ├── __init__.py                       # builds + registers the mod (build_mod)
    └── pyproject.toml                    # mod metadata (name, version, authors, description)
```

## Checking & reloading

- `python tools/offline_check.py` — imports the mod with fake SDK modules, runs its collectors,
  extracts real tactical maps from the game's packages, serves the page and runs its JS under Node.
  Run after every change; it's the only test we have outside the game. Without `project.json`'s game
  it skips the game file checks.
- In game: `pyexec helios_tracker/reload.py`. Page edits only need a browser refresh.
- Probes: `py exec(open(r"<repo>\tools\probe_<name>.py").read())`, output to
  `tools/probe_<name>.txt` (found through the mod's junction: `sys.modules["helios_tracker"]`'s real path).
- Offline tools that read game files take the game from `project.json` via `tools/project.py`
  (`project.cooked_dir()`, `project.path("references.gibbed")`, `project.require(...)`).
- Dev outputs (probe dumps, logs, screenshots) are gitignored — keep it that way; extracted game
  files must never be committed.

## Conventions

- Target the **current SDK (v3.x, Python 3.14)**, i.e. `mods_base` / `unrealsdk` APIs.
  Do **not** write legacy-style mods (`from ..ModMenu import SDKMod`, `unrealsdk.RegisterHook`) —
  those only run via `legacy_compat`.
- Use `mods_base`: `build_mod()`, `@hook(...)`, `*Option` classes for configurability, `@keybind`.
- Developed here, **not** inside the game folder. The package is linked into the game's `sdk_mods`
  with a directory junction (no admin needed), so edits here are live in-game:
  `python tools/link_mod.py` (or
  `New-Item -ItemType Junction -Path "<game>\sdk_mods\helios_tracker" -Target "<repo>\helios_tracker"`)
- **Game text only**: names shown for game things (objects, enemies, items, parts...) come from the game
  (its localized properties / functions, in the game's language) or we don't have them - then the
  technical name prettified and marked as a guess ("Fire Barrel ?"). No glossaries / mapping tables of
  object names. The page's own UI labels are ours to translate.
- **Game enums by name**: unrealsdk's enums are int-based, `str(value)` is the number ("0"), not
  "DMGSURFACE_Generic" - a string test silently never matches. Compare through `getattr(v, "name", v)`
  (inspector.py `_enum_name`); in offline_check fake them with `enum.IntEnum`, not strings.
- **Probes: no blind calls**: never call game functions picked by a name pattern ("every Get* without
  parameters" crashed the game: some native getters assume a context, a card being built, a menu open).
  Read properties and list signatures; call a specific function only once it's known. Write the output
  file after each section, so a crash still leaves what came before.
- **Dev overlays**: anything drawn on the canvas from `PostRender` renders in front of the console (a
  console-state check doesn't help): give it an auto-timeout (~15 s) and a short, blind-typeable off
  command (`pyexec <mod>/off.py`), said before it runs.
- **Page refreshes follow the Refresh rate setting** (Settings, `view.motion`: Updates only / N fps / Smooth - it's
  there to keep the GPU and Windows' compositor quiet next to the game): anything on the page that changes by itself
  (a countdown, a live value, an animation step) is updated from the frames - a `refresh...(now)` called at the end
  of `draw.js`'s frame (like `refreshPlayerInfo`, `refreshShops`), throttled inside (e.g. 250 ms), writing the
  DOM only when the text changed. Never its own `setInterval` / `setTimeout` loop: that runs at its own rate whatever
  the setting says (the shops' countdown first did - the user caught it). `offline_check` fails on any timer that
  isn't in its short allowlist (the frame scheduler, the settings save, the reconnect retry, the cutscene clock: the
  one exception - no game updates reach the page while a video plays, so frames would freeze it); a new one needs a
  reason there.
- **offline_check: unique names**: `check_helios_tracker()` is one very long function; a new test
  block's variables share its scope - reusing a name (`later`, `gun`) broke asserts far below twice.
  Use specific names (`card_gun`, `later_shot`) and grep before introducing one.
- Release format: `.sdkmod` = a renamed zip containing `helios_tracker/...`, without the dev files
  (`reload.py`, `.cache/`, logs). Agent / dev docs live at the root, never inside `helios_tracker/`.
- Never scan the whole drive; scope searches to this project or the game folder.
- Edit scripts containing backslash escapes must be written to a file first: shell heredocs (even
  quoted ones, through some agent shells) can turn `\\` into `\`, which once wrote NUL bytes into a
  source file.
- **Line endings: keep each file's own.** The repo mixes CRLF and LF files and git converts nothing (`core.autocrlf`
  false): an edit script's Python `read_text` / `write_text` turns a file into CRLF on Windows (text mode) - whole
  files then show as rewritten in the diff (it happened to 8 files once). Scripts edit bytes (`read_bytes` /
  `write_bytes`) or open with `newline=""`; check `git diff --stat` for a file suddenly "all changed" before committing.
- Solo repo: commit straight to `master`, no branches - and only when asked. One exception: the website.

## Repositories

- `origin` = `ZooLSmith/helios-tracker-private` (private): the code, `master`.
- `public` = `ZooLSmith/helios-tracker` (public): the site, the `documentation` branch - **never the code** - and a
  `master` holding only a "not published yet" README (the local orphan branch `public-master`, no shared history).
  Locally `remote.public.push` sends only `documentation`, and `.git/hooks/pre-push` refuses anything else to it but
  `public-master` -> `master` (a fresh clone has neither: set them up again).

## Website (GitHub Pages)

- The `documentation` branch is the site, served by GitHub Pages from its root at `https://helios-tracker.zoolsmith.com/` (its `CNAME`
  file; the domain's DNS: a CNAME record to `zoolsmith.github.io`). It's an orphan branch
  (no history shared with `master`), checked out as a worktree at `_work/web_documentation`
  (`git worktree add _work/web_documentation documentation`; `_work/` is gitignored).
- Handwritten HTML / CSS, no build: one folder per language (`en/`, `fr/`...) with the same file names,
  `assets/` the shared CSS / JS / fonts / images. The languages are listed once, in
  `assets/js/languages.js` (name + the site's UI words): the header's language dropdown and the site
  root's choice / redirect are built from it. A new language = its folder + an entry there (+ its
  `<link rel="alternate" hreflang>` in the pages' heads). Everything dynamic runs in the browser: the
  search reads the pages the navigation lists, so a new page goes in every page's `<nav class="side">`.
- Preview: `python -m http.server` in the worktree (search needs http, not `file://`).
- Wording follows the page's own labels (`helios_tracker/web/i18n/en.js`, `fr.js`); the mod's in-game
  options are English in both languages.
- Nothing extracted from the game goes on the site (fonts, map images, icons): it's public.
- Keep what's learned in the repo (these files, `.agent/`), not in an agent's private memory, so every
  agent and person sees it.
