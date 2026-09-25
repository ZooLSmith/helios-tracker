# Dev probe (in game), instant: why the fog of war covers everything - this level's discovery areas vs
# the player's DiscoveredWorldAreas (every entry, uncovered or not) and FullyExploredAreas.
# Writes tools/probe_fog.txt (overwrites)
#   py exec(open(r"<repo>\tools\probe_fog.py").read())
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_fog.txt"  # the repo, through the mod's junction
lines: list[str] = []
try:
    pc = get_pc()
    wi = ENGINE.GetCurrentWorldInfo()
    lines.append(f"map: {wi.GetStreamingPersistentMapName()}  me at {pc.Pawn.Location.X:.0f}, {pc.Pawn.Location.Y:.0f}")
    lines.append("== this level's areas")
    for a in unrealsdk.find_all("WorldDiscoveryArea", exact=False):
        if a.Name.startswith("Default__"):
            continue
        lines.append(f"   {a.Name}: short={a.DefaultWorldAreaShortName!s} custom={a.bUseCustomName}/{a.CustomName!s}"
                     f" name={a.WorldAreaDisplayName!r} fogonly={a.bForFogOfWarOnly} r={a.DetectionRadius:.0f}"
                     f" at {a.Location.X:.0f}, {a.Location.Y:.0f} short()={_s if (_s := str(a.GetWorldAreaShortName())) else ''}"
                     f" players={len(a.PlayersDetected)}")
    entries = list(pc.DiscoveredWorldAreas)
    lines.append(f"== pc.DiscoveredWorldAreas: {len(entries)}")
    for e in entries:
        lines.append(f"   {e.DiscoveryName!s} uncovered={e.HasBeenUncovered}")
    lines.append(f"== pc.FullyExploredAreas: {[str(m) for m in pc.FullyExploredAreas]}")
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"probe_fog: {len(lines)} lines -> {OUT}")
