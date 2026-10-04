"""Borderlands 2's missions (the base: every game's unless its profile has its own) - The mission log: its entries, their statuses / objectives / progress, where a mission is, its markers."""

from typing import Any

from ..base import Part


class Missions(Part):
    """The mission log: its entries, their statuses / objectives / progress, where a mission is, its markers."""

    def objective_name(self, objective: Any) -> str:
        """An objective's own name, the guess when it has no text (an objective of objectives()): its definition's."""
        from ...util import def_name  # noqa: PLC0415

        return def_name(objective)

    def entries(self, tracker: Any) -> Any:
        """The playthrough's missions, each {MissionDef, Status, its progress...} (missions.py MissionLog): the
        tracker's MissionList - every mission of the game, not started ones too. None: not there yet (loading)."""
        return tracker.MissionList

    def picked_entries(self, tracker: Any) -> Any:
        """The mission entries that can be active (picked up) - what the markers look through each second (the caller
        keeps the Active / ReadyToTurnIn ones): BL2's log is every mission, as mission_entries."""
        return self.entries(tracker)

    def objectives(self, mdef: Any) -> list[tuple[int, Any]]:
        """A mission definition's objectives, in order: (its key - what objective_index maps to its index - , the
        objective: ProgressMessage, ObjectiveCount, bObjectiveIsOptional). ObjectiveDefs, keyed by address."""
        return [(o._get_address(), o) for o in mdef.ObjectiveDefs if o is not None]

    def progress(self, entry: Any) -> tuple[int, ...]:
        """A mission entry's count per objective (its definition's order): ObjectivesProgress."""
        return tuple(int(v) for v in entry.ObjectivesProgress)

    def status(self, entry: Any) -> str:
        """A mission entry's status, as the page names them (EMissionStatus without "MS_": Active, ReadyToTurnIn...)."""
        return str(getattr(entry.Status, "name", entry.Status)).removeprefix("MS_")

    def number(self, mdef: Any) -> int:
        """Its number in the story (the page's order)."""
        return int(mdef.MissionNumber)

    def home(self, mdef: Any) -> dict[str, str] | None:
        """A mission's area for the page ({"a": its name as the game shows it, "map": its map}): where its giver is -
        its TravelStation (missions.station: StationDisplayName, StationLevelName)."""
        from ...missions import station  # noqa: PLC0415

        return station(mdef.TravelStation)

    def offered(self, pc: Any, mission: Any, state: str, logged: bool) -> bool:
        """Whether a giver's mission can be picked up now (its "!"): the mission log's word (MissionLog.giver_states:
        not started, the missions it needs done) - `state` "begin"."""
        return state == "begin"

    def current_objectives(self, current: list[int], count: int) -> list[int]:
        """A mission's current objectives (their indexes) from its current step's (MissionLog: ActiveObjectiveSet +
        SubObjectiveSets): BL2's objectives come in steps - those."""
        return current

    # the last markers() call's time per part (s): the debug report's breakdown (assigned, never changed in place)
    marker_parts: dict[str, float] = {}

    def level_lookups(self, client: bool) -> dict[str, str]:
        """The level's actors to look up after an objects scan for the mission markers (collector._lookup, one a tick):
        name -> class; markers() gets them by name. BL2: its markers come from the tracker's waypoint components - but a
        co-op client has none: the level's waypoint actors then ("waypoints": collector._client_markers)."""
        return {"waypoints": "WillowWaypoint"} if client else {}

    def markers(self, actors: dict[str, list[Any]], tracker: Any, active_addr: int | None) -> list[dict[str, Any]] | None:
        """The mission markers when they don't come from the tracker's waypoint components (the collector reads those:
        BL2's - None here), from the level's actors (level_lookups': name -> [WeakPointer])."""
        return None
