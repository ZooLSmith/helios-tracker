"""
Player skills (game thread): each player's action skill (ready / running / cooling down), their
timed passive effects (e.g. Locked and Loaded's buff) and melee skill cooldown - for the page's
Players list and player Info tab.

Verified in game (tools/probe_passives.txt, cooldown probes):
- pc.GetSkillManager() = the SkillEffectManager (one for everyone); its ActiveSkills = the running
  Skill instances: Definition (SkillDefinition: SkillName localized, SkillType SKILL_TYPE_Action /
  SKILL_TYPE_Passive, DurationType DURATION_Timed / DURATION_Infinite), SkillState (SKILL_Active),
  Duration, StartTime (world seconds), SkillInstigator (the player's controller).
  Time left = StartTime + Duration - WorldInfo.TimeSeconds. The action skill running is the
  SKILL_TYPE_Action instance (pc.ActionSkillTime didn't move for Gunzerking).
- pc.SkillCooldownPool.Data (CurrentValue, ConsumptionRate): the action skill's cooldown (the HUD
  bar's), GetSkillCooldownTime() its full length; MeleeSkillCooldownPool / GetMeleeSkillCooldownTime()
  the same for the melee skill. On the host, another player's pool reads empty
  (tools/probe_action_skill.txt): their cooldown = the full length from when their action skill was last
  seen running (the instance's Duration isn't its real length). pc.SavedSkillTreeSkill: the action skill's definition (seen: Gunzerking;
  on the host, another player's gave no name: their tree's SKILL_TYPE_Action skill then).
- Not unlocked yet (before the story gives it - Lv 1 in the Pre-Sequel, tools/probe_tps.txt): the tree's action skill
  has Grade 0 (1 once it's there: BL2's Gunzerking, Krieg's, tools/probe_skill_layout.txt) - its cooldown still reads
  a length and an empty pool: it looked "ready". No "ak" then.

Hidden helper skills: some timed effects run as a helper that no skill tree lists, with dev text
for a name (Krieg's Blood Overdrive runs "BloodOverdriveChild": "Blood Overdrive Child - If you are
reading this please bug it!"). The helper uses its skill's icon (skill_icon: unique per tree skill,
shared with its helpers - tools/probe_child_skill.txt): shown under that tree skill's name.
Nameless timed effects (an empty SkillName) - seen on a Pre-Sequel Lv 1 player: definitions a behaviour creates,
"GD_PlayerShared.Behaviors.PlayerBehavior_LevelUp:Behavior_AttributeEffect_1.SkillDefinition_2" (4 s, twice),
"...PlayerBehavior_LevelUpNaturally:...SkillDefinition_1" (30 s), "GD_JackCombatNPC.injured.JackInjuredDefinition:
Behavior_AttributeEffect_4.SkillDefinition_1" (15 s). Each definition's path logged once.

The manager is read once per pass (every SKILLS_EVERY s) for everyone; definitions are cached forever
(static game data); the full cooldown lengths are function calls, refreshed every MAX_EVERY s.
"""

from typing import Any

from unrealsdk.unreal import WeakPointer

from .util import def_name, field, log, try_

SKILLS_EVERY = 0.2  # s between reads of the skill manager (every player's running skills)
MAX_EVERY = 5.0  # s between reads of a player's full cooldown lengths (function calls)

# SkillDefinition address -> (localized name, SkillType name, DurationType name)
_defs: dict[int, tuple[str, str, str]] = {}
# Controller address -> (its tree's skill definition addresses, SkillIcon path -> tree skill name,
# the action skill's name): a skill tree's definitions never change (static per class)
_trees: dict[int, tuple[set[int], dict[str, str], str]] = {}
_unnamed: set[int] = set()  # nameless timed skills' definitions already logged


def skill_icon(skill_def: Any) -> str:
    """A skill's icon texture path, as the game's movies name it ("SharedSkillIcons_Soldier.SkillIcon-Able"; gameicons.py
    serves it): its SkillIcon movie's path - or, with a SkillIconTextureName (the Pre-Sequel's), that texture in the
    movie's package: its DLC classes' skills all share one movie ("SharedSkillIcons_Cro_Aurelia.SkillIcon-Aurelia",
    every icon an image of it), the name picks theirs ("SkillIcon-Avalanche"). "" without an icon."""
    movie = try_(lambda: skill_def.SkillIcon._path_name(), "") or ""
    texture = str(try_(lambda: skill_def.SkillIconTextureName, "") or "")
    if movie and texture and texture.lower() != "none":
        return f"{movie.split('.')[0]}.{texture}"
    return movie


def _tree_names(pc: Any) -> tuple[set[int], dict[str, str], str]:
    """The player's tree skills: their definitions, their names by icon, and the action skill's name
    (the tree's SKILL_TYPE_Action skill) - read once per controller (an empty tree: again next time)."""
    key = pc._get_address()
    if (cached := _trees.get(key)) is None:
        defs: set[int] = set()
        by_icon: dict[str, str] = {}
        action = ""
        for s in try_(lambda: list(pc.PlayerSkillTree.Skills), []) or []:
            d = try_(lambda s=s: s.Definition)
            if d is None:
                continue
            defs.add(d._get_address())
            name, kind, _ = definition_info(d)
            if kind == "SKILL_TYPE_Action" and not action:
                action = name
            icon = skill_icon(d)
            if icon and name:
                by_icon.setdefault(icon, name)
        cached = (defs, by_icon, action)
        if defs:
            _trees[key] = cached
    return cached


def _shown_name(skill_def: Any, name: str, pc: Any) -> str:
    """A tree skill's own name; a hidden helper's (not in the player's tree): the tree skill with its icon."""
    defs, by_icon, _ = _tree_names(pc)
    if not defs or skill_def._get_address() in defs:
        return name
    icon = skill_icon(skill_def)
    return by_icon.get(icon, name) if icon else name


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
        # controller address -> {"act": (name, left, duration) | None, "timed": [(name, left, duration, made up)]}
        self._by_pc: dict[int, dict[str, Any]] = {}
        # controller address -> (next read, action skill full cooldown, melee full cooldown, action skill name,
        # whether it's still locked)
        self._max: dict[int, tuple[float, float, float, str, bool]] = {}
        self._world = 0.0  # the world time of the last update() call
        # controller address -> the world time their action skill was last seen running: the start of
        # its cooldown for the other players on the host, whose cooldown pool reads empty
        self._act_seen: dict[int, float] = {}
        self._local = 0  # the local controller's address

    def update(self, pc: Any, world_time: float, now: float) -> None:
        """Every SKILLS_EVERY: every running timed skill, by player."""
        self._world = world_time
        self._local = try_(lambda: pc._get_address(), 0)
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
        # (field(): properties looked up once - ~10x cheaper than by name, see util.field)
        for skill in try_(lambda: list(field(manager, "ActiveSkills")), []) or []:
            skill_def = try_(lambda s=skill: field(s, "Definition"))
            if skill_def is None:
                continue
            name, kind, duration_type = definition_info(skill_def)
            if duration_type != "DURATION_Timed" or _enum_name(try_(lambda s=skill: field(s, "SkillState"))) != "SKILL_Active":
                continue
            duration = try_(lambda s=skill: float(field(s, "Duration")), 0.0)
            left = try_(lambda s=skill: float(field(s, "StartTime")), 0.0) + duration - world_time
            instigator = try_(lambda s=skill: field(s, "SkillInstigator"))
            if duration <= 0 or left <= 0 or instigator is None:
                continue
            entry = by_pc.setdefault(instigator._get_address(), {"act": None, "timed": []})
            if kind == "SKILL_TYPE_Action":
                entry["act"] = (name, left, duration)
                self._act_seen[instigator._get_address()] = world_time
            else:
                shown = try_(lambda d=skill_def, n=name, c=instigator: _shown_name(d, n, c), name)
                if not shown:  # no name of the game's: its object name, a guess
                    shown = try_(lambda d=skill_def: def_name(d), "") or "?"
                    if skill_def._get_address() not in _unnamed:
                        _unnamed.add(skill_def._get_address())
                        log(f"timed skill without a name: {try_(lambda d=skill_def: d._path_name(), shown)} ({duration:.1f} s)")
                    entry["timed"].append((shown, left, duration, True))
                else:
                    entry["timed"].append((shown, left, duration, False))
        self._by_pc = by_pc

    def player(self, pawn: Any, now: float) -> dict[str, Any]:
        """The payload fields for one player pawn: "ak" (action skill: ["r", name] ready, ["a", fraction
        left, seconds left, name] running, ["c", fraction left, seconds left, name] cooling down),
        "ps" (timed passive effects: [[name, seconds left, duration(, 1: a made-up name)]]), "mk" (melee skill cooling down:
        [fraction left, seconds left]). Empty without their controller (a co-op client only has its own)."""
        # (driving, the controller possesses the vehicle: the player pawn's own is None meanwhile)
        pc = try_(lambda: field(pawn, "Controller")) or try_(lambda: field(pawn, "DrivenVehicle").Controller)
        if pc is None or try_(lambda: field(pc, "SkillCooldownPool")) is None:
            return self._remote(pawn)
        key = pc._get_address()
        cached = self._max.get(key)
        if cached is None or now >= cached[0]:
            saved = try_(lambda: pc.SavedSkillTreeSkill)
            action_name = ""
            if saved is not None and definition_info(saved)[1] == "SKILL_TYPE_Action":
                action_name = definition_info(saved)[0]
            if not action_name:  # the host, another player: SavedSkillTreeSkill has no name - their tree's
                action_name = try_(lambda: _tree_names(pc)[2], "") or ""
            cached = (now + MAX_EVERY, try_(lambda: float(pc.GetSkillCooldownTime()), 0.0),
                      try_(lambda: float(pc.GetMeleeSkillCooldownTime()), 0.0), action_name, _action_locked(pc))
            self._max[key] = cached
        _, action_max, melee_max, action_name, locked = cached
        out: dict[str, Any] = {}
        running = self._by_pc.get(key, {})
        if (act := running.get("act")) is not None:
            name, left, duration = act
            out["ak"] = ["a", round(left / duration, 3), round(left, 1), name or action_name]
        elif action_max > 0 and not locked:
            left = _pool_seconds(try_(lambda: field(pc, "SkillCooldownPool").Data))
            if left[0] <= 0 and key != self._local and (ended := self._act_seen.get(key)) is not None:
                # another player on the host: their pool reads empty (tools/probe_action_skill.txt) -
                # the full cooldown from when their skill stopped running (its Duration isn't when:
                # Phaselock said 120 s, ended after 1 s)
                remaining = ended + action_max - self._world
                if ended > self._world:  # the world time restarted (a level load): long over
                    del self._act_seen[key]
                elif remaining > 0:
                    left = (remaining, round(remaining, 1))
            out["ak"] = ["c", round(min(1.0, left[0] / action_max), 3), left[1], action_name] if left[0] > 0 else ["r", action_name]
        if running.get("timed"):
            out["ps"] = [[name, round(left, 1), round(duration, 1), *([1] if raw else [])]
                         for name, left, duration, raw in running["timed"]]
        if melee_max > 0:
            left = _pool_seconds(try_(lambda: field(pc, "MeleeSkillCooldownPool").Data))
            if left[0] > 0:
                out["mk"] = [round(min(1.0, left[0] / melee_max), 3), left[1]]
        return out

    def _remote(self, pawn: Any) -> dict[str, Any]:
        """Another player on a co-op client (no controller): only when they last used their action
        skill - the pawn's replicated NextActionSkillActiveAbilityTime, set to the world time of each
        use (seen in game, tools/probe_coop_skill.py; not when it's ready again: no duration or cooldown
        reaches a client). -> {"ak": ["u", seconds ago]}, nothing if never used here."""
        used = try_(lambda: float(field(pawn, "NextActionSkillActiveAbilityTime")), 0.0)
        if used <= 0 or used > self._world:
            return {}
        return {"ak": ["u", round(self._world - used)]}

    def forget(self, keep: set[int]) -> None:
        """Drops the cooldown lengths (and last action skill runs) of controllers that are gone."""
        self._max = {k: v for k, v in self._max.items() if k in keep}
        self._act_seen = {k: v for k, v in self._act_seen.items() if k in keep}


def _action_locked(pc: Any) -> bool:
    """Whether the player's action skill isn't unlocked yet: its tree's SKILL_TYPE_Action skill at Grade 0 (a grade that
    doesn't read: unlocked, as before)."""
    for s in try_(lambda: list(pc.PlayerSkillTree.Skills), []) or []:
        d = try_(lambda s=s: s.Definition)
        if d is not None and definition_info(d)[1] == "SKILL_TYPE_Action":
            return try_(lambda s=s: int(s.Grade), None) == 0
    return False


def _pool_seconds(pool: Any) -> tuple[float, float]:
    """(the pool's value, seconds until empty at its drain rate) - the HUD bar's numbers."""
    value = try_(lambda: float(field(pool, "CurrentValue")), 0.0)
    rate = try_(lambda: float(field(pool, "ConsumptionRate")), 1.0) or 1.0
    return value, round(value / rate, 1) if value > 0 else 0.0
