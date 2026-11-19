# Dev probe (in game - the Pre-Sequel), read-only: what Cryo does to a hit, and how the game holds it on a target (the
# damage log - BL2's damage part as is in this game: notes.md "Slag" is BL2's). The user: Cryo is slag's reskin (a
# damage bonus on a frozen / chilled target), but the damage log's Realtime shows its share as "ticks" - hits whose
# DamageSource is WillowDmgSource_StatusEffect (games/bl2/damage.py _kind), not slag's share (ExtraDamageDealtDueToAmplify,
# credited to whoever applied a STATUS_EFFECT_Amp effect - damage.py amplifiers).
# 1. Declarations only, nothing called: the StatusEffectType enum's names (is there an Amp? a Cryo?), and the
#    functions / properties with "Amp" / "Slag" / "Cryo" / "Freeze" / "Frozen" / "Chill" in their name on the pawn,
#    pipeline and status effect classes.
# 2. For DURATION seconds:
#    - WillowPawn:TakeDamage PRE / POST: each hit, one line - who, whom, source, element, causer, every non-zero / true
#      field of its DamageSummary (ExtraDamageDealtDueToAmplify, the reductions...); on a hit with an amplify bonus or a
#      status effect's (a tick), the target's active effects (their type, instigator, DamagePerSecond...);
#    - StatusEffectsComponent:ApplyStatusEffect PRE (which effect, its type, inside which hit), OnStatusEffectEnd PRE;
#    - each effect definition seen the first time: all its properties (DEFINITIONS at most);
#    - run 2 (the first showed Cryo a damage over time, no ExtraDamageDealtDueToAmplify - presequel.md; the user: a
#      frozen enemy takes more damage): on every hit the victim's frozen state (CurrentFrozenState, bIsFrozen,
#      bPendingFrozen - properties); WillowAIPawn's SetFrozenState / Freeze / RemoveFrozenState PRE (hooks only, nothing
#      called - native ones may not fire: the state on the hits covers it); the victim's attribute modifiers (every
#      *ModifierStack: whatever a freeze multiplies is one) - the non-empty ones when first seen, then each change.
# The test, solo, in this order, a few seconds apart, on the same enemy if you can (one that doesn't die fast):
#   a. a plain (non-elemental, not cryo) gun: a few body shots;
#   b. a cryo gun until the target is chilled (slowed, blue), then the plain gun again;
#   c. keep the cryo on until it's frozen solid, then AT ONCE the plain gun (body shots, a headshot), a melee, a slam -
#      while it's still frozen; again on another enemy if you can.
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_cryo.txt (overwrites; section 1 at once, the hooks' part every 2 s)
#   py exec(open(r"<repo>\tools\probes\probe_cryo.py").read())
import enum
import re
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_cryo.txt"  # the repo, through the mod's junction
DURATION = 150.0
FULL_HITS = 500  # every hit's line up to this many; after it, only those with a bonus, a crit or an effect's
EFFECT_LISTS = 80  # the target's active effects listed (on a bonus / tick hit) this many times
DEFINITIONS = 12  # effect definitions dumped in full
WORD = re.compile(r"Amp|Slag|Cryo|Freez|Frozen|Chill")
CLASSES = ("WillowGame.WillowPawn", "WillowGame.WillowAIPawn", "WillowGame.WillowDamagePipeline",
           "WillowGame.StatusEffectsComponent", "WillowGame.StatusEffectDefinition")
HIT = "WillowGame.WillowPawn:TakeDamage"
APPLY = "WillowGame.StatusEffectsComponent:ApplyStatusEffect"
END = "WillowGame.StatusEffectsComponent:OnStatusEffectEnd"
FREEZES = ("WillowGame.WillowAIPawn:SetFrozenState", "WillowGame.WillowAIPawn:Freeze",
           "WillowGame.WillowAIPawn:RemoveFrozenState")
TICK = "WillowGame.WillowGameViewportClient:PostRender"
HOOK_ID = "helios_probe_cryo"
CPF_PARM, CPF_RETURN = 0x80, 0x400
SKIP_KINDS = ("Function", "Const", "Enum", "ScriptStruct", "State")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value._path_name()}"
    if type(value).__name__ == "WrappedArray":  # (before the struct test: an array has a _type too)
        items = _try(lambda: list(value), []) or []
        if depth >= 3:
            return f"[{len(items)} items]"
        return f"[{len(items)}: " + "; ".join(_brief(v, depth + 1) for v in items[:12])[:4000] + "]"
    if hasattr(value, "_type") and depth < 3:  # a struct: its fields
        fields = _try(lambda: list(value._type._fields()), []) or []
        inner = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(getattr(value, str(f.Name)), depth + 1))}" for f in fields)
        return "{" + inner[:3000] + "}"
    return repr(value)[:300]


def _name(obj) -> str:  # noqa: ANN001
    return "None" if obj is None else str(_try(lambda: obj.Name))


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _own_params(fn) -> list:  # noqa: ANN001
    """The function's own parameters (not its locals, not its parent's), the return value left out."""
    me = fn._get_address()
    out = []
    for p in _try(lambda: list(fn._fields()), []) or []:
        flags = int(_try(lambda p=p: p.PropertyFlags, 0) or 0)
        if not flags & CPF_PARM or flags & CPF_RETURN or str(p.Name) == "ReturnValue":
            continue
        if _try(lambda p=p: p.Outer._get_address(), None) != me:
            continue
        out.append(p)
    return out


def _class_fields(cls) -> list:  # noqa: ANN001
    """A class's fields, its parents' included (the nearest first), each name once."""
    out, seen = [], set()
    c = cls
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            if str(f.Name) not in seen:
                seen.add(str(f.Name))
                out.append((c, f))
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _props(obj) -> list[str]:  # noqa: ANN001
    """All of an object's properties (not its functions), read."""
    return [f"      {c.Name}.{f.Name} ({f.Class.Name}) = {_try(lambda f=f: _brief(obj._get_field(f)))}"
            for c, f in _class_fields(obj.Class) if str(f.Class.Name) not in SKIP_KINDS]


OUT.write_text("", encoding="utf-8")

# --- 1. declarations
lines.append("== 1a. the StatusEffectType enum (StatusEffectDefinition's property): its names")
definition_cls = _try(lambda: unrealsdk.find_class("StatusEffectDefinition"), None)
type_prop = None
if definition_cls is not None and not isinstance(definition_cls, str):
    type_prop = next((f for _, f in _class_fields(definition_cls) if str(f.Name) == "StatusEffectType"), None)
if type_prop is None:
    lines.append("   StatusEffectDefinition.StatusEffectType: not found")
else:
    uenum = _try(lambda: type_prop.Enum, None)
    lines.append(f"   its enum: {_brief(uenum)}")
    members = _try(lambda: [m.name for m in unrealsdk.find_enum(str(uenum.Name))], None) if uenum is not None else None
    lines.append(f"   names: {members}")
lines.append("== 1b. 'Amp' / 'Slag' / 'Cryo' / 'Freez' / 'Frozen' / 'Chill' in a name - declared, nothing called or read")
for path in CLASSES:
    cls = _try(lambda path=path: unrealsdk.find_class(path.split(".", 1)[1]), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"   {path}: not found")
        continue
    lines.append(f"-- {path}")
    for c, f in _class_fields(cls):
        if not WORD.search(str(f.Name)):
            continue
        kind = str(f.Class.Name)
        if kind == "Function":
            params = ", ".join(f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _own_params(f))
            lines.append(f"   {c.Name}:{f.Name}({params})  [0x{int(_try(lambda f=f: f.FunctionFlags, 0) or 0):x}]")
        elif kind not in SKIP_KINDS:
            lines.append(f"   {c.Name}.{f.Name} ({kind})")
_flush()

# --- 2. the hooks
t0 = time.perf_counter()
state = {"hit": 0, "flush": 0.0, "effect_lists": 0}
open_hits: list[str] = []
dumped: set[int] = set()  # the effect definitions dumped (addresses)
stacks: dict[int, dict[str, str]] = {}  # a pawn's address -> its ModifierStacks as last written
stack_fields: dict[int, list] = {}  # a class's address -> [(stack field, attribute field or None)]


def _frozen(pawn) -> str:  # noqa: ANN001
    """The pawn's frozen state, as its properties say it."""
    return (f"frozen={_try(lambda: _brief(pawn.CurrentFrozenState))}/{_try(lambda: pawn.bIsFrozen)}"
            f"/pending {_try(lambda: pawn.bPendingFrozen)}")


def _stack_fields(obj) -> list:  # noqa: ANN001
    key = obj.Class._get_address()
    if key not in stack_fields:
        fields = {str(f.Name): f for _, f in _class_fields(obj.Class)}
        stack_fields[key] = [(f, fields.get(n.removesuffix("ModifierStack"))) for n, f in fields.items()
                             if n.endswith("ModifierStack") and str(f.Class.Name) == "ArrayProperty"]
    return stack_fields[key]


def _watch(obj, role: str) -> None:  # noqa: ANN001
    """The pawn's attribute modifiers: the non-empty ones the first time, then each change (with the value)."""
    if obj is None:
        return
    key = obj._get_address()
    first = key not in stacks
    known = stacks.setdefault(key, {})
    for stack, attr in _stack_fields(obj):
        text = _try(lambda stack=stack: _brief(obj._get_field(stack)))
        name = str(stack.Name)
        if known.get(name, "[0: ]") == text:
            continue
        known[name] = text
        value = _try(lambda attr=attr: _brief(obj._get_field(attr))) if attr is not None else "?"
        lines.append(f"            {role} {_name(obj)} {'has' if first else 'now'} "
                     f"{name.removesuffix('ModifierStack')} = {value}: {text}")


def _now() -> str:
    return f"{time.perf_counter() - t0:8.3f}"


def _summary(summary) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(summary._type._fields()), []) or []:
        n = str(f.Name)
        if n in ("ReflectionData", "DamageTakenSkillEventsTriggered", "DamageDealtSkillEventsTriggered"):
            continue
        v = _try(lambda n=n: getattr(summary, n), None)
        if v in (None, False, 0, 0.0):
            continue
        out.append(f"{n}={_brief(v)}" if not hasattr(v, "Class") else f"{n}={_name(v)}")
    return " ".join(out)


def _effects(pawn) -> str:  # noqa: ANN001
    """The pawn's active effects: each one's definition, type, instigator, DamagePerSecond, time."""
    out = []
    for ase in _try(lambda: list(pawn.StatusEffectComp.ActiveStatusEffects), []) or []:
        definition = _try(lambda ase=ase: ase.StatusEffectDefinition, None)
        out.append(f"{_name(definition)} type={_try(lambda d=definition: _brief(d.StatusEffectType))}"
                   f" by={_name(_try(lambda ase=ase: ase.EventInstigator, None))}"
                   f" dps={_try(lambda ase=ase: _brief(ase.DamagePerSecond))}"
                   f" t={_try(lambda ase=ase: _brief(ase.TotalElapsedTime))}/{_try(lambda ase=ase: _brief(ase.Duration))}")
    return "[" + "; ".join(out) + "]"


def _dump(definition) -> None:  # noqa: ANN001
    if definition is None or len(dumped) >= DEFINITIONS:
        return
    key = definition._get_address()
    if key in dumped:
        return
    dumped.add(key)
    lines.append(f"== 2b. effect definition {_brief(definition)} - all its properties")
    lines.extend(_props(definition))  # (not +=: a local)


def hit_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    state["hit"] += 1
    open_hits.append(f"hit #{state['hit']}")


def hit_post(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    if not open_hits:
        return
    label = open_hits.pop()
    pipeline = _try(lambda: args.Pipeline, None)
    summary = _try(lambda: pipeline.DamageSummary, None)
    amp = _try(lambda: summary.ExtraDamageDealtDueToAmplify, 0.0)
    crit = _try(lambda: summary.bWasCrit, False)
    source = _name(_try(lambda: pipeline.DamageSource))
    effect_hit = "StatusEffect" in source
    controller = _try(lambda: pipeline.DamageInstigator, None)
    attacker = _try(lambda: controller.Pawn, None) if controller is not None else None
    if "Vacuum" in _name(_try(lambda: pipeline.DamageTypeDef)):  # (the open air's ticks: run 1's 900 lines, nothing)
        return
    if state["hit"] <= FULL_HITS or amp or crit or effect_hit:
        lines.append(f"{_now()} {label} {_name(attacker)} -> {_name(obj)}: {source}"
                     f" {_name(_try(lambda: pipeline.DamageTypeDef))} causer {_name(_try(lambda: args.DamageCauser))} |"
                     f" {_frozen(obj)} | {_summary(summary)}")
    if (amp or effect_hit) and state["effect_lists"] < EFFECT_LISTS:  # what's on the target then: whose effect
        state["effect_lists"] += 1
        lines.append(f"            effects on {_name(obj)}: {_effects(obj)}")
    _watch(obj, "victim")


def apply_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    definition = _try(lambda: args.StatusEffectDefinition, None)
    inside = f" (inside {open_hits[-1]})" if open_hits else ""
    lines.append(f"{_now()} APPLY {_try(lambda: definition._path_name(), '?')}"
                 f" type={_try(lambda: _brief(definition.StatusEffectType))}{inside} on {_name(_try(lambda: obj.Outer))}"
                 f" by {_name(_try(lambda: args.InstigatedBy))} causer {_name(_try(lambda: args.DamageCauser))}"
                 f" spreading {_try(lambda: args.bIsFromSpreading)}")
    _dump(definition)


def end_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    lines.append(f"{_now()} END on {_name(_try(lambda: obj.Outer))}: {_try(lambda: _brief(args.ASE))}")


def freeze_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    inside = f" (inside {open_hits[-1]})" if open_hits else ""
    name = _try(lambda: str(func.func.Name), "?")  # (a BoundFunction: its UFunction in .func)
    params = _try(lambda: _brief(args.NewFrozenState), "") if name == "SetFrozenState" else ""
    lines.append(f"{_now()} {name}({params}){inside} on {_name(obj)} - was {_frozen(obj)}")
    _watch(obj, "frozen")


def _remove() -> None:
    for path in (HIT, APPLY, END, *FREEZES):
        remove_hook(path, Type.PRE, HOOK_ID)
        remove_hook(path, Type.POST, HOOK_ID)
    remove_hook(TICK, Type.POST, HOOK_ID)


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter() - t0
    if now - state["flush"] > 2.0:
        state["flush"] = now
        _flush()
    if now < DURATION:
        return
    _remove()
    lines.append(f"== done: {state['hit']} hits in {DURATION:.0f} s")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== 2. hooks for {DURATION:.0f} s - plain gun, then chilled + plain gun, then frozen + plain / melee / slam")
_flush()
add_hook(HIT, Type.PRE, HOOK_ID, hit_pre)
add_hook(HIT, Type.POST, HOOK_ID, hit_post)
add_hook(APPLY, Type.PRE, HOOK_ID, apply_pre)
add_hook(END, Type.PRE, HOOK_ID, end_pre)
for freeze in FREEZES:
    add_hook(freeze, Type.PRE, HOOK_ID, freeze_pre)
add_hook(TICK, Type.POST, HOOK_ID, _tick)
print(f"[helios probe] {OUT.stem}: running for {DURATION:.0f} s - plain gun, chill it + plain gun, freeze it + plain / melee / slam")
