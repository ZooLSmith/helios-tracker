# Helios Tracker (Borderlands 2 mod)

This repo holds **Helios Tracker**, a live web map mod for Borderlands 2, built with the
[Python SDK](https://bl-sdk.github.io/developing/) (unrealsdk / pyunrealsdk + `mods_base` mod manager).
The mod itself is the `helios_tracker/` package: read `helios_tracker/CLAUDE.md` (the spec) and
`helios_tracker/.claude/documentation/notes.md` when working on it. See
`.claude/documentation/references.md` for the game install path, installed SDK version, APIs and
useful links.

It is **standalone**. The HUD widget mods (`ammo_counter`, `skill_timer`, `xp_counter`) and their shared
library `z_hud_overlay` live in their own repo (`E:\Projects\python\borderlands-2`). Helios Tracker
draws nothing in game and must not use `z_hud_overlay`.

## Layout

```
bl2-helios-tracker/
├── CLAUDE.md
├── .claude/documentation/references.md   # paths, SDK facts, API notes
├── tools/                                # offline_check.py + in-game probes (probe_*.py)
└── helios_tracker/                       # the mod (Python package + web/ page)
    ├── CLAUDE.md                         # mod spec
    ├── .claude/documentation/notes.md    # findings about the game's objects
    ├── __init__.py                       # builds + registers the mod (build_mod)
    └── pyproject.toml                    # mod metadata (name, version, authors, description)
```

## Checking & reloading

- `python tools/offline_check.py` — imports the mod with fake SDK modules, runs its collectors,
  extracts real tactical maps from the game's packages, serves the page and runs its JS under Node.
  Run after every change; it's the only test we have outside the game.
- In game: `pyexec helios_tracker/reload.py`. Page edits only need a browser refresh.
- Probes: `py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_<name>.py").read())`,
  output to `tools/probe_<name>.txt`.
- Dev outputs (probe dumps, logs, screenshots) are gitignored — keep it that way; extracted game
  files must never be committed.

## Conventions

- Target the **current SDK (v3.x, Python 3.14)**, i.e. `mods_base` / `unrealsdk` APIs.
  Do **not** write legacy-style mods (`from ..ModMenu import SDKMod`, `unrealsdk.RegisterHook`) —
  those only run via `legacy_compat`.
- Use `mods_base`: `build_mod()`, `@hook(...)`, `*Option` classes for configurability, `@keybind`.
- Developed here, **not** inside the game folder. The package is linked into the game's `sdk_mods`
  with a directory junction (no admin needed), so edits here are live in-game:
  `New-Item -ItemType Junction -Path "<game>\sdk_mods\helios_tracker" -Target "E:\Projects\python\bl2-helios-tracker\helios_tracker"`
- Release format: `.sdkmod` = a renamed zip containing `helios_tracker/...`.
- Never scan the whole drive; scope searches to this project or the game folder.
- Edit scripts containing backslash escapes must be written to a file first (the Bash tool eats
  `\\` even in quoted heredocs, which once wrote NUL bytes into a source file).
