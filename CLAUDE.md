# Borderlands 2 Addons

This folder is a workspace for making **Borderlands 2 mods (addons)** with the
[Python SDK](https://bl-sdk.github.io/developing/) (unrealsdk / pyunrealsdk + `mods_base` mod manager).

Each subfolder is one mod (a Python package). See `.claude/documentation/references.md` for the
game install path, installed SDK version, APIs and useful links.

## Layout

```
borderlands-2/
├── CLAUDE.md
├── .claude/documentation/references.md   # paths, SDK facts, API notes
├── tools/                                # dev scripts (offline_check.py, reload_all.py, probes)
├── z_hud_overlay/                        # shared library mod for the HUD mods (see its CLAUDE.md)
└── <mod_name>/                           # one Python package per mod
    ├── CLAUDE.md                         # mod-specific instructions/spec
    ├── .claude/documentation/            # mod-specific notes
    ├── __init__.py                       # builds + registers the mod (build_mod)
    └── pyproject.toml                    # mod metadata (name, version, authors, description)
```

Each mod subfolder has its **own `CLAUDE.md` and `.claude/`** with mod-specific instructions and docs.
Read them when working on that mod. Keep this root file generic.

## Shared code

Shared code lives in **hidden library packages**: plain packages in `sdk_mods` that our mods import
(`from z_hud_overlay import ...`), installed separately by users. They deliberately **don't call
`build_mod`**, so they don't clutter the mods menu; any hooks they need use
`@hook(..., immediately_enable=True)`. No dist / build step and no copies. Current library: `z_hud_overlay` (Scaleform HUD overlay, menu
tracking, visibility, anchors, shared option groups) — used by `ammo_counter`, `skill_timer`,
`xp_counter`. `helios_tracker` (live web map) is standalone and must not use it: it draws nothing
in game.

## Checking & reloading

- `python tools/offline_check.py` — imports the library + mods with fake SDK modules, runs their
  draw paths and validates generated movies. Run after every change; it's the only test we have
  outside the game.
- In game: `pyexec <mod>/reload.py` (one mod) or
  `py exec(open(r"E:\Projects\python\borderlands-2\tools\reload_all.py").read())` (library + mods).
- `python tools/upk_extract.py list|dump <package.upk> ...` — extracts Scaleform movies from the game's
  packages on disk (LZO decompression included), for movies that can't be dumped at runtime.
- Dev outputs (probe dumps, extracted game movies, screenshots) are gitignored — keep it that way;
  extracted game files must never be committed.

## Conventions

- Target the **current SDK (v3.x, Python 3.14)**, i.e. `mods_base` / `unrealsdk` APIs.
  Do **not** write legacy-style mods (`from ..ModMenu import SDKMod`, `unrealsdk.RegisterHook`) —
  those only run via `legacy_compat`.
- Use `mods_base`: `build_mod()`, `@hook(...)`, `*Option` classes for configurability, `@keybind`.
- Mod folder names must be valid Python identifiers to be importable (use `snake_case`, no dashes).
- Mods are developed here, **not** inside the game folder. Each mod folder is linked into the game's
  `sdk_mods` with a directory junction (no admin needed), so edits here are live in-game:
  `New-Item -ItemType Junction -Path "<game>\sdk_mods\<mod_name>" -Target "<this folder>\<mod_name>"`
  Create one for every new mod (libraries too). Current junctions: `ammo_counter`, `skill_timer`, `xp_counter`, `z_hud_overlay`, `helios_tracker`.
- Release format: `.sdkmod` = a renamed zip containing `<mod_name>/...`.
- Never scan the whole drive; scope searches to this project or the game folder.
- Edit scripts containing backslash escapes must be written to a file first (the Bash tool eats
  `\\` even in quoted heredocs, which once wrote NUL bytes into a source file).
