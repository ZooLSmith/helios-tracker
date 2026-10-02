# Dev probe (in game, as a co-op CLIENT), instant: what the HUD minimap's icon lists hold - on a client
# there are no mission waypoint components (tools/probes/probe_client_markers.txt), but the minimap still shows
# the objectives: where does it get them? Run it with a mission tracked whose marker the HUD shows.
# Logs: each Icons_* list of the minimap (Objective, AreaObjective, AreaObjectiveSticky,
# MissionEligible, MissionRedeemable): every entry, field by field (a struct / object: nested one level)
# - which ones are in use, what they point at (an actor? a location? a radius?); and the minimap's
# other fields whose name looks objective / mission / icon related.
# Writes tools/probes/probe_minimap_icons.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_minimap_icons.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_minimap_icons.txt"  # the repo, through the mod's junction
LISTS = ("Icons_Objective", "Icons_AreaObjective", "Icons_AreaObjectiveSticky", "Icons_MissionEligible", "Icons_MissionRedeemable")
PATTERN = re.compile(r"objective|mission|waypoint|icon|target|marker", re.I)
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
        return f"{value:.1f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        extra = ""
        loc = _try(lambda: value.Location, None)
        if loc is not None and hasattr(loc, "X"):
            extra = f" @({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})"
        return f"{value.Class.Name}'{_try(value._path_name)}'{extra}"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:6]) + (f", ... ({len(value)})" if len(value) > 6 else "") + "]"
    return repr(value)


def _fields(obj, label: str) -> None:  # noqa: ANN001
    """An object's own properties (a GFxObject / icon holder), one line each."""
    lines.append(f"      {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in ("Object", "GFxObject"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property"):
                lines.append(f"         {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    maps = [m for m in _try(lambda: list(unrealsdk.find_all("HUDWidget_Minimap", exact=False)), []) if not m.Name.startswith("Default__")]
    lines.append(f"{len(maps)} HUDWidget_Minimap: {[m.Name for m in maps]}")
    for mm in maps[:1]:
        for name in LISTS:
            items = _try(lambda n=name: list(getattr(mm, n)), [])
            lines.append(f"== {name}: {len(items) if isinstance(items, list) else items} entries")
            for i, it in enumerate(items if isinstance(items, list) else []):
                lines.append(f"   [{i}] {_brief(it)}")
                if i < 3 and hasattr(it, "Class") and not isinstance(it, str):  # an object: its fields, for the first few
                    _fields(it, "fields")
        lines.append("== the minimap's other objective / mission / icon fields")
        c = mm.Class
        while c is not None and c.Name != "Object":
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)) and str(f.Name) not in LISTS:
                    lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(mm._get_field(f)))}")
                elif f.Class.Name == "Function" and PATTERN.search(str(f.Name)):
                    params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                    lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
            c = c.SuperField


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_minimap_icons: {len(lines)} lines -> {OUT}")
