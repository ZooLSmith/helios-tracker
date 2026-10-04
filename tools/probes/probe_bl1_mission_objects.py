# Dev probe (in game), instant, read-only: Borderlands 1's mission objects (Z0_MissionData.MissionObjects.*: MO_TKsFood)
# - still on the page after their mission's done, the game showing none. Is it hidden (bHidden), unusable
# (bCanBeUsed), its mesh hidden (HiddenGame / bHidden on its components), collision off, a behavior set switched?
# For the interactive objects within 30 m whose definition is a mission object's: those, its InstanceState, the
# definition's name. Writes probe_bl1_mission_objects.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_mission_objects.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_mission_objects.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_mission_objects.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
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


def _enum(value) -> str:  # noqa: ANN001
    return f"{value.name} ({int(value)})" if isinstance(value, Enum) else repr(value)


import math  # noqa: E402

import unrealsdk  # noqa: E402

mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
me = _try(lambda: pc.Pawn.Location, None)
found = 0
for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
    path = str(_try(lambda i=io: i.InteractiveObjectDefinition._path_name(), ""))
    if "MissionObject" not in path:
        continue
    loc = _try(lambda i=io: i.Location, None)
    if me is None or loc is None or isinstance(loc, str):
        continue
    dist = math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100
    if dist > 30:
        continue
    found += 1
    lines.append(f"-- {_try(lambda: io.Name)} {dist:.1f} m: {path}")
    lines.append(f"   bHidden={_try(lambda: io.bHidden)} bCanBeUsed={_try(lambda: io.bCanBeUsed)} bDeleteMe={_try(lambda: io.bDeleteMe)} "
                 f"CollisionType={_try(lambda: io.CollisionType)} bCollideActors={_try(lambda: io.bCollideActors)} "
                 f"DrawScale={_try(lambda: io.DrawScale)}")
    for comp in _try(lambda: list(io.Components), []) or []:
        if comp is None or isinstance(comp, str):
            continue
        lines.append(f"   component {_try(lambda c=comp: c.Class.Name)} {_try(lambda c=comp: c.Name)}: "
                     f"HiddenGame={_try(lambda c=comp: c.HiddenGame)} bAttached={_try(lambda c=comp: c.bAttached)} "
                     f"CollideActors={_try(lambda c=comp: c.CollideActors)}")
    for entry in _try(lambda: list(io.InstanceState.Data), []) or []:
        lines.append(f"   instance {_try(lambda e=entry: e.Name)} ({_enum(_try(lambda e=entry: e.Type))}): "
                     f"Bool={_try(lambda e=entry: e.Bool)} Int={_try(lambda e=entry: e.Int)} Float={_try(lambda e=entry: e.Float)}")
    _flush()
lines.append(f"== {found} mission objects within 30 m")
_flush()
