"""Borderlands 2's objects (the base: every game's unless its profile has its own) - Interactive objects and pickups: behaviours, looted, exits, the missions they give, pickups at rest.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part


class Objects(Part):
    """Interactive objects and pickups: behaviours, looted, exits, the missions they give, pickups at rest."""

    def behaviors(self, definition: Any) -> list[Any]:
        """An interactive object definition's behaviours (inspector.explosion_info looks for a Behavior_Explode): its
        BehaviorProviderDefinition's BehaviorSequences[].BehaviorData2[].Behavior - none without a provider (some of
        the Pre-Sequel's objects: not a failure)."""
        provider = definition.BehaviorProviderDefinition
        if provider is None:
            return []
        return [data.Behavior for seq in provider.BehaviorSequences for data in seq.BehaviorData2 if data.Behavior is not None]

    def exit_text(self, station: Any) -> str:
        """A map exit's name as the game shows it ("Exit to Frostburn Canyon"), "" if it isn't one / has none: the
        station's LevelTravelMapDisplayName ("Exit to %s") with its TravelDefinition's destination's DisplayName, in the
        game's language. Also a mission waypoint on a map exit (the objective in another map: a
        LevelTransitionWaypointComponent on a LevelTravelStation - no objective of its own, no WaypointInfo:
        tools/probes/probe_waypoint_exit.txt)."""
        from ...util import try_  # noqa: PLC0415

        text = try_(lambda: str(station.LevelTravelMapDisplayName), "") or ""
        dest = try_(lambda: str(self._destination_name(station.TravelDefinition.DestinationStationDefinition)), "") or ""
        if not text or not dest:
            return ""
        return text.replace("%s", dest) if "%s" in text else f"{text} {dest}"

    def _destination_name(self, destination: Any) -> str:
        """A travel station definition's name for its map exits: BL2's DisplayName."""
        return str(destination.DisplayName)

    def is_looted(self, io: Any, client: bool) -> bool:
        """A container looted: opened, and no longer usable (bCanBeUsed[0] 1 -> 0). Opened: its SimpleAnimState is a
        bitmask over its animations (SimpleAnimInfo[].AnimName - tools/probes/probe_prelooted.txt: Open, Open_Vacuum,
        Opened(_Idle), Closed(_Idle)), the "Opened..." one's bit set: closed 8 (Closed), just opened 14, looted and the
        level reloaded 12, spawned looted 4 (Opened alone), BL2's 7 - the state 7 alone (the first rule) missed all but
        the last. Without an "Opened" animation: the state 7. A co-op client (tools/probes/probe_client_containers.txt):
        the state (replicated) but bCanBeUsed stays 1 - it isn't sent: the state alone there."""
        from ...util import try_  # noqa: PLC0415

        state = try_(lambda: int(io.SimpleAnimState), 0)
        anims = [try_(lambda a=a: str(a.AnimName), "") for a in try_(lambda: list(io.SimpleAnimInfo), []) or []]
        opened_bits = [n for n, name in enumerate(anims) if name.lower().startswith("opened")]
        opened = any(state >> n & 1 for n in opened_bits) if opened_bits else state == 7
        return opened and (client or not try_(lambda: io.bCanBeUsed[0], 1))

    def extra_fields(self, io: Any, definition: Any) -> dict[str, Any]:
        """An object's record fields for a system only some games have (an air dome's "dome": [radius, on] - re-read
        with dome(); its generator "dg", an oxygen source "o2"): none here."""
        return {}

    def dome(self, io: Any) -> list[int] | None:
        """An air dome bubble's [radius (uu), 1 on / 0 off] now (a record whose extra_fields had "dome"): none here."""
        return None

    def exit(self, io: Any) -> tuple[str, str]:
        """A map exit's names (an object taking the player to another map): (the game's text for it - "Exit to Frostburn
        Canyon" -, the area it leads to as the game names it - the page words that "Exit to <area>"); ("", "") if it
        isn't one. BL2's exits are travel stations, their text the game's (exit_text)."""
        return self.exit_text(io), ""

    def directives(self, io: Any) -> list[Any]:
        """An interactive object's missions it gives / takes back ({MissionDefinition, bBeginsMission, bEndsMission}):
        its Directives' (a MissionDirectivesDefinition - the bounty board, tools/probes/probe_bounty.txt)."""
        directives = io.Directives  # (None: most objects - no mission to give or take back)
        return list(directives.MissionDirectives) if directives is not None else []

    def pickup_at_rest(self, get: Any) -> bool:
        """Whether a pickup has stopped moving (`get`: its util.reader): WillowPickup.bPickupAtRest - False while it
        tumbles or slides, True ~0.25-1 s after it fully stopped (tools/probes/probe_pickup_rest.txt: two drops, one
        sliding down a slope; .agent/notes.md "Pickups at rest")."""
        return bool(get("bPickupAtRest"))
