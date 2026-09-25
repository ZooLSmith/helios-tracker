# Dev probe (in game), read-only, instant: the two loot values probe_loot_odds2.py left (notes.md "Loot odds").
# Only properties are read; nothing is called.
#  1) GD_Itempools.Scheduling.Gamestage_* (a pool's MinGameStageRequirement: Pool_Weapons_Pistols_06_Legendary needs
#     Gamestage_07) - each one's resolvers and their own fields: the stage it stands for;
#  2) WorldInfo.Game.DesignerAttributes (the host's live designer attributes: GearDrops_CommonWeightModifier's
#     value is one of them) - every field of each (empty ones too: what links one to its definition, its Value).
# Writes tools/probe_loot_odds3.txt (appends, a section at a time)
#   py exec(open(r"<repo>\tools\probe_loot_odds3.py").read())
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_loot_odds3.txt"  # the repo, through the mod's junction
lines: list[str] = []
SKIP = {"HashNext", "HashOuterNext", "StateFrame", "LinkerIndex", "ObjectInternalInteger", "NetIndex", "ObjectFlags", "Linker"}


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
        name = getattr(value, "name", None)
        if name:
            return str(name)
        return f"{value:.6g}" if isinstance(value, float) else repr(value)
    if depth > 4:
        return f"<{type(value).__name__}>"
    if type(value).__name__ == "WrappedArray":
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:12]) + (f", ... ({len(value)} total)" if len(value) > 12 else "") + "]"
    if hasattr(value, "_type"):
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    return f"<{type(value).__name__}: {str(value)[:80]}>"


def _fields(obj, indent: str) -> None:  # noqa: ANN001
    """Every property of obj (empty ones too), its class and superclasses."""
    if obj is None or isinstance(obj, str):
        lines.append(f"{indent}{obj!r}")
        return
    c, seen = obj.Class, set()
    while c is not None and c.Name != "Object":
        for f in c._fields():
            kind = f.Class.Name
            if f.Name in seen or f.Name in SKIP or not kind.endswith("Property") or kind == "DelegateProperty" or "VfTable" in f.Name:
                continue
            seen.add(f.Name)
            lines.append(f"{indent}{c.Name}.{f.Name} ({kind.replace('Property', '')}) = {_brief(_try(lambda f=f: obj._get_field(f)))[:1500]}")
        c = c.SuperField


world = ENGINE.GetCurrentWorldInfo()
lines.append("#" * 70)
lines.append(f"# {time.strftime('%H:%M:%S')}  map={_try(lambda: world.GetStreamingPersistentMapName())}")

lines.append("== 1) GD_Itempools.Scheduling.Gamestage_*")
stages = [a for a in unrealsdk.find_all("AttributeDefinition", exact=False)
          if not a.Name.startswith("Default__") and _try(a._path_name, "").startswith("GD_Itempools.Scheduling.")]
lines.append(f"   {len(stages)} of them")
for a in sorted(stages, key=lambda a: str(a.Name)):
    lines.append(f"-- {_brief(a)}")
    for r in _try(lambda a=a: list(a.ValueResolverChain), []) or []:
        lines.append(f"   value resolver {_brief(r)}")
        _fields(r, "      ")
    _flush()

lines.append("== 2) WorldInfo.Game.DesignerAttributes (the host's)")
game = _try(lambda: world.Game, None)
lines.append(f"   Game = {_brief(game)}  (None: a co-op client)")
if game is not None and not isinstance(game, str):
    for inst in _try(lambda: list(game.DesignerAttributes), []) or []:
        lines.append(f"-- {_brief(inst)}")
        _fields(inst, "   ")
        _flush()
_flush()
print(f"[probe_loot_odds3] {len(stages)} stage attributes -> {OUT}")
