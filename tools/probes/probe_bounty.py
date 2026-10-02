# Dev probe (in game, any distance), instant: how a bounty board (the mission board: several missions in
# a submenu) says which missions it gives - it isn't a pawn, so the collector's quest givers (NPCs'
# MissionDirectives) miss it. Run it in a level with a board (Sanctuary).
# Logs: every interactive object of the level whose name / definition says bounty or board, or that has
# a non-empty mission-looking property - every property of it and of its definition (property reads
# only, no function called), and the MissionTracker's DynamicMissionDirectives / MissionDirectors.
# The file is written after each section (a crash keeps what came before).
# Writes tools/probes/probe_bounty.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bounty.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_bounty.txt"  # the repo, through the mod's junction
MISSIONISH = re.compile(r"mission|director|bounty", re.I)
SKIP = {"Object", "Actor", "GBXDefinition"}
lines: list[str] = []


def flush() -> None:
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
        return f"{value:.1f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:12]) + (f", ... ({len(value)})" if len(value) > 12 else "") + "]"
    return repr(value)


def props(obj) -> list[tuple[str, str, object]]:  # noqa: ANN001
    out, c = [], obj.Class
    while c is not None and c.Name not in SKIP:
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property"):
                out.append((str(c.Name), str(f.Name), _try(lambda f=f: obj._get_field(f), None)))
        c = c.SuperField
    return out


def dump(label: str, obj) -> None:  # noqa: ANN001
    lines.append(f"   --- {label}: {_brief(obj)}")
    for cls, name, value in props(obj):
        lines.append(f"      {cls}.{name} = {_try(lambda v=value: _brief(v))}")


def filled(value) -> bool:  # noqa: ANN001
    if value is None or isinstance(value, (bool, int, float)):
        return False  # (flags / numbers: not a mission list)
    if isinstance(value, str):
        return bool(value)
    return not (hasattr(value, "__len__") and len(value) == 0)


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    lines.append(f"map {_try(lambda: str(wi.GetStreamingPersistentMapName()))}")
    flush()
    ios = [io for io in unrealsdk.find_all("WillowInteractiveObject", exact=False) if not io.Name.startswith("Default__")]
    lines.append(f"{len(ios)} interactive objects")
    flush()
    shown = 0
    for io in ios:
        defn = _try(lambda io=io: io.InteractiveObjectDefinition, None)
        what = f"{io.Class.Name} {io.Name} {_try(lambda d=defn: d._path_name(), '')}".lower()
        missionish = [(c, n, v) for c, n, v in props(io) if MISSIONISH.search(n) and filled(v)]
        if not ("bounty" in what or "board" in what or missionish):
            continue
        shown += 1
        loc = _try(lambda io=io: io.Location, None)
        lines.append(f"== {io.Class.Name} {_try(io._path_name)} def={_brief(defn)} at "
                     f"{_try(lambda l=loc: (round(l.X), round(l.Y), round(l.Z)))}")
        for c, n, v in missionish:
            lines.append(f"   (missionish) {c}.{n} = {_try(lambda v=v: _brief(v))}")
        dump("object", io)
        if defn is not None and not isinstance(defn, str):
            dump("definition", defn)
        flush()
    lines.append(f"{shown} shown")
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    for t in trackers[:1]:
        lines.append(f"== tracker DynamicMissionDirectives = {_try(lambda t=t: _brief(t.DynamicMissionDirectives))}")
        lines.append(f"== tracker MissionDirectors = {_try(lambda t=t: _brief(t.MissionDirectors))}")
    flush()


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
flush()
