"""Borderlands 2's assets (the base: every game's unless its profile has its own) - The game's files the page shows (fonts, icons): when they're read, what a request waits for, card icons.
Moved from games.py (profiles.md step 4: a pure move)."""

import time
from typing import Any

from ..base import Part


class Assets(Part):
    """The game's files the page shows (fonts, icons): when they're read, what a request waits for, card icons."""

    def job(self, boot: bool) -> Any:
        """The work reading the game's files (fonts, item card / skill icons) - to run once, in a thread - at boot or when
        a page first connects (`boot`), or None (__init__._start_assets): BL2's files scan (gamescan.py: one pass,
        cached on disk) when a page connects - not at every game start. Its language read now (the game thread: its
        font library, gamefonts.font_library)."""
        if boot:
            return None
        from ... import gamefonts, gamescan, gamework  # noqa: PLC0415
        from ...collector import game_language  # noqa: PLC0415
        from ...gamedir import cooked_dir  # noqa: PLC0415
        from ...util import log, log_error  # noqa: PLC0415

        # the game's language (Core.Object's static GetLanguage: "INT", "RUS"... - read here, on the game thread)
        language = game_language()

        def scan() -> None:
            try:
                t = time.monotonic()
                gamescan.run(cooked_dir(), language)
                log(f"game files indexed in {time.monotonic() - t:.1f} s ({gamework.mode()}): language {language or '?'}"
                    f" ({gamefonts.font_library(language)}), fonts {', '.join(gamefonts.FONTS.names())}")
            except Exception as ex:  # noqa: BLE001
                log_error("game files scan", ex)

        return scan

    def wait_for(self, path: str, timeout: float) -> None:
        """A server thread asked for a file of the game's (path: "/font/...", "/icon/"...): waits, up to `timeout`, for
        what it needs to be read - BL2's: the files scan (a page just opened: its scan's running)."""
        from ... import gamescan  # noqa: PLC0415

        if path.startswith(("/font/", "/icon/", "/cardicon/", "/texture/")) and not gamescan.ready():
            gamescan.wait(timeout)

    def card_icon_png(self, kind: str, key: str) -> bytes | None:
        """An item card icon (/cardicon/<kind>/<key>.png) as a PNG, or None: the game's UI movies' (gamecards.py, from
        the files scan). The server's threads: no SDK."""
        from ... import gamecards  # noqa: PLC0415

        return gamecards.card_png(kind, key)

    def card_icons_ready(self) -> bool:
        """Whether card_icon_png can find icons (the page asks only then): the scan done, the keys known."""
        from ... import gamecards  # noqa: PLC0415

        return gamecards.ready()
