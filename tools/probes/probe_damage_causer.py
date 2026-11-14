# Dev probe (in game), read-only: what a hit's causer is tied to - for the damage log's "who dealt it" when the game
# credits a player with a barrel's explosion, a fire left on the ground (WillowDamageArea), their own grenade: the live
# log showed those as the player hitting themselves (instigator = them). Which object does the game tie the causer to?
# For DURATION seconds, WillowPawn:TakeDamage and WillowInteractiveObject:TakeDamage PRE: per causer class, its first
# SAMPLES hits - the victim, InstigatedBy, the causer, and property reads only on it: Owner (3 levels), Instigator, Base,
# Outer (2 levels: a Behavior_Explode is no actor), its archetype (ObjectArchetype). Nothing called.
# Run it, then: shoot an explosive barrel near enemies and near yourself, stand in its fire, throw a grenade at your
# feet, let an enemy hit you. Hooks removed after DURATION by themselves (running it again removes the previous run's).
# Writes tools/probes/probe_damage_causer.txt (overwrites); prints in the console when done.
#   py exec(open(r"<repo>\tools\probes\probe_damage_causer.py").read())
import sys
import time
from pathlib import Path

from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_damage_causer.txt"
DURATION = 90.0
SAMPLES = 4
HOOK_ID = "helios_probe_damage_causer"
HOOKS = ["WillowGame.WillowPawn:TakeDamage", "WillowGame.WillowInteractiveObject:TakeDamage"]
lines: list[str] = []
seen: dict[str, int] = {}


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _name(obj) -> str:  # noqa: ANN001
    if obj is None:
        return "None"
    if isinstance(obj, str):
        return obj
    return str(_try(lambda: f"{obj.Class.Name}:{obj.Name}"))


def _chain(obj, prop: str, depth: int) -> str:  # noqa: ANN001
    out = []
    for _ in range(depth):
        obj = _try(lambda o=obj: getattr(o, prop), None)
        if obj is None or isinstance(obj, str):
            out.append(_name(obj))
            break
        out.append(_name(obj))
    return " > ".join(out)


def _pre(label: str):  # noqa: ANN202
    def pre(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        causer = _try(lambda: args.DamageCauser, None)
        key = f"{label} {_try(lambda: causer.Class.Name, 'None') if causer is not None else 'None'}"
        if seen.get(key, 0) >= SAMPLES:
            return
        seen[key] = seen.get(key, 0) + 1
        lines.append(f"{time.perf_counter() - t0:8.3f} {key}: victim {_name(obj)}, InstigatedBy {_name(_try(lambda: args.InstigatedBy, None))}"
                     f" (its pawn {_name(_try(lambda: args.InstigatedBy.Pawn, None))}), amount {_try(lambda: args.DamageAmount)}")
        if causer is not None:
            lines.append(f"           causer {_name(causer)}; Owner {_chain(causer, 'Owner', 3)}; Instigator"
                         f" {_name(_try(lambda: causer.Instigator, None))}; Base {_name(_try(lambda: causer.Base, None))}")
            lines.append(f"           Outer {_chain(causer, 'Outer', 2)}; archetype {_name(_try(lambda: causer.ObjectArchetype, None))}")
    return pre


def _remove() -> None:
    for path in HOOKS:
        _try(lambda path=path: remove_hook(path, Type.PRE, HOOK_ID))
    _try(lambda: remove_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID))


def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    if time.perf_counter() - t0 < DURATION:
        return
    _remove()
    lines.append(f"== done: {sum(seen.values())} hits sampled, {len(seen)} causer kinds")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[helios probe] {OUT.stem}: done - {OUT}")


_remove()  # (a previous run's)
t0 = time.perf_counter()
lines.append(f"== a hit's causer, {DURATION:.0f} s - fight now")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
for hook_path, hook_label in zip(HOOKS, ("pawn", "object")):
    added = _try(lambda p=hook_path, lb=hook_label: add_hook(p, Type.PRE, HOOK_ID, _pre(lb)))
    if added is not True:
        lines.append(f"   add_hook: {hook_path} -> {added}")
add_hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST, HOOK_ID, _tick)
print(f"[helios probe] {OUT.stem}: hooked for {DURATION:.0f} s - fight now")
