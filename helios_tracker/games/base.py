"""A game's profile and its parts (games/__init__.py): what a game's profile holds - its data and one part per domain."""

from typing import Any


class Part:
    """One domain of a game's profile (world, missions...). Borderlands 2's parts are the base (bl2/); a game whose way
    differs subclasses the part (bl1/). The main code calls a part's methods and never names a game's class."""

    def __init__(self, profile: Any) -> None:
        self.profile = profile  # (its profile: another part's, if it ever needs one - self.profile.world...)

    def level_changed(self) -> None:
        """A new level: what this part keeps per level, forgotten (util.level_changed -> Profile.level_changed). None here."""


class Profile:
    """A game's profile: its data (key, packages, features... - a game's profile class sets them) and its parts, built
    from PARTS (part name -> part class): GAME.world, GAME.missions..."""

    PARTS: dict[str, type[Part]] = {}
    world: Any
    missions: Any
    items: Any
    objects: Any
    pawns: Any
    shops: Any
    skills: Any
    assets: Any
    ui: Any

    def __init__(self) -> None:
        self.parts: dict[str, Part] = {name: cls(self) for name, cls in self.PARTS.items()}
        for name, part in self.parts.items():
            setattr(self, name, part)

    def level_changed(self) -> None:
        """A new level (registered with util.on_level_change): each part's own reset."""
        for part in self.parts.values():
            part.level_changed()
