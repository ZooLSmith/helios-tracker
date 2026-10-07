# Dev probe (in game, Borderlands 1), instant: the missions on a co-op CLIENT - the mod shows none there, nothing logged
# (Bl1Missions.entries: the controller's MissionPlaythroughData[GRI.HostCurrentPlaythrough].MissionList - None when the
# playthrough's entry isn't there). What a client has: its own log, the host's (replicated?), the tracker's.
# Logs:
#  - the net mode; the GRI's HostCurrentPlaythrough and its fields about missions / playthroughs;
#  - the local controller's MissionPlaythroughData (each entry: PlayThroughNumber, ActiveMission, its MissionList's
#    length and first entries - definition, status, progress), its other fields about missions;
#  - the local player info's fields about missions;
#  - every MissionTracker-like actor: its fields about missions (MissionList, ActiveMission...), the first entries;
#  - the other players' controllers / player infos, if any, their mission fields.
# Reads properties only (no function called). The output is written after each section.
# Run it in BL1 as a co-op CLIENT, the host with missions picked up (and you too, if possible).
# Writes tools/probes/probe_bl1_client_missions.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bl1_client_missions.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_client_missions.txt"  # the repo, through the mod's junction
FIELDS = re.compile(r"mission|playthrough|quest|objective", re.I)
lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0, items_max: int = 8) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1, items_max))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1, items_max) for v in items[:items_max]) + "]"
    return repr(value)


def _fields(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and FIELDS.search(str(f.Name)):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    gri = _try(lambda: wi.GRI, None)
    lines.append(f"netmode: {_brief(_try(lambda: wi.NetMode))}  local pc: {_brief(pc)}  "
                 f"GRI.HostCurrentPlaythrough: {_try(lambda: gri.HostCurrentPlaythrough)}")
    _save()
    if gri is not None and not isinstance(gri, str):
        _fields(gri, "GRI: mission / playthrough fields")
        _save()
    # the local controller's mission data, per playthrough
    data = _try(lambda: list(pc.MissionPlaythroughData), [])
    lines.append(f"== local controller MissionPlaythroughData: {len(data) if isinstance(data, list) else data} entries")
    for n, entry in enumerate(data if isinstance(data, list) else []):
        mission_list = _try(lambda e=entry: list(e.MissionList), [])
        lines.append(f"   [{n}] PlayThroughNumber={_try(lambda e=entry: e.PlayThroughNumber)} "
                     f"ActiveMission={_brief(_try(lambda e=entry: e.ActiveMission))} MissionList len {len(mission_list)}")
        for m in mission_list[:10]:
            lines.append(f"      {_brief(_try(lambda m=m: m.MissionDef))} {_brief(_try(lambda m=m: m.Status))} "
                         f"{_brief(_try(lambda m=m: m.Objectives))}")
    _save()
    _fields(pc, "local controller: mission fields")
    _save()
    _fields(_try(lambda: pc.PlayerReplicationInfo, None), "local player info: mission fields")
    _save()
    # the mission trackers
    for cls in ("MissionTracker", "WillowMissionTracker"):
        for tracker in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or []:
            if str(tracker.Name).startswith("Default__"):
                continue
            _fields(tracker, f"{cls} {_try(tracker._path_name)}")
            _save()
    # the other players' controllers / player infos
    for other in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), []) or []:
        if str(other.Name).startswith("Default__") or other._get_address() == pc._get_address():
            continue
        _fields(other, f"another controller {other.Name}")
        _save()
    for pri in _try(lambda: list(unrealsdk.find_all("WillowPlayerReplicationInfo", exact=False)), []) or []:
        if str(pri.Name).startswith("Default__"):
            continue
        _fields(pri, f"player info {pri.Name} ({_try(lambda p=pri: p.PlayerName)})")
        _save()


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
print(f"probe_bl1_client_missions: {len(lines)} lines -> {OUT}")
