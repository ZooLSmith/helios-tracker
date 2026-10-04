"""Borderlands 1's world: what differs from Borderlands 2's (games/bl2/world.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.world import World


class Bl1World(World):
    """Borderlands 1's world."""

    def map_name(self, wi: Any) -> str:
        # The world is "Loader" in every area (tools/probes/probe_bl1.txt): the area is streamed in, the first of its
        # StreamingLevels - a LevelStreamingPersistent ('arid_p'), the others its sublevels (LevelStreamingKismet). No
        # GetStreamingPersistentMapName (AttributeError). None streamed in (the main menu): the world's own package,
        # its path's first part ("menumap.TheWorld:PersistentLevel.WorldInfo_0").
        for level in wi.StreamingLevels:
            if level is not None and level.Class.Name == "LevelStreamingPersistent":
                return str(level.PackageName)
        return wi._path_name().split(".", 1)[0]

    def paused(self, wi: Any) -> bool:
        # The escape menu sets Pauser; the status menus (inventory, map, skills...) don't - they set
        # WorldInfo.bStatusMenuOnly, the world stopped all the same (tools/probes/probe_bl1_pause.txt) - but not the
        # shops' timer (the user): shops.py keeps Pauser
        return wi.Pauser is not None or bool(wi.bStatusMenuOnly)

    def level_name_in(self, level_list: Any, map_name: str) -> str:
        # its lists' entries, read as properties: {PersistentMap 'arid_p', LevelName 'Arid Badlands' (the game's text,
        # localized)...} - gd_globals.General.LevelList, offline (.agent/bl1.md "Level names")
        want = map_name.lower()
        return next((str(entry.LevelName) for entry in level_list.LevelList if str(entry.PersistentMap).lower() == want), "")

    def level_key(self, wi: Any, map_name: str) -> tuple:
        return (map_name,)  # (one map anchor per area: found at the change - levelmap.landmark)

    def map_source(self, wi: Any, map_name: str) -> Any:
        from ... import levelmap  # noqa: PLC0415

        return levelmap.landmark(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        return False  # no bForceNoSkip argument (the log: AttributeError)
