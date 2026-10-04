"""
The game files' heavy work - the packages' scan, fonts / icons decoded - off the game's Python: in a
subinterpreter (Python 3.14's concurrent.interpreters) with a GIL of its own, so it runs beside the game thread
instead of taking turns with it (a thread of ours, pure Python - LZO, DXT, PNG - held the one GIL: the game's hooks
waited on it every frame, the page's first load lagged the game).

- The worker: one subinterpreter, started on the first job, fed through a queue (a job: a JSON string; its answer:
  bytes); it imports this package's file-only modules under another name (helios_work: never the mod's
  __init__ - mods_base / unrealsdk aren't there). Jobs one at a time (a lock).
- Its results cached on disk (.cache/assets in paths.DATA, gitignored): a font / an icon decoded once per install, keyed by the job
  and its packages' sizes and dates (a patched package: decoded again).
- A job names its function (fn: a *_job of a file-only module, "games.bl2.files.gameicons:texture_job") and its
  arguments: the worker imports that module and calls it - it knows no job, no game. Built in code only (fn()), never
  from what a page asks.
- No subinterpreters (an older Python) / the worker won't start: the job runs here, politely (a pause after each
  decompressed block, a short switch interval), as before.
Files only: no SDK, no UObjects.
"""

import hashlib
import importlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import paths

HERE = Path(__file__).parent
ASSETS = paths.DATA / ".cache" / "assets"
VERSION = 4  # the rendering's: another number = every asset decoded again (4: element icons drawn without their level)
JOB_TIMEOUT = 300.0  # s a job may take in the worker (the first scan: ~5 s)
POLITE_PAUSE = 0.003  # s slept after each decompressed block, a job run in process
POLITE_SWITCH = 0.001  # s (Python's default: 0.005), a job run in process

_lock = threading.Lock()
_worker: dict = {}  # "interp", "jobs", "results", "thread" - or "failed": the in-process fallback

WORKER_CODE = """
import os, pkgutil, sys, types

def package(name, path):
    # the package and its subpackages as bare modules: their __init__ never runs here (games/__init__ picks a game,
    # imports the parts - none of the worker's business); a job's module imports through them
    pkg = types.ModuleType(name)
    pkg.__path__ = [path]
    sys.modules[name] = pkg
    for info in pkgutil.iter_modules([path]):
        if info.ispkg:
            package(name + "." + info.name, os.path.join(path, info.name))

package("helios_work", mod_dir)
from helios_work import gamework
from helios_work.formats import upk
upk.keep_open(True)  # (packages / atlases kept between jobs: a session's icons out of one atlas)
while True:
    job = jobs.get()
    if job is None:
        break
    try:
        results.put(b"\\x01" + gamework.run_job(job))
    except BaseException as ex:
        results.put(b"\\x00" + repr(ex).encode("utf-8", "replace"))
"""


def fn(job: Any) -> str:
    """A job's function as a job names it ("games.bl2.files.gameicons:texture_job"): a *_job function of the mod's
    file-only modules (no SDK at their module level: the worker imports them)."""
    module = job.__module__.partition(".")[2]  # (the package's name: helios_tracker here, helios_work in the worker)
    assert job.__name__.endswith("_job") and module, job
    return f"{module}:{job.__name__}"


def run_job(job: str) -> bytes:
    """A job (JSON: {"fn": fn(...), its arguments...}) -> its bytes: its function, called with the rest - in the worker
    (or here, the fallback)."""
    j = json.loads(job)
    module, _, name = j.pop("fn").partition(":")
    if not name.endswith("_job"):
        raise ValueError(f"not a job: {name!r}")
    return getattr(importlib.import_module(f"{__package__}.{module}"), name)(**j)


def _start() -> bool:
    if _worker:
        return "failed" not in _worker
    try:
        from concurrent import interpreters  # noqa: PLC0415

        interp = interpreters.create()
        jobs, results = interpreters.create_queue(), interpreters.create_queue()
        interp.prepare_main(jobs=jobs, results=results, mod_dir=str(HERE))
        thread = threading.Thread(target=interp.exec, args=(WORKER_CODE,), name="helios_tracker game files", daemon=True)
        thread.start()
        _worker.update(interp=interp, jobs=jobs, results=results, thread=thread, empty=interpreters.QueueEmpty)
        # (the module's there for a reload: its stop() ends the previous one)
        sys._helios_tracker_worker = sys.modules[__name__]  # type: ignore[attr-defined]  # noqa: SLF001
        return True
    except Exception:  # noqa: BLE001 - no subinterpreters here: in process
        _worker["failed"] = True
        return False


def _in_worker(job: str) -> bytes:
    _worker["jobs"].put(job)
    start = time.monotonic()
    while True:
        try:
            answer = _worker["results"].get(timeout=1)  # (whole seconds: 3.14's Queue.get truncates it - 0.5 is 0)
            break
        except _worker["empty"]:
            if not _worker["thread"].is_alive() or time.monotonic() - start > JOB_TIMEOUT:
                _worker.clear()
                _worker["failed"] = True  # (dead / stuck: the rest of the session in process)
                raise RuntimeError("the game files' worker stopped") from None
    if answer[:1] == b"\x01":
        return answer[1:]
    raise RuntimeError(answer[1:].decode("utf-8", "replace"))


def _polite(job: str) -> bytes:
    """In process: the thread yields to the game thread (1 ms switches, a pause after each decompressed block)."""
    from .formats import upk  # noqa: PLC0415

    old = sys.getswitchinterval()
    sys.setswitchinterval(POLITE_SWITCH)
    upk.set_pause(POLITE_PAUSE)
    try:
        return run_job(job)
    finally:
        upk.set_pause(0)
        sys.setswitchinterval(old)


def work(job: dict) -> bytes:
    """Runs a job in the worker (or here, politely) -> its bytes; raises if it failed. One at a time."""
    text = json.dumps(job, sort_keys=True)
    with _lock:
        if _start():
            try:
                return _in_worker(text)
            except RuntimeError:
                if "failed" not in _worker:
                    raise  # (the job's own error)
        return _polite(text)


def asset(job: dict, packages: list[Path]) -> bytes | None:
    """A job's bytes from the disk cache, else worked out (then cached); None if it failed / gave nothing.
    `packages`: the files it reads (their sizes and dates in the key)."""
    stamps = []
    for p in packages:
        try:
            st = p.stat()
            stamps.append([str(p), st.st_size, st.st_mtime_ns])
        except OSError:
            return None
    key = hashlib.sha1(json.dumps([VERSION, job, stamps], sort_keys=True).encode()).hexdigest()  # noqa: S324 - a file name
    path = ASSETS / key[:2] / f"{key}.bin"
    try:
        return path.read_bytes() or None
    except OSError:
        pass
    try:
        data = work(job)
    except Exception:  # noqa: BLE001 - missing / won't decode: none (not cached: asked again next session)
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError:
        pass
    return data or None


def mode() -> str:
    """How jobs run (for the log)."""
    return "in process" if "failed" in _worker else "subinterpreter" if _worker else "not started"


def stop() -> None:
    """Ends the worker (the mod's stop / a reload)."""
    with _lock:
        if "jobs" in _worker:
            _worker["jobs"].put(None)
            _worker["thread"].join(5)
            try:
                _worker["interp"].close()
            except Exception:  # noqa: BLE001, S110 - still running (a stuck job): left to the process' end
                pass
        _worker.clear()
