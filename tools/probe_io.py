# Dev probe (in game), instant, read-only: what an interactive thing really is - its class, usability, the behaviour
# chains its events run (a switch, a lever, an explosive...). Two ways:
#   - near you (default): every actor within 3 m of the player (any class: a lever the map doesn't show may not be a
#     WillowInteractiveObject at all), then the interactive objects among them in depth;
#   - by definition name: every instance in the level (the Electrical Fuse Box - drawn as an explosive: its definition
#     holds a Behavior_Explode, inspector.explosion_info - a switch?):
#     py PROBE_DEF = "IO_ElectricalFenceBox"; exec(open(r"<repo>\tools\probe_io.py").read())
# In depth: 1. the object: location, health, usability (bCanBeUsed...), its definition; 2. the definition's own
# properties; 3. its BehaviorProviderDefinition: each sequence, its events (EventData2: name, enabled) and the chains of
# behaviours each runs (ConsolidatedOutputLinkData: ArrayIndexAndLength = index << 16 | length, each link's
# LinkIdAndLinkedBehavior & 0xFFFF = the behaviour's index); 4. each Behavior_Explode and its explosion definition.
# Properties only, no calls. Writes tools/probe_io.txt (appends), after each section.
#   py exec(open(r"<repo>\tools\probe_io.py").read())
import math
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_io.txt"  # the repo, through the mod's junction
DEF_NAME = globals().pop("PROBE_DEF", None)
NEAR = 300  # uu (1 uu = 1 cm)
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _val(v) -> str:  # noqa: ANN001
    if hasattr(v, "_path_name"):
        return f"{_try(lambda: v.Class.Name)} {_try(lambda: v._path_name())}"
    if hasattr(v, "_type"):  # a struct
        return _struct(v)
    return repr(getattr(v, "name", v))


def _struct(value) -> str:  # noqa: ANN001
    parts = []
    for f in _try(lambda: list(value._type._fields()), []) or []:
        if str(f.Class.Name).endswith("Property"):
            parts.append(f"{f.Name}={_val(_try(lambda f=f: value._get_field(f)))}")
    return "{" + ", ".join(parts) + "}"


def _props(o, indent: str = "    ") -> None:  # noqa: ANN001
    """Every property of an object, one line each (arrays: their first items)."""
    for f in _try(lambda: list(o.Class._fields()), []) or []:
        if not str(f.Class.Name).endswith("Property"):
            continue
        v = _try(lambda f=f: getattr(o, str(f.Name)))
        if hasattr(v, "__len__") and not isinstance(v, str) and not hasattr(v, "_type") and not hasattr(v, "_path_name"):
            items = _try(lambda v=v: list(v), [])
            lines.append(f"{indent}{f.Name} [{len(items)}]: " + ", ".join(_val(x) for x in items[:12]))
        else:
            lines.append(f"{indent}{f.Name} = {_val(v)}")


def _where(a) -> str:  # noqa: ANN001
    loc = _try(lambda: a.Location, None)
    return f"({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})" if loc is not None and not isinstance(loc, str) else "?"


def _behaviors(definition) -> None:  # noqa: ANN001
    provider = _try(lambda: definition.BehaviorProviderDefinition, None)
    lines.append(f"  == behaviours ({_val(provider)})")
    explodes = []
    for seq in _try(lambda: list(provider.BehaviorSequences), []) or []:
        behaviors = _try(lambda s=seq: list(s.BehaviorData2), []) or []
        links = _try(lambda s=seq: list(s.ConsolidatedOutputLinkData), []) or []
        lines.append(f"  sequence {_try(lambda s=seq: s.BehaviorSequenceName)}: {len(behaviors)} behaviours")
        for n, b in enumerate(behaviors):
            beh = _try(lambda b=b: b.Behavior, None)
            lines.append(f"    [{n}] {_val(beh)}")
            if beh is not None and _try(lambda b=beh: str(b.Class.Name), "") == "Behavior_Explode":
                explodes.append(beh)

        def chain(packed, depth, seen, links=links, behaviors=behaviors) -> None:  # noqa: ANN001
            if not isinstance(packed, int):
                return
            start, count = packed >> 16, packed & 0xFFFF
            for link in links[start:start + count]:
                index = _try(lambda l=link: l.LinkIdAndLinkedBehavior & 0xFFFF, None)
                if not isinstance(index, int) or index >= len(behaviors):
                    lines.append(f"{'  ' * depth}-> ? {_val(link)}")
                    continue
                beh = _try(lambda i=index: behaviors[i].Behavior, None)
                lines.append(f"{'  ' * depth}-> [{index}] {_try(lambda b=beh: b.Class.Name)}"
                             f" (delay {_try(lambda l=link: l.ActivateDelay)})")
                if index not in seen and depth < 12:
                    chain(_try(lambda i=index: behaviors[i].OutputLinks.ArrayIndexAndLength, 0), depth + 1, seen | {index})

        for ev in _try(lambda s=seq: list(s.EventData2), []) or []:
            user = _try(lambda e=ev: e.UserData, None)
            lines.append(f"    event {_try(lambda u=user: u.EventName)} (enabled {_try(lambda u=user: u.bEnabled)})")
            chain(_try(lambda e=ev: e.OutputLinks.ArrayIndexAndLength, 0), 4, frozenset())
        _flush()
    for beh in explodes:
        lines.append(f"  == {_val(beh)}")
        _props(beh)
        exp = _try(lambda b=beh: b.Definition, None)
        if exp is not None and not isinstance(exp, str):
            lines.append(f"    its Definition {_val(exp)}:")
            _props(exp, "      ")
        _flush()


def _deep(io) -> None:  # noqa: ANN001
    lines.append(f"== {_val(io)} at {_where(io)}")
    for name in ("bCanBeUsed", "UsableIconType", "Health", "HealthMax", "bHasBeenKilled", "bHidden",
                 "InteractiveObjectState", "Balance"):
        lines.append(f"    {name} = {_val(_try(lambda n=name: getattr(io, n)))}")
    definition = _try(lambda: io.InteractiveObjectDefinition, None)
    lines.append(f"  definition: {_val(definition)}")
    _flush()
    if definition is not None and not isinstance(definition, str) and _try(lambda: definition._path_name(), "") not in done:
        done.add(definition._path_name())
        lines.append("  == definition's own properties")
        _props(definition)
        _flush()
        _behaviors(definition)


done: set[str] = set()
if DEF_NAME:
    lines.append(f"by definition {DEF_NAME}")
    ios = [io for io in unrealsdk.find_all("WillowInteractiveObject", exact=False)
           if _try(lambda io=io: str(io.InteractiveObjectDefinition.Name), "") == DEF_NAME]
    lines.append(f"  {len(ios)} in the level")
    _flush()
    for io in ios:
        _deep(io)
else:
    pawn = get_pc().Pawn
    me = pawn.Location
    lines.append(f"near the player at {_where(pawn)}, {NEAR} uu")
    near = []
    for a in unrealsdk.find_all("Actor", exact=False):
        if a.Name.startswith("Default__"):
            continue
        loc = _try(lambda a=a: a.Location, None)
        if loc is None or isinstance(loc, str):
            continue
        d = math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z))
        if d <= NEAR and a != pawn:
            near.append((d, a))
    near.sort(key=lambda x: x[0])
    for d, a in near:
        lines.append(f"  {d:5.0f} uu  {_val(a)}  def {_val(_try(lambda a=a: a.InteractiveObjectDefinition, None))}")
    _flush()
    for d, a in near:
        if _try(lambda a=a: a.Class._inherits(unrealsdk.find_class("WillowInteractiveObject")), False) is True:
            _deep(a)
lines.append("done")
_flush()
