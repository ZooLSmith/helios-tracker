# Dev probe (in game), 15 min in the background: how to tell a cutscene (a video or a scripted one) is
# playing - the console can't be opened during a video. Start it, then play through a cutscene.
# Logs, with the time since the start:
#  - the candidates from tools/probe_cutscene.txt, every 0.25 s (changes only): the controller's
#    cinematic mode flags / ignored input / view target / ECHO video, the GRI's bAllInCinematicMode, the
#    HUD's bShowHUD, the pawn's bUnderMatineeControl, the world's bPlayersOnly;
#  - gaps: the game not rendering frames (PostRender silent more than 1 s: a video playing?);
#  - when cinematic mode turns on (and 2 s later): the Matinee sequences playing - their position,
#    length (the InterpData plugged in), flags - an in-engine cutscene's progress;
#  - every call of a game function named like movie / cinematic / matinee / cutscene / bink (hooked),
#    with its arguments (the movie's name...) and the time since the previous call (a video's length).
# Again: restarts. Stop early: py helios_cutscene_stop()
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_cutscene_watch.txt (overwrites; as it goes)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_cutscene_watch.py").read())
import builtins
import enum
import re
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_cutscene_watch.txt")
RUN_FOR = 15 * 60.0
SAMPLE_EVERY = 0.25
GAP = 1.0
HOOK_ID = "helios_probe_cutscene"
RENDER = "WillowGame.WillowGameViewportClient:PostRender"
FUNC_PATTERN = re.compile(r"movie|cinemat|matinee|cutscene|bink", re.I)
FUNC_SKIP = re.compile(r"^(Get|Is|Has|Can|Should)|Tick|Update|Render|Loading", re.I)  # per-frame / queries: noise
MAX_HOOKS = 400
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
    return repr(value)


def _flush() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _sample() -> dict[str, str]:
    pc = get_pc()
    wi = ENGINE.GetCurrentWorldInfo()
    pawn = _try(lambda: pc.Pawn)
    hud = _try(lambda: pc.myHUD)
    gri = _try(lambda: wi.GRI)
    reads = {
        "pc.bCinematicMode": lambda: pc.bCinematicMode,
        "pc.bKismetEnabledCinematicMode": lambda: pc.bKismetEnabledCinematicMode,
        "pc.bCinematicModeHidePlayer": lambda: pc.bCinematicModeHidePlayer,
        "pc.bWasCinematic": lambda: pc.bWasCinematic,
        "pc.bIgnoreMoveInput": lambda: pc.bIgnoreMoveInput,
        "pc.bIgnoreLookInput": lambda: pc.bIgnoreLookInput,
        "pc.ViewTarget": lambda: pc.ViewTarget,
        "pc.CurrentEchoVideoMovie": lambda: pc.CurrentEchoVideoMovie,
        "pc.CurrentThirdPersonMovie": lambda: pc.CurrentThirdPersonMovie,
        "pc.bTextureMovieIsPaused": lambda: pc.bTextureMovieIsPaused,
        "pc.VoGMovieDuration": lambda: pc.VoGMovieDuration,
        "gri.bAllInCinematicMode": lambda: gri.bAllInCinematicMode,
        "hud.bShowHUD": lambda: hud.bShowHUD,
        "pawn.bUnderMatineeControl": lambda: pawn.bUnderMatineeControl,
        "pawn.bHidden": lambda: pawn.bHidden,
        "wi.bPlayersOnly": lambda: wi.bPlayersOnly,
        "wi.TextureMovies": lambda: len(wi.TextureMovies),
    }
    return {k: _try(lambda f=f: _brief(f()), "<err>") for k, f in reads.items()}


def stop() -> None:
    remove_hook(RENDER, Type.POST, HOOK_ID)
    for f in state.get("hooked", []):
        remove_hook(f, Type.PRE, HOOK_ID)
    state["hooked"] = []
    lines.append(f"== stopped at {time.monotonic() - t0:.1f}s")
    _flush()
    print(f"[probe_cutscene] stopped -> {OUT}")


INTERP_FIELDS = re.compile(r"position|length|playing|loop|rate|interp|reverse|paused|skip|cinemat|duration|time", re.I)


def _dump_interps(label: str) -> None:
    """The Matinee sequences playing (an in-engine cutscene: its position / length?): every property
    named like position / length / playing..., and the objects linked to it (its InterpData?)."""
    playing = [a for a in _try(lambda: list(unrealsdk.find_all("SeqAct_Interp", exact=False)), []) or []
               if not a.Name.startswith("Default__") and _try(lambda a=a: a.bIsPlaying, False)]
    lines.append(f"  == {label}: {len(playing)} Matinee sequences playing")
    for a in playing[:6]:
        lines.append(f"     {_brief(a)} ({_try(a._path_name, '?')})")
        c = a.Class
        while c is not None and c.Name != "Object":
            for f in _try(lambda c=c: list(c._fields()), []) or []:
                if f.Class.Name.endswith("Property") and INTERP_FIELDS.search(str(f.Name)):
                    lines.append(f"        {c.Name}.{f.Name} = {_try(lambda f=f: _brief(a._get_field(f)), '?')}")
            c = c.SuperField
        # its variables (the InterpData is plugged in as one): name, class, and an InterpData's length
        for link in _try(lambda a=a: list(a.VariableLinks), []) or []:
            for v in _try(lambda link=link: list(link.LinkedVariables), []) or []:
                length = _try(lambda v=v: _brief(v.InterpLength), None)
                lines.append(f"        var {link.LinkDesc!s}: {_brief(v)}" + (f" InterpLength={length}" if length else ""))
    _flush()


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
    if changed:
        state["values"] = values
        lines.append(f"  {now - t0:7.2f}s  " + ", ".join(f"{k}={v}" for k, v in changed.items()))
        _flush()
        if changed.get("pc.bCinematicMode") == "True":  # a cutscene starting: what plays it, then again 2 s in
            _dump_interps("cinematic mode on")
            state["redump"] = now + 2.0
    if state.get("redump") and now >= state["redump"]:
        state["redump"] = 0.0
        _dump_interps("2 s later")


def _args(args) -> str:  # noqa: ANN001
    """A call's arguments, name=value (the movie's name, its flags...)."""
    out = []
    for f in _try(lambda: list(args._type._fields()), []) or []:
        flags = _try(lambda f=f: f.PropertyFlags, 0x80)
        if f.Class.Name.endswith("Property") and flags & 0x80 and not flags & 0x400:  # parameters (CPF_Parm), not the return value
            out.append(f"{f.Name}={_try(lambda f=f: _brief(args._get_field(f)), '?')}")
    return ", ".join(out)


def on_call(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    # the time since the previous call (a video's length: from its play call to its stop / finished one)
    now = time.monotonic()
    since = f" (+{now - state['last_call']:.2f}s since the last call)" if state["last_call"] else ""
    state["last_call"] = now
    lines.append(f"  {now - t0:7.2f}s  call {_try(lambda: func.func._path_name(), '?')}({_args(args)}) on {_brief(obj)}{since}")
    _flush()


if callable(getattr(builtins, "helios_cutscene_stop", None)):
    try:
        builtins.helios_cutscene_stop()
    except Exception:  # noqa: BLE001
        pass
t0 = time.monotonic()
state: dict = {"next": 0.0, "last_frame": 0.0, "last_call": 0.0, "values": {}, "hooked": []}
builtins.helios_cutscene_stop = stop
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
    add_hook(RENDER, Type.POST, HOOK_ID, tick)
    _flush()
    print(f"[probe_cutscene] watching for {RUN_FOR / 60:.0f} min - play the cutscene; stop early: py helios_cutscene_stop()")
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    _flush()
    stop()
