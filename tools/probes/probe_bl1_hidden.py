# Dev probe (in game), instant, read-only: why one of Borderlands 1's Claptraps isn't seen in game while our map shows
# it (.agent/bl1.md). Firestone has two Claptrap pawns: WillowAIPawn_1 (a settler: seen) and WillowAIPawn_10 (Friendly,
# its MatineeGroupName 'Claptrap_BB_04': not seen) - both bHidden False (probe_bl1_npc.txt). Every field that differs
# between them, the pawns' and their mesh / collision components' - the game's switch for "not there".
# Properties only. Writes tools/probes/probe_bl1_hidden.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_hidden.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_hidden.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_hidden.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:160] if default == "<err>" else default


def _brief(value) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, (str, int, bool)):
        return repr(value) if isinstance(value, str) else str(value)
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if type(value).__name__ == "WrappedArray":
        return f"[{len(value)}]"
    return "<struct>"


def _scalars(obj) -> dict[str, str]:  # noqa: ANN001
    out = {}
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if f.Class.Name in ("BoolProperty", "IntProperty", "FloatProperty", "ByteProperty", "NameProperty", "ObjectProperty",
                            "StrProperty", "ArrayProperty"):
            out[str(f.Name)] = _brief(_try(lambda f=f: obj._get_field(f)))
    return out


def _diff(label: str, a, b) -> None:  # noqa: ANN001
    sa, sb = _scalars(a), _scalars(b)
    lines.append(f"== {label}: {_brief(a)} vs {_brief(b)}")
    for key in sorted(set(sa) | set(sb)):
        va, vb = sa.get(key), sb.get(key)
        if va != vb and not (va and vb and va.startswith(("WillowMind'", "WillowInventoryManager'", "CylinderComponent'",
                                                                "SkeletalMeshComponent'", "Willow", "Level'"))
                                and va.split("'")[0] == vb.split("'")[0]):
            lines.append(f"   {key}: {va}  |  {vb}")


pawns = {p._path_name(): p for p in unrealsdk.find_all("WillowAIPawn", exact=False) if "Firestone" in p._path_name()}
seen = next((p for path, p in pawns.items() if path.endswith("WillowAIPawn_1")), None)
unseen = next((p for path, p in pawns.items() if path.endswith("WillowAIPawn_10")), None)
lines.append(f"Firestone pawns: {sorted(pawns)}")
if seen is None or unseen is None:
    lines.append("one of WillowAIPawn_1 / _10 missing")
else:
    _diff("pawns (seen | not seen)", seen, unseen)
    for comp in ("Mesh", "CylinderComponent", "CollisionComponent"):
        a, b = _try(lambda c=comp: getattr(seen, c), None), _try(lambda c=comp: getattr(unseen, c), None)
        if a is not None and b is not None and not isinstance(a, str) and not isinstance(b, str):
            _diff(f"{comp}", a, b)
    a, b = _try(lambda: seen.Controller, None), _try(lambda: unseen.Controller, None)
    if a is not None and b is not None and not isinstance(a, str) and not isinstance(b, str):
        _diff("controllers", a, b)
lines.append("== done")
with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"probe_bl1_hidden: written to {OUT}")
