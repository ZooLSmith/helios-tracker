"""Borderlands: The Pre-Sequel (.agent/presequel.md): Borderlands 2's profile, its own data and the few methods that differ."""

from typing import Any

from . import JUMPPADS, OXYGEN, profile
from .bl2 import Borderlands2
from .bl2.objects import Objects
from .bl2.skills import Skills


class TpsObjects(Objects):
    """The Pre-Sequel's objects: BL2's, its map exits' destination name, its oxygen system's objects."""

    def extra_fields(self, io: Any, definition: Any) -> dict[str, Any]:
        # by its definition's name: an air dome's bubble - its breathable area and whether it's on (its definition "_On"
        # either way: the name isn't the state) -, its generator (its button switches a dome on - its own state: none
        # that changes), an oxygen fissure (IO_OxygenCracks, _Large, _NoMesh: "Oxygen Source" - refills Oz kits)
        name = str(definition.Name)
        if "AirDome_Bubble" in name:
            return {"dome": dome} if (dome := self.dome(io)) else {}
        if "AirDome_Generator" in name:
            return {"dg": 1}
        if "OxygenCracks" in name:
            return {"o2": 1}
        return {}

    def dome(self, io: Any) -> list[int] | None:
        # an air dome bubble (IO_AirDome_Bubble_*): its CollisionComponent, a SphereComponent - Bounds.BoxExtent its
        # radius (1500 x the object's DrawScale), bAttached whether it's on (False until its generator's button is
        # pushed: tools/probes/probe_dome_state.txt); None without it
        from ..util import try_  # noqa: PLC0415

        comp = try_(lambda: io.CollisionComponent)
        radius = try_(lambda: float(comp.Bounds.BoxExtent.X), 0.0) if comp is not None else 0.0
        if radius <= 0:
            return None
        return [round(radius), 1 if try_(lambda: bool(comp.bAttached), False) else 0]

    def _destination_name(self, destination: Any) -> str:
        # its LevelTravelStationDefinition has no DisplayName (the page said "Map Exit"): StationDisplayName - "Pity's
        # Fall" for Outlands_P's exit (tools/probes/probe_exit_text.txt, 2026-10-04)
        return str(destination.StationDisplayName)


class TpsSkills(Skills):
    """The Pre-Sequel's skills: BL2's but their icons."""

    def icon(self, skill_def: Any) -> str:
        # with a SkillIconTextureName (BL2 has none), that texture in its movie's package: its DLC classes' skills all
        # share one movie ("SharedSkillIcons_Cro_Aurelia.SkillIcon-Aurelia", every icon an image of it), the name picks
        # theirs ("SkillIcon-Avalanche")
        movie = super().icon(skill_def)
        texture = str(skill_def.SkillIconTextureName or "")
        if movie and texture and texture.lower() != "none":
            return f"{movie.split('.')[0]}.{texture}"
        return movie


@profile("TPS")
class PreSequel(Borderlands2):
    """Borderlands: The Pre-Sequel (.agent/presequel.md)."""

    PARTS = {**Borderlands2.PARTS, "objects": TpsObjects, "skills": TpsSkills}
    key = "tps"
    gibbed_prefix = "BLOZ"
    features = Borderlands2.features | {OXYGEN, JUMPPADS}
