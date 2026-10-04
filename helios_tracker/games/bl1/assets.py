"""Borderlands 1's assets: what differs from Borderlands 2's (games/bl2/assets.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.assets import Assets

BL1_CARD_KINDS = ("manufacturer", "type", "element")  # its card icons read (Borderlands1.card_icon_png)


class Bl1Assets(Assets):
    """Borderlands 1's assets."""

    def card_icon_png(self, kind: str, key: str) -> bytes | None:
        # No files scan (its packages: version 584): its movies' sprites, drawn - the manufacturers' from its card's
        # movie (bl1map.card_icon), the type's: the item's icon, the menus' (bl1map.item_icon - not its card's
        # "zippy" art, a Claptrap holding it: the user); its elements' (frames "fire0".."shock4": the element and its
        # tech level, x2 / x4 drawn) not read yet
        from ... import bl1map, gamecards, gamedir  # noqa: PLC0415

        cooked = gamedir.cooked_dir()
        if kind not in BL1_CARD_KINDS or cooked is None:
            return None
        if kind == "type":
            return bl1map.item_icon_png(cooked, key)
        if kind == "element":
            return bl1map.element_icon_png(cooked, key)
        return bl1map.card_icon_png(cooked, gamecards.keys(kind), key)

    def card_icons_ready(self) -> bool:
        # (the movie read on demand: once the keys are known - the first players' read; the elements need none)
        from ... import gamecards  # noqa: PLC0415

        return all(gamecards.keys(kind) for kind in BL1_CARD_KINDS if kind != "element")

    def job(self, boot: bool) -> Any:
        # Its fonts at boot: Packages/Fonts/Fonts_en.upk's movie (bl1fonts.py: DefineFont3 - WillowBody, WillowHead,
        # Brush Script Std) - a few headers; no scan finds them (its packages: version 584 - the page had no WillowBody,
        # /font 404s); its card / menu icons read on demand (card_icon_png)
        if not boot:
            return None
        from ... import bl1fonts, gamefonts  # noqa: PLC0415
        from ...gamedir import cooked_dir  # noqa: PLC0415
        from ...util import log, log_error  # noqa: PLC0415

        def fonts() -> None:
            try:
                gamefonts.set_catalogue(bl1fonts.catalogue(cooked_dir()))
                log(f"game fonts: {', '.join(gamefonts.FONTS.names()) or 'none'}")
            except Exception as ex:  # noqa: BLE001
                log_error("game fonts", ex)

        return fonts

    def wait_for(self, path: str, timeout: float) -> None:
        # (its fonts' catalogue: read as the mod starts - its icons read on demand, nothing to wait for)
        from ... import gamefonts  # noqa: PLC0415

        if path.startswith("/font/"):
            gamefonts.FONTS.wait(timeout)
