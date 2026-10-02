# Dev helper: hot-reloads this mod after code edits, without restarting the game.
# Console: pyexec helios_tracker/reload.py   (an open options menu switches to the reloaded mod: updater.follow_menu)
#   (running the .sdkmod - tools/use_sdkmod.bat: reload.py isn't in it - pyexec .helios_tracker_dev/reload.py)
# The page (web/) is read from disk on every request: for page edits just refresh the tab.
# The mod's modules are dropped and imported fresh (reloading them one by one breaks on new imports).
import importlib
import sys

_pkg = sys.modules.get("helios_tracker")
_old = getattr(_pkg, "mod", None)
_was_enabled = _old is not None and _old.is_enabled
if _old is not None:
    _old.save_settings()  # (a change made in the open menu: saved only when leaving it)
    _old.disable(dont_update_setting=True)  # stops the web server
for _name in [n for n in sys.modules if n == "helios_tracker" or n.startswith("helios_tracker.")]:
    del sys.modules[_name]
importlib.invalidate_caches()  # a replaced .sdkmod: the zip importer's cached index read again (else old offsets)
_pkg = importlib.import_module("helios_tracker")  # build_mod() deregisters the old mod object
if _was_enabled:
    _pkg.mod.enable()
if _old is not None:
    _pkg.updater.follow_menu(_old, _pkg.mod)
print(f"helios_tracker reloaded (enabled={_pkg.mod.is_enabled})")
