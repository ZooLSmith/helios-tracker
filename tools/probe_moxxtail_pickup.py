# Dev probe (in game), instant, read-only: the pickups an activated Moxxtail spawns (the Pre-Sequel's buff drinks: its
# definition's Behavior_SpawnItems, bDisablePickups - GD_Moxxtails.Pickups.PickupDummy_*, a UsableItemDefinition: the
# page drew one as an "Other" pickup, "Usable Item", over the Moxxtail). What marks it as not pickable: for each
# WillowPickup within 60 m of the player, its inventory's class / definition, then every property of the pickup whose name
# has Pick / Use / Disable / Interact / Touch / Collision / Owner / Spawn / Mission / Hidden (arrays and structs shown), and
# the same for its inventory. Properties only, no calls. Writes tools/probe_moxxtail_pickup.txt (appends), after each.
#   py exec(open(r"<repo>\tools\probe_moxxtail_pickup.py").read())
import math
import re
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_moxxtail_pickup.txt"
RANGE = 6000.0
WORDS = re.compile(r"pick|use|disabl|interact|touch|collision|owner|spawn|mission|hidden", re.I)
lines: list[str] = []


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _show(v, depth: int = 0) -> str:  # noqa: ANN001
    if hasattr(v, "name") and not hasattr(v, "_path_name"):
        return str(v.name)
    if hasattr(v, "_path_name"):
        return f"{_try(lambda: v.Class.Name)} {_try(lambda: v._path_name())}"
    if hasattr(v, "_type") and depth < 2:
        return "{" + ", ".join(f"{f.Name}={_show(_try(lambda f=f: v._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(v._type._fields()), []) or []
                               if str(f.Class.Name).endswith("Property")) + "}"
    if hasattr(v, "__len__") and not isinstance(v, str):
        return "[" + ", ".join(_show(x, depth + 1) for x in list(v)[:6]) + "]"
    return repr(v)


def _props(obj, indent: str) -> None:  # noqa: ANN001
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if str(f.Class.Name).endswith("Property") and WORDS.search(str(f.Name)) and not str(f.Name).startswith("VfTable"):
            lines.append(f"{indent}{f.Name} [{f.Class.Name}] = {_show(_try(lambda f=f: obj._get_field(f)))[:300]}")


def main() -> None:
    ploc = _try(lambda: get_pc().Pawn.Location, None)
    if ploc is None or isinstance(ploc, str):
        print("probe_moxxtail_pickup: no player position")
        return
    lines.append("#" * 70)
    lines.append(f"run at {time.strftime('%H:%M:%S')}")
    _flush()
    for pickup in _try(lambda: list(unrealsdk.find_all("WillowPickup", exact=False)), []) or []:
        loc = _try(lambda p=pickup: p.Location, None)
        if loc is None or isinstance(loc, str) or str(pickup.Name).startswith("Default__"):
            continue
        dist = math.dist((loc.X, loc.Y, loc.Z), (ploc.X, ploc.Y, ploc.Z))
        if dist > RANGE:
            continue
        inv = _try(lambda p=pickup: p.Inventory, None)
        definition = _try(lambda i=inv: i.DefinitionData.ItemDefinition, None) if inv is not None else None
        lines.append(f"== {pickup.Class.Name} {pickup.Name} distance {dist:.0f}")
        lines.append(f"   inventory {_show(inv)}  definition {_show(definition)}")
        _props(pickup, "   pickup.")
        if inv is not None and not isinstance(inv, str):
            _props(inv, "   inventory.")
        _flush()
    lines.append("done")
    _flush()


main()
print(f"probe_moxxtail_pickup: written to {OUT}")
