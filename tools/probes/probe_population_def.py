# Dev probe (in game), instant, read-only: what a population point spawns (design.md "Containers before they spawn",
# question 1). The level's PopulationOpportunityPoints (chests, coolers, cash boxes, piles: notes.md "Containers spawned
# by distance") each have a PopulationDef (PopulationDefinition:CashBox, WeaponChest_White...) - which object definition
# / balance / archetype does it give, with what weight, can it give nothing?
# 1. the level's distinct PopulationDefs (how many points each, how many spawned now);
# 2. each one as a tree: every property - structs and arrays opened (an array's first MAX_ITEMS), objects it points to
#    followed MAX_DEPTH deep - read, nothing called;
# 3. one spawned point (bHasSpawned) in full: its own properties the same way (a reference to what it spawned?).
# Writes tools/probes/probe_population_def.txt (overwrites; definition by definition)
#   py exec(open(r"<repo>\tools\probes\probe_population_def.py").read())
import enum
import sys
from collections import defaultdict
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_population_def.txt"  # the repo, through the mod's junction
MAX_DEPTH = 4  # objects / structs followed this deep
MAX_ITEMS = 6  # an array's entries opened
MAX_DEFS = 25  # population definitions dumped
SKIP_FIELDS = {"Outer", "Class", "ObjectArchetype", "ObjectFlags", "VfTableObject", "HashNext", "HashOuterNext",
               "StateFrame", "_Linker", "_LinkerIndex", "NetIndex", "Name"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:120] if default == "<err>" else default


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _is_object(value) -> bool:  # noqa: ANN001
    return hasattr(value, "_path_name") and hasattr(value, "Class")


def _is_array(value) -> bool:  # noqa: ANN001
    return type(value).__name__ == "WrappedArray" or isinstance(value, (list, tuple))


def _is_struct(value) -> bool:  # noqa: ANN001
    # (a WrappedArray has a _type too - its inner property: tested first, _is_array)
    return hasattr(type(value), "_type") and not _is_object(value) and not _is_array(value)


def _fields_of(cls) -> list:  # noqa: ANN001
    """A class's / struct's properties, its chain up to Object."""
    out, seen, c = [], set(), cls
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            if str(f.Class.Name).endswith("Property") and str(f.Name) not in seen and str(f.Name) not in SKIP_FIELDS:
                seen.add(str(f.Name))
                out.append(f)
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _show(label: str, value, indent: int, depth: int, visited: set) -> None:  # noqa: ANN001
    pad = "   " * indent
    if value is None:
        lines.append(f"{pad}{label} = None")
    elif isinstance(value, enum.Enum):
        lines.append(f"{pad}{label} = {value.name}")
    elif isinstance(value, (bool, int, float, str)):
        lines.append(f"{pad}{label} = {value!r}"[:200])
    elif _is_object(value):
        key = _try(lambda: value._get_address(), id(value))
        path = _try(lambda: value._path_name(), str(value.Name))
        lines.append(f"{pad}{label} = {value.Class.Name}'{path}'")
        if depth < MAX_DEPTH and key not in visited:
            visited.add(key)
            for f in _fields_of(value.Class):
                _show(str(f.Name), _try(lambda f=f: value._get_field(f)), indent + 1, depth + 1, visited)
    elif _is_struct(value):
        lines.append(f"{pad}{label} = struct {_try(lambda: value._type.Name, '?')}")
        if depth < MAX_DEPTH:
            for f in _fields_of(value._type):
                _show(str(f.Name), _try(lambda f=f: value._get_field(f)), indent + 1, depth + 1, visited)
    elif _is_array(value) or (hasattr(value, "__len__") and hasattr(value, "__getitem__")):
        items = _try(lambda: list(value), [])
        lines.append(f"{pad}{label} = [{len(items)} entries]")
        for n, item in enumerate(items[:MAX_ITEMS]):
            _show(f"[{n}]", item, indent + 1, depth, visited)
    else:
        lines.append(f"{pad}{label} = {value!r}"[:200])


OUT.write_text("", encoding="utf-8")
points = [p for p in _try(lambda: list(unrealsdk.find_all("PopulationOpportunityPoint", exact=False)), []) or []
          if not p.Name.startswith("Default__")]
by_def: dict[int, list] = defaultdict(list)
defs = {}
for p in points:
    d = _try(lambda p=p: p.PopulationDef, None)
    if d is not None and not isinstance(d, str):
        by_def[d._get_address()].append(p)
        defs[d._get_address()] = d

# --- 1. the definitions
lines.append(f"== {len(points)} PopulationOpportunityPoints, {len(defs)} PopulationDefs (points, spawned now)")
for key, d in sorted(defs.items(), key=lambda kv: -len(by_def[kv[0]])):
    spawned = sum(1 for p in by_def[key] if _try(lambda p=p: p.bHasSpawned, False) is True)
    lines.append(f"   {len(by_def[key]):3} points, {spawned:3} spawned  {d.Class.Name}'{_try(d._path_name, d.Name)}'")
_flush()

# --- 2. each definition as a tree
for key, d in list(sorted(defs.items(), key=lambda kv: -len(by_def[kv[0]])))[:MAX_DEFS]:
    lines.append("")
    lines.append(f"== {d.Class.Name}'{_try(d._path_name, d.Name)}' ({len(by_def[key])} points)")
    _show("def", d, 1, 0, set())
    _flush()

# --- 3. one spawned point in full
spawned_point = next((p for p in points if _try(lambda p=p: p.bHasSpawned, False) is True), None)
lines.append("")
if spawned_point is None:
    lines.append("== no spawned point now (go within 80 m of a container's point, run again)")
else:
    lines.append(f"== a spawned point: {spawned_point.Name} ({_try(lambda: spawned_point.PopulationDef.Name)})")
    for f in _fields_of(spawned_point.Class):  # (its objects shown by name, one level opened)
        _show(str(f.Name), _try(lambda f=f: spawned_point._get_field(f)), 1, MAX_DEPTH - 1, set())
_flush()
print(f"[probe_population_def] -> {OUT}")
