# Dev probe (in game), 120 s: what tells that a player is in a menu (inventory / status menu, map,
# pause, vendor, chat...) - for the map, like crippled / dead / respawning. Solo, host and co-op client:
# is it visible for the OTHER players too (replicated on their pawn / player info, or only on their
# controller, which only the host has)?
# Run it, then open and close menus one at a time, a few seconds each, calling out which (inventory,
# map, skills, pause / ESC, a vendor, chat); in co-op have the other player do the same.
# Logs (changes only, sampled every 0.25 s): every bool / byte / int / name / object property whose name
# looks menu / input / UI related, on each player's controller, HUD, pawn and player info (all bool /
# byte ones on the player infos: whatever is replicated); the controllers' state; the open GFx movies
# (every 1 s).
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_menu.txt (overwrites)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_menu.py").read())
import enum
import re
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_menu.txt")
SAMPLE_FOR = 120.0
SAMPLE_EVERY = 0.25
MOVIES_EVERY = 1.0
PATTERN = re.compile(r"menu|pause|status|inventor|vendor|shop|chat|typ|busy|afk|idle|focus|input|ignore|"
                     r"cinematic|movie|gfx|dialog|interact|trade|console|paused|hud|screen|modal|lock", re.I)
SCALARS = {"BoolProperty", "ByteProperty", "IntProperty", "NameProperty", "StrProperty", "ObjectProperty"}
lines: list[str] = []
_class_fields: dict[tuple[str, bool], list] = {}


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{value.Name}'"
    return repr(value)


def _fields(obj, every_flag: bool) -> list:  # noqa: ANN001
    """obj's scalar properties matching PATTERN (every bool / byte one too if every_flag), per class."""
    key = (_try(lambda: obj.Class._path_name(), "?"), every_flag)
    if key not in _class_fields:
        out, c = [], obj.Class
        while c is not None and c.Name != "Object":
            for f in _try(lambda c=c: list(c._fields()), []):
                kind = f.Class.Name
                if kind in SCALARS and (PATTERN.search(str(f.Name))
                                        or (every_flag and kind in ("BoolProperty", "ByteProperty"))):
                    out.append(f)
            c = c.SuperField
        _class_fields[key] = out
    return _class_fields[key]


def _values(obj, label: str, every_flag: bool = False) -> dict[str, str]:  # noqa: ANN001
    if obj is None or isinstance(obj, str):
        return {}
    vals = {f"{label}.{f.Name}": _try(lambda f=f: _brief(obj._get_field(f))) for f in _fields(obj, every_flag)}
    if hasattr(obj, "GetStateName"):
        vals[f"{label}.<state>"] = _try(lambda: str(obj.GetStateName()))
    return vals


def _players() -> list:
    wi = ENGINE.GetCurrentWorldInfo()
    out, p = [], _try(lambda: wi.PawnList, None)
    for _ in range(1000):
        if p is None or isinstance(p, str):
            break
        if "Player" in str(p.Class.Name):
            out.append(p)
        p = _try(lambda p=p: p.NextPawn, None)
    return out


def _sample() -> dict[str, str]:
    pc = get_pc(possibly_loading=True)
    vals: dict[str, str] = {}
    if pc is None:
        return {"pc": "None"}
    me = _try(lambda: pc.MyWillowPawn, None)
    vals |= _values(pc, "myPC")
    vals |= _values(_try(lambda: pc.MyHUD, None), "myHUD")
    vals["myPC.GetHUDMovie()"] = _try(lambda: _brief(pc.GetHUDMovie()))
    vals["myPC.IsPaused()"] = _try(lambda: repr(pc.IsPaused()))
    for p in _players():
        pri = _try(lambda p=p: p.PlayerReplicationInfo, None)
        name = _try(lambda pri=pri: str(pri.PlayerName), "?") if pri is not None else "?"
        label = "me" if me is not None and p == me else name
        vals |= _values(p, f"{label}:pawn")
        vals |= _values(pri, f"{label}:PRI", every_flag=True)
        ctrl = _try(lambda p=p: p.Controller, None)
        if label != "me":  # the host has every player's controller, a client none
            vals[f"{label}:controller"] = _brief(ctrl) if not isinstance(ctrl, str) else ctrl
            vals |= _values(ctrl, f"{label}:PC")
    return vals


def _movies() -> str:
    open_ = []
    for m in _try(lambda: list(unrealsdk.find_all("GFxMoviePlayer", exact=False)), []):
        if str(m.Name).startswith("Default__"):
            continue
        if _try(lambda m=m: bool(m.bMovieIsOpen), False):
            open_.append(f"{m.Class.Name}'{m.Name}'")
    return ", ".join(sorted(open_))


def main() -> None:
    lines.append(f"probe_menu {time.strftime('%H:%M:%S')}  netmode={_try(lambda: ENGINE.GetCurrentWorldInfo().NetMode)}")
    first = _try(_sample, {})
    lines.append("== initial values")
    lines.extend(f"   {k} = {v}" for k, v in sorted(first.items()))
    lines.append(f"== open movies: {_try(_movies)}")
    lines.append("== changes")
    OUT.write_text("\n".join(lines), encoding="utf-8")

    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_menu"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state = time.monotonic(), {"next": 0.0, "movies_next": 0.0, "last": first, "movies": ""}

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append("== done")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_menu] done, {len(lines)} lines -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        changed = []
        vals = _try(_sample, {})
        last = state["last"]
        for k in sorted(set(vals) | set(last)):
            if vals.get(k) != last.get(k):
                changed.append(f"{k}: {last.get(k)} -> {vals.get(k)}")
        state["last"] = vals
        if now >= state["movies_next"]:
            state["movies_next"] = now + MOVIES_EVERY
            movies = _try(_movies)
            if movies != state["movies"]:
                changed.append(f"open movies: {movies}")
                state["movies"] = movies
        if changed:
            lines.append(f"  {now - t0:6.2f}s")
            lines.extend(f"      {c}" for c in changed)
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_menu] sampling for {SAMPLE_FOR:.0f}s - open / close menus one at a time")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
