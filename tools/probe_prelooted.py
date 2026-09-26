# Dev probe (in game), instant, read-only: containers the game spawns already looted show "Not looted yet" on the page
# (collector.py _is_looted: SimpleAnimState 7 AND bCanBeUsed[0] 0 - checked on containers the player opened; on the
# Pre-Sequel's Moonsurface, 6 lootable objects read not usable but not looted: storage lockers, a safe...). Stand next
# to a pre-looted container (and an unlooted one, for the difference) and run it: every lootable interactive object
# within 30 m - its name, definition, distance, SimpleAnimState, bCanBeUsed, then every simple property (bool / byte /
# int / float / name), one "key = value" per line to diff; its animation list (SimpleAnimInfo[].AnimName: the
# state's meaning - SimpleAnimState is an index into it).
# Properties only, no calls. Writes tools/probe_prelooted.txt (appends), after each object.
#   py exec(open(r"<repo>\tools\probe_prelooted.py").read())
import math
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_prelooted.txt"  # the repo, through the mod's junction
RANGE = 3000.0  # uu (30 m)
SIMPLE = ("BoolProperty", "ByteProperty", "IntProperty", "FloatProperty", "NameProperty")
SKIP = {"ObjectInternalInteger", "NetIndex", "LastRenderTime", "LastNetUpdateTime", "CreationTime", "LastThrottleCheck",
        "SkelUpdateTime"}
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


def _value(v):  # noqa: ANN001, ANN202
    v = getattr(v, "name", v)
    return round(v, 3) if isinstance(v, float) else v


def main() -> None:
    pawn = _try(lambda: get_pc().Pawn, None)
    ploc = _try(lambda: pawn.Location, None)
    if ploc is None or isinstance(ploc, str):
        print("probe_prelooted: no player position")
        return
    lines.append("#" * 70)
    lines.append(f"run at {time.strftime('%H:%M:%S')}, player at ({ploc.X:.0f}, {ploc.Y:.0f}, {ploc.Z:.0f})")
    _flush()
    for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
        loc = _try(lambda io=io: io.Location, None)
        if loc is None or isinstance(loc, str) or str(io.Name).startswith("Default__"):
            continue
        dist = math.dist((loc.X, loc.Y, loc.Z), (ploc.X, ploc.Y, ploc.Z))
        balance = _try(lambda io=io: io.BalanceDefinitionState.BalanceDefinition, None)
        lootable = bool(_try(lambda io=io: len(io.Loot), 0) or (balance is not None and not isinstance(balance, str) and (
            _try(lambda: len(balance.DefaultLoot), 0) or _try(lambda: len(balance.DefaultIncludedLootLists), 0))))
        if dist > RANGE or not lootable:
            continue
        name = _try(lambda: str(balance.DefaultDisplayName), "") if balance is not None and not isinstance(balance, str) else ""
        dname = _try(lambda io=io: str(io.InteractiveObjectDefinition.Name), "?")
        key = f"{dname}@{loc.X:.0f},{loc.Y:.0f}"
        lines.append(f"== {name!r} {key} distance {dist:.0f}: SimpleAnimState {_value(_try(lambda io=io: io.SimpleAnimState))!r}"
                     f", bCanBeUsed {_try(lambda io=io: list(io.bCanBeUsed))!r}")
        # its animations (SimpleAnimState: an index into this list - 7 / 12 / 4 are positions, per container type)
        state = _try(lambda io=io: int(io.SimpleAnimState), -1)
        for n, anim in enumerate(_try(lambda io=io: list(io.SimpleAnimInfo), []) or []):
            lines.append(f"{key}.SimpleAnimInfo[{n}] = {_try(lambda a=anim: str(a.AnimName))!r}{'   <== now' if n == state else ''}")
        for f in _try(lambda io=io: list(io.Class._fields()), []) or []:
            if str(f.Class.Name) in SIMPLE and str(f.Name) not in SKIP:
                lines.append(f"{key}.{f.Name} = {_value(_try(lambda f=f, io=io: io._get_field(f)))!r}")
        _flush()
    lines.append("done")
    _flush()


main()
print(f"probe_prelooted: written to {OUT}")
