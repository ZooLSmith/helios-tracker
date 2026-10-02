# Dev probe (in game), instant: where a vehicle's boost (nitro) and health live - for the Players list's
# vehicle bars. Run it while DRIVING (or on a turret), right after boosting a little (so the meter isn't
# full), then again after it refilled if you can.
# Logs: the player's DrivenVehicle (a seat on a turret: then its MyVehicle / Base / Owner), the vehicle's
# every property / function whose name looks boost / nitro / turbo / pool / resource / health / seat
# related (resource pools with their Data: CurrentValue, MaxValue...), and its controller's too.
# Writes tools/probes/probe_vehicle.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_vehicle.py").read())
import enum
import re
import sys
from pathlib import Path

from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_vehicle.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"boost|nitro|turbo|pool|resource|health|seat|fuel|energy|shield", re.I)
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
        return f"{value:.2f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        s = f"{value.Class.Name}'{value.Name}'"
        if depth == 0 and "Pool" in str(value.Class.Name):  # a resource pool: its values
            s += " {" + ", ".join(f"{k}={_try(lambda k=k: _brief(getattr(value, k), 1))}"
                                  for k in ("CurrentValue", "MaxValue", "BaseMaxValue", "ConsumptionRate", "RegenerationRate")) + "}"
        return s
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:6]) + "]"
    return repr(value)


def _related(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if not PATTERN.search(str(f.Name)):
                continue
            if f.Class.Name == "Function":
                params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
            elif f.Class.Name.endswith("Property"):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    pawn = _try(lambda: get_pc().MyWillowPawn, None)
    driven = _try(lambda: pawn.DrivenVehicle, None)
    lines.append(f"player pawn {_brief(pawn)}, DrivenVehicle {_brief(driven)}")
    if driven is None or isinstance(driven, str):
        lines.append("not driving: run it in a vehicle")
        return
    vehicle = driven
    if "WeaponPawn" in str(driven.Class.Name):  # a seat (turret): its links to the vehicle
        for name in ("MyVehicle", "Base", "Owner"):
            lines.append(f"seat.{name} = {_try(lambda n=name: _brief(getattr(driven, n)))}")
        _related(driven, "the seat")
        vehicle = _try(lambda: driven.MyVehicle, None) or _try(lambda: driven.Base, None) or driven
    _related(vehicle, "the vehicle")
    _related(_try(lambda: vehicle.Controller, None), "its controller")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_vehicle: {len(lines)} lines -> {OUT}")
