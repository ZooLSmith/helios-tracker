# Dev probe (in game), read-only: what slag does to a hit, and who it's credited to (the damage log's Recap - design.md
# "Damage log"). DamageSummary has ExtraDamageDealtDueToAmplify (0 on every hit probe_damage.py saw: plain, fire,
# crits, a barrel, a grenade) - slag's bonus, or an Amp shield's? And how the game holds slag on a target.
# 1. Signatures / declarations only, nothing called: functions and properties with "Amp" / "Slag" in their name
#    (case-sensitive: not "Clamp", "Camp") on the pawn, shield, pipeline and status effect classes.
# 2. For DURATION seconds:
#    - WillowPawn:TakeDamage PRE / POST: each hit numbered; after it, one line - who, whom, source, element, every
#      non-zero / true field of its DamageSummary (the reductions, ExtraDamageDealtDueToAmplify...);
#    - on the victim and the attacker's pawn: every attribute's ModifierStack (whatever slag or a shield changes is an
#      attribute modifier) - the non-empty ones when first seen, then each change, with the attribute's value;
#    - StatusEffectsComponent:ApplyStatusEffect PRE (who, which effect, inside which hit), OnStatusEffectEnd PRE (its
#      ASE): slag applied, refreshed, two at once?
#    - the next frame after a slag-looking effect is applied (its definition's path holds "Amp" / "Slag"): the
#      victim's StatusEffectsComponent, all its properties (arrays listed) - SNAPSHOTS times at most.
# The test, solo (Sanctuary's shooting range target: it doesn't die), in this order, a few seconds apart:
#   a. a plain (non-elemental) gun, no Amp shield: a few body shots;
#   b. slag the target (a slag gun, a slag grenade, Maya's skill...), then the same plain gun while it glows purple;
#   c. let the slag end, then an Amp shield equipped and full: a few shots with the plain gun;
#   d. (if you can) an Amp shield full AND the target slagged.
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_slag.txt (overwrites; section 1 at once, the hooks' part every 2 s)
#   py exec(open(r"<repo>\tools\probes\probe_slag.py").read())
import enum
import re
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_slag.txt"  # the repo, through the mod's junction
DURATION = 150.0
FULL_HITS = 400  # every hit's line up to this many; after it, only the hits with an amplify bonus or a crit
SNAPSHOTS = 3
AMP_LISTS = 40  # the target's active effects listed on a hit with an amplify bonus, this many times
WORD = re.compile(r"Amp|Slag")
CLASSES = ("WillowGame.WillowPawn", "WillowGame.WillowAIPawn", "WillowGame.WillowPlayerPawn",
           "WillowGame.WillowShield", "WillowGame.WillowDamagePipeline", "WillowGame.StatusEffectsComponent",
           "WillowGame.StatusEffectDefinition", "WillowGame.WillowPlayerController")
HIT = "WillowGame.WillowPawn:TakeDamage"
APPLY = "WillowGame.StatusEffectsComponent:ApplyStatusEffect"
END = "WillowGame.StatusEffectsComponent:OnStatusEffectEnd"
TICK = "WillowGame.WillowGameViewportClient:PostRender"
HOOK_ID = "helios_probe_slag"
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
    if type(value).__name__ == "WrappedArray":  # (before the struct test: an array has a _type too - the run 1 "{}")
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
lines.append("== 1. 'Amp' / 'Slag' in a name (case-sensitive) - declared, nothing called or read")
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
state = {"hit": 0, "flush": 0.0, "snaps": 0, "amp_lists": 0}
open_hits: list[str] = []
stacks: dict[int, dict[str, str]] = {}  # a pawn's address -> its ModifierStacks as last written
stack_fields: dict[int, list] = {}  # a class's address -> [(stack field, attribute field or None)]
to_snapshot: list[WeakPointer] = []  # the components to dump on the next frame


def _now() -> str:
    return f"{time.perf_counter() - t0:8.3f}"


def _stack_fields(obj) -> list:  # noqa: ANN001
    key = obj.Class._get_address()
    if key not in stack_fields:
        fields = {str(f.Name): f for _, f in _class_fields(obj.Class)}
        stack_fields[key] = [(f, fields.get(n.removesuffix("ModifierStack"))) for n, f in fields.items()
                             if n.endswith("ModifierStack") and str(f.Class.Name) == "ArrayProperty"]
    return stack_fields[key]


def _watch(obj, role: str) -> None:  # noqa: ANN001
    """The pawn's attribute modifiers: the non-empty ones the first time, then each change."""
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
        what = "has" if first else "now"
        lines.append(f"            {role} {_name(obj)} {what} {name.removesuffix('ModifierStack')} = {value}: {text}")


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
    controller = _try(lambda: pipeline.DamageInstigator, None)
    attacker = _try(lambda: controller.Pawn, None) if controller is not None else None
    if state["hit"] <= FULL_HITS or amp or crit:
        lines.append(f"{_now()} {label} {_name(attacker)} -> {_name(obj)}: {_name(_try(lambda: pipeline.DamageSource))}"
                     f" {_name(_try(lambda: pipeline.DamageTypeDef))} causer {_name(_try(lambda: args.DamageCauser))} |"
                     f" {_summary(summary)}")
    if amp and state["amp_lists"] < AMP_LISTS:  # the effects on the target when a bonus landed: whose slag
        state["amp_lists"] += 1
        lines.append(f"            effects on {_name(obj)}: "
                     f"{_try(lambda: _brief(obj.StatusEffectComp.ActiveStatusEffects))}")
    _watch(obj, "victim")
    if attacker is not None and not isinstance(attacker, str):
        _watch(attacker, "attacker")


def apply_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    definition = _try(lambda: args.StatusEffectDefinition, None)
    path = str(_try(lambda: definition._path_name(), ""))
    inside = f" (inside {open_hits[-1]})" if open_hits else ""
    lines.append(f"{_now()} APPLY {path}{inside} on {_name(_try(lambda: obj.Outer))} by"
                 f" {_name(_try(lambda: args.InstigatedBy))} causer {_name(_try(lambda: args.DamageCauser))}"
                 f" spreading {_try(lambda: args.bIsFromSpreading)}")
    if WORD.search(path) and state["snaps"] < SNAPSHOTS:
        to_snapshot.append(WeakPointer(obj))


def end_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    lines.append(f"{_now()} END on {_name(_try(lambda: obj.Outer))}: {_try(lambda: _brief(args.ASE))}")


def _remove() -> None:
    for path in (HIT, APPLY, END):
        remove_hook(path, Type.PRE, HOOK_ID)
        remove_hook(path, Type.POST, HOOK_ID)
    remove_hook(TICK, Type.POST, HOOK_ID)


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter() - t0
    while to_snapshot and state["snaps"] < SNAPSHOTS:
        comp = to_snapshot.pop(0)()
        if comp is None:
            continue
        state["snaps"] += 1
        lines.append(f"== 2b. snapshot {state['snaps']} at {now:.1f} s: {_brief(comp)} - all its properties")
        _flush()
        lines.extend(_props(comp))  # (not +=: a local)
        _flush()
    to_snapshot.clear()
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
lines.append(f"== 2. hooks for {DURATION:.0f} s - plain gun, then slagged, then Amp shield (the header's order)")
_flush()
add_hook(HIT, Type.PRE, HOOK_ID, hit_pre)
add_hook(HIT, Type.POST, HOOK_ID, hit_post)
add_hook(APPLY, Type.PRE, HOOK_ID, apply_pre)
add_hook(END, Type.PRE, HOOK_ID, end_pre)
add_hook(TICK, Type.POST, HOOK_ID, _tick)
print(f"[helios probe] {OUT.stem}: running for {DURATION:.0f} s - plain gun, slag it + plain gun, Amp shield")
