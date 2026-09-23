"""
The user's own `autoexec.ps1` (next to this file, optional): run while the server runs.

For a tunnel (`cloudflared tunnel run ...`) or anything else that should live with the map. It gets
the server's port in `HELIOS_PORT`, runs hidden (no console window over the game), its output goes
to `autoexec.log`. The process and everything it starts are in a job object: stopping the
server - or the game exiting / crashing - ends the whole tree.
"""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from .util import log, log_error

SCRIPT = Path(__file__).with_name("autoexec.ps1")
SCRIPT_LOG = Path(__file__).with_name("autoexec.log")

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32() -> ctypes.WinDLL:
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


class UserScript:
    """One run of the script; stop() ends it and whatever it started."""

    def __init__(self, port: int) -> None:
        self._k = _kernel32()
        self._job = self._k.CreateJobObjectW(None, None)
        if not self._job:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._k.SetInformationJobObject(self._job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                               ctypes.byref(info), ctypes.sizeof(info)):
            err = ctypes.WinError(ctypes.get_last_error())
            self._k.CloseHandle(self._job)
            raise err
        with SCRIPT_LOG.open("w", encoding="utf-8") as out:  # the child keeps its own handle
            self._proc = subprocess.Popen(  # noqa: S603
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(SCRIPT)],
                cwd=SCRIPT.parent, env={**os.environ, "HELIOS_PORT": str(port)},
                stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        # A child started in the instant before this isn't in the job: the script starts slower than that.
        if not self._k.AssignProcessToJobObject(self._job, int(self._proc._handle)):  # noqa: SLF001
            log_error("script job", ctypes.WinError(ctypes.get_last_error()))

    def stop(self) -> None:
        self._k.TerminateJobObject(self._job, 0)
        self._k.CloseHandle(self._job)
        self._job = None
        if self._proc.poll() is None:  # not in the job (assignment failed)
            self._proc.kill()


def start_script(port: int) -> UserScript | None:
    if sys.platform != "win32" or not SCRIPT.is_file():
        return None
    try:
        script = UserScript(port)
    except Exception as ex:  # noqa: BLE001
        log_error("starting autoexec.ps1", ex)
        return None
    log(f"started {SCRIPT.name} (output: {SCRIPT_LOG.name})")
    return script
