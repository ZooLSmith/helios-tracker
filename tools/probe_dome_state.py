# Dev probe (in game), instant, read-only: where an air dome's on / off state is (tools/probe_oxygen.py found its size -
# its bubble's sphere, 1500 x DrawScale - but nothing that changed when its generator's button was pushed: the
# definitions stay "_On", the sphere the same; .agent/presequel.md). Every simple property (bool, byte / enum, int,
# float, name) of each air dome object within 80 m (bubble, generator), of its collision component, and the player's
# OzVacuumComponent (CanBreatheThroughOtherMeans read as the struct it is), one "key = value" per line - so two runs
# diff: run it inside a dome switched OFF, then again after pushing its button (ON), then outside.
# Properties only, no calls. Writes tools/probe_dome_state.txt (appends), after each object.
#   py exec(open(r"<repo>\tools\probe_dome_state.py").read())
import math
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_dome_state.txt"  # the repo, through the mod's junction
RANGE = 8000.0  # uu (80 m) around the player
SIMPLE = ("BoolProperty", "ByteProperty", "IntProperty", "FloatProperty", "NameProperty",
          "FloatAttributeProperty", "IntAttributeProperty", "ByteAttributeProperty")
SKIP = {"ObjectInternalInteger", "NetIndex", "LastRenderTime", "LastNetUpdateTime", "CreationTime", "NetUpdateTime",
        "LastSlowUpdateTime", "TimeSinceLastTick", "LastTickTime"}
lines: list[str] = []


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _value(v):  # noqa: ANN001, ANN202
    v = getattr(v, "name", v)  # (an enum: its name)
    return round(v, 3) if isinstance(v, float) else v


def _simple(obj, prefix: str) -> None:
    """Every simple property of obj, one line each: '<prefix>.<name> = <value>'."""
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if str(f.Class.Name) not in SIMPLE or str(f.Name) in SKIP:
            continue
        lines.append(f"{prefix}.{f.Name} = {_value(_try(lambda f=f: obj._get_field(f)))!r}")


def _struct(value, prefix: str, depth: int = 0) -> None:
    """A struct's fields, nested structs / arrays too (their length, their first entries)."""
    for f in _try(lambda: list(value._type._fields()), []) or []:
        if not str(f.Class.Name).endswith("Property"):
            continue
        v = _try(lambda f=f: value._get_field(f))
        if hasattr(v, "_type") and depth < 3:
            _struct(v, f"{prefix}.{f.Name}", depth + 1)
        elif hasattr(v, "_path_name"):
            lines.append(f"{prefix}.{f.Name} = {_try(lambda v=v: v.Class.Name)} {_try(lambda v=v: v._path_name())}")
        elif hasattr(v, "__len__") and not isinstance(v, str):
            items = _try(lambda v=v: list(v), [])
            lines.append(f"{prefix}.{f.Name} = [{len(items)}]")
            for n, item in enumerate(items[:6]):
                if hasattr(item, "_type"):
                    _struct(item, f"{prefix}.{f.Name}[{n}]", depth + 1)
                else:
                    lines.append(f"{prefix}.{f.Name}[{n}] = {_try(lambda i=item: i._path_name(), item)!r}")
        else:
            lines.append(f"{prefix}.{f.Name} = {_value(v)!r}")


def main() -> None:
    pc = get_pc()
    pawn = _try(lambda: pc.Pawn, None)
    ploc = _try(lambda: pawn.Location, None)
    lines.append("#" * 70)
    lines.append(f"run at {time.strftime('%H:%M:%S')}, player at ({ploc.X:.0f}, {ploc.Y:.0f}, {ploc.Z:.0f})")
    _flush()
    # the player's breathing
    for c in _try(lambda: list(unrealsdk.find_all("OzVacuumComponent", exact=False)), []) or []:
        if "WillowPlayerPawn" not in str(_try(lambda c=c: c._path_name(), "")):
            continue
        lines.append(f"== {c._path_name()}")
        _simple(c, "vacuum")
        means = _try(lambda c=c: c.CanBreatheThroughOtherMeans, None)
        if means is not None and not isinstance(means, str):
            _struct(means, "vacuum.CanBreatheThroughOtherMeans")
        _flush()
    # the air domes around
    for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
        dname = _try(lambda io=io: str(io.InteractiveObjectDefinition.Name), "")
        loc = _try(lambda io=io: io.Location, None)
        if "AirDome" not in dname or loc is None or isinstance(loc, str) or ploc is None or isinstance(ploc, str):
            continue
        dist = math.dist((loc.X, loc.Y, loc.Z), (ploc.X, ploc.Y, ploc.Z))
        if dist > RANGE:
            continue
        key = f"{dname}@{loc.X:.0f},{loc.Y:.0f}"
        lines.append(f"== {key} ({io._path_name()}) distance {dist:.0f}")
        _simple(io, key)
        comp = _try(lambda io=io: io.CollisionComponent, None)
        if comp is not None and not isinstance(comp, str):
            lines.append(f"{key}.CollisionComponent = {_try(lambda: comp.Class.Name)}")
            _simple(comp, f"{key}.CollisionComponent")
        _flush()
    lines.append("done")
    _flush()


main()
print(f"probe_dome_state: written to {OUT}")
