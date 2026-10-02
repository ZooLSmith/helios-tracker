# Dev probe (in game): the current map's streaming sublevels and their state right now - for the 3D map study
# (.agent/notes.md "Level geometry for a 3D map"): the extraction reads every sublevel the map lists from the files;
# this tells whether the game has them all loaded / visible, or switches some by script (LevelStreamingKismet).
# Reads properties only. Run it right after a level loads, then again elsewhere / after a mission step: each run
# appends a snapshot.
# Appends to tools/probes/probe_streaming.txt
#   py exec(open(r"<repo>\tools\probes\probe_streaming.py").read())
import sys
import time
from pathlib import Path

from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_streaming.txt"  # the repo, through the mod's junction
FLAGS = ("bShouldBeLoaded", "bShouldBeVisible", "bIsVisible", "bHasLoadRequestPending", "bHasUnloadRequestPending",
         "bIsRequestingUnloadAndRemoval", "bShouldBlockOnLoad")


def _try(fn, default=None):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _snapshot() -> list[str]:
    wi = ENGINE.GetCurrentWorldInfo()
    pawn = _try(lambda: get_pc().Pawn)
    loc = _try(lambda: pawn.Location)
    where = f"{loc.X:.0f} {loc.Y:.0f} {loc.Z:.0f}" if loc is not None else "?"
    lines = [f"== {time.strftime('%H:%M:%S')} {wi.GetStreamingPersistentMapName()} - player at {where}"]
    for s in wi.StreamingLevels:
        if s is None:
            continue
        loaded = _try(lambda s=s: s.LoadedLevel is not None, "?")
        flags = " ".join(f"{f}={int(v)}" for f in FLAGS if (v := _try(lambda s=s, f=f: getattr(s, f))) is not None)
        lines.append(f"  {s.Class.Name:28s} {str(s.PackageName):28s} loaded={loaded!s:5s} {flags}")
    return lines


out = _snapshot()
with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(out) + "\n")
print("\n".join(out))
