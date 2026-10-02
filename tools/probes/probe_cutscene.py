# Dev probe (in game), instant: how to tell a cutscene is playing. Run it DURING a cutscene, then again
# after it (normal play) - each run is appended, to compare.
# Logs the fields named like cinematic / matinee / cutscene / movie / HUD shown / input ignored / view
# target on the controller, pawn, HUD, world info, GRI and the game info, plus the view target and the
# active Matinee sequences (SeqAct_Interp being played).
# Appends to tools/probes/probe_cutscene.txt
#   py exec(open(r"<repo>\tools\probes\probe_cutscene.py").read())
import enum
import re
import time
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_cutscene.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"cinemat|matinee|cutscene|movie|showhud|bshowhud|ignore(move|look)input|viewtarget|"
                     r"playersonly|hidehud|bhidden$|interp|scripted", re.I)
lines: list[str] = [f"######## run at {time.strftime('%H:%M:%S')}"]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return f"(len {len(value)})"
    return repr(value)


def _fields(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    seen = set()
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)) and str(f.Name) not in seen:
                seen.add(str(f.Name))
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    pc = get_pc()
    wi = ENGINE.GetCurrentWorldInfo()
    lines.append(f"map: {_try(lambda: wi.GetStreamingPersistentMapName())}")
    for label, obj in {"pc": pc, "pawn": _try(lambda: pc.Pawn, None), "HUD": _try(lambda: pc.myHUD, None),
                       "WorldInfo": wi, "GRI": _try(lambda: wi.GRI, None), "GameInfo": _try(lambda: wi.Game, None),
                       "camera": _try(lambda: pc.PlayerCamera, None)}.items():
        if obj is not None and not isinstance(obj, str):
            _fields(obj, label)
    lines.append(f"== view target: {_try(lambda: _brief(pc.GetViewTarget()))}")
    playing = [s for s in _try(lambda: list(unrealsdk.find_all("SeqAct_Interp", exact=False)), [])
               if not s.Name.startswith("Default__") and _try(lambda s=s: s.bIsPlaying, False)]
    lines.append(f"== {len(playing)} Matinee sequences playing")
    for s in playing[:8]:
        lines.append(f"   {_brief(s)} position={_try(lambda s=s: _brief(s.Position))}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_cutscene: {len(lines)} lines appended -> {OUT}")
