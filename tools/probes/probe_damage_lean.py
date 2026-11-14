# Dev probe (in game), read-only: the damage log's hooks as they'd be built - their cost in a real fight - and the
# killing blow (design.md "Damage log"; notes.md "Damage: where a hit can be read").
# 1. The functions named Died / Killed / *Injur* / *Death* on the pawn classes (Engine.Pawn, WillowPawn,
#    WillowAIPawn, WillowPlayerPawn): their own parameters, their flags - signatures only, nothing called.
# 2. For DURATION seconds, the lean hooks (util.field reads, a tuple appended, nothing formatted):
#    - WillowPawn:TakeDamage PRE / POST: the hit's DamageCauser on a stack (the pipeline has none);
#    - the victim's ProcessDamageTakenSkillEvents (WillowPawn's, WillowPlayerPawn's own) PRE: the hit read off its
#      Pipeline - FinalDamage, DamageDealtToShields, bWasCrit, PreviousHealth, bWasInjured, the element, the source,
#      the instigator - addresses only;
#    - WillowInteractiveObject:TakeDamage POST: the same off its Pipeline, bHasBeenKilled after;
#    - the death functions found in 1 (PRE): inside a hit's TakeDamage or not (the call stack: the killing blow).
#    Each hook's body timed (perf_counter): calls, mean, max, total; the busiest second.
#    Names only for the first NAMED events and every death (resolved when they happen, outside the timing).
# Fight real enemies (kill some: a gun, a grenade, a burn if you can; get downed if you dare) right after running it.
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_damage_lean.txt (overwrites; section 1 at once, the rest at the end)
#   py exec(open(r"<repo>\tools\probes\probe_damage_lean.py").read())
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook

from helios_tracker.util import field

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_damage_lean.txt"  # the repo, through the mod's junction
DURATION = 90.0
NAMED = 40
DEATH_WORDS = ("died", "killed", "injur", "death", "reviv", "secondwind", "rejuvenat")
DEATH_CLASSES = ("Engine.Pawn", "WillowGame.WillowPawn", "WillowGame.WillowAIPawn", "WillowGame.WillowPlayerPawn",
                 "WillowGame.WillowPlayerController")
# Hooked among them: these names only (run 1 hooked all 119 matches - per-frame cameras among them - and a state
# function's path, "Engine.Pawn:Dying.Died", most likely made add_hook raise: the script stopped before its timer)
DEATH_HOOKED = ("Died", "KilledBy", "MostlyKilledBy", "PreKilledBy", "PlayInjured", "SetInjuredState",
                "SetInjuredDeadState", "GoFromInjuredToHealthy", "GoFromInjuredToMostlyDead", "RejuvenateFromInjured",
                "Behavior_GiveInjuredPlayerSecondWind", "CausePlayerDeath", "InjuredRespawn", "ForceInjuredDeadState",
                "KilledEnemy", "StartInjuredDeathSequence", "EndInjuredState")
HOOK_ID = "helios_probe_damage_lean"
CPF_PARM, CPF_RETURN = 0x80, 0x400
FLAGS = {0x1: "Final", 0x40: "Net", 0x100: "Simulated", 0x400: "Native", 0x800: "Event", 0x2000: "Static",
         0x200000: "NetServer", 0x1000000: "NetClient"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _own_params(fn) -> list:  # noqa: ANN001
    me = fn._get_address()
    out = []
    for p in _try(lambda: list(fn._fields()), []) or []:
        flags = int(_try(lambda p=p: p.PropertyFlags, 0) or 0)
        if flags & CPF_PARM and not flags & CPF_RETURN and _try(lambda p=p: p.Outer._get_address(), None) == me:
            out.append(p)
    return out


def _signature(fn) -> str:  # noqa: ANN001
    value = int(_try(lambda: fn.FunctionFlags, 0) or 0)
    params = [f"{p.Class.Name.removesuffix('Property')} {p.Name}" for p in _own_params(fn)]
    return f"{fn._path_name()}({', '.join(params)})  [0x{value:x} {'|'.join(n for b, n in FLAGS.items() if value & b)}]"


def _name(obj) -> str:  # noqa: ANN001
    if obj is None:
        return "None"
    return str(_try(lambda: f"{obj.Class.Name}:{obj.Name}"))


OUT.write_text("", encoding="utf-8")

# --- 1. the death functions
lines.append("== 1. death functions on the pawn classes (signatures, not called)")
deaths = []
for fn in unrealsdk.find_all("Function"):
    path = str(fn._path_name())
    owner = path.split(":")[0]
    if owner in DEATH_CLASSES and any(w in str(fn.Name).lower() for w in DEATH_WORDS):
        deaths.append((path, fn))
deaths.sort(key=lambda pf: pf[0])
lines += [f"   {_signature(f)}" for _, f in deaths]
all_deaths = [p for p, _ in deaths]  # (run 1 may have left hooks on any of them: all removed)
deaths = [(p, f) for p, f in deaths if "." not in p.split(":", 1)[1] and str(f.Name) != "GetRevivePct"
          and (str(f.Name) in DEATH_HOOKED or "reviv" in str(f.Name).lower())]
# (SetRevivePct: called every frame while downed, -1 when nobody revives - run 2 filled the 200 lines with it: a
# change only now; GetRevivePct the same, dropped)
last_value: dict[str, str] = {}
lines.append(f"-- hooked: {[p for p, _ in deaths]}")
_flush()

# --- 2. the lean hooks
timing: dict[str, list[float]] = {}  # hook -> [calls, total s, max s]
causers: list = []  # the open TakeDamage calls' DamageCauser (None: not read)
events: list[tuple] = []
named: list[str] = []
kills: list[str] = []
per_second: dict[int, int] = {}
t0 = time.perf_counter()


def _timed(label: str, start: float) -> None:
    spent = time.perf_counter() - start
    entry = timing.get(label)
    if entry is None:
        timing[label] = [1, spent, spent]
    else:
        entry[0] += 1
        entry[1] += spent
        if spent > entry[2]:
            entry[2] = spent


def _addr(obj):  # noqa: ANN001, ANN202
    return obj._get_address() if obj is not None else 0


def _read(pipeline, causer, victim, kind: str, start: float) -> None:  # noqa: ANN001
    summary = field(pipeline, "DamageSummary")
    events.append((start - t0, kind, _addr(victim), _addr(field(pipeline, "DamageInstigator")),
                   field(summary, "FinalDamage"), field(summary, "DamageDealtToShields"), field(summary, "bWasCrit"),
                   field(summary, "PreviousHealth"), field(summary, "bWasInjured"),
                   _addr(field(pipeline, "DamageTypeDef")), _addr(field(pipeline, "DamageSource")), _addr(causer)))
    second = int(start - t0)
    per_second[second] = per_second.get(second, 0) + 1


def _name_event(pipeline, causer, victim) -> None:  # noqa: ANN001
    e = events[-1]
    named.append(f"{e[0]:8.3f} {e[1]} {_name(victim)} by {_name(field(pipeline, 'DamageInstigator'))}: final {e[4]:.1f}"
                 f" shields {e[5]:.1f} crit {e[6]} prev {e[7]:.1f} injured {e[8]} type {_name(field(pipeline, 'DamageTypeDef'))}"
                 f" source {_try(lambda: field(pipeline, 'DamageSource').Name)} causer {_name(causer)}"
                 f" (depth {len(causers)})")


def take_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    start = time.perf_counter()
    causers.append(field(args, "DamageCauser"))
    _timed("WillowPawn:TakeDamage PRE", start)


def take_post(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    start = time.perf_counter()
    if causers:
        causers.pop()
    _timed("WillowPawn:TakeDamage POST", start)


def taken(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    start = time.perf_counter()
    pipeline = field(args, "Pipeline")
    causer = causers[-1] if causers else None
    _read(pipeline, causer, obj, "pawn", start)
    _timed("ProcessDamageTakenSkillEvents PRE", start)
    if len(named) < NAMED:
        _name_event(pipeline, causer, obj)


def io_post(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    start = time.perf_counter()
    pipeline = field(args, "Pipeline")
    causer = field(args, "DamageCauser")
    _read(pipeline, causer, obj, "object", start)
    killed = field(obj, "bHasBeenKilled")
    _timed("WillowInteractiveObject:TakeDamage POST", start)
    if len(named) < NAMED:
        _name_event(pipeline, causer, obj)
    if killed:
        kills.append(f"{start - t0:8.3f} object {_name(obj)} bHasBeenKilled after a hit (event #{len(events)})")


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        name = f"{value.Class.Name}:{value.Name}"
        summary = _try(lambda: value.DamageSummary, None) if str(value.Class.Name) == "WillowDamagePipeline" else None
        if summary is not None and not isinstance(summary, str):  # (a pipeline: the hit it holds)
            name += (f" [final {_try(lambda: summary.FinalDamage)} shields {_try(lambda: summary.DamageDealtToShields)}"
                     f" crit {_try(lambda: summary.bWasCrit)} prev {_try(lambda: summary.PreviousHealth)}"
                     f" source {_try(lambda: value.DamageSource.Name)}]")
        return name
    if hasattr(value, "name") and not isinstance(value, str):
        return str(value.name)
    return repr(value)[:200]


def _death(path: str, names: list[str]):  # noqa: ANN202
    def pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        if len(kills) >= 200:  # (a death-named function called often: noise)
            return
        now = time.perf_counter() - t0
        inside = f"inside a TakeDamage (depth {len(causers)}), the last hit read: event #{len(events)}" if causers else "outside any TakeDamage"
        last = events[-1] if events else None
        same = last is not None and last[2] == _addr(obj)
        params = ", ".join(f"{n}={_try(lambda n=n: _brief(getattr(args, n)))}" for n in names)
        if "RevivePct" in path:  # (a change only)
            key = f"{path} {_addr(obj)}"
            if last_value.get(key) == params:
                return
            last_value[key] = params
        kills.append(f"{now:8.3f} {path} on {_name(obj)}: {inside}; the last hit's victim this one: {same}"
                     + (f" (final {last[4]:.1f}, prev health {last[7]:.1f}, injured {last[8]})" if same else "")
                     + "\n            " + params)
    return pre


HOOKS = [("WillowGame.WillowPawn:TakeDamage", Type.PRE, take_pre), ("WillowGame.WillowPawn:TakeDamage", Type.POST, take_post),
         ("WillowGame.WillowPawn:ProcessDamageTakenSkillEvents", Type.PRE, taken),
         ("WillowGame.WillowPlayerPawn:ProcessDamageTakenSkillEvents", Type.PRE, taken),
         ("WillowGame.WillowInteractiveObject:TakeDamage", Type.POST, io_post)]
HOOKS += [(p, Type.PRE, _death(p, [str(x.Name) for x in _own_params(f)])) for p, f in deaths]


def _remove() -> None:
    for path, kind, _ in HOOKS:
        _try(lambda path=path, kind=kind: remove_hook(path, kind, HOOK_ID))
    for path in all_deaths:
        _try(lambda path=path: remove_hook(path, Type.PRE, HOOK_ID))
    remove_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID)


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    if time.perf_counter() - t0 < DURATION:
        return
    _remove()
    lines.append(f"== 2. {len(events)} hits in {DURATION:.0f} s; the busiest second: {max(per_second.values(), default=0)}")
    lines.append("-- our hooks' bodies (calls, mean us, max us, total ms)")
    for label, (n, total, top) in sorted(timing.items()):
        lines.append(f"   {label}: {n} calls, {total / n * 1e6:.1f} us mean, {top * 1e6:.1f} us max, {total * 1e3:.1f} ms")
    lines.append(f"-- the first {len(named)} hits, named")
    lines.extend(named)
    lines.append("-- deaths and objects killed")
    lines.extend(kills or ["   (none)"])  # (not +=: that makes `lines` a local - the end failed once)
    lines.append(f"-- open TakeDamage calls left on the stack: {len(causers)} (should be 0)")
    lines.append("== done")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== 2. lean hooks for {DURATION:.0f} s ({len(HOOKS)}) - fight now")
_flush()
for path, kind, fn in HOOKS:
    added = _try(lambda path=path, kind=kind, fn=fn: add_hook(path, kind, HOOK_ID, fn))
    if added is not True:  # (True: added; False: already there; a string: it raised)
        lines.append(f"   add_hook: {path} -> {added}")
_flush()
add_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID, _tick)
