# Dev probe (in game), instant, read-only: what each kind of property access costs from Python - the
# collector's per-update pawn / pickup reads are ~30 us each (5.9 ms for 12 pawns), too slow.
# Times N reads of each on an AI pawn (or the player's): by name, a struct and its member, the address,
# and via a property looked up once (_find + _get_field), plus an empty Python loop for reference.
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_perf.txt (appends)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_perf.py").read())
import time
from pathlib import Path

from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_perf.txt")
N = 2000
lines: list[str] = []


def _time(label: str, fn) -> None:  # noqa: ANN001
    try:
        fn()  # warm up / fail early
        start = time.perf_counter()
        for _ in range(N):
            fn()
        us = (time.perf_counter() - start) / N * 1e6
        lines.append(f"   {label:52s} {us:8.2f} us")
    except Exception as ex:  # noqa: BLE001
        lines.append(f"   {label:52s} failed: {type(ex).__name__}: {ex}")


def main() -> None:
    lines.append("#" * 60)
    pc = get_pc()
    wi = ENGINE.GetCurrentWorldInfo()
    pawn, p = None, wi.PawnList
    while p is not None:  # an AI pawn if any
        if "AIPawn" in str(p.Class.Name):
            pawn = p
            break
        p = p.NextPawn
    pawn = pawn or pc.Pawn
    lines.append(f"pawn: {pawn.Class.Name} {pawn.Name}")
    cls = pawn.Class
    _time("empty loop (reference)", lambda: None)
    _time("pawn._get_address()", lambda: pawn._get_address())
    _time("pawn.Class", lambda: pawn.Class)
    _time("pawn.Class.Name (str)", lambda: str(pawn.Class.Name))
    _time("pawn.bDeleteMe (bool by name)", lambda: pawn.bDeleteMe)
    _time("pawn.HealthVar (float by name)", lambda: pawn.HealthVar)
    _time("pawn.Location (struct)", lambda: pawn.Location)
    loc = pawn.Location
    _time("loc.X (member of a held struct)", lambda: loc.X)
    _time("pawn.Location.X (struct + member)", lambda: pawn.Location.X)
    _time("pawn.Rotation.Yaw", lambda: pawn.Rotation.Yaw)
    _time("pawn.NextPawn (object)", lambda: pawn.NextPawn)
    # a property looked up once, then read by field
    for name in ("HealthVar", "Location", "bDeleteMe"):
        prop = None
        try:
            prop = cls._find(name)
        except Exception as ex:  # noqa: BLE001
            lines.append(f"   _find({name}) failed: {type(ex).__name__}: {ex}")
        if prop is not None:
            _time(f"pawn._get_field(prop {name})", lambda prop=prop: pawn._get_field(prop))
    _time("GetHealth() (a function call)", lambda: pawn.GetHealth())


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_perf: {len(lines)} lines -> {OUT}")
