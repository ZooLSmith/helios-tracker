# Dev probe (in game), 25 s: how a vehicle's boost (nitro) refills - a delay before it starts (like a
# shield's recharge delay?) and a rate. Get in a vehicle, run it, then boost for a second or two, let go,
# and wait until it's full again (do it twice if you can).
# Logs: at the start, every property of the vehicle's AfterburnerPool (its ResourcePool: values, rates,
# delays...), the vehicle's and its definition's fields whose names look boost / afterburner / regen /
# delay / recharge related; then the pool's value every 0.1 s (changes only, with the time) - the delay
# is the pause between the drop stopping and the refill starting.
# Writes tools/probes/probe_boost.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_boost.py").read())
import enum
import re
import time
import sys
from pathlib import Path

from mods_base import get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_boost.txt"  # the repo, through the mod's junction
SAMPLE_FOR = 25.0
SAMPLE_EVERY = 0.1
PATTERN = re.compile(r"boost|after|burner|turbo|regen|delay|recharge|pool|nitro", re.I)
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
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:8]) + "]"
    return repr(value)


def _dump(obj, label: str, only_matching: bool) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in ("Object",):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (not only_matching or PATTERN.search(str(f.Name))):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _vehicle():  # noqa: ANN202
    driven = _try(lambda: get_pc().MyWillowPawn.DrivenVehicle, None)
    if driven is not None and not isinstance(driven, str) and "WeaponPawn" in str(driven.Class.Name):
        driven = _try(lambda: driven.MyVehicle, None) or _try(lambda: driven.Base, None)
    return driven if driven is not None and not isinstance(driven, str) else None


def main() -> None:
    v = _vehicle()
    if v is None:
        lines.append("not in a vehicle: get in one first")
        return
    pool = _try(lambda: v.AfterburnerPool.Data, None)
    _dump(pool, "AfterburnerPool.Data (every property)", only_matching=False)
    _dump(v, "the vehicle (boost / regen / delay...)", only_matching=True)
    for name in ("VehicleDef", "BalanceDefinitionState", "AfterburnerDefinition", "AfterburnerPoolDefinition"):
        d = _try(lambda n=name: getattr(v, n), None)
        if d is not None and not isinstance(d, str) and hasattr(d, "Class"):
            _dump(d, f"vehicle.{name}", only_matching=True)
    lines.append("== the pool's value over time (changes only)")
    OUT.write_text("\n".join(lines), encoding="utf-8")

    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_boost"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state = time.monotonic(), {"next": 0.0, "last": None}

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append("== done")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_boost] done -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        veh = _vehicle()
        value = _try(lambda: round(float(veh.AfterburnerPool.Data.CurrentValue), 2), None) if veh else None
        if value != state["last"]:
            state["last"] = value
            lines.append(f"  {now - t0:6.2f}s  {value}")
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_boost] sampling for {SAMPLE_FOR:.0f}s - boost, let go, wait for it to refill")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
