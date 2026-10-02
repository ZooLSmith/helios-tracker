# Dev probe (in game), instant, read-only: where the Pre-Sequel's oxygen is, for a map layer and the domes' areas
# (.agent/presequel.md). Run it standing INSIDE an air dome (its bubble), then once outside in a vacuum - each run appends.
# 1. the HUD minimap's own oxygen icon lists: HUDWidget_Minimap.Icons_OxygenFissure / Icons_OxygenSpots - each entry's
#    fields (the other lists are pools of {Object, bVisible, MapPos}: .agent/notes.md), what its Object is (class,
#    definition, location).
# 2. the player's OzVacuumComponent (the pawn's component of that class): bHaveBreathingDevice, InOxygenTimer,
#    CanBreatheThroughOtherMeans[] {IdentifierObject, IdentifierId} - what gives air now (a dome?).
# 3. every air dome bubble / generator (a WillowInteractiveObject whose definition's name has "AirDome"): location,
#    DrawScale / DrawScale3D, each component property's class and Bounds {Origin, BoxExtent, SphereRadius}, the distance
#    to the player.
# Properties only, no calls. Writes tools/probes/probe_oxygen.txt (appends), after each section.
#   py exec(open(r"<repo>\tools\probes\probe_oxygen.py").read())
import math
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_oxygen.txt"  # the repo, through the mod's junction
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _obj(o) -> str:  # noqa: ANN001
    if o is None or isinstance(o, str):
        return repr(o)
    definition = _try(lambda: o.InteractiveObjectDefinition._path_name(), "")
    loc = _try(lambda: o.Location, None)
    where = f" at ({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})" if loc is not None and not isinstance(loc, str) else ""
    return f"{_try(lambda: o.Class.Name)} {_try(lambda: o._path_name())}{' def ' + definition if definition else ''}{where}"


def _struct(value) -> str:  # noqa: ANN001
    parts = []
    for f in _try(lambda: list(value._type._fields()), []) or []:
        if str(f.Class.Name).endswith("Property"):
            v = _try(lambda f=f: value._get_field(f))
            parts.append(f"{f.Name}={_obj(v) if hasattr(v, '_path_name') else getattr(v, 'name', v)!r}")
    return "{" + ", ".join(parts) + "}"


def _bounds(b) -> str:  # noqa: ANN001
    if b is None or isinstance(b, str):
        return repr(b)
    o, e = _try(lambda: b.Origin, None), _try(lambda: b.BoxExtent, None)
    return (f"Origin ({o.X:.0f}, {o.Y:.0f}, {o.Z:.0f}) BoxExtent ({e.X:.0f}, {e.Y:.0f}, {e.Z:.0f})"
            f" SphereRadius {_try(lambda: b.SphereRadius)!r}") if o is not None and e is not None else repr(b)


def main() -> None:
    pc = get_pc()
    pawn = _try(lambda: pc.Pawn, None)
    ploc = _try(lambda: pawn.Location, None)
    lines.append(f"player at ({ploc.X:.0f}, {ploc.Y:.0f}, {ploc.Z:.0f})" if ploc is not None and not isinstance(ploc, str) else "player: ?")
    lines.append("== 1. the minimap's oxygen lists")
    for mm in _try(lambda: list(unrealsdk.find_all("HUDWidget_Minimap", exact=False)), []) or []:
        if str(mm.Name).startswith("Default__"):
            continue
        lines.append(f"-- {mm._path_name()}")
        for prop in ("Icons_OxygenFissure", "Icons_OxygenSpots"):
            entries = _try(lambda p=prop: list(getattr(mm, p)))
            lines.append(f"   {prop}: {len(entries) if isinstance(entries, list) else entries}")
            for n, e in enumerate(entries if isinstance(entries, list) else []):
                lines.append(f"     [{n}] {_struct(e)[:500]}")
    _flush()
    lines.append("== 2. the player's OzVacuumComponent")
    comps = [c for c in _try(lambda: list(unrealsdk.find_all("OzVacuumComponent", exact=False)), []) or []
             if not str(c.Name).startswith("Default__")]
    for c in comps:
        owner = _try(lambda c=c: c.Owner, None)
        lines.append(f"-- {c._path_name()} (owner {_obj(owner)})")
        for name in ("bHaveBreathingDevice", "InOxygenTimer", "bFirstFrame"):
            lines.append(f"   {name} = {_try(lambda n=name: getattr(c, n))!r}")
        means = _try(lambda c=c: list(c.CanBreatheThroughOtherMeans))
        lines.append(f"   CanBreatheThroughOtherMeans: {len(means) if isinstance(means, list) else means}")
        for m in means if isinstance(means, list) else []:
            lines.append(f"     {_struct(m)}")
    _flush()
    lines.append("== 3. the air domes")
    for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
        dname = _try(lambda io=io: str(io.InteractiveObjectDefinition.Name), "")
        if "AirDome" not in dname:
            continue
        loc = _try(lambda io=io: io.Location, None)
        dist = (math.dist((loc.X, loc.Y, loc.Z), (ploc.X, ploc.Y, ploc.Z)) if loc is not None and ploc is not None
                and not isinstance(loc, str) and not isinstance(ploc, str) else None)
        lines.append(f"-- {_obj(io)}  distance {dist:.0f}" if dist is not None else f"-- {_obj(io)}")
        lines.append(f"   DrawScale = {_try(lambda io=io: io.DrawScale)!r}  DrawScale3D = {_struct(_try(lambda io=io: io.DrawScale3D))}")
        for f in _try(lambda io=io: list(io.Class._fields()), []) or []:
            if str(f.Class.Name) not in ("ObjectProperty", "ComponentProperty"):
                continue
            comp = _try(lambda f=f, io=io: io._get_field(f), None)
            if comp is None or isinstance(comp, str) or "Component" not in str(_try(lambda c=comp: c.Class.Name, "")):
                continue
            lines.append(f"   {f.Name}: {comp.Class.Name} Bounds {_bounds(_try(lambda c=comp: c.Bounds, None))}")
        _flush()
    lines.append("done")
    _flush()


main()
print(f"probe_oxygen: written to {OUT}")
