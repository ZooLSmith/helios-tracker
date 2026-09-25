# Dev probe (in game), instant: what tells containers apart - their loot configuration (item pools),
# balance loot lists, icons, and state (opened / used). One object per definition, the closest first.
# Run it once, then OPEN a chest or two and run it again: the state fields that change show "looted".
# Writes tools/probe_containers.txt (appends)
#   py exec(open(r"<repo>\tools\probe_containers.py").read())
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_containers.txt"  # the repo, through the mod's junction
MAX_TYPES = 30
STATE = re.compile(r"(?i)used|open|loot|state|enabled|usable|locked|spawn|looted|empty|active|cost")
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, (str, bytes, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else repr(value)
    if depth > 7:  # item pools sit deep: loot data > item attachments > pool
        return f"<{type(value).__name__}>"
    if type(value).__name__ == "WrappedArray":  # before structs: arrays have a _type too
        items = [_brief(v, depth + 1) for v in list(value)[:10]]
        return "[" + ", ".join(items) + (f", ... ({len(value)} total)" if len(value) > 10 else "") + "]"
    if hasattr(value, "_type"):  # WrappedStruct
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    return f"<{type(value).__name__}: {str(value)[:80]}>"


def _fields(obj, indent: str, match=None, stop=("Actor", "Object")) -> None:  # noqa: ANN001
    c, seen = obj.Class, set()
    while c is not None and c.Name not in stop:
        for f in c._fields():
            kind = f.Class.Name
            if f.Name in seen or not kind.endswith("Property") or kind == "DelegateProperty" or "VfTable" in f.Name:
                continue
            if match and not match.search(f.Name):
                continue
            seen.add(f.Name)
            lines.append(f"{indent}{c.Name}.{f.Name} = {_brief(_try(lambda f=f: obj._get_field(f)))[:700]}")
        c = c.SuperField


pawn = get_pc().Pawn
here = pawn.Location
lines.append("#" * 70)
by_def: dict[str, tuple[float, object]] = {}
for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
    if io.Name.startswith("Default__") or io.Outer is None or io.Outer.Class.Name != "Level":
        continue
    d = _try(lambda o=io: str(o.InteractiveObjectDefinition.Name), "?")
    dist = _try(lambda o=io: math.dist((o.Location.X, o.Location.Y, o.Location.Z), (here.X, here.Y, here.Z)), 1e12)
    if d not in by_def or dist < by_def[d][0]:
        by_def[d] = (dist, io)
for d, (dist, io) in sorted(by_def.items(), key=lambda kv: kv[1][0])[:MAX_TYPES]:
    lines.append(f"== {d}  ({io.Name}, {dist / 100:.0f} m away)")
    lines.append(f"   Loot = {_brief(_try(lambda o=io: o.Loot))[:3000]}")
    balance = _try(lambda o=io: o.BalanceDefinitionState.BalanceDefinition, None)
    lines.append(f"   balance = {_brief(balance)}")
    if hasattr(balance, "Class"):
        lines.append(f"   balance.DefaultLoot = {_brief(_try(lambda: balance.DefaultLoot))[:4000]}")
        lines.append(f"   balance.DefaultIncludedLootLists = {_brief(_try(lambda: balance.DefaultIncludedLootLists))[:800]}")
        for ll in _try(lambda: list(balance.DefaultIncludedLootLists), []) or []:
            lines.append(f"      list {_brief(ll)} LootData = {_brief(_try(lambda l=ll: l.LootData))[:4000]}")
        lines.append(f"   balance.Grades = {_brief(_try(lambda: balance.Grades))[:1200]}")
    definition = _try(lambda o=io: o.InteractiveObjectDefinition, None)
    if hasattr(definition, "Class"):
        _fields(definition, "   def.", re.compile(r"(?i)icon|loot|usable|type|grade|balance|category"), stop=("GBXDefinition", "Object"))
    _fields(io, "   io.", STATE)

with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"[probe_containers] {len(by_def)} object types, {len(lines)} lines -> {OUT}")
