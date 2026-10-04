# Dev probe (in game), instant, read-only: how a Borderlands 1 NPC's pawn and its name go together (.agent/bl1.md).
# Its pawn has no balance (no name: Claptrap's AIPawnName 'ClapTrap' only); its name is an interactive object's
# definition's - gd_ClapTrap.NPC.NPC_ClapTrapFirestone, an InteractiveObjectDefinition, DisplayName "Claptrap"
# (offline). Which object, linked how to which pawn:
# 1. the AI pawns without a balance: Base, Owner, Attached[], Children[], their scalar / object fields;
# 2. the interactive objects whose definition is an NPC's (its path holds ".NPC.", a WillowInteractiveNPC - Dr. Zed - a bounty
#    board), or that are based on / owned by a pawn: their definition's name fields at run time, definition, DisplayName, Base, Owner, Location, the nearest such pawn and its distance.
# Properties only. Writes tools/probes/probe_bl1_npc.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_npc.py").read())
from enum import Enum
import math
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_npc.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_npc.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


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
        return f"{value:.1f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 2:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:10]) + "]"
    if hasattr(value, "_type"):
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


def _live(name: str) -> list:
    return [o for o in _try(lambda: list(unrealsdk.find_all(name, exact=False)), []) or []
            if not str(o.Name).startswith("Default__") and ".TheWorld:" in _try(lambda o=o: o._path_name(), "")]


def _dist(a, b) -> float:  # noqa: ANN001
    la, lb = _try(lambda: a.Location, None), _try(lambda: b.Location, None)
    if la is None or lb is None or isinstance(la, str) or isinstance(lb, str):
        return 1e12
    return math.dist((la.X, la.Y, la.Z), (lb.X, lb.Y, lb.Z))


# 1. the pawns without a balance
npcs = [p for p in _live("WillowAIPawn") if _try(lambda p=p: p.BalanceDefinitionState.BalanceDefinition, 1) is None]
lines.append(f"== AI pawns without a balance: {len(npcs)}")
for pawn in npcs:
    lines.append(f"-- {pawn._path_name()}: AIPawnName {_brief(_try(lambda p=pawn: p.AIPawnName))}, at {_brief(_try(lambda p=pawn: p.Location))}")
    for prop in ("bHidden", "bDeleteMe", "bCollideActors", "bBlockActors", "Physics", "MatineeGroupName", "Health", "DrawScale",
                 "Base", "Owner", "Attached", "Children", "Controller", "ObjectArchetype", "Tag", "Allegiance", "MissionDirectives",
                 "InteractiveObject", "UseObject", "NPCInteractiveObject", "TalkInteractiveObject"):
        lines.append(f"   {prop}: {_brief(_try(lambda p=pawn, n=prop: getattr(p, n)))[:600]}")
_flush()

# 2. the NPCs' interactive objects
ios = [io for io in _live("WillowInteractiveObject")
       if ".NPC." in _try(lambda io=io: io.InteractiveObjectDefinition._path_name(), "")
       or io.Class.Name == "WillowInteractiveNPC" or "BountyBoard" in _try(lambda io=io: io.InteractiveObjectDefinition._path_name(), "")
       or _try(lambda io=io: io.Base, None) in npcs or _try(lambda io=io: io.Owner, None) in npcs]
lines.append(f"== their interactive objects: {len(ios)}")
for io in ios:
    definition = _try(lambda io=io: io.InteractiveObjectDefinition, None)
    nearest = min(npcs, key=lambda p, io=io: _dist(io, p)) if npcs else None
    lines.append(f"-- {io._path_name()}: definition {_brief(definition)}, DisplayName "
                 f"{_brief(_try(lambda d=definition: d.DisplayName))}, at {_brief(_try(lambda io=io: io.Location))}")
    # its definition at run time (DisplayName: empty in the packages - filled from somewhere when loaded?)
    lines.append(f"   class {io.Class.Name}, bHidden {_brief(_try(lambda io=io: io.bHidden))}; definition's names: "
                 + ", ".join(f"{f.Name}={_brief(_try(lambda f=f, d=definition: d._get_field(f)))[:120]}"
                             for f in (_try(lambda d=definition: list(d.Class._fields()), []) or [])
                             if "name" in str(f.Name).lower() or "header" in str(f.Name).lower() or "mission" in str(f.Name).lower()))
    lines.append(f"   Base {_brief(_try(lambda io=io: io.Base))}, Owner {_brief(_try(lambda io=io: io.Owner))}, "
                 f"Attached {_brief(_try(lambda io=io: io.Attached))[:300]}, Tag {_brief(_try(lambda io=io: io.Tag))}")
    if nearest is not None:
        lines.append(f"   nearest pawn without a balance: {nearest._path_name()} at {_dist(io, nearest):.0f} uu")
_flush()
lines.append("== done")
_flush()
print(f"probe_bl1_npc: written to {OUT}")
