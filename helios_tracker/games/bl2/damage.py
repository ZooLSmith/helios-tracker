"""Borderlands 2's damage (the base: every game's unless its profile has its own) - Damage: the functions the damage log
hooks, a hit read off the game's pipeline, an effect's start and end, who a hit's party counts as (notes.md "Damage:
where a hit can be read": probe_damage.py, probe_status_effect.py, probe_damage_lean.py - BL2, a host)."""

from typing import Any

from ...util import field as _field  # (at module level: read in every hit - util imports no SDK, no games)
from ..base import Part

# A hit's kind (hit()'s last value)
NORMAL, TICK, FLOOD = 0, 1, 2


class Damage(Part):
    """The damage log's game side: what to hook, how a hit reads. Everything here runs inside the game's hooks - property
    reads only (util.field), no function calls, nothing named (damage.py names what's new at its tick)."""

    # (function, PRE, the log's role for it - damage.py _ROLES). One hook per function: each override calls its parent,
    # so the one hooked is the level every call passes through once (a hook on each = a hit 4 times - notes.md).
    HOOKS = (
        # a pawn's hit: its TakeDamage around it (what runs inside belongs to it: the call stack), read once the damage is
        # applied - the victim's ProcessDamageTakenSkillEvents (WillowPlayerPawn's its own: it doesn't call WillowPawn's)
        ("WillowGame.WillowPawn:TakeDamage", True, "open"),
        ("WillowGame.WillowPawn:TakeDamage", False, "close"),
        ("WillowGame.WillowPawn:ProcessDamageTakenSkillEvents", True, "read"),
        ("WillowGame.WillowPlayerPawn:ProcessDamageTakenSkillEvents", True, "read"),
        # an interactive object's (a barrel): no skill events - its TakeDamage's POST, the pipeline filled
        ("WillowGame.WillowInteractiveObject:TakeDamage", True, "object_open"),
        ("WillowGame.WillowInteractiveObject:TakeDamage", False, "object_close"),
        # the killing blow: Died runs inside the killing hit's TakeDamage (an AI pawn; a player never Dies - bled out)
        ("Engine.Pawn:Died", True, "died"),
        # an effect (a burn...): applied inside the hit that applied it (a splash's: after its TakeDamage - none then),
        # each application its own; its end
        ("WillowGame.StatusEffectsComponent:ApplyStatusEffect", True, "effect_start"),
        ("WillowGame.StatusEffectsComponent:OnStatusEffectEnd", True, "effect_end"),
        # a player: downed inside the hit that downed them, a second wind inside the kill that gave it, bled out, up
        ("WillowGame.WillowPawn:PlayInjured", True, "downed"),
        ("WillowGame.WillowPawn:ClientOnRevived", True, "second_wind"),
        ("WillowGame.WillowPawn:SetInjuredDeadState", True, "dead_state"),
        ("WillowGame.WillowPawn:GoFromInjuredToHealthy", True, "healthy"),
    )

    def __init__(self, profile: Any) -> None:
        super().__init__(profile)
        self._kinds: dict[int, int] = {}  # a damage source class's address -> its hits' kind (classes: static)
        self._classes: dict[str, Any] = {}

    def hooks(self) -> tuple[tuple[str, bool, str], ...]:
        """The functions hooked: (path, PRE, role) - the roles damage.py handles."""
        return self.HOOKS

    def hit(self, args: Any) -> tuple[Any, float, float, bool, Any, Any, int]:
        """A hit, off its `Pipeline` (a WillowDamagePipeline - reused for every hit: read in the call): (the instigator - a
        controller, health damage, shield damage, crit, the element - its WillowDamageTypeDefinition or None, the source
        class, its kind - NORMAL / TICK - an effect's / FLOOD - crushing, a hit every few tenths of a millisecond).
        The amounts are the game's before the health clamps them (a 50-health barrel: 97 taken)."""
        pipeline = _field(args, "Pipeline")
        summary = _field(pipeline, "DamageSummary")
        source = _field(pipeline, "DamageSource")
        return (_field(pipeline, "DamageInstigator"), float(_field(summary, "FinalDamage")),
                float(_field(summary, "DamageDealtToShields")), bool(_field(summary, "bWasCrit")),
                _field(pipeline, "DamageTypeDef"), source, self._kind(source))

    def _kind(self, source: Any) -> int:
        if source is None:
            return NORMAL
        key = source._get_address()
        kind = self._kinds.get(key)
        if kind is None:
            name = str(source.Name)  # (once per class)
            kind = self._kinds[key] = TICK if name == "WillowDmgSource_StatusEffect" else FLOOD if name == "DmgType_Crushed" else NORMAL
        return kind

    def causer(self, args: Any) -> Any:
        """What dealt it (TakeDamage's DamageCauser - the pipeline has none): a weapon, a grenade's or a firing mode's
        Behavior_Explode, a MeleeDefinition, a vehicle's weapon... None for some (run over, crushed)."""
        return _field(args, "DamageCauser")

    def object_killed(self, obj: Any) -> bool:
        """An interactive object destroyed (a barrel blown): its bHasBeenKilled - read before and after its hit."""
        return bool(_field(obj, "bHasBeenKilled"))

    def identity(self, obj: Any) -> Any:
        """What a hit's party counts as in the log (its id): a player - their controller (it outlives their pawn: a
        respawned player is the same one); an AI's controller - its pawn (None: the controller); anything else itself."""
        if obj.Class._inherits(self._cls("Controller")):
            if obj.Class._inherits(self._cls("PlayerController")):
                return obj
            return _field(obj, "Pawn") or obj
        if obj.Class._inherits(self._cls("WillowPlayerPawn")):
            return _field(obj, "Controller") or obj
        return obj

    def actor(self, identity: Any) -> Any:
        """The actor to name for an identity (a player's controller: their pawn now - None while they have none)."""
        if identity.Class._inherits(self._cls("Controller")):
            return _field(identity, "Pawn")
        return identity

    def effect_started(self, component: Any, args: Any) -> tuple[Any, Any, Any, Any]:
        """ApplyStatusEffect, on the victim's StatusEffectsComponent: (the victim - the component's Outer, the instigator,
        the causer, the StatusEffectDefinition)."""
        return (component.Outer, _field(args, "InstigatedBy"), _field(args, "DamageCauser"),
                _field(args, "StatusEffectDefinition"))

    def effect_ended(self, component: Any, args: Any) -> tuple[Any, Any, Any, Any]:
        """OnStatusEffectEnd(ASE): the same, off the active effect's struct (EventInstigator, DamageCauser...)."""
        ase = _field(args, "ASE")
        return (component.Outer, _field(ase, "EventInstigator"), _field(ase, "DamageCauser"),
                _field(ase, "StatusEffectDefinition"))

    def downed_by(self, args: Any) -> Any:
        """PlayInjured(Killer, ...): who downed them (a controller)."""
        return _field(args, "Killer")

    def dead_state_start(self, args: Any) -> bool:
        """SetInjuredDeadState(INJUREDDEAD_Start): a downed player bled out (their death - no Died for a player)."""
        value = _field(args, "InjuredDeadStateVal")
        return getattr(value, "name", value) == "INJUREDDEAD_Start"

    def _cls(self, name: str) -> Any:
        cls = self._classes.get(name)
        if cls is None:
            import unrealsdk  # noqa: PLC0415

            cls = self._classes[name] = unrealsdk.find_class(name)
        return cls
