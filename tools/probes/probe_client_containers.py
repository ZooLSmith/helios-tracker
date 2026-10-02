# Dev probe (in game, as a co-op CLIENT), instant: what tells an opened container on a client - the
# collector's test (SimpleAnimState 7 + bCanBeUsed[0] off, tools/probes/probe_containers.txt, as host) never
# fires there. Stand near a container you opened and one you didn't (a few metres), then run it.
# Logs: every interactive object within 25 m: its name, definition, distance, SimpleAnimState,
# RepSimpleAnimState, bCanBeUsed, and every other property whose name looks state / use / open / loot
# related (to spot what differs between the opened and unopened one).
# Writes tools/probes/probe_client_containers.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_client_containers.py").read())
import enum
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_client_containers.txt"  # the repo, through the mod's junction
RANGE = 2500.0  # uu (25 m)
PATTERN = re.compile(r"state|use|usab|open|loot|anim|spawn|empty|close|activ", re.I)
SCALARS = {"BoolProperty", "ByteProperty", "IntProperty", "FloatProperty", "NameProperty", "ObjectProperty", "StructProperty"}
lines: list[str] = []


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
        return f"{value:.2f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{value.Name}'"
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f)))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name in SCALARS - {"StructProperty"}) + "}"
    return repr(value)


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    me = get_pc().Pawn
    here = me.Location
    lines.append(f"map {_try(lambda: str(wi.GetStreamingPersistentMapName()))} netmode={_try(lambda: _brief(wi.NetMode))}")
    near = []
    for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
        if io.Name.startswith("Default__"):
            continue
        loc = _try(lambda io=io: io.Location, None)
        if loc is None or isinstance(loc, str):
            continue
        d = math.dist((loc.X, loc.Y, loc.Z), (here.X, here.Y, here.Z))
        if d <= RANGE:
            near.append((d, io))
    near.sort(key=lambda x: x[0])
    lines.append(f"{len(near)} interactive objects within {RANGE / 100:.0f} m")
    for d, io in near:
        lines.append(f"== {io.Name} def={_try(lambda io=io: io.InteractiveObjectDefinition.Name)} {d / 100:.1f} m"
                     f"  SimpleAnimState={_try(lambda io=io: io.SimpleAnimState)} RepSimpleAnimState={_try(lambda io=io: io.RepSimpleAnimState)}"
                     f" bCanBeUsed={_try(lambda io=io: tuple(io.bCanBeUsed))} hidden={_try(lambda io=io: io.bHidden)}")
        c = io.Class
        while c is not None and c.Name != "Actor":
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name in SCALARS and PATTERN.search(str(f.Name)):
                    lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f, io=io: _brief(io._get_field(f)))}")
            c = c.SuperField


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_client_containers: {len(lines)} lines -> {OUT}")
