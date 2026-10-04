"""Tiny Tina's Assault on Dragon Keep, the standalone: Borderlands 2's engine and data - its profile, its own data."""

from . import profile
from .bl2 import Borderlands2


@profile("AoDK")
class DragonKeep(Borderlands2):
    """Tiny Tina's Assault on Dragon Keep, the standalone: BL2's engine and data."""

    key = "aodk"
    gibbed_prefix = ""  # no Gibbed editor for it
