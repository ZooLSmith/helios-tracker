# Dev probe (in game, co-op - run it on the HOST), read-only: how healing shows (the damage log's Recap and Log -
# design.md "Damage log": healing done to other players, Maya's), and two players' slag on one target (notes.md
# "Slag": re-applied by the same player it refreshes - by another?).
# 1. Signatures only, nothing called: the functions named *Heal* / *Regen* / *Restor* / *Transfus* / *Reviv* /
#    *LifeSteal* / *Drain* / GiveHealth... in WillowGame / GearboxFramework / Engine.
# 2. For DURATION seconds:
#    - a hook (PRE) on a few of them (HOOKED: picked by hand - run 1 hooked every match and crashed the game),
#      counted, the first DETAIL_PER_FUNCTION of each written out: its simple parameters, the object, the hit it ran in;
#    - WillowPawn:TakeDamage PRE / POST: each hit numbered; a hit between two players written out (Restoration heals
#      an ally by shooting them: a hit? its amounts?), the others counted; a hit with a slag bonus
#      (ExtraDamageDealtDueToAmplify): the target's slag effects and who applied each (two players: two entries?);
#    - every frame, each player's health (read, never called: run 2's GetHealth() on a found pawn crashed the game -
#      its HealthPool's Data CurrentValue / MaxValue, as the collector reads a vehicle's boost pool): a rise written out - how much, the hit
#      open then (if any), the hooked functions that ran since the last frame (what healed them).
# The test (two players or more, the host runs it), in any order, a few seconds apart:
#   a. both slag the same enemy (two slag guns / grenades), then shoot it;
#   b. a player hurt, healed by the other: Maya's Restoration (shoot your ally), a Transfusion grenade, a Moxxi gun,
#      a health vial, a regen relic / class mod, Zer0 / Krieg skills - whatever you have; note which you did, when;
#   c. one player downed, revived by the other; (and a second wind if it comes).
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_healing.txt (overwrites; section 1 at once, the rest every 2 s)
#   py exec(open(r"<repo>\tools\probes\probe_healing.py").read())
import enum
import re
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_healing.txt"  # the repo, through the mod's junction
DURATION = 240.0
DETAIL_PER_FUNCTION = 8
MAX_SLAG_LINES = 60
MAX_RISES = 300
PACKAGES = ("WillowGame", "GearboxFramework", "Engine")
WORDS = re.compile(r"heal|regen|restor|transfus|reviv|lifesteal|drain|givehealth|addhealth", re.IGNORECASE)
HIT = "WillowGame.WillowPawn:TakeDamage"
TICK = "WillowGame.WillowGameViewportClient:PostRender"
HOOK_ID = "helios_probe_healing"
CPF_PARM, CPF_RETURN = 0x80, 0x400
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
        return f"{value.Class.Name}:{value.Name}"
    if type(value).__name__ == "WrappedArray":  # (before the struct test: an array has a _type too)
        items = _try(lambda: list(value), []) or []
        if depth >= 2:
            return f"[{len(items)} items]"
        return f"[{len(items)}: " + "; ".join(_brief(v, depth + 1) for v in items[:8])[:1500] + "]"
    if hasattr(value, "_type") and depth < 2:  # a struct: its fields
        fields = _try(lambda: list(value._type._fields()), []) or []
        inner = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(getattr(value, str(f.Name)), depth + 1))}" for f in fields)
        return "{" + inner[:1500] + "}"
    return repr(value)[:200]


def _name(obj) -> str:  # noqa: ANN001
    return "None" if obj is None or isinstance(obj, str) else str(_try(lambda: obj.Name))


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


def _signature(fn) -> str:  # noqa: ANN001
    params = ", ".join(f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _own_params(fn))
    return f"{fn._path_name()}({params})  [0x{int(_try(lambda: fn.FunctionFlags, 0) or 0):x}]"


OUT.write_text("", encoding="utf-8")

# --- 1. the functions
lines.append("== 1. functions named like healing / reviving (signatures, not called)")
found = []
for fn in unrealsdk.find_all("Function"):
    path = str(fn._path_name())
    if WORDS.search(str(fn.Name)) and path.split(".", 1)[0] in PACKAGES:
        found.append((path, fn))
found.sort(key=lambda pf: pf[0])
lines.extend(f"   {_signature(f)}" for _, f in found)
_flush()


# Hooked: these only, picked from section 1's signatures (run 1 hooked all 117 matches - interfaces, UI, engine
# natives - and crashed the game as the hooks went in): script functions (no Native flag), on the classes a heal goes
# through
HOOKED = (
    "WillowGame.WillowPawn:HealDamage",  # (Amount, Healer, DamageType, DamageTypeDefinition, bIsShieldRestore)
    "WillowGame.WillowPawn:PlayHealingHit",  # (InstigatedBy, HitLocation, Momentum, HitInfo, Pipeline): a healing hit
    "WillowGame.WillowCoopGameInfo:ConvertDamageToHealing",  # (Damage, DamagedPawn, DamageInstigator, ...): an ally hit
    "WillowGame.WillowPawn:SetBeingRevived",  # (bNewBeingRevived, NewReviver)
    "WillowGame.WillowPawn:RevivePawnHealthAndShield",
    "WillowGame.WillowPawn:GoFromInjuredToHealthy",
    "WillowGame.WillowPlayerController:ClientOnRevivedPlayer",  # (PRI)
)
READABLE = ("FloatProperty", "IntProperty", "BoolProperty", "ByteProperty", "NameProperty", "StrProperty",
            "ObjectProperty", "ClassProperty")  # (a parameter read: these only - no struct, array, interface)
STEP_FLUSHED = 6  # the first calls: each read announced and saved first (a crash names it)
by_path = dict(found)
hooked = [(p, by_path[p]) for p in HOOKED if p in by_path]
lines.append(f"-- hooked: {len(hooked)} - " + ", ".join(p.rsplit(":", 1)[1] for p, _ in hooked))
lines.extend(f"   not found: {p}" for p in HOOKED if p not in by_path)
_flush()

# --- 2. the hooks
t0 = time.perf_counter()
state = {"hit": 0, "flush": 0.0, "slag": 0, "rises": 0, "found": -10.0, "other_hits": 0, "calls": 0}
counts: dict[str, int] = {}
detail: dict[str, int] = {}
open_hits: list[tuple[str, object]] = []  # (label, victim)
recent: list[str] = []  # the hooked functions that ran since the last frame
players: list[WeakPointer] = []
health: dict[int, float] = {}


def _now() -> str:
    return f"{time.perf_counter() - t0:8.3f}"


def _is_player(obj) -> bool:  # noqa: ANN001
    return obj is not None and not isinstance(obj, str) and str(_try(lambda: obj.Class.Name, "")) == "WillowPlayerPawn"


def _make(path: str, names: list[str]):  # noqa: ANN202
    def pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        counts[path] = counts.get(path, 0) + 1
        if len(recent) < 40:
            recent.append(path.rsplit(":", 1)[1])
        if detail.get(path, 0) >= DETAIL_PER_FUNCTION:
            return
        detail[path] = detail.get(path, 0) + 1
        state["calls"] += 1
        step = state["calls"] <= STEP_FLUSHED
        inside = f" (inside {open_hits[-1][0]})" if open_hits else ""
        lines.append(f"{_now()} CALL {path}{inside} on {_name(obj)}")
        if step:
            _flush()
        for n in names:
            if step:
                lines.append(f"            reading {n}...")
                _flush()
            lines.append(f"            {n} = {_try(lambda n=n: _brief(getattr(args, n)))}")
        if step:
            _flush()
    return pre


def hit_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    state["hit"] += 1
    open_hits.append((f"hit #{state['hit']}", obj))


def hit_post(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    if not open_hits:
        return
    label, _ = open_hits.pop()
    pipeline = _try(lambda: args.Pipeline, None)
    summary = _try(lambda: pipeline.DamageSummary, None)
    controller = _try(lambda: pipeline.DamageInstigator, None)
    attacker = _try(lambda: controller.Pawn, None) if controller is not None and not isinstance(controller, str) else None
    amp = _try(lambda: float(summary.ExtraDamageDealtDueToAmplify), 0.0)
    amounts = (f"initial {_try(lambda: _brief(summary.InitialDamage))} final {_try(lambda: _brief(summary.FinalDamage))}"
               f" shields {_try(lambda: _brief(summary.DamageDealtToShields))} amp {amp:.1f}")
    what = f"{_name(_try(lambda: pipeline.DamageSource))} {_name(_try(lambda: pipeline.DamageTypeDef))}"
    if _is_player(obj) and _is_player(attacker):
        lines.append(f"{_now()} {label} PLAYER -> PLAYER {_name(attacker)} -> {_name(obj)}: {what} | {amounts}")
    else:
        state["other_hits"] += 1
    if amp and state["slag"] < MAX_SLAG_LINES:
        state["slag"] += 1
        effects = _try(lambda: list(obj.StatusEffectComp.ActiveStatusEffects), []) or []
        slags = []
        for ase in effects if isinstance(effects, list) else []:
            kind = _try(lambda ase=ase: ase.StatusEffectDefinition.StatusEffectType, None)
            slags.append(f"{getattr(kind, 'name', kind)} by {_name(_try(lambda ase=ase: ase.EventInstigator, None))}"
                         f" ({_try(lambda ase=ase: _brief(ase.TotalElapsedTime))} / {_try(lambda ase=ase: _brief(ase.Duration))} s)")
        lines.append(f"{_now()} {label} SLAG BONUS {_name(attacker)} -> {_name(obj)}: {what} | {amounts} | effects: "
                     + ("; ".join(slags) or "none"))


def _remove() -> None:
    for path, _ in hooked:
        remove_hook(path, Type.PRE, HOOK_ID)
    remove_hook(HIT, Type.PRE, HOOK_ID)
    remove_hook(HIT, Type.POST, HOOK_ID)
    remove_hook(TICK, Type.POST, HOOK_ID)


def _poll(now: float) -> None:
    """Each player's health: a rise written out with what ran since the last frame."""
    if now - state["found"] > 1.0:
        state["found"] = now
        players[:] = [WeakPointer(p) for p in unrealsdk.find_all("WillowPlayerPawn")
                      if "Default__" not in str(p.Name) and _try(lambda p=p: p.Controller, None) is not None]
    for ptr in players:
        pawn = ptr()
        if pawn is None:
            continue
        key = pawn._get_address()
        pool = _try(lambda pawn=pawn: pawn.HealthPool.Data, None)
        value = _try(lambda pool=pool: float(pool.CurrentValue), None) if pool is not None and not isinstance(pool, str) else None
        if not state.get("said"):  # (once: whether the health reads at all - the hooks work either way)
            state["said"] = 1
            lines.append(f"   health of {_name(pawn)} read: {value!r} (pool {_brief(pool) if pool is not None else None})")
        if not isinstance(value, float):
            continue
        before = health.get(key)
        health[key] = value
        if before is None or value <= before + 0.01 or state["rises"] >= MAX_RISES:
            continue
        state["rises"] += 1
        top = _try(lambda pool=pool: float(pool.MaxValue), 0.0)
        inside = f" (a hit open: {open_hits[-1][0]})" if open_hits else ""
        lines.append(f"{now:8.3f} HEALTH UP {_name(pawn)} +{value - before:.1f} -> {value:.1f} / {top:.1f}{inside}"
                     f" | ran since the last frame: {', '.join(recent) or 'nothing hooked'}")


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter() - t0
    _poll(now)
    recent.clear()
    if now - state["flush"] > 2.0:
        state["flush"] = now
        _flush()
    if now < DURATION:
        return
    _remove()
    lines.append(f"== 2b. calls in {DURATION:.0f} s ({state['hit']} hits, {state['other_hits']} not between players)")
    lines.extend(f"   {n:6d}  {path}" for path, n in sorted(counts.items(), key=lambda pn: -pn[1]))  # (not +=: a local)
    lines.append(f"   (hooked, never called: {len(hooked) - len(counts)})")
    lines.append("== done")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== 2. hooks for {DURATION:.0f} s - slag one target together, heal each other, revive each other")
_flush()
for path, fn in hooked:
    names = [str(p.Name) for p in _own_params(fn) if str(p.Class.Name) in READABLE]
    lines.append(f"   hooking {path} (reads {', '.join(names) or 'nothing'})...")
    _flush()
    add_hook(path, Type.PRE, HOOK_ID, _make(path, names))
add_hook(HIT, Type.PRE, HOOK_ID, hit_pre)
add_hook(HIT, Type.POST, HOOK_ID, hit_post)
add_hook(TICK, Type.POST, HOOK_ID, _tick)
lines.append("   all hooked")
_flush()
print(f"[helios probe] {OUT.stem}: running for {DURATION:.0f} s - slag together, heal each other, revive")
