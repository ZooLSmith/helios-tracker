"""
What the game's files give the page, kept for every game's way of reading them (games.GAME.assets: when they're read,
what serves them): the fonts' catalogue (the server's /font/<slug>.ttf) and the item card icons' keys - the game's
labels for each kind, read by the inspector from the loaded definitions; a game's card icons are looked up by them.
Any thread; no SDK.
"""

import threading
from typing import Any

from . import gamework

# region Fonts


class GameFonts:
    """The game's UI fonts: a catalogue the game's assets give (each font found cheaply - its header only: the Asian
    fonts' 13,000+ glyphs take a minute to convert, only when asked for), converted on demand by the job each entry
    names; get(slug) converts once. Thread-safe; dict-like for the server (get)."""

    def __init__(self, catalogue: dict | None = None) -> None:
        self._lock = threading.Lock()
        self._ready = threading.Event()  # (a catalogue set: the server's font requests wait for it - wait)
        self._ttf: dict[str, bytes | None] = {}
        # slug -> (name, glyphs, package, export, n, the job converting it: gamework.fn of a font_job(path, idx, n))
        self.catalogue: dict[str, tuple] = catalogue or {}

    def set_catalogue(self, catalogue: dict) -> None:
        with self._lock:
            self.catalogue = catalogue
            self._ttf = {}
        self._ready.set()

    def wait(self, timeout: float) -> bool:
        """Waits for a catalogue (a page asks for its fonts as it loads - before the catalogue's there, a 404 it never
        asks again)."""
        return self._ready.wait(timeout)

    def names(self) -> list[str]:
        return [name for name, *_ in self.catalogue.values()]

    def get(self, slug: str, default: bytes | None = None) -> bytes | None:
        """A font as TrueType: converted by gamework (its subinterpreter; cached on disk), kept."""
        with self._lock:
            if slug in self._ttf:
                return self._ttf[slug] if self._ttf[slug] is not None else default
            entry = self.catalogue.get(slug)
        data = None
        if entry is not None:
            _name, _count, path, idx, n, fn = entry
            data = gamework.asset({"fn": fn, "path": str(path), "idx": idx, "n": n}, [path])
        with self._lock:
            self._ttf[slug] = data
        return data if data is not None else default


FONTS = GameFonts()  # the mod's: its catalogue from the game's assets (games.GAME.assets.job) - the server serves it

# endregion
# region The item card icons' keys

_lock = threading.Lock()
_keys: dict[str, set[str]] = {}  # kind ("manufacturer", "type", "element") -> the game's keys (lower case)

# Called (no arguments, any thread) when what the page can ask for may have changed: the mod publishes it ("assets") -
# the page asks for icons only once they can be found (asked before: a 404, and a map marker gave up on it)
listener: Any = None


def changed() -> None:
    """What can be served may have changed (keys known, a game's index read): the listener told."""
    if listener is not None:
        try:
            listener()
        except Exception:  # noqa: BLE001, S110 - (the page's news: never breaks the index / the game thread)
            pass


def set_keys(kind: str, keys: set[str]) -> None:
    """The game's own keys for a kind (from the loaded definitions): what its icons are labelled."""
    with _lock:
        _keys[kind] = {k.lower() for k in keys if k}
    changed()


def keys(kind: str) -> set[str]:
    """The game's keys for a kind, as set_keys got them (lower case) - empty until the first players' read."""
    with _lock:
        return set(_keys.get(kind, ()))


# endregion
