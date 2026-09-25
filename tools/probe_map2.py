# Dev probe (in game): samples the player's world position/yaw together with the minimap's MapClip
# placement (the minimap moves/rotates/scales the tactical map movie so the player is centered),
# to fit the exact world -> tactical map pixel transform. Draws nothing.
# Console (with the HUD minimap visible, not in a menu):
#   py exec(open(r"<repo>\tools\probe_map2.py").read())
# Then WALK AROUND AND TURN for 20 s (both directions, long straight lines help).
# Stops by itself after SAMPLE_FOR; early: py import unrealsdk.hooks as h; h.remove_hook("WillowGame.WillowGameViewportClient:PostRender", h.Type.POST, "helios_probe_map2")
# (the file keeps what was sampled so far).
# Writes tools/probe_map2.txt
import time
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import WeakPointer

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_map2.txt"  # the repo, through the mod's junction
SAMPLE_FOR = 20.0
SAMPLE_EVERY = 0.25
FLASH_VARS = ("_x", "_y", "_rotation", "_xscale", "_yscale", "_width", "_height")

lines: list[str] = []


def _try(fn):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"


def _r(v):  # noqa: ANN001, ANN202
    return round(v, 3) if isinstance(v, float) else v


widgets = [w for w in unrealsdk.find_all("HUDWidget_Minimap", exact=False) if not w.Name.startswith("Default__")]
lines.append(f"minimap widgets: {[w._path_name() for w in widgets]}")
if not widgets:
    print("[probe_map2] no HUDWidget_Minimap - be in game with the HUD visible")
else:
    w = widgets[-1]
    for name in ("WorldRadius", "UnrealUnitsPerPixel", "OuterRadius", "bPlayerRelative", "MapYawOffset",
                 "NorthMarkerOffset"):
        lines.append(f"  {name} = {_try(lambda n=name: getattr(w, n))}")
    clip = w.MapClip
    lines.append(f"  MapClip = {_try(lambda: clip._path_name())}")
    lines.append(f"  MapClip.GetDisplayInfo() = {_try(clip.GetDisplayInfo)}")
    for extra in ("DirArrowClip", "NorthMarkerClip"):
        c = _try(lambda e=extra: getattr(w, e))
        if hasattr(c, "GetDisplayInfo"):
            lines.append(f"  {extra}.GetDisplayInfo() = {_try(c.GetDisplayInfo)}")
    lines.append("== samples: t | pawn X Y Z yaw | MapClip " + " ".join(FLASH_VARS))
    OUT.write_text("\n".join(lines), encoding="utf-8")

    # Never keep UObjects across frames: hold the widget weakly, fetch MapClip each sample.
    _weak = WeakPointer(w)
    _HOOK_FUNC = "WillowGame.WillowGameViewportClient:PostRender"
    _HOOK_ID = "helios_probe_map2"
    remove_hook(_HOOK_FUNC, Type.POST, _HOOK_ID)
    _t0 = time.monotonic()
    _next = [0.0]

    def _tick(obj, args, ret, func):  # noqa: ANN001, ANN202, ARG001
        now = time.monotonic()
        if now - _t0 > SAMPLE_FOR:
            remove_hook(_HOOK_FUNC, Type.POST, _HOOK_ID)
            OUT.write_text("\n".join(lines), encoding="utf-8")
            print(f"[probe_map2] done, {len(lines)} lines -> {OUT}")
            return
        if now < _next[0]:
            return
        _next[0] = now + SAMPLE_EVERY
        wd = _weak()
        pawn = _try(lambda: get_pc().Pawn)
        if wd is None or not hasattr(pawn, "Location"):
            lines.append(f"  {now - _t0:6.2f}s  widget={wd is not None} pawn={pawn}")
            return
        loc, yaw = pawn.Location, pawn.Rotation.Yaw
        clip = wd.MapClip
        flash = " ".join(str(_r(_try(lambda v=v: clip.GetFloat(v)))) for v in FLASH_VARS)
        lines.append(f"  {now - _t0:6.2f}s | {loc.X:.1f} {loc.Y:.1f} {loc.Z:.1f} {yaw} | {flash}")
        if len(lines) % 10 == 0:
            OUT.write_text("\n".join(lines), encoding="utf-8")

    add_hook(_HOOK_FUNC, Type.POST, _HOOK_ID, _tick)
    print(f"[probe_map2] sampling for {SAMPLE_FOR:.0f}s - walk around and turn")
