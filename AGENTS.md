# Helios Tracker (Borderlands 2 mod)

This repo holds **Helios Tracker**, a live web map mod for Borderlands 2, built with the
[Python SDK](https://bl-sdk.github.io/developing/) (unrealsdk / pyunrealsdk + `mods_base` mod manager).
The mod itself is the `helios_tracker/` package: read `.agent/spec.md` (the spec) and
`.agent/notes.md` when working on it
(`.agent/design.md`: design wishes not built yet, and why). See
`.agent/references.md` for the game's layout, installed SDK version, APIs and
useful links. The Pre-Sequel: `.agent/presequel.md`.

Machine paths live in `project.json` (repo root, gitignored; from `project.example.json`): never
hard-code one. What needs a path names its key; `<game>` in the docs is `game.path`, `<repo>` this
repo's root.

Helios Tracker draws nothing in game: everything it shows is on the page. The one exception, the user's call: the
updater speaks through the game's own UI (its dialog box, its bottom-left message - `ui_utils`), never drawn by us.

## Layout

```
bl2-helios-tracker/
├── AGENTS.md                             # this file (CLAUDE.md: a pointer to it, for Claude Code)
├── README.md, LICENSE                    # the public repo's front page; GPL-3.0
├── .github/workflows/nexus.yml           # each GitHub release uploaded to Nexus Mods
├── project.example.json                  # template of project.json: this machine's paths
├── .agent/                               # everything for agents / devs (never in the mod folder):
│   ├── spec.md                           #   the mod's spec
│   ├── notes.md                          #   findings about the game's objects
│   ├── design.md                         #   design wishes not built yet, and why
│   ├── references.md                     #   game layout, SDK facts, API notes
│   └── presequel.md                      #   the mod in the Pre-Sequel: what works, what was seen
├── tools/                                # offline_check.py, project.py (reads project.json),
│   │                                     # link_mod.py, build_sdkmod.py + use_sdkmod / use_dev.bat,
│   │                                     # release.py, fake_release.py (the updater's test server)
│   └── probes/                           #   in-game probes (probe_*.py, their .txt) + offline research
│                                         #   tools (check_navwalk, dump_tacmap_movie, find_fonts...)
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
- As players run it: `tools/use_sdkmod.bat` builds `_work/dist/helios_tracker.sdkmod` (`tools/build_sdkmod.py`) and
  puts it in `sdk_mods`, the junction parked as `.helios_tracker_dev` (a folder beats a `.sdkmod`; dot names are skipped);
  `tools/use_dev.bat` goes back to the junction. Restart the game after either - or, the game running, reload: the
  `.sdkmod` has no `reload.py`, so `pyexec .helios_tracker_dev/reload.py`.
- Updater: `python tools/fake_release.py` - a local stand-in for GitHub's releases (the working tree, version + 1);
  then the mod's options: Check for Updates -> the dialog. Only from a `.sdkmod`: the junction never updates.
- Probes: `py exec(open(r"<repo>\tools\probes\probe_<name>.py").read())`, output to
  `tools/probes/probe_<name>.txt` (found through the mod's junction: `sys.modules["helios_tracker"]`'s real path).
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
  That fallback is the thing's **own** object name, as is: no heuristics to make a nicer one (walking to an
  owner object, stripping prefixes / suffixes picked to fit the cases at hand - the user: "don't make stuff up, no
  hacks no guessing"; a nameless level-up effect first came out "Level Up Naturally ?" that way).
- **US English** in everything players read (the page's `en.js`, the mod's English in `i18n.py`, the README, the
  site's `en.js` and heads): color, centered, gray, favorite... - not colour, centred. (The `{n} %` spacing is
  on purpose: font issues.)
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
- **Settings go in the group of what they change** (the Settings tab's headings): **Who** = about the tracked player
  (Follow, Rotate to their heading), **Map** = how the map is drawn (colours, opacity, markers, 3D view, coordinates),
  **Panels** = the interface. A new option next to the last one added is the trap (the 3D view first landed under Who,
  by Rotate - the user caught it, and not the first time).
- **offline_check: unique names**: `check_helios_tracker()` is one very long function; a new test
  block's variables share its scope - reusing a name (`later`, `gun`) broke asserts far below twice.
  Use specific names (`card_gun`, `later_shot`) and grep before introducing one.
- Release format: `.sdkmod` = a renamed zip containing `helios_tracker/...`, without the dev files
  (`reload.py`, `.cache/`, logs). Agent / dev docs live at the root, never inside `helios_tracker/`.
- Releasing (the user runs it - publishing, like pushing, is theirs): bump `helios_tracker/pyproject.toml`'s
  version, commit, push `master` (both remotes), then `python tools/release.py` (checks, builds, verifies; says what
  it would publish) and
  `--publish [--notes "..."]`: a GitHub release of the public repo, tag `vX.Y.Z` = the version, the `.sdkmod`
  attached - what the mod's updater reads. Agents run it without `--publish` only. Each published release also
  goes to Nexus Mods (`.github/workflows/nexus.yml`, the official upload action: the `.sdkmod` zipped, a new
  version of the mod's file - its secret / variables in the public repo's settings, see the workflow's header).
- Never scan the whole drive; scope searches to this project or the game folder.
- Edit scripts containing backslash escapes must be written to a file first: shell heredocs (even
  quoted ones, through some agent shells) can turn `\\` into `\`, which once wrote NUL bytes into a
  source file.
- **Line endings: keep each file's own.** The repo mixes CRLF and LF files and git converts nothing (`core.autocrlf`
  false): an edit script's Python `read_text` / `write_text` turns a file into CRLF on Windows (text mode) - whole
  files then show as rewritten in the diff (it happened to 8 files once). Scripts edit bytes (`read_bytes` /
  `write_bytes`) or open with `newline=""`; check `git diff --stat` for a file suddenly "all changed" before committing.
- Solo repo: commit straight to `master`, no branches - and only when asked. One exception: the website.
- **Never push** (any remote, any branch): the user pushes.

## Repositories

- The code is open source (GPL-3.0, `LICENSE`), its whole history public.
- `public` = `ZooLSmith/helios-tracker` (public): `master` = the code (the same history as `origin`'s), the site (the
  `documentation` branch), the releases (`tools/release.py`: the `.sdkmod` attached).
- `origin` = `ZooLSmith/helios-tracker-private` (private): the same `master`, and whatever isn't public yet (an
  experimental branch). Locally `remote.public.push` sends `master` and `documentation` only, and `.git/hooks/pre-push`
  refuses any other branch to the public repo (a fresh clone has neither: set them up again).

## Website (GitHub Pages)

- The `documentation` branch is the site, served by GitHub Pages from its root at `https://helios-tracker.zoolsmith.com/` (its `CNAME`
  file; the domain's DNS: a CNAME record to `zoolsmith.github.io`). It's an orphan branch
  (no history shared with `master`), checked out as a worktree at `_work/web_documentation`
  (`git worktree add _work/web_documentation documentation`; `_work/` is gitignored).
- Handwritten HTML / CSS, no build: one set of pages at the root (`index.html`, `install.html`...), `assets/` the
  shared CSS / JS / fonts / images. Translated the tracker page's way: the pages hold structure only, each text a
  key (`data-i18n="install.sdk"`, `data-i18n-label` / `-title` / `-placeholder` / `-content` for attributes), the
  words in `assets/i18n/en.js` (every key; values are HTML) and the others (same keys), filled by `assets/js/i18n.js`.
  The language: the visitor's pick in localStorage (`helios.site.lang`, "auto" = the browser's), switched in place.
  The same nine languages as the page. A new language = a catalog + its line in `assets/i18n/index.js` (a new
  script: its fonts in `site.css` - Exo 2's subset, or a `:lang()` stack of system fonts like the CJK ones); a new
  page = its file + its line in `site.js`'s
  `PAGES` (the bar's links and the search are built from it) + its line in `sitemap.xml` + its keys. No menu to open: the pages
  are a few words each in the top bar, a row of their own on small screens. An empty translation hides its element (a note
  only one language needs). Old `/en/...`, `/fr/...` links: `404.html` redirects them.
- Search keywords, never shown: a heading's `data-search="kw.xxx"` names a catalog key (words, commas), matched like
  the heading. The language's and the English ones both count, so a `kw.*` key missing from a catalog is fine (the
  one exception to "same keys").
- Every page needs JavaScript (no text without it): what the site builds (the pages' links, search, copy buttons) carries keys
  too, so a language switch re-translates it; anything built from the text listens to the `i18n` event.
- Link previews (Discord, X...): each page's head has Open Graph tags and its `<title>` / description in English,
  written out (the bots run no JavaScript; the script still swaps them for the visitor's language) - a page's title
  or description changed in `en.js`: change them there too. The image: `assets/img/og.jpg` (1200 x 630).
- Search engines: each page's head has its canonical address (`<link rel="canonical">`, the one without `.html`), the
  home's a WebSite JSON-LD (the site's name in results); `sitemap.xml` lists the pages, `robots.txt` points to it
  (and keeps `/live/` out). The icons: `favicon.png` (64) and `favicon-192.png` (Google wants a multiple of 48 px).
- Links without `.html` (`install`, `share?path=home`, the home `./`): GitHub Pages serves `/install` as
  `install.html`. Preview: `python tools/site_preview.py` (does the same; `python -m http.server` doesn't).
- The home page (`body.home`): the bar as on every page (its logo too: one that comes and goes jars), its hero one action (Install, GitHub beside it);
  the other pages are the bar's links, and the questionnaire linked from "Where to view it".
- Wording follows the page's own labels (`helios_tracker/web/i18n/<code>.js`, the same language's); the mod's
  in-game options by their names in the game's language (`helios_tracker/i18n.py`, the same language's).
- Nothing extracted from the game goes on the site (fonts, map images, icons): it's public. One exception, the
  user's call: screenshots of the mod running (the overview's previews, `assets/img/previews/`) - pictures of it in
  use, like any mod page's, not the game's files.
- Keep what's learned in the repo (these files, `.agent/`), not in an agent's private memory, so every
  agent and person sees it.
