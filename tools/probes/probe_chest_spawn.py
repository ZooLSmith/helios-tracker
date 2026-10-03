# Dev probe (in game), instant, read-only: chests seem to exist only near the player (the page shows them as you come
# close - 2026-10-04) - the game spawning them on approach (its population system's opportunity points), or us?
# 1. every interactive object, grouped by definition: how many, the nearest / farthest (m) - placed things exist far away
#    (the level's Bullymong piles up to 110 m: probe_hidden_pile.txt), spawned-on-approach ones only near;
# 2. every population point (classes named like PopulationOpportunity / PopulationPoint / Den): distance, what it spawns
#    (its population definition, by name), and its properties named like spawn / radius / range / active / count /
#    enabled / dormant / relevant / distance - read, nothing called.
# Run it twice if you can: once where chests show, once after walking away (where they don't).
# Writes tools/probes/probe_chest_spawn.txt (appends: one block per run)
#   py exec(open(r"<repo>\tools\probes\probe_chest_spawn.py").read())
import enum
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_chest_spawn.txt"  # the repo, through the mod's junction
POP_CLASSES = ("WillowPopulationOpportunityPoint", "PopulationOpportunityPoint", "PopulationOpportunityDen",
               "PopulationOpportunity", "WillowPopulationPoint", "PopulationPoint")
FIELDS = re.compile(r"spawn|radius|range|active|count|enabl|dormant|relevan|distance|popdef|population|def$|respawn|"
                    r"maxactive|isfull|bdisabled|trigger", re.I)
SIMPLE = {"BoolProperty", "ByteProperty", "IntProperty", "FloatProperty", "NameProperty", "ObjectProperty", "StrProperty"}
MAX_POINTS = 120
# an area to list in full (world units, as the page's coordinates: X / Y by the cursor) - None: skipped
BOX = ((-4239, -53082), (603, -41022))
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
        return f"{value:.1f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}:{value.Name}"
    return repr(value)[:60]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _dist(obj, me) -> float:  # noqa: ANN001
    loc = _try(lambda: obj.Location, None)
    if loc is None or isinstance(loc, str) or me is None:
        return float("inf")
    return math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100


def _fields(obj) -> list[str]:  # noqa: ANN001
    out, seen = [], set()
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and str(c.Name) != "Actor":
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            name = str(f.Name)
            if str(f.Class.Name) in SIMPLE and name not in seen and FIELDS.search(name):
                seen.add(name)
                out.append(f"{name}={_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = _try(lambda c=c: c.SuperField, None)
    return out


me = _try(lambda: get_pc().Pawn.Location, None)
lines.append("#" * 70)
lines.append(f"probe_chest_spawn {time.strftime('%Y-%m-%d %H:%M:%S')} - the player at "
             f"{(f'({me.X:.0f}, {me.Y:.0f}, {me.Z:.0f})') if me is not None else '?'}")

# --- 1. interactive objects by definition
groups: dict[str, list[float]] = defaultdict(list)
for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
    if io.Name.startswith("Default__"):
        continue
    definition = str(_try(lambda io=io: io.InteractiveObjectDefinition.Name, "?"))
    groups[definition].append(_dist(io, me))
lines.append(f"== interactive objects: {sum(len(v) for v in groups.values())}, by definition (count, nearest - farthest m)")
for definition, dists in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    lines.append(f"   {len(dists):3}  {min(dists):7.1f} - {max(dists):7.1f}  {definition}")
_flush()

# --- 2. population points
seen_points: set[int] = set()
points = []
for cls in POP_CLASSES:
    found = _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), None)
    if found is None or isinstance(found, str):
        lines.append(f"== no class {cls}")
        continue
    lines.append(f"== {cls}: {len([p for p in found if not p.Name.startswith('Default__')])}")
    for p in found:
        if p.Name.startswith("Default__") or (key := p._get_address()) in seen_points:
            continue
        seen_points.add(key)
        points.append(p)
_flush()
lines.append(f"== population points: {len(points)} (nearest {MAX_POINTS})")
for p in sorted(points, key=lambda p: _dist(p, me))[:MAX_POINTS]:
    lines.append(f"   {_dist(p, me):7.1f} m  {p.Class.Name}:{p.Name}  " + ", ".join(_fields(p)))
_flush()
# --- 3. everything in BOX: interactive objects (placed ones exist at any distance) and population points (what they'd
# spawn; bHasSpawned: there now - within their SpawnAndCullRadius of the player)
if BOX is not None:
    (x0, y0), (x1, y1) = (min(BOX[0][0], BOX[1][0]), min(BOX[0][1], BOX[1][1])), (max(BOX[0][0], BOX[1][0]), max(BOX[0][1], BOX[1][1]))

    def _inside(obj):  # noqa: ANN001, ANN202
        loc = _try(lambda: obj.Location, None)
        return loc is not None and not isinstance(loc, str) and x0 <= loc.X <= x1 and y0 <= loc.Y <= y1

    def _at(obj) -> str:  # noqa: ANN001
        loc = obj.Location
        return f"({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f}) {_dist(obj, me):.0f} m"

    in_box = [io for io in unrealsdk.find_all("WillowInteractiveObject", exact=False)
              if not io.Name.startswith("Default__") and _inside(io)]
    lines.append(f"== in the box x {x0}..{x1}, y {y0}..{y1}: {len(in_box)} interactive objects")
    for io in sorted(in_box, key=lambda o: str(_try(lambda o=o: o.InteractiveObjectDefinition.Name, "?"))):
        lines.append(f"   {_try(lambda io=io: io.InteractiveObjectDefinition.Name, '?')}  {io.Name}  {_at(io)}"
                     f"  bHidden={_try(lambda io=io: io.bHidden)}")
    box_points = [p for p in points if _inside(p)]
    lines.append(f"== in the box: {len(box_points)} population points")
    for p in sorted(box_points, key=lambda p: _dist(p, me)):
        what = _try(lambda p=p: p.PopulationDef.Name, None) or _try(lambda p=p: p.PointDef.Name, "?")
        lines.append(f"   {p.Class.Name}:{p.Name}  {what}  {_at(p)}  bHasSpawned={_try(lambda p=p: p.bHasSpawned)}"
                     f"  SpawnAndCullRadius={_try(lambda p=p: p.SpawnAndCullRadius)}")
    _flush()
print(f"[probe_chest_spawn] -> {OUT}")
