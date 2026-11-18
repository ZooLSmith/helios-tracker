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
        # a heal (notes.md "Healing": an ally's hit converted to healing - a TakeDamage, HealDamage inside it, its
        # FinalDamage the health given back): the hit marked a heal, not damage
        ("WillowGame.WillowPawn:HealDamage", True, "healed"),
    )

    def __init__(self, profile: Any) -> None:
        super().__init__(profile)
        self._kinds: dict[int, int] = {}  # a damage source class's address -> its hits' kind (classes: static)
        self._areas: dict[int, bool] = {}  # a causer class's address -> a damage area (classes: static)
        self._projectiles: dict[int, bool] = {}  # a causer class's address -> a projectile (classes: static)
        self._classes: dict[str, Any] = {}

    def hooks(self) -> tuple[tuple[str, bool, str], ...]:
        """The functions hooked: (path, PRE, role) - the roles damage.py handles."""
        return self.HOOKS

    def hit(self, args: Any) -> tuple[Any, float, float, bool, Any, Any, int, float, float]:
        """A hit, off its `Pipeline` (a WillowDamagePipeline - reused for every hit: read in the call): (the instigator - a
        controller, health damage, shield damage, crit, the element - its WillowDamageTypeDefinition or None, the source
        class, its kind - NORMAL / TICK - an effect's / FLOOD - crushing, a hit every few tenths of a millisecond, the
        health before it, the amplified share - below).
        The amounts are the game's before the health clamps them (a 50-health barrel: 97 taken): the health before it
        (PreviousHealth) says how much of it was overkill.
        The amplified share: slag's bonus over the hit's base and that bonus (notes.md "Slag": ExtraDamageDealtDueToAmplify
        is slag's, 0 on a target not slagged, = InitialDamage - +100 % - on one slagged). The game applies the other
        steps (crit, surface...) to the slagged amount, one after the other: the bonus's share of the hit is that ratio of
        its final amounts (0.5) - 0 without a bonus."""
        pipeline = _field(args, "Pipeline")
        summary = _field(pipeline, "DamageSummary")
        source = _field(pipeline, "DamageSource")
        extra = float(_field(summary, "ExtraDamageDealtDueToAmplify"))
        base = float(_field(summary, "InitialDamage"))
        share = extra / (base + extra) if extra > 0 and base + extra > 0 else 0.0
        return (_field(pipeline, "DamageInstigator"), float(_field(summary, "FinalDamage")),
                float(_field(summary, "DamageDealtToShields")), bool(_field(summary, "bWasCrit")),
                _field(pipeline, "DamageTypeDef"), source, self._kind(source), float(_field(summary, "PreviousHealth")),
                share)

    def amplifiers(self, victim: Any) -> list[Any]:
        """Who slagged `victim` (read only for a hit with an amplified share): the instigators (controllers) of the slag
        effects running on it - its StatusEffectComp's ActiveStatusEffects whose definition's StatusEffectType is
        STATUS_EFFECT_Amp (Startup.upk's GD_Amp.StatusEffect.Status_Amp; notes.md "Slag": re-applied by the same player it
        refreshes - one entry -, by two players not seen yet). A pawn's only: an interactive object's effects not probed
        (none: its bonus stays its shooter's)."""
        if not victim.Class._inherits(self._cls("WillowPawn")):
            return []
        out = []
        for ase in _field(_field(victim, "StatusEffectComp"), "ActiveStatusEffects"):
            definition = _field(ase, "StatusEffectDefinition")
            kind = _field(definition, "StatusEffectType") if definition is not None else None
            if getattr(kind, "name", kind) == "STATUS_EFFECT_Amp":
                out.append(_field(ase, "EventInstigator"))
        return out

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
        Behavior_Explode, a MeleeDefinition, a vehicle's weapon... None for some (run over, crushed).
        A projectile (a rocket, a Dahl rifle's grenade, an enemy's spore bomb) is a new object each shot - one entry per
        shot, the user saw "Projectile 1", "Projectile 98": its weapon instead, its Owner when that's an Inventory (a
        player's - probe_projectile.py), else its Definition (a ProjectileDefinition: shared by every shot of its kind -
        an enemy's)."""
        causer = _field(args, "DamageCauser")
        if causer is None or not self._is_projectile(causer):
            return causer
        owner = _field(causer, "Owner")
        if owner is not None and owner.Class._inherits(self._cls("Inventory")):
            return owner
        return _field(causer, "Definition") or causer

    def _is_projectile(self, obj: Any) -> bool:
        key = obj.Class._get_address()
        found = self._projectiles.get(key)
        if found is None:
            found = self._projectiles[key] = bool(obj.Class._inherits(self._cls("WillowProjectile")))  # (once per class)
        return found

    def owner(self, causer: Any) -> Any:
        """The object a causer belongs to, when the game ties it to one: a damage area (a barrel's fire on the ground) -
        its Owner, the interactive object that left it (probe_damage_causer.py: WillowDamageArea's Owner and Base the
        barrel; the hit's instigator the player who set it off). None otherwise."""
        if causer is None:
            return None
        cls = causer.Class
        key = cls._get_address()
        area = self._areas.get(key)
        if area is None:
            area = self._areas[key] = bool(cls._inherits(self._cls("WillowDamageArea")))  # (once per class)
        if not area:
            return None
        owner = _field(causer, "Owner")
        return owner if owner is not None and owner.Class._inherits(self._cls("WillowInteractiveObject")) else None

    def object_has_health(self, obj: Any) -> bool:
        """An interactive object that has health (the log leaves the others out - the user): its definition can take
        damage (bCanTakeDirectDamage / bCanTakeRadiusDamage) and its MaxHealth is above 0 - the map's own rule
        (collector._health)."""
        definition = _field(obj, "InteractiveObjectDefinition")
        if definition is None or not (_field(definition, "bCanTakeDirectDamage") or _field(definition, "bCanTakeRadiusDamage")):
            return False
        return float(_field(obj, "MaxHealth")) > 0

    def object_killed(self, obj: Any) -> bool:
        """An interactive object destroyed (a barrel blown): its bHasBeenKilled, or its Health down to 0 (a skag pile
        breaks without the flag - the user saw its card stay in Realtime; notes.md: a blown barrel reads health 0) - read
        before and after its hit (only for one with health: object_has_health)."""
        return bool(_field(obj, "bHasBeenKilled")) or float(_field(obj, "Health")) <= 0

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

    def healed(self, args: Any) -> tuple[Any, float, bool]:
        """HealDamage(Amount, Healer, DamageType, DamageTypeDefinition, bIsShieldRestore): (the healer - a controller, the
        amount, to the shield)."""
        return _field(args, "Healer"), float(_field(args, "Amount")), bool(_field(args, "bIsShieldRestore"))

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
