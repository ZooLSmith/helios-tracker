"""
Borderlands 1's textures by object path, as PNGs - a pickup's own icon (its ItemDefinition.PickupFlagIcon, as BL2's:
"FX_Items.Textures.Credits", .Health, .Ammo_SMG... - tools/probes/probe_bl1_pickup_icons.txt). No files scan to index
them: a path's first part is its package, a file of that name somewhere under CookedPC (FX_Items: Packages/effects/
FX_Items.upk) - found by name, the export by the rest of its path. Decoded by gamework (cached on disk). Files only:
no SDK - the server's threads.
"""

import re
import threading
from pathlib import Path

from .... import gamework
from ....formats.image import decode_dxt, png
from ....formats.upk import _texture
from .upk_bl1 import Bl1Package

TEXTURE_PATH = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_-]+)+")
MAX_PNGS = 200  # PNGs kept

_lock = threading.Lock()
_files: dict[str, dict[str, Path]] = {}  # CookedPC -> its packages by name (lower case): read once
_pngs: dict[str, bytes | None] = {}


def _package_file(cooked: Path, name: str) -> Path | None:
    """The package file named `name` under CookedPC (any folder) - the folder listed once."""
    with _lock:
        files = _files.get(str(cooked))
    if files is None:
        files = {p.stem.lower(): p for p in cooked.rglob("*.upk")}
        with _lock:
            _files[str(cooked)] = files
    return files.get(name.lower())


def texture_png(cooked: Path, path: str) -> bytes | None:
    """A texture by its object path ("FX_Items.Textures.Credits") as a PNG, or None (not a path, no such package or
    texture, won't decode). Kept. Thread-safe."""
    if not TEXTURE_PATH.fullmatch(path or ""):
        return None
    key = path.lower()
    with _lock:
        if key in _pngs:
            return _pngs[key]
    package, _, inner = path.partition(".")
    file = _package_file(cooked, package)
    data = gamework.asset({"fn": gamework.fn(texture_job), "path": str(file), "name": inner}, [file]) if file else None
    with _lock:
        if len(_pngs) >= MAX_PNGS:
            _pngs.pop(next(iter(_pngs)))
        _pngs[key] = data
    return data


def texture_job(path: str, name: str) -> bytes:
    """A package's texture (its path inside the package: "Textures.Credits") as a PNG - b"" for none (gamework's job)."""
    pkg = Bl1Package(Path(path))
    try:
        if (idx := pkg.find(name, "Texture2D")) is None:
            return b""
        fmt, w, h, body = _texture(pkg, idx)
    finally:
        pkg.close()
    return png(w, h, decode_dxt(fmt, w, h, body))
