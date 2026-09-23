# Dev probe (in game), instant: what can be read of each player's inventory and skills - for the
# local player, and (in co-op) for the others, as host or as client.
# Run it solo first, then in co-op (ideally once as host and once as client).
# Writes E:\Projects\python\bl2-helios-tracker\tools\probe_inventory.txt (appends)
#   py exec(open(r"E:\Projects\python\bl2-helios-tracker\tools\probe_inventory.py").read())
from enum import Enum
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(r"E:\Projects\python\bl2-helios-tracker\tools\probe_inventory.txt")
MAX_BACKPACK = 8  # items detailed per backpack (the rest only counted)
NET_MODES = {0: "standalone", 1: "dedicated server", 2: "listen server (host)", 3: "client"}

lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _name(obj) -> str:  # noqa: ANN001
    if obj is None:
        return "None"
    return _try(lambda: str(obj.Name)) if hasattr(obj, "Name") else str(obj)


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    """Compact struct / object / array rendering (objects by name, structs field by field)."""
    if value is None:
        return "None"
    if isinstance(value, Enum):  # first: flag enums iterate over themselves (endless recursion)
        return str(value.name)
    if isinstance(value, (str, int, bool)):
        return str(value)
    if depth > 4:
        return "..."
    if hasattr(value, "_type"):  # WrappedStruct
        if depth > 2:
            return "{...}"
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if not f.Class.Name.endswith("Property"):
                continue
            v = _try(lambda f=f: value._get_field(f))
            parts.append(f"{f.Name}={_brief(v, depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):  # UObject
        return _name(value)
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):  # WrappedArray
        items = [_brief(v, depth + 1) for v in list(value)[:6]]
        more = f", ... ({len(value)} total)" if len(value) > 6 else ""
        return "[" + ", ".join(items) + more + "]"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _call_str(fn) -> str:  # noqa: ANN001
    for args in ((), ("",)):
        try:
            r = fn(*args)
        except TypeError:
            continue
        except Exception as ex:  # noqa: BLE001
            return f"<{type(ex).__name__}>"
        if isinstance(r, tuple):
            r = next((v for v in r if isinstance(v, str) and v), "")
        return str(r)
    return "<no str>"


def _item(inv, indent: str) -> None:  # noqa: ANN001
    """One weapon / item: identity, stats-ish fields, parts."""
    if inv is None:
        lines.append(f"{indent}None")
        return
    name = _call_str(inv.GetShortHumanReadableName) if hasattr(inv, "GetShortHumanReadableName") else "?"
    lines.append(
        f"{indent}{inv.Class.Name} '{name}' GeneratedItemName={_try(lambda: inv.GeneratedItemName, '-')!r}"
        f" rarity={_try(lambda: inv.RarityLevel)} level={_try(lambda: inv.ExpLevel)}"
        f" value={_try(lambda: inv.MonetaryValue)} location={_try(lambda: inv.ItemLocation)}"
        f" slot={_try(lambda: inv.QuickSelectSlot, '-')} mark={_try(lambda: inv.Mark)}",
    )
    lines.append(f"{indent}  DefinitionData = {_brief(_try(lambda: inv.DefinitionData))}")
    for fn in ("GetHumanReadableName", "GetInventoryCardString"):
        if hasattr(inv, fn):
            lines.append(f"{indent}  {fn}() = {_call_str(getattr(inv, fn))[:300]!r}")
    for prop in ("ItemCardModifierStats", "UIStatModifiers", "ReplicatedWeaponCardModifierValues",
                 "ReplicatedItemCardModifierValues"):
        v = _try(lambda p=prop: getattr(inv, p), None)
        if v is not None:
            lines.append(f"{indent}  {prop} = {_brief(v)[:600]}")
    if inv.Class.Name.startswith("WillowWeapon") or hasattr(inv, "GetMultiProjectileCount"):
        for stat in ("InstantHitDamage", "FireRate", "ClipSize", "ReloadTime", "Spread", "AimError"):
            v = _try(lambda s=stat: getattr(inv, s), None)
            if v is not None:
                lines.append(f"{indent}  {stat} = {_brief(v)[:200]}")


def _chain(first, label: str, indent: str) -> None:  # noqa: ANN001
    lines.append(f"{indent}{label}:")
    inv, n = first, 0
    while inv is not None and n < 32:
        _item(inv, indent + "  ")
        inv = _try(lambda i=inv: i.Inventory, None)
        n += 1


def _inventory(pawn, indent: str) -> None:  # noqa: ANN001
    lines.append(f"{indent}pawn.Weapon = {_name(_try(lambda: pawn.Weapon, None))}")
    lines.append(f"{indent}pawn.EquippedItems = {_brief(_try(lambda: pawn.EquippedItems))}")
    lines.append(f"{indent}pawn.HolsteredWeaponSlots = {_brief(_try(lambda: pawn.HolsteredWeaponSlots))}")
    inv_mgr = _try(lambda: pawn.InvManager, None)
    lines.append(f"{indent}InvManager = {_try(lambda: inv_mgr._path_name(), None)}")
    if inv_mgr is None:
        return
    _chain(_try(lambda: inv_mgr.InventoryChain, None), "InventoryChain (equipped weapons)", indent)
    _chain(_try(lambda: inv_mgr.ItemChain, None), "ItemChain (equipped gear)", indent)
    backpack = _try(lambda: list(inv_mgr.Backpack), [])
    lines.append(f"{indent}Backpack: {len(backpack) if isinstance(backpack, list) else backpack} entries,"
                 f" BackpackInventoryCount={_try(lambda: inv_mgr.BackpackInventoryCount)}")
    for inv in backpack[:MAX_BACKPACK] if isinstance(backpack, list) else []:
        _item(inv, indent + "  ")


def _skills(pc, indent: str) -> None:  # noqa: ANN001
    tree = _try(lambda: pc.PlayerSkillTree, None)
    lines.append(f"{indent}PlayerSkillTree = {_try(lambda: tree._path_name(), None)}")
    if tree is None:
        return
    lines.append(f"{indent}  PlayerClass = {_name(_try(lambda: pc.PlayerClass, None))}")
    branches = _try(lambda: list(tree.Branches), [])
    lines.append(f"{indent}  Branches ({len(branches)}): {_brief(branches[0])[:800] if branches else '-'}")
    tiers = _try(lambda: list(tree.Tiers), [])
    lines.append(f"{indent}  Tiers ({len(tiers)}): first {_brief(tiers[0])[:400] if tiers else '-'}")
    skills = _try(lambda: list(tree.Skills), [])
    lines.append(f"{indent}  Skills ({len(skills)}): first {_brief(skills[0])[:600] if skills else '-'}")
    for s in skills:
        fields = {f.Name: _try(lambda f=f: s._get_field(f)) for f in _try(lambda: list(s._type._fields()), [])
                  if f.Class.Name.endswith("Property")}
        definition = next((v for v in fields.values() if hasattr(v, "Class") and v.Class.Name == "SkillDefinition"), None)
        nums = {k: v for k, v in fields.items() if isinstance(v, int)}
        if definition is not None:
            lines.append(
                f"{indent}    {_name(definition)} '{_try(lambda d=definition: d.SkillName)}'"
                f" max={_try(lambda d=definition: d.MaxGrade)} {nums}",
            )
    lines.append(f"{indent}  GetSkillPointsSpentInTree() = {_try(tree.GetSkillPointsSpentInTree)}")


wi = ENGINE.GetCurrentWorldInfo()
me = get_pc()
lines.append("#" * 70)
lines.append(f"map {_try(wi.GetStreamingPersistentMapName)}, NetMode {NET_MODES.get(wi.NetMode, wi.NetMode)},"
             f" local PC {me._path_name()}")

lines.append("== PlayerReplicationInfos (replicated to everyone)")
for pri in unrealsdk.find_all("WillowPlayerReplicationInfo", exact=False):
    if pri.Name.startswith("Default__"):
        continue
    lines.append(f"  {pri.PlayerName!r} ({pri._path_name()}) local={pri == me.PlayerReplicationInfo}")
    for prop in ("ExpLevel", "CharacterNameIdDef", "ClassModNamePart", "GeneralSkillPoints", "SpecialistSkillPoints",
                 "NumTrackedSkillSlotsInUse", "TrackedSkills", "StandInGear", "Currency"):
        lines.append(f"    {prop} = {_brief(_try(lambda p=prop, r=pri: getattr(r, p)))[:1500]}")

lines.append("== PlayerControllers in memory (host: everyone's; client: only our own)")
for pc in unrealsdk.find_all("WillowPlayerController", exact=False):
    if pc.Name.startswith("Default__"):
        continue
    pri = _try(lambda p=pc: p.PlayerReplicationInfo, None)
    lines.append(f"  PC {pc._path_name()} player={_try(lambda: pri.PlayerName, None)!r} local={pc == me}")
    lines.append(f"    level={_try(lambda: pri.ExpLevel)} ExpPool={_try(lambda p=pc: p.ExpPool.Data.CurrentValue)}"
                 f" NextLevelAt={_try(lambda: pri.ExpPointsNextLevelAt)}"
                 f" RequiredFor(level)={_try(lambda p=pc: p.GetExpPointsRequiredForLevel(pri.ExpLevel))}")
    _skills(pc, "    ")

lines.append("== Player pawns")
pawn = wi.PawnList
for _ in range(1000):
    if pawn is None:
        break
    if pawn.Class.Name.startswith("WillowPlayerPawn") or "PlayerPawn" in pawn.Class.Name:
        pri = _try(lambda p=pawn: p.PlayerReplicationInfo, None)
        lines.append(f"  pawn {pawn._path_name()} player={_try(lambda: pri.PlayerName, None)!r}"
                     f" local={pawn == me.Pawn or pawn == _try(lambda: me.MyWillowPawn, None)}")
        _inventory(pawn, "    ")
    pawn = _try(lambda p=pawn: p.NextPawn, None)

with OUT.open("a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(f"[probe_inventory] {len(lines)} lines -> {OUT}")
