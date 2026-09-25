# Dev probe (in game), 10 s: where the collector's state update spends its time (the log's "state.pawns" took 8-15 ms
# nearly every update with 53 pawns in Sanctuary). Wraps Collector._publish_state in cProfile for RUN_FOR seconds, then
# writes the most expensive functions (own time, then cumulative). No game calls of its own. Keep the map page open.
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
RUN_FOR = 10.0
col = MOD._collector  # noqa: SLF001
prof = cProfile.Profile()
state = {"calls": 0, "start": time.perf_counter(), "orig": None}


def _finish() -> None:
    col._publish_state = state["orig"]  # noqa: SLF001 - (back to the class's own)
    del col._publish_state  # noqa: SLF001
    buf = io.StringIO()
    st = pstats.Stats(prof, stream=buf)
    buf.write(f"{state['calls']} state updates profiled over {time.perf_counter() - state['start']:.1f} s\n\n== by own time\n")
    st.sort_stats("tottime").print_stats(25)
    buf.write("\n== by cumulative time\n")
    st.sort_stats("cumulative").print_stats(25)
    OUT.write_text(buf.getvalue(), encoding="utf-8")
    print(f"probe_profile: written {OUT}")


def _wrapped(now: float) -> None:
    state["calls"] += 1
    prof.enable()
    try:
        state["orig"](now)
    finally:
        prof.disable()
    if time.perf_counter() - state["start"] > RUN_FOR:
        _finish()


state["orig"] = col._publish_state  # noqa: SLF001 - (the bound method)
col._publish_state = _wrapped  # noqa: SLF001 - (an instance attribute: shadows the method until _finish)
print(f"probe_profile: {RUN_FOR:.0f} s, writing {OUT}")
