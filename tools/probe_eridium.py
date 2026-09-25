# Dev probe (in game), instant, read-only: how eridium pickups differ from cash - they both come out
# "cash" (Presentation "Credits"?). For every usable-item pickup in the level (cash, eridium, ammo,
# health...): its item definition, presentation, currency fields and distance to us, nearest first.
# Run it with eridium on the ground nearby (and cash, for comparison).
# Writes tools/probe_eridium.txt (appends)
#   py exec(open(r"<repo>\tools\probe_eridium.py").read())
import math
from enum import Enum
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_eridium.txt"  # the repo, through the mod's junction
lines: list[str] = ["#" * 70]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _v(value) -> str:  # noqa: ANN001
    if isinstance(value, Enum):
        return str(value.name)
    if hasattr(value, "_path_name"):
        return _try(lambda: value._path_name())
    return str(value)


me = _try(lambda: get_pc().Pawn.Location, None)
rows = []
for pickup in _try(lambda: list(unrealsdk.find_all("WillowPickup", exact=False)), []):
    if str(pickup.Name).startswith("Default__") or _try(lambda p=pickup: p.bDeleteMe, True) is True:
        continue
    inv = _try(lambda p=pickup: p.Inventory, None)
    if inv is None or str(inv.Class.Name) != "WillowUsableItem":
        continue
    loc = _try(lambda p=pickup: p.Location, None)
    dist = math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100 if loc is not None and me is not None else -1
    item_def = _try(lambda i=inv: i.DefinitionData.ItemDefinition, None)
    fields = {"def": _v(item_def),
              "Presentation": _v(_try(lambda d=item_def: d.Presentation, None)),
              "name": _try(lambda i=inv: i.GetShortHumanReadableName(), "?")}
    for f in ("FormOfCurrency", "CurrencyType", "bIsCurrency", "ItemName", "NonCompositeStaticMesh", "UIMeshRotation"):
        if (v := _try(lambda d=item_def, f=f: getattr(d, f), None)) is not None:
            fields[f] = _v(v)
    for f in ("CostsToPickUpType", "CostsToPickUpAmount"):
        if (v := _try(lambda p=pickup, f=f: getattr(p, f), None)) is not None:
            fields["pickup." + f] = _v(v)
    rows.append((dist, fields))
rows.sort(key=lambda r: r[0])
lines.append(f"{len(rows)} usable-item pickups, nearest first (distance in m)")
for dist, fields in rows[:40]:
    lines.append(f"  {dist:7.1f} m  " + "  ".join(f"{k}={v}" for k, v in fields.items()))
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_eridium: {len(rows)} pickups -> {OUT}")
