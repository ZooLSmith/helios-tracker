# Dev probe (in game), 90 s: what happens to the player between going down, dying and respawning -
# for the map (a dead / respawning player shouldn't be drawn, or followed, wherever the game parks
# their pawn). Run it, then get downed and die (or get revived), and wait for the respawn.
# Logs (changes only, sampled every 0.25 s): the controller's state, its pawn (which one, where,
# health, IsInjured), every player pawn in the level; and at the start every respawn / revive /
# death related field on the controller, the pawn and the game info (the respawn station?).
# Writes E:\Projects\python\borderlands-2\tools\probe_respawn.txt (overwrites)
#   py exec(open(r"E:\Projects\python\borderlands-2\tools\probe_respawn.py").read())
import enum
import re
import time
from pathlib import Path

from mods_base import ENGINE, get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook

OUT = Path(r"E:\Projects\python\borderlands-2\tools\probe_respawn.txt")
SAMPLE_FOR = 90.0
SAMPLE_EVERY = 0.25
PATTERN = re.compile(r"respawn|revive|death|dead|injur|dying|down|newu|healthstation|spawnpoint|restart", re.I)
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
        return f"{type(value).__name__}.{value.name}"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:6]) + "]"
    if isinstance(value, float):
        return f"{value:.2f}"
    return repr(value)


def _related_fields(obj, label: str) -> None:  # noqa: ANN001
    """Every property / function of obj's classes whose name matches PATTERN (values for properties)."""
    lines.append(f"== {label}: {_brief(obj)}")
    if obj is None or not hasattr(obj, "Class"):
        return
    c = obj.Class
    while c is not None and c.Name not in ("Object", "Actor"):
        for f in _try(lambda c=c: list(c._fields()), []):
            if not PATTERN.search(str(f.Name)):
                continue
            if f.Class.Name == "Function":
                params = [p.Name for p in _try(lambda f=f: list(f._fields()), [])]
                lines.append(f"   {c.Name}.{f.Name}({', '.join(map(str, params))})")
            elif f.Class.Name.endswith("Property"):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _loc(actor) -> str:  # noqa: ANN001
    return _try(lambda: f"({actor.Location.X:.0f}, {actor.Location.Y:.0f}, {actor.Location.Z:.0f})", "?")


def _sample() -> str:
    pc = get_pc(possibly_loading=True)
    if pc is None:
        return "no pc"
    pawn = _try(lambda: pc.Pawn, None)
    my = _try(lambda: pc.MyWillowPawn, None)
    parts = [f"pc state={_try(lambda: str(pc.GetStateName()))}"]
    for label, p in (("Pawn", pawn), ("MyWillowPawn", my)):
        if p is None or isinstance(p, str):
            parts.append(f"{label}=None")
            continue
        parts.append(f"{label}={p.Name}@{_loc(p)} hp={_try(lambda p=p: round(p.GetHealth()))}"
                     f" injured={_try(lambda p=p: p.IsInjured())} deleteMe={_try(lambda p=p: p.bDeleteMe)}"
                     f" hidden={_try(lambda p=p: p.bHidden)} state={_try(lambda p=p: str(p.GetStateName()))}")
    wi = ENGINE.GetCurrentWorldInfo()
    players, p = [], _try(lambda: wi.PawnList, None)
    for _ in range(1000):
        if p is None or isinstance(p, str):
            break
        if "Player" in str(p.Class.Name):
            players.append(f"{p.Name}@{_loc(p)}")
        p = _try(lambda p=p: p.NextPawn, None)
    parts.append(f"player pawns={players}")
    return " | ".join(parts)


def main() -> None:
    lines.append(f"probe_respawn {time.strftime('%H:%M:%S')}")
    pc = get_pc()
    _related_fields(pc, "controller")
    _related_fields(_try(lambda: pc.Pawn, None), "pawn")
    _related_fields(_try(lambda: ENGINE.GetCurrentWorldInfo().Game, None), "game info")
    lines.append("== samples (changes only)")
    OUT.write_text("\n".join(lines), encoding="utf-8")

    hook_func, hook_id = "WillowGame.WillowGameViewportClient:PostRender", "helios_probe_respawn"
    remove_hook(hook_func, Type.POST, hook_id)
    t0, state = time.monotonic(), {"next": 0.0, "last": ""}

    def tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - t0 > SAMPLE_FOR:
            remove_hook(hook_func, Type.POST, hook_id)
            lines.append("== done")
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_respawn] done, {len(lines)} lines -> {OUT}")
            return
        if now < state["next"]:
            return
        state["next"] = now + SAMPLE_EVERY
        sample = _try(_sample)
        if sample != state["last"]:
            state["last"] = sample
            lines.append(f"  {now - t0:6.2f}s  {sample}")
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(hook_func, Type.POST, hook_id, tick)
    print(f"[probe_respawn] sampling for {SAMPLE_FOR:.0f}s - get downed, die, respawn")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
