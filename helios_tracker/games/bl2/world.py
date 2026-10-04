"""Borderlands 2's world (the base: every game's unless its profile has its own) - The level and the world: its map's name and key, whether it's paused, its map's source, its level names.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part


class World(Part):
    """The level and the world: its map's name and key, whether it's paused, its map's source, its level names."""

    def map_name(self, wi: Any) -> str:
        """The persistent level's map name ("Sanctuary_P"), from the world info."""
        return str(wi.GetStreamingPersistentMapName())

    def paused(self, wi: Any) -> bool:
        """Whether the game's world stands still (its menu): WorldInfo.Pauser set. (Not every clock: shops.py.)"""
        return wi.Pauser is not None

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        """A map's name as the game shows it, from one of its level lists (a LevelDependencyList: the base game's
        GD_Globals.General.LevelList, one per DLC - each knowing only its own maps), "" if it doesn't know it."""
        return str(level_list.GetFriendlyLevelNameFromMapName(map_name))

    def level_key(self, wi: Any, map_name: str) -> tuple:
        """What tells levels apart, read every second (cheap): another one = a new level."""
        from ... import levelmap  # noqa: PLC0415

        return map_name, levelmap.tactical_key(wi)

    def map_source(self, wi: Any, map_name: str) -> Any:
        """The level's map (levelmap.MapSource: its placement, how its images load), None without one - at a level
        change, on the game thread."""
        from ... import levelmap  # noqa: PLC0415

        return levelmap.tactical(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        """ClientPlayBinkMovie's arguments: whether the video can't be skipped."""
        return bool(args.bForceNoSkip)
