# Dev probe (in game), instant, read-only: what a Borderlands 1 pickup's definition says about its icon (2026-10-04: the
# page shows no symbol for health, cash, ammo - BL2's is its ItemDefinition.PickupFlagIcon, a texture its files scan
# indexes; BL1 has no scan). For the pickups within NEAR_M, one per item class + definition:
# 1. the chain the collector reads: Inventory.DefinitionData.ItemDefinition(.PickupFlagIcon), each link or why not;
# 2. the definition's properties naming an icon, a frame, a texture, a movie (names / strings / objects), every class of
#    its chain - and the objects they point to: class, path;
# 3. the inventory's own such properties (ZippyFrame, FlashFrame...), read as properties - nothing called.
# Writes tools/probes/probe_bl1_pickup_icons.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bl1_pickup_icons.py").read())
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_pickup_icons.txt"  # the repo, through the mod's junction
NEAR_M = 40.0
WORDS = re.compile(r"icon|frame|texture|movie|flash|zippy|image|symbol|hud", re.I)
KINDS = {"StrProperty", "NameProperty", "ObjectProperty", "IntProperty", "ByteProperty", "ClassProperty"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:160] if default == "<err>" else default


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _chain(cls):  # noqa: ANN001, ANN202
    out, c = [], cls
    while c is not None and not isinstance(c, str) and str(c.Name) != "Object":
        out.append(c)
        c = _try(lambda c=c: c.SuperField, None)
    return out


def _show(value) -> str:  # noqa: ANN001
    if value is None or isinstance(value, (str, int, float, bool)):
        return repr(value)
    if hasattr(value, "Class") and hasattr(value, "_path_name"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    return repr(value)[:120]


COOKED = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1]  # (replaced below: the game's CookedPC)
_files: dict[str, list[str]] = {}


def _package_files(name: str) -> list[str]:
    """The game's package files named `name` (CookedPC, its subfolders): where a texture's own package would be."""
    if name.lower() not in _files:
        _files[name.lower()] = [str(p.relative_to(COOKED)) for p in COOKED.rglob(f"{name}.upk")]
    return _files[name.lower()]


def _texture(label: str, value) -> None:  # noqa: ANN001
    if value is not None and not isinstance(value, str) and hasattr(value, "Class") and "Texture" in str(value.Class.Name):
        path = str(_try(value._path_name, ""))
        lines.append(f"         texture {path}: its package's file(s) {_package_files(path.split('.')[0])}")


def _iconish(label: str, obj) -> None:  # noqa: ANN001
    if obj is None or isinstance(obj, str) or not hasattr(obj, "Class"):
        lines.append(f"   {label}: {obj!r}"[:200])
        return
    lines.append(f"   {label}: {_show(obj)}")
    for c in _chain(obj.Class):
        for f in _try(lambda c=c: list(c._fields()), []) or []:
            if str(f.Class.Name) in KINDS and WORDS.search(str(f.Name)):
                value = _try(lambda f=f: obj._get_field(f))
                lines.append(f"      {c.Name}.{f.Name} = {_show(value)}")
                _texture(f.Name, value)


OUT.write_text("", encoding="utf-8")
COOKED = sys.modules["helios_tracker.gamedir"].cooked_dir() or COOKED
lines.append(f"== the game's packages: {COOKED}")
me =_try(lambda: get_pc().Pawn.Location, None)


def _dist(obj) -> float:  # noqa: ANN001
    loc = _try(lambda: obj.Location, None)
    if loc is None or isinstance(loc, str) or me is None or isinstance(me, str):
        return float("inf")
    return math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) / 100


seen = set()
pickups = sorted((d, p) for p in unrealsdk.find_all("WillowPickup", exact=False)
                 if not p.Name.startswith("Default__") and (d := _dist(p)) <= NEAR_M)
lines.append(f"== {len(pickups)} pickups within {NEAR_M:.0f} m")
_flush()
for distance, pickup in pickups:
    inv = _try(lambda p=pickup: p.Inventory, None)
    definition = _try(lambda i=inv: i.DefinitionData.ItemDefinition, None) if inv is not None and not isinstance(inv, str) else None
    key = (str(_try(lambda: inv.Class.Name, "?")), _show(definition))
    if key in seen:
        continue
    seen.add(key)
    lines.append(f"== {pickup.Name} at {distance:.1f} m: inventory {_show(inv)}")
    lines.append(f"   DefinitionData: {_show(_try(lambda: inv.DefinitionData))}")
    lines.append(f"   ItemDefinition: {_show(definition)}")
    flag = _try(lambda: definition.PickupFlagIcon)
    lines.append(f"   .PickupFlagIcon: {_show(flag)}")
    _texture("PickupFlagIcon", flag)
    _iconish("the definition", definition)
    _iconish("the inventory", inv)
    _flush()
print(f"[probe_bl1_pickup_icons] -> {OUT}")
