# Dev probe (in game), instant: where a co-op CLIENT keeps its character's discovered Vault symbols in memory. The
# client's controller has no LevelChallengeUnlocks (empty) and its symbols no challenge / number
# (tools/probes/probe_vault_client.txt, NM_Client) - but the character's save is loaded (the client sends it to join):
# its save game object (WillowSaveGame-like: LevelChallengeUnlocks, OneOffLevelChallengeCompletion - Gibbed's
# WillowTwoPlayerSaveGame) or a save manager's cache.
# Logs:
#  - the loaded classes named like a save game / save manager / challenge manager, their own properties;
#  - their instances (not the defaults): the fields about challenges / the character (name, class, level), in full;
#  - the local controller's fields about saves (a cached save game, a save slot);
#  - every Vault symbol: its position (the host's numbers by position - probe_vault_discovered.txt), number, challenge.
# Reads properties only (no function called). The output is written after each section.
# Run it as a co-op CLIENT in Sanctuary (a character with symbols found there if possible), then the same as host / solo.
# Writes tools/probes/probe_vault_save.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_vault_save.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_vault_save.txt"  # the repo, through the mod's junction
CLASSES = re.compile(r"savegame|savemanager|savedata|challengemanager|challengelist|playerchallenge|profile", re.I)
FIELDS = re.compile(r"challenge|unlock|oneoff|levelobj|playername|characterclass|playerclass|explevel|saveguid|savegameid|slot", re.I)
PC_FIELDS = re.compile(r"save|profile|challenge", re.I)
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
    if depth > 3:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1) for v in items[:300]) + "]"
    return repr(value)


def _fields(obj, pattern, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (pattern is None or pattern.search(str(f.Name))):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    lines.append(f"map: {_try(lambda: wi.GetStreamingPersistentMapName())}  netmode: {_brief(_try(lambda: wi.NetMode))}  "
                 f"local pc: {_brief(pc)}  name: {_try(lambda: pc.PlayerReplicationInfo.PlayerName)}")
    _save()
    # the classes
    classes = sorted((c for c in _try(lambda: list(unrealsdk.find_all("Class", exact=True)), []) if CLASSES.search(str(c.Name))),
                     key=lambda c: str(c.Name))
    lines.append(f"== {len(classes)} classes named like a save game / save manager / challenge manager")
    for c in classes:
        own = [f"{f.Name}:{f.Class.Name.replace('Property', '')}" for f in _try(lambda c=c: list(c._fields()), [])
               if f.Class.Name.endswith("Property")]
        lines.append(f"   {c.Name} < {_try(lambda c=c: c.SuperField.Name, '?')}: {', '.join(own[:60])}")
    _save()
    # their instances
    for c in classes:
        objs = [o for o in _try(lambda c=c: list(unrealsdk.find_all(str(c.Name), exact=True)), [])
                if not str(o.Name).startswith("Default__")]
        if not objs:
            continue
        lines.append(f"== {len(objs)} {c.Name} instances")
        for o in objs[:6]:
            _fields(o, FIELDS, f"{c.Name} {_try(o._path_name)}")
            _save()
    # the controller's save fields
    _fields(pc, PC_FIELDS, "local controller: save / profile / challenge fields")
    _save()
    # the symbols: positions (the host's numbers by position)
    symbols = [io for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), [])
               if not io.Name.startswith("Default__") and not io.bDeleteMe and io.InteractiveObjectDefinition is not None
               and io.InteractiveObjectDefinition.Name == "IO_VaultRoy"]
    lines.append(f"== {len(symbols)} Vault symbols")
    for io in symbols:
        loc = io.Location
        lines.append(f"   {_try(io._path_name)} at ({loc.X:.0f}, {loc.Y:.0f}, {loc.Z:.0f}) number={io.NumberInChallengeGroup} "
                     f"challenge={_brief(_try(lambda io=io: io.AssociatedChallenge))} bCanBeUsed={_brief(_try(lambda io=io: io.bCanBeUsed))}")
    _save()


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
print(f"probe_vault_save: {len(lines)} lines -> {OUT}")
