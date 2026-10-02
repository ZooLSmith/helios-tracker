"""Where the mod's files are: read from its package (a folder, or a folder inside helios_tracker.sdkmod - a zip),
written to a real folder. No SDK imports: the game files' worker (gamework.py, a subinterpreter) uses it too.

- Read (the page's files): read(rel) - from the folder, or out of the zip (Path.read_bytes can't).
- Written (logs, .cache/): DATA - the package folder itself (dev: the repo, gitignored), or, from a .sdkmod,
  sdk_mods/.helios_tracker/ (the loader skips dot names: any other folder there it imports as a mod). Also the
  place for a downloaded update, before it replaces the .sdkmod.
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
DATA = SDK_MODS / f".{PACKAGE.name}" if SDKMOD else PACKAGE
if SDKMOD:
    try:
        DATA.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


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
