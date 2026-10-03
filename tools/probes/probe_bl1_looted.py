# Dev probe (in game), instant, read-only: Borderlands 1's looted containers - the page never shows them looted. BL2's
# test (collector._is_looted): SimpleAnimState / SimpleAnimInfo (an "Opened" animation's bit) and bCanBeUsed[0] - BL1's
# WillowInteractiveObject has neither animation field (WillowGame.u, offline), a bCanBeUsed, an InstanceState
# (an InstanceDataSet: Data[] {Name, Type, Bool, Int, Float...} - an item's FlashTechFrame was one). Run it by a looted
# container and one not looted yet: the interactive objects within 25 m with loot (Loot[] or a lootable definition) -
# their definition, distance, bCanBeUsed, every InstanceState entry, their bool / int / byte / name fields.
# Writes tools/probes/probe_bl1_looted.txt (appends), after each object.
#   py exec(open(r"<repo>\tools\probes\probe_bl1_looted.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_looted.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_looted.txt"
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
near = []
for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
    if "Default__" in str(_try(lambda i=io: i.Name, "")):
        continue
    loc = _try(lambda i=io: i.Location, None)
    if me is None or loc is None or isinstance(loc, str):
        continue
    dist = math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z))
    if dist < 2500:
        near.append((dist, io))
near.sort(key=lambda t: t[0])
lines.append(f"== {len(near)} interactive objects within 25 m")
_flush()
for dist, io in near:
    definition = _try(lambda: io.InteractiveObjectDefinition, None)
    lines.append(f"-- {_try(lambda: io.Name)} {dist / 100:.1f} m: {_try(lambda: definition._path_name())}")
    lines.append(f"   bCanBeUsed={_try(lambda: io.bCanBeUsed)} Loot={len(_try(lambda: list(io.Loot), []) or [])}")
    for entry in _try(lambda: list(io.InstanceState.Data), []) or []:
        lines.append(f"   instance {_try(lambda e=entry: e.Name)} ({_enum(_try(lambda e=entry: e.Type))}): "
                     f"Bool={_try(lambda e=entry: e.Bool)} Int={_try(lambda e=entry: e.Int)} Float={_try(lambda e=entry: e.Float)} "
                     f"Object={_try(lambda e=entry: e.Object)}")
    simple = []
    for f in _try(lambda: list(io.Class._fields()), []) or []:
        if str(f.Class.Name) in ("BoolProperty", "IntProperty", "ByteProperty", "NameProperty"):
            simple.append(f"{f.Name}={_try(lambda f=f: io._get_field(f))}")
    lines.append("   fields: " + ", ".join(map(str, simple))[:3000])
    _flush()
