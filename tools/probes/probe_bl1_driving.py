# Dev probe (in game), instant, read-only: Borderlands 1 in a vehicle - the page's player list got a "Player" (its name
# empty: util.player_info reads the vehicle's player info while driving - BL1 drives a WillowWeaponPawn seat at times,
# the log's vitals check). Run it in the driver's seat, then in the turret: the controller's Pawn / MyWillowPawn,
# the player pawn's DrivenVehicle (class chain), each one's PlayerReplicationInfo (its PlayerName), the seat's
# MyVehicle / Base / Owner, the vehicle's Driver / Controller / PRI. Writes probe_bl1_driving.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_driving.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_driving.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_driving.txt"
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


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)


def _cls(o):  # noqa: ANN001, ANN202
    out, c = [], _try(lambda: o.Class, None)
    while c is not None and not isinstance(c, str) and len(out) < 6:
        out.append(str(c.Name))
        c = _try(lambda c=c: c.SuperField, None)
    return f"{_try(lambda: o.Name)} ({' < '.join(out)})"


def _pri(o):  # noqa: ANN001, ANN202
    pri = _try(lambda: o.PlayerReplicationInfo, None)
    if pri is None or isinstance(pri, str):
        return f"PRI {pri!r}"
    return f"PRI {_try(lambda: pri.Name)} PlayerName={_try(lambda: str(pri.PlayerName))!r}"


me = _try(lambda: pc.MyWillowPawn, None)
lines.append(f"== pc.Pawn {_cls(_try(lambda: pc.Pawn, None))}; pc.MyWillowPawn {_cls(me)}; pc {_pri(pc)}")
lines.append(f"   me: {_pri(me)}; Controller {_try(lambda: me.Controller.Name)}")
driven = _try(lambda: me.DrivenVehicle, None)
lines.append(f"   DrivenVehicle {_cls(driven)}: {_pri(driven)}; Controller {_try(lambda: driven.Controller.Name)}; "
             f"Driver {_try(lambda: driven.Driver.Name)}")
for link in ("MyVehicle", "Base", "Owner"):
    v = _try(lambda l=link: getattr(driven, l), None)
    lines.append(f"   driven.{link} {_cls(v)}: {_pri(v)}; Driver {_try(lambda v=v: v.Driver.Name)}")
_flush()
