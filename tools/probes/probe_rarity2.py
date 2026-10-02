# Dev probe (in game), instant, read-only: where the game gets an item's rarity colour -
# GlobalsDefinition.RarityLevelColors is empty (probe_rarity.txt), legendaries were at RarityLevel 9.
# 1) every property / function with "Rarity" or "Color" in its name on the inventory, pickup, item
#    card and globals classes (walking up the class chain); 2) per rarity level, one loaded item's
#    no-argument rarity / colour getters called (read-only getters only: Get*).
# Writes tools/probes/probe_rarity2.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_rarity2.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_rarity2.txt"  # the repo, through the mod's junction
KEYS = ("rarity", "color", "colour")
lines: list[str] = ["#" * 70]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {str(ex)[:80]}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.3f}" if isinstance(value, float) else str(value)
    if isinstance(value, tuple):
        return "(" + ", ".join(_brief(v, depth + 1) for v in value) + ")"
    if depth > 3:
        return "..."
    if hasattr(value, "_type"):
        return "{" + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return _try(lambda: value._path_name())
    if hasattr(value, "__len__"):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:20]) + "]"
    return str(value)


def _members(cls_name: str) -> None:
    cls = _try(lambda: unrealsdk.find_class(cls_name), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"== {cls_name}: not found")
        return
    lines.append(f"== {cls_name}")
    c = cls
    while c is not None:
        for f in _try(lambda c=c: list(c._fields()), []):
            name = str(f.Name)
            if f.Outer == c and any(k in name.lower() for k in KEYS):
                lines.append(f"   {c.Name}.{name} ({f.Class.Name})")
        c = _try(lambda c=c: c.SuperField, None)


for cls_name in ("WillowWeapon", "WillowItem", "WillowInventory", "WillowPickup", "GlobalsDefinition",
                 "WillowInventoryDefinition", "InventoryBalanceDefinition", "WillowPlayerController", "WillowHUD",
                 "WillowGFxItemCard", "ItemCardGFxObject", "WillowGFxMenuHelperItemCard"):
    _members(cls_name)

lines.append("== getters called on one item per rarity level")
seen: set[int] = set()
for cls in ("WillowWeapon", "WillowShield", "WillowGrenadeMod", "WillowClassMod", "WillowArtifact"):
    for inv in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []):
        level = _try(lambda i=inv: int(inv.RarityLevel), None)
        if str(inv.Name).startswith("Default__") or not isinstance(level, int) or level in seen:
            continue
        seen.add(level)
        lines.append(f"   rarity {level}: {cls} '{_try(lambda i=inv: i.GetShortHumanReadableName(), '?')}'")
        c = inv.Class
        while c is not None:
            for f in _try(lambda c=c: list(c._fields()), []):
                name = str(f.Name)
                if f.Outer != c or f.Class.Name != "Function" or not name.startswith("Get"):
                    continue
                if not any(k in name.lower() for k in KEYS):
                    continue
                result = _try(lambda i=inv, n=name: getattr(i, n)())
                lines.append(f"      {name}() = {_brief(result)[:300]}")
            c = _try(lambda c=c: c.SuperField, None)
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_rarity2: {len(lines)} lines -> {OUT}")
