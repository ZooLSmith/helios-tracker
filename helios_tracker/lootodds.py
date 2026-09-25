"""
Loot odds: a container's chances, from its loot data - for the click panel's "Can contain" (the `odds` of an object
record, the pools in the objects payload's `pools`).

Game thread only (the collector builds them with an object's record: static data, cached). Everything is read as
properties, nothing is called (tools/probe_loot_odds*.txt, .agent/notes.md "Loot odds"):
- a container picks ONE loot configuration by weight (each its `Weight`), then rolls each of its ItemAttachments'
  ItemPool; a pool picks ONE of its BalancedItems by weight (`Probability`): an item balance or a sub-pool;
- a weight is an AttributeInitializationData: its InitializationDefinition's value, else its BaseValueAttribute's,
  else BaseValueConstant - times BaseValueScaleConstant. An InitializationDefinition: its ValueFormula,
  Multiplier x Level^Power + Offset. An attribute: its value resolver - a ConstantAttributeValueResolver's
  ConstantValue; an AmmoDropWeightAttributeValueResolver's two cases (the player's health / ammo: above its
  ResourceThreshold AboveThresholdWeight, below between Min- and MaxBelowThresholdWeight - "if low on health");
  a designer attribute: the host's live value (WorldInfo.Game.DesignerAttributes: each InstancedDesignerAttribute's
  Value, by its DesignerAttributeDefinitionPathName - GearDrops_CommonWeightModifier read 0.625, its base 1:
  tools/probe_loot_odds3.txt), else (a co-op client) its BaseValue;
- anything else (conditional resolvers, random variance, a runtime-built weight): unknown - its entry has no chance
  (None) and the others' percentages leave it out.
These rules are inferred from the data, not checked against the game's own draws: the page marks them "~".
"""

from typing import Any

from .util import try_

MAX_DEPTH = 6  # pool nesting followed
MAX_ENTRIES = 40  # a pool's entries sent
CONDITIONS = {"Health": "health"}  # an AmmoDropWeight resolver's resource -> the page's condition ("if low on ...")


class Val:
    """A weight: its usual value `n`, and - when it depends on the player being low on something (`cond`: "health",
    "ammo") - its range then `lo` (min, max)."""

    __slots__ = ("cond", "lo", "n")

    def __init__(self, n: float, lo: tuple[float, float] | None = None, cond: str | None = None) -> None:
        self.n, self.lo, self.cond = n, lo, cond

    def times(self, k: float) -> "Val":
        return Val(self.n * k, (self.lo[0] * k, self.lo[1] * k) if self.lo else None, self.cond)


def _mul(a: Val, b: Val) -> Val:
    lo = None
    if a.lo or b.lo:  # (one side depends on a condition: the other taken as usual)
        alo, blo = a.lo or (a.n, a.n), b.lo or (b.n, b.n)
        lo = (alo[0] * blo[0], alo[1] * blo[1])
    return Val(a.n * b.n, lo, a.cond or b.cond)


def _add(a: Val, b: Val) -> Val:
    lo = None
    if a.lo or b.lo:
        alo, blo = a.lo or (a.n, a.n), b.lo or (b.n, b.n)
        lo = (alo[0] + blo[0], alo[1] + blo[1])
    return Val(a.n + b.n, lo, a.cond or b.cond)


_inits: dict[int, Val | None] = {}  # InitializationDefinition / attribute address -> its value (static data)
_designer: dict[str, float] = {}  # the host's live designer attributes: definition path -> value (refresh())
version = 0  # bumped when the live values changed: every odds worked out again (the collector sends them anew)


def refresh(world_info: Any) -> bool:
    """The host's live designer attributes read again (a co-op client has none: the base values); True if they
    changed - then every cached value, container and pool is forgotten (worked out again with the new ones)."""
    global version  # noqa: PLW0603
    game = try_(lambda: world_info.Game)
    live = {}
    for inst in (try_(lambda: list(game.DesignerAttributes), []) or []) if game is not None else []:
        path = str(try_(lambda i=inst: i.DesignerAttributeDefinitionPathName, "") or "")
        value = try_(lambda i=inst: float(i.Value))
        if path and value is not None:
            live[path] = round(value, 6)
    if live == _designer:
        return False
    _designer.clear()
    _designer.update(live)
    _inits.clear()
    _containers.clear()
    POOLS.clear()
    version += 1
    return True


def data_value(data: Any, depth: int = 0) -> Val | None:
    """An AttributeInitializationData's value, or None (unknown)."""
    if data is None or depth > 8:
        return None
    scale = try_(lambda: float(data.BaseValueScaleConstant), 1.0)
    init = try_(lambda: data.InitializationDefinition)
    attr = try_(lambda: data.BaseValueAttribute)
    if init is not None:
        base = _init_value(init, depth + 1)
    elif attr is not None:
        base = attr_value(attr, depth + 1)
    else:
        const = try_(lambda: float(data.BaseValueConstant))
        base = Val(const) if const is not None else None
    return base.times(scale) if base is not None else None


def _init_value(init: Any, depth: int) -> Val | None:
    key = init._get_address()
    if key in _inits:
        return _inits[key]
    _inits[key] = None  # (a cycle: unknown)
    value = None
    formula = try_(lambda: init.ValueFormula)
    enabled = lambda s: bool(try_(lambda: s.bEnabled, False))  # noqa: E731
    if (formula is not None and enabled(formula) and not enabled(try_(lambda: init.ConditionalInitialization))
            and not enabled(try_(lambda: init.RandomVariance))):
        terms = [data_value(try_(lambda n=n: getattr(formula, n)), depth) for n in ("Multiplier", "Level", "Power", "Offset")]
        if all(t is not None for t in terms):
            mult, level, power, offset = terms
            if power.lo is None:  # (a power depending on a condition: not seen - unknown)
                raised = level if power.n == 1 else Val(level.n ** power.n, tuple(x ** power.n for x in level.lo) if level.lo else None, level.cond)
                value = _add(_mul(mult, raised), offset)
    _inits[key] = value
    return value


def attr_value(attr: Any, depth: int = 0) -> Val | None:
    """An attribute's value: a constant, a low-on-health / ammo weight, a designer attribute's base - or None."""
    key = attr._get_address()
    if key in _inits:
        return _inits[key]
    _inits[key] = None
    value = None
    if str(attr.Class.Name) == "DesignerAttributeDefinition":
        live = _designer.get(str(try_(attr._path_name, "") or ""))  # the host's live value, else its base
        value = Val(live) if live is not None else data_value(try_(lambda: attr.BaseValue), depth)
    else:
        resolvers = try_(lambda: list(attr.ValueResolverChain), []) or []
        r = resolvers[0] if len(resolvers) == 1 else None
        kind = str(try_(lambda: r.Class.Name, "")) if r is not None else ""
        if kind == "ConstantAttributeValueResolver":
            const = try_(lambda: float(r.ConstantValue))
            value = Val(const) if const is not None else None
        elif kind == "AmmoDropWeightAttributeValueResolver":
            above = data_value(try_(lambda: r.AboveThresholdWeight), depth)
            low_min = data_value(try_(lambda: r.MinBelowThresholdWeight), depth)
            low_max = data_value(try_(lambda: r.MaxBelowThresholdWeight), depth)
            if above is not None and low_min is not None and low_max is not None:
                resource = str(try_(lambda: r.Resource.Name, "") or "")
                value = Val(above.n, (low_min.n, low_max.n), CONDITIONS.get(resource, "ammo"))
    _inits[key] = value
    return value


def _stage(pool: Any) -> int | None:
    """A pool's minimum game stage (its MinGameStageRequirement attribute's value), or None."""
    attr = try_(lambda: pool.MinGameStageRequirement)
    value = attr_value(attr) if attr is not None else None
    return round(value.n) if value is not None and value.lo is None else None


def _shares(weights: list[Val | None]) -> list[tuple[float | None, tuple[float, float] | None]]:
    """Weights -> each one's chance (0-1) as usual, and - for one depending on a condition - its chance then (min,
    max), the others as usual. Unknown weights: None, left out of the total."""
    total = sum(w.n for w in weights if w is not None)
    out = []
    for w in weights:
        if w is None or total <= 0 and not w.lo:
            out.append((None, None))
            continue
        share = w.n / total if total > 0 else 0.0
        low = None
        if w.lo:  # (only this one low: the others as usual)
            rest = total - w.n
            low = tuple(x / (rest + x) if rest + x > 0 else 0.0 for x in w.lo)
        out.append((share, low))
    return out


def _pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100, 3)


def pool_key(pool: Any) -> str:
    return str(try_(pool._path_name, "") or pool.Name)


def add_pool(pool: Any, pools: dict[str, dict[str, Any]], depth: int = 0) -> str:
    """A pool's entry in `pools` (its name, and each entry: name, chance %, if-low range, condition, its sub-pool's
    key, its minimum stage), with its sub-pools, recursively; its key."""
    key = pool_key(pool)
    if key in pools or depth > MAX_DEPTH:
        return key
    record: dict[str, Any] = {"n": str(pool.Name)}
    pools[key] = record  # (before the sub-pools: a cycle ends here)
    entries = (try_(lambda: list(pool.BalancedItems), []) or [])[:MAX_ENTRIES]
    weights = [data_value(try_(lambda e=e: e.Probability)) for e in entries]
    rows = []
    for entry, w, (share, low) in zip(entries, weights, _shares(weights)):
        sub = try_(lambda e=entry: e.ItmPoolDefinition)
        item = try_(lambda e=entry: e.InvBalanceDefinition)
        target = sub if sub is not None else item
        row: dict[str, Any] = {"n": str(try_(lambda t=target: t.Name, "?"))}
        if share is not None:
            row["p"] = _pct(share)
        if low:
            row["lo"], row["c"] = [_pct(low[0]), _pct(low[1])], w.cond
        if sub is not None:
            row["pool"] = add_pool(sub, pools, depth + 1)
            if (stage := _stage(sub)) is not None and stage > 1:
                row["min"] = stage  # (a rarity pool from that game stage: Pool_..._06_Legendary, Gamestage_07)
        rows.append(row)
    record["e"] = rows
    return key


# Every pool a container's odds reach (static game data, never cleared: a path per key) - the `lootpools` payload
POOLS: dict[str, dict[str, Any]] = {}
_containers: dict[int, list[dict[str, Any]]] = {}  # balance address -> its configurations' odds


def container_odds(io: Any, balance: Any) -> list[dict[str, Any]]:
    """A container's loot configurations with their chances (configs_odds), its pools added to POOLS: from its
    balance (per type, cached) - its default loot and its loot lists' configurations, one set the game picks from (an
    object's own Loot is that set: the golden chest's, tools/probe_loot_odds.txt) - else the object's own Loot."""
    key = try_(lambda: balance._get_address()) if balance is not None else None
    if key is not None and key in _containers:
        return _containers[key]
    configs = list(try_(lambda: list(balance.DefaultLoot), []) or []) if balance is not None else []
    for lst in (try_(lambda: list(balance.DefaultIncludedLootLists), []) or []) if balance is not None else []:
        configs += try_(lambda l=lst: list(l.LootData), []) or []
    if not configs:
        configs = try_(lambda: list(io.Loot), []) or []
        key = None  # (the object's own: not per type)
    odds = configs_odds(configs, POOLS) if configs else []
    if key is not None:
        _containers[key] = odds
    return odds


def configs_odds(configs: Any, pools: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Loot configurations -> each one's chance (%, its if-low range and condition) and its pools ([key, how many]),
    the pools added to `pools`."""
    configs = try_(lambda: list(configs), []) or []
    weights = [data_value(try_(lambda c=c: c.Weight)) for c in configs]
    out = []
    for cfg, w, (share, low) in zip(configs, weights, _shares(weights)):
        counts: dict[str, int] = {}
        for att in try_(lambda c=cfg: list(c.ItemAttachments), []) or []:
            pool = try_(lambda a=att: a.ItemPool)
            if pool is not None:
                key = add_pool(pool, pools)
                counts[key] = counts.get(key, 0) + 1
        row: dict[str, Any] = {"a": [[k, n] for k, n in counts.items()]}
        if share is not None:
            row["p"] = _pct(share)
        if low:
            row["lo"], row["c"] = [_pct(low[0]), _pct(low[1])], w.cond
        out.append(row)
    return out
