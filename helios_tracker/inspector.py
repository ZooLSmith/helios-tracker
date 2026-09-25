"""
Player inspection: equipped gear, backpack and skills of every player, for the page's inspector.

Game thread only (called by the collector every PLAYERS_EVERY). Reads defensively: what's missing
is reported (as a reason code the page translates), not guessed. Stats are sent as raw numbers
([key, value, extra]); the page labels and formats them. Expected availability (to verify with tools/probe_inventory.py):
- inventory: `pawn.InvManager` - our own; on the host probably everyone's, on a client only ours.
  A client still gets the others' equipped gear, replicated on their pawn (seen in game,
  tools/probe_coop.py): `Weapon` (in hand), `HolsteredWeaponSlots` (the other carried weapons) and
  `EquippedItems` (shield, grenade, class mod, relic) - not their backpack. The host has everyone's
  inventory manager, but not the others' backpack items (`Backpack` empty, no item objects of theirs
  besides the equipped ones: tools/probe_backpack.txt). Their `BackpackInventoryCount` there isn't
  their count either: it read 24 one session, 0 then negative (after a drop) in another - it seems to
  only count what the host saw them pick up / drop. So nothing of their backpack is shown;
- skills: `pawn.Controller.PlayerSkillTree` - our own; on the host probably everyone's (the host
  has every player's controller), never the others' on a client.
"""

import re
from typing import Any

import unrealsdk
from mods_base import get_pc

from . import gamecards

from .util import addr, call_str, def_name, field, item_name, log, log_error, named, player_info, try_

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
_grids: dict[tuple[str, int], list[dict[str, Any]]] = {}  # branch grids (static per class)
_level_start: dict[int, int] = {}  # level -> total XP where it starts (a fixed game table)
_xp_logged = [False]  # why the local player's XP is missing: logged once


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
    """Card-like stats [key, card value, current value, extra], where they exist: the card's (the item's own: each
    attribute's *BaseValue twin - InstantHitDamageBaseValue 126.4) and the current one, with the owner's bonuses
    (skills, class mod, relic: InstantHitDamage 354.3) - both, for the player's own maths (the user's call: "the
    point of the plugin is to help us on calculus"). No BaseValue twin: the current value for both."""
    out: list[list[Any]] = []

    def get(name: str) -> float | None:  # (field(): ~10x cheaper than by name - these are re-read every pass)
        return _num(try_(lambda: field(inv, name)))

    def pair(name: str) -> tuple[float | None, float | None]:  # (card, current)
        now = get(name)
        base = get(name + "BaseValue")
        return (base if base is not None else now), now

    if kind == "weapon":
        (dmg0, dmg), pellets = pair("InstantHitDamage"), get("ProjectilesPerShot")
        if dmg:
            out.append(["damage", round(dmg0), round(dmg), round(pellets or 1)])
        interval0, interval = pair("FireInterval")
        if interval and interval > 0 and interval0 and interval0 > 0:
            out.append(["fireRate", round(1 / interval0, 2), round(1 / interval, 2)])
        clip0, clip = pair("ClipSize")
        if clip:
            out.append(["magazine", round(clip0), round(clip)])
        reload0, reload = pair("ReloadTime")
        if reload:
            out.append(["reload", round(reload0, 2), round(reload, 2)])
        if (chance := _element_chance(inv)) is not None:
            out.append(["elementChance", *chance])
    elif kind == "grenade":
        dmg0, dmg = pair("GrenadeDamage")
        if dmg:
            out.append(["damage", round(dmg0), round(dmg)])
        radius0, radius = pair("BlastRadius")
        if radius:  # uu -> m (1 uu = 1 cm, measured: tools/probe_scale.py)
            out.append(["blastRadius", round(radius0 / 100, 1), round(radius / 100, 1)])
        fuse0, fuse = pair("FuseTime")
        if fuse:
            out.append(["fuse", round(fuse0, 2), round(fuse, 2)])
    return out


def _localized(obj: Any, grade: int) -> str:
    """The game's own display text for a definition, in the game's language ("" if it has none).

    Localized properties (see the repo's .agent/notes.md): name parts' PartName, weapon types'
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


def _item(inv: Any, equipped: bool, ctrl: Any = None) -> dict[str, Any]:
    kind = _kind(inv)
    name = item_name(inv)
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
    if card := _card_lines(inv, kind):
        item["card"] = card
    # its item card icons' keys, the game's (gamecards.py serves them: /cardicon/<kind>/<key>.png): its manufacturer's
    # FlashLabelName ("maliwan"), a weapon's type's ScaleformFrameName ("pistol" - a property), another item's
    # type frame from the card's own IItemCardable.GetZippyFrame() ("Artifact", "comm", "Customization_Head":
    # tools/probe_zippy.txt; a call - once per definition, cached) and its ElementalFrame (relics, grenades)
    data = try_(lambda: inv.DefinitionData)
    if data is not None:
        if mf := str(try_(lambda: data.ManufacturerDefinition.FlashLabelName, "") or ""):
            item["mf"] = mf
        if kind == "weapon" and (wt := str(try_(lambda: data.WeaponTypeDefinition.ScaleformFrameName, "") or "")):
            item["wt"] = wt
    if kind != "weapon":
        definition = try_(lambda: data.ItemDefinition) if data is not None else None
        zkey = (str(try_(lambda: inv.Class.Name, "")), definition._get_address() if definition is not None else addr(inv))
        if zkey not in _zippy:
            _zippy[zkey] = str(try_(lambda: inv.GetZippyFrame(), "") or "")
        if _zippy[zkey].lower() not in ("", "none"):
            item["wt"] = _zippy[zkey].lower()
        if (element := try_(lambda: str(inv.ElementalFrame), "") or "").lower() not in ("", "none"):
            item["el"] = element
    if kind == "weapon" and (element := try_(lambda: str(inv.ElementalFrame), "") or "").lower() not in ("", "none"):
        # its element: the item card's frame for its icon ("shock" - an identifier: the game has no display name for
        # it, tools/probe_weapon_card2.txt) and its damage per second (StatusEffectDamage: 76.3 on a shock pistol)
        item["el"] = element
        item["edps"] = round(try_(lambda: float(inv.StatusEffectDamage), 0.0), 1)
        # its colour: its card line's TextColor (the page picks it); without one, the damage type's HUDDamageColor
        # (the hit markers' colour, never on a card: the fallback)
        damage_type = next(iter(try_(lambda: list(inv.InstantHitDamageTypeDefinitions), []) or []), None)
        colour = try_(lambda: damage_type.HUDDamageColor) if damage_type is not None else None
        if damage_type is not None and (name := _element_name(damage_type, ctrl or get_pc())):
            item["eln"] = name  # the game's name for it ("shock": its localization)
        if colour is not None:
            rgb = tuple(try_(lambda c=c: int(getattr(colour, c)), 0) for c in ("R", "G", "B"))
            if any(rgb):
                item["ecol"] = "#%02x%02x%02x" % rgb
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
        if slot := try_(lambda: int(field(inv, "QuickSelectSlot")), 0):
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
        inv = try_(lambda i=inv: field(i, "Inventory"))
    return out


def _inventory(pawn: Any, player: dict[str, Any]) -> None:
    inv_mgr = try_(lambda: pawn.InvManager)
    if inv_mgr is None:  # (a co-op client, for the others) what their pawn shows: their equipped gear
        seen: set[int] = set()
        equipped = []
        for inv in [try_(lambda: pawn.Weapon), *(try_(lambda: list(pawn.HolsteredWeaponSlots), []) or []),
                    *(try_(lambda: list(pawn.EquippedItems), []) or [])]:
            if inv is None or (key := inv._get_address()) in seen:
                continue
            seen.add(key)
            try:
                equipped.append(_equipped_item(inv))
            except Exception as ex:  # noqa: BLE001
                log_error("inspect item", ex)
        equipped.sort(key=lambda it: (it["k"] != "weapon", it.get("slot", 9), it["k"]))
        player["equipped"] = equipped
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
    slots = try_(lambda: int(inv_mgr.InventorySlotMax_Misc), None)
    if player["local"] and slots:
        player["slots"] = [len(backpack), slots]  # backpack slots used / available (ours: our items)
    if not player["local"] and not backpack:  # (as host) the others' items aren't sent
        player["backpackWhy"] = "notSent"


def _static_info(obj: Any, fn) -> dict[str, Any]:  # noqa: ANN001
    key = obj._get_address()
    if key not in _static:
        _static[key] = fn(obj)
    return _static[key]


_stats_cache: dict[tuple[int, int, int], list[dict[str, Any]]] = {}  # (skill def, grade, player level) -> its lines


def _skill_stats(sd: Any, ctrl: Any, grade: int) -> list[dict[str, Any]]:
    """A skill's tooltip stats at a grade, as the game computes them (tools/probe_skill_stats2.txt):
    SkillDefinition.GetSkillEffectPresentations(grade, the player's controller, out lines) -> each line's
    presentation (Description: game text with a $NUMBER$ placeholder, "Gun Damage: $NUMBER$"; its display
    flags) and ModifierValue (0.06 = +6 % when shown as a percentage). A function call: cached per (skill,
    grade, player level) - the skills payload is only rebuilt when the points spent change anyway.
    -> [{"d": text, "v": value, + the flags that are set: pct, pf (percent as float), inv, nn (no number), np (no
    plus sign), pos (always positive: SIGNSTYLE_Positive), fl (rounding: float, precision fp; else an int),
    pre / suf}]"""
    level = try_(lambda: int(ctrl.PlayerReplicationInfo.ExpLevel), 0)
    key = (sd._get_address(), grade, level)
    if key in _stats_cache:
        return _stats_cache[key]
    result = try_(lambda: sd.GetSkillEffectPresentations(grade, ctrl, []))
    entries = result[1] if isinstance(result, tuple) and len(result) > 1 else []
    out = [line for e in entries or [] if (line := _presentation_line(e))]
    _stats_cache[key] = out
    return out


def _enum_name(value: Any) -> str:
    """A game enum's name ("SIGNSTYLE_Positive"): its .name - str() of one gives its number on Python 3.11+ (the
    enums are int-based), which broke every name test ("Generic" in str(...) never matched)."""
    return str(getattr(value, "name", value) or "")


_LOC_REF = re.compile(r"\$([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)")
_game_texts: dict[str, str] = {}


def _game_text(text: str) -> str:
    """A text as the game shows it: a localization reference ("$WillowGame.ItemCardPresentationDescriptions.
    CharacterHead": a customization's card line) looked up in the loaded localization, in the game's language
    (Object.Localize(section, key, package): WillowGame.int's "Unlocks this head for the Quick Change system...";
    once per reference, cached); "" when it has none (never the raw reference). Other texts as they are."""
    m = _LOC_REF.fullmatch(text.strip())
    if m is None:
        return text
    if text not in _game_texts:
        package, section, key = m.groups()
        ctrl = try_(get_pc)
        found = str(try_(lambda: ctrl.Localize(section, key, package), "") or "") if ctrl is not None else ""
        _game_texts[text] = "" if not found or found.startswith("?") else found.strip()
    return _game_texts[text]


def _presentation_line(entry: Any, item: Any = None) -> dict[str, Any] | None:
    """One {AttributePresentation, ModifierValue, bShouldDisplay} entry (a skill's stats, an item card's lines) ->
    a line for the page: its text, display flags (see _skill_stats), value; None if hidden / without text.
    Its text (tools/probe_weapon_card2.txt): the Description (a $NUMBER$ placeholder), else NoConstraintText
    ("Deals bonus elemental damage."), and / or a Prefix / Suffix around the number ("Consumes [skill]" 2
    "ammo[-skill] per shot."). Its colour: TextColor when not white (the element's: shock's blue on "Highly
    effective vs Shields."; a unique's red text). An item's line tied to one of its attributes (the shot cost):
    that attribute's current value on the item ("cur": 2 - ModifierValue is the modifier, 1)."""
    p = try_(lambda: entry.AttributePresentation)
    if p is None or not try_(lambda: bool(entry.bShouldDisplay), True):
        return None
    text = _game_text(try_(lambda: str(p.Description), "") or "")
    pre, suf = _game_text(try_(lambda: str(p.Prefix), "") or ""), _game_text(try_(lambda: str(p.Suffix), "") or "")
    if not text and not pre and not suf:
        text = _game_text(try_(lambda: str(p.NoConstraintText), "") or "")
    value = try_(lambda: float(entry.ModifierValue), None)
    if (not text and not pre and not suf) or value is None:
        return None
    flag = lambda name: try_(lambda: bool(getattr(p, name)), False)  # noqa: E731
    line: dict[str, Any] = {"d": text, "v": round(value, 6)}
    for short, name in (("pct", "bDisplayAsPercentage"), ("pf", "bDisplayPercentAsFloat"), ("inv", "bDisplayAsInverse"),
                        ("nn", "bDontDisplayNumber"), ("np", "bDontDisplayPlusSign")):
        if flag(name):
            line[short] = 1
    if "Positive" in _enum_name(try_(lambda: p.SignStyle, "")):
        line["pos"] = 1
    if "Float" in _enum_name(try_(lambda: p.RoundingMode, "")):
        line["fl"] = 1
        line["fp"] = try_(lambda: int(p.FloatPrecision), 1)
    if pre:
        line["pre"] = pre
    if suf:
        line["suf"] = suf
    colour = try_(lambda: p.TextColor)
    if colour is not None and try_(lambda: bool(p.bEnableTextColor), False):
        rgb = tuple(try_(lambda c=c: int(getattr(colour, c)), 255) for c in ("R", "G", "B"))
        if rgb != (255, 255, 255):
            line["col"] = "#%02x%02x%02x" % rgb
    if item is not None and (current := _attribute_value(item, try_(lambda: p.Attribute))) is not None:
        line["cur"] = current
    return line


def _attribute_value(obj: Any, attribute: Any) -> float | None:
    """An attribute's current value on an object, by property only: its first value resolver, when it reads a
    property (ObjectPropertyAttributeValueResolver.PropertyName: the weapon's own field), read from the object -
    no function call. None if it's resolved otherwise."""
    if attribute is None:
        return None
    resolver = next(iter(try_(lambda: list(attribute.ValueResolverChain), []) or []), None)
    name = str(try_(lambda: resolver.PropertyName, "") or "") if resolver is not None else ""
    if not name or name == "None":
        return None
    value = try_(lambda: float(getattr(obj, name)))
    return round(value, 4) if value is not None else None


_base_chances: dict[int, float | None] = {}  # status effect definition -> its base chance (%)
_zippy: dict[tuple[str, int], str] = {}  # (item class, definition address) -> its GetZippyFrame() (its card's type frame)
_element_names: dict[str, str] = {}  # damage type key ("Shock") -> the game's name for it, in its language


def _element_name(damage_type: Any, ctrl: Any) -> str:
    """An element's name as the game writes it, in its language: WillowMenu.int's [DamageTypes] section
    (Incendiary=incendiary, Shock=shock, Corrosive=corrosive, Explosive=explosive, Amp=slag - lower case: the game
    puts them in sentences, "%d" in its mission hints), keyed by the damage type's DamageType enum without its
    DAMAGE_TYPE_ prefix (DAMAGE_TYPE_Shock -> Shock). Object.Localize(section, key, package): a lookup of the
    loaded localization, called once per element (cached). "" if it has none (UE3's "?INT?...?" = missing)."""
    key = _enum_name(try_(lambda: damage_type.DamageType, "")).removeprefix("DAMAGE_TYPE_")
    if not key:
        return ""
    if key not in _element_names:
        text = str(try_(lambda: ctrl.Localize("DamageTypes", key, "WillowMenu"), "") or "") if ctrl is not None else ""
        _element_names[key] = "" if text.startswith("?") else text.strip()
    return _element_names[key]


def _element_chance(weapon: Any) -> list[float] | None:
    """A weapon's elemental effect chance, the card's way (tools/probe_element_chance.txt): its element's base
    chance (its damage type's StatusEffect: DamageSurfaceChanceModifiers[SurfaceType Generic].BaseChance - shock
    20) x its BaseStatusEffectChanceModifier (0.6) x its StatusEffectChanceModifier (1.4) = 16.8 % - the card uses
    the base values; with the player's skills' modifiers (the current values: 1.496) it's 17.95 %.
    -> [the card's %, the current %], or None without an element / a readable base chance. Property reads."""
    damage_type = next(iter(try_(lambda: list(weapon.InstantHitDamageTypeDefinitions), []) or []), None)
    effect = try_(lambda: damage_type.StatusEffect) if damage_type is not None else None
    if effect is None:
        return None
    key = effect._get_address()
    if key not in _base_chances:
        base = None
        for mod in try_(lambda: list(effect.DamageSurfaceChanceModifiers), []) or []:
            if "Generic" in _enum_name(try_(lambda m=mod: m.SurfaceType, "")):
                chance = try_(lambda m=mod: m.BaseChance)
                if chance is not None and try_(lambda: chance.BaseValueAttribute) is None:  # (a constant, not resolved)
                    base = try_(lambda: float(chance.BaseValueConstant) * float(chance.BaseValueScaleConstant))
                break
        _base_chances[key] = base
    base = _base_chances[key]
    if not base:
        return None
    read = lambda name: try_(lambda: float(field(weapon, name)))  # noqa: E731
    card = [read("BaseStatusEffectChanceModifierBaseValue"), read("StatusEffectChanceModifierBaseValue")]
    now = [read("BaseStatusEffectChanceModifier"), read("StatusEffectChanceModifier")]
    if None in card or None in now:
        return None
    return [round(base * card[0] * card[1], 2), round(base * now[0] * now[1], 2)]


def _card_lines(inv: Any, kind: str) -> list[dict[str, Any]]:
    """An item's card lines, as the game's item card shows them (tools/probe_weapon_card.txt): a weapon's
    WeaponCardModifierStats (its material's "High elemental effect chance.", its element's "Highly effective vs
    Shields.", its shot cost...), other gear's ItemCardModifierStats (a class mod's skill bonuses...) - the same
    entries as the skills' stats. Static per item: read with its record.
    Its element's line (its damage type's own WeaponCardPresentations: "GD_Shock.DamageType.DmgType_Shock_Impact:
    AttributePresentationDefinition_5") marked "el": the element's colour - its TextColor when set (shock's blue),
    else the page falls back to the damage type's HUDDamageColor (fire's "Highly effective vs Flesh." has none)."""
    name = "WeaponCardModifierStats" if kind == "weapon" else "ItemCardModifierStats"
    element_lines = {try_(lambda p=p: addr(p)) for d in try_(lambda: list(inv.InstantHitDamageTypeDefinitions), []) or [] if d is not None
                     for p in try_(lambda d=d: list(d.WeaponCardPresentations), []) or [] if p is not None} if kind == "weapon" else set()
    out = []
    for e in try_(lambda: list(getattr(inv, name)), []) or []:
        if line := _presentation_line(e, inv):
            if element_lines and try_(lambda e=e: addr(e.AttributePresentation)) in element_lines:
                line["el"] = 1
            out.append(line)
    return out


_card_keys_sent = [False]


def _card_keys() -> None:
    """Once: the game's keys for the item card icons, from the loaded definitions - every manufacturer's
    FlashLabelName, every weapon type's ScaleformFrameName (gamecards.py picks the sprites labelled with them).
    Two find_all (each walks every object): once per session."""
    if _card_keys_sent[0]:
        return
    _card_keys_sent[0] = True
    for kind, cls, prop in (("manufacturer", "ManufacturerDefinition", "FlashLabelName"),
                            ("type", "WeaponTypeDefinition", "ScaleformFrameName")):
        keys = {str(try_(lambda d=d: getattr(d, prop), "") or "") for d in try_(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or []
                if not d.Name.startswith("Default__")}
        gamecards.set_keys(kind, keys - {"", "None"})
    # the elements': the damage types' DamageType enum, its names without DAMAGE_TYPE_ (Shock, Amp: slag...) - the
    # element list's frames ("shock", "amp"; a weapon's ElementalFrame picks one)
    damage_type = next(iter(try_(lambda: list(unrealsdk.find_all("WillowDamageTypeDefinition", exact=False)), []) or []), None)
    enum = type(try_(lambda: damage_type.DamageType)) if damage_type is not None else None
    members = getattr(enum, "__members__", None) or {}
    gamecards.set_keys("element", {name.removeprefix("DAMAGE_TYPE_") for name in members} - {"", "MAX"})


def _skill_bonuses(pawn: Any) -> dict[str, int]:
    """The skill ranks the equipped items add (a class mod's "+2 Steady", blue in the skill screen:
    tools/probe_skill_bonus.txt): an item's ItemCardModifierStats[] = {AttributePresentation, ModifierValue}
    - its card's lines; a skill bonus's presentation lives in the class's skills package
    (GD_AttributePresentation.Skills_Soldier.AttrPresent_Steady) and is named after the skill's definition
    (GD_Soldier_Skills.Gunpowder.Steady): value 2.02 -> +2. The tree's own Grade / GetSkillGrade: the points spent
    only. -> {skill definition name (lower case): [[ranks, the item's name], ...]} - per item, like the game's
    "+2 skill points from <the class mod>"."""
    bonuses: dict[str, list[list[Any]]] = {}
    item = try_(lambda: pawn.InvManager.ItemChain)
    for _ in range(MAX_CHAIN):
        if item is None:
            break
        for line in try_(lambda i=item: list(i.ItemCardModifierStats), []) or []:
            pres = try_(lambda ln=line: ln.AttributePresentation)
            path = try_(lambda p=pres: p._path_name(), "") if pres is not None else ""
            name = try_(lambda p=pres: str(p.Name), "") if pres is not None else ""
            if ".Skills_" not in path or not name.startswith("AttrPresent_"):
                continue
            ranks = int(try_(lambda ln=line: float(ln.ModifierValue), 0.0))
            if ranks:
                key = name[len("AttrPresent_"):].lower()
                bonuses.setdefault(key, []).append([ranks, try_(lambda i=item: item_name(i), "") or ""])
        item = try_(lambda i=item: field(i, "Inventory"))
    return bonuses


def _skills(ctrl: Any, player: dict[str, Any], bonuses: dict[str, list[list[Any]]] | None = None) -> None:
    tree = try_(lambda: ctrl.PlayerSkillTree) if ctrl is not None else None
    if tree is None:
        player["skillsWhy"] = "unavailable" if player["local"] else "coopClient"
        return
    # The whole tree is ~50 skills x several reads: only re-read when the points spent change
    points = try_(lambda: int(tree.GetSkillPointsSpentInTree()), None)
    ctrl_key = ctrl._get_address()  # (not `key`: the loops below used to overwrite it - the cache never hit)
    bonuses = bonuses or {}
    # (a class mod swapped: the bonuses change, not the points)
    cache_key = (points, tuple(sorted((k, tuple(map(tuple, v))) for k, v in bonuses.items())))
    cached = _skills_cache.get(ctrl_key)
    if cached is not None and cached[0] == cache_key and points is not None:
        player.update(cached[1])
        return
    # The tree's arrays (PlayerSkillTree*Data structs): Branches[] = {Definition, ...},
    # Tiers[] = {TierNumber, ParentBranchIndex, ...}, Skills[] = {Definition, Grade, ParentTierIndex,
    # ...}: a skill -> its tier -> its branch, by index. (Not the SkillTree*StateData structs:
    # those are what GetSkillState / GetBranchState return - reading them here found nothing.)
    branches: dict[int, dict[str, Any]] = {}  # branch index -> branch
    defs: dict[int, Any] = {}
    for bi, b in enumerate(try_(lambda: list(tree.Branches), []) or []):
        bd = try_(lambda b=b: b.Definition) or try_(lambda b=b: b.BranchDefinition)
        if bd is None:
            continue
        info = _static_info(bd, lambda d: named(try_(lambda: str(d.BranchName), ""), def_name(d)))
        branches[bi] = {**info, "pts": 0, "skills": []}
        defs[bi] = bd
    # The root branch (the action skill, one skill) isn't a skill tree: the branch without a parent,
    # or at SkillTreeRootIndex
    root_index = try_(lambda: int(tree.SkillTreeRootIndex), None)
    structure_known = root_index is not None
    for bi, b in enumerate(try_(lambda: list(tree.Branches), []) or []):
        parent = try_(lambda b=b: int(b.ParentBranchIndex), None)
        structure_known = structure_known or parent is not None
        if bi in branches and (bi == root_index or (parent is not None and parent < 0)):
            branches[bi]["root"] = True
    tiers = try_(lambda: list(tree.Tiers), []) or []
    loose: list[dict[str, Any]] = []
    by_def: dict[int, dict[str, Any]] = {}  # SkillDefinition address -> the skill (for the grids)
    for s in try_(lambda: list(tree.Skills), []) or []:
        sd = try_(lambda s=s: s.Definition) or try_(lambda s=s: s.SkillDefinition)
        if sd is None:
            continue
        info = _static_info(sd, lambda d: {
            **named(try_(lambda: str(d.SkillName), ""), def_name(d)),
            "m": try_(lambda: int(d.MaxGrade), 0),
            "d": try_(lambda: str(d.SkillDescription), ""),
            # its icon: the movie's path = its texture's (gameicons.py serves it: /icon/<path>.png)
            **({"ic": ic} if (ic := try_(lambda: d.SkillIcon._path_name(), "")) else {}),
        })
        grade = try_(lambda s=s: int(s.Grade), None)
        if grade is None:
            grade = try_(lambda s=s: int(s.SkillGrade), 0)
        tier_index = try_(lambda s=s: int(s.ParentTierIndex), -1)
        tier = tiers[tier_index] if 0 <= tier_index < len(tiers) else None
        skill = {**info, "g": grade, "t": try_(lambda: int(tier.TierNumber), 0) if tier is not None else 0}
        # bonus ranks from the equipped items (a class mod's): "b"; they only count once the skill has a point
        # of its own (the user) - the stats at the effective rank (points + bonus: the game's blue values) then,
        # none without a point; the next point's: one more (a first point: 1 + the bonus)
        sources = bonuses.get(try_(lambda: str(sd.Name), "").lower(), [])
        bonus = sum(ranks for ranks, _name in sources)
        if bonus:
            skill["b"] = bonus
            skill["bs"] = sources  # [[ranks, the item's name]]: where they come from
        effective = grade + bonus if grade > 0 else 0
        if effective > 0 and (fx := _skill_stats(sd, ctrl, effective)):
            skill["fx"] = fx
        if grade < info["m"] and (fxn := _skill_stats(sd, ctrl, grade + bonus + 1)):
            skill["fxn"] = fxn
        by_def[sd._get_address()] = skill
        branch = branches.get(try_(lambda: int(tier.ParentBranchIndex), -1)) if tier is not None else None
        if branch is not None:
            branch["skills"].append(skill)
            branch["pts"] += grade
        else:
            loose.append(skill)
    if not structure_known:  # couldn't read the tree structure: guess it's the one-skill branch
        for br in branches.values():
            if len(br["skills"]) == 1:
                br["root"] = True
    for bkey, branch in branches.items():  # the static layout, filled with this player's grades
        grid = _branch_grid(defs[bkey])
        if grid:
            branch["tiers"] = [
                {"need": tier["need"], "cells": [by_def.get(c) if c is not None else None for c in tier["cells"]]}
                for tier in grid
            ]
    trees = [branches[k] for k in sorted(branches) if branches[k]["skills"]]
    if loose:
        trees.insert(0, {"n": "", "pts": 0, "skills": loose})  # the page names it
    result = {"skills": trees, "skillPoints": points}
    _skills_cache[ctrl_key] = (cache_key, result)
    player.update(result)


def _branch_grid(bd: Any) -> list[dict[str, Any]]:
    """A branch's skill grid, as the skill tree menu draws it (static per class: cached).

    SkillTreeBranchDefinition.Tiers[] = {Skills[], PointsToUnlockNextTier} (one row per tier), and
    .Layout.Tiers[].bCellIsOccupied[] (which columns of that row hold a skill): the row's skills
    fill the occupied cells in order. -> [{"need": points, "cells": [SkillDefinition address | None]}]
    """
    key = ("grid", bd._get_address())
    if key in _grids:
        return _grids[key]
    grid = []
    layout_tiers = try_(lambda: list(bd.Layout.Tiers), []) or []
    for n, tier in enumerate(try_(lambda: list(bd.Tiers), []) or []):
        skills = [s for s in try_(lambda t=tier: list(t.Skills), []) if s is not None]
        occupied = try_(lambda n=n: [bool(c) for c in layout_tiers[n].bCellIsOccupied], None)
        if not occupied:
            occupied = [True] * len(skills)  # no layout: the skills side by side
        queue = iter(skills)
        cells = [(next(queue, None) if on else None) for on in occupied]
        # More skills than occupied cells: hidden helpers the menu never shows, listed after the real
        # ones (Krieg: "_Bloodlust" the stack counter, "FireStatusDetector"... - tools/probe_skill_layout.txt).
        # Left out: appended, they widened the grid and shifted every row.
        grid.append({
            "need": try_(lambda t=tier: int(t.PointsToUnlockNextTier), 0) or 0,
            "cells": [s._get_address() if s is not None else None for s in cells],
        })
    _grids[key] = grid
    return grid


def _xp(ctrl: Any, pri: Any, level: int) -> dict[str, Any]:
    """{"xp": [in this level, level size]} - from the controller (as the XP Counter mod reads it):
    total XP = ExpPool.Data.CurrentValue, next level at PRI.ExpPointsNextLevelAt, the level's start
    from GetExpPointsRequiredForLevel (cached). Needs the controller: ours, or everyone's as host.
    At the level cap (nothing left to earn): [0, 0]."""
    if ctrl is None or not level:
        return {}
    total = try_(lambda: int(ctrl.ExpPool.Data.CurrentValue))
    next_at = try_(lambda: int(pri.ExpPointsNextLevelAt))
    if total is None or next_at is None:
        return {}
    if level not in _level_start:
        start = try_(lambda: int(ctrl.GetExpPointsRequiredForLevel(level)))
        if start is None:
            return {}
        _level_start[level] = start
    start = _level_start[level]
    if next_at <= total:
        return {"xp": [0, 0]}
    return {"xp": [total - start, next_at - start]}


_class_names: dict[int, dict[str, Any]] = {}  # controller / player info address -> _class_name()


def _class_name(ctrl: Any, pri: Any) -> dict[str, Any]:
    """_class_name_uncached(), once per player (a player's class never changes)."""
    owner = ctrl if ctrl is not None else pri
    key = try_(lambda: owner._get_address())
    if key is None:
        return _class_name_uncached(ctrl, pri)
    if (cached := _class_names.get(key)) is None:
        cached = _class_name_uncached(ctrl, pri)
        if cached.get("cls") and not cached.get("clsRaw"):  # only the game's name (not yet loaded: again next time)
            _class_names[key] = cached
    return cached


def _class_name_uncached(ctrl: Any, pri: Any) -> dict[str, Any]:
    """{"cls": class, "char": character} - the game's localized class name ("Gunzerker" /
    "Défourailleur") and character name ("Salvador"), via the player info (shared with everyone:
    works for others on a client too) or the class definition; else the class definition's object
    name, flagged made-up ("clsRaw")."""
    # The player info points at the *character* (PlayerNameIdentifierDefinition: "Salvador"), whose
    # CharacterClassId is the class (PlayerClassIdentifierDefinition: "Gunzerker") - seen in game
    character = try_(lambda: pri.CharacterNameIdDef) or try_(lambda: ctrl.PlayerClass.CharacterNameId)
    class_id = try_(lambda: character.CharacterClassId)
    out: dict[str, Any] = {}
    if name := try_(lambda: str(character.LocalizedCharacterName), ""):
        out["char"] = name
    text = try_(lambda: str(class_id.LocalizedClassNameNonCaps), "")
    if text:
        return {**out, "cls": text}
    raw = def_name(try_(lambda: ctrl.PlayerClass) if ctrl is not None else None) or def_name(class_id)
    return {**out, "cls": raw, "clsRaw": 1} if raw else {**out, "cls": ""}


def read_players(world_info: Any, me: Any, pc: Any = None) -> list[dict[str, Any]]:
    """Every player pawn in the level, with what can be read of their gear and skills."""
    for cache in (_backpack_cache, _equipped_cache):
        if len(cache) > 2000:  # items sold / dropped / from other levels: start over now and then
            cache.clear()
    players = []
    me_addr = addr(me) if me is not None else None
    # Who hosts: us unless we're a client (NetMode 3); then the party leader (the host's player info
    # has bIsPartyLeader on a client: tools/probe_coop.txt)
    client = try_(lambda: int(world_info.NetMode), 0) == 3
    pawn = world_info.PawnList
    for _ in range(1000):
        if pawn is None:
            break
        try:
            # the class first (cheap): the player info (slow reads) only for players
            pri = player_info(pawn) if "PlayerPawn" in str(pawn.Class.Name) else None  # the vehicle's while driving
            if pri is not None and not field(pawn, "bDeleteMe"):
                # Driving, the controller possesses the vehicle and the player pawn's own is None:
                # through the vehicle, and ours is always the local player controller
                ctrl = try_(lambda p=pawn: p.Controller) or try_(lambda p=pawn: p.DrivenVehicle.Controller)
                if ctrl is None and me is not None and addr(pawn) == addr(me):
                    ctrl = pc
                player: dict[str, Any] = {
                    "i": addr(pawn),
                    "n": try_(lambda: str(pri.PlayerName), "") or "Player",
                    "local": addr(pawn) == me_addr,
                    "lvl": try_(lambda: int(pri.ExpLevel), 0),
                    "host": (bool(try_(lambda: pri.bIsPartyLeader, False)) if client
                             else addr(pawn) == me_addr),
                    **_class_name(ctrl, pri),
                    **_xp(ctrl, pri, try_(lambda: int(pri.ExpLevel), 0)),
                }
                if player["local"] and "xp" not in player and not _xp_logged[0]:
                    _xp_logged[0] = True
                    log(f"xp unavailable for the local player: controller={ctrl is not None}"
                        f" total={try_(lambda: ctrl.ExpPool.Data.CurrentValue)}"
                        f" next={try_(lambda: pri.ExpPointsNextLevelAt)} level={try_(lambda: pri.ExpLevel)}")
                _card_keys()
                _inventory(pawn, player)
                _skills(ctrl, player, try_(lambda p=pawn: _skill_bonuses(p), {}))
                players.append(player)
        except Exception as ex:  # noqa: BLE001
            log_error("inspect player", ex)
        pawn = try_(lambda p=pawn: field(p, "NextPawn"))
    players.sort(key=lambda p: (not p["local"], p["n"].lower()))
    return players
