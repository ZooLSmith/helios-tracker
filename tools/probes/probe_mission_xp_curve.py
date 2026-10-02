# Dev probe (in game), instant: how a mission's XP (and cash) scales with its level vs the player's -
# for "do it soon" (outlevelled missions give less XP). WRITES GAME DATA, TEMPORARILY: for up to 3
# missions not picked up yet (GameStage not locked), sets MissionDefinition.GameStage to levels around
# the player's, reads the reward the game computes each time, then restores the original value (always,
# checked). v2: sweeps ExpLevel (GameStage alone didn't change the XP: first run), and one picked-up
# mission (its GameStage too).
# Best on a save you don't mind. Writes tools/probes/probe_mission_xp_curve.txt
#   py exec(open(r"<repo>\tools\probes\probe_mission_xp_curve.py").read())
import sys
from pathlib import Path

import unrealsdk
from mods_base import get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_mission_xp_curve.txt"  # the repo, through the mod's junction
MISSIONS = 3
BELOW, ABOVE = 12, 6  # mission levels from player - BELOW to player + ABOVE
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _levels(mdef) -> str:  # noqa: ANN001
    return (f"GetExpLevel {_try(lambda: mdef.GetExpLevel())} GetGameStage {_try(lambda: mdef.GetGameStage())}"
            f" GetExpectedGameStage {_try(lambda: mdef.GetExpectedGameStage())} ExpLevel {_try(lambda: mdef.ExpLevel)}"
            f" GameStage {_try(lambda: mdef.GameStage)}")


def _sweep(mdef, pc, player: int, field: str) -> None:  # noqa: ANN001
    """Sets `field` to levels around the player's, reads the reward each time, restores it (always)."""
    original = int(getattr(mdef, field))
    lines.append(f"   -- sweep {field} (was {original}) | mission level | gap | xp | cash")
    try:
        for level in range(max(1, player - BELOW), player + ABOVE + 1):
            setattr(mdef, field, level)
            xp = _try(lambda: mdef.GetExperienceReward(pc, False))
            cash = _try(lambda: mdef.GetCurrencyReward(pc, False))
            lines.append(f"   {level:3d} | {level - player:+3d} | {xp} | {cash} | GetExpLevel {_try(lambda: mdef.GetExpLevel())}")
    finally:
        setattr(mdef, field, original)
    lines.append(f"   restored {field}: {int(getattr(mdef, field))} (was {original}) {'OK' if int(getattr(mdef, field)) == original else 'MISMATCH'}")


def _curve(mdef, pc, player: int) -> None:  # noqa: ANN001
    lines.append(f"== {_try(lambda: str(mdef.MissionName))!r} ({mdef.Name}) locked {_try(lambda: mdef.bGameStageLocked)}"
                 f" xp now {_try(lambda: mdef.GetExperienceReward(pc, False))} | {_levels(mdef)}")
    _sweep(mdef, pc, player, "ExpLevel")
    if _try(lambda: mdef.bGameStageLocked, False) is True:  # a picked-up one: does GameStage matter there?
        _sweep(mdef, pc, player, "GameStage")
    lines.append(f"   after: {_levels(mdef)}")


def main() -> None:
    lines.append("#" * 60)
    pc = get_pc()
    player = int(pc.PlayerReplicationInfo.ExpLevel)
    lines.append(f"player level {player}")
    tracker = next((t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")), None)
    picked = []
    for entry in list(tracker.MissionList):
        mdef = _try(lambda e=entry: e.MissionDef, None)
        if (mdef is None or isinstance(mdef, str) or _try(lambda m=mdef: m.bGameStageLocked, True) is not False
                or _try(lambda e=entry: e.Status.name, "") != "MS_NotStarted" or _try(lambda m=mdef: m.DlcExpansion, 1) is not None):
            continue
        picked.append(mdef)
        if len(picked) >= MISSIONS:
            break
    lines.append(f"{len(picked)} not-picked-up base-game missions")
    # plus one picked-up one (active, level locked): the control
    for entry in list(tracker.MissionList):
        mdef = _try(lambda e=entry: e.MissionDef, None)
        if _try(lambda e=entry: e.Status.name, "") == "MS_Active" and _try(lambda m=mdef: m.bGameStageLocked, False) is True:
            picked.append(mdef)
            break
    for mdef in picked:
        try:
            _curve(mdef, pc, player)
        except Exception as ex:  # noqa: BLE001
            lines.append(f"   failed: {type(ex).__name__}: {ex}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
with OUT.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"probe_mission_xp_curve: {len(lines)} lines -> {OUT}")
