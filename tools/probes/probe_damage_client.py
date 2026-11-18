# Dev probe (in game, co-op - run it on a CLIENT), read-only: what a co-op client sees of the damage (the user,
# 2026-11-18: "damages don't register when I'm a client" - design.md "Damage log", question 3: TakeDamage is the
# server's in UE3; the log's hooks - GAME.damage.HOOKS - may never run on a client).
# 0. The machine's NetMode (3 = a client).
# 1. Read only, nothing called: the pawns' properties named like damage / hit / health / shield / crit / injured
#    (their flags: Net = replicated, what a client gets), the signatures of the functions hooked below, and the fields
#    of DisplayRecentDamageForPlayer's DamageEventData (the floating damage numbers: a client shows its own).
# 2. For DURATION seconds:
#    - the log's own hooks (HOST_HOOKS): counted, the first few written out - do any run on a client?
#    - client candidates (CLIENT_HOOKS, picked by hand - script functions or events; run 1 of probe_healing hooked 117
#      by name and crashed): each call written out (the first DETAIL_PER_FUNCTION) with its simple parameters, its
#      structs in full (DamageEventData: amount? crit? target? element?);
#    - every frame, every pawn's health and shield (the replicated HealthVar / ShieldVar - run 1 read HealthPool.Data:
#      empty on a client; never a call on a found pawn: probe_healing run 2 crashed so): a drop written out - how much,
#      the pawn's replicated HitDamageTypeDefinition / crit flags
#      then, the hooked functions that ran since the last frame (what a drop can be matched with).
# The test (as the CLIENT, a few seconds apart, note what you did): shoot an enemy (a body shot, a crit), an elemental
# gun (a burn), a grenade, a barrel; let the HOST shoot an enemy you can see; get hit; get downed if it comes.
# Hooks removed after DURATION by themselves (the console says when); running it again removes the previous run's first.
# Writes tools/probes/probe_damage_client.txt (overwrites; section 1 at once, the rest every 2 s)
#   py exec(open(r"<repo>\tools\probes\probe_damage_client.py").read())
import enum
import re
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_damage_client.txt"  # the repo, through the mod's junction
DURATION = 180.0
DETAIL_PER_FUNCTION = 25
HOST_DETAIL = 3
MAX_DROPS = 400
MAX_PAWNS = 80
TICK = "WillowGame.WillowGameViewportClient:PostRender"
HOOK_ID = "helios_probe_damage_client"
CPF_PARM, CPF_RETURN, CPF_NET = 0x80, 0x400, 0x20
WORDS = re.compile(r"damage|hit|health|shield|crit|injur|killer|instigat|dying|dead|revive", re.IGNORECASE)
CLASSES = ("Engine.Pawn", "WillowGame.WillowPawn", "WillowGame.WillowAIPawn", "WillowGame.WillowPlayerPawn",
           "WillowGame.WillowInteractiveObject")
lines: list[str] = []

# The damage log's hooks (helios_tracker/games/bl2/damage.py HOOKS): counted - do they run on a client?
HOST_HOOKS = (
    "WillowGame.WillowPawn:TakeDamage",
    "WillowGame.WillowPawn:ProcessDamageTakenSkillEvents",
    "WillowGame.WillowPlayerPawn:ProcessDamageTakenSkillEvents",
    "WillowGame.WillowInteractiveObject:TakeDamage",
    "Engine.Pawn:Died",
    "WillowGame.StatusEffectsComponent:ApplyStatusEffect",
    "WillowGame.StatusEffectsComponent:OnStatusEffectEnd",
    "WillowGame.WillowPawn:PlayInjured",
    "WillowGame.WillowPawn:ClientOnRevived",
    "WillowGame.WillowPawn:SetInjuredDeadState",
    "WillowGame.WillowPawn:GoFromInjuredToHealthy",
    "WillowGame.WillowPawn:HealDamage",
)
# A client's candidates (probe_damage_functions.txt's signatures - events / simulated / client functions); one not
# found is said, not hooked
CLIENT_HOOKS = (
    "WillowGame.WillowDamageTypeDefinition:DisplayRecentDamageForPlayer",  # (PC, DamageEventData, ...): damage numbers
    "WillowGame.WillowProjectile:OnDamagedEnemy",  # (DamageTaker, bWasCrit, HealthDamage, ShieldDamage)
    "WillowGame.WillowProjectile:OnDamagedNeutral",
    "WillowGame.WillowPlayerController:AddHUDDamageIndicator",  # (HitDir, bShieldOnlyDamage): you were hit
    "WillowGame.WillowPlayerController:ClientDamageShake",  # (Damage, ...)
    "WillowGame.WillowPlayerPawn:PlayDamageCameraShake",  # (Damage, HitDir)
    "WillowGame.WillowHUDGFxMovie:AddCriticalText",  # (MessageString...): "Critical!"?
    "WillowGame.WillowPawn:PlayHealingHit",
    "WillowGame.WillowPawn:SetInjuredState",
    "Engine.Pawn:PlayDying",
    "Engine.Pawn:TornOff",
    "Engine.Pawn:PlayHit",
    "WillowGame.WillowPawn:PlayHit",
    "WillowGame.WillowAIPawn:PlayHit",
    "WillowGame.WillowPawn:PlayTakeHitEffects",
    "WillowGame.WillowInteractiveObject:PlayHit",
)
READABLE = ("FloatProperty", "IntProperty", "BoolProperty", "ByteProperty", "NameProperty", "StrProperty",
            "ObjectProperty", "ClassProperty", "StructProperty")
STEP_FLUSHED = 8  # the first calls: each read announced and saved first (a crash names it)


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
    if hasattr(value, "_type") and depth < 3:  # a struct: its fields
        fields = _try(lambda: list(value._type._fields()), []) or []
        inner = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(getattr(value, str(f.Name)), depth + 1))}" for f in fields)
        return "{" + inner[:2500] + "}"
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


def _function(path: str):  # noqa: ANN202
    return _try(lambda: unrealsdk.find_object("Function", path), None)


OUT.write_text("", encoding="utf-8")

# --- 0. the machine
pc = get_pc()
lines.append(f"== 0. NetMode {_try(lambda: _brief(pc.WorldInfo.NetMode))} (3 = client), PC {_name(pc)},"
             f" pawn {_name(_try(lambda: pc.Pawn, None))}")
_flush()

# --- 1. read only
lines.append("== 1a. properties named like damage / health / hit... (Net = replicated)")
for cls_path in CLASSES:
    cls = _try(lambda c=cls_path: unrealsdk.find_class(c.rsplit(".", 1)[1]), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"   {cls_path}: not found")
        continue
    me = cls._get_address()
    for prop in _try(lambda c=cls: list(c._fields()), []) or []:
        if _try(lambda p=prop: p.Outer._get_address(), None) != me or not WORDS.search(str(prop.Name)):
            continue
        if str(prop.Class.Name) == "Function":
            continue
        flags = int(_try(lambda p=prop: p.PropertyFlags, 0) or 0)
        lines.append(f"   {cls_path}.{prop.Name} ({prop.Class.Name}){' Net' if flags & CPF_NET else ''}  [0x{flags:x}]")
_flush()

lines.append("== 1b. the hooked functions (signatures)")
hooked: list[tuple[str, object, bool]] = []  # (path, function, a host hook)
for path in HOST_HOOKS + CLIENT_HOOKS:
    fn = _function(path)
    if fn is None or isinstance(fn, str):
        lines.append(f"   not found: {path}")
        continue
    hooked.append((path, fn, path in HOST_HOOKS))
    lines.append(f"   {'host  ' if path in HOST_HOOKS else 'client'} {_signature(fn)}")
_flush()

lines.append("== 1c. DisplayRecentDamageForPlayer's structs (fields)")
display = _function(CLIENT_HOOKS[0])
for p in _own_params(display) if display is not None and not isinstance(display, str) else []:
    if str(p.Class.Name) != "StructProperty":
        continue
    struct = _try(lambda p=p: p.Struct, None)
    names = [f"{f.Class.Name.removesuffix('Property')} {f.Name}" for f in (_try(lambda s=struct: list(s._fields()), []) or [])]
    lines.append(f"   {p.Name}: {_name(struct)} {{{', '.join(names)}}}")
_flush()

# --- 2. the hooks
t0 = time.perf_counter()
state = {"flush": 0.0, "drops": 0, "found": -10.0, "calls": 0}
counts: dict[str, int] = {}
detail: dict[str, int] = {}
recent: list[str] = []  # the hooked functions that ran since the last frame
pawns: list[WeakPointer] = []
vitals: dict[int, tuple[float, float]] = {}


def _now() -> str:
    return f"{time.perf_counter() - t0:8.3f}"


def _make(path: str, names: list[str], host: bool):  # noqa: ANN202
    short = path.rsplit(":", 1)[1]

    def pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        counts[path] = counts.get(path, 0) + 1
        if len(recent) < 40:
            recent.append(f"{short}@{_name(obj)}")
        if detail.get(path, 0) >= (HOST_DETAIL if host else DETAIL_PER_FUNCTION):
            return
        detail[path] = detail.get(path, 0) + 1
        state["calls"] += 1
        step = state["calls"] <= STEP_FLUSHED
        lines.append(f"{_now()} CALL {path} on {_name(obj)} ({_try(lambda: obj.Class.Name)})")
        if step:
            _flush()
        for n in names:
            if step:
                lines.append(f"            reading {n}...")
                _flush()
            lines.append(f"            {n} = {_try(lambda n=n: _brief(getattr(args, n)))}")
        if short == "PlayHit":  # run 1: it runs on a client for every hit, the attacker's pawn in hand - the rest?
            pipeline = _try(lambda: args.Pipeline, None)
            if pipeline is not None and not isinstance(pipeline, str):
                lines.append(f"            Pipeline.DamageInstigator = {_name(_try(lambda: pipeline.DamageInstigator, None))},"
                             f" DamageSource = {_name(_try(lambda: pipeline.DamageSource, None))},"
                             f" DamageTypeDef = {_name(_try(lambda: pipeline.DamageTypeDef, None))}")
                lines.append(f"            Pipeline.DamageSummary = {_try(lambda: _brief(pipeline.DamageSummary))}")
            lines.append(f"            victim: health {_health(obj)!r} shield {_shield(obj)!r}"
                         f" HitDamageTypeDefinition {_name(_try(lambda: obj.HitDamageTypeDefinition, None))}"
                         f" DamageLocationInfo {_try(lambda: _brief(obj.DamageLocationInfo))}")
        if step:
            _flush()
    return pre


def _health(pawn) -> float | None:  # noqa: ANN001
    """The replicated health (Engine.Pawn.HealthVar, Net - run 1: HealthPool.Data is empty on a client)."""
    value = _try(lambda: float(pawn.HealthVar), None)
    return value if isinstance(value, float) else None


def _shield(pawn) -> float | None:  # noqa: ANN001
    """The replicated shield (WillowPawn.ShieldVar, an int, Net)."""
    value = _try(lambda: float(pawn.ShieldVar), None)
    return value if isinstance(value, float) else None


def _poll(now: float) -> None:
    """Every pawn's health and shield: a drop written out with what ran since the last frame."""
    if now - state["found"] > 1.0:
        state["found"] = now
        found = [p for p in unrealsdk.find_all("WillowPawn", exact=False) if "Default__" not in str(p.Name)
                 and float(_try(lambda p=p: p.HealthMaxVar, 0.0) or 0.0) > 0]
        pawns[:] = [WeakPointer(p) for p in found[:MAX_PAWNS]]
        if not state.get("said") and found:
            state["said"] = 1
            lines.append(f"   {len(found)} pawns with a max health; read: " + ", ".join(
                f"{_name(p)}={_health(p)!r}/{_try(lambda p=p: p.HealthMaxVar)} sh {_shield(p)!r}/{_try(lambda p=p: p.ShieldMaxVar)}"
                for p in found[:6]))
    for ptr in pawns:
        pawn = ptr()
        if pawn is None:
            continue
        key = pawn._get_address()
        health = _health(pawn)
        if health is None:
            continue
        shield = _shield(pawn) or 0.0
        before = vitals.get(key)
        vitals[key] = (health, shield)
        if before is None or state["drops"] >= MAX_DROPS:
            continue
        lost_h, lost_s = before[0] - health, before[1] - shield
        if lost_h <= 0.01 and lost_s <= 0.01:
            continue
        state["drops"] += 1
        flags = (f"HitDamageTypeDefinition={_name(_try(lambda: pawn.HitDamageTypeDefinition, None))}"
                 f" crit={_try(lambda: pawn.bWasLastDamageACriticalHit)}/{_try(lambda: pawn.bTookCriticalHitThisTick)}"
                 f" injured={_try(lambda: _brief(pawn.InjuredState))}")
        lines.append(f"{now:8.3f} DROP {_name(pawn)} ({_try(lambda: pawn.Class.Name)}) health -{max(lost_h, 0):.1f}"
                     f" shield -{max(lost_s, 0):.1f} -> {health:.1f} / {shield:.1f} | {flags}"
                     f" | ran since the last frame: {', '.join(recent) or 'nothing hooked'}")


def _remove() -> None:
    for path in HOST_HOOKS + CLIENT_HOOKS:
        remove_hook(path, Type.PRE, HOOK_ID)
    remove_hook(TICK, Type.POST, HOOK_ID)


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
    lines.append(f"== 2b. calls in {DURATION:.0f} s ({state['drops']} drops written)")
    lines.extend(f"   {n:6d}  {path}" for path, n in sorted(counts.items(), key=lambda pn: -pn[1]))  # (not +=: a local)
    never = [p for p, _, _ in hooked if p not in counts]
    lines.append("   never called: " + (", ".join(p.rsplit(".", 1)[1] for p in never) or "none"))
    lines.append("== done")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== 2. hooks for {DURATION:.0f} s - shoot (body, crit, a burn, a grenade, a barrel), the host shoots, get hit")
_flush()
for path, fn, host in hooked:
    names = [str(p.Name) for p in _own_params(fn) if str(p.Class.Name) in READABLE]
    lines.append(f"   hooking {path} (reads {', '.join(names) or 'nothing'})...")
    _flush()
    add_hook(path, Type.PRE, HOOK_ID, _make(path, names, host))
add_hook(TICK, Type.POST, HOOK_ID, _tick)
lines.append("   all hooked")
_flush()
print(f"[helios probe] {OUT.stem}: running for {DURATION:.0f} s - shoot, crit, burn, grenade, barrel; get hit")
