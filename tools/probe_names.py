# Dev probe (in game), instant: what each name source returns for every pawn in the level (to see
# why some enemies get no game name in helios_tracker). Stand near a few enemies / NPCs.
# Writes tools/probe_names.txt (appends)
#   py exec(open(r"<repo>\tools\probe_names.py").read())
import sys
from pathlib import Path

from mods_base import ENGINE

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_names.txt"  # the repo, through the mod's junction
lines: list[str] = []


def _call(obj, fn: str, *args) -> str:  # noqa: ANN001
    if not hasattr(obj, fn):
        return "<no such function>"
    try:
        return repr(getattr(obj, fn)(*args))
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"


def _get(fn) -> str:  # noqa: ANN001
    try:
        return repr(fn())
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"


wi = ENGINE.GetCurrentWorldInfo()
lines.append("#" * 70)
lines.append(f"map {wi.GetStreamingPersistentMapName()}")
pawn, n = wi.PawnList, 0
while pawn is not None and n < 300:
    n += 1
    lines.append(f"== {pawn.Class.Name} {pawn.Name}  AIClass={_get(lambda p=pawn: p.AIClass.Name)}")
    for fn in ("GetTargetName", "GetMapDisplayName", "GetTransformedName", "GetHumanReadableName"):
        lines.append(f"    {fn}() = {_call(pawn, fn)}    {fn}('') = {_call(pawn, fn, '')}")
    lines.append(f"    MasteredDisplayName = {_get(lambda p=pawn: p.MasteredDisplayName)}")
    lines.append(f"    BalanceDefinitionState = {_get(lambda p=pawn: p.BalanceDefinitionState)}")
    pawn = pawn.NextPawn

# Interactive objects: one per definition (barrels, chests, stations...), every name-ish source
import unrealsdk  # noqa: E402

seen: set[str] = set()
for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
    if io.Name.startswith("Default__") or io.Outer is None or io.Outer.Class.Name != "Level":
        continue
    definition = _get(lambda o=io: o.InteractiveObjectDefinition.Name)
    if definition in seen or len(seen) >= 40:
        continue
    seen.add(definition)
    lines.append(f"== IO {io.Class.Name} {io.Name} def={definition}")
    for fn in ("GetTargetName", "GetHumanReadableName"):
        lines.append(f"    {fn}() = {_call(io, fn)}    {fn}('') = {_call(io, fn, '')}")
    lines.append(f"    BalanceDefinitionState = {_get(lambda o=io: o.BalanceDefinitionState)}")
    lines.append(f"    balance DefaultDisplayName = {_get(lambda o=io: o.BalanceDefinitionState.BalanceDefinition.DefaultDisplayName)}")
    for prop in ("StatusMenuMapInfoBoxHeader", "StatusMenuMapInfoBoxDescription", "ObjectFlags", "HUDIconDefinition",
                 "CompassIcon", "UsedByPlayerMessage", "UseText", "TargetName"):
        lines.append(f"    def.{prop} = {_get(lambda o=io, p=prop: getattr(o.InteractiveObjectDefinition, p))}")
    for prop in ("TargetName", "DisplayName", "CompassIcon", "UseText"):
        lines.append(f"    io.{prop} = {_get(lambda o=io, p=prop: getattr(o, p))}")

with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"[probe_names] {n} pawns -> {OUT}")
