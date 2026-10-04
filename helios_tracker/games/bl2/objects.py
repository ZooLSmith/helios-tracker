"""Borderlands 2's objects (the base: every game's unless its profile has its own) - Interactive objects and pickups: behaviours, looted, exits, the missions they give, pickups at rest.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part


class Objects(Part):
    """Interactive objects and pickups: behaviours, looted, exits, the missions they give, pickups at rest."""

    def behaviors(self, definition: Any) -> list[Any]:
        """An interactive object definition's behaviours (inspector.explosion_info looks for a Behavior_Explode): its
        BehaviorProviderDefinition's BehaviorSequences[].BehaviorData2[].Behavior."""
        return [data.Behavior for seq in definition.BehaviorProviderDefinition.BehaviorSequences
                for data in seq.BehaviorData2 if data.Behavior is not None]

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

    def destination(self, io: Any) -> str:
        """The map an interactive object takes the player to ("" if none): BL2's exits are travel stations, named by the
        game ("Exit to ..." - collector._exit_text): none here."""
        return ""

    def directives(self, io: Any) -> list[Any]:
        """An interactive object's missions it gives / takes back ({MissionDefinition, bBeginsMission, bEndsMission}):
        its Directives' (a MissionDirectivesDefinition - the bounty board, tools/probes/probe_bounty.txt)."""
        directives = io.Directives  # (None: most objects - no mission to give or take back)
        return list(directives.MissionDirectives) if directives is not None else []

    def pickup_at_rest(self, get: Any) -> bool:
        """Whether a pickup has stopped moving (`get`: its util.reader): WillowPickup.bPickupAtRest - False while it
        tumbles or slides, True ~0.25-1 s after it fully stopped (tools/probes/probe_pickup_rest.txt: two drops, one
        sliding down a slope; .agent/notes.md "Pickups at rest"). Borderlands 1's the same (the probe there, 2026-10-04)."""
        return bool(get("bPickupAtRest"))
