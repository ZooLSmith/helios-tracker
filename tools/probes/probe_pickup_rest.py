# Dev probe (in game), 30 s in the background, read-only: does a dropped pickup ever "settle" in a way the game says?
# The collector reads every pickup 10 times a second (state.pickups: ~4 ms a tick with 45 of them); one at rest could
# be read less often - if something tells it's at rest. Loot is a rigid body while it tumbles (PhysX, on the CPU: not
# the NVIDIA-only effects); whether BL2 then switches it to another physics mode / a flag is what this looks for.
# 1. at once: WillowPickup's class chain - its properties and functions named like physics / rest / sleep / fixed /
#    velocity... (functions only listed, never called), and its collision component's;
# 2. every SAMPLE_EVERY for RUN_FOR: the pickups (new ones found each second: a drop's whole life) - their Physics,
#    speed (Velocity), how far they moved since the last sample, and every simple property found in 1 (on the pickup
#    and its collision component) - a line per pickup when something changed.
# Run it, then drop an item (or kill an enemy for loot) and wait ~20 s. Stop early: py helios_pickup_rest_stop()
# Writes tools/probes/probe_pickup_rest.txt (overwrites; as it goes)
#   py exec(open(r"<repo>\tools\probes\probe_pickup_rest.py").read())
import builtins
import enum
import math
import re
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_pickup_rest.txt"  # the repo, through the mod's junction
RUN_FOR = 30.0
SAMPLE_EVERY = 0.25
FIND_EVERY = 1.0  # s between looks for new pickups (a find_all: every object walked)
MAX_PICKUPS = 40
NEAR_M = 40.0  # only pickups this close to the player (m)
HOOK_ID = "helios_probe_pickup_rest"
RENDER = "WillowGame.WillowGameViewportClient:PostRender"
NAMES = re.compile(r"phys|rest|sleep|awake|fix|settl|velocity|rigid|land|ground|bounce|frozen|static|movable|kinematic"
                   r"|collision|toss|drop|spawn|lifespan|replicat|netupdate", re.I)
SIMPLE = {"BoolProperty", "ByteProperty", "FloatProperty", "IntProperty", "NameProperty"}
lines: list[str] = []
state: dict = {"pickups": {}, "last": {}, "props": [], "comp_props": [], "next_find": 0.0, "next_sample": 0.0}
t0 = time.monotonic()


def _try(fn, default=None):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.2f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value.Name}"
    if all(hasattr(value, a) for a in ("X", "Y", "Z")):
        return f"({value.X:.1f}, {value.Y:.1f}, {value.Z:.1f})"
    return repr(value)


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _chain(cls):  # noqa: ANN001, ANN202
    out, c = [], cls
    while c is not None and str(c.Name) != "Object" and len(out) < 20:
        out.append(c)
        c = _try(lambda c=c: c.SuperField)
    return out


def _matching(cls, label: str) -> list:  # noqa: ANN001
    """The class chain's properties and functions named like NAMES - listed; the simple properties returned (to read)."""
    simple = []
    lines.append(f"== {label}: {' < '.join(str(c.Name) for c in _chain(cls))}")
    for c in _chain(cls):
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            kind = str(f.Class.Name)
            if not NAMES.search(str(f.Name)):
                continue
            if kind == "Function":
                lines.append(f"   fn   {c.Name}.{f.Name}()  (listed, not called)")
            elif kind.endswith("Property"):
                lines.append(f"   prop {c.Name}.{f.Name}: {kind}")
                if kind in SIMPLE:
                    simple.append(f)
    return simple


# --- 1. what the classes have
OUT.write_text(f"probe_pickup_rest {time.strftime('%Y-%m-%d %H:%M:%S')} - run for {RUN_FOR:.0f} s\n", encoding="utf-8")
pickup_class = unrealsdk.find_class("WillowPickup")
state["props"] = _matching(pickup_class, "WillowPickup")
_flush()
# its collision component's class: from a pickup in the world (the first one found)
first = next((p for p in unrealsdk.find_all("WillowPickup", exact=False) if not p.Name.startswith("Default__")), None)
comp = _try(lambda: first.CollisionComponent) if first is not None else None
if comp is not None:
    state["comp_props"] = _matching(comp.Class, f"its CollisionComponent ({_brief(comp)})")
else:
    lines.append("== no pickup in the world yet: its collision component not listed (drop something, run again)")
_flush()


# --- 2. samples
def _me():  # noqa: ANN202
    return _try(lambda: get_pc().Pawn.Location)


def _find(now: float) -> None:
    me = _me()
    for p in unrealsdk.find_all("WillowPickup", exact=False):
        if len(state["pickups"]) >= MAX_PICKUPS:
            break
        if p.Name.startswith("Default__") or (key := p._get_address()) in state["pickups"]:
            continue
        loc = _try(lambda p=p: p.Location)
        if me is not None and loc is not None and math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100 > NEAR_M:
            continue
        state["pickups"][key] = (WeakPointer(p), str(p.Name), _try(lambda p=p: str(p.Inventory.Class.Name), "?"))
        lines.append(f"[{now - t0:6.2f}s] + {p.Name} ({state['pickups'][key][2]})")


def _read(p) -> dict[str, str]:  # noqa: ANN001
    loc = _try(lambda: p.Location)
    vel = _try(lambda: p.Velocity)
    out = {"Physics": _try(lambda: _brief(p.Physics), "?"),
           "speed": f"{math.sqrt(vel.X ** 2 + vel.Y ** 2 + vel.Z ** 2):.1f}" if vel is not None else "?",
           "loc": f"({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})" if loc is not None else "?"}
    for f in state["props"]:
        out[str(f.Name)] = _try(lambda f=f: _brief(p._get_field(f)), "?")
    comp = _try(lambda: p.CollisionComponent)
    if comp is not None:
        out["comp"] = _brief(comp)
        for f in state["comp_props"]:
            out["comp." + str(f.Name)] = _try(lambda f=f: _brief(comp._get_field(f)), "?")
    return out


def _sample(now: float) -> None:
    for key, (ptr, name, _kind) in list(state["pickups"].items()):
        p = ptr()
        if p is None or _try(lambda p=p: p.bDeleteMe, False):
            if state["last"].pop(key, None) is not None:
                lines.append(f"[{now - t0:6.2f}s] - {name} gone")
            continue
        now_read = _read(p)
        was = state["last"].get(key)
        if was is None:
            lines.append(f"[{now - t0:6.2f}s]   {name}: " + ", ".join(f"{k}={v}" for k, v in now_read.items() if v))
        else:
            changed = {k: v for k, v in now_read.items() if was.get(k) != v}
            if changed:
                lines.append(f"[{now - t0:6.2f}s]   {name}: " + ", ".join(f"{k} {was.get(k)} -> {v}" for k, v in changed.items()))
        state["last"][key] = now_read


def stop() -> None:
    remove_hook(RENDER, Type.POST, HOOK_ID)
    lines.append(f"== stopped at {time.monotonic() - t0:.1f}s ({len(state['pickups'])} pickups followed)")
    _flush()
    print(f"[probe_pickup_rest] stopped -> {OUT}")


def _on_render(*_args) -> None:  # noqa: ANN002
    now = time.monotonic()
    if now - t0 > RUN_FOR:
        stop()
        return
    try:
        if now >= state["next_find"]:
            state["next_find"] = now + FIND_EVERY
            _find(now)
        if now >= state["next_sample"]:
            state["next_sample"] = now + SAMPLE_EVERY
            _sample(now)
            _flush()
    except Exception as ex:  # noqa: BLE001
        lines.append(f"<{type(ex).__name__}: {ex}>")
        stop()


remove_hook(RENDER, Type.POST, HOOK_ID)  # (again: restarts)
add_hook(RENDER, Type.POST, HOOK_ID, _on_render)
builtins.helios_pickup_rest_stop = stop
lines.append(f"== sampling every {SAMPLE_EVERY} s for {RUN_FOR:.0f} s (stop early: py helios_pickup_rest_stop())")
_flush()
print(f"[probe_pickup_rest] running {RUN_FOR:.0f} s - drop something now; stop early: py helios_pickup_rest_stop()")
