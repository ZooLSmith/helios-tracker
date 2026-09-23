# Dev probe (in game), instant, read-only: the game's rarity per RarityLevel, from its own getters -
# GlobalsDefinition.GetRarityForLevel (-> EItemRarity) / GetRarityColorForLevel /
# GetRarityLevelColorsIndexforLevel, for levels 0-15 and 500-510 (probe_rarity2.txt found them;
# the RarityLevelColors table itself read empty). Plus the EItemRarity enum's members.
# Writes E:\Projects\python\borderlands-2\tools\probe_rarity3.txt (appends)
#   py exec(open(r"E:\Projects\python\borderlands-2\tools\probe_rarity3.py").read())
from enum import Enum
from pathlib import Path

import unrealsdk

OUT = Path(r"E:\Projects\python\borderlands-2\tools\probe_rarity3.txt")
lines: list[str] = ["#" * 70]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {str(ex)[:100]}>" if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if isinstance(value, Enum):
        return f"{value.name}({value.value})"
    if hasattr(value, "_type"):
        return "{" + ", ".join(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)))}"
                               for f in _try(lambda: list(value._type._fields()), [])
                               if f.Class.Name.endswith("Property")) + "}"
    if isinstance(value, tuple):
        return "(" + ", ".join(_brief(v) for v in value) + ")"
    return str(value)


enum = _try(lambda: unrealsdk.find_enum("EItemRarity"), None)
lines.append(f"EItemRarity: {[f'{m.name}={m.value}' for m in enum] if enum is not None and not isinstance(enum, str) else enum}")
globals_def = next((g for g in _try(lambda: list(unrealsdk.find_all("GlobalsDefinition", exact=False)), [])
                    if not str(g.Name).startswith("Default__")), None)
lines.append(f"globals: {_try(lambda: globals_def._path_name(), None)}")
for fn in ("GetRarityForLevel", "GetRarityColorForLevel", "GetRarityLevelColorsIndexforLevel", "GetRarityColorForRarityRating"):
    func = _try(lambda f=fn: getattr(globals_def, f), None)
    lines.append(f"{fn} args: {_try(lambda: [str(a.Name) + ':' + a.Class.Name for a in func.func._fields()])}")
for level in [*range(0, 16), *range(500, 511)]:
    parts = [f"{fn[3:]}={_brief(_try(lambda f=fn: getattr(globals_def, f)(level)))}"
             for fn in ("GetRarityForLevel", "GetRarityColorForLevel", "GetRarityLevelColorsIndexforLevel")]
    lines.append(f"  level {level:3d}: " + "  ".join(parts))
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_rarity3: {len(lines)} lines -> {OUT}")
