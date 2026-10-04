"""
BL2's fonts: its font libraries (one per language - which one the game uses) and its compacted fonts converted for
the worker (font_job: the files scan's catalogue names it - gamescan.run). The format: formats/fonts.py.
"""

from pathlib import Path

from ....formats.fonts import movie_fonts, to_ttf
from ....formats.swf import _movie_raw
from ....formats.upk import opened

# The game's font libraries, one per language (both games' DefaultEngine.ini load them all: UI_FontsEn / Jp / Kr and
# BL2's Twn, the Pre-Sequel's Ru) - the game's code picks its language's. The same font name is in each, drawn
# differently: the Pre-Sequel's UI_FontsRu WillowBody has narrower Latin letters than UI_FontsEn's (BL2's and the
# Pre-Sequel's English ones are the same). Its language (Object.GetLanguage: "INT", "RUS"...) -> its library; ours,
# no data says it (the user's call: follow the game's language - an item's name in its letters, no missing glyphs).
FONT_LIBRARIES = {"RUS": "UI_FontsRu", "JPN": "UI_FontsJp", "KOR": "UI_FontsKr", "TWN": "UI_FontsTwn"}
DEFAULT_LIBRARY = "UI_FontsEn"  # (the Latin languages': INT, FRA, DEU, ESN, ITA)


def font_library(language: str) -> str:
    """The font library the game uses in `language` (its GetLanguage: "INT", "RUS"...)."""
    return FONT_LIBRARIES.get(str(language or "").upper(), DEFAULT_LIBRARY)


def font_job(path: str, idx: int, n: int) -> bytes:
    """A movie's n-th compacted font as TrueType (gamework's job: the catalogue's)."""
    with opened(Path(path)) as pkg:  # (the worker: kept open for the next job)
        return to_ttf(movie_fonts(_movie_raw(pkg, idx))[n])
