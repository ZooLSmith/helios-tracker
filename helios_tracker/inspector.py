"""
Player inspection: equipped gear, backpack and skills of every player, for the page's inspector.

Game thread only (called by the collector every PLAYERS_EVERY). Reads defensively: what's missing
is reported (as a reason code the page translates), not guessed. Stats are sent as raw numbers
([key, value, extra]); the page labels and formats them. Expected availability (to verify with tools/probe_inventory.py):
- inventory: `pawn.InvManager` - our own; on the host probably everyone's, on a client only ours
  (then only the weapon in hand, `pawn.Weapon`, is known for the others);
- skills: `pawn.Controller.PlayerSkillTree` - our own; on the host probably everyone's (the host
  has every player's controller), never the others' on a client.
"""

from typing import Any

from .util import addr, call_str, def_name, log_error, named, try_

MAX_CHAIN = 32  # guard for the linked inventory chains
ITEM_KINDS = {  # class (or a superclass) -> kind shown by the page
    "WillowWeapon": "weapon",
    "WillowShield": "shield",
    "WillowGrenadeMod": "grenade",
    "WillowClassMod": "classmod",
    "WillowArtifact": "relic",
    "WillowMissionItem": "mission",
    "WillowUsableItem": "usable",
}

_static: dict[int, dict[str, Any]] = {}  # SkillDefinition / branch address -> names (static data)
# Backpack items, by (address, class): they only change when picked up / sold, so each is read
# once (equipped items are re-read: their stats include the owner's current bonuses)
_backpack_cache: dict[tuple[int, str], dict[str, Any]] = {}
# Equipped items' static data (name, parts...) by the same key: only their stats are re-read
_equipped_cache: dict[tuple[int, str], dict[str, Any]] = {}
# Skill trees by controller address: re-read only when the points spent change
_skills_cache: dict[int, tuple[Any, dict[str, Any]]] = {}


def _kind(inv: Any) -> str:
    cls = inv.Class
    while cls is not None:
        if (kind := ITEM_KINDS.get(str(cls.Name))) is not None:
            return kind
        cls = cls.SuperField
    return "item"


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def _stats(inv: Any, kind: str) -> list[list[Any]]:
    """Card-like stats [key, value, extra] (current values, with the owner's bonuses), where they exist."""
    out: list[list[Any]] = []

    def get(name: str) -> float | None:
        return _num(try_(lambda: getattr(inv, name)))

    if kind == "weapon":
        dmg, pellets = get("InstantHitDamage"), get("ProjectilesPerShot")
        if dmg:
            out.append(["damage", round(dmg), round(pellets or 1)])
        if (interval := get("FireInterval")) and interval > 0:
            out.append(["fireRate", round(1 / interval, 2)])
        if clip := get("ClipSize"):
            out.append(["magazine", round(clip)])
        if reload := get("ReloadTime"):
            out.append(["reload", round(reload, 2)])
        if (chance := get("StatusEffectChanceModifier")) and chance > 0:
            out.append(["elementChance", round(chance, 3)])
    elif kind == "grenade":
        if dmg := get("GrenadeDamage"):
            out.append(["damage", round(dmg)])
        if radius := get("BlastRadius"):
            out.append(["blastRadius", round(radius / 50, 1)])  # uu -> m
        if fuse := get("FuseTime"):
            out.append(["fuse", round(fuse, 2)])
    return out


def _localized(obj: Any, grade: int) -> str:
    """The game's own display text for a definition, in the game's language ("" if it has none).

    Localized properties (see .claude/documentation/notes.md): name parts' PartName, weapon types'
    Typename, item definitions' ItemName, manufacturers' Grades[grade].DisplayName.
    """
    for prop in ("PartName", "Typename", "ItemName"):
        text = try_(lambda p=prop: str(getattr(obj, p)), "")
        if text:
            return text
    grades = try_(lambda: list(obj.Grades), [])
    if grades:
        grade_data = grades[grade] if 0 <= grade < len(grades) else grades[0]
        return try_(lambda: str(grade_data.DisplayName), "")
    return ""


def _parts(inv: Any, item: dict[str, Any]) -> list[list[str]]:
    """DefinitionData fields as [slot, object name, group, localized name].

    The group is the part's package group, which names its role for item parts (e.g.
    GD_GrenadeMods.DamageRadius.DamageRadius_Normal -> "DamageRadius"); the page labels by it.
    Also sets item["type"] / item["maker"] (localized weapon type or item name, manufacturer).
    """
    data = try_(lambda: inv.DefinitionData)
    if data is None:
        return []
    fields = [f for f in try_(lambda: list(data._type._fields()), []) if f.Class.Name.endswith("Property")]
    grade = next((try_(lambda f=f: int(data._get_field(f)), 0) for f in fields if f.Name == "ManufacturerGradeIndex"), 0)
    out = []
    for f in fields:
        if f.Class.Name != "ObjectProperty":
            continue
        obj = try_(lambda f=f: data._get_field(f))
        if obj is None:
            continue
        slot = str(f.Name)
        for suffix in ("ItemNamePartDefinition", "ItemPartDefinition", "PartDefinition", "Definition"):
            slot = slot.removesuffix(suffix)
        group = try_(lambda o=obj: str(o.Outer.Name), "")
        text = _localized(obj, grade) if slot in ("WeaponType", "Item", "Manufacturer", "Prefix", "Title",
                                                   "PrefixItemName", "TitleItemName") else ""
        if slot in ("WeaponType", "Item") and text:
            item["type"] = text
        elif slot == "Manufacturer" and text:
            item["maker"] = text
        out.append([slot, str(obj.Name), group, text])
    return out


def _item(inv: Any, equipped: bool) -> dict[str, Any]:
    kind = _kind(inv)
    name = call_str(inv.GetShortHumanReadableName) or try_(lambda: str(inv.GeneratedItemName), "")
    item: dict[str, Any] = {
        "i": addr(inv),
        **named(name, def_name(inv.Class)),
        "k": kind,
        "c": str(inv.Class.Name),
        "q": try_(lambda: int(inv.RarityLevel), 0),
        "l": try_(lambda: int(inv.ExpLevel), 0),
        "v": try_(lambda: int(inv.MonetaryValue), 0),
        "e": equipped,
        "stats": _stats(inv, kind),
    }
    item["parts"] = _parts(inv, item)
    if kind == "weapon" and (slot := try_(lambda: int(inv.QuickSelectSlot), 0)):
        item["slot"] = slot
    return item


def _equipped_item(inv: Any) -> dict[str, Any]:
    """An equipped item: static data from the cache, stats (owner's bonuses) and slot read now."""
    key = (inv._get_address(), str(inv.Class.Name))
    if key not in _equipped_cache:
        _equipped_cache[key] = _item(inv, True)
    item = {**_equipped_cache[key], "stats": _stats(inv, _equipped_cache[key]["k"])}
    if item["k"] == "weapon":
        item.pop("slot", None)
        if slot := try_(lambda: int(inv.QuickSelectSlot), 0):
            item["slot"] = slot
    return item


def _chain(first: Any, equipped: bool) -> list[dict[str, Any]]:
    out, inv = [], first
    for _ in range(MAX_CHAIN):
        if inv is None:
            break
        try:
            out.append(_equipped_item(inv) if equipped else _item(inv, equipped))
        except Exception as ex:  # noqa: BLE001
            log_error("inspect item", ex)
        inv = try_(lambda i=inv: i.Inventory)
    return out


def _inventory(pawn: Any, player: dict[str, Any]) -> None:
    inv_mgr = try_(lambda: pawn.InvManager)
    if inv_mgr is None:
        held = try_(lambda: pawn.Weapon)
        player["equipped"] = [_item(held, True)] if held is not None else []
        player["inventory"] = "partial"
        player["inventoryWhy"] = "unavailable" if player["local"] else "coopClient"
        return
    equipped = _chain(try_(lambda: inv_mgr.InventoryChain), True) + _chain(try_(lambda: inv_mgr.ItemChain), True)
    equipped.sort(key=lambda it: (it["k"] != "weapon", it.get("slot", 9), it["k"]))
    backpack = []
    for inv in try_(lambda: list(inv_mgr.Backpack), []):
        if inv is None:
            continue
        try:
            key = (inv._get_address(), str(inv.Class.Name))
            if key not in _backpack_cache:
                _backpack_cache[key] = _item(inv, False)
            backpack.append(_backpack_cache[key])
        except Exception as ex:  # noqa: BLE001
            log_error("inspect backpack item", ex)
    player["equipped"] = equipped
    player["backpack"] = backpack
    player["inventory"] = "full"


def _static_info(obj: Any, fn) -> dict[str, Any]:  # noqa: ANN001
    key = obj._get_address()
    if key not in _static:
        _static[key] = fn(obj)
    return _static[key]


def _skills(ctrl: Any, player: dict[str, Any]) -> None:
    tree = try_(lambda: ctrl.PlayerSkillTree) if ctrl is not None else None
    if tree is None:
        player["skillsWhy"] = "unavailable" if player["local"] else "coopClient"
        return
    # The whole tree is ~50 skills x several reads: only re-read when the points spent change
    points = try_(lambda: int(tree.GetSkillPointsSpentInTree()), None)
    key = ctrl._get_address()
    cached = _skills_cache.get(key)
    if cached is not None and cached[0] == points and points is not None:
        player.update(cached[1])
        return
    branches: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for b in try_(lambda: list(tree.Branches), []):
        bd = try_(lambda b=b: b.BranchDefinition)
        if bd is None:
            continue
        info = _static_info(bd, lambda d: named(try_(lambda: str(d.BranchName), ""), def_name(d)))
        key = bd._get_address()
        branches[key] = {**info, "pts": try_(lambda b=b: int(b.PointsSpentInBranch), 0), "skills": []}
        order.append(key)
    loose: list[dict[str, Any]] = []
    for s in try_(lambda: list(tree.Skills), []):
        sd = try_(lambda s=s: s.SkillDefinition)
        if sd is None:
            continue
        info = _static_info(sd, lambda d: {
            **named(try_(lambda: str(d.SkillName), ""), def_name(d)),
            "m": try_(lambda: int(d.MaxGrade), 0),
            "d": try_(lambda: str(d.SkillDescription), ""),
        })
        skill = {**info, "g": try_(lambda s=s: int(s.SkillGrade), 0), "t": try_(lambda s=s: int(s.TierNumber), 0)}
        parent = try_(lambda s=s: s.ParentBranchDefinition)
        target = branches.get(parent._get_address()) if parent is not None else None
        (target["skills"] if target is not None else loose).append(skill)
    trees = [branches[k] for k in order if branches[k]["skills"]]
    if loose:
        trees.insert(0, {"n": "", "pts": 0, "skills": loose})  # the page names it
    result = {"skills": trees, "skillPoints": points}
    _skills_cache[key] = (points, result)
    player.update(result)


def _class_name(ctrl: Any, pri: Any) -> str:
    """From the class definition's object name (no localized name found yet): a raw name."""
    cls = try_(lambda: ctrl.PlayerClass) if ctrl is not None else None
    return def_name(cls) or def_name(try_(lambda: pri.CharacterNameIdDef)) or ""


def read_players(world_info: Any, me: Any) -> list[dict[str, Any]]:
    """Every player pawn in the level, with what can be read of their gear and skills."""
    for cache in (_backpack_cache, _equipped_cache):
        if len(cache) > 2000:  # items sold / dropped / from other levels: start over now and then
            cache.clear()
    players = []
    me_addr = addr(me) if me is not None else None
    pawn = world_info.PawnList
    for _ in range(1000):
        if pawn is None:
            break
        try:
            pri = try_(lambda p=pawn: p.PlayerReplicationInfo)
            if pri is not None and "PlayerPawn" in str(pawn.Class.Name) and not pawn.bDeleteMe:
                ctrl = try_(lambda p=pawn: p.Controller)
                player: dict[str, Any] = {
                    "i": addr(pawn),
                    "n": try_(lambda: str(pri.PlayerName), "") or "Player",
                    "local": addr(pawn) == me_addr,
                    "lvl": try_(lambda: int(pri.ExpLevel), 0),
                    "cls": _class_name(ctrl, pri),
                    "clsRaw": 1,
                }
                _inventory(pawn, player)
                _skills(ctrl, player)
                players.append(player)
        except Exception as ex:  # noqa: BLE001
            log_error("inspect player", ex)
        pawn = try_(lambda p=pawn: p.NextPawn)
    players.sort(key=lambda p: (not p["local"], p["n"].lower()))
    return players
