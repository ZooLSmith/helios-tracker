"""Borderlands 2's assets (the base: every game's unless its profile has its own) - The game's files the page shows (fonts, icons): when they're read, what a request waits for, card icons."""

import re
import time
from typing import Any

from ..base import Part

# its images the server asks for (serve): a skill icon by its movie's path, an item card icon by kind and key, an
# always-loaded texture by path (a pickup's icon)
ICON = re.compile(r"/icon/((?:UI_[A-Za-z0-9]+_)?SharedSkillIcons_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+)\.png", re.I)
CARD_ICON = re.compile(r"/cardicon/(manufacturer|type|element)/([A-Za-z0-9_]+)\.png")
TEXTURE = re.compile(r"/texture/([A-Za-z0-9_]+(?:\.[A-Za-z0-9_-]+)+)\.png")


class Assets(Part):
    """The game's files the page shows (fonts, icons): when they're read, what a request waits for, card icons."""

    def job(self, boot: bool) -> Any:
        """The work reading the game's files (fonts, item card / skill icons) - to run once, in a thread - at boot or when
        a page first connects (`boot`), or None (__init__._start_assets): BL2's files scan (files/gamescan.py: one pass,
        cached on disk) when a page connects - not at every game start. Its language read now (the game thread: its
        font library, gamefonts.font_library)."""
        if boot:
            return None
        from ... import assets, gamework  # noqa: PLC0415
        from ...collector import game_language  # noqa: PLC0415
        from .files import gamefonts, gamescan  # noqa: PLC0415
        from ...gamedir import cooked_dir  # noqa: PLC0415
        from ...util import log, log_error  # noqa: PLC0415

        # the game's language (Core.Object's static GetLanguage: "INT", "RUS"... - read here, on the game thread)
        language = game_language()

        def scan() -> None:
            try:
                t = time.monotonic()
                gamescan.run(cooked_dir(), language)
                log(f"game files indexed in {time.monotonic() - t:.1f} s ({gamework.mode()}): language {language or '?'}"
                    f" ({gamefonts.font_library(language)}), fonts {', '.join(assets.FONTS.names())}")
            except Exception as ex:  # noqa: BLE001
                log_error("game files scan", ex)

        return scan

    def wait_for(self, path: str, timeout: float) -> None:
        """A server thread asked for a file of the game's (path: "/font/...", "/icon/"...): waits, up to `timeout`, for
        what it needs to be read - BL2's: the files scan (a page just opened: its scan's running)."""
        from .files import gamescan  # noqa: PLC0415

        if path.startswith(("/font/", "/icon/", "/cardicon/", "/texture/")) and not gamescan.ready():
            gamescan.wait(timeout)

    def card_icon_png(self, kind: str, key: str) -> bytes | None:
        """An item card icon (/cardicon/<kind>/<key>.png) as a PNG, or None: the game's UI movies' (files/gamecards.py,
        from the files scan). The server's threads: no SDK."""
        from .files import gamecards  # noqa: PLC0415

        return gamecards.card_png(kind, key)

    def card_icons_ready(self) -> bool:
        """Whether card_icon_png can find icons (the page asks only then): the scan done, the keys known."""
        from .files import gamecards  # noqa: PLC0415

        return gamecards.ready()

    def textures_ready(self) -> bool:
        """Whether serve can find the always-loaded textures (a pickup's icon: the page asks only then)."""
        from .files import gameicons  # noqa: PLC0415

        return gameicons.textures_ready()

    def serve(self, path: str) -> bytes | None:
        """A request for one of the game's images (the server's threads: no SDK) -> a PNG, or None (not one, not found):
        a skill icon (/icon/<its movie's path>.png), an item card icon (/cardicon/<kind>/<key>.png), an always-loaded
        texture by path (/texture/<path>.png: a pickup's icon) - files/gameicons.py, gamecards.py."""
        from .files import gameicons  # noqa: PLC0415

        if m := ICON.fullmatch(path):
            return gameicons.icon_png(m[1])
        if m := CARD_ICON.fullmatch(path):
            return self.card_icon_png(m[1], m[2])
        if m := TEXTURE.fullmatch(path):
            return gameicons.texture_by_path(m[1])
        return None
