"""Borderlands 2's ui (the base: every game's unless its profile has its own) - The game's own UI the mod speaks through (its bottom-left message).
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part


class Ui(Part):
    """The game's own UI the mod speaks through (its bottom-left message)."""

    def show_message(self, text: str, duration: float) -> None:
        """The game's bottom-left message (ui_utils' co-op one: it stays until hide_message)."""
        from ui_utils import show_coop_message  # noqa: PLC0415 (not in every game's ui_utils: imported here, in BL2's)

        show_coop_message(text)

    def hide_message(self) -> None:
        from ui_utils import hide_coop_message  # noqa: PLC0415

        hide_coop_message()
