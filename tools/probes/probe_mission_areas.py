# Dev probe (in game), instant: where a mission's area name is - for grouping the mission log by
# area. Every mission's TravelStation / TurnInStation (FastTravelStationDefinition) and
# GameStageRegion (WillowRegionDefinition): the first few of each class dumped field by field, then
# every distinct one with its text fields; and how many missions point to each.
# Writes tools/probes/probe_mission_areas.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_mission_areas.py").read())
import enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_mission_areas.txt"  # the repo, through the mod's junction
FIELDS = ("TravelStation", "TurnInStation", "GameStageRegion")
FULL_EACH = 2  # objects of each class dumped field by field
STOP = {"Object", "GBXDefinition"}
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
        return f"{type(value).__name__}.{value.name}"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:6]) + "]"
    return repr(value)


def _props(obj):  # noqa: ANN001, ANN202
    c = obj.Class
    while c is not None and c.Name not in STOP:
        for f in c._fields():
            if f.Class.Name.endswith("Property"):
                yield c.Name, f
        c = c.SuperField


def main() -> None:
    lines.append("#" * 60)
    tracker = next((t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")), None)
    entries = list(_try(lambda: tracker.MissionList, []) or [])
    lines.append(f"{len(entries)} missions")
    seen: dict[int, list] = {}  # object address -> [object, field, missions pointing to it]
    for entry in entries:
        mdef = _try(lambda e=entry: e.MissionDef, None)
        if mdef is None or isinstance(mdef, str):
            continue
        for field in FIELDS:
            obj = _try(lambda f=field: getattr(mdef, f), None)
            if obj is None or isinstance(obj, str):
                continue
            seen.setdefault(obj._get_address(), [obj, field, []])[2].append(str(mdef.Name))
    dumped: dict[str, int] = {}
    for obj, field, missions in seen.values():
        cls = obj.Class.Name
        if dumped.get(cls, 0) < FULL_EACH:
            dumped[cls] = dumped.get(cls, 0) + 1
            lines.append(f"== {field}: {_brief(obj)} (full)")
            for owner, f in _props(obj):
                lines.append(f"   {owner}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
    lines.append("== every distinct one: text fields")
    for obj, field, missions in sorted(seen.values(), key=lambda v: (v[1], str(v[0].Name))):
        texts = {f.Name: _try(lambda f=f: obj._get_field(f)) for _, f in _props(obj) if f.Class.Name == "StrProperty"}
        texts = {k: v for k, v in texts.items() if v}
        lines.append(f"{field:15} {_brief(obj)} x{len(missions)} {texts} e.g. {missions[:3]}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_mission_areas: {len(lines)} lines -> {OUT}")
