# Dev probe (in game), read-only: what links a damage-over-time tick to the hit that applied it (the damage log:
# design.md "Damage log", notes.md "Damage: where a hit can be read" - a tick names the gun's definition only).
# 1. Every function with "StatusEffect" in its name in WillowGame / GearboxFramework: its own parameters, its flags -
#    signatures only, nothing called. The pawn classes' properties with "status" in their name (the class, not read).
# 2. For DURATION seconds: a hook (PRE + POST) on those functions of the classes in HOOK_CLASS_WORDS, and on
#    WillowPawn:TakeDamage (each hit numbered; after it: source, element, amount, its Pipeline - a tick is a hit too). Each call
#    counted; the first DETAIL_PER_FUNCTION of each written out - its own parameters read (CPF_Parm, its Outer the
#    function: never the locals - probe_damage.py's crash), the hit it ran inside (a status effect applied by that
#    hit?), the object it ran on.
# 3. Every SNAPSHOT_EVERY seconds (SNAPSHOTS times): the last victim's properties with "status" in their name, and
#    for an object one (a component?) all its properties - arrays' entries listed (what an active effect holds).
# Shoot something with an elemental gun (fire, then corrosive or shock) right after running it, let it burn.
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_status_effect.txt (overwrites; section by section, the hooks' part every 2 s)
#   py exec(open(r"<repo>\tools\probes\probe_status_effect.py").read())
import enum
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_status_effect.txt"  # the repo, through the mod's junction
DURATION = 45.0
DETAIL_PER_FUNCTION = 10
STEP_FLUSHED = 4
SNAPSHOT_EVERY = 4.0
SNAPSHOTS = 4
MAX_HOOKS = 120
PACKAGES = ("WillowGame", "GearboxFramework")
HOOK_CLASS_WORDS = ("statuseffect", "willowpawn", "willowaipawn", "willowplayerpawn")
PAWN_CLASSES = ("WillowPawn", "WillowAIPawn", "WillowPlayerPawn")
HIT_HOOKS = ("WillowGame.WillowPawn:TakeDamage",)  # (every pawn's hit goes through it - probe_damage.txt: an effect applied by a hit runs inside it)
HOOK_ID = "helios_probe_status_effect"
CPF_PARM, CPF_RETURN = 0x80, 0x400
FLAGS = {0x1: "Final", 0x40: "Net", 0x100: "Simulated", 0x400: "Native", 0x800: "Event", 0x2000: "Static",
         0x200000: "NetServer", 0x1000000: "NetClient"}
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
    if hasattr(value, "_type") and depth < 3:  # a struct: its fields
        fields = _try(lambda: list(value._type._fields()), []) or []
        inner = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(getattr(value, str(f.Name)), depth + 1))}" for f in fields)
        return "{" + inner[:3000] + "}"
    if type(value).__name__ == "WrappedArray" and depth < 3:
        items = _try(lambda: list(value), []) or []
        return f"[{len(items)}: " + "; ".join(_brief(v, depth + 1) for v in items[:12])[:4000] + "]"
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


OUT.write_text("", encoding="utf-8")

# --- 1. the functions, the pawns' status properties
lines.append("== 1. functions with 'StatusEffect' in their name (signatures, not called)")
found = []
for fn in unrealsdk.find_all("Function"):
    path = str(fn._path_name())
    if "statuseffect" in str(fn.Name).lower() and path.split(".", 1)[0] in PACKAGES:
        found.append((path, fn))
found.sort(key=lambda pf: pf[0])
lines += [f"   {_signature(f)}" for _, f in found]
lines.append("-- the pawn classes' properties with 'status' in their name (declared, not read)")
for name in PAWN_CLASSES:
    cls = _try(lambda name=name: unrealsdk.find_class(name), None)
    for f in _try(lambda cls=cls: list(cls._fields()), []) or []:
        if "status" in str(f.Name).lower() and str(f.Class.Name) not in ("Function", "Const", "Enum", "ScriptStruct", "State"):
            if _try(lambda f=f: f.Outer._get_address(), None) == _try(lambda cls=cls: cls._get_address(), 0):
                lines.append(f"   {name}.{f.Name} ({f.Class.Name})")
_flush()

# --- 2. the hooks
hooked = [(p, f) for p, f in found if any(w in p.split(".", 1)[1].split(":")[0].lower() for w in HOOK_CLASS_WORDS)][:MAX_HOOKS]
hooked += [(p, unrealsdk.find_object("Function", p)) for p in HIT_HOOKS]
counts: dict[str, int] = {}
detail: dict[str, int] = {}
state = {"details": 0, "hit": 0, "flush": 0.0, "snap": 0.0, "snaps": 0}
open_hits: list[str] = []  # the hits being processed: "hit #n"
victim: list[WeakPointer] = []
t0 = time.perf_counter()


def _make(path: str, names: list[str]):  # noqa: ANN202
    is_hit = path in HIT_HOOKS

    def pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.perf_counter() - t0
        counts[path] = counts.get(path, 0) + 1
        if is_hit:
            state["hit"] += 1
            open_hits.append(f"hit #{state['hit']}")
            victim[:] = [WeakPointer(obj)]
            return
        if detail.get(path, 0) >= DETAIL_PER_FUNCTION:
            return
        detail[path] = detail.get(path, 0) + 1
        state["details"] += 1
        step = state["details"] <= STEP_FLUSHED  # (each read announced first: a crash names it)
        inside = f" (inside {open_hits[-1]})" if open_hits else ""
        lines.append(f"{now:8.3f} PRE  {path}{inside} on {_try(lambda: _brief(obj))}")
        if step:
            _flush()
        for n in names:
            if step:
                lines.append(f"            reading {n}...")
                _flush()
            lines.append(f"            {n} = {_try(lambda n=n: _brief(getattr(args, n)))}")
        if step:
            _flush()

    def post(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        if not is_hit or not open_hits:
            return
        label = open_hits.pop()
        pipeline = _try(lambda: args.Pipeline, None)
        summary = _try(lambda: pipeline.DamageSummary, None)
        lines.append(f"{time.perf_counter() - t0:8.3f} {label} done on {_try(lambda: str(obj.Name))}: source"
                     f" {_brief(_try(lambda: pipeline.DamageSource))} type {_brief(_try(lambda: pipeline.DamageTypeDef))}"
                     f" final {_brief(_try(lambda: summary.FinalDamage))} shields {_brief(_try(lambda: summary.DamageDealtToShields))}"
                     f" crit {_try(lambda: summary.bWasCrit)} causer {_brief(_try(lambda: args.DamageCauser))}")
    return pre, post


def _remove() -> None:
    for path, _ in hooked:
        remove_hook(path, Type.PRE, HOOK_ID)
        remove_hook(path, Type.POST, HOOK_ID)
    remove_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID)


def _snapshot(now: float) -> None:
    target = victim[0]() if victim else None
    if target is None:
        return
    state["snaps"] += 1
    lines.append(f"== 3. snapshot {state['snaps']} at {now:.1f} s: {_brief(target)} - its 'status' properties")
    _flush()
    for line in _props(target, ("status",)):
        lines.append(line)
        _flush()
    c = _try(lambda: target.Class, None)  # the object ones: all their properties
    seen: set[str] = set()
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            fname = str(f.Name)
            if fname in seen or "status" not in fname.lower() or str(f.Class.Name) != "ObjectProperty":
                continue
            seen.add(fname)
            inner = _try(lambda f=f: target._get_field(f), None)
            if inner is None or isinstance(inner, str):
                continue
            lines.append(f"   -- {fname} = {_brief(inner)}: all its properties")
            lines.extend(_props(inner))
            _flush()
        c = _try(lambda c=c: c.SuperField, None)


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter() - t0
    if now - state["flush"] > 2.0:
        state["flush"] = now
        _flush()
    if state["snaps"] < SNAPSHOTS and victim and now - state["snap"] > SNAPSHOT_EVERY:
        state["snap"] = now
        _snapshot(now)
    if now < DURATION:
        return
    _remove()
    lines.append(f"== 2b. calls in {DURATION:.0f} s")
    lines += [f"   {n:6d}  {path}" for path, n in sorted(counts.items(), key=lambda pn: -pn[1])]
    lines.append(f"   (hooked, never called: {len(hooked) - len(counts)})")
    lines.append("== done")
    _flush()


_remove()  # (a previous run's)
lines.append(f"== 2. hooks on {len(hooked)} functions for {DURATION:.0f} s - shoot now (elemental), let it burn")
_flush()
for path, fn in hooked:
    pre, post = _make(path, [str(p.Name) for p in _own_params(fn)])
    add_hook(path, Type.PRE, HOOK_ID, pre)
    add_hook(path, Type.POST, HOOK_ID, post)
add_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID, _tick)
