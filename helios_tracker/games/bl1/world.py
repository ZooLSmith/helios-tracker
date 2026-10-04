"""Borderlands 1's world: what differs from Borderlands 2's (games/bl2/world.py) - .agent/bl1.md."""

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
        return (map_name,)  # (one map anchor per area: found at the change - _landmark)

    def map_source(self, wi: Any, map_name: str) -> Any:
        return _landmark(wi, map_name)

    def movie_no_skip(self, args: Any) -> bool:
        return False  # no bForceNoSkip argument (the log: AttributeError)


def _landmark(wi: Any, map_name: str) -> Any:
    """The area's map: its anchor (one LevelLandmarkAnchor per area, in its persistent level - tools/probes/probe_bl1.txt:
    arid_p's: the placement, its map frame) and the menu movie's vector frame rendered (bl1map.py) - a find_all, at a
    level change only."""
    import unrealsdk  # noqa: PLC0415

    from ... import gamedir, levelmap  # noqa: PLC0415
    from .files import bl1map  # noqa: PLC0415
    from ...util import log, try_  # noqa: PLC0415

    prefix = map_name.lower() + "."
    anchor = next((a for a in unrealsdk.find_all("LevelLandmarkAnchor", exact=True)
                   if a._path_name().lower().startswith(prefix)), None)
    if anchor is None:
        log(f"no map for {map_name}: no LevelLandmarkAnchor in it")
        return None
    scale = anchor.DrawScale
    yaw = int(anchor.Rotation.Yaw)
    # a half turn: the texture's quad turned 180 degrees = its scale's two signs flipped (the Underdome lobby's anchor:
    # 179.5 degrees, DrawScale3D -7.0 - upright, as the game draws it); other turns: placed unturned (the page's map
    # doesn't turn - bl1map.placement)
    half_turn = abs(abs(yaw % 65536 - 32768)) <= 182
    flip = -1.0 if half_turn else 1.0
    dlc_map = anchor.DLCMap
    numbers = bl1map.Anchor(str(anchor.MapFrame), anchor.Location.X, anchor.Location.Y, yaw,
                            flip * scale * anchor.DrawScale3D.X, flip * scale * anchor.DrawScale3D.Y,
                            anchor.TextureSizeX, anchor.TextureSizeY, dlc_map._path_name() if dlc_map is not None else "")
    if not half_turn and abs(((yaw + 32768) % 65536) - 32768) > 182:  # (1 degree)
        log(f"map anchor of {map_name} turned {yaw * 360 / 65536:.1f} degrees: its map placed unturned")
    cooked = gamedir.cooked_dir()

    def load() -> Any:  # (a levelmap.MapResult)
        if cooked is None:
            raise FileNotFoundError("couldn't find the game's WillowGame/CookedPC")
        images = bl1map.load_map(cooked, numbers.frame, numbers.dlc_map)  # (a DLC area's: its own movie)
        if not images:
            return levelmap.MapResult([])
        x0, x1, y0, y1 = images[0].bounds
        center, upp = bl1map.placement(numbers, (x1 - x0, y1 - y0))
        return levelmap.MapResult(images, None, {"center": center, "upp": upp})

    return levelmap.MapSource(anchor._path_name(), {"killz": try_(lambda: round(wi.KillZ))}, load)
