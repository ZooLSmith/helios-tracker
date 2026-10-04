"""Borderlands: The Pre-Sequel (.agent/presequel.md): Borderlands 2's profile, its own data."""

from . import JUMPPADS, OXYGEN, profile
from .bl2 import Borderlands2


@profile("TPS")
class PreSequel(Borderlands2):
    """Borderlands: The Pre-Sequel (.agent/presequel.md)."""

    key = "tps"
    gibbed_prefix = "BLOZ"
    features = Borderlands2.features | {OXYGEN, JUMPPADS}
