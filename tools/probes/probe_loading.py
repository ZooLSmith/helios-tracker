# Dev probe (in game), 15 min in the background: how to tell a loading screen is up - yours (a level change,
# a fast travel, quitting to the menu) and, in co-op, another player's. Start it, then change level / fast
# travel (and, in co-op, have someone else do it).
# Logs, with the time since the start:
#  - every call of a game function named like travel / loading movie / load map / seamless / transition /
#    level streaming / login / possess (hooked), with its arguments;
#  - gaps: the game not rendering frames (the loading screen itself?);
#  - every 0.25 s (changes only): the map, your controller / pawn, the controller's loading movie flags,
#    and every player's replication info (the GRI's PRIArray): name, pawn or not, and their fields named
#    like loading / travel / ready / spectator / waiting (listed once at the start).
# Again: restarts. Stop early: py helios_loading_stop()
# Writes tools/probes/probe_loading.txt (overwrites; as it goes)
#   py exec(open(r"<repo>\tools\probes\probe_loading.py").read())
import builtins
import enum
import re
import time
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_loading.txt"  # the repo, through the mod's junction
RUN_FOR = 15 * 60.0
SAMPLE_EVERY = 0.25
GAP = 1.0
HOOK_ID = "helios_probe_loading"
RENDER = "WillowGame.WillowGameViewportClient:PostRender"
FUNC_PATTERN = re.compile(r"travel|loadingmovie|loadmap|loadlevel|loadedworld|seamless|findplaymovie|stopmovie|"
                          r"transition|levelstreaming|prelogin|postlogin|logout|possess|notifyloaded|restartplayer|"
                          r"switchlevel|mapchange|loadingscreen", re.I)
FUNC_SKIP = re.compile(r"^(Get|Is|Has|Can|Should)|Tick|Update(?!LevelStreaming)|Render", re.I)  # per-frame / queries
MAX_HOOKS = 400
PRI_PATTERN = re.compile(r"load|travel|ready|spectat|waiting|outofgame|inactive|bIsBot|bBot$|bHasBeenWelcomed|StartTime", re.I)
lines: list[str] = []


def _try(fn, default=None):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.2f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value.Name}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return f"(len {len(value)})"
    return repr(value)


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _pri_fields(pri) -> list:  # noqa: ANN001
    out, c = [], _try(lambda: pri.Class)
    while c is not None and c.Name != "Object":
        out += [f for f in _try(lambda c=c: list(c._fields()), []) or []
                if f.Class.Name.endswith("Property") and PRI_PATTERN.search(str(f.Name))]
        c = c.SuperField
    return out


def _sample() -> dict[str, str]:
    pc = get_pc(possibly_loading=True)
    wi = ENGINE.GetCurrentWorldInfo()
    reads = {
        "map": lambda: wi.GetStreamingPersistentMapName(),
        "pc": lambda: pc,
        "pc.Pawn": lambda: pc.Pawn,
        "pc.bWantsToDisableLoadingMovie": lambda: pc.bWantsToDisableLoadingMovie,
        "pc.WaitTimeToDisableLoadingMovie": lambda: round(float(pc.WaitTimeToDisableLoadingMovie), 1),
        "pc.bStopgapBlockForDeferredMovies": lambda: pc.bStopgapBlockForDeferredMovies,
        "pc.LoadingMovieLoadedLevelNames": lambda: len(pc.LoadingMovieLoadedLevelNames),
        "pc.bCinematicMode": lambda: pc.bCinematicMode,
        "wi.NetMode": lambda: wi.NetMode,
    }
    out = {k: _try(lambda f=f: _brief(f()), "<err>") for k, f in reads.items()}
    for n, pri in enumerate(_try(lambda: list(wi.GRI.PRIArray), []) or []):
        fields = state["pri_fields"].setdefault(str(_try(lambda: pri.Class.Name, "?")), _pri_fields(pri))
        name = _try(lambda: str(pri.PlayerName), "?")
        pawn = _try(lambda: _brief(pri.Owner.Pawn), "?")  # (its controller's pawn: the host has every controller)
        values = ", ".join(f"{f.Name}={_try(lambda f=f: _brief(pri._get_field(f)), '?')}" for f in fields)
        out[f"PRI[{n}]"] = f"{name}: pawn {pawn}; {values}"
    return out


def stop() -> None:
    remove_hook(RENDER, Type.POST, HOOK_ID)
    for f in state.get("hooked", []):
        remove_hook(f, Type.PRE, HOOK_ID)
    state["hooked"] = []
    lines.append(f"== stopped at {time.monotonic() - t0:.1f}s")
    _flush()
    print(f"[probe_loading] stopped -> {OUT}")


def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.monotonic()
    if now - t0 > RUN_FOR:
        stop()
        return
    if state["last_frame"] and now - state["last_frame"] > GAP:
        lines.append(f"  {now - t0:7.2f}s  ** no frame for {now - state['last_frame']:.1f}s")
    state["last_frame"] = now
    if now < state["next"]:
        return
    state["next"] = now + SAMPLE_EVERY
    values = _sample()
    changed = {k: v for k, v in values.items() if state["values"].get(k) != v}
    gone = [k for k in state["values"] if k not in values]
    if changed or gone:
        state["values"] = values
        lines.append(f"  {now - t0:7.2f}s  " + ", ".join(f"{k}={v}" for k, v in changed.items())
                     + (f" (gone: {', '.join(gone)})" if gone else ""))
        _flush()


def _args(args) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(args._type._fields()), []) or []:
        flags = _try(lambda f=f: f.PropertyFlags, 0x80)
        if f.Class.Name.endswith("Property") and flags & 0x80 and not flags & 0x400:  # parameters, not the return value
            out.append(f"{f.Name}={_try(lambda f=f: _brief(args._get_field(f)), '?')}")
    return ", ".join(out)


def on_call(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    now = time.monotonic()
    lines.append(f"  {now - t0:7.2f}s  call {_try(lambda: func.func._path_name(), '?')}({_args(args)}) on {_brief(obj)}")
    _flush()


if callable(getattr(builtins, "helios_loading_stop", None)):
    try:
        builtins.helios_loading_stop()
    except Exception:  # noqa: BLE001
        pass
t0 = time.monotonic()
state: dict = {"next": 0.0, "last_frame": 0.0, "values": {}, "hooked": [], "pri_fields": {}}
builtins.helios_loading_stop = stop
try:
    lines.append(f"== started {time.strftime('%H:%M:%S')}, map {ENGINE.GetCurrentWorldInfo().GetStreamingPersistentMapName()}")
    funcs = []
    for f in unrealsdk.find_all("Function", exact=True):
        path = _try(f._path_name, "")
        name = str(f.Name)
        if FUNC_PATTERN.search(name) and not FUNC_SKIP.search(name) and path.split(".")[0] in ("WillowGame", "Engine", "GearboxFramework", "GameFramework"):
            funcs.append(path)
    for path in sorted(set(funcs))[:MAX_HOOKS]:
        if _try(lambda p=path: add_hook(p, Type.PRE, HOOK_ID, on_call) or True, False):
            state["hooked"].append(path)
    lines.append(f"== hooked {len(state['hooked'])} functions: {', '.join(p.rpartition('.')[2] for p in state['hooked'])}")
    pri0 = _try(lambda: ENGINE.GetCurrentWorldInfo().GRI.PRIArray[0])
    if pri0 is not None:
        lines.append(f"== PRI fields sampled: {', '.join(str(f.Name) for f in _pri_fields(pri0))}")
    add_hook(RENDER, Type.POST, HOOK_ID, tick)
    _flush()
    print(f"[probe_loading] watching for {RUN_FOR / 60:.0f} min - change level / fast travel; stop early: py helios_loading_stop()")
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    _flush()
    stop()
