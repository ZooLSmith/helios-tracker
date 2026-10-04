# Dev probe (in game), instant, read-only: Borderlands 1's enemy / NPC names and shield card stats - both empty on the
# page there (.agent/bl1.md). BL2 names a pawn from its balance's PlayThroughs[].DisplayName; BL1's
# AIPawnBalanceDefinition has Grades[] = AIPawnGradeModifierData {ExpLevel, DisplayName...} instead (WillowGame.u,
# offline) - which grade a pawn is: its BalanceDefinitionState? BL2's shield stats: WillowItem.UIStatModifiers[].
# 1. AI pawns (up to 16, nearest first): their name fields, BalanceDefinitionState, its definition's Grades[]
#    (ExpLevel, DisplayName), their level / game stage, allegiance - enemies and NPCs both.
# 2. shields (the world's and the player's, up to 6): UIStatModifiers, every field, DefinitionData's.
# Properties only. Writes tools/probes/probe_bl1_names.txt after each section (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_names.py").read())
from enum import Enum
import math
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:  # the repo, through the mod's junction (sys.modules if the mod imported, else sdk_mods)
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_names.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_names.txt"
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
        return f"{value:.3f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray" or (hasattr(value, "__len__") and not hasattr(value, "_type")):
        items = list(value)  # (an array has a _type too: checked first - probe_bl1.py printed arrays as "{}")
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:8]) + "]"
    if hasattr(value, "_type"):  # struct
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    return str(value)


SKIP = {"Outer", "Class", "Name", "ObjectArchetype", "ObjectFlags", "HashNext", "HashOuterNext", "StateFrame",
        "LinkerIndex", "ObjectInternalInteger", "NetIndex", "VfTableObject", "Linker"}


def _fields(obj, limit: int = 4000, only=None) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        name = str(f.Name)
        if f.Class.Name.endswith("Property") and name not in SKIP and (only is None or only(name)):
            out.append(f"{name}={_brief(_try(lambda f=f: obj._get_field(f)))[:300]}")
    return ", ".join(out)[:limit]


def _live(name: str) -> list:
    return [o for o in _try(lambda: list(unrealsdk.find_all(name, exact=False)), []) or []
            if not str(o.Name).startswith("Default__")]


pc = _try(lambda: __import__("mods_base").get_pc(), None)
me = _try(lambda: pc.Pawn, None)
here = _try(lambda: me.Location, None)


def _dist(actor) -> float:  # noqa: ANN001
    loc = _try(lambda: actor.Location, None)
    if here is None or isinstance(here, str) or loc is None or isinstance(loc, str):
        return 1e12
    return math.dist((here.X, here.Y, here.Z), (loc.X, loc.Y, loc.Z))


# 1. AI pawns
lines.append("== AI pawns")
pawns = sorted(_live("WillowAIPawn"), key=_dist)[:16]
for pawn in pawns:
    lines.append(f"-- {pawn._path_name()} ({pawn.Class.Name}), {round(_dist(pawn))} uu away")
    lines.append("   names: " + _fields(pawn, 1500, lambda n: "name" in n.lower() or "display" in n.lower()))
    lines.append(f"   ExpLevel {_brief(_try(lambda p=pawn: p.ExpLevel))}, GameStage {_brief(_try(lambda p=pawn: p.GameStage))}, "
                 f"AwesomeLevel {_brief(_try(lambda p=pawn: p.AwesomeLevel))}, Allegiance {_brief(_try(lambda p=pawn: p.Allegiance))}, "
                 f"AIClass {_brief(_try(lambda p=pawn: p.AIClass))}")
    state = _try(lambda p=pawn: p.BalanceDefinitionState, None)
    lines.append(f"   BalanceDefinitionState: {_brief(state)}")
    balance = _try(lambda s=state: s.BalanceDefinition, None) if state is not None and not isinstance(state, str) else None
    if balance is not None and not isinstance(balance, str):
        grades = _try(lambda b=balance: list(b.Grades), [])
        lines.append(f"   balance {balance._path_name()} ({balance.Class.Name}): {len(grades) if isinstance(grades, list) else grades} grades")
        for n, grade in enumerate(grades if isinstance(grades, list) else []):
            lines.append(f"     [{n}] ExpLevel {_brief(_try(lambda g=grade: g.ExpLevel))}, DisplayName "
                         f"{_brief(_try(lambda g=grade: g.DisplayName))}")
        lines.append(f"   balance fields: {_fields(balance, 1500, lambda n: n not in ('Grades',))}")
    _flush()

# 2. shields
lines.append("== shields")
shields = _live("WillowShield")[:6]
lines.append(f"{len(shields)} live")
for shield in shields:
    lines.append(f"-- {shield._path_name()} (owner {_brief(_try(lambda s=shield: s.Owner))})")
    lines.append(f"   UIStatModifiers: {_brief(_try(lambda s=shield: s.UIStatModifiers))}")
    lines.append(f"   fields: {_fields(shield, 5000)}")
    data = _try(lambda s=shield: s.DefinitionData, None)
    lines.append(f"   DefinitionData: {_brief(data)}")
    item_def = _try(lambda d=data: d.ItemDefinition, None) if data is not None and not isinstance(data, str) else None
    if item_def is not None and not isinstance(item_def, str):
        lines.append(f"   item definition {item_def._path_name()}: {_fields(item_def, 3000)}")
    _flush()

# 3. missions (the page shows no objective markers, the mission panel no details): the tracker's list, the active
# mission's definition, the waypoints (BL1 has no MissionWaypoints on its tracker - probe_bl1.txt)
lines.append("== missions")
for tracker in _live("MissionTracker")[:1]:
    lines.append(f"-- tracker {tracker._path_name()}: ActiveMission {_brief(_try(lambda t=tracker: t.ActiveMission))}")
    entries = _try(lambda t=tracker: list(t.MissionList), [])
    lines.append(f"   MissionList: {len(entries) if isinstance(entries, list) else entries}")
    for entry in (entries if isinstance(entries, list) else [])[:12]:
        lines.append(f"     {_brief(entry)[:700]}")
    _flush()
    mission = _try(lambda t=tracker: t.ActiveMission, None)
    if mission is not None and not isinstance(mission, str):
        lines.append(f"-- active mission {mission._path_name()}: {_fields(mission, 6000)}")
        _flush()
waypoints = sorted(_live("WillowWaypoint"), key=_dist)[:15]
lines.append(f"-- waypoints (nearest {len(waypoints)})")
for wp in waypoints:
    lines.append(f"   {wp._path_name()} ({wp.Class.Name}) at {_brief(_try(lambda w=wp: w.Location))}: "
                 f"{_fields(wp, 1200, lambda n: not n.startswith(('b', 'Net', 'Collision', 'Draw', 'Rotation', 'Physics', 'Role', 'Remote', 'Tick', 'VfTable', 'Components', 'AllComponents', 'Timers', 'Detach', 'PrePivot', 'Custom', 'Replicated')))}")
_flush()

lines.append("== done")
_flush()
print(f"probe_bl1_names: written to {OUT}")
