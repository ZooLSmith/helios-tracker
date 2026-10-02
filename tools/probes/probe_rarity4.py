# Dev probe (in game), instant, read-only: every RarityLevel the game colours, 0-2000 - probe_rarity3
# only asked 0-15 / 500-520 and never met colour entries 9-11 (the wiki's Cursed / Gemstone tiers
# may be those, or the unnamed 8 / 14-16). Consecutive levels with the same colour entry and colour
# are one range. Then the items loaded now (pickups, inventories) whose level the page doesn't name,
# with their game name - to tie a tier to real items (have a Gemstone / Cursed item near you).
# Writes tools/probes/probe_rarity4.txt (appends)
#   py exec(open(r"<repo>\tools\probes\probe_rarity4.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_rarity4.txt"  # the repo, through the mod's junction
lines: list[str] = ["#" * 70]
NAMED = {0, 1, 2, 3, 4, 5, 6, 7, 12, 13, 17}  # colour entries the page names (model.js TIER_BY_ENTRY)


def _try(fn, default=None):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _rgb(c) -> str:  # noqa: ANN001
    return "#{:02x}{:02x}{:02x}/a{}".format(*(_try(lambda k=k: int(getattr(c, k)), 0) for k in "RGBA"))


enum = _try(lambda: unrealsdk.find_enum("EItemRarity"))
members = _try(lambda: [f"{m}={int(v)}" for m, v in enum.__members__.items()], [])  # aliases too
lines.append(f"EItemRarity: {members}")
g = next((x for x in _try(lambda: list(unrealsdk.find_all("GlobalsDefinition", exact=False)), [])
          if not str(x.Name).startswith("Default__")), None)
lines.append(f"globals: {_try(lambda: g._path_name())}")

entry_of: dict[int, int] = {}
ranges: list[list] = []  # [first, last, entry, colour, rarity]
for level in range(0, 2001):
    entry = _try(lambda lv=level: int(g.GetRarityLevelColorsIndexforLevel(lv)), -2)
    colour = _try(lambda lv=level: _rgb(g.GetRarityColorForLevel(lv)), "?")
    rar = _try(lambda lv=level: g.GetRarityForLevel(lv))
    rar = f"{rar.name}({rar.value})" if isinstance(rar, Enum) else str(rar)
    entry_of[level] = entry
    if ranges and ranges[-1][1] == level - 1 and ranges[-1][2:] == [entry, colour, rar]:
        ranges[-1][1] = level
    else:
        ranges.append([level, level, entry, colour, rar])
lines.append("levels (first-last: colour entry, colour, GetRarityForLevel):")
for first, last, entry, colour, rar in ranges:
    if entry == -1 and first > 520:  # (uncoloured levels past the known ones: one line is enough)
        lines.append(f"  {first:4d}-{last:4d}: entry -1 (none)")
        continue
    mark = "" if entry in NAMED or entry < 0 else "   <- not named by the page"
    lines.append(f"  {first:4d}-{last:4d}: entry {entry:2d}  {colour}  {rar}{mark}")
entries = sorted({e for e in entry_of.values() if e >= 0})
lines.append(f"colour entries met: {entries}")

# Items loaded now, at a level whose entry the page doesn't name
seen = 0
for cls, attr in (("WillowPickup", "InventoryRarityLevel"), ("WillowInventory", "RarityLevel")):
    for obj in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []):
        if str(obj.Name).startswith("Default__"):
            continue
        level = _try(lambda o=obj, a=attr: int(getattr(o, a)), None)
        if level is None or entry_of.get(level, -1) in NAMED:
            continue
        inv = obj.Inventory if cls == "WillowPickup" else obj
        name = _try(lambda i=inv: str(i.GetShortHumanReadableName()), "?")
        lines.append(f"  unnamed tier: {cls} {obj.Name} level {level} (entry {entry_of.get(level, '?')}): '{name}' "
                     f"{_try(lambda i=inv: i.Class.Name, '?')}")
        seen += 1
lines.append(f"loaded items at an unnamed tier: {seen}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_rarity4: {len(lines)} lines -> {OUT}")
