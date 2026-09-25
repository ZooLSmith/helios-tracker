# Dev helper (offline tools): this machine's paths, from project.json at the repo root (a copy of
# project.example.json). The tools import it: import project; project.cooked_dir()
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "project.json"


def load() -> dict:
    """project.json, or {} when there's none (or it doesn't parse: said once on stderr)."""
    if not FILE.is_file():
        return {}
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except ValueError as e:
        print(f"project.json: {e}", file=sys.stderr)
        return {}


def path(key: str) -> Path | None:
    """A declared path by dotted key ("game", "references.gibbed"), None when unset. Relative ones are
    the repo's."""
    entry = load()
    for part in key.split("."):
        entry = entry.get(part) if isinstance(entry, dict) else None
    if isinstance(entry, dict):
        entry = entry.get("path")
    if not entry:
        return None
    p = Path(entry).expanduser()
    return p if p.is_absolute() else ROOT / p


def game_dir() -> Path | None:
    return path("game")


def cooked_dir() -> Path | None:
    """WillowGame/CookedPCConsole of the declared install, None without one."""
    game = game_dir()
    return game / "WillowGame" / "CookedPCConsole" if game else None


def require(p: Path | None, what: str) -> Path:
    """p, or exit with where to declare it."""
    if p is None or not p.exists():
        sys.exit(f"{what} not found ({p or 'not set'}): set it in {FILE.name} (see project.example.json)")
    return p
