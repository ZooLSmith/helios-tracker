# Dev probe (in game), instant: where a level's discovery areas' names are (the Pre-Sequel, Pity's Fall: its
# WorldDiscoveryArea has WorldAreaDisplayString, not BL2's WorldAreaDisplayName - and it's empty on every area).
# Dumps every property's value (no functions) of the first few areas that aren't fog-only, then of the objects they
# point to (BalanceToRegionDef...), one level deep. Read-only (properties, no calls).
# Run it in a level with area names (the Pre-Sequel: Pity's Fall).
# Writes tools/probes/probe_areas.txt (overwrites; after each object)
#   py exec(open(r"<repo>\tools\probes\probe_areas.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_areas.txt"  # the repo, through the mod's junction
AREAS = 4  # areas dumped in full
lines: list[str] = []


def _write() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def _dump(obj, label: str, stop_at: str = "Actor") -> list:  # noqa: ANN001
    """Every property of obj's own classes (up to stop_at), its object references returned."""
    lines.append(f"== {label}: {_brief(obj)}")
    refs = []
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in (stop_at, "Object"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if not f.Class.Name.endswith("Property"):
                continue
            value = _try(lambda f=f: obj._get_field(f))
            lines.append(f"  {c.Name}.{f.Name} ({f.Class.Name}): {_brief(value)}")
            if f.Class.Name == "ObjectProperty" and hasattr(value, "_path_name"):
                refs.append((f.Name, value))
        c = _try(lambda c=c: c.SuperField, None)
    _write()
    return refs


areas = [a for a in unrealsdk.find_all("WorldDiscoveryArea", exact=False)
         if not a.Name.startswith("Default__") and not _try(lambda a=a: a.bForFogOfWarOnly, True)]
lines.append(f"areas not fog-only: {len(areas)}")
_write()
seen = set()
for a in areas[:AREAS]:
    for name, ref in _dump(a, "area"):
        key = _try(ref._path_name)
        if key not in seen:
            seen.add(key)
            _dump(ref, f"{name} of {a.Name}", stop_at="")
lines.append("== the others, their name-like fields")
for a in areas[AREAS:]:
    lines.append(f"  {a.Name}: CustomName {_try(lambda a=a: str(a.CustomName))}, "
                 f"WorldAreaDisplayString {_try(lambda a=a: repr(a.WorldAreaDisplayString))}, "
                 f"BalanceToRegionDef {_brief(_try(lambda a=a: a.BalanceToRegionDef))}")
lines.append("done")
_write()
