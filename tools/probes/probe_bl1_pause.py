# Dev probe (in game), read-only: Borderlands 1's pause and its shields (.agent/bl1.md).
# 1. at once: the player's items (their class, definition, UIStatModifiers, ItemCardModifierStats): BL1 has no
#    WillowShield class - which item is the shield, and where its card's numbers are.
# 2. for 40 s: what changes while a menu is open - the page shows "paused" from WorldInfo.Pauser, set by the escape
#    menu but not by the inventory (the enemies stop all the same). Hooks Engine.GameViewportClient:Tick (it runs in
#    menus; BL1 has no WillowGameViewportClient:Tick) and logs every scalar field of the world info, the player's
#    replication info, controller and pawn whose value changed, with the time. Open the escape menu (a few s), close
#    it, open the inventory (a few s), close it, maybe another menu - then wait for "done".
# Properties only. Writes tools/probes/probe_bl1_pause.txt (appends): items at once, changes as they come.
#   py exec(open(r"<repo>\tools\probes\probe_bl1_pause.py").read())
from enum import Enum
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook


def _out() -> Path:  # the repo, through the mod's junction (sys.modules if the mod imported, else sdk_mods)
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_pause.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_pause.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
HOOK = ("Engine.GameViewportClient:Tick", Type.POST, "helios_probe_bl1_pause")
WATCH_FOR = 40.0  # s
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.3f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:8]) + "]"
    if hasattr(value, "_type"):  # struct
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
pawn = _try(lambda: pc.Pawn, None)

# 1. the player's items
lines.append(f"== items of {_brief(pawn)}")
items = [o for o in _try(lambda: list(unrealsdk.find_all("WillowInventory", exact=False)), []) or []
         if not str(o.Name).startswith("Default__") and _try(lambda o=o: o.Owner == pawn, False)]
for item in items:
    data = _try(lambda i=item: i.DefinitionData, None)
    item_def = _try(lambda d=data: d.ItemDefinition, None) if data is not None and not isinstance(data, str) else None
    lines.append(f"-- {item._path_name()} ({item.Class.Name}): definition {_brief(item_def)} "
                 f"({_try(lambda d=item_def: d.Class.Name) if item_def is not None else '-'})")
    lines.append(f"   UIStatModifiers: {_brief(_try(lambda i=item: i.UIStatModifiers))[:1500]}")
    lines.append(f"   ItemCardModifierStats: {_brief(_try(lambda i=item: i.ItemCardModifierStats))[:1500]}")
    lines.append(f"   ReplicatedItemCardModifierValues: {_brief(_try(lambda i=item: i.ReplicatedItemCardModifierValues))[:800]}")
    lines.append(f"   equipped: {_brief(_try(lambda i=item: i.bEquipped))}, slot {_brief(_try(lambda i=item: i.EquippedSlot))}")
_flush()


# 2. what changes in menus
def _scalars(obj) -> dict[str, str]:  # noqa: ANN001
    """Its fields worth comparing: numbers, booleans, enums, names, objects (by path) - not structs / arrays."""
    out = {}
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        kind = f.Class.Name
        if kind in ("BoolProperty", "IntProperty", "FloatProperty", "ByteProperty", "NameProperty", "ObjectProperty", "StrProperty"):
            name = str(f.Name)
            if name in ("TimeSeconds", "RealTimeSeconds", "AudioTimeSeconds", "DeltaSeconds", "LastRenderTime", "NetUpdateTime",
                        "LastNetUpdateTime", "Location", "Rotation", "Velocity"):
                continue
            out[name] = _brief(_try(lambda f=f: obj._get_field(f)))[:200]
    return out


watched = {"wi": lambda: mods_base.ENGINE.GetCurrentWorldInfo(),
           "pri": lambda: pc.PlayerReplicationInfo, "pc": lambda: pc, "pawn": lambda: pc.Pawn}
state = {"start": time.monotonic(), "last": {}, "next": 0.0}


def _on_tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.monotonic()
    if now < state["next"]:
        return
    state["next"] = now + 0.25
    try:
        for key, get in watched.items():
            target = _try(get, None)
            if target is None or isinstance(target, str):
                continue
            values = _scalars(target)
            before = state["last"].get(key)
            if before is not None:
                changed = [f"{k}: {before.get(k)} -> {v}" for k, v in values.items() if before.get(k) != v]
                if changed:
                    lines.append(f"{now - state['start']:6.2f} s {key}: " + "; ".join(changed)[:3000])
            state["last"][key] = values
        if now - state["start"] > WATCH_FOR:
            remove_hook(HOOK[0], HOOK[1], HOOK[2])
            lines.append("== done")
        _flush()
    except Exception as ex:  # noqa: BLE001
        lines.append(f"<watch failed: {type(ex).__name__}: {ex}>")
        _flush()


remove_hook(HOOK[0], HOOK[1], HOOK[2])  # (a previous run's)
add_hook(HOOK[0], HOOK[1], HOOK[2], _on_tick)
lines.append(f"== watching for {WATCH_FOR:.0f} s from {time.strftime('%H:%M:%S')}: open the escape menu, then the inventory")
_flush()
print(f"probe_bl1_pause: watching for {WATCH_FOR:.0f} s - open the escape menu, then the inventory ({OUT})")
