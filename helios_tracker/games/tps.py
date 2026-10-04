"""Borderlands: The Pre-Sequel (.agent/presequel.md): Borderlands 2's profile, its own data."""

from typing import Any

from . import JUMPPADS, OXYGEN, profile
from .bl2 import Borderlands2
from .bl2.objects import Objects


class TpsObjects(Objects):
    """The Pre-Sequel's objects: BL2's but its map exits' destination name."""

    def _destination_name(self, destination: Any) -> str:
        # its LevelTravelStationDefinition has no DisplayName (the page said "Map Exit"): StationDisplayName - "Pity's
        # Fall" for Outlands_P's exit (tools/probes/probe_exit_text.txt, 2026-10-04)
        return str(destination.StationDisplayName)


@profile("TPS")
class PreSequel(Borderlands2):
    """Borderlands: The Pre-Sequel (.agent/presequel.md)."""

    PARTS = {**Borderlands2.PARTS, "objects": TpsObjects}
    key = "tps"
    gibbed_prefix = "BLOZ"
    features = Borderlands2.features | {OXYGEN, JUMPPADS}
