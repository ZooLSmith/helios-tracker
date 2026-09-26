"""
One scan of the game's packages for what the page shows from them - the UI fonts, the item card icons, the skill
icons - and a cache of its result (files only: no SDK, no UObjects).

Opening a package means decompressing its header tables (pure-Python LZO): ~0.6 s for Engine.upk, 1.3 s for
WillowGame.upk. Done on a thread of the game's Python, that froze the game (the one GIL: the game thread's hooks
wait on it every frame). So:
- the scan runs in gamework's subinterpreter (a GIL of its own: beside the game, not in turns with it); without
  one, here, politely (a 1 ms switch interval, a pause after each decompressed block);
- one pass, each package opened once, everything collected from it;
- its result cached (an index - names, export numbers, rectangles; no game art) in .cache/scan.json next to the
  mod (gitignored), per package, keyed by the file's size and date: from the second session on, nothing is
  scanned; a changed package (a patch) is scanned again, alone. The game's side only reads that file.
"""

import json
import threading
from pathlib import Path

from . import gamecards, gamefonts, gameicons, gamework
from .tacmap import Package

CACHE = Path(__file__).with_name(".cache") / "scan.json"
VERSION = 3  # the cache's layout: another number = scanned again (2: the card arts' layers; 3: the textures)
PAUSE = 0.003  # s slept after each decompressed block, scanning in process
SWITCH_INTERVAL = 0.001  # s (Python's default: 0.005), scanning in process

_lock = threading.Lock()
_done = threading.Event()


def packages(cooked: Path) -> list[Path]:
    """What's scanned: the engine config's always-loaded packages (fonts, card icons: gamecards.engine_packages),
    then the classes' streaming packages (skill icons: gameicons)."""
    out = []
    engine_set.clear()
    engine_set.update(gamecards.engine_packages(cooked))
    for p in gamecards.engine_packages(cooked) + gameicons.icon_packages(cooked):
        if p not in out:
            out.append(p)
    return out


engine_set: set[Path] = set()  # the always-loaded packages (packages(): their textures indexed too)


def scan_package(path: Path) -> dict:
    """Everything the page uses from one package: {"fonts": [[name, glyphs, export, n]], "arts": [gamecards'
    art dicts + "movie"], "icons": {path: export}, "textures": {path: export} - every texture of an always-loaded
    package (a pickup's own icon, its PickupFlagIcon: served by path, gameicons.texture_by_path)}."""
    out: dict = {"fonts": [], "arts": [], "icons": {}, "textures": {}}
    always = path in engine_set
    pkg = Package(path)
    try:
        for i in range(len(pkg.exports)):
            cls = pkg.class_name(i)
            if cls == "SwfMovie":
                try:
                    raw = gamefonts.movie_raw(pkg, i)
                except Exception:  # noqa: BLE001, S112 - a movie that won't read
                    continue
                try:
                    out["fonts"] += [[name, count, i, n] for n, name, count in gamefonts.font_headers(raw)]
                except Exception:  # noqa: BLE001, S110
                    pass
                try:
                    movie = pkg.path(i)
                    out["arts"] += [{**art, "movie": movie} for art in gamecards.movie_arts(raw, movie.split(".")[0])]
                except Exception:  # noqa: BLE001, S110
                    pass
            elif cls == "Texture2D":
                name = pkg.path(i)
                if gameicons.ICON_PATH.fullmatch(name):
                    out["icons"].setdefault(name.lower(), i)
                if always:
                    out["textures"].setdefault(name.lower(), i)
    finally:
        pkg.close()
    return out


def _load_cache(cache: Path) -> dict:
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data.get("packages", {}) if data.get("version") == VERSION else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: Path, entries: dict) -> None:
    try:
        cache.parent.mkdir(exist_ok=True)
        tmp = cache.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": VERSION, "packages": entries}), encoding="utf-8")
        tmp.replace(cache)
    except OSError:
        pass  # (no cache: scanned again next time)


def _stamp(path: Path) -> list[int]:
    st = path.stat()
    return [st.st_size, st.st_mtime_ns]


def _fresh(cooked: Path, cached: dict) -> bool:
    return all((e := cached.get(str(p))) is not None and e.get("stamp") == _stamp(p) for p in packages(cooked))


def scan_to_cache(cooked: Path, cache: Path) -> None:
    """The scan (gamework's job: in its subinterpreter): the changed / new packages scanned, the cache written."""
    cached = _load_cache(cache)
    entries: dict = {}
    for path in packages(cooked):
        key, stamp = str(path), _stamp(path)
        if (entry := cached.get(key)) is not None and entry.get("stamp") == stamp:
            entries[key] = entry
            continue
        try:
            entries[key] = {"stamp": stamp, **scan_package(path)}
        except Exception:  # noqa: BLE001 - a package that won't read: nothing from it
            entries[key] = {"stamp": stamp, "fonts": [], "arts": [], "icons": {}, "textures": {}}
    if entries != cached:
        _save_cache(cache, entries)


def run(cooked: Path | None) -> None:
    """The game's side (a thread: a page connected): the scan in the worker unless the cache's up to date, then
    the fonts / card icons / skill icons get their indexes from the cache. Once per session."""
    with _lock:
        if _done.is_set() or cooked is None:
            return
        entries = _load_cache(CACHE)
        if not _fresh(cooked, entries):
            gamework.work({"do": "scan", "cooked": str(cooked), "cache": str(CACHE)})
            entries = _load_cache(CACHE)
        # the indexes: fonts (each name's fullest), card arts (by label), skill icons (by path)
        fonts: dict = {}
        arts: dict = {}
        icons: dict = {}
        textures: dict = {}
        for key, entry in entries.items():
            path = Path(key)
            for name, count, idx, n in entry["fonts"]:
                slug = gamefonts.slug(name)
                if slug and count and (slug not in fonts or count > fonts[slug][1]):
                    fonts[slug] = (name, count, path, idx, n)
            for art in entry["arts"]:
                arts.setdefault(art["label"], []).append(gamecards.Art.load(path, art))
            for icon, idx in entry["icons"].items():
                icons.setdefault(icon, (path, idx))
            for tex, idx in entry.get("textures", {}).items():
                textures.setdefault(tex, (path, idx))
        gamefonts.set_catalogue(fonts)
        gameicons.set_textures(textures)  # (before the card arts: their news - "assets" - tells about both)
        gamecards.set_index(arts)
        gameicons.set_index(icons)
        _done.set()


def ready() -> bool:
    return _done.is_set()


def wait(timeout: float) -> bool:
    """Waits for the scan to be done (a server thread: a font asked for as the page opens)."""
    return _done.wait(timeout)
