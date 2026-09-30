# Dev probe (in game), 20 s: where the collector's frequent tasks spend their time - the state update (the log's
# "state.pawns" took 8-15 ms nearly every update with 53 pawns in Sanctuary; "state.pickups" 5-20 ms with 40 pickups)
# and the players' inspection (every 2 s, 10-18 ms, once 557 ms: a hitch you see). Wraps each task (Collector.
# _publish_state, _publish_players) in its own cProfile for RUN_FOR seconds, then writes the most expensive functions
# (own time, then cumulative) and each task's calls / worst time. No game calls of its own. Keep the map page open.
# Writes tools/probe_profile.txt (overwrites; at the end)
#   py exec(open(r"<repo>\tools\probe_profile.py").read())
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

MOD = sys.modules["helios_tracker"]
OUT = Path(MOD.__file__).resolve().parents[1] / "tools" / "probe_profile.txt"
RUN_FOR = 20.0
TASKS = ("_publish_state", "_publish_players")
col = MOD._collector  # noqa: SLF001
start = time.perf_counter()
runs = {name: {"prof": cProfile.Profile(), "calls": 0, "worst": 0.0, "total": 0.0} for name in TASKS}
done = [False]


def _finish() -> None:
    done[0] = True
    for name in TASKS:
        col.__dict__.pop(name, None)  # (back to the class's own)
    buf = io.StringIO()
    buf.write(f"profiled over {time.perf_counter() - start:.1f} s\n")
    for name, r in runs.items():
        buf.write(f"\n######## {name}: {r['calls']} calls, {r['total']:.0f} ms in all, worst {r['worst']:.1f} ms\n")
        if not r["calls"]:
            continue
        st = pstats.Stats(r["prof"], stream=buf)
        buf.write("\n== by own time\n")
        st.sort_stats("tottime").print_stats(30)
        buf.write("\n== by cumulative time\n")
        st.sort_stats("cumulative").print_stats(30)
    OUT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"probe_profile: written {OUT}")


def _wrap(name: str):  # noqa: ANN202
    orig = getattr(col, name)  # (the bound method)
    r = runs[name]

    def wrapped(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        r["calls"] += 1
        t = time.perf_counter()
        r["prof"].enable()
        try:
            return orig(*args, **kwargs)
        finally:
            r["prof"].disable()
            ms = (time.perf_counter() - t) * 1000
            r["total"] += ms
            r["worst"] = max(r["worst"], ms)
            if not done[0] and time.perf_counter() - start > RUN_FOR:
                _finish()
    return wrapped


for task in TASKS:
    setattr(col, task, _wrap(task))  # (an instance attribute: shadows the method until _finish)
print(f"probe_profile: {RUN_FOR:.0f} s, writing {OUT}")
