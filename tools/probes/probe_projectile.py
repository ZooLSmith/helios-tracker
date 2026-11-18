# Dev probe (in game), read-only: what a projectile that dealt damage says about the weapon / grenade that fired it (the
# damage log credits a hit to its DamageCauser - a projectile is a new object each shot: "Projectile 1", "Projectile 98"
# from the same launcher, the user saw; probe_damage_causer.txt: its Owner the controller, its Instigator the pawn).
# For DURATION seconds a hook (PRE) on WillowPawn:TakeDamage and WillowInteractiveObject:TakeDamage notes the hit's
# DamageCauser when it's a WillowProjectile (nothing else read in the hook); on the next frame (PostRender) the first
# DUMPS of them get all their properties written out - arrays' entries listed, structs' fields -, a projectile's
# ObjectArchetype's too (its template: shared by every shot of one gun?).
# Fire a rocket launcher, a projectile gun (a Maliwan / Torgue one), throw a grenade at enemies - a few of each.
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_projectile.txt (overwrites; each dump as it's done)
#   py exec(open(r"<repo>\tools\probes\probe_projectile.py").read())
import enum
import sys
import time
from pathlib import Path

from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_projectile.txt"  # the repo, through the mod's junction
DURATION = 120.0
DUMPS = 6
HOOKS = ("WillowGame.WillowPawn:TakeDamage", "WillowGame.WillowInteractiveObject:TakeDamage")
TICK = "WillowGame.WillowGameViewportClient:PostRender"
HOOK_ID = "helios_probe_projectile"
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
        if depth >= 2:
            return f"[{len(items)} items]"
        return f"[{len(items)}: " + "; ".join(_brief(v, depth + 1) for v in items[:8])[:1500] + "]"
    if hasattr(value, "_type") and depth < 2:  # a struct: its fields
        fields = _try(lambda: list(value._type._fields()), []) or []
        inner = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(getattr(value, str(f.Name)), depth + 1))}" for f in fields)
        return "{" + inner[:1500] + "}"
    return repr(value)[:200]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _props(obj) -> list[str]:  # noqa: ANN001
    """All of an object's properties (not its functions), read - its class's first."""
    out, seen = [], set()
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            name, kind = str(f.Name), str(f.Class.Name)
            if name in seen or kind in SKIP_KINDS:
                continue
            seen.add(name)
            out.append(f"      {c.Name}.{name} ({kind}) = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = _try(lambda c=c: c.SuperField, None)
    return out


OUT.write_text("", encoding="utf-8")
t0 = time.perf_counter()
state = {"dumps": 0, "seen": 0}
pending: list[tuple[WeakPointer, str]] = []
counts: dict[str, int] = {}


def hit_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    causer = args.DamageCauser
    if causer is None or str(causer.Class.Name) != "WillowProjectile":
        return
    state["seen"] += 1
    counts[str(causer.Name)] = counts.get(str(causer.Name), 0) + 1
    if state["dumps"] + len(pending) < DUMPS and counts[str(causer.Name)] == 1:
        pending.append((WeakPointer(causer), f"{time.perf_counter() - t0:8.3f} on {obj.Name}"))


def _remove() -> None:
    for path in HOOKS:
        remove_hook(path, Type.PRE, HOOK_ID)
    remove_hook(TICK, Type.POST, HOOK_ID)


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter() - t0
    while pending:
        ptr, when = pending.pop(0)
        proj = ptr()
        state["dumps"] += 1
        if proj is None:
            lines.append(f"== projectile {state['dumps']} ({when}): gone before the next frame")
            _flush()
            continue
        lines.append(f"== projectile {state['dumps']} ({when}): {_brief(proj)} - all its properties")
        _flush()
        lines.extend(_props(proj))  # (not +=: a local)
        _flush()
        archetype = _try(lambda proj=proj: proj.ObjectArchetype, None)
        if archetype is not None and not isinstance(archetype, str) and state["dumps"] == 1:
            lines.append(f"   -- its ObjectArchetype {_brief(archetype)}: all its properties")
            lines.extend(_props(archetype))
            _flush()
    if now < DURATION:
        return
    _remove()
    lines.append(f"== done: {state['seen']} hits by a projectile, {len(counts)} projectiles, {state['dumps']} dumped")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== hooks for {DURATION:.0f} s - fire rockets, projectile guns, grenades at enemies")
_flush()
for path in HOOKS:
    add_hook(path, Type.PRE, HOOK_ID, hit_pre)
add_hook(TICK, Type.POST, HOOK_ID, _tick)
print(f"[helios probe] {OUT.stem}: running for {DURATION:.0f} s - rockets, projectile guns, grenades")
