"""Borderlands 2's skills (the base: every game's unless its profile has its own) - The players' skill trees and action skill.
Moved from games.py (profiles.md step 4: a pure move)."""

from typing import Any

from ..base import Part


class Skills(Part):
    """The players' skill trees and action skill."""

    def icon(self, skill_def: Any) -> str:
        """A skill's icon texture path, as the game's movies name it ("SharedSkillIcons_Soldier.SkillIcon-Able":
        files/gameicons.py serves it), "" without one: its SkillIcon movie's path."""
        movie = skill_def.SkillIcon
        return str(movie._path_name()) if movie is not None else ""

    def read(self, ctrl: Any, player: dict[str, Any], bonuses: dict[str, Any]) -> None:
        """A player's skill tree into their record ("skills": trees -> tiers -> cells, "skillPoints"): BL2's PlayerSkillTree
        (inspector._skills)."""
        from ...inspector import _skills  # noqa: PLC0415

        _skills(ctrl, player, bonuses)

    def action_locked(self, pc: Any) -> bool:
        """Whether the player's action skill isn't unlocked yet (its cooldown then reads "ready"): BL2's tree's
        SKILL_TYPE_Action skill at Grade 0 (skills._action_locked)."""
        from ...skills import _action_locked  # noqa: PLC0415

        return _action_locked(pc)
