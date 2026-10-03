# Dev probe (in game), instant, read-only: Borderlands 1's vehicles - the page shows none (not even as "other"). The
# collector walks WorldInfo.PawnList (a WillowVehicle: kind "vehicle"), skips hidden pawns but the players'. Run it with
# a vehicle spawned nearby: 1. the pawns of PawnList within 50 m - class and its superclasses, bHidden, bDeleteMe,
# Health, Driver, DrivenVehicle; 2. every WillowVehicle / Vehicle actor within 50 m (find_all): the same, and whether
# PawnList has it. Writes tools/probes/probe_bl1_vehicles.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_vehicles.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_vehicles.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_vehicles.txt"
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
wi = _try(lambda: mods_base.ENGINE.GetCurrentWorldInfo(), None)


def _supers(o):  # noqa: ANN001, ANN202
    out, c = [], _try(lambda: o.Class, None)
    while c is not None and not isinstance(c, str) and len(out) < 12:
        out.append(str(c.Name))
        c = _try(lambda c=c: c.SuperField, None)
    return " < ".join(out)


def _near(o):  # noqa: ANN001, ANN202
    loc = _try(lambda: o.Location, None)
    if me is None or loc is None or isinstance(loc, str):
        return None
    d = math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100
    return d if d <= 50 else None


def _describe(p, d):  # noqa: ANN001, ANN202
    return (f"{_try(lambda: p.Name)} {d:.1f} m: {_supers(p)}; bHidden={_try(lambda: p.bHidden)} "
            f"bDeleteMe={_try(lambda: p.bDeleteMe)} Health={_try(lambda: p.Health)} "
            f"Driver={_try(lambda: p.Driver.Name)} DrivenVehicle={_try(lambda: p.DrivenVehicle.Name)}")


in_list = set()
lines.append("== PawnList within 50 m")
p, n = _try(lambda: wi.PawnList, None), 0
while p is not None and not isinstance(p, str) and n < 1000:
    n += 1
    in_list.add(_try(lambda p=p: p._get_address(), 0))
    if (d := _near(p)) is not None:
        lines.append("   " + _describe(p, d))
    p = _try(lambda p=p: p.NextPawn, None)
_flush()
lines.append("== vehicle actors within 50 m (find_all)")
for cls in ("WillowVehicle", "Vehicle"):
    for v in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or []:
        if "Default__" in str(_try(lambda v=v: v.Name, "")) or (d := _near(v)) is None:
            continue
        lines.append(f"   [{cls}] in PawnList={_try(lambda v=v: v._get_address(), 0) in in_list} " + _describe(v, d))
_flush()
