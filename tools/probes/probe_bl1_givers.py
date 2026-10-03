# Dev probe (in game): Borderlands 1's quest givers' "!" - the page shows none (the bounty board: one quest taken, one
# still offered, the game's "!"). BL2's: a giver's directives (io.Directives.MissionDirectives) against the mission log's
# not started missions - BL1's directives are on the object (WillowInteractiveObject.MissionDirectives: {MissionDefinition,
# bBeginsMission, bEndsMission}), its log only the missions picked up. WillowGame.u (offline, script): the object's
# GetEligibleMissions(WPC, out EligibleMissions) (its directives, filtered by the player's eligibility) and
# GetMissionsEligibility; the controller's GetMissionEligibility(InMission) (minimum level, dependencies, status).
# For the interactive objects within 30 m with directives: those fields, the two calls with the player's controller,
# GetMissionEligibility of each of their missions; the mission's status in the log. Writes probe_bl1_givers.txt (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1_givers.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1_givers.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1_givers.txt"
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


import math  # noqa: E402

import unrealsdk  # noqa: E402

mods_base = __import__("mods_base")
pc = _try(lambda: mods_base.get_pc(), None)
me = _try(lambda: pc.Pawn.Location, None)


def _path(o):  # noqa: ANN001, ANN202
    return getattr(o, "_path_name", lambda: o)()


found = 0
for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), []) or []:
    if "Default__" in str(_try(lambda i=io: i.Name, "")):
        continue
    loc = _try(lambda i=io: i.Location, None)
    if me is None or loc is None or isinstance(loc, str) or math.dist((loc.X, loc.Y, loc.Z), (me.X, me.Y, me.Z)) > 3000:
        continue
    directives = _try(lambda i=io: list(i.MissionDirectives), [])
    if not directives or isinstance(directives, str):
        continue
    found += 1
    lines.append(f"-- {_try(lambda: io.Class.Name)} {_try(lambda: io.Name)}: {_path(_try(lambda: io.InteractiveObjectDefinition))}")
    lines.append(f"   bAnnounceWhenMissionsAvailable={_try(lambda: io.bAnnounceWhenMissionsAvailable)} "
                 f"MissionDirectivesBitfield={_try(lambda: io.MissionDirectivesBitfield)} "
                 f"AnnouncedMissions={[_path(m) for m in (_try(lambda: list(io.AnnouncedMissions), []) or [])]}")
    for d in directives:
        mission = _try(lambda d=d: d.MissionDefinition, None)
        lines.append(f"   directive {_path(mission)} begins={_try(lambda d=d: d.bBeginsMission)} ends={_try(lambda d=d: d.bEndsMission)}: "
                     f"GetMissionEligibility={_try(lambda m=mission: pc.GetMissionEligibility(m))!r}")
    result = _try(lambda: io.GetEligibleMissions(pc))
    lines.append(f"   GetEligibleMissions(pc) -> {[_path(x) for x in result] if isinstance(result, (list, tuple)) else result!r}")
    if isinstance(result, tuple):
        for part in result:
            lines.append(f"     part: {[_path(x) for x in part] if hasattr(part, '__iter__') and not isinstance(part, str) else _path(part)!r}")
    _flush()
lines.append(f"== {found} objects with directives within 30 m")
_flush()
