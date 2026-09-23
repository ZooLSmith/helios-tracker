# Dev probe (in game), instant: the level of the area the player is in - for the panel, under the
# level's name. Run it in a normal area (enemies around helps).
# Logs: region / game stage related properties and functions on the controller, pawn, world info,
# game info and replication info; every WillowRegionDefinition (the first ones in full, the others one
# line) with pc.GetGameStageFromRegion(region) - and which ones the missions of this map point to
# (MissionDefinition.GameStageRegion, their TravelStation in this map); the enemies' levels here.
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_region.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_region.py").read())
import enum
import re
from collections import Counter
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_region.txt")
PATTERN = re.compile(r"region|gamestage|stage|arealevel|explevel|zonelevel|awesome", re.I)
SCALARS = {"StrProperty", "NameProperty", "ObjectProperty", "ByteProperty", "IntProperty", "BoolProperty",
           "FloatProperty", "ArrayProperty", "StructProperty"}
STOP = {"Object"}
FULL = 3
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
        return f"{value:.2f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name in SCALARS) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:8]) + (f", ... ({len(value)})" if len(value) > 8 else "") + "]"
    return repr(value)


def _related(obj, label: str) -> None:  # noqa: ANN001
    """obj's properties and functions whose name matches PATTERN."""
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in STOP:
        for f in _try(lambda c=c: list(c._fields()), []):
            if not PATTERN.search(str(f.Name)):
                continue
            if f.Class.Name == "Function":
                params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(params)})")
            elif f.Class.Name in SCALARS:
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _dump(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"   -- {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name not in STOP | {"GBXDefinition"}:
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name in SCALARS:
                lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    map_name = _try(lambda: str(wi.GetStreamingPersistentMapName()), "")
    lines.append(f"map: {map_name}")
    for obj, label in ((pc, "controller"), (_try(lambda: pc.Pawn, None), "pawn"), (wi, "world info"),
                       (_try(lambda: wi.Game, None), "game info"), (_try(lambda: wi.GRI, None), "game replication info"),
                       (_try(lambda: pc.PlayerReplicationInfo, None), "player replication info")):
        if obj is not None and not isinstance(obj, str):
            _related(obj, label)

    # the regions the missions of this map point to
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    here: Counter = Counter()
    for e in _try(lambda: list(trackers[0].MissionList), []) if trackers else []:
        m = _try(lambda e=e: e.MissionDef, None)
        if _try(lambda m=m: str(m.TravelStation.StationLevelName), "").lower() == map_name.lower():
            here[_try(lambda m=m: m.GameStageRegion._path_name(), "?")] += 1
    lines.append(f"== regions of this map's missions: {dict(here)}")

    regions = [r for r in _try(lambda: list(unrealsdk.find_all("WillowRegionDefinition", exact=False)), [])
               if not r.Name.startswith("Default__")]
    lines.append(f"== {len(regions)} WillowRegionDefinition objects (this map's missions' first)")
    regions.sort(key=lambda r: (_try(r._path_name, "") not in here, _try(r._path_name, "")))
    for n, r in enumerate(regions):
        stage = _try(lambda r=r: _brief(pc.GetGameStageFromRegion(r)))
        if n < FULL:
            _dump(r, f"region (GetGameStageFromRegion = {stage})")
        else:
            lines.append(f"   {_try(r._path_name)}  stage={stage}")

    # for comparison: the enemies' levels here
    levels, p = Counter(), _try(lambda: wi.PawnList, None)
    for _ in range(2000):
        if p is None or isinstance(p, str):
            break
        if _try(lambda p=p: bool(p.IsEnemy(pc.Pawn)), False):
            levels[_try(lambda p=p: int(p.GetExpLevel()), -1)] += 1
        p = _try(lambda p=p: p.NextPawn, None)
    lines.append(f"== enemy levels here (level: count): {dict(sorted(levels.items()))}")
    lines.append(f"player level: {_try(lambda: pc.PlayerReplicationInfo.ExpLevel)}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_region: {len(lines)} lines -> {OUT}")
