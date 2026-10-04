"""Where the mod's files are: read from its package (a folder, or a folder inside helios_tracker.sdkmod - a zip),
written to a real folder. No SDK imports: the game files' worker (gamework.py, a subinterpreter) uses it too.

- Read (the page's files): read(rel) - from the folder, or out of the zip (Path.read_bytes can't).
- Written (logs, .cache/, the user's script, a downloaded update before it replaces the .sdkmod): DATA -
  sdk_mods/.helios_tracker/ beside the package, whichever the install (a .sdkmod or a folder: the package holds code
  only - the user: its folder had the logs and the script among the modules). The loader skips dot names: any other
  folder there it would import as a mod.
- DIAGNOSTICS: the debug measurements on (frames.py's frame report and its canary, the slow-task report's
  breakdowns) - a folder install (dev) yes, a .sdkmod (what players run) no; a `diagnostics` file in DATA says
  otherwise ("on" / "off": a player's for a bug report, a dev's to measure without them). Read at load.
"""

import zipfile
from pathlib import Path

PACKAGE = Path(__file__).parent


def _sdkmod(package: Path) -> Path | None:
    """The .sdkmod holding the package (its nearest ancestor that's a file), None for a folder."""
    for parent in (package, *package.parents):
        if parent.is_dir():
            return None
        if parent.is_file():
            return parent
    return None


SDKMOD = _sdkmod(PACKAGE)
SDK_MODS = SDKMOD.parent if SDKMOD else PACKAGE.parent
DATA = SDK_MODS / f".{PACKAGE.name}"
try:
    DATA.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def _diagnostics() -> bool:
    try:
        said = (DATA / "diagnostics").read_text(encoding="utf-8").strip().lower()
    except OSError:
        return SDKMOD is None  # (no file: the install says)
    return said in ("on", "1", "true", "yes")


DIAGNOSTICS = _diagnostics()


def read(rel: str) -> bytes | None:
    """A file of the package ("web/index.html"), None if there's none."""
    if SDKMOD is None:
        path = PACKAGE / rel
        return path.read_bytes() if path.is_file() else None
    inner = PACKAGE.relative_to(SDKMOD).as_posix() + "/" + rel  # (zip names: "/", from the zip's root)
    try:
        with zipfile.ZipFile(SDKMOD) as z:  # (opened per read: nothing held on the file)
            return z.read(inner)
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
