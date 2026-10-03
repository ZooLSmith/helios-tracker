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
- No subinterpreters (an older Python) / the worker won't start: the job runs here, politely (gamescan's pause and
  switch interval), as before.
Files only: no SDK, no UObjects.
"""

import hashlib
import json
import sys
import threading
import time
from pathlib import Path

from . import paths

HERE = Path(__file__).parent
ASSETS = paths.DATA / ".cache" / "assets"
VERSION = 2  # the rendering's: another number = every asset decoded again (2: BL1's item icons with their back shape)
JOB_TIMEOUT = 300.0  # s a job may take in the worker (the first scan: ~5 s)

_lock = threading.Lock()
_worker: dict = {}  # "interp", "jobs", "results", "thread" - or "failed": the in-process fallback

WORKER_CODE = """
import sys, types
pkg = types.ModuleType("helios_work")
pkg.__path__ = [mod_dir]
sys.modules["helios_work"] = pkg
from helios_work import gamework, upk
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


def run_job(job: str) -> bytes:
    """A job (JSON: {"do": ..., ...}) -> its bytes - in the worker (or here, the fallback)."""
    from . import gamecards, gamefonts, gameicons, gamescan  # noqa: PLC0415 - (the worker: helios_work's)

    j = json.loads(job)
    do = j["do"]
    if do == "scan":
        gamescan.scan_to_cache(Path(j["cooked"]), Path(j["cache"]))
        return b""
    if do == "font":
        return gamefonts.font_ttf(Path(j["package"]), j["export"], j["n"])
    if do == "icon":
        return gameicons.texture_png(Path(j["package"]), j["export"])
    if do == "card":
        return gamecards.layers_png(j["layers"])
    if do == "menuicon":  # (Borderlands 1's skill icons: bl1map.menu_icon_png)
        from . import bl1map  # noqa: PLC0415

        return _bgra_png(bl1map.clip_icon(Path(j["cooked"]), *j["parts"]))
    if do == "cardicon":  # (Borderlands 1's item card icons: bl1map.card_icon_png)
        from . import bl1map  # noqa: PLC0415

        return _bgra_png(bl1map.card_icon(Path(j["cooked"]), j["keys"], j["label"]))
    if do == "itemicon":  # (Borderlands 1's item icons: bl1map.item_icon_png)
        from . import bl1map  # noqa: PLC0415

        return _bgra_png(bl1map.item_icon(Path(j["cooked"]), j["label"]))
    raise ValueError(f"unknown job {do!r}")


def _bgra_png(drawn: tuple[int, int, bytes] | None) -> bytes:
    """A drawing (width, height, BGRA) as a PNG - b"" for none."""
    from . import gameicons  # noqa: PLC0415

    if drawn is None:
        return b""
    w, h, bgra = drawn
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    return gameicons.png(w, h, bytes(rgba))


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
    from . import gamescan, upk  # noqa: PLC0415

    old = sys.getswitchinterval()
    sys.setswitchinterval(gamescan.SWITCH_INTERVAL)
    upk.set_pause(gamescan.PAUSE)
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
