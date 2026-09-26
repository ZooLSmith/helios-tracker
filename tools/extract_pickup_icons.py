"""Offline: the pickups' own icons (their PickupFlagIcon textures, found in game by tools/probe_pickup_icons.py) as PNGs
in _work/pickup_icons/ (gitignored: nothing extracted from the game goes in the repo) - to look at them before choosing
map markers. Searches the always-loaded packages (the engine config's, gamecards.engine_packages) and Startup /
WillowGame for each texture's object path.

    python tools/extract_pickup_icons.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import project  # noqa: E402

PROBE = ROOT / "tools" / "probe_pickup_icons.txt"
OUT = ROOT / "_work" / "pickup_icons"


def main() -> None:
    # the mod's file readers only (no SDK): its package reader, DXT decoder, PNG encoder
    import types  # noqa: PLC0415

    # the package without its __init__ (that builds the mod: the SDK) - its file-only modules import as they are
    package = types.ModuleType("helios_tracker")
    package.__path__ = [str(ROOT / "helios_tracker")]
    sys.modules["helios_tracker"] = package
    from helios_tracker.gamecards import engine_packages  # noqa: PLC0415
    from helios_tracker.gameicons import decode_dxt, png  # noqa: PLC0415
    from helios_tracker.tacmap import Package, _texture  # noqa: PLC0415

    cooked = project.require(project.cooked_dir(), "the game's cooked packages (project.json: game.path)")
    paths = sorted(set(re.findall(r"= ([A-Za-z0-9_]+\.[A-Za-z0-9_.]+) \[Texture2D\]", PROBE.read_text(encoding="utf-8"))))
    if not paths:
        print(f"no textures in {PROBE}: run tools/probe_pickup_icons.py in game first")
        return
    packages = list(dict.fromkeys([*engine_packages(cooked), cooked / "Startup.upk", cooked / "WillowGame.upk"]))
    OUT.mkdir(parents=True, exist_ok=True)
    left = set(paths)
    for package_file in packages:
        if not left or not package_file.is_file():
            continue
        pkg = Package(package_file)
        try:
            for path in sorted(left):
                idx = pkg.find(path, "Texture2D")
                if idx is None:
                    continue
                fmt, w, h, body = _texture(pkg, idx)
                (OUT / f"{path.rpartition('.')[2]}.png").write_bytes(png(w, h, decode_dxt(fmt, w, h, body)))
                print(f"{path}: {w}x{h} {fmt} (from {package_file.name})")
                left.discard(path)
        finally:
            pkg.close()
    for path in sorted(left):
        print(f"{path}: not found in the always-loaded packages")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
