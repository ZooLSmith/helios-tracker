# Dev probe (in game), instant, read-only: where a Moxxtail's price is (the Pre-Sequel's buff drinks, bought: their
# balance carries a chest's loot list, EpicChestRedLoot - the page took them for epic chests). WillowInteractiveObject's
# bCostsToUse / CostsToUseType / CostsToUseAmount read nothing on them (the page's data, 2026-09-26). For each Moxxtail
# (its definition's name has "Moxxtail") within 60 m, and one other lootable object for comparison: those three raw,
# then every property whose name has Cost / Use / Usab / Price / Currency / Buy (any type, arrays and structs shown).
# Properties only, no calls. Writes tools/probes/probe_moxxtail.txt (appends), after each object.
#   py exec(open(r"<repo>\tools\probes\probe_moxxtail.py").read())
import math
import re
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_moxxtail.txt"  # the repo, through the mod's junction
RANGE = 6000.0
WORDS = re.compile(r"cost|use|usab|price|currenc|buy", re.I)
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


def _dump(io, label: str, dist: float) -> None:  # noqa: ANN001
    lines.append(f"== {label} {_try(lambda: io.InteractiveObjectDefinition._path_name())} distance {dist:.0f}")
    for name in ("bCostsToUse", "CostsToUseType", "CostsToUseAmount"):
        lines.append(f"   {name} = {_show(_try(lambda n=name: getattr(io, n)))}")
    for f in _try(lambda: list(io.Class._fields()), []) or []:
        if str(f.Class.Name).endswith("Property") and WORDS.search(str(f.Name)) and str(f.Name) not in (
                "bCostsToUse", "CostsToUseType", "CostsToUseAmount"):
            lines.append(f"   {f.Name} [{f.Class.Name}] = {_show(_try(lambda f=f: io._get_field(f)))[:300]}")
    _flush()


def main() -> None:
    ploc = _try(lambda: get_pc().Pawn.Location, None)
    if ploc is None or isinstance(ploc, str):
        print("probe_moxxtail: no player position")
        return
    lines.append("#" * 70)
    lines.append(f"run at {time.strftime('%H:%M:%S')}")
    _flush()
    other = False
    for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
        loc = _try(lambda io=io: io.Location, None)
        if loc is None or isinstance(loc, str) or str(io.Name).startswith("Default__"):
            continue
        dist = math.dist((loc.X, loc.Y, loc.Z), (ploc.X, ploc.Y, ploc.Z))
        if dist > RANGE:
            continue
        dname = str(_try(lambda io=io: io.InteractiveObjectDefinition.Name, ""))
        if "Moxxtail" in dname:
            _dump(io, "Moxxtail", dist)
        elif not other and _try(lambda io=io: len(io.Loot), 0) == 0 and "Moxxtail" not in dname and \
                _try(lambda io=io: io.BalanceDefinitionState.BalanceDefinition, None) is not None:
            other = True
            _dump(io, "another object (for comparison)", dist)
    lines.append("done")
    _flush()


main()
print(f"probe_moxxtail: written to {OUT}")
