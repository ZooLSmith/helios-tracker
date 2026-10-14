# Dev probe (in game), instant, read-only: a mission item the page still shows after its choice was made (Dragon Keep's
# "Ell in Shining Armor": the bulky armor picked, the Metal Bikini left on the map - its objective never done, the
# mission ReadyToTurnIn; 2026-10-14). What tells it apart from the pickups the game still has in play: run it anywhere
# in the level (no need to stand by it).
# 1. every WillowPickup in the level: its item's name and class, bHidden, bPickupable;
# 2. the target (its item's name holds TARGET): all its simple properties (bool / byte / int / float / name / str,
#    objects by name) and its components', and its Inventory's - read, nothing called;
# 3. the fields where it differs from most of the other pickups (what takes it out of play, likely), then its full dump.
# Writes tools/probes/probe_mission_pickup.txt (overwrites; section by section)
#   py exec(open(r"<repo>\tools\probes\probe_mission_pickup.py").read())
import enum
import sys
from collections import Counter
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_mission_pickup.txt"  # the repo, through the mod's junction
TARGET = "bikini"  # in the item's name (lowercase)
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


def _dump(p) -> dict[str, str]:  # noqa: ANN001
    """The pickup's properties, each component's as "c<n>:<class>.<field>", its item's as "inv.<field>"."""
    out = dict(_props(p))
    for n, comp in enumerate(_try(lambda: list(p.Components), []) or []):
        if comp is None or isinstance(comp, str):
            continue
        prefix = f"c{n}:{comp.Class.Name}."
        out.update({prefix + k: v for k, v in _props(comp).items()})
    inv = _try(lambda: p.Inventory, None)
    if inv is not None and not isinstance(inv, str):
        out.update({"inv." + k: v for k, v in _props(inv).items()})
    return out


def _item(p) -> str:  # noqa: ANN001
    inv = _try(lambda: p.Inventory, None)
    if inv is None or isinstance(inv, str):
        return f"<no item: {inv}>"
    return f"{_try(lambda: inv.GetShortHumanReadableName(), '?')} ({inv.Class.Name})"


OUT.write_text("", encoding="utf-8")
pickups = [p for p in unrealsdk.find_all("WillowPickup", exact=False) if not p.Name.startswith("Default__")]

# --- 1. every pickup
lines.append(f"== {len(pickups)} pickups")
for p in pickups:
    loc = _try(lambda p=p: p.Location, None)
    where = f"({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})" if loc is not None and not isinstance(loc, str) else "?"
    lines.append(f"   {p.Name}  {_item(p)}  at {where}  bHidden={_try(lambda p=p: p.bHidden)}"
                 f"  bPickupable={_try(lambda p=p: p.bPickupable)}  bDeleteMe={_try(lambda p=p: p.bDeleteMe)}")
_flush()

# --- 2. the target
target = next((p for p in pickups if TARGET in _item(p).lower()), None)
if target is None:
    lines.append(f"== no pickup whose item's name holds {TARGET!r}: in its level? run again there")
    _flush()
else:
    others = [p for p in pickups if p is not target]
    target_dump = _dump(target)
    other_dumps = [_dump(p) for p in others]
    lines.append(f"== target {target.Name}: {_item(target)}; compared with the {len(others)} other pickups")
    _flush()

    # --- 3. where it differs from most of them
    lines.append("== fields where the target differs from most of the others (target value | the others' most common, count)")
    for key, value in sorted(target_dump.items()):
        seen = Counter(d.get(key, "<absent>") for d in other_dumps)
        if not seen:
            continue
        common, count = seen.most_common(1)[0]
        if value != common and count > len(other_dumps) / 2 and not key.endswith(("Location", "Name", "Tag")):
            lines.append(f"   {key}: {value} | {common} ({count}/{len(other_dumps)})")
    _flush()
    # the other mission items in the level, their flags side by side (the bulky armor, if still around)
    lines.append("== mission items (WillowMissionItem), a few fields each")
    for p in pickups:
        if "WillowMissionItem" in _item(p):
            d = _dump(p) if p is not target else target_dump
            keys = ("bHidden", "bPickupable", "bPickupAtRest", "bIsMissionItem", "bCollideActors", "bBlockActors",
                    "LifeSpan", "Physics", "Base", "Owner", "inv.Owner")
            lines.append(f"   {p.Name} {_item(p)}: " + ", ".join(f"{k}={d.get(k, '<absent>')}" for k in keys))
            meshes = [k for k in d if ":" in k and k.endswith(".HiddenGame")]
            lines.append("      meshes HiddenGame: " + ", ".join(f"{k.split('.')[0]}={d[k]}" for k in meshes))
    _flush()
    lines.append("== the target's full dump")
    lines += [f"   {k} = {v}" for k, v in sorted(target_dump.items())]
    _flush()
print(f"[probe_mission_pickup] -> {OUT}")
