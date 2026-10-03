"""
The game's folders: the install, its cooked packages, a package by file name. Files only (any thread); the folders'
names and depth per game come from the profile (games.py).
"""

import sys
from pathlib import Path

from . import games


def game_dir() -> Path | None:
    """This install's folder, the one holding WillowGame: up from the game's executable (games.py exe_depth: BL2's
    Binaries/Win32/Borderlands2.exe, BL1's Binaries/Borderlands.exe), else up from this file (the mod folder in
    sdk_mods - unresolved: it may be a junction elsewhere)."""
    candidates = [Path(sys.executable).parents[games.GAME.exe_depth], *Path(__file__).absolute().parents]
    for base in candidates:
        if (base / "WillowGame").is_dir():
            return base
    return None


def cooked_dir() -> Path | None:
    """WillowGame/<the profile's packages folder> of this install: the packages the mod reads (None: none read)."""
    game, folder = game_dir(), games.GAME.packages
    d = game / "WillowGame" / folder if game is not None and folder else None
    return d if d is not None and d.is_dir() else None


# DLC packages: <game>/DLC/<code name>/{Lic,Compat}/Content/*.upk (seen: DLC/Sage/Lic/Content/
# Sage_Underground_P.upk) - file name (lower case) -> path, listed once (the DLCs don't change while
# the game runs)
_dlc_packages: dict[str, Path] | None = None


def package_path(file_name: str) -> Path | None:
    """A cooked package by file name: the base game's (WillowGame/CookedPCConsole), else a DLC's. Files
    only (the map extraction thread)."""
    global _dlc_packages  # noqa: PLW0603
    cooked = cooked_dir()
    if cooked is None:
        return None
    if (path := cooked / file_name).is_file():
        return path
    if _dlc_packages is None:
        _dlc_packages = {}
        for content in sorted((cooked.parent.parent / "DLC").glob("*/*/Content")):
            for pkg in content.glob("*.upk"):
                _dlc_packages.setdefault(pkg.name.lower(), pkg)
    return _dlc_packages.get(file_name.lower())
