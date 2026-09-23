# References

## Game install

- **Borderlands 2 is installed at:** `E:\SteamLibrary\steamapps\common\Borderlands 2`
- Executable / SDK plugin folder: `...\Borderlands 2\Binaries\Win32\`
  - `Plugins\` — `unrealsdk.dll`, `pyunrealsdk.dll`, `python314.dll` (**Python 3.14, 32-bit**),
    `unrealsdk.toml` (SDK config), `unrealsdk.log` (SDK log — check here for tracebacks)
- Mods folder: `...\Borderlands 2\sdk_mods\`
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

Current setup: each mod is a **directory junction** in `sdk_mods` pointing back here:
- `sdk_mods\ammo_counter` → `E:\Projects\python\borderlands-2\ammo_counter`

Deleting a junction (`Remove-Item <link>` — no `-Recurse`) only removes the link, not the project.

Alternative (not used): create `Binaries\Win32\Plugins\unrealsdk.user.toml` (overrides
`unrealsdk.toml`, don't edit the original):

```toml
[unrealsdk]
console_log_level = "DWRN"   # show developer warnings in the console

[mod_manager]
extra_folders = ["E:\\Projects\\python\\borderlands-2"]
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

## Links

- Developer docs: https://bl-sdk.github.io/developing/
- Getting started: https://bl-sdk.github.io/developing/getting_started/
- Releasing a mod: https://bl-sdk.github.io/developing/releasing_your_mod/
- ui_utils (BL2): https://bl-sdk.github.io/developing/ui_utils/willow2/
- BL2 mod DB: https://bl-sdk.github.io/willow2-mod-db/
- GitHub org: https://github.com/bl-sdk
