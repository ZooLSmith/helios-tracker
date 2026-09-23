# Dev helper: hot-reloads this mod after code edits, without restarting the game.
# Console: pyexec helios_tracker/reload.py   (reopen the mod's options menu afterwards)
# The page (web/) is read from disk on every request: for page edits just refresh the tab.
# The mod's modules are dropped and imported fresh (reloading them one by one breaks on new imports).
import importlib
import sys

_pkg = sys.modules.get("helios_tracker")
_was_enabled = _pkg is not None and hasattr(_pkg, "mod") and _pkg.mod.is_enabled
if _pkg is not None and hasattr(_pkg, "mod"):
    _pkg.mod.disable(dont_update_setting=True)  # stops the web server
for _name in [n for n in sys.modules if n == "helios_tracker" or n.startswith("helios_tracker.")]:
    del sys.modules[_name]
_pkg = importlib.import_module("helios_tracker")  # build_mod() deregisters the old mod object
if _was_enabled:
    _pkg.mod.enable()
print(f"helios_tracker reloaded (enabled={_pkg.mod.is_enabled})")
