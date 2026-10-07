# Dev probe (in game), instant: a Vault symbol's discovered state on a co-op CLIENT. The client's game knows it (its use
# prompt, "Discover", only on the ones not found yet) but the symbol's AssociatedChallenge isn't replicated there
# (tools/probes/probe_directors.txt, NM_Client), so collector / games.GAME.objects.discovered doesn't ask.
# Logs:
#  - the net mode, the map;
#  - the local controller's fields about challenges / use / interaction (the use prompt's object), its
#    LevelChallengeUnlocks / OneOffLevelChallengeCompletion in full, its functions about challenges / use (signatures);
#  - the level challenge definitions loaded (GD_Challenges.LevelChallenges...): the map's in full, the others one line;
#  - every Vault symbol in the world's levels: its fields in full (the first one), then per symbol its number, challenge,
#    bCanBeUsed, use / icon fields; the WillowInteractiveObject functions about use / challenge (signatures);
#  - LAST (each its own section, the file written before: a crash still leaves the rest): per symbol
#    GetHasUnlockedLevelChallengeObject(symbol) - its AssociatedChallenge None here: what it gives is the question.
# Run it as a co-op CLIENT, standing next to a Vault symbol NOT discovered yet (its Discover prompt showing); a map with
# one found too if possible (Sanctuary). Then the same as the host / solo, the same place, to compare.
# Writes tools/probes/probe_vault_client.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_vault_client.py").read())
import enum
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_vault_client.txt"  # the repo, through the mod's junction
PC_FIELDS = re.compile(r"challenge|unlock|oneoff|levelobj|usab|usable|interact|icon|prompt|current.*use|use.*target", re.I)
PC_FUNCS = re.compile(r"challenge|levelobj|usab|usable|interact", re.I)
IO_FIELDS = re.compile(r"challenge|usab|use|interact|icon|prompt|discover", re.I)
IO_FUNCS = re.compile(r"challenge|usab|usable|interact|icon|discover", re.I)
lines: list[str] = []


def _save() -> None:
    OUT.write_text("\n".join(lines), encoding="utf-8")


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0, items_max: int = 40) -> str:  # noqa: ANN001
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
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1, items_max))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        items = list(value)
        return f"(len {len(items)}) [" + ", ".join(_brief(v, depth + 1, items_max) for v in items[:items_max]) + "]"
    return repr(value)


def _fields(obj, pattern, label: str) -> None:  # noqa: ANN001
    lines.append(f"== {label}: {_brief(obj)}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name.endswith("Property") and (pattern is None or pattern.search(str(f.Name))):
                lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f: _brief(obj._get_field(f)))}")
        c = c.SuperField


def _functions(obj, pattern, label: str) -> None:  # noqa: ANN001  (signatures only: none called)
    lines.append(f"== {label}")
    c = _try(lambda: obj.Class, None)
    while c is not None and not isinstance(c, str) and c.Name != "Object":
        for f in _try(lambda c=c: list(c._fields()), []):
            if f.Class.Name == "Function" and pattern.search(str(f.Name)):
                params = ", ".join(f"{p.Class.Name.replace('Property', '')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), []))
                lines.append(f"   {c.Name}.{f.Name}({params})")
        c = c.SuperField


def _world_levels() -> set[int]:  # (collector._levels)
    wi = ENGINE.GetCurrentWorldInfo()
    return {wi.Outer._get_address()} | {s.LoadedLevel._get_address() for s in wi.StreamingLevels
                                         if s is not None and s.LoadedLevel is not None}


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    map_name = str(_try(lambda: wi.GetStreamingPersistentMapName(), ""))
    lines.append(f"map: {map_name}  netmode: {_brief(_try(lambda: wi.NetMode))}  local pc: {_brief(pc)}")
    _save()
    # the controller
    _fields(pc, PC_FIELDS, "local controller: challenge / use fields")
    lines.append(f"   LevelChallengeUnlocks (full) = {_brief(_try(lambda: pc.LevelChallengeUnlocks), items_max=500)}")
    for n, entry in enumerate(_try(lambda: list(pc.OneOffLevelChallengeCompletion), []) or []):
        lines.append(f"   OneOffLevelChallengeCompletion[{n}] = {_brief(entry, items_max=500)}")
    _save()
    _functions(pc, PC_FUNCS, "local controller: functions about challenges / use (signatures)")
    _save()
    # the level challenge definitions loaded
    base = map_name.lower().removesuffix("_p")
    defs = [d for d in _try(lambda: list(unrealsdk.find_all("ChallengeDefinition", exact=False)), [])
            if "levelchallenges" in str(_try(d._path_name, "")).lower()]
    lines.append(f"== {len(defs)} level challenge definitions loaded (map base name {base!r})")
    full = [d for d in defs if base and base in str(d.Name).lower()] or defs[:2]
    for d in defs:
        if d not in full:
            lines.append(f"   {_try(d._path_name)}")
    for d in full:
        _fields(d, None, f"challenge definition {_try(d._path_name)}")
        _save()
    # the symbols
    levels = _world_levels()
    symbols = [io for io in _try(lambda: list(unrealsdk.find_all("WillowInteractiveObject", exact=False)), [])
               if not io.Name.startswith("Default__") and io.Outer is not None and io.Outer.Class.Name == "Level"
               and io.Outer._get_address() in levels and not io.bDeleteMe
               and io.InteractiveObjectDefinition is not None and io.InteractiveObjectDefinition.Name == "IO_VaultRoy"]
    lines.append(f"== {len(symbols)} Vault symbols in the world's levels")
    pawn = _try(lambda: pc.Pawn, None)
    here = pawn.Location if pawn is not None and not isinstance(pawn, str) else None
    symbols.sort(key=lambda io: (io.Location.X - here.X) ** 2 + (io.Location.Y - here.Y) ** 2 + (io.Location.Z - here.Z) ** 2
                 if here is not None else 0)
    _save()
    if symbols:
        _fields(symbols[0], None, f"the nearest symbol {symbols[0].Name}: every field")
        _save()
        _functions(symbols[0], IO_FUNCS, "WillowInteractiveObject functions about use / challenge (signatures)")
        _save()
    for io in symbols:
        loc = io.Location
        dist = (((loc.X - here.X) ** 2 + (loc.Y - here.Y) ** 2 + (loc.Z - here.Z) ** 2) ** 0.5 / 100) if here is not None else -1
        _fields(io, IO_FIELDS, f"symbol {io.Name} number={io.NumberInChallengeGroup} {dist:.1f} m")
        _save()
    # the map's level object challenges (ECT_LevelObject, AssociatedMap = this map) and this player's mask for each:
    # LevelChallengeUnlocks entries = LevelChallengeObjectGroupIdx << 11 | the found objects' bits (bit number - 1) - one
    # sample (Sanctuary: 27 << 11 | 4 = 55300, symbol 3 found): checked here on more
    unlocks = [int(v) for v in _try(lambda: list(pc.LevelChallengeUnlocks), []) or []]
    lines.append("== LevelChallengeUnlocks decoded (>> 11, & 0x7FF): " + ", ".join(f"{v} = group {v >> 11} mask {v & 0x7FF:#b}" for v in unlocks))
    lines.append(f"== level object challenges of {map_name}")
    for d in defs:
        same_map = str(_try(lambda d=d: d.AssociatedMap, "")).lower() == map_name.lower()
        if same_map and getattr(_try(lambda d=d: d.ChallengeType), "name", "") == "ECT_LevelObject":
            group = int(_try(lambda d=d: d.LevelChallengeObjectGroupIdx, -1))
            mask = [v & 0x7FF for v in unlocks if v >> 11 == group]
            lines.append(f"   {d.Name} group={group} goal={_try(lambda d=d: d.GoalValue)} '{_try(lambda d=d: d.ChallengeName)}' "
                         f"mask={[bin(m) for m in mask]}")
    _save()
    # GetAssociatedChallenge() (no parameters): the challenge on a client, where the property is None?
    lines.append("== GetAssociatedChallenge() per symbol (each line written before the next call)")
    for io in symbols:
        lines.append(f"   {io.Name} number={io.NumberInChallengeGroup}: calling...")
        _save()
        lines[-1] = lines[-1].replace("calling...", _brief(_try(lambda io=io: io.GetAssociatedChallenge())))
        _save()
    # last: the call, its challenge None on a client
    lines.append("== GetHasUnlockedLevelChallengeObject per symbol (each line written before the next call)")
    for io in symbols:
        lines.append(f"   {io.Name} number={io.NumberInChallengeGroup} challenge={_brief(_try(lambda io=io: io.AssociatedChallenge))}: calling...")
        _save()
        lines[-1] = lines[-1].replace("calling...", str(_try(lambda io=io: pc.GetHasUnlockedLevelChallengeObject(io))))
        _save()
    lines.append(f"== GetNumLevelObjectsFound per challenge definition of this map")
    for d in full:
        lines.append(f"   {_try(d._path_name)}: {_try(lambda d=d: pc.GetNumLevelObjectsFound(d))}")
        _save()


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_save()
print(f"probe_vault_client: {len(lines)} lines -> {OUT}")
