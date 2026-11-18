# Dev probe (in game), read-only: what ties a player's minion - Gaige's Deathtrap, Axton's turret - to its player (the
# damage log credits a hit to the game's instigator: "Deathtrap" came out as its own attacker, not its player's - the
# user). For DURATION seconds a hook (PRE) on WillowPawn:TakeDamage notes the hit's InstigatedBy when it's an AI's
# controller (not a player's - nothing else read in the hook); on the next frame (PostRender) the first DUMPS distinct
# ones get all their properties written out - the controller, its pawn, the hit's DamageCauser -, arrays' entries
# listed, structs' fields. Then the local player's pawn's Allegiance (its AllegianceChildren: your turret - notes.md).
# Let Deathtrap / the turret fight alone a bit (enemies hitting each other also show: a few dumps at most).
# Hooks removed after DURATION by themselves; running it again removes the previous run's first.
# Writes tools/probes/probe_minion.txt (overwrites; each dump as it's done)
#   py exec(open(r"<repo>\tools\probes\probe_minion.py").read())
import enum
import sys
import time
from pathlib import Path

from mods_base import get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_minion.txt"  # the repo, through the mod's junction
DURATION = 120.0
DUMPS = 4
HOOK = "WillowGame.WillowPawn:TakeDamage"
TICK = "WillowGame.WillowGameViewportClient:PostRender"
HOOK_ID = "helios_probe_minion"
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


def _is(obj, name: str) -> bool:  # noqa: ANN001
    c = obj.Class
    while c is not None:
        if str(c.Name) == name:
            return True
        c = c.SuperField
    return False


OUT.write_text("", encoding="utf-8")
t0 = time.perf_counter()
state = {"dumps": 0, "seen": 0}
pending: list[tuple[WeakPointer, WeakPointer | None, str]] = []
seen_ids: set[int] = set()
names: dict[str, int] = {}


def hit_pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    by = args.InstigatedBy
    if by is None or _is(by, "PlayerController"):
        return
    state["seen"] += 1
    key = f"{by.Class.Name} {by.Name}"
    names[key] = names.get(key, 0) + 1
    address = by._get_address()
    if address in seen_ids or state["dumps"] + len(pending) >= DUMPS:
        return
    seen_ids.add(address)
    causer = args.DamageCauser
    pending.append((WeakPointer(by), WeakPointer(causer) if causer is not None else None,
                    f"{time.perf_counter() - t0:8.3f} on {obj.Name}"))


def _remove() -> None:
    remove_hook(HOOK, Type.PRE, HOOK_ID)
    remove_hook(TICK, Type.POST, HOOK_ID)


def _dump(title: str, obj) -> None:  # noqa: ANN001
    if obj is None or isinstance(obj, str):
        lines.append(f"   -- {title}: None")
        _flush()
        return
    lines.append(f"   -- {title} {_brief(obj)}: all its properties")
    lines.extend(_props(obj))  # (not +=: a local)
    _flush()


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.perf_counter() - t0
    while pending:
        by_ptr, causer_ptr, when = pending.pop(0)
        by = by_ptr()
        state["dumps"] += 1
        if by is None:
            lines.append(f"== instigator {state['dumps']} ({when}): gone before the next frame")
            _flush()
            continue
        lines.append(f"== instigator {state['dumps']} ({when}): {_brief(by)}")
        _flush()
        _dump("its controller", by)
        _dump("its pawn", _try(lambda by=by: by.Pawn, None))
        _dump("the hit's DamageCauser", causer_ptr() if causer_ptr is not None else None)
    if now < DURATION:
        return
    _remove()
    pc = _try(get_pc, None)
    pawn = _try(lambda: pc.Pawn, None) if pc is not None and not isinstance(pc, str) else None
    allegiance = _try(lambda: pawn.Allegiance, None) if pawn is not None and not isinstance(pawn, str) else None
    _dump("the local player's pawn's Allegiance", allegiance)
    lines.append(f"== done: {state['seen']} hits by an AI, {state['dumps']} dumped - per instigator: "
                 + ", ".join(f"{k} {n}" for k, n in sorted(names.items(), key=lambda kv: -kv[1])))
    print(f"[helios probe] {OUT.stem}: done - {OUT}")  # (in the console: no checking the file to know)
    _flush()


_remove()  # (a previous run's)
lines.append(f"== hooks for {DURATION:.0f} s - let Deathtrap / the turret fight")
_flush()
add_hook(HOOK, Type.PRE, HOOK_ID, hit_pre)
add_hook(TICK, Type.POST, HOOK_ID, _tick)
print(f"[helios probe] {OUT.stem}: running for {DURATION:.0f} s - let Deathtrap / the turret fight")
