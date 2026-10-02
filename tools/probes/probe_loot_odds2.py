# Dev probe (in game), read-only, instant: the loot weights probe_loot_odds.py couldn't read as numbers (notes.md
# "Loot odds"). Only properties are read; functions are listed, never called.
#  1) GD_Balance.Weighting.GearDrops_CommonWeightModifier (common gear's weight: Weight_1_Common_RareMod's multiplier) -
#     the attribute, its context / value resolvers (their own properties), where its value may live (the game info's
#     designer-attribute-ish fields), and Weight_1_Common_RareMod's formula in full;
#  2) the other attributes a weight points to: the item of the day's Att_IOTD_Weighting_* (a constant resolver: its
#     value), GD_Itempools.DropWeights.DropODDS_* (health, ammo: their resolvers' settings);
#  3) game stage gating: a pool's every field (empty ones too: the names), a BalancedItems entry's every field, and a
#     legendary / a common weapon balance's manufacturers' grades (GameStageRequirement?).
# Writes tools/probes/probe_loot_odds2.txt (appends, a section at a time)
#   py exec(open(r"<repo>\tools\probes\probe_loot_odds2.py").read())
import re
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_loot_odds2.txt"  # the repo, through the mod's junction
lines: list[str] = []


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, (str, bytes, int, float, bool)):
        name = getattr(value, "name", None)  # game enums are int-based: show their name
        if name:
            return str(name)
        return f"{value:.6g}" if isinstance(value, float) else repr(value)
    if depth > 4:
        return f"<{type(value).__name__}>"
    if type(value).__name__ == "WrappedArray":
        items = [_brief(v, depth + 1) for v in list(value)[:12]]
        return "[" + ", ".join(items) + (f", ... ({len(value)} total)" if len(value) > 12 else "") + "]"
    if hasattr(value, "_type"):  # WrappedStruct
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    return f"<{type(value).__name__}: {str(value)[:80]}>"


EMPTY = ("None", "0", "False", "''", "[]", "'None'")
SKIP = {"HashNext", "HashOuterNext", "StateFrame", "LinkerIndex", "ObjectInternalInteger", "NetIndex", "ObjectFlags"}


def _fields(obj, indent: str, stop=("Object",), keep_empty: bool = False, width: int = 2000) -> None:  # noqa: ANN001
    """Every property of obj (the non-empty ones, or all of them), its class and superclasses up to `stop`."""
    if obj is None or isinstance(obj, str):
        lines.append(f"{indent}{obj!r}")
        return
    c, seen = obj.Class, set()
    while c is not None and c.Name not in stop:
        for f in c._fields():
            kind = f.Class.Name
            if f.Name in seen or f.Name in SKIP or not kind.endswith("Property") or kind == "DelegateProperty" or "VfTable" in f.Name:
                continue
            seen.add(f.Name)
            text = _brief(_try(lambda f=f: obj._get_field(f)))
            if keep_empty or text not in EMPTY:
                lines.append(f"{indent}{c.Name}.{f.Name} ({kind.replace('Property', '')}) = {text[:width]}")
        c = c.SuperField


def _object(cls: str, path: str):  # noqa: ANN202
    return _try(lambda: unrealsdk.find_object(cls, path), None)


def _resolvers(attr, indent: str) -> None:  # noqa: ANN001
    """An attribute's context / value resolvers: each one's own properties (where its value comes from)."""
    for chain in ("ContextResolverChain", "ValueResolverChain"):
        for r in _try(lambda c=chain: list(getattr(attr, c)), []) or []:
            lines.append(f"{indent}{chain}: {_brief(r)}")
            _fields(r, indent + "   ", stop=("Object",), keep_empty=True)


def _signatures(cls_name: str, indent: str) -> None:
    cls = _try(lambda: unrealsdk.find_class(cls_name), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"{indent}{cls_name}: not found")
        return
    for f in cls._fields():
        if f.Class.Name == "Function":
            params = [f"{p.Class.Name.replace('Property', '')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
            lines.append(f"{indent}{cls_name}.{f.Name}({', '.join(params)})")


pc = get_pc()
world = ENGINE.GetCurrentWorldInfo()
lines.append("#" * 70)
lines.append(f"# {time.strftime('%H:%M:%S')}  map={_try(lambda: world.GetStreamingPersistentMapName())}  "
             f"player level={_try(lambda: pc.PlayerReplicationInfo.ExpLevel)}")
_flush()

# 1) common gear's weight modifier
lines.append("== 1) GearDrops_CommonWeightModifier")
modifier = _object("DesignerAttributeDefinition", "GD_Balance.Weighting.GearDrops_CommonWeightModifier") \
    or _object("AttributeDefinition", "GD_Balance.Weighting.GearDrops_CommonWeightModifier")
lines.append(f"   {_brief(modifier)}")
if modifier is not None and not isinstance(modifier, str):
    _fields(modifier, "   ", keep_empty=True)
    _resolvers(modifier, "   ")
rare_mod = _object("AttributeInitializationDefinition", "GD_Balance.Weighting.Weight_1_Common_RareMod")
lines.append(f"-- {_brief(rare_mod)} (its formula in full)")
_fields(rare_mod, "   ", stop=("Object",), keep_empty=True, width=4000)
# every other DesignerAttributeDefinition in that package: their base values (siblings of the modifier)
for d in unrealsdk.find_all("DesignerAttributeDefinition", exact=False):
    path = _try(d._path_name, "")
    if path.startswith("GD_Balance.Weighting.") and not d.Name.startswith("Default__"):
        lines.append(f"   sibling {path}: BaseValue={_brief(_try(lambda d=d: d.BaseValue))} Scope={_brief(_try(lambda d=d: d.Scope))}")
# where a global designer attribute's value may live: the game info's / GRI's fields that look like it
game = _try(lambda: world.Game, None)
for label, obj in (("WorldInfo.Game", game), ("GRI", _try(lambda: world.GRI, None))):
    lines.append(f"-- {label} = {_brief(obj)}: fields matching designer / attribute / modifier / weight / drop / loot")
    if obj is None or isinstance(obj, str):
        continue
    pattern = re.compile(r"(?i)designer|attribute|modifier|weight|drop|loot|playthrough|rarity")
    c, seen = obj.Class, set()
    while c is not None and c.Name not in ("Actor", "Object"):
        for f in c._fields():
            if f.Name in seen or not f.Class.Name.endswith("Property") or not pattern.search(f.Name):
                continue
            seen.add(f.Name)
            lines.append(f"   {c.Name}.{f.Name} = {_brief(_try(lambda f=f: obj._get_field(f)))[:1500]}")
        c = c.SuperField
_flush()

# 2) the other attributes a weight points to
lines.append("== 2) Att_IOTD_Weighting_* and DropODDS_*")
for a in unrealsdk.find_all("AttributeDefinition", exact=False):
    path = _try(a._path_name, "")
    if a.Name.startswith("Default__") or not ("IOTD_Weighting" in path or path.startswith("GD_Itempools.DropWeights.")):
        continue
    lines.append(f"-- {_brief(a)}")
    _fields(a, "   ", stop=("Object",))
    _resolvers(a, "   ")
    _flush()

# 3) game stage gating
lines.append("== 3) game stage gating")
pool = _object("ItemPoolDefinition", "GD_Itempools.WeaponPools.Pool_Weapons_Pistols_06_Legendary") \
    or _object("ItemPoolDefinition", "GD_Gladiolus_Itempools.WeaponPools.Pool_Weapons_Pistols_07_LegendaryPlusPearl")
lines.append(f"-- a legendary pool {_brief(pool)}: every field (empty ones too)")
_fields(pool, "   ", stop=("Object",), keep_empty=True)
entries = _try(lambda: list(pool.BalancedItems), []) if pool is not None and not isinstance(pool, str) else []
if entries:
    lines.append(f"   its first entry, every field: {_brief(entries[0])}")
    balance = _try(lambda: entries[0].InvBalanceDefinition, None)
    lines.append(f"-- its first entry's balance {_brief(balance)}: every non-empty field")
    _fields(balance, "   ", stop=("Object",), width=3000)
common = _object("ItemPoolDefinition", "GD_Itempools.WeaponPools.Pool_Weapons_Pistols_01_Common")
centries = _try(lambda: list(common.BalancedItems), []) if common is not None and not isinstance(common, str) else []
if centries:
    cbal = _try(lambda: centries[0].InvBalanceDefinition, None)
    lines.append(f"-- a common pistol balance {_brief(cbal)}: every non-empty field")
    _fields(cbal, "   ", stop=("Object",), width=3000)
_flush()

lines.append("== signatures (not called)")
for cls_name in ("DesignerAttributeDefinition", "ConstantAttributeValueResolver", "AmmoDropWeightAttributeValueResolver",
                 "ObjectPropertyAttributeValueResolver", "GameInfoAttributeContextResolver", "DesignerAttributeContextResolver"):
    _signatures(cls_name, "   ")
_flush()
print(f"[probe_loot_odds2] -> {OUT}")
