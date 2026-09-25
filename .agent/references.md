# References

## Game install

- **Where Borderlands 2 is installed:** `project.json`'s `game.path` (written `<game>` below;
  `<repo>` is this repo's root). Steam's default: `C:\Program Files (x86)\Steam\steamapps\common\Borderlands 2`.
- Executable / SDK plugin folder: `<game>\Binaries\Win32\`
  - `Plugins\` — `unrealsdk.dll`, `pyunrealsdk.dll`, `python314.dll` (**Python 3.14, 32-bit**),
    `unrealsdk.toml` (SDK config), `unrealsdk.log` (SDK log — check here for tracebacks)
- Game packages: `<game>\WillowGame\CookedPCConsole\`, DLCs' in `<game>\DLC\<Name>\...\Content`
- Mods folder: `<game>\sdk_mods\`
  - `__main__.py` — mod manager init script
  - `*.sdkmod` — installed mods/libs (zips): `mods_base`, `ui_utils`, `keybinds`, `networking`,
    `save_options`, `console_mod_menu`, `willow2_mod_menu`, `legacy_compat`, …
  - `.stubs\` — type stubs for `unrealsdk` / `pyunrealsdk` (point the IDE at this + `sdk_mods`)
  - `settings\` — per-mod JSON settings (saved option values)
  - `ActionSkillCountdown\` — a legacy-style mod that draws text on the HUD canvas; good reference
    for the `PostRender` + `Canvas.DrawText` technique.

## Installed SDK

- Mod manager display version: **3.8** (`mods_base` 1.12), BL2 menu: willow2_mod_menu.
- `unrealsdk.toml` currently has:
  ```toml
  [pyunrealsdk]
  init_script = "..\\..\\..\\sdk_mods\\__main__.py"
  pyexec_root = "..\\..\\..\\sdk_mods"
  ```

### Loading mods from this project folder

Current setup: each mod is a **directory junction** in `sdk_mods` pointing back here
(`python tools/link_mod.py` makes it):
- `<game>\sdk_mods\helios_tracker` → `<repo>\helios_tracker`

Deleting a junction (`Remove-Item <link>` — no `-Recurse`) only removes the link, not the project.

Alternative (not used): create `Binaries\Win32\Plugins\unrealsdk.user.toml` (overrides
`unrealsdk.toml`, don't edit the original):

```toml
[unrealsdk]
console_log_level = "DWRN"   # show developer warnings in the console

[mod_manager]
extra_folders = ["<repo>"]   # absolute, with doubled backslashes
```

### Dev tips

- Console commands: `py <code>` (supports `py << EOF` heredocs) and `pyexec <file>` (relative to
  `pyexec_root`) — handy for poking at live objects.
- Debugging: `pip install debugpy` into a matching 3.14 32-bit env, set `[pyunrealsdk] debugpy = true`,
  attach to `localhost:5678`.
- IDE: add `sdk_mods` and `sdk_mods/.stubs` to `python.analysis.extraPaths`.

## Modern API cheat sheet (mods_base)

```python
import unrealsdk
from unrealsdk.hooks import Type
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct
from mods_base import build_mod, hook, get_pc, ENGINE, SliderOption, BoolOption, SpinnerOption, \
    DropdownOption, NestedOption, GroupedOption, keybind

@hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST)
def on_post_render(obj: UObject, args: WrappedStruct, ret, func: BoundFunction) -> None:
    canvas = args.Canvas
    ...

build_mod()  # picks up hooks/options/keybinds defined in the module + metadata from pyproject.toml
```

- **Hook names use `:` between class and function** (`Package.Class:Function`). A `.` silently
  matches nothing — the hook registers fine but never fires. (Legacy mods used `.`.)
- **Out params must still be passed** (any placeholder value); results come back as a tuple
  `(return_value, *out_params)`, with `Ellipsis` as the return value of void functions:
  `_, w, h = canvas.TextSize(text, 0, 0)`.
- **Never keep raw UObject references across frames** unless something keeps them alive. Wrapper
  objects like `GFxObject`s from `GetVariableObject`/`GetObject` are freed by the next garbage
  collection (e.g. opening the pause menu); touching one afterwards is a **hard game crash**
  (fatal error inside pyunrealsdk, stack shows `PyObject_GetMethod` → `cast_to_ffield`). Hold them
  via `unrealsdk.unreal.WeakPointer` (returns None once freed), and set
  `obj.ObjectFlags |= ObjectFlags.KEEP_ALIVE` on ones you must keep (clear it when done).
- Errors inside a per-frame hook (e.g. `PostRender`) flood `unrealsdk.log` — catch and log each
  distinct error once.
- Hook callbacks: `(obj, args, ret, func)`; pre-hooks may return `unrealsdk.hooks.Block` to block.
- `unrealsdk.find_object(class, path)`, `unrealsdk.find_all(class)`, `unrealsdk.load_package(...)`.
- `get_pc()` → local `WillowPlayerController`.
- Keep-alive for constructed objects: `mods_base.ObjectFlags.KEEP_ALIVE`.

## HUD drawing notes

- BL2's HUD is Scaleform (GFx); mods typically overlay on the UE3 `Canvas` from `PostRender`.
- `Canvas`: `SetPos`, `SetDrawColorStruct((b, g, r, a))`, `DrawText(text, cr, xscale, yscale)`,
  `DrawTile(Texture2D, XL, YL, U, V, UL, VL)`, `SizeX/SizeY`, `Font`.
- Fonts seen used: `UI_Fonts.Font_Willowbody_18pt`, `UI_Fonts.Font_Willowhead_8pt`,
  `UI_Fonts.Font_Hud_Medium`, `EngineFonts.SmallFont`, `EngineFonts.TinyFont`.
- Hide overlay when: no HUD movie (`pc.GetHUDMovie() is None`), menus open, in FFYL, in vehicle.

## Game data dumps (Gibbed.Borderlands2)

`project.json`'s `references.gibbed` (https://github.com/gibbed/Gibbed.Borderlands2): Gibbed's save
editor (C#, 2021), cloned for reference (read-only; nothing from it goes in this repo). Paths below are
relative to that clone. Its game data is JSON dumped from the game's objects,
keyed by object path (`GD_...`), base game plus every DLC. It lives in the `Resources\Dumps` submodule
(checked out with `git submodule update --init`):
`projects\Gibbed.Borderlands2.GameInfo\Resources\Dumps\` (~2.8 MB)

- `Missions.json`: path → `number`, `name`, `description`, `is_plot_critical`, `can_be_failed`.
- `Travel Stations.json` / `Fast Travel Station Ordering.json`: stations → `level_name` (`*_P`),
  display names, DLC; the fast travel list order.
- `Items.json`: item definitions → name, `type` (`UsableItem`, …): pickups, ammo, cash, mission items.
- `Weapon Balance.json` / `Item Balance.json` (+ `* Part Lists.json`): balances → base / item type,
  manufacturers, parts. The balance path names the rarity grade (`_3_Rare`, `_4_VeryRare`, `_5_Alien`
  = E-tech, `Legendary`, …).
- `Weapon Name Parts.json` / `Item Name Parts.json`: prefixes and titles → names (`unique`: a named
  item's).
- `Weapon Types.json`, `Weapon Parts.json`, `Item Parts.json`: types and parts.
- `Customizations.json` (heads / skins → name, class, DLC), `Player Classes.json`,
  `Downloadable Contents.json` / `Downloadable Packages.json` (DLC ids → names), `Asset Library
  Manager.json` (the save format's part indexes).
- DLC code names (the `GD_<Name>_…` packages): Orchid = Pirate's Booty, Iris = Campaign of Carnage,
  Sage = Hammerlock's Hunt, Aster = Dragon Keep, Anemone = Fight for Sanctuary, Flax = Bloody Harvest,
  Allium / Nasturtium = Headhunter packs, Gladiolus / Lobelia = Ultimate Upgrade Packs,
  Tulip = Mechromancer, Lilac = Psycho.
- Not in there: RarityLevel values, colours, positions or level contents. Use them to put a name to
  an object path the game gives us, or to check one, **not** as the page's text: names still come from
  the game at runtime (`AGENTS.md`: game text only).
- Rarity leads: Gemstone = Dragon Keep's `GD_Aster_Weapons.*_4_<Gem>` balances (Quartz, Emerald,
  Diamond, Citrine, Garnet, Rock...: grade 4 like Epic, with a `Prefix_Gemstone_*` name part; also
  `GD_Anemone_Weapons...Prefix_Gemstone_Rock`). Cursed (Pirate's Booty per the wiki): no lead in the
  dumps yet. To match against `tools/probe_rarity4.py`'s unnamed levels.
- The code: `projects\Gibbed.Borderlands2.FileFormats` (save file and packed item / weapon formats),
  `projects\Gibbed.Borderlands2.GameInfo` (loaders for the dumps).

## Links

- Developer docs: https://bl-sdk.github.io/developing/
- Getting started: https://bl-sdk.github.io/developing/getting_started/
- Releasing a mod: https://bl-sdk.github.io/developing/releasing_your_mod/
- ui_utils (BL2): https://bl-sdk.github.io/developing/ui_utils/willow2/
- BL2 mod DB: https://bl-sdk.github.io/willow2-mod-db/
- GitHub org: https://github.com/bl-sdk
