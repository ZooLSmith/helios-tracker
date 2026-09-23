"""
Player skills (game thread): each player's action skill (ready / running / cooling down), their
timed passive effects (e.g. Locked and Loaded's buff) and melee skill cooldown - for the page's
Players list and player Info tab.

Verified in game (tools/probe_passives.txt, tools/probe_cooldown*.py via skill_timer):
- pc.GetSkillManager() = the SkillEffectManager (one for everyone); its ActiveSkills = the running
  Skill instances: Definition (SkillDefinition: SkillName localized, SkillType SKILL_TYPE_Action /
  SKILL_TYPE_Passive, DurationType DURATION_Timed / DURATION_Infinite), SkillState (SKILL_Active),
  Duration, StartTime (world seconds), SkillInstigator (the player's controller).
  Time left = StartTime + Duration - WorldInfo.TimeSeconds. The action skill running is the
  SKILL_TYPE_Action instance (pc.ActionSkillTime didn't move for Gunzerking).
- pc.SkillCooldownPool.Data (CurrentValue, ConsumptionRate): the action skill's cooldown (the HUD
  bar's), GetSkillCooldownTime() its full length; MeleeSkillCooldownPool / GetMeleeSkillCooldownTime()
  the same for the melee skill. pc.SavedSkillTreeSkill: the action skill's definition (seen: Gunzerking).

The manager is read once per pass (every SKILLS_EVERY s) for everyone; definitions are cached forever
(static game data); the full cooldown lengths are function calls, refreshed every MAX_EVERY s.
"""

from typing import Any

from unrealsdk.unreal import WeakPointer

from .util import try_

SKILLS_EVERY = 0.2  # s between reads of the skill manager (every player's running skills)
MAX_EVERY = 5.0  # s between reads of a player's full cooldown lengths (function calls)

# SkillDefinition address -> (localized name, SkillType name, DurationType name)
_defs: dict[int, tuple[str, str, str]] = {}


def _enum_name(value: Any) -> str:
    return str(getattr(value, "name", "") or "")


def definition_info(skill_def: Any) -> tuple[str, str, str]:
    """(name, type, duration type) of a skill definition, read once."""
    key = skill_def._get_address()
    if (info := _defs.get(key)) is None:
        info = _defs[key] = (
            try_(lambda: str(skill_def.SkillName), "") or "",
            _enum_name(try_(lambda: skill_def.SkillType)),
            _enum_name(try_(lambda: skill_def.DurationType)),
        )
    return info


class SkillReader:
    def __init__(self) -> None:
        self._manager: WeakPointer | None = None
        self._next = 0.0
        # controller address -> {"act": (name, left, duration) | None, "timed": [(name, left, duration)]}
        self._by_pc: dict[int, dict[str, Any]] = {}
        # controller address -> (next read, action skill full cooldown, melee full cooldown, action skill name)
        self._max: dict[int, tuple[float, float, float, str]] = {}

    def update(self, pc: Any, world_time: float, now: float) -> None:
        """Every SKILLS_EVERY: every running timed skill, by player."""
        if now < self._next:
            return
        self._next = now + SKILLS_EVERY
        manager = self._manager() if self._manager is not None else None
        if manager is None:
            manager = try_(lambda: pc.GetSkillManager())
            if manager is None:
                self._by_pc = {}
                return
            self._manager = WeakPointer(manager)
        by_pc: dict[int, dict[str, Any]] = {}
        for skill in try_(lambda: list(manager.ActiveSkills), []) or []:
            skill_def = try_(lambda s=skill: s.Definition)
            if skill_def is None:
                continue
            name, kind, duration_type = definition_info(skill_def)
            if duration_type != "DURATION_Timed" or _enum_name(try_(lambda s=skill: s.SkillState)) != "SKILL_Active":
                continue
            duration = try_(lambda s=skill: float(s.Duration), 0.0)
            left = try_(lambda s=skill: float(s.StartTime), 0.0) + duration - world_time
            instigator = try_(lambda s=skill: s.SkillInstigator)
            if duration <= 0 or left <= 0 or instigator is None:
                continue
            entry = by_pc.setdefault(instigator._get_address(), {"act": None, "timed": []})
            if kind == "SKILL_TYPE_Action":
                entry["act"] = (name, left, duration)
            else:
                entry["timed"].append((name, left, duration))
        self._by_pc = by_pc

    def player(self, pawn: Any, now: float) -> dict[str, Any]:
        """The payload fields for one player pawn: "ak" (action skill: ["r", name] ready, ["a", fraction
        left, seconds left, name] running, ["c", fraction left, seconds left, name] cooling down),
        "ps" (timed passive effects: [[name, seconds left, duration]]), "mk" (melee skill cooling down:
        [fraction left, seconds left]). Empty without their controller (a co-op client only has its own)."""
        pc = try_(lambda: pawn.Controller)
        if pc is None or not hasattr(pc, "SkillCooldownPool"):
            return {}
        key = pc._get_address()
        cached = self._max.get(key)
        if cached is None or now >= cached[0]:
            saved = try_(lambda: pc.SavedSkillTreeSkill)
            action_name = ""
            if saved is not None and definition_info(saved)[1] == "SKILL_TYPE_Action":
                action_name = definition_info(saved)[0]
            cached = (now + MAX_EVERY, try_(lambda: float(pc.GetSkillCooldownTime()), 0.0),
                      try_(lambda: float(pc.GetMeleeSkillCooldownTime()), 0.0), action_name)
            self._max[key] = cached
        _, action_max, melee_max, action_name = cached
        out: dict[str, Any] = {}
        running = self._by_pc.get(key, {})
        if (act := running.get("act")) is not None:
            name, left, duration = act
            out["ak"] = ["a", round(left / duration, 3), round(left, 1), name or action_name]
        elif action_max > 0:
            left = _pool_seconds(try_(lambda: pc.SkillCooldownPool.Data))
            out["ak"] = ["c", round(min(1.0, left[0] / action_max), 3), left[1], action_name] if left[0] > 0 else ["r", action_name]
        if running.get("timed"):
            out["ps"] = [[name, round(left, 1), round(duration, 1)] for name, left, duration in running["timed"]]
        if melee_max > 0:
            left = _pool_seconds(try_(lambda: pc.MeleeSkillCooldownPool.Data))
            if left[0] > 0:
                out["mk"] = [round(min(1.0, left[0] / melee_max), 3), left[1]]
        return out

    def forget(self, keep: set[int]) -> None:
        """Drops the cooldown lengths of controllers that are gone."""
        self._max = {k: v for k, v in self._max.items() if k in keep}


def _pool_seconds(pool: Any) -> tuple[float, float]:
    """(the pool's value, seconds until empty at its drain rate) - the HUD bar's numbers."""
    value = try_(lambda: float(pool.CurrentValue), 0.0)
    rate = try_(lambda: float(pool.ConsumptionRate), 1.0) or 1.0
    return value, round(value / rate, 1) if value > 0 else 0.0
