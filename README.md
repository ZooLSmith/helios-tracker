# Helios Tracker

A live map of the current level of **Borderlands 2** (and The Pre-Sequel) in your web browser: the game's own map
with players, enemies, NPCs, vehicles, loot and interactive objects on it, live, with zoom and pan - on a second
screen, a phone, in OBS or in the Steam overlay. A mod for the [Python SDK](https://bl-sdk.github.io/).

**Install, use, share the map:** [helios-tracker.zoolsmith.com](https://helios-tracker.zoolsmith.com/) - download
`helios_tracker.sdkmod` from the [releases](https://github.com/ZooLSmith/helios-tracker/releases).

## How it works

The mod (`helios_tracker/`, Python) reads the level and what's in it from the game, runs a small local web server
and streams it to the page (`helios_tracker/web/`, plain HTML / ES modules, no build). It draws nothing in game.
The maps, fonts and icons come from your own game files, read at runtime - nothing of the game's is shipped.

## Development

- `AGENTS.md`: the layout, conventions and workflow (for people and coding agents alike); `.agent/spec.md` the
  spec, `.agent/notes.md` the findings about the game's objects.
- `project.json` (from `project.example.json`): your machine's paths. `python tools/link_mod.py` links the mod into
  the game's `sdk_mods` (edits live in game); `python tools/offline_check.py` checks it outside the game.
- `python tools/build_sdkmod.py` builds the `.sdkmod`; `tools/release.py` publishes a release.

## License

[GPL-3.0](LICENSE). Borderlands is a trademark of Gearbox Software; this is an unofficial fan project.
