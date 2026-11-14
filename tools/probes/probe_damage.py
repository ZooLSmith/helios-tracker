# Dev probe (in game), read-only: where a hit can be read - the damage log's first probe (design.md "Damage log").
# 1. (LIST_FUNCTIONS) every function named *Damage* / *Crit* in the game's code packages: its parameters, its flags
#    (Native: a native caller never goes through a hook) - signatures only, nothing called. Run 1's output kept in
#    probe_damage_functions.txt (38 classes declare their own TakeDamage / TakeRadiusDamage).
# 2. For DURATION seconds: a hook (PRE + POST) on the functions in HOOKS - the TakeDamage / TakeRadiusDamage of the
#    damageable classes, the skill events that carry the damage pipeline, the notifications with a crit flag. Each
#    call counted with our time in it; the first DETAIL_PER_FUNCTION calls of each written out: its parameters
#    read (nothing called on them), the object's health / shield before (PRE) and after (POST) - GetHealth /
#    GetShieldStrength on a pawn (the collector's calls), Health on another actor -, a call made inside another
#    hooked one (an override calling its parent: a hit counted twice); after a TakeDamage or a skill event, its
#    Pipeline's properties (a WillowDamagePipeline: the crit, the element?) for the first PIPELINE_DUMPS.
# 3. After: the properties of the last targets hit whose name holds damage / crit / hit / killed (read only).
# Run 1 (2026-11-14) crashed the game at the first hit: it read every field `_fields()` gave a function - its
# locals too (uninitialized in a PRE hook: an Array local = garbage) and its parent's parameters. Now only the
# function's own parameters (CPF_Parm, its Outer the function), and the first STEP_FLUSHED calls write a line before
# each read (a crash names what it was reading).
# Shoot something (crits, an elemental gun; a barrel too; get hit if you can) right after running it.
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_damage.txt (overwrites; section by section, the hooks' part every 2 s)
#   py exec(open(r"<repo>\tools\probes\probe_damage.py").read())
import enum
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_damage.txt"  # the repo, through the mod's junction
LIST_FUNCTIONS = False
DURATION = 45.0
DETAIL_PER_FUNCTION = 25
PIPELINE_DUMPS = 3
SUMMARIES = 40  # a hit's DamageSummary in full, one field a line (run 2 cut it at 800 characters)
STEP_FLUSHED = 4
PACKAGES = ("Engine", "GameFramework", "GearboxFramework", "WillowGame")
HOOKS = (
    "Engine.Actor:TakeDamage", "Engine.Actor:TakeRadiusDamage", "Engine.Pawn:TakeDamage",
    "Engine.KActor:TakeDamage", "Engine.SkeletalMeshActor:TakeDamage", "WillowGame.BehaviorVolume:TakeDamage",
    "WillowGame.WillowPawn:TakeDamage", "WillowGame.WillowPawn:TakeRadiusDamage", "WillowGame.WillowAIPawn:TakeDamage",
    "WillowGame.WillowPlayerPawn:TakeDamage", "WillowGame.WillowVehicle:TakeDamage",
    "WillowGame.WillowInteractiveObject:TakeDamage", "WillowGame.WillowInteractiveObject:TakeRadiusDamage",
    "WillowGame.WillowPawn:ProcessDamageDealtSkillEvents", "WillowGame.WillowPawn:ProcessDamageTakenSkillEvents",
    "WillowGame.WillowPlayerPawn:ProcessDamageDealtSkillEvents", "WillowGame.WillowPlayerPawn:ProcessDamageTakenSkillEvents",
    "WillowGame.WillowPlayerController:NotifyDamageDealt", "WillowGame.WillowPawn:NotifyDamageTaken",
    "WillowGame.WillowInteractiveObject:NotifyDamageTaken", "WillowGame.WillowGameInfo:UpdateTookDamageFromEnemyStats",
    "WillowGame.WillowProjectile:OnDamagedEnemy",
)
SUMMARY_AT = ("WillowGame.WillowPawn:ProcessDamageTakenSkillEvents", "WillowGame.WillowPlayerPawn:ProcessDamageTakenSkillEvents",
              "WillowGame.WillowInteractiveObject:TakeDamage")  # (the victim's, once per hit: run 2)
TARGET_WORDS = ("damage", "crit", "hit", "killed")
HOOK_ID = "helios_probe_damage"
CPF_PARM, CPF_RETURN = 0x80, 0x400
FLAGS = {0x1: "Final", 0x40: "Net", 0x80: "NetReliable", 0x100: "Simulated", 0x200: "Exec", 0x400: "Native",
         0x800: "Event", 0x2000: "Static", 0x200000: "NetServer", 0x1000000: "NetClient"}
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
    if hasattr(value, "_type") and depth < 2:  # a struct: its fields
        fields = _try(lambda: list(value._type._fields()), []) or []
        inner = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(getattr(value, str(f.Name)), depth + 1))}" for f in fields)
        return "{" + inner[:6000] + "}"
    return repr(value)[:300]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _flags(fn) -> str:  # noqa: ANN001
    value = int(_try(lambda: fn.FunctionFlags, 0) or 0)
    return f"0x{value:x} " + "|".join(n for bit, n in FLAGS.items() if value & bit)


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


def _signature(fn) -> str:  # noqa: ANN001
    params = [f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _own_params(fn)]
    return f"{fn._path_name()}({', '.join(params)})  [{_flags(fn)}]"


OUT.write_text("", encoding="utf-8")
PAWN = unrealsdk.find_class("Pawn")

# --- 1. the functions
if LIST_FUNCTIONS:
    lines.append("== 1. functions named *damage* / *crit* (signatures, not called)")
    found = []
    for fn in unrealsdk.find_all("Function"):
        name = str(fn.Name).lower()
        if ("damage" in name or "crit" in name) and str(fn._path_name()).split(".", 1)[0] in PACKAGES:
            found.append(fn)
    lines += [f"   {_signature(f)}" for f in sorted(found, key=lambda f: str(f._path_name()))]
    _flush()

# --- 2. the hooks
hooked = []
lines.append("== 2. the hooked functions (their own parameters)")
for path in HOOKS:
    fn = _try(lambda path=path: unrealsdk.find_object("Function", path), None)
    if fn is None or isinstance(fn, str):
        lines.append(f"   (not found) {path}")
        continue
    hooked.append((path, [str(p.Name) for p in _own_params(fn)]))
    lines.append(f"   {_signature(fn)}")
_flush()

counts: dict[str, int] = {}
ours: dict[str, float] = {}
detail: dict[str, int] = {}
stack: list[tuple[str, bool]] = []  # the hooked calls open: (path, written out)
targets: dict[int, WeakPointer] = {}  # (weak: a barrel blown up is gone by the end)
state = {"details": 0, "pipelines": 0, "summaries": 0, "flush": 0.0}
t0 = time.perf_counter()


def _vitals(obj) -> str:  # noqa: ANN001
    if _try(lambda: obj.Class._inherits(PAWN), False) is True:
        return f"health {_brief(_try(obj.GetHealth))} shield {_brief(_try(obj.GetShieldStrength))}"
    return f"Health {_brief(_try(lambda: obj.Health))}"


def _props(obj, words=None) -> list[str]:  # noqa: ANN001
    """An object's properties (not its functions) whose name holds one of `words` (None: all), read."""
    out, seen = [], set()
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            fname, kind = str(f.Name), str(f.Class.Name)
            if fname in seen or kind in ("Function", "Const", "Enum", "ScriptStruct", "State"):
                continue
            seen.add(fname)
            if words is not None and not any(w in fname.lower() for w in words):
                continue
            out.append(f"      {c.Name}.{fname} ({kind}) = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _make(path: str, names: list[str]):  # noqa: ANN202
    takes = "TakeDamage" in path or "TakeRadiusDamage" in path

    def pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        start = time.perf_counter()
        counts[path] = counts.get(path, 0) + 1
        nested = f" (inside {stack[-1][0]})" if stack else ""
        written = detail.get(path, 0) < DETAIL_PER_FUNCTION
        stack.append((path, written))
        if written:
            detail[path] = detail.get(path, 0) + 1
            state["details"] += 1
            step = state["details"] <= STEP_FLUSHED  # (each read announced first: a crash names it)
            lines.append(f"{start - t0:8.3f} PRE  {path}{nested} on {_try(lambda: _brief(obj))}")
            if step:
                _flush()
            for n in names:
                if step:
                    lines.append(f"            reading {n}...")
                    _flush()
                lines.append(f"            {n} = {_try(lambda n=n: _brief(getattr(args, n)))}")
            if step:
                lines.append("            reading vitals...")
                _flush()
            lines.append(f"            {_vitals(obj)}")
            if takes:
                targets[_try(lambda: obj._get_address(), id(obj))] = WeakPointer(obj)
            if step:
                _flush()
        ours[path] = ours.get(path, 0.0) + time.perf_counter() - start

    def post(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        start = time.perf_counter()
        written = stack.pop()[1] if stack else False
        if written:
            lines.append(f"{start - t0:8.3f} POST {path} on {_try(lambda: str(obj.Name))}: {_vitals(obj)}")
            if "Pipeline" in names and state["pipelines"] < PIPELINE_DUMPS:
                pipeline = _try(lambda: args.Pipeline, None)
                if pipeline is not None and not isinstance(pipeline, str):
                    state["pipelines"] += 1
                    lines.append(f"      -- its Pipeline {_brief(pipeline)}:")
                    _flush()
                    lines.extend(_props(pipeline))
                    _flush()
        if path in SUMMARY_AT and state["summaries"] < SUMMARIES:
            pipeline = _try(lambda: args.Pipeline, None)
            if pipeline is not None and not isinstance(pipeline, str):
                state["summaries"] += 1
                summary = _try(lambda: pipeline.DamageSummary, None)
                lines.append(f"{start - t0:8.3f} SUMMARY after {path} on {_try(lambda: str(obj.Name))} ({_vitals(obj)}):"
                             f" type {_brief(_try(lambda: pipeline.DamageTypeDef))} source {_brief(_try(lambda: pipeline.DamageSource))}"
                             f" instigator {_brief(_try(lambda: pipeline.DamageInstigator))}")
                for f in _try(lambda: list(summary._type._fields()), []) or []:
                    lines.append(f"      {f.Name} = {_try(lambda f=f: _brief(getattr(summary, str(f.Name))))}")
                _flush()
        ours[path] = ours.get(path, 0.0) + time.perf_counter() - start
    return pre, post


def _remove() -> None:
    for path in HOOKS:
        remove_hook(path, Type.PRE, HOOK_ID)
        remove_hook(path, Type.POST, HOOK_ID)
    remove_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID)


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter()
    if now - state["flush"] > 2.0:
        state["flush"] = now
        _flush()
    if now - t0 < DURATION:
        return
    _remove()
    lines.append(f"== 2b. calls in {DURATION:.0f} s (our hook's time per call)")
    for path, n in sorted(counts.items(), key=lambda pn: -pn[1]):
        lines.append(f"   {n:6d}  {ours.get(path, 0.0) / n * 1e6:7.1f} us  {path}")
    _flush()
    lines.append("== 3. the last targets' properties (damage / crit / hit / killed in their name)")
    for pointer in list(targets.values())[-6:]:
        target = pointer()
        if target is None:
            lines.append("-- (gone)")
            continue
        lines.append(f"-- {_brief(target)}")
        lines.extend(_props(target, TARGET_WORDS))
        _flush()
    lines.append("== done")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== 2. hooks on {len(hooked)} functions for {DURATION:.0f} s - shoot now")
_flush()
for path, names in hooked:
    pre, post = _make(path, names)
    add_hook(path, Type.PRE, HOOK_ID, pre)
    add_hook(path, Type.POST, HOOK_ID, post)
add_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID, _tick)
