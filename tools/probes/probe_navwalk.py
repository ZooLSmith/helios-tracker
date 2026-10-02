# Dev probe (in game), 60 min in the background: where the player really walks, to check the level's nav mesh
# (GBXNavMesh, see .agent/notes.md "Level geometry for a 3D map") covers it - checked offline by
# tools/probes/check_navwalk.py. Walk / drive around a few levels (rooftops, ledges, stairs, places without enemies).
# Logs, reading properties only (the collector's own reads):
#  - per level: its map name, the tactical map movie, the volume's bounds centre, UnrealUnitsPerPixel and
#    NorthOffsetInDegreesClockwise (the runtime values: checks the 2D map's rotation too);
#  - every 0.5 s, when the pawn moved more than 1 m: its feet (Location.Z - collision half height), its Physics,
#    its class (a vehicle's differs).
# Again: restarts. Stop early: py helios_navwalk_stop()
# Writes tools/probes/probe_navwalk.txt (overwrites; every 5 s)
#   py exec(open(r"<repo>\tools\probes\probe_navwalk.py").read())
import builtins
import sys
import time
from pathlib import Path

from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_navwalk.txt"  # the repo, through the mod's junction
RUN_FOR = 60 * 60.0
SAMPLE_EVERY = 0.5
FLUSH_EVERY = 5.0
MIN_MOVE = 100.0  # uu
HOOK_ID = "helios_probe_navwalk"
RENDER = "WillowGame.WillowGameViewportClient:PostRender"
lines: list[str] = ["# L map movie centerX centerY upp north | P t map x y feetZ physics pawnClass"]
state = {"start": time.perf_counter(), "next": 0.0, "flush": 0.0, "level": None, "last": None, "errors": set()}


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _enum_name(v) -> str:  # noqa: ANN001
    return str(getattr(v, "name", v))


def _stop() -> None:
    remove_hook(RENDER, Type.POST, HOOK_ID)
    lines.append(f"# stopped at {time.perf_counter() - state['start']:.1f} s")
    _flush()


def _tick(*_args) -> None:  # noqa: ANN002
    now = time.perf_counter() - state["start"]
    if now < state["next"]:
        return
    state["next"] = now + SAMPLE_EVERY
    try:
        if now > RUN_FOR:
            _stop()
            return
        wi = ENGINE.GetCurrentWorldInfo()
        if wi is None:
            return
        name = str(wi.GetStreamingPersistentMapName())
        if name != state["level"]:
            state["level"] = name
            state["last"] = None
            info = wi.GetMapInfo()
            vol = info.TacticalMapVolume if info is not None else None
            movie = info.TacticalMapMovie if info is not None else None
            if vol is not None:
                c = vol.BrushComponent.Bounds.Origin
                lines.append(f"L\t{name}\t{movie._path_name() if movie is not None else ''}\t{c.X:.1f}\t{c.Y:.1f}\t"
                             f"{vol.UnrealUnitsPerPixel}\t{vol.NorthOffsetInDegreesClockwise}")
            else:
                lines.append(f"L\t{name}\t\t\t\t\t")
        pawn = get_pc().Pawn
        if pawn is not None:
            loc = pawn.Location
            last = state["last"]
            if last is None or (loc.X - last[0]) ** 2 + (loc.Y - last[1]) ** 2 + (loc.Z - last[2]) ** 2 > MIN_MOVE**2:
                state["last"] = (loc.X, loc.Y, loc.Z)
                cyl = pawn.CylinderComponent
                feet = loc.Z - (cyl.CollisionHeight if cyl is not None else 0.0)
                lines.append(f"P\t{now:.1f}\t{name}\t{loc.X:.1f}\t{loc.Y:.1f}\t{feet:.1f}\t"
                             f"{_enum_name(pawn.Physics)}\t{pawn.Class.Name}")
    except Exception as e:  # noqa: BLE001
        key = f"{type(e).__name__}: {e}"
        if key not in state["errors"]:
            state["errors"].add(key)
            lines.append(f"# error at {now:.1f} s: {key}")
    if now >= state["flush"]:
        state["flush"] = now + FLUSH_EVERY
        _flush()


remove_hook(RENDER, Type.POST, HOOK_ID)
add_hook(RENDER, Type.POST, HOOK_ID, _tick)
builtins.helios_navwalk_stop = _stop
lines.append(f"# started, {RUN_FOR / 60:.0f} min")
_flush()
