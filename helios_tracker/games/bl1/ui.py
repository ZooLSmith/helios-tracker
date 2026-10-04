"""Borderlands 1's ui: what differs from Borderlands 2's (games/bl2/ui.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.ui import Ui


class Bl1Ui(Ui):
    """Borderlands 1's ui."""

    def show_message(self, text: str, duration: float) -> None:
        # BL1's ui_utils (1.3) has no co-op message: its HUD one, which goes away by itself
        from ui_utils import show_hud_message  # noqa: PLC0415

        from ...i18n import t  # noqa: PLC0415

        show_hud_message(t("box.title"), text, duration)

    def hide_message(self) -> None:
        pass
