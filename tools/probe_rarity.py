# Dev probe (in game), instant, read-only: the game's own rarity table - the page only knows rarity
# levels 0-6 and 500+, a friend's legendaries were level 9 ("Rarity 9"). Dumps
# GlobalsDefinition.RarityLevelColors (and the other rarity fields there), plus every weapon / item in
# memory by rarity level with its name, so each level can be matched to its colour.
# Writes tools/probe_rarity.txt (appends)
#   py exec(open(r"<repo>\tools\probe_rarity.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_rarity.txt"  # the repo, through the mod's junction
lines: list[str] = ["#" * 70]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.3f}" if isinstance(value, float) else str(value)
    if depth > 3:
        return "..."
    if hasattr(value, "_type"):
        return "{" + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return _try(lambda: value._path_name())
    if hasattr(value, "__len__"):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:40]) + "]"
    return str(value)


for g in _try(lambda: list(unrealsdk.find_all("GlobalsDefinition", exact=False)), []):
    if str(g.Name).startswith("Default__"):
        continue
    lines.append(f"== {g._path_name()}")
    for f in _try(lambda g=g: list(g.Class._fields()), []):
        if "arity" in str(f.Name) and f.Class.Name.endswith("Property"):
            value = _try(lambda f=f, g=g: g._get_field(f))
            if hasattr(value, "__len__") and not isinstance(value, str) and not hasattr(value, "_type"):
                lines.append(f"   {f.Name} ({len(value)}):")
                for i, v in enumerate(list(value)):
                    lines.append(f"      [{i}] {_brief(v)}")
            else:
                lines.append(f"   {f.Name} = {_brief(value)[:600]}")

lines.append("== items in memory by rarity level (a few names each)")
by_level: dict[int, list[str]] = {}
for cls in ("WillowWeapon", "WillowShield", "WillowGrenadeMod", "WillowClassMod", "WillowArtifact"):
    for inv in _try(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []):
        if str(inv.Name).startswith("Default__"):
            continue
        level = _try(lambda i=inv: int(inv.RarityLevel), None)
        if isinstance(level, int):
            by_level.setdefault(level, []).append(f"{cls[6:]}:{_try(lambda i=inv: i.GetShortHumanReadableName(), '?')}")
for level in sorted(by_level):
    lines.append(f"   {level:4d}: {len(by_level[level])} - {', '.join(by_level[level][:6])}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_rarity: {len(lines)} lines -> {OUT}")
