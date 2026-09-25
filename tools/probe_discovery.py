# Dev probe (in game), instant: the level's area names (the "discovered" areas: a name on the HUD and
# some XP when entered) and the map's fog of war - where the game keeps them.
# Logs:
#  - the classes whose name looks discovery / fog of war / explored related (every loaded UClass), with
#    their own properties;
#  - every WorldDiscoveryArea-like actor in the level (the first ones in full, the others one line):
#    position, radius, name, discovered?;
#  - the fields of the controller, pawn, PRI, HUD, world / game / replication info and the map info
#    whose name looks related (their values: arrays with their length and first entries).
# Run it in a level with a few areas discovered and some not (e.g. Southern Shelf part way).
# Writes tools/probe_discovery.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_discovery.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_discovery.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"discover|fog|fow|explor|reveal|unveil|areaname|worldarea|mapdata", re.I)
FULL = 4  # actors dumped in full per class
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
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:6]) + "]"
    return repr(value)


def _dump(obj, label: str, only_matching: bool) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in ("Object",):
        if only_matching and c.Name == "Actor":
            break
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (not only_matching or PATTERN.search(str(f.Name))):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
            elif f.Class.Name == "Function" and PATTERN.search(str(f.Name)):
                lines.append(f"   {c.Name}.{f.Name}()  (function)")
        c = c.SuperField


def main() -> None:
    pc = get_pc()
    wi = ENGINE.GetCurrentWorldInfo()
    lines.append(f"map: {_try(lambda: wi.GetStreamingPersistentMapName())}")
    # the related classes
    classes = [c for c in _try(lambda: list(unrealsdk.find_all("Class", exact=True)), [])
               if PATTERN.search(str(c.Name))]
    lines.append(f"== {len(classes)} classes named like discovery / fog of war")
    for c in sorted(classes, key=lambda c: str(c.Name)):
        own = [f"{f.Name}:{f.Class.Name.replace('Property', '')}" for f in _try(lambda c=c: list(c._fields()), [])
               if f.Class.Name.endswith("Property") or f.Class.Name == "Function"]
        sup = _try(lambda c=c: c.SuperField.Name, "?")
        lines.append(f"   {c.Name} < {sup}: {', '.join(own[:40])}")
    # their instances in the level (actors and objects)
    for c in sorted(classes, key=lambda c: str(c.Name)):
        objs = [o for o in _try(lambda c=c: list(unrealsdk.find_all(str(c.Name), exact=True)), [])
                if "Default__" not in str(_try(o._path_name, ""))]
        if not objs:
            continue
        lines.append(f"== {len(objs)} {c.Name} objects")
        for n, o in enumerate(objs):
            if n < FULL:
                _dump(o, f"{c.Name} #{n}", only_matching=False)
            else:
                loc = _try(lambda o=o: o.Location, None)
                where = f" at ({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})" if loc is not None and hasattr(loc, "X") else ""
                lines.append(f"   #{n} {_brief(o)}{where}")
    # where a player's discovered areas / fog might be kept
    holders = {
        "pc": pc,
        "pawn": _try(lambda: pc.MyWillowPawn, None),
        "PRI": _try(lambda: pc.PlayerReplicationInfo, None),
        "HUD": _try(lambda: pc.myHUD, None),
        "WorldInfo": wi,
        "GameInfo": _try(lambda: wi.Game, None),
        "GRI": _try(lambda: wi.GRI, None),
        "MapInfo": _try(lambda: wi.GetMapInfo(), None),
    }
    for label, obj in holders.items():
        if obj is not None and not isinstance(obj, str):
            _dump(obj, f"{label} (related fields / functions)", only_matching=True)


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_discovery: {len(lines)} lines -> {OUT}")
