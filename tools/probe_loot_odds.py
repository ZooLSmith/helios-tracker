# Dev probe (in game), read-only, instant: what a container's loot chances are made of - for "Can contain" with
# percentages. Only properties are read; functions are listed (signatures), never called.
# For the closest few lootable objects (a red chest first if one's near, then the closest others, then the closest
# vending machine): their loot configurations (Loot / the balance's DefaultLoot / DefaultIncludedLootLists: each
# one's Weight, its ItemAttachments), then every pool they reach, a few levels deep: its BalancedItems (each entry's
# item or sub-pool, Probability, bDropOnDeath) and its own fields; then every InitializationDefinition /
# BaseValueAttribute a Probability / Weight points to, once each - whether they hold plain numbers or need the game.
# Stand near a chest or two (Sanctuary: its red chest; any area with lockers / ammo crates).
# Writes tools/probe_loot_odds.txt (appends, a section at a time)
#   py exec(open(r"<repo>\tools\probe_loot_odds.py").read())
import math
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probe_loot_odds.txt"  # the repo, through the mod's junction
MAX_OBJECTS = 4  # containers looked at (a chest, the closest others)
MAX_DEPTH = 4  # pool nesting followed
MAX_POOLS = 80  # pools dumped in all (a chest's tree reaches many)
MAX_ENTRIES = 40  # BalancedItems per pool written
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
        return f"{value:.4g}" if isinstance(value, float) else repr(value)
    if depth > 3:
        return f"<{type(value).__name__}>"
    if type(value).__name__ == "WrappedArray":
        items = [_brief(v, depth + 1) for v in list(value)[:8]]
        return "[" + ", ".join(items) + (f", ... ({len(value)} total)" if len(value) > 8 else "") + "]"
    if hasattr(value, "_type"):  # WrappedStruct
        parts = []
        for f in _try(lambda: list(value._type._fields()), []):
            if f.Class.Name.endswith("Property"):
                parts.append(f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}")
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{_try(value._path_name)}'"
    return f"<{type(value).__name__}: {str(value)[:80]}>"


EMPTY = ("None", "0", "0", "False", "''", "[]", "'None'")


def _fields(obj, indent: str, stop=("Object",)) -> None:  # noqa: ANN001
    """Every non-empty property of obj, its class and superclasses up to `stop`."""
    c, seen = obj.Class, set()
    while c is not None and c.Name not in stop:
        for f in c._fields():
            kind = f.Class.Name
            if f.Name in seen or not kind.endswith("Property") or kind == "DelegateProperty" or "VfTable" in f.Name:
                continue
            seen.add(f.Name)
            text = _brief(_try(lambda f=f: obj._get_field(f)))
            if text not in EMPTY:
                lines.append(f"{indent}{c.Name}.{f.Name} = {text[:900]}")
        c = c.SuperField


def _signatures(cls_name: str, indent: str) -> None:
    cls = _try(lambda: unrealsdk.find_class(cls_name), None)
    if cls is None or isinstance(cls, str):
        lines.append(f"{indent}{cls_name}: not found")
        return
    for f in cls._fields():
        if f.Class.Name == "Function":
            params = [f"{p.Class.Name.replace('Property', '')} {p.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
            lines.append(f"{indent}{cls_name}.{f.Name}({', '.join(params)})")


pools_todo: list[tuple[object, int]] = []  # (pool, depth)
pools_seen: set[str] = set()
inits_seen: dict[str, object] = {}  # path -> InitializationDefinition / BaseValueAttribute met in a Probability / Weight


def _note_value(value) -> None:  # noqa: ANN001
    """An AttributeInitializationData (a Probability, a Weight): the objects it points to, for the last section."""
    for name in ("InitializationDefinition", "BaseValueAttribute"):
        obj = _try(lambda n=name: getattr(value, n), None)
        if obj is not None and not isinstance(obj, str):
            inits_seen.setdefault(_try(obj._path_name, str(obj)), obj)


def _note_pool(pool, depth: int) -> None:  # noqa: ANN001
    if pool is None or isinstance(pool, str):
        return
    path = _try(pool._path_name, str(pool))
    if path not in pools_seen:
        pools_seen.add(path)
        pools_todo.append((pool, depth))


def _configs(configs, indent: str) -> None:  # noqa: ANN001
    """Loot configurations (a Loot array / DefaultLoot / a loot list's LootData): each one's weight and attachments."""
    for i, cfg in enumerate(_try(lambda: list(configs), []) or []):
        weight = _try(lambda c=cfg: c.Weight, None)
        lines.append(f"{indent}[{i}] {_try(lambda c=cfg: c.ConfigurationName, '?')}  Weight={_brief(weight)}")
        if weight is not None:
            _note_value(weight)
        for j, att in enumerate(_try(lambda c=cfg: list(c.ItemAttachments), []) or []):
            lines.append(f"{indent}    attach[{j}] {_brief(att)[:600]}")
            _note_pool(_try(lambda a=att: a.ItemPool, None), 0)
            for name in ("PoolProbability", "Probability"):  # (whichever the struct has)
                value = _try(lambda a=att, n=name: getattr(a, n), None)
                if value is not None and not isinstance(value, str):
                    _note_value(value)


pc = get_pc()
here = pc.Pawn.Location
world = ENGINE.GetCurrentWorldInfo()
lines.append("#" * 70)
lines.append(f"# {time.strftime('%H:%M:%S')}  map={_try(lambda: world.GetStreamingPersistentMapName())}  "
             f"player level={_try(lambda: pc.PlayerReplicationInfo.ExpLevel)}")
_flush()

# the objects: lootable (their own Loot, or their balance's), not opened, the closest; a red chest first
candidates = []
for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
    if io.Name.startswith("Default__") or io.Outer is None or io.Outer.Class.Name != "Level":
        continue
    balance = _try(lambda o=io: o.BalanceDefinitionState.BalanceDefinition, None)
    own = _try(lambda o=io: len(o.Loot), 0) or 0
    lists = [str(_try(lambda l=l: l.Name, "")) for l in (_try(lambda b=balance: list(b.DefaultIncludedLootLists), []) or [])] \
        if balance is not None and not isinstance(balance, str) else []
    shared = (_try(lambda b=balance: len(b.DefaultLoot), 0) or 0) if balance is not None and not isinstance(balance, str) else 0
    vending = "Vending" in io.Class.Name
    if not (own or shared or lists or vending):
        continue
    dist = _try(lambda o=io: math.dist((o.Location.X, o.Location.Y, o.Location.Z), (here.X, here.Y, here.Z)), 1e12)
    candidates.append((dist, io, balance, lists, vending))
candidates.sort(key=lambda c: c[0])
chest = [c for c in candidates if any("epic" in n.lower() for n in c[3]) and not c[4]][:1]
others = [c for c in candidates if not c[4] and c not in chest][: MAX_OBJECTS - len(chest)]
machine = [c for c in candidates if c[4]][:1]
lines.append(f"== {len(candidates)} lootable objects in the level; looking at {len(chest) + len(others) + len(machine)}")
for dist, io, balance, lists, vending in chest + others + machine:
    lines.append(f"-- {io.Class.Name} {io.Name}  {dist / 100:.0f} m  def={_brief(_try(lambda o=io: o.InteractiveObjectDefinition, None))}")
    lines.append(f"   balance={_brief(balance)}  anim state={_try(lambda o=io: int(o.SimpleAnimState), '?')}  "
                 f"usable={_brief(_try(lambda o=io: tuple(o.bCanBeUsed), None))}  GameStage={_try(lambda o=io: o.GameStage, '?')}")
    lines.append("   Loot (its own):")
    _configs(_try(lambda o=io: o.Loot, []), "     ")
    if balance is not None and not isinstance(balance, str):
        lines.append("   balance.DefaultLoot:")
        _configs(_try(lambda: balance.DefaultLoot, []), "     ")
        for ll in _try(lambda: list(balance.DefaultIncludedLootLists), []) or []:
            lines.append(f"   balance list {_brief(ll)}:")
            _configs(_try(lambda l=ll: l.LootData, []), "     ")
    _flush()

# the pools, breadth first: each one's entries (item or sub-pool, Probability) and its own fields
lines.append(f"== pools (up to {MAX_POOLS}, {MAX_DEPTH} levels deep)")
done = 0
while pools_todo and done < MAX_POOLS:
    pool, depth = pools_todo.pop(0)
    done += 1
    lines.append(f"-- [{depth}] {_brief(pool)}")
    entries = _try(lambda p=pool: list(p.BalancedItems), []) or []
    lines.append(f"   BalancedItems: {len(entries)}")
    for k, entry in enumerate(entries[:MAX_ENTRIES]):
        sub = _try(lambda e=entry: e.ItmPoolDefinition, None)
        item = _try(lambda e=entry: e.InvBalanceDefinition, None)
        prob = _try(lambda e=entry: e.Probability, None)
        lines.append(f"     [{k}] pool={_brief(sub)} item={_brief(item)} drop={_brief(_try(lambda e=entry: e.bDropOnDeath, None))}")
        lines.append(f"          Probability={_brief(prob)}")
        if prob is not None and not isinstance(prob, str):
            _note_value(prob)
        if depth + 1 < MAX_DEPTH:
            _note_pool(sub, depth + 1)
    _fields(pool, "   ", stop=("GBXDefinition", "Object"))
    if done % 10 == 0:
        _flush()
lines.append(f"   ({len(pools_todo)} pools left unread)")
_flush()

# what the chances point to: plain numbers, or something only the game evaluates
lines.append(f"== {len(inits_seen)} InitializationDefinitions / attributes the chances point to")
for path, obj in sorted(inits_seen.items()):
    lines.append(f"-- {_brief(obj)}")
    _fields(obj, "   ", stop=("Object",))
_flush()

lines.append("== signatures (not called)")
for cls_name in ("ItemPoolDefinition", "AttributeInitializationDefinition", "AttributeDefinition", "ItemPool"):
    _signatures(cls_name, "   ")
_flush()
print(f"[probe_loot_odds] {len(chest) + len(others) + len(machine)} objects, {done} pools, {len(inits_seen)} initializations -> {OUT}")
