# Dev probe (in game): Borderlands 1's missions available but not picked up, for the page's mission list. Its log
# (pc.MissionPlaythroughData[playthrough].MissionList) has only the missions picked up; the controller's
# GetMissionEligibility reads WillowGameInfo.MissionTracker (WillowGame.u, offline) - does the tracker know every
# mission? 1. the tracker's fields (arrays: their length); 2. its MissionList: how many, how many in the log; 3. the
# ones not in the log: their GetMissionEligibility (a count per answer, the eligible ones by name - their giver unknown
# here); 4. every loaded MissionDefinition (find_all: the tracker lists the active one only): how many, the eligible
# ones not in the log with their MissionGiver (its localized text: where it's picked up). Writes probe_bl1_tracker.txt (appends), after each section.
#   py exec(open(r"<repo>\tools\probes\probe_bl1_tracker.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_tracker.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_tracker.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _enum(value) -> str:  # noqa: ANN001
    return f"{value.name} ({int(value)})" if isinstance(value, Enum) else repr(value)


mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
wi = _try(lambda: mods_base.ENGINE.GetCurrentWorldInfo(), None)
game = _try(lambda: wi.Game, None)
tracker = _try(lambda: game.MissionTracker, None)
lines.append(f"== tracker {_try(lambda: tracker._path_name())} (class {_try(lambda: tracker.Class.Name)})")
for f in _try(lambda: list(tracker.Class._fields()), []) or []:
    if str(f.Class.Name).endswith("Property"):
        v = _try(lambda f=f: tracker._get_field(f))
        n = _try(lambda v=v: len(v), None) if not isinstance(v, (str, int, float)) else None
        lines.append(f"   {f.Name} ({f.Class.Name}): {f'[{n}]' if n is not None else str(v)[:200]}")
_flush()

playthrough = _try(lambda: int(wi.GRI.HostCurrentPlaythrough), 0)
log = _try(lambda: list(pc.MissionPlaythroughData[playthrough].MissionList), []) or []
logged = {_try(lambda e=e: e.MissionDef._path_name(), "") for e in log}
lines.append(f"== log (playthrough {playthrough}): {len(log)} missions")
everything = _try(lambda: list(tracker.MissionList), []) or []
defs = []
for e in everything:
    d = e if hasattr(e, "_path_name") else _try(lambda e=e: e.MissionDef, None)
    if d is not None and not isinstance(d, str):
        defs.append(d)
lines.append(f"== tracker.MissionList: {len(everything)} entries ({len(defs)} definitions), {sum(d._path_name() in logged for d in defs)} in the log")
_flush()

answers, eligible = {}, []
for d in defs:
    if d._path_name() in logged:
        continue
    a = _try(lambda d=d: pc.GetMissionEligibility(d))
    key = getattr(a, "name", str(a))
    answers[key] = answers.get(key, 0) + 1
    if key == "ME_Eligible":
        eligible.append(f"{d._path_name()} {_try(lambda d=d: str(d.MissionName))!r}")
lines.append(f"== not in the log: {answers}")
lines += [f"   eligible: {x}" for x in eligible[:60]]
_flush()

import unrealsdk  # noqa: E402

loaded = [d for d in _try(lambda: list(unrealsdk.find_all("MissionDefinition", exact=False)), []) or []
          if "Default__" not in str(_try(lambda d=d: d.Name, ""))]
packages = {}
for d in loaded:
    pkg = _try(lambda d=d: d._path_name().split(".")[0], "?")
    packages[pkg] = packages.get(pkg, 0) + 1
lines.append(f"== loaded MissionDefinitions: {len(loaded)}, by package {packages}")
_flush()
answers, eligible = {}, []
for d in loaded:
    if d._path_name() in logged:
        continue
    a = _try(lambda d=d: pc.GetMissionEligibility(d))
    key = getattr(a, "name", str(a))
    answers[key] = answers.get(key, 0) + 1
    if key == "ME_Eligible":
        eligible.append(f"{d._path_name()} {_try(lambda d=d: str(d.MissionName))!r} giver {_try(lambda d=d: str(d.MissionGiver))!r}")
lines.append(f"== loaded, not in the log: {answers}")
lines += [f"   eligible: {x}" for x in eligible[:80]]
_flush()
