"""
Pickup amounts: how much a cash / eridium / ammo / health pickup gives - for the map's tooltip ("$ 22", "18 rounds").

Game thread only (the collector, once per pickup: cached with its record). Everything is read as properties, nothing is
called (tools/probe_pickup_amounts*.txt, .agent/notes.md "Pickup amounts"):
- what a pickup gives: its item definition's ExternalAttributeEffects (ammo: its pool + Init_AmmoAmountShared_<type>)
  and its "external" AttributeSlotEffects (cash: CreditsOnHand + the BaseCredits slot - the effect itself has scale 0),
  each an AttributeInitializationData: its InitializationDefinition's value, else its BaseValueAttribute's, else
  BaseValueConstant - times BaseValueScaleConstant;
- an InitializationDefinition: its ConditionalInitialization when enabled (the first case whose expressions all hold,
  else its default), else its ValueFormula, Multiplier x Level^Power + Offset (cash: 1.25 x 1.12^ExpLevel, x 10);
- an attribute: its value resolver - ConstantAttributeValueResolver's ConstantValue; ObjectPropertyAttributeValueResolver
  a property of the item (ExpLevel, ClonedForSharing); PlayThroughCountAttributeValueResolver the playthrough (1, 2;
  IncludePlaythroughThree 0: the third counts as 2 - inferred); ConditionalAttributeValueResolver its ValueExpressions
  (as above); AttributeSlotEffectAttributeValueResolver the item definition's slot of that name (its value, + per grade
  above the base grade); a designer attribute: lootodds' (the host's live value, else its base);
- anything else (random variance, other resolvers, the picker's own bonuses - skills, relics): unknown / left out. The
  page marks the amount "~".
"""

import math
from typing import Any

from . import lootodds
from .util import try_

MAX_DEPTH = 10
OPERATORS = {
    "OPERATOR_EqualTo": lambda a, b: a == b,
    "OPERATOR_NotEqualTo": lambda a, b: a != b,
    "OPERATOR_GreaterThan": lambda a, b: a > b,
    "OPERATOR_GreaterThanOrEqualTo": lambda a, b: a >= b,
    "OPERATOR_LessThan": lambda a, b: a < b,
    "OPERATOR_LessThanOrEqualTo": lambda a, b: a <= b,
}


def _name(v: Any) -> str:
    return str(getattr(v, "name", v))


class _Ctx:
    """What an amount depends on: the item (its properties, its definition's slots) and the playthrough (1-based)."""

    def __init__(self, inv: Any, definition: Any, playthrough: int) -> None:
        self.inv, self.definition, self.playthrough = inv, definition, playthrough


def _data(data: Any, ctx: _Ctx, depth: int) -> float | None:
    """An AttributeInitializationData's value, or None (unknown)."""
    if data is None or depth > MAX_DEPTH:
        return None
    scale = try_(lambda: float(data.BaseValueScaleConstant), 1.0)
    init = try_(lambda: data.InitializationDefinition)
    attr = try_(lambda: data.BaseValueAttribute)
    if init is not None:
        base = _init(init, ctx, depth + 1)
    elif attr is not None:
        base = _attr(attr, ctx, depth + 1)
    else:
        base = try_(lambda: float(data.BaseValueConstant))
    return base * scale if base is not None else None


def _enabled(s: Any) -> bool:
    return bool(try_(lambda: s.bEnabled, False))


def _init(init: Any, ctx: _Ctx, depth: int) -> float | None:
    if _enabled(try_(lambda: init.RandomVariance)):
        return None
    cond = try_(lambda: init.ConditionalInitialization)
    if _enabled(cond):
        return _cond(cond, ctx, depth)
    formula = try_(lambda: init.ValueFormula)
    if formula is None or not _enabled(formula):
        return None
    mult, level, power, offset = (_data(try_(lambda n=n: getattr(formula, n)), ctx, depth) for n in ("Multiplier", "Level", "Power", "Offset"))
    if None in (mult, level, power, offset):
        return None
    try:
        return mult * level ** power + offset
    except (ArithmeticError, ValueError):
        return None


def _cond(cond: Any, ctx: _Ctx, depth: int) -> float | None:
    """A conditional's value: the first case whose expressions all hold, else its default (unknown operand: unknown)."""
    for case in try_(lambda: list(cond.ConditionalExpressionList), []) or []:
        holds = True
        for e in try_(lambda c=case: list(c.Expressions), []) or []:
            a = _attr(try_(lambda e=e: e.AttributeOperand1), ctx, depth + 1)
            op2 = try_(lambda e=e: e.AttributeOperand2)
            b = _attr(op2, ctx, depth + 1) if op2 is not None else try_(lambda e=e: float(e.ConstantOperand2))
            test = OPERATORS.get(_name(try_(lambda e=e: e.ComparisonOperator)))
            if a is None or b is None or test is None:
                return None
            if not test(a, b):
                holds = False
                break
        if holds:
            return _data(try_(lambda c=case: c.BaseValueIfTrue), ctx, depth + 1)
    return _data(try_(lambda: cond.DefaultBaseValue), ctx, depth + 1)


def _attr(attr: Any, ctx: _Ctx, depth: int) -> float | None:
    if attr is None or depth > MAX_DEPTH:
        return None
    if str(attr.Class.Name) == "DesignerAttributeDefinition":
        value = lootodds.attr_value(attr)
        return value.n if value is not None else None
    resolvers = try_(lambda: list(attr.ValueResolverChain), []) or []
    if len(resolvers) != 1:
        return None
    r = resolvers[0]
    kind = str(try_(lambda: r.Class.Name, ""))
    if kind == "ConstantAttributeValueResolver":
        return try_(lambda: float(r.ConstantValue))
    if kind == "ObjectPropertyAttributeValueResolver":  # a property of the item (the context: the pickup's)
        name = str(try_(lambda: r.PropertyName, "") or "")
        value = try_(lambda: getattr(ctx.inv, name)) if name and name != "None" else None
        return float(value) if isinstance(value, (int, float)) else None
    if kind == "PlayThroughCountAttributeValueResolver":
        if ctx.playthrough < 1:
            return None
        three = try_(lambda: int(r.IncludePlaythroughThree), 0)
        return float(ctx.playthrough if three else min(ctx.playthrough, 2))
    if kind == "ConditionalAttributeValueResolver":
        return _cond(try_(lambda: r.ValueExpressions), ctx, depth + 1)
    if kind == "AttributeSlotEffectAttributeValueResolver":
        return _slot(str(try_(lambda: r.SlotName, "") or ""), ctx, depth + 1)
    return None


def _slot_grade(name: str, ctx: _Ctx, depth: int) -> float | None:
    base = _data(try_(lambda: ctx.definition.AttributeSlotBaseGrade), ctx, depth)
    ups = [u for u in try_(lambda: list(ctx.definition.AttributeSlotUpgrades), []) or [] if str(try_(lambda u=u: u.SlotName, "")) == name]
    return None if base is None else base + sum(try_(lambda u=u: int(u.GradeIncrease), 0) for u in ups)


def _slot_value(slot: Any, ctx: _Ctx, depth: int) -> float | None:
    """A slot effect's value: its base, + its per-grade upgrade for each grade above 1."""
    base = _data(try_(lambda: slot.BaseModifierValue), ctx, depth)
    grade = _slot_grade(str(try_(lambda: slot.SlotName, "")), ctx, depth)
    if base is None or grade is None:
        return None
    if grade <= 1:
        return base
    per = _data(try_(lambda: slot.PerGradeUpgrade), ctx, depth)
    return base + (grade - 1) * per if per is not None else None


def _slot(name: str, ctx: _Ctx, depth: int) -> float | None:
    for slot in try_(lambda: list(ctx.definition.AttributeSlotEffects), []) or []:
        if str(try_(lambda s=slot: s.SlotName, "")) == name:
            return _slot_value(slot, ctx, depth)
    return None


ADDS = {"MT_PreAdd", "MT_PostAdd"}


def pickup_amount(inv: Any, playthrough: int) -> int | None:
    """How much the pickup gives (its effects adding to an attribute: credits, eridium, ammo, health), rounded up; None if
    it can't be worked out (or it gives nothing that way). `playthrough`: 1-based (the controller's CurrentPlaythrough
    + 1)."""
    definition = try_(lambda: inv.DefinitionData.ItemDefinition)
    if definition is None:
        return None
    ctx = _Ctx(inv, definition, playthrough)
    total, known = 0.0, False
    for effect in try_(lambda: list(definition.ExternalAttributeEffects), []) or []:
        if _name(try_(lambda e=effect: e.ModifierType)) not in ADDS:
            continue
        value = _data(try_(lambda e=effect: e.BaseModifierValue), ctx, 0)
        if value is None:
            return None
        total += value
        known = True
    for slot in try_(lambda: list(definition.AttributeSlotEffects), []) or []:  # ("external": applied to who picks it up)
        if not try_(lambda s=slot: bool(s.bExternalSlot), False) or _name(try_(lambda s=slot: s.ModifierType)) not in ADDS:
            continue
        value = _slot_value(slot, ctx, 0)
        if value is None:
            return None
        total += value
        known = True
    # rounded up, as the game credits it (seen: $22.03 -> $23, $2.47 -> $3; a float's dust above a whole number: not)
    return math.ceil(total - 1e-4) if known and total > 0 else None
