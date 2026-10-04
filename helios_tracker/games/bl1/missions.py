"""Borderlands 1's missions: what differs from Borderlands 2's (games/bl2/missions.py) - .agent/bl1.md.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..bl2.missions import Missions


class _NotPickedUp:
    """A Borderlands 1 mission not in the player's log, read as a log entry not started (missions._live: Status,
    bHeardKickoff, no progress) - Bl1Missions.entries. Offered (the page's "kick", BL2's bHeardKickoff: its
    giver offered it): the game's word - it can be picked up now, the controller's GetMissionEligibility ME_Eligible
    (tools/probes/probe_bl1_tracker.txt: 16 of the 205 not picked up - T.K. Has More Work, each DLC's first...); read
    when asked (the log's full pass: not started ones)."""

    Status = "MS_NotStarted"
    Objectives = ()

    def __init__(self, mission: Any, pc: Any, eligible: Any) -> None:
        self.MissionDef = mission
        self._pc = pc
        self._eligible = eligible  # (the profile's: once per mission while the log stays the same)

    @property
    def bHeardKickoff(self) -> bool:  # noqa: N802 - (the log entry's field it stands in for)
        return self._eligible(self._pc, self.MissionDef)


class Bl1Missions(Missions):
    """Borderlands 1's missions."""

    def __init__(self, profile: Any) -> None:
        super().__init__(profile)
        # The missions not picked up (mission_entries): rebuilt only when what they depend on changes - the playthrough,
        # the missions picked up and their statuses, the player's level (_mission_key); every call rebuilt them (~218,
        # 2026-10-04: missions 8-11 ms nearly every second). Their eligibility (a function call) read once per mission
        # while the key holds - the log's not started ones and the givers' "!" (mission_offered) alike.
        self._mission_key: tuple = ()
        self._not_picked: list[Any] = []
        self._eligible: dict[int, bool] = {}  # mission definition address -> GetMissionEligibility is ME_Eligible
        self._missions: list[Any] = []  # every MissionDefinition loaded (_mission_definitions)

    def entries(self, tracker: Any) -> Any:
        # The tracker's MissionList is bare definitions (its active one): the player's own, per playthrough -
        # WillowPlayerController.MissionPlaythroughData[] = MissionPlaythroughInfo {PlayThroughNumber, ActiveMission,
        # MissionList: [{MissionDef, Status, Objectives: [{StatId, CurrentAmount}]}]} - the one of the playthrough
        # played (WillowGameReplicationInfo.HostCurrentPlaythrough: the array's entries all said PlayThroughNumber 0 -
        # tools/probes/probe_bl1_missions.txt). Only the missions the player has picked up: then every other mission
        # the game has loaded, not started (BL2's log lists the whole playthrough so) - every MissionDefinition is
        # loaded, the base game's and the DLCs' (tools/probes/probe_bl1_tracker.txt: 218), each as a _NotPickedUp.
        from mods_base import ENGINE, get_pc  # noqa: PLC0415

        pc = get_pc()
        playthrough = int(ENGINE.GetCurrentWorldInfo().GRI.HostCurrentPlaythrough)
        if playthrough >= len(pc.MissionPlaythroughData):  # empty for a moment as a save loads (the log, 2026-10-04)
            return None
        log = list(pc.MissionPlaythroughData[playthrough].MissionList)
        status = [(e.MissionDef._get_address(), int(e.Status)) for e in log if e.MissionDef is not None]
        key = (playthrough, tuple(status), int(pc.PlayerReplicationInfo.ExpLevel))
        if key != self._mission_key:  # (what eligibility depends on changed: dependencies done, minimum level)
            self._mission_key = key
            self._eligible = {}
            picked = {address for address, _ in status}
            self._not_picked = [_NotPickedUp(d, pc, self._eligible_for) for d in self._mission_definitions()
                                if d._get_address() not in picked]
        return log + self._not_picked

    def picked_entries(self, tracker: Any) -> Any:
        # its log only: the stand-ins for the missions not picked up (~218) can't be active - the markers went through
        # them all every second (2-3 ms)
        return [e for e in self.entries(tracker) or () if not isinstance(e, _NotPickedUp)]

    def _eligible_for(self, pc: Any, mission: Any) -> bool:
        """The controller's GetMissionEligibility(mission) is ME_Eligible - once per mission while the key holds."""
        key = mission._get_address()
        if (eligible := self._eligible.get(key)) is None:
            eligible = self._eligible[key] = getattr(pc.GetMissionEligibility(mission), "name", "") == "ME_Eligible"
        return eligible

    def _mission_definitions(self) -> list[Any]:
        """Every MissionDefinition loaded - a find_all (it walks every object): once, kept (static game data)."""
        import unrealsdk  # noqa: PLC0415

        if not self._missions:
            self._missions = [d for d in unrealsdk.find_all("MissionDefinition", exact=False) if not d.Name.startswith("Default__")]
        return self._missions

    def objectives(self, mdef: Any) -> list[tuple[int, Any]]:
        # Objectives[] = MissionObjectiveData structs {StatId, ObjectiveCount, ProgressMessage}: keyed by their index
        return list(enumerate(mdef.Objectives))

    def progress(self, entry: Any) -> tuple[int, ...]:
        return tuple(int(o.CurrentAmount) for o in entry.Objectives)

    def status(self, entry: Any) -> str:
        # EMissionStatus: NotStarted, Active, ReadyToTurnIn, Complete, Redeemed - turned in: Redeemed (every done one
        # in the probe); Complete, BL2's "done", too
        name = str(getattr(entry.Status, "name", entry.Status)).removeprefix("MS_")
        return "Complete" if name in ("Complete", "Redeemed") else name

    def number(self, mdef: Any) -> int:
        return int(mdef.PlotMissionNumber)

    def home(self, mdef: Any) -> dict[str, str] | None:
        # No TravelStation (every mission fell in the page's "other" - the user): its waypoints' level - where it's
        # handed in (TurnInWaypointDefinition: usually its giver - T.K. Has More Work's WP_Al), else where it's done
        # (TargetWaypointDefinition) - their PersistentLevelName, named as the map's title is (the level lists' text:
        # collector.level_name). Its GameStageRegion has no name of its own (gd_GameStages.Arid.Arid__A). None: no
        # waypoint, or a level no list knows.
        from ...collector import level_name  # noqa: PLC0415

        for waypoint in (mdef.TurnInWaypointDefinition, mdef.TargetWaypointDefinition):
            level = str(waypoint.PersistentLevelName) if waypoint is not None else ""
            if level and level.lower() != "none" and (name := level_name(level)):
                return {"a": name, "map": level}
        return None

    def offered(self, pc: Any, mission: Any, state: str, logged: bool) -> bool:
        # Its log has only the missions picked up (no "not started" ones): the game's own word - the controller's
        # GetMissionEligibility(mission) (script: its minimum level, dependencies, status) ME_Eligible, and not in the
        # log (a mission picked up is eligible too: the board's Bandit Presence, taken, ME_Eligible) - probe_bl1_givers:
        # the board's T.K. Has More Work, ME_Eligible, its AnnouncedMissions - the game's "!" (the user)
        # (once per mission while the log stays the same: _eligible_for - it was a call per giver mission per second)
        return not logged and self._eligible_for(pc, mission)

    def current_objectives(self, current: list[int], count: int) -> list[int]:
        return list(range(count))  # (no steps: all its objectives at once)

    def level_lookups(self, client: bool) -> list[str]:
        return ["waypoints", "exits"]  # (no waypoint components: its markers from the waypoint actors, and its exits)

    def markers(self, collector: Any, tracker: Any, active_addr: int | None) -> list[dict[str, Any]] | None:
        # the level's waypoint actors of its picked-up missions' waypoint definitions, the exits to other areas
        # (collector._waypoint_markers - to its own module with the rest of BL1's code: profiles.md step 5)
        return collector._waypoint_markers(tracker, active_addr)
