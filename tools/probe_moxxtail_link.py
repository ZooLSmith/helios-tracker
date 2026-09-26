# Dev probe (in game), instant, read-only: what ties a Moxxtail's drink (a pickup you pay for: bCostsToPickUp, 10
# moonstones - tools/probe_moxxtail_pickup.txt) to its Moxxtail (the WillowInteractiveObject whose Behavior_SpawnItems
# made it, at an attachment point: the pickup's bIsPickupAttachedToSomething). For each pickup that costs to pick up,
# within 60 m: its Base / Owner / Instigator, and every object property (and array of objects) of the pickup and of its
# inventory whose value is an actor - then, for each Moxxtail, its Attached / Children and every object property (and
# array) whose value is a WillowPickup. Distances for reference only. Properties only, no calls. Writes
# tools/probe_moxxtail_link.txt (appends), after each object.
#   py exec(open(r"<repo>\tools\probe_moxxtail_link.py").read())
import math
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_moxxtail_link.txt"
RANGE = 6000.0
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


def _name(v) -> str:  # noqa: ANN001
    if v is None:
        return "None"
    return f"{_try(lambda: v.Class.Name)} {_try(lambda: v._path_name())}"


def _is(v, cls: str) -> bool:  # noqa: ANN001
    c = _try(lambda: v.Class, None)
    while c is not None and not isinstance(c, str):
        if str(c.Name) == cls:
            return True
        c = _try(lambda c=c: c.SuperField, None)
    return False


def _refs(obj, indent: str, cls: str) -> None:  # noqa: ANN001
    """Every ObjectProperty / array of objects of obj whose value is a `cls` (Actor: any actor)."""
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        kind = str(f.Class.Name)
        if kind == "ObjectProperty":
            v = _try(lambda f=f: obj._get_field(f), None)
            if v is not None and not isinstance(v, str) and _is(v, cls):
                lines.append(f"{indent}{f.Name} = {_name(v)}")
        elif kind == "ArrayProperty" and str(_try(lambda f=f: f.Inner.Class.Name, "")) == "ObjectProperty":
            vals = _try(lambda f=f: list(obj._get_field(f)), []) or []
            hits = [x for x in vals if x is not None and not isinstance(x, str) and _is(x, cls)]
            if hits:
                lines.append(f"{indent}{f.Name} = [{', '.join(_name(x) for x in hits[:8])}] ({len(vals)} in all)")


def _dist(a, b) -> float:  # noqa: ANN001
    return math.dist((a.X, a.Y, a.Z), (b.X, b.Y, b.Z))


def main() -> None:
    ploc = _try(lambda: get_pc().Pawn.Location, None)
    if ploc is None or isinstance(ploc, str):
        print("probe_moxxtail_link: no player position")
        return
    lines.append("#" * 70)
    lines.append(f"run at {time.strftime('%H:%M:%S')}")
    _flush()
    near = lambda a: (loc := _try(lambda: a.Location, None)) is not None and not isinstance(loc, str) \
        and not str(a.Name).startswith("Default__") and _dist(loc, ploc) <= RANGE  # noqa: E731
    drinks = [p for p in _try(lambda: list(unrealsdk.find_all("WillowPickup", exact=False)), []) or []
              if near(p) and _try(lambda p=p: bool(p.bCostsToPickUp), False)]
    moxx = [io for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []
            if near(io) and "Moxxtail" in str(_try(lambda io=io: io.InteractiveObjectDefinition.Name, ""))]
    for p in drinks:
        inv = _try(lambda p=p: p.Inventory, None)
        lines.append(f"== drink {p.Name} {_try(lambda: inv.DefinitionData.ItemDefinition.Name)}")
        for key in ("Base", "Owner", "Instigator", "BaseBoneName", "BaseSkelComponent"):
            lines.append(f"   pickup.{key} = {_name(v) if not isinstance(v := _try(lambda k=key: getattr(p, k), None), (str, type(None))) else v}")
        _refs(p, "   pickup ref ", "Actor")
        if inv is not None and not isinstance(inv, str):
            _refs(inv, "   inventory ref ", "Actor")
        closest = min(moxx, key=lambda io: _dist(io.Location, p.Location), default=None)
        if closest is not None:
            lines.append(f"   (nearest Moxxtail {closest.Name} {closest.InteractiveObjectDefinition.Name}: "
                         f"{_dist(closest.Location, p.Location):.0f} uu)")
        _flush()
    for io in moxx:
        lines.append(f"== Moxxtail {io.Name} {io.InteractiveObjectDefinition.Name}")
        for key in ("Attached", "Children"):
            vals = _try(lambda k=key: list(getattr(io, k)), []) or []
            lines.append(f"   {key} = [{', '.join(_name(x) for x in vals[:10])}]" if not isinstance(vals, str) else f"   {key} = {vals}")
        _refs(io, "   ref ", "WillowPickup")
        _flush()
    lines.append("done")
    _flush()


main()
print(f"probe_moxxtail_link: written to {OUT}")
