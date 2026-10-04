"""
Borderlands 1's UI fonts as web fonts (files only: no SDK, no UObjects). Its menus' movies import their fonts from a
font library (their own DefineFont3 tags: 0 glyphs) - Packages/Fonts/Fonts_en.upk's movie Fonts_en: WillowBody (the
menus' text - BL2's too), WillowHead (its headings), Brush Script Std; full DefineFont3 fonts (formats/swffont.py), converted
to TrueType on demand by gamework (font_job, cached on disk) - the catalogue for assets.FONTS (the server's
/font/<slug>.ttf). Fonts_en only: the game's other languages have no library of their own here. .agent/bl1.md "Fonts".
"""

from pathlib import Path

from .... import gamework
from ....formats.fonts import GameFont, slug, to_ttf
from ....formats.swf import _movie_raw, _movie_tags
from ....formats.swffont import parse_font3
from .upk_bl1 import Bl1Package

LIBRARY_PACKAGE = Path("Packages") / "Fonts" / "Fonts_en.upk"  # under WillowGame/CookedPC
LIBRARY_MOVIE = "Fonts_en"
FONT3 = 75  # DefineFont3


def _fonts(path: Path, export: int) -> list[bytes]:
    """The library movie's DefineFont3 tags' bodies, in order."""
    pkg = Bl1Package(path)
    try:
        return [body for code, body in _movie_tags(_movie_raw(pkg, export)) if code == FONT3]
    finally:
        pkg.close()


def catalogue(cooked: Path) -> dict[str, tuple[str, int, Path, int, int, str]]:
    """The library's fonts with glyphs, by slug: (name, glyphs, package, export, n - its n-th DefineFont3, font_job -
    what converts it: assets.GameFonts'). {} without the library."""
    path = cooked / LIBRARY_PACKAGE
    if not path.is_file():
        return {}
    pkg = Bl1Package(path)
    try:
        export = pkg.find(LIBRARY_MOVIE, "GFxMovieInfo")
    finally:
        pkg.close()
    if export is None:
        return {}
    out = {}
    for n, body in enumerate(_fonts(path, export)):
        name_len = body[4]
        name = body[5 : 5 + name_len].rstrip(b"\0").decode("latin1")
        glyphs = int.from_bytes(body[5 + name_len : 7 + name_len], "little")
        if glyphs:
            out.setdefault(slug(name), (name, glyphs, path, export, n, gamework.fn(font_job)))
    return out


def font(path: Path, export: int, n: int) -> GameFont:
    return parse_font3(_fonts(path, export)[n])


def font_job(path: str, idx: int, n: int) -> bytes:
    """The library's n-th DefineFont3 as TrueType (gamework's job: the catalogue's)."""
    return to_ttf(font(Path(path), idx, n))
