"""Borderlands 1's objects: what differs from Borderlands 2's (games/bl2/objects.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.objects import Objects

BL1_BEHAVIOR_ARRAYS = ("OnSpawn", "OnBehaviorSetEnabled", "OnBehaviorSetDisabled", "OnTouch", "OnUnTouch", "OnUsedBy",
                       "OnTakeDamage", "OnKilled")
BL1_REACTION_ARRAYS = ("CustomEvents", "TimerEvents", "CounterEvents")
MAP_CHANGE_STEPS = 8  # a map changer's event to its map change action: at most so many links (Borderlands1._destinations)


class Bl1Objects(Objects):
    """Borderlands 1's objects."""

    def __init__(self, profile: Any) -> None:
        super().__init__(profile)
        self._events_indexed = False  # the level's script events indexed (_events_by_origin) - forgotten per level
        self._events_by_origin: dict[int, list[Any]] = {}  # object address -> WeakPointers to the events it triggers
        self._destination_map: dict[int, str] = {}  # object address -> the map it changes to ("": none), worked out

    def behaviors(self, definition: Any) -> list[Any]:
        # No behaviour provider: behaviour sets - DefaultBehaviorSet and ExtraBehaviorSets[], InteractiveObjectBehaviorSet
        # (WillowGame.u, offline): event arrays of behaviours (OnKilled, OnTakeDamage...) and of reactions holding
        # Behaviors[] (CustomEvents, TimerEvents, CounterEvents). Its exploding barrels: a Behavior_Explode in them
        # (gd_Explosives.Barrels.ExplodingBarrel_Incendiary.Behavior_Explode_0)
        out: list[Any] = []
        for behavior_set in [definition.DefaultBehaviorSet, *definition.ExtraBehaviorSets]:
            for name in BL1_BEHAVIOR_ARRAYS:
                out += [b for b in getattr(behavior_set, name) if b is not None]
            for name in BL1_REACTION_ARRAYS:
                out += [b for reaction in getattr(behavior_set, name) for b in reaction.Behaviors if b is not None]
        return out

    def is_looted(self, io: Any, client: bool) -> bool:
        # No SimpleAnimState / SimpleAnimInfo (WillowGame.u, offline), its bCanBeUsed a flag (BL2's an array): looted
        # = no longer usable (tools/probes/probe_bl1_looted.txt: the looted containers False, a toilet not searched
        # yet True). (A co-op client's: not seen.)
        return not bool(io.bCanBeUsed)

    def exit(self, io: Any) -> tuple[str, str]:
        # its map changers have no text of their own: the area their level script takes the player to (_destination),
        # by the game's level lists
        from ...collector import level_name  # noqa: PLC0415

        destination = self._destination(io)
        return "", level_name(destination) if destination else ""

    def _destination(self, io: Any) -> str:
        # Its map changers (gd_MapChangeObjects.Default_MapChanger, Vehicle_MapChanger_Arid: "Map Changer ?" on the
        # page - the user) have no destination of their own: the level's script has it - an event of theirs (a
        # SeqEvent_Used / SeqEvent_Touch whose Originator is the changer) leads to a
        # WillowSeqAct_PrepareMapChangeFromDefinition, its DefaultMap the map (W_Arid_P.umap, offline: 6 of them -
        # Dry_P, Arid_SkagGully_P, Arid_Mine_P, interlude_1_p - the vehicle's -, Arid_Arena_Coliseum_P, Arid_Cave_P).
        # The events indexed once per area (_events_by_origin), followed for the objects asked about only (the whole
        # script followed at once: 151 ms in one record - 2026-10-04).
        key = io._get_address()
        if not self._events_indexed:
            self._index_events()
        elif (found := self._destination_map.get(key)) is not None:
            return found
        found = ""
        for ptr in self._events_by_origin.get(key, []):
            if (event := ptr()) is not None and (found := self._map_change_from(event)):
                break
        self._destination_map[key] = found
        return found

    def level_changed(self) -> None:
        # (the level's script events and the exits worked out from them: a level's - by the area's name they once
        # outlived a save-quit-continue in the same area, the old addresses kept)
        self._events_indexed, self._events_by_origin, self._destination_map = False, {}, {}

    def _index_events(self) -> None:
        """The level's script events by who triggers them: every event's Originator (a find_all and a property read
        each), its object's address -> the event - once per level (level_changed)."""
        import unrealsdk  # noqa: PLC0415
        from unrealsdk.unreal import WeakPointer  # noqa: PLC0415

        from ...util import field  # noqa: PLC0415

        index: dict[int, list[Any]] = {}
        for event in unrealsdk.find_all("SequenceEvent", exact=False):
            if event.Name.startswith("Default__") or (origin := field(event, "Originator")) is None:
                continue
            index.setdefault(origin._get_address(), []).append(WeakPointer(event))
        self._events_indexed, self._events_by_origin, self._destination_map = True, index, {}

    def _map_change_from(self, event: Any) -> str:
        """The DefaultMap an event's output links reach (a few steps: gates, delays between), "" if none."""
        from ...util import field  # noqa: PLC0415

        queue, seen = [(event, 0)], set()
        while queue:
            op, depth = queue.pop(0)
            if op is None or op._get_address() in seen or depth > MAP_CHANGE_STEPS:
                continue
            seen.add(op._get_address())
            if op.Class.Name == "WillowSeqAct_PrepareMapChangeFromDefinition" and (to := str(field(op, "DefaultMap"))) not in ("", "None"):
                return to
            for output in field(op, "OutputLinks"):
                queue += [(link.LinkedOp, depth + 1) for link in output.Links]
        return ""

    def directives(self, io: Any) -> list[Any]:
        # On the object itself: WillowInteractiveObject.MissionDirectives (tools/probes/probe_bl1_givers.txt: the bounty
        # board's 15, Dr. Zed's 11 - a WillowInteractiveNPC, an interactive object) - no Directives
        return list(io.MissionDirectives)
