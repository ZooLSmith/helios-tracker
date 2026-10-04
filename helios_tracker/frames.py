"""
Frame times: what the game feels, beside what our tasks take (collector._Timings). Our code runs on the game thread
(its hooks) and in the server's threads, which share the game's Python - the GIL: while a thread holds it, the game's
next call into one of our hooks waits for it (the frame stalls, and no task of ours shows it). So each frame is timed
- between PostRender calls - with what happened in it: our hooks' time (and which tasks ran), the server threads'
work, and a canary's lateness (a thread of ours waking every CANARY_EVERY: late = someone held the GIL - only
meaningful while our hooks weren't running, since the game thread holds it then). A spike (a frame over SPIKE_RATIO x
the usual and SPIKE_EXTRA_MS past it) is classed, in this order:
- "ours": our hooks took at least half the excess (a task: the slow-task report says more);
- "server": the server threads worked through a quarter of it or more (likely the GIL - our hooks waited for it);
- "gil": the canary woke late by half the excess or more - Python held the GIL, outside our hooks and the server's
  measured work (another mod's hooks, a thread of ours not measured);
- "game": none of those - the GIL was free: not Python (the game's own work, the system, the GPU).
Reported every REPORT_EVERY seconds, when there were spikes: the usual frame, per class the spikes (over 50 / 100 ms)
and the time lost, the worst ones.
Debug only (paths.DIAGNOSTICS): off, every call returns at once - no canary, no report.
No SDK: the hooks (__init__.py), the collector's tasks and the server's threads report here.
"""

import threading
import time
from typing import Any

from .paths import DIAGNOSTICS
from .util import log

REPORT_EVERY = 30.0  # s between reports (only when there were spikes)
SPIKE_RATIO = 2.0  # a spike: this many times the usual frame...
SPIKE_EXTRA_MS = 10.0  # ...and this much longer than it
GAP_MS = 1000.0  # a longer frame isn't one (a loading screen, a video, the window minimized): counted apart
BASE_WEIGHT = 0.02  # the usual frame: a running average, each frame (not a spike) this much of it
TASK_MS = 0.5  # a task this long or more is named in a spike's breakdown
WORST = 3  # spikes described in a report
CANARY_EVERY = 0.01  # s: the canary's sleep (a wake-up this often: microseconds of GIL each)
KINDS = ("ours", "server", "gil", "game")


class _Ours:
    """`with FRAMES.ours():` around a hook's body - the time it took counts as ours. Nested hooks (one of ours called
    from inside another, through the game): the outer one only."""

    __slots__ = ("_frames",)

    def __init__(self, frames: "Frames") -> None:
        self._frames = frames

    def __enter__(self) -> None:
        f = self._frames
        f._depth += 1
        if f._depth == 1:
            f._entered = time.perf_counter()

    def __exit__(self, *exc: object) -> None:
        f = self._frames
        f._depth -= 1
        if f._depth == 0:
            f._ours += time.perf_counter() - f._entered


class _Off:
    """`with FRAMES.ours():` with the measurements off: nothing."""

    __slots__ = ()

    def __enter__(self) -> None:
        pass

    def __exit__(self, *exc: object) -> None:
        pass


class Frames:
    """The frames' times and what happened in each. frame(), ours(), task(): the game thread; server_work(),
    server_count(): the server's threads (under the lock - a few microseconds); the canary: its own thread.
    `enabled` False (paths.DIAGNOSTICS): all of it does nothing."""

    def __init__(self, enabled: bool = DIAGNOSTICS) -> None:
        self.enabled = enabled
        self._lock = threading.Lock()
        self._depth = 0
        self._entered = 0.0
        self._ours_context = _Ours(self) if enabled else _Off()
        self._last = 0.0  # the last frame's start (perf_counter)
        self.usual = 0.0  # ms: the usual frame (a running average, spikes left out)
        # this frame's
        self._ours = 0.0  # s in our hooks
        self._tasks: list[tuple[str, float]] = []  # (task, ms) - the long enough ones
        self._server = 0.0  # s of the server threads' work
        self._server_counts: dict[str, int] = {}  # requests, snapshots... in this frame
        self._bytes = 0  # sent to the pages in this frame
        self._late = 0.0  # s: the canary's latest wake-up in this frame, past its sleep
        # the canary
        self._canary: threading.Thread | None = None
        self._canary_stop = threading.Event()
        # the report's
        self._frames = 0
        self._gaps = 0
        self._spikes: list[dict[str, Any]] = []
        self._next_report = 0.0

    def ours(self) -> _Ours:
        return self._ours_context

    def task(self, name: str, ms: float) -> None:
        if self.enabled and ms >= TASK_MS:
            self._tasks.append((name, ms))

    def server_work(self, kind: str, seconds: float, sent: int = 0) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._server += seconds
            self._server_counts[kind] = self._server_counts.get(kind, 0) + 1
            self._bytes += sent

    def server_count(self, kind: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._server_counts[kind] = self._server_counts.get(kind, 0) + 1

    def late(self, seconds: float) -> None:
        """The canary woke this late (past its sleep)."""
        with self._lock:
            self._late = max(self._late, seconds)

    def start_canary(self) -> None:
        """The canary thread (the mod enabled): wakes every CANARY_EVERY, says how late."""
        if not self.enabled or (self._canary is not None and self._canary.is_alive()):
            return
        self._canary_stop.clear()
        self._canary = threading.Thread(target=self._canary_loop, name="helios_tracker canary", daemon=True)
        self._canary.start()

    def stop_canary(self) -> None:
        self._canary_stop.set()
        if self._canary is not None:
            self._canary.join(1.0)
            self._canary = None

    def _canary_loop(self) -> None:
        while not self._canary_stop.is_set():
            asleep = time.perf_counter()
            time.sleep(CANARY_EVERY)
            self.late(max(0.0, time.perf_counter() - asleep - CANARY_EVERY))

    def frame(self, now: float) -> None:
        """A frame starts (PostRender, `now`: perf_counter): the one before it is measured."""
        if not self.enabled:
            return
        last, self._last = self._last, now
        ours, tasks = self._ours, self._tasks
        self._ours, self._tasks = 0.0, []
        with self._lock:
            server, counts, sent, late = self._server, self._server_counts, self._bytes, self._late
            self._server, self._server_counts, self._bytes, self._late = 0.0, {}, 0, 0.0
        if not last:
            return
        ms = (now - last) * 1000
        if ms > GAP_MS:
            self._gaps += 1
        else:
            self._frames += 1
            usual = self.usual or ms
            if ms > usual * SPIKE_RATIO and ms - usual > SPIKE_EXTRA_MS:
                excess = ms - usual
                ours_ms, server_ms, late_ms = ours * 1000, server * 1000, late * 1000
                kind = ("ours" if ours_ms >= excess / 2 else "server" if server_ms >= excess / 4
                        else "gil" if late_ms >= excess / 2 else "game")
                self._spikes.append({"ms": ms, "usual": usual, "ours": ours_ms, "tasks": tasks, "server": server_ms,
                                     "counts": counts, "sent": sent, "late": late_ms, "kind": kind})
            else:
                self.usual = usual + (ms - usual) * BASE_WEIGHT
        self._report(time.monotonic())

    def _report(self, now: float) -> None:
        if now < self._next_report:
            return
        first = not self._next_report
        self._next_report = now + REPORT_EVERY
        if self._spikes and not first:
            log(self.summary())
        self._frames = self._gaps = 0
        self._spikes = []

    def summary(self) -> str:
        """The report's line: the frames since the last one; per class the spikes (over 50 / 100 ms) and the time they
        lost (past the usual frame); the worst ones."""
        per_kind = []
        for kind in KINDS:
            of_kind = [s for s in self._spikes if s["kind"] == kind]
            if of_kind:
                lost = sum(s["ms"] - s["usual"] for s in of_kind)
                big = sum(s["ms"] > 50 for s in of_kind)
                huge = sum(s["ms"] > 100 for s in of_kind)
                per_kind.append(f"{kind} {len(of_kind)} ({big} > 50 ms, {huge} > 100 ms, {lost:.0f} ms lost)")
        worst = sorted(self._spikes, key=lambda s: -s["ms"])[:WORST]
        gaps = f", {self._gaps} gaps > {GAP_MS / 1000:.0f} s" if self._gaps else ""
        return (f"frames in the last {REPORT_EVERY:.0f} s: {self._frames}, usually {self.usual:.1f} ms{gaps}; "
                f"{len(self._spikes)} spikes: {', '.join(per_kind)} - worst: {'; '.join(_describe(s) for s in worst)}")


def _describe(spike: dict[str, Any]) -> str:
    """One spike: "182 ms (usual 16.4) server: ours 3.1 ms [state 2.0], server 96.0 ms [1 snapshot, 34 request], 120 KB
    sent, canary 90 ms late"."""
    tasks = sorted(spike["tasks"], key=lambda t: -t[1])
    ours = f"ours {spike['ours']:.1f} ms" + (f" [{', '.join(f'{n} {ms:.1f}' for n, ms in tasks)}]" if tasks else "")
    counts = ", ".join(f"{n} {k}" for k, n in sorted(spike["counts"].items()))
    server = f"server {spike['server']:.1f} ms" + (f" [{counts}]" if counts else "")
    sent = f", {spike['sent'] / 1024:.0f} KB sent" if spike["sent"] else ""
    return (f"{spike['ms']:.0f} ms (usual {spike['usual']:.1f}) {spike['kind']}: {ours}, {server}{sent}, "
            f"canary {spike['late']:.0f} ms late")


FRAMES = Frames()
