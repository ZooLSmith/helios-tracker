# Dev probe (in game), instant, read-only: what one step of the mission log's full pass costs in Borderlands 1
# (2026-10-04: a step read only 4-5 entries in its 2 ms - ~0.5 ms an entry - and fetching the list ~2 ms each step:
# ~60 steps a pass, 2-5 ms each). Times, over the whole list, each read missions.py's step / _live makes - through the
# mod's own functions (the profile's, already called each pass: nothing new called), by the entry's status:
# 1. the list (games.GAME.missions.entries): its parts - the log copied, the statuses key, the not-picked list;
# 2. per entry: status, bHeardKickoff (eligibility, cached), the GameStage read, _definition (cached), _waiting_on, _live.
# Writes tools/probes/probe_bl1_log_cost.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_bl1_log_cost.py").read())
import sys
import time
from pathlib import Path

ht = sys.modules["helios_tracker"]
OUT = Path(ht.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_log_cost.txt"  # the repo, through the mod's junction
games, missions, util = ht.games, sys.modules["helios_tracker.missions"], sys.modules["helios_tracker.util"]
col = ht._collector
lines: list[str] = []


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _timed(fn, n: int = 1):  # noqa: ANN001, ANN202 - (ms per call, the last result or the exception)
    started = time.perf_counter()
    result = None
    for _ in range(n):
        try:
            result = fn()
        except Exception as ex:  # noqa: BLE001
            result = ex
    return (time.perf_counter() - started) * 1000 / n, result


tracker = col._tracker() if col._tracker is not None else None
part = games.GAME.missions
lines.append(f"== game {games.GAME.key}, tracker {tracker is not None}, part {type(part).__name__}")
_flush()

# 1. the list
ms, entries = _timed(lambda: part.entries(tracker), 5)
lines.append(f"== entries(): {ms:.2f} ms a call (5 calls), {len(entries) if isinstance(entries, list) else entries!r} entries")
if hasattr(part, "_mission_key"):
    from mods_base import ENGINE, get_pc

    pc = get_pc()
    playthrough = int(ENGINE.GetCurrentWorldInfo().GRI.HostCurrentPlaythrough)
    ms_log, log = _timed(lambda: list(pc.MissionPlaythroughData[playthrough].MissionList), 5)
    ms_status, status = _timed(lambda: [(e.MissionDef._get_address(), int(e.Status)) for e in log if e.MissionDef is not None], 5)
    ms_level, _ = _timed(lambda: int(pc.PlayerReplicationInfo.ExpLevel), 5)
    lines.append(f"   the log copied: {ms_log:.2f} ms ({len(log)} entries); the statuses: {ms_status:.2f} ms; the level: {ms_level:.3f} ms")
    lines.append(f"   key stable across two calls: {part._mission_key == part._mission_key}; eligibility cached: "
                 f"{len(part._eligible)}; not picked up: {len(part._not_picked)}")
    k1 = part._mission_key
    part.entries(tracker)
    lines.append(f"   key after another call unchanged: {k1 == part._mission_key}")
_flush()

# 2. per entry, by status
totals: dict[str, dict[str, float]] = {}
counts: dict[str, int] = {}
log_state = col._log
prev = {a: st for (_, a), st in zip(log_state._addrs, log_state._live, strict=False)}
status_by_id = {r["i"]: st[0] for r, st in zip(log_state._records, log_state._live, strict=False)}
progress = {a: st[1] for (_, a), st in zip(log_state._addrs, log_state._live, strict=False)}
for entry in entries if isinstance(entries, list) else []:
    ms_s, st = _timed(lambda e=entry: part.status(e))
    kind = f"{type(entry).__name__}/{st}"
    t = totals.setdefault(kind, {})
    counts[kind] = counts.get(kind, 0) + 1
    mdef = entry.MissionDef
    for name, fn in (
        ("status", lambda e=entry: part.status(e)),
        ("kickoff", lambda e=entry: e.bHeardKickoff),
        ("stage", lambda m=mdef: int(util.field(m, "GameStage"))),
        ("definition", lambda m=mdef: missions._definition(m)),
        ("waiting_on", lambda m=mdef: missions._waiting_on(m, status_by_id, progress)),
        ("progress", lambda e=entry: part.progress(e)),
        ("live", lambda e=entry, m=mdef: missions._live(e, missions._definition(m)[1], prev.get(m._get_address()), True,
                                                         status_by_id, progress)),
    ):
        ms_part, _ = _timed(fn)
        t[name] = t.get(name, 0.0) + ms_part
for kind, t in sorted(totals.items()):
    lines.append(f"== {kind}: {counts[kind]} entries - per entry: "
                 + ", ".join(f"{name} {v / counts[kind]:.3f} ms" for name, v in t.items()))
_flush()
print(f"[probe_bl1_log_cost] -> {OUT}")
