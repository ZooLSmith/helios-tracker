"""
The engine's config: the packages it always loads (UE3's ini files). Files only, no SDK.
"""

from pathlib import Path


def engine_packages(cooked: Path) -> list[Path]:
    """The always-loaded packages, in the engine's order: [Engine.ScriptPackages] (every *Packages entry but the
    editor's), [Engine.StartupPackages] (Package=), from Engine/Config/BaseEngine.ini then the game's
    Config/DefaultEngine.ini (+ entries), then the cooked Startup - only the files that exist."""
    game = cooked.parent.parent
    names: list[str] = []
    for ini in [game / "Engine" / "Config" / "BaseEngine.ini", *sorted(cooked.parent.glob("Config/DefaultEngine.ini"))]:
        try:
            text = ini.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        section = ""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line.strip("[]")
            elif "=" in line and not line.startswith(";"):
                key, value = (s.strip() for s in line.split("=", 1))
                key = key.lstrip("+.-!")
                if (section == "Engine.ScriptPackages" and key.endswith("Packages") and "Editor" not in key) or \
                        (section == "Engine.StartupPackages" and key == "Package"):
                    if value and value not in names:
                        names.append(value)
    names.append("Startup")
    out, seen = [], set()
    for name in names:
        path = cooked / f"{name}.upk"
        if path.is_file() and path not in seen:
            seen.add(path)
            out.append(path)
    return out
