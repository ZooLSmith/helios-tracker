# Dev probe (in game), instant, read-only: what a co-op CLIENT has of the other players - their gear,
# skills, XP and action skill all live on the host (their controller / inventory manager), so this looks
# for what gets replicated anyway: the player info and pawn properties (local vs other, side by side),
# every inventory actor in memory with its owner, and every skill instance.
# Run it while joined to someone else's game.
# Writes tools/probes/probe_coop.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_coop.py").read())
import re
from enum import Enum
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_coop.txt"  # the repo, through the mod's junction
NET_MODES = {0: "standalone", 1: "dedicated server", 2: "listen server (host)", 3: "client"}
PAWN_KEYS = re.compile(r"Skill|Exp|Action|Inv|Equip|Shield|Grenade|Artifact|Relic|Weapon|Item|Cooldown|Level|Class"
                       r"|Mod|Gear|Slot|Badass|Pool|Replicated", re.I)
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):  # first: flag enums iterate over themselves (endless recursion)
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_type"):  # struct
        if depth > 1:
            return "{...}"
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(lambda: value.Name)}'"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = [_brief(v, depth + 1) for v in list(value)[:5]]
        return "[" + ", ".join(items) + (f", ... ({len(value)})" if len(value) > 5 else "") + "]"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _props(obj) -> list:  # noqa: ANN001
    return [f for f in _try(lambda: list(obj.Class._fields()), []) if f.Class.Name.endswith("Property")]


def _side_by_side(title: str, mine, theirs, keep=None) -> None:  # noqa: ANN001
    lines.append(f"== {title}: local | other")
    if theirs is None:
        lines.append("   (other is None)")
        return
    for f in _props(theirs):
        name = str(f.Name)
        if keep is not None and not keep.search(name):
            continue
        a = _brief(_try(lambda f=f: mine._get_field(f))) if mine is not None else "-"
        b = _brief(_try(lambda f=f: theirs._get_field(f)))
        if a in ("0", "0.00", "False", "None", "[]", "") and a == b:
            continue  # empty on both: noise
        lines.append(f"   {name:40s} {a[:120]:60s} | {b[:160]}")


wi = ENGINE.GetCurrentWorldInfo()
pc = get_pc()
lines.append("#" * 70)
lines.append(f"map {_try(wi.GetStreamingPersistentMapName)}, NetMode {NET_MODES.get(wi.NetMode, wi.NetMode)}")
my_pawn = _try(lambda: pc.Pawn, None)
my_pri = _try(lambda: pc.PlayerReplicationInfo, None)
others = []
p = wi.PawnList
while p is not None:
    if "PlayerPawn" in str(p.Class.Name) and p != my_pawn:
        others.append(p)
    p = _try(lambda q=p: q.NextPawn, None)
lines.append(f"local pawn {_brief(my_pawn)}, other player pawns: {[_brief(o) for o in others]}")
other = others[0] if others else None
other_pri = _try(lambda: other.PlayerReplicationInfo, None) if other is not None else None
lines.append(f"other: {_try(lambda: other_pri.PlayerName, None)!r}, Controller={_brief(_try(lambda: other.Controller, None))}"
             f" InvManager={_brief(_try(lambda: other.InvManager, None))}")
_side_by_side("PlayerReplicationInfo (every property)", my_pri, other_pri)
_side_by_side("pawn (gear / skill / level related)", my_pawn, other, PAWN_KEYS)

lines.append("== inventory actors in memory (owner / instigator)")
for cls in ("WillowWeapon", "WillowShield", "WillowGrenadeMod", "WillowClassMod", "WillowArtifact"):
    for inv in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []):
        if str(inv.Name).startswith("Default__"):
            continue
        owner = _try(lambda i=inv: i.Owner, None)
        inst = _try(lambda i=inv: i.Instigator, None)
        who = "local" if my_pawn is not None and my_pawn in (owner, inst) else \
              "OTHER" if other is not None and other in (owner, inst) else "-"
        if who == "-" and not cls.endswith("Weapon"):
            who = f"owner={_brief(owner)}"
        if who == "-":
            continue  # AI weapons
        name = _try(lambda i=inv: i.GetShortHumanReadableName(), "?")
        lines.append(f"   {who:8s} {inv.Class.Name:28s} {name!r} lvl={_try(lambda i=inv: i.ExpLevel)}"
                     f" rarity={_try(lambda i=inv: i.RarityLevel)} slot={_try(lambda i=inv: i.QuickSelectSlot, '-')}"
                     f" location={_try(lambda i=inv: i.ItemLocation, '-')}")

lines.append("== skill instances in memory (instigator)")
for s in _try(lambda: list(unrealsdk.find_all("Skill", exact=False)), []):
    if str(s.Name).startswith("Default__"):
        continue
    inst = _try(lambda s=s: s.SkillInstigator, None)
    lines.append(f"   {_brief(_try(lambda s=s: s.Definition, None)):60s} state={_try(lambda s=s: s.SkillState)}"
                 f" instigator={_brief(inst)}")
lines.append("== controllers / skill trees in memory")
for c in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), []):
    if not str(c.Name).startswith("Default__"):
        lines.append(f"   {_brief(c)} local={c == pc} tree={_brief(_try(lambda c=c: c.PlayerSkillTree, None))}")

with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_coop: {len(lines)} lines -> {OUT}")
