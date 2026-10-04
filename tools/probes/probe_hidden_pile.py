# Dev probe (in game), instant, read-only: an interactive object the page shows but the game doesn't (a Bullymong pile
# 6 m away, nothing there - 2026-10-04). What tells it apart from the visible ones of its kind: stand by it, run this.
# 1. every interactive object within NEAR_M: definition, distance;
# 2. the nearest whose definition's name holds TARGET (the invisible one) and every other one of its definition in the
#    level (the visible ones, mostly): all their simple properties (bool / byte / int / float / name, objects by name)
#    and their components' - read, nothing called;
# 3. the fields where it differs from most of the others (what switches it off, likely), then its full dump.
# Writes tools/probes/probe_hidden_pile.txt (overwrites; section by section)
#   py exec(open(r"<repo>\tools\probes\probe_hidden_pile.py").read())
import enum
import math
import sys
from collections import Counter
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_hidden_pile.txt"  # the repo, through the mod's junction
TARGET = "BullymongPile"  # in the definition's name
NEAR_M = 15.0
MAX_PEERS = 40
SIMPLE = {"BoolProperty", "ByteProperty", "IntProperty", "FloatProperty", "NameProperty", "ObjectProperty", "StrProperty"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value.Name}"
    return repr(value)[:80]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _props(obj) -> dict[str, str]:  # noqa: ANN001
    """Every simple property of obj (its class chain up to Object), by name -> its value, read."""
    out: dict[str, str] = {}
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            if str(f.Class.Name) in SIMPLE and str(f.Name) not in out:
                out[str(f.Name)] = _try(lambda f=f: _brief(obj._get_field(f)))
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _dump(io) -> dict[str, str]:  # noqa: ANN001
    """The object's properties, and each component's as "<n>:<class>.<field>"."""
    out = dict(_props(io))
    for n, comp in enumerate(_try(lambda: list(io.Components), []) or []):
        if comp is None or isinstance(comp, str):
            continue
        prefix = f"c{n}:{comp.Class.Name}."
        out.update({prefix + k: v for k, v in _props(comp).items()})
    return out


def _dist(io, me) -> float:  # noqa: ANN001
    loc = _try(lambda: io.Location, None)
    if loc is None or isinstance(loc, str) or me is None:
        return float("inf")
    return math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100


def _definition(io) -> str:  # noqa: ANN001
    return str(_try(lambda: io.InteractiveObjectDefinition._path_name(), "?"))


OUT.write_text("", encoding="utf-8")
me = _try(lambda: get_pc().Pawn.Location, None)
objects = [io for io in unrealsdk.find_all("WillowInteractiveObject", exact=False) if not io.Name.startswith("Default__")]

# --- 1. near
near = sorted((d, io) for io in objects if (d := _dist(io, me)) <= NEAR_M)
lines.append(f"== within {NEAR_M:.0f} m: {len(near)} interactive objects (of {len(objects)})")
for d, io in near:
    lines.append(f"   {d:5.1f} m  {io.Name}  {_definition(io)}  bHidden={_try(lambda io=io: io.bHidden)}")
_flush()

# --- 2. the target and its peers
target = next((io for d, io in near if TARGET.lower() in _definition(io).lower()), None)
if target is None:
    lines.append(f"== no {TARGET} within {NEAR_M:.0f} m: stand by it and run again")
    _flush()
else:
    definition = _definition(target)
    peers = [io for io in objects if io is not target and _definition(io) == definition][:MAX_PEERS]
    lines.append(f"== target {target.Name} at {_dist(target, me):.1f} m, {definition}; {len(peers)} others of it in the level:")
    for io in peers:
        lines.append(f"   {_dist(io, me):7.1f} m  {io.Name}")
    _flush()
    # 2b. its animations (SimpleAnimState: a bit per SimpleAnimInfo entry - games.py is_looted: "Opened" alone = spawned
    # looted, on chests) and where it is, against the others
    def _anims(io):  # noqa: ANN001, ANN202
        names = [str(_try(lambda a=a: a.AnimName)) for a in _try(lambda: list(io.SimpleAnimInfo), []) or []]
        state = _try(lambda: int(io.SimpleAnimState), -1)
        on = [f"{n}={name}" for n, name in enumerate(names) if isinstance(state, int) and state >= 0 and state >> n & 1]
        loc = _try(lambda: io.Location, None)
        where = f"({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})" if loc is not None and not isinstance(loc, str) else "?"
        return (f"state {state} -> bits on {on}; anims {list(enumerate(names))}; bCanBeUsed {_try(lambda: tuple(io.bCanBeUsed))}"
                f" Health {_try(lambda: io.Health)}; at {where}")
    lines.append(f"== animations (the player at {(f'({me.X:.0f}, {me.Y:.0f}, {me.Z:.0f})') if me is not None else '?'})")
    lines.append(f"   TARGET {target.Name}: {_anims(target)}")
    for io in peers:
        lines.append(f"   {io.Name}: {_anims(io)}")
    _flush()
    target_dump = _dump(target)
    peer_dumps = [_dump(io) for io in peers]

    # --- 3. where it differs from most of them
    lines.append("== fields where the target differs from most of the others (target value | the others' most common, count)")
    for key, value in sorted(target_dump.items()):
        others = Counter(d.get(key, "<absent>") for d in peer_dumps)
        if not others:
            continue
        common, count = others.most_common(1)[0]
        if value != common and count > len(peer_dumps) / 2 and not key.endswith(("Location", "Name", "Tag")):
            lines.append(f"   {key}: {value} | {common} ({count}/{len(peer_dumps)})")
    _flush()
    lines.append("== the target's full dump")
    lines += [f"   {k} = {v}" for k, v in sorted(target_dump.items())]
    _flush()
    print(f"[probe_hidden_pile] -> {OUT}")
