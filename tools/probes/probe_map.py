# Dev probe (in game), instant: current map name, its WillowMapInfo / tactical map volume, and the
# numbers needed to convert world positions to tactical map pixels.
# Run it twice, standing at two different spots, ideally once with the map (status menu) open.
# Writes tools/probes/probe_map.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_map.py").read())
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_map.txt"  # the repo, through the mod's junction
INTERESTING = re.compile(r"(?i)map|scale|unit|pixel|north|yaw|offset|transform|center|size|radius|location|volume")

lines: list[str] = []


def _try(fn):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"


def _fields(obj, label: str, match: re.Pattern | None = INTERESTING) -> None:  # noqa: ANN001
    """Relevant properties with values."""
    lines.append(f"== {label}: {_try(lambda: obj._path_name()) if obj is not None else None}")
    if obj is None or isinstance(obj, (str, tuple)):
        return
    c = obj.Class
    seen = set()
    while c is not None:
        for f in c._fields():
            if f.Name in seen or not f.Class.Name.endswith("Property") or (match and not match.search(f.Name)):
                continue
            seen.add(f.Name)
            v = _try(lambda f=f: obj._get_field(f))
            if hasattr(v, "_path_name"):
                v = _try(lambda v=v: v._path_name())
            lines.append(f"  {f.Class.Name.replace('Property', '')} {f.Name} = {v}")
        c = c.SuperField


pc = get_pc()
wi = ENGINE.GetCurrentWorldInfo()
lines.append("#" * 60)
lines.append(f"GetStreamingPersistentMapName = {_try(wi.GetStreamingPersistentMapName)}")
lines.append(f"GetMapName(False) = {_try(lambda: wi.GetMapName(False))}")
lines.append(f"GetMapName(True) = {_try(lambda: wi.GetMapName(True))}")
lines.append(f"player Location = {_try(lambda: pc.Pawn.Location)}  Rotation = {_try(lambda: pc.Pawn.Rotation)}")

info = _try(wi.GetMapInfo)
lines.append(f"GetMapInfo() = {info}  MyMapInfo = {_try(lambda: wi.MyMapInfo)}")
if hasattr(info, "Class"):
    _fields(info, "WillowMapInfo", None)
    vol = _try(lambda: info.TacticalMapVolume)
    if hasattr(vol, "Class"):
        _fields(vol, "TacticalMapVolume")
        _fields(_try(lambda: vol.BrushComponent), "  BrushComponent", re.compile(r"(?i)bounds|scale|translation"))

for cls in ("HUDWidget_Minimap", "StatusMenuMapGFxObject"):
    for o in unrealsdk.find_all(cls, exact=False):
        if not o.Name.startswith("Default__"):
            _fields(o, cls)

for vol in unrealsdk.find_all("WillowTacticalMapVolume", exact=False):
    if not vol.Name.startswith("Default__"):
        lines.append(f"volume in memory: {vol._path_name()} Location={_try(lambda v=vol: v.Location)}")

with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"[probe_map] {len(lines)} lines -> {OUT}")
