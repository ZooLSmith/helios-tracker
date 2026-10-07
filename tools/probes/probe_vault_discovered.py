# Dev probe (in game), instant: where a player's discovered Vault symbols (IO_VaultRoy, the Cult of the Vault
# challenge) are kept - nothing on the object says it (.agent/notes.md, "Vault symbols").
# Leads: the symbol is an IILevelChallengeObject (NumberInChallengeGroup, AssociatedChallenge); the controller has
# GetHasUnlockedLevelChallengeObject(Interface LevelChallengeObject) and ClientSetLevelChallengeUnlockMask(
# AssociatedChallenge, Index, Mask, TotalObjectCount) (tools/probes/probe_mission_level.txt); the save keeps
# LevelChallengeUnlocks (ints: masks?) and OneOffLevelChallengeCompletion (Gibbed's WillowTwoPlayerSaveGame).
# Logs:
#  - every player controller's fields whose name looks challenge / unlock related (their values);
#  - every Vault symbol in the world's levels: number, challenge, position, and per controller
#    GetHasUnlockedLevelChallengeObject(symbol) and GetNumLevelObjectsFound(its challenge).
# Only these two functions are called (known signatures), only on symbols in the world's levels (collector._in_world:
# a level loaded outside the world crashed GetTargetName once). The output is written after each section.
# Run it in a map with some symbols discovered and some not (e.g. Sanctuary part way); on a co-op host, with a
# client who has discovered other ones.
# Writes tools/probes/probe_vault_discovered.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_vault_discovered.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_vault_discovered.txt"  # the repo, through the mod's junction
PATTERN = re.compile(r"challenge|unlock|oneoff|levelobj|discover", re.I)
lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.3f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:40]) + "]"
    return repr(value)


def _dump_matching(obj, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _world_levels() -> set[int]:  # (collector._levels)
    wi = ENGINE.GetCurrentWorldInfo()
    return {wi.Outer._get_address()} | {s.LoadedLevel._get_address() for s in wi.StreamingLevels
                                         if s is not None and s.LoadedLevel is not None}


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    lines.append(f"map: {_try(lambda: wi.GetStreamingPersistentMapName())}  local pc: {_brief(pc)}")
    pcs = [p for p in _try(lambda: list(unrealsdk.find_all("WillowPlayerController", exact=False)), [])
           if not p.Name.startswith("Default__")]
    lines.append(f"{len(pcs)} player controllers: " + ", ".join(
        f"{p.Name} ({_try(lambda p=p: p.PlayerReplicationInfo.PlayerName)}, local={_try(lambda p=p: p.IsLocalPlayerController())})"
        for p in pcs))
    _save()
    # where the masks might be kept
    for p in pcs:
        _dump_matching(p, f"controller {p.Name} (challenge / unlock fields)")
        _save()
    # the symbols
    levels = _world_levels()
    symbols = [io for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), [])
               if not io.Name.startswith("Default__") and io.Outer is not None and io.Outer.Class.Name == "Level"
               and io.Outer._get_address() in levels and not io.bDeleteMe
               and io.InteractiveObjectDefinition is not None and io.InteractiveObjectDefinition.Name == "IO_VaultRoy"]
    lines.append(f"== {len(symbols)} Vault symbols in the world's levels")
    _save()
    challenges = {}
    for io in sorted(symbols, key=lambda io: io.NumberInChallengeGroup):
        loc = io.Location
        chal = _try(lambda io=io: io.AssociatedChallenge, None)
        if chal is not None and not isinstance(chal, str):
            challenges[chal._path_name()] = chal
        lines.append(f"   {io.Name} number={io.NumberInChallengeGroup} challenge={_brief(chal)} "
                     f"at ({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f})")
        for p in pcs:
            lines.append(f"      {p.Name}: GetHasUnlockedLevelChallengeObject = "
                         f"{_try(lambda p=p, io=io: p.GetHasUnlockedLevelChallengeObject(io))}")
        _save()
    lines.append(f"== {len(challenges)} challenges")
    for path, chal in challenges.items():
        lines.append(f"   {path}")
        for p in pcs:
            lines.append(f"      {p.Name}: GetNumLevelObjectsFound = "
                         f"{_try(lambda p=p, chal=chal: p.GetNumLevelObjectsFound(chal))}")
        _save()


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
print(f"probe_vault_discovered: {len(lines)} lines -> {OUT}")
