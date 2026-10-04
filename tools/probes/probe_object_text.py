# Dev probe (in game), instant, read-only: does the game have text of its own for an object the page names by a guess
# ("Outpost Definition ?" - Borderlands 1's New-U stations, EmergencyTeleportOutpost, 2026-10-04)? Stand by one, run it.
# For the nearest interactive object whose class or definition name holds TARGET (within NEAR_M):
# 1. every text property (strings, names) of the object, its definition, its balance, its class's default object - and
#    of the objects its definition points to, one level down;
# 2. the functions of the object's and its definition's classes named like a name / a text (listed, never called).
# Writes tools/probes/probe_object_text.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_object_text.py").read())
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_object_text.txt"  # the repo, through the mod's junction
TARGET = "Outpost"  # in the object's class or definition name
NEAR_M = 20.0
TEXT = {"StrProperty", "NameProperty"}
FUNCTIONS = re.compile(r"name|text|display|caption|title|label|header|message|string|hint|prompt", re.I)
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _chain(cls):  # noqa: ANN001, ANN202
    out, c = [], cls
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        out.append(c)
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _texts(label: str, obj, follow: bool) -> None:  # noqa: ANN001
    """obj's text properties (non-empty ones, and the empty ones by name); with follow, its object properties' too."""
    if obj is None or isinstance(obj, str):
        lines.append(f"== {label}: None")
        return
    lines.append(f"== {label}: {obj.Class.Name}'{_try(obj._path_name, obj.Name)}'")
    empty, linked = [], []
    for c in _chain(obj.Class):
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            kind = str(f.Class.Name)
            if kind in TEXT:
                value = str(_try(lambda f=f: obj._get_field(f), ""))
                if value and value != "None":
                    lines.append(f"   {c.Name}.{f.Name} = {value!r}")
                else:
                    empty.append(str(f.Name))
            elif follow and kind == "ObjectProperty":
                target = _try(lambda f=f: obj._get_field(f), None)
                if target is not None and not isinstance(target, str) and hasattr(target, "Class"):
                    linked.append((f"{label}.{f.Name}", target))
    if empty:
        lines.append(f"   (empty: {', '.join(empty[:40])})")
    _flush()
    for sub_label, target in linked[:12]:
        _texts(sub_label, target, False)


def _functions(label: str, cls) -> None:  # noqa: ANN001
    found = [f"{c.Name}.{f.Name}()" for c in _chain(cls) for f in _try(lambda c=c: list(c._fields()), []) or []
             if str(f.Class.Name) == "Function" and FUNCTIONS.search(str(f.Name))]
    lines.append(f"== {label}'s functions named like a text (listed, not called): {len(found)}")
    lines.extend(f"   {name}" for name in found)  # (not +=: that makes `lines` local here)
    _flush()


OUT.write_text("", encoding="utf-8")
me = _try(lambda: get_pc().Pawn.Location, None)


def _dist(obj) -> float:  # noqa: ANN001
    loc = _try(lambda: obj.Location, None)
    if loc is None or isinstance(loc, str) or me is None or isinstance(me, str):
        return float("inf")
    return math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100


def _matches(io) -> bool:  # noqa: ANN001
    names = f"{io.Class.Name} {_try(lambda: io.InteractiveObjectDefinition.Name, '')}"
    return TARGET.lower() in names.lower()


candidates = sorted((d, io) for io in unrealsdk.find_all("WillowInteractiveObject", exact=False)
                    if not io.Name.startswith("Default__") and _matches(io) and (d := _dist(io)) <= NEAR_M)
if not candidates:
    lines.append(f"== no interactive object with {TARGET!r} in its class / definition within {NEAR_M:.0f} m")
    _flush()
else:
    distance, target = candidates[0]
    lines.append(f"== the nearest: {target.Name} ({target.Class.Name}) at {distance:.1f} m")
    _flush()
    definition = _try(lambda: target.InteractiveObjectDefinition, None)
    _texts("object", target, False)
    _texts("definition", definition, True)
    _texts("balance", _try(lambda: target.BalanceDefinitionState.BalanceDefinition, None), True)
    _texts("class default", _try(lambda: target.Class.ClassDefaultObject, None), False)
    _functions("the object", target.Class)
    if definition is not None and not isinstance(definition, str):
        _functions("the definition", definition.Class)
print(f"[probe_object_text] -> {OUT}")
