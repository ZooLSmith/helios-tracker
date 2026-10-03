# Dev probe (in game), read-only: how Borderlands 1's map tab places the world on its vector map (.agent/bl1.md "The
# map screen") - what decides the page's world -> map for BL1.
# Run it in a level (map closed), then open the map (the menu's map tab): it hooks the tab's per-frame update
# (WillowGFxHelperMap:UpdateObjects, POST - a hook, nothing called) and, at each opening (a new helper object, or a
# pause over 2 s between updates), writes:
# 1. the helper: every field (Anchor, CoordScale, Transform, AnchorSize, ViewSize, ClipSize, ViewOffset, DesiredCenter,
#    Scales, CurrScaleVal...);
# 2. its anchor (the level's LevelLandmarkAnchor): every field (Location, DrawScale(3D), Texture, TextureSize, MapFrame);
# 3. its MapObjects: each one's TransformedLocation / CustomObjectLoc and what it is (a player: their world Location;
#    a landmark: its Location) - world and map side by side, to fit the transform;
# 4. the level's LevelLandmark / SubLevelLandmark actors (Location, fields).
# Run it once per game session (running it again starts over), then open the map once in each of a few levels (the
# more levels, the better the fit): 8 openings, then the hook removes itself. Floats in full (the Transform's are ~1e-5). Writes tools/probes/probe_bl1_map.txt after each section (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_map.py").read())
from enum import Enum
import sys
import time
from pathlib import Path

import unrealsdk
from unrealsdk.hooks import Type, add_hook, remove_hook


def _out() -> Path:  # the repo, through the mod's junction (sys.modules if the mod imported, else sdk_mods)
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_map.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_map.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
HOOK = ("WillowGame.WillowGFxHelperMap:UpdateObjects", Type.POST, "helios_probe_bl1_map")
MAX_DUMPS = 8
lines: list[str] = []


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return repr(value) if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if hasattr(value, "_type"):  # struct
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "__len__"):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:8]) + "]"
    return str(value)


SKIP = {"Outer", "Class", "Name", "ObjectArchetype", "ObjectFlags", "HashNext", "HashOuterNext", "StateFrame",
        "LinkerIndex", "ObjectInternalInteger", "NetIndex", "VfTableObject", "Linker"}


def _fields(obj, limit: int = 6000) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if f.Class.Name.endswith("Property") and str(f.Name) not in SKIP:
            out.append(f"{f.Name}={_brief(_try(lambda f=f: obj._get_field(f)))[:400]}")
    return ", ".join(out)[:limit]


def _loc(actor) -> str:  # noqa: ANN001
    return _brief(_try(lambda: actor.Location)) if actor is not None else "-"


state = {"dumps": 0, "helper": None, "last": 0.0}


def _dump(helper) -> None:  # noqa: ANN001
    state["dumps"] += 1
    lines.append("#" * 70)
    lines.append(f"== opening {state['dumps']} at {time.strftime('%H:%M:%S')}: {helper._path_name()}")
    pc = _try(lambda: helper.PlayerOwner, None)
    pawn = _try(lambda: pc.Pawn, None) if pc is not None and not isinstance(pc, str) else None
    lines.append(f"player owner {_brief(pc)}, pawn {_brief(pawn)} at {_loc(pawn)}, rotation {_brief(_try(lambda: pawn.Rotation))}")
    _flush()
    # 1. the helper
    lines.append(f"-- helper fields: {_fields(helper)}")
    _flush()
    # 2. its anchor
    anchor = _try(lambda: helper.Anchor, None)
    if anchor is not None and not isinstance(anchor, str):
        lines.append(f"-- anchor {anchor._path_name()}: {_fields(anchor)}")
    else:
        lines.append(f"-- anchor: {anchor}")
    _flush()
    # 3. the map objects: world and map side by side
    objects = _try(lambda: list(helper.MapObjects), [])
    lines.append(f"-- MapObjects ({len(objects) if isinstance(objects, list) else objects})")
    for n, obj in enumerate(objects if isinstance(objects, list) else []):
        player = _try(lambda o=obj: o.Player, None)
        landmark = _try(lambda o=obj: o.Landmark, None)
        io = _try(lambda o=obj: o.ClientInteractiveObject, None)
        what = (f"player {_brief(player)} at {_loc(_try(lambda p=player: p.Pawn, None) if player is not None and not isinstance(player, str) else None)}"
                if player is not None else f"landmark {_brief(landmark)} at {_loc(landmark)}" if landmark is not None
                else f"object {_brief(io)} at {_loc(io)}" if io is not None else "custom")
        lines.append(f"   [{n}] {what}; TransformedLocation {_brief(_try(lambda o=obj: o.TransformedLocation))}, "
                     f"CustomObjectLoc {_brief(_try(lambda o=obj: o.CustomObjectLoc))}, Angle {_brief(_try(lambda o=obj: o.Angle))}, "
                     f"icon {_brief(_try(lambda o=obj: o.AS_IconPath))} {_brief(_try(lambda o=obj: o.AS_IconClipFrame))}, "
                     f"waypoint {_brief(_try(lambda o=obj: o.bWaypoint))}")
    _flush()
    # 4. the level's landmarks (first opening only: they don't move)
    if state["dumps"] == 1:
        for cls in ("LevelLandmarkAnchor", "LevelLandmark", "SubLevelLandmark"):
            found = [a for a in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=True)), []) or []
                     if not str(a.Name).startswith("Default__")]
            lines.append(f"-- {cls}: {len(found)}")
            for a in found[:40]:
                lines.append(f"   {a._path_name()}: {_fields(a, 1500)}")
            _flush()
    if state["dumps"] >= MAX_DUMPS:
        remove_hook(HOOK[0], HOOK[1], HOOK[2])
        lines.append(f"== {MAX_DUMPS} openings: hook removed")
        _flush()


def _on_update(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
    try:
        now = time.monotonic()
        new_opening = state["helper"] != obj._path_name() or now - state["last"] > 2.0
        state["helper"], state["last"] = obj._path_name(), now
        if new_opening and state["dumps"] < MAX_DUMPS:
            _dump(obj)
    except Exception as ex:  # noqa: BLE001
        lines.append(f"<dump failed: {type(ex).__name__}: {ex}>")
        _flush()


remove_hook(HOOK[0], HOOK[1], HOOK[2])  # (a previous run's)
add_hook(HOOK[0], HOOK[1], HOOK[2], _on_update)
lines.append("#" * 70)
lines.append(f"probe_bl1_map armed at {time.strftime('%H:%M:%S')}: open the map (up to {MAX_DUMPS} openings: one per level)")
_flush()
print(f"probe_bl1_map: open the map - written to {OUT}")
