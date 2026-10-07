"""
Player inspection: equipped gear, backpack and skills of every player, for the page's inspector.

Game thread only (called by the collector every PLAYERS_EVERY). Reads defensively: what's missing
is reported (as a reason code the page translates), not guessed. Stats are sent as raw numbers
([key, value, extra]); the page labels and formats them. Expected availability (to verify with tools/probes/probe_inventory.py):
- inventory: `pawn.InvManager` - our own; on the host probably everyone's, on a client only ours.
  A client still gets the others' equipped gear, replicated on their pawn (seen in game,
  tools/probes/probe_coop.py): `Weapon` (in hand), `HolsteredWeaponSlots` (the other carried weapons) and
  `EquippedItems` (shield, grenade, class mod, relic) - not their backpack. The host has everyone's
  inventory manager, but not the others' backpack items (`Backpack` empty, no item objects of theirs
  besides the equipped ones: tools/probes/probe_backpack.txt). Their `BackpackInventoryCount` there isn't
  their count either: it read 24 one session, 0 then negative (after a drop) in another - it seems to
  only count what the host saw them pick up / drop. So nothing of their backpack is shown;
- skills: `pawn.Controller.PlayerSkillTree` - our own; on the host probably everyone's (the host
  has every player's controller), never the others' on a client.
"""

import base64
import html
import json
import math
import re
import time
import zlib
from pathlib import Path
from typing import Any

import unrealsdk
from unrealsdk.unreal import WeakPointer
from mods_base import get_pc

from . import amounts, assets, games, paths

from .skills import skill_icon
from .util import PerObject, addr, call_str, def_name, field, item_name, log, log_error, named, player_info, try_

MAX_CHAIN = 32  # guard for the linked inventory chains

_static: dict[int, dict[str, Any]] = {}  # SkillDefinition / branch address -> names (static data)
# Backpack items, by (address, class): they only change when picked up / sold, so each is read
# once (equipped items are re-read: their stats include the owner's current bonuses)
class _ItemCache:
    """Item records by the item object: (address, class) -> (a WeakPointer to it, its record). An entry lives as long as
    its item: dropped, picked up, moved to the backpack - the same object, the same record; destroyed (sold, consumed,
    gone with its level), its WeakPointer is dead - even with another object at its address since - and the entry is
    rebuilt / swept (the user: cache them, clear the ones truly destroyed; first a blind clear past 2000 entries)."""

    def __init__(self) -> None:
        self._entries: dict[tuple[int, str], tuple[Any, dict[str, Any]]] = {}

    def get(self, inv: Any) -> dict[str, Any] | None:
        entry = self._entries.get((inv._get_address(), str(inv.Class.Name)))
        return entry[1] if entry is not None and entry[0]() is not None else None

    def put(self, inv: Any, record: dict[str, Any]) -> dict[str, Any]:
        self._entries[(inv._get_address(), str(inv.Class.Name))] = (WeakPointer(inv), record)
        return record

    def sweep(self) -> None:
        """Forgets the items destroyed since."""
        for key in [k for k, (ptr, _) in self._entries.items() if ptr() is None]:
            del self._entries[key]


# Backpack items (and gear on the ground: the same objects, dropped): they only change when picked up / sold, so each
# is read once (equipped items are re-read: their stats include the owner's current bonuses)
_backpack_cache = _ItemCache()
# Equipped items' static data (name, parts...) by the same key: only their stats are re-read
_equipped_cache = _ItemCache()
# A players pass builds gear cards (function calls: a few ms each - a whole backpack in one pass: 80-560 ms, a hitch) for
# at most ITEMS_SECONDS, at least one; the rest at the next pass - the collector retries soon, publishing only a complete
# pass (players_complete).
ITEMS_SECONDS = 0.004
_items_pass = {"deadline": float("inf"), "built": 0, "left": False, "skipped": 0}  # (outside a pass: no limit)
# A skill tree whose points can't be read (another player's, on the host - its cache never hit: re-read every pass,
# ~13 ms, 2026-10-04 co-op) is cached anyway, read again after this long
SKILLS_UNKNOWN_EVERY = 10.0  # s
# the last players pass's parts (s): the player's own fields (class, xp...), card keys, inventory, skills - for the
# slow-task report's breakdown (collector, paths.DIAGNOSTICS)
players_parts: dict[str, float] = {}
# Skill trees by controller (checked alive: util.PerObject): re-read only when the points spent change
_skills_cache = PerObject()
# An item's element level (games.GAME.items.element_level - a game's may be function calls; static per item): every
# players pass read it again for each equipped item (2026-10-04: players.inventory 3-5 ms a pass)
_element_levels = PerObject()
_grids: dict[tuple[str, int], list[dict[str, Any]]] = {}  # branch grids (static per class)
_level_start: dict[int, int] = {}  # level -> total XP where it starts (a fixed game table)
_xp_logged = [False]  # why the local player's XP is missing: logged once


def _kind(inv: Any) -> str:
    """An item's kind as the page shows it ("weapon", "shield"... - "item" if nothing tells): each game's."""
    return try_(lambda: games.GAME.items.kind(inv), "item") or "item"




def card_keys(inv: Any, kind: str | None = None) -> dict[str, str]:
    """Its item card icons' keys, the game's (gamecards.py serves them: /cardicon/<kind>/<key>.png): "mf" its
    manufacturer's FlashLabelName ("maliwan"), "wt" a weapon's type's ScaleformFrameName ("pistol" - a property),
    another item's type frame from the card's own IItemCardable.GetZippyFrame() (games.GAME.items.zippy_frame: "Artifact", "comm",
    "Customization_Head": tools/probes/probe_zippy.txt; a call - once per definition, cached; the game calls it for a ground
    item's card too), "el" its ElementalFrame ("shock" - an identifier: the game has no display name for it,
    tools/probes/probe_weapon_card2.txt). Those it has. Also for the pickups on the map (their type icon)."""
    kind = kind or _kind(inv)
    out: dict[str, str] = {}
    data = try_(lambda: inv.DefinitionData)
    if data is not None:
        if mf := str(try_(lambda: data.ManufacturerDefinition.FlashLabelName, "") or ""):
            out["mf"] = mf
        if kind == "weapon" and (wt := str(try_(lambda: data.WeaponTypeDefinition.ScaleformFrameName, "") or "")):
            out["wt"] = wt
    if kind != "weapon":
        definition = try_(lambda: data.ItemDefinition) if data is not None else None
        # (cached per definition; without one, read each time - an item's own address would outlive it as a key)
        zkey = (str(try_(lambda: inv.Class.Name, "")), definition._get_address()) if definition is not None else None
        if zkey is None or zkey not in _zippy:
            frame = str(try_(lambda: games.GAME.items.zippy_frame(inv), "") or "")
            if zkey is not None:
                _zippy[zkey] = frame
        else:
            frame = _zippy[zkey]
        if frame.lower() not in ("", "none"):
            out["wt"] = frame.lower()
    if element := try_(lambda: games.GAME.items.element_frame(inv, kind), "") or "":  # (each game's)
        out["el"] = element
    return out


def gibbed_code(inv: Any) -> str:
    """Its code for Gibbed's save editors ("BL2(hwAAAAAB...)", the Pre-Sequel's "BLOZ(...)"), or "". The body is the
    game's own item serial - what a save holds: the native CreateSerialNumber()'s Buffer, the packed bits before the
    game writes its check and scrambles it (tools/probes/probe_serial2.txt) - finished the way Gibbed's copy button does it
    (PackedDataHelper.Encode): the unique id cleared (then the scrambling, seeded by it, does nothing), the check
    written (CRC32 of the 40 bytes with 0xFFFF in its place, its halves xored), the trailing 0xFF bytes dropped,
    base64. A call, once per item record (they're cached)."""
    prefix = games.GAME.gibbed_prefix
    serial = try_(lambda: inv.CreateSerialNumber()) if prefix else None
    if serial is None or _enum_name(try_(lambda: serial.State, "")) != "SNS_Full":
        return ""
    data = try_(lambda: bytearray(int(b) & 0xFF for b in serial.Buffer))
    if not data or len(data) != 40:
        return ""
    data[1:5] = bytes(4)  # the unique id
    data[5:7] = b"\xff\xff"
    check = zlib.crc32(data)
    data[5:7] = (((check >> 16) ^ check) & 0xFFFF).to_bytes(2, "big")
    end = len(data)
    while end > 7 and data[end - 1] == 0xFF:
        end -= 1
    return f"{prefix}({base64.b64encode(bytes(data[:end])).decode('ascii')})"


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
            # rounded as the game's card does (its profile's damage_presentation), else to the nearest
            if (pres := _damage_presentation()) is not None:
                out.append(["damage", _presented(pres, dmg0)[0], _presented(pres, dmg)[0], round(pellets or 1)])
            else:
                out.append(["damage", round(dmg0), round(dmg), round(pellets or 1)])
        spread0, spread = pair("Spread")
        if spread is not None and (accuracy := _accuracy(inv, spread0, spread)) is not None:
            out.append(["accuracy", *accuracy])
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
    if (level := try_(lambda: _element_levels.get(inv))) is None:  # (static per item: read once)
        level = try_(lambda: games.GAME.items.element_level(inv, kind), 0) or 0
        try_(lambda: _element_levels.put(inv, level))  # (an object it can't key - the offline check's fakes: read each time)
    if level:
        out.append(["elementLevel", level, level])
    elif kind == "grenade":
        dmg0, dmg = pair("GrenadeDamage")
        if dmg:
            out.append(["damage", round(dmg0), round(dmg)])
        radius0, radius = pair("BlastRadius")
        if radius:  # uu -> m (1 uu = 1 cm, measured: tools/probes/probe_scale.py)
            out.append(["blastRadius", round(radius0 / 100, 1), round(radius / 100, 1)])
        fuse0, fuse = pair("FuseTime")
        if fuse:
            out.append(["fuse", round(fuse0, 2), round(fuse, 2)])
    return out


_rounding_logged: set[str] = set()  # attribute presentations' rounding modes not handled, already logged
ACCURACY_PRESENTATION = "GD_AttributePresentation.Weapons.AttrPresent_WeaponSpread"  # the card's "Accuracy" (both games)
_accuracy_pres: list[Any] = []  # [the presentation, or None]: found once


def _presented(pres: Any, value: float) -> tuple[float, int]:
    """A value rounded as its attribute presentation shows it: (value, decimals). RoundingMode ATTRROUNDING_IntRound
    -> a whole number (half away from zero, not Python's to-even); ATTRROUNDING_IntCeil -> rounded up; ATTRROUNDING_Float
    (the accuracy's) or unset -> the game's decimals (games.GAME.items.presented_decimals: BL2's FloatPrecision);
    another mode: logged once, those decimals meanwhile (not guessed)."""
    mode = str(getattr(try_(lambda: pres.RoundingMode), "name", "") or "")
    if mode == "ATTRROUNDING_IntRound":
        return math.floor(abs(value) + 0.5) * (1 if value >= 0 else -1), 0
    if mode == "ATTRROUNDING_IntCeil":  # (up to the next whole number: a projectile's damage - probe_bl1_cards.txt)
        return math.ceil(value), 0
    if mode not in ("", "ATTRROUNDING_Float") and mode not in _rounding_logged:
        _rounding_logged.add(mode)
        log(f"item card stat rounding not handled: {mode} ({try_(lambda: pres._path_name(), '?')})")
    decimals = try_(lambda: games.GAME.items.presented_decimals(pres), 0) or 0  # (each game's)
    return round(value, decimals), decimals


def _remapped(pres: Any, value: float, inv: Any) -> float | None:
    """A value through its presentation's RemappingData (bValueRemappingEnabled): InputValueMn..Mx onto
    OutputValueMn..Mx, linearly - each bound an AttributeInitializationData (amounts' evaluation; the accuracy's:
    0..15 onto 100..0, both games' Startup.upk). Not clamped (whether the game clamps: not known). None without it."""
    if not try_(lambda: bool(pres.bValueRemappingEnabled), False):
        return None
    data = try_(lambda: pres.RemappingData)
    ctx = amounts._Ctx(inv, None, 1)  # noqa: SLF001 - (the pickup amounts' evaluator: constants, formulas, attributes)
    bounds = [amounts._data(try_(lambda n=name: getattr(data, n)), ctx, 0)  # noqa: SLF001
              for name in ("InputValueMn", "InputValueMx", "OutputValueMn", "OutputValueMx")] if data is not None else []
    if len(bounds) != 4 or any(b is None for b in bounds) or bounds[1] == bounds[0]:
        return None
    in_mn, in_mx, out_mn, out_mx = bounds
    return out_mn + (value - in_mn) * (out_mx - out_mn) / (in_mx - in_mn)


_damage_pres: list[Any] = []  # the game's damage presentation (its profile's), looked up once


def _damage_presentation() -> Any:
    """The weapon card damage's attribute presentation, if the game has one for it (games.GAME.damage_presentation)."""
    if not _damage_pres:
        path = games.GAME.damage_presentation
        _damage_pres.append(try_(lambda: unrealsdk.find_object("AttributePresentationDefinition", path)) if path else None)
    return _damage_pres[0]


def _accuracy(inv: Any, spread0: float | None, spread: float) -> list[Any] | None:
    """A weapon's card Accuracy (72.1 for a shotgun's Spread 4.19 - tools/probes/probe_accuracy.txt): its spread through
    the "Accuracy" presentation's remapping, rounded as it says -> [card (from SpreadBaseValue), with the owner's
    bonuses (Spread), decimals], or None (no presentation / remapping)."""
    if not _accuracy_pres:
        _accuracy_pres.append(try_(lambda: unrealsdk.find_object("AttributePresentationDefinition", ACCURACY_PRESENTATION)))
    pres = _accuracy_pres[0]
    if pres is None:
        return None
    card, now = _remapped(pres, spread0 if spread0 is not None else spread, inv), _remapped(pres, spread, inv)
    if card is None or now is None:
        return None
    (card, decimals), (now, _) = _presented(pres, card), _presented(pres, now)
    return [card, now, decimals]


def _ui_stats(inv: Any) -> list[list[Any]]:
    """An item's card stats as the game's card shows them (a shield's Capacity 53, Recharge Rate 16, Recharge Delay
    2.36 - tools/probes/probe_shield.txt): WillowItem.UIStatModifiers[] = {AttributePresentation, ModifierTotal (53.059...)},
    the presentation's Description the label (the game's text) and its rounding the value's (_presented).
    -> [[label, value, decimals]]. The same property in both games (WillowGame.upk)."""
    out: list[list[Any]] = []
    for entry in try_(lambda: list(inv.UIStatModifiers), []) or []:
        pres = try_(lambda e=entry: e.AttributePresentation)
        value = _num(try_(lambda e=entry: e.ModifierTotal))
        label = try_(lambda p=pres: str(p.Description), "") if pres is not None else ""
        if not label or value is None:
            continue
        out.append([label, *_presented(pres, value)])
    return out


def _localized(obj: Any, grade: int) -> str:
    """The game's own display text for a definition, in the game's language ("" if it has none).

    Localized properties (see the repo's .agent/notes.md): name parts' PartName, weapon types'
    Typename, item definitions' ItemName, manufacturers' Grades[grade].DisplayName. HTML entities decoded, as the
    game's (Scaleform, HTML) text fields show them: "S&amp;S Munitions" (the page escapes what it shows itself).
    """
    for prop in ("PartName", "Typename", "ItemName"):
        text = try_(lambda p=prop: str(getattr(obj, p)), "")
        if text and text != "None":  # ("None": an unset name, not a name - the Pre-Sequel's Tediore laser type has none)
            return html.unescape(text)
    grades = try_(lambda: list(obj.Grades), [])
    if grades:
        grade_data = grades[grade] if 0 <= grade < len(grades) else grades[0]
        return html.unescape(try_(lambda: str(grade_data.DisplayName), "") or "")
    return ""


_type_names: dict[str, str] | None = None  # WeaponType enum name -> the name the game's weapon types give it


def _type_name(weapon_type_def: Any) -> str:
    """A weapon type definition with no Typename of its own (the Pre-Sequel's WT_Tediore_Laser - the other makers' lasers:
    "Laser"): the name the game's other weapon types of the same WeaponType give (WT_Laser), from the loaded
    WeaponTypeDefinitions - the ones not named in full (bTypeNameIsFullName: a vehicle's gun, "Moon Buggy Light Laser")
    - the most common; read once. "" if none."""
    global _type_names  # noqa: PLW0603
    if _type_names is None:
        counts: dict[str, dict[str, int]] = {}
        for d in try_(lambda: list(unrealsdk.find_all("WeaponTypeDefinition", exact=False)), []) or []:
            if try_(lambda d=d: bool(d.bTypeNameIsFullName), False):
                continue
            enum = _enum_name(try_(lambda d=d: d.WeaponType, ""))
            text = str(try_(lambda d=d: d.Typename, "") or "")
            if enum and text and text != "None":
                counts.setdefault(enum, {})[text] = counts.setdefault(enum, {}).get(text, 0) + 1
        _type_names = {enum: max(names, key=names.get) for enum, names in counts.items()}
    return _type_names.get(_enum_name(try_(lambda: weapon_type_def.WeaponType, "")), "")


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
        if slot == "WeaponType" and not text:  # (no name of its own: its weapon type's, from the game's others)
            text = try_(lambda o=obj: _type_name(o), "") or ""
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
        "l": try_(lambda: games.GAME.items.card_level(inv, int(inv.ExpLevel)), 0),  # (the card's: each game's)
        "v": try_(lambda: int(inv.MonetaryValue), 0),
        "e": equipped,
        "stats": _stats(inv, kind),
        # its card's stats, the game's labels - the kinds whose card lists them (games.GAME.ui_stat_kinds: a shield)
        **({"ui": ui} if kind in games.GAME.ui_stat_kinds and (ui := _ui_stats(inv)) else {}),
    }
    if card := _card_lines(inv, kind):
        item["card"] = card
    item.update(card_keys(inv, kind))
    if kind == "weapon" and "el" in item:
        # its element's damage per second (StatusEffectDamage: 76.3 on a shock pistol)
        item["edps"] = round(try_(lambda: float(inv.StatusEffectDamage), 0.0), 1)
        # its colour: its card line's TextColor (the page picks it); without one, the damage type's HUDDamageColor
        # (the hit markers' colour, never on a card: the fallback)
        damage_type = next(iter(try_(lambda: list(inv.InstantHitDamageTypeDefinitions), []) or []), None)
        colour = try_(lambda: damage_type.HUDDamageColor) if damage_type is not None else None
        if damage_type is not None and (enum := _enum_name(try_(lambda: damage_type.DamageType, ""))):
            games.GAME.items.learn_element(enum, item["el"])  # (its card frame next to its damage type: each game's)
        if damage_type is not None and (name := _element_name(damage_type, ctrl or get_pc())):
            item["eln"] = name  # the game's name for it ("shock": its localization)
        if colour is not None:
            rgb = tuple(try_(lambda c=c: int(getattr(colour, c)), 0) for c in ("R", "G", "B"))
            if any(rgb):
                item["ecol"] = "#%02x%02x%02x" % rgb
    item["parts"] = _parts(inv, item)
    if code := gibbed_code(inv):
        item["gib"] = code  # (the Details fold: copyable)
    if kind == "weapon" and (slot := try_(lambda: int(inv.QuickSelectSlot), 0)):
        item["slot"] = slot
    return item


def _cached_item(cache: _ItemCache, inv: Any, equipped: bool) -> dict[str, Any] | None:
    """An item's card from the cache - else built, if the pass has time left (ITEMS_SECONDS; at least one per pass);
    None: left for the next pass (players_complete says so)."""
    if (record := cache.get(inv)) is not None:
        return record
    if _later():
        return None
    _items_pass["built"] += 1
    return cache.put(inv, _item(inv, equipped))


def _later() -> bool:
    """The pass's budget spent (at least one thing built): what's not cached yet is left for the next pass."""
    if _items_pass["built"] and time.perf_counter() > _items_pass["deadline"]:
        _items_pass["left"] = True
        _items_pass["skipped"] += 1
        return True
    return False


def players_complete() -> bool:
    """Whether the last read_players built every card it met (else: some left for the next pass)."""
    return not _items_pass["left"]


def _equipped_item(inv: Any) -> dict[str, Any] | None:
    """An equipped item: static data from the cache, stats (owner's bonuses) and slot read now (None: its card left
    for the next pass)."""
    if (static := _cached_item(_equipped_cache, inv, True)) is None:
        return None
    item = {**static, "stats": _stats(inv, static["k"])}
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
            if (item := _equipped_item(inv) if equipped else _item(inv, equipped)) is not None:
                out.append(item)
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
                if (item := _equipped_item(inv)) is not None:
                    equipped.append(item)
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
            if (item := _cached_item(_backpack_cache, inv, False)) is not None:
                backpack.append(item)
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


GROUND_GEAR = {"weapon", "shield", "grenade", "classmod", "relic"}  # pickups whose item gets its card (+ customization)


def is_gear(inv: Any) -> bool:
    """Real gear (a weapon, shield... a skin / head): what the page shows a card for (model.js GEAR_CLASSES)."""
    return _kind(inv) in GROUND_GEAR or "CustomizationItem" in str(inv.Class.Name)


def ground_item(inv: Any, build: bool = True) -> tuple[dict[str, Any] | None, bool]:
    """(a gear pickup's item record, whether it was built now). The backpack's own record: an item dropped / picked up
    is the same object - the same address, the same record (built once, whichever came first; the page finds it by id
    in either). Not read yet and `build` False: (None, False) - the collector builds a few per update."""
    if (record := _backpack_cache.get(inv)) is not None:
        return record, False
    if not build:
        return None, False
    return _backpack_cache.put(inv, _item(inv, False)), True


def _static_info(obj: Any, fn) -> dict[str, Any]:  # noqa: ANN001
    key = obj._get_address()
    if key not in _static:
        _static[key] = fn(obj)
    return _static[key]


_stats_cache: dict[tuple[int, int, int], list[dict[str, Any]]] = {}  # (skill def, grade, player level) -> its lines


def _skill_stats(sd: Any, ctrl: Any, grade: int) -> list[dict[str, Any]]:
    """A skill's tooltip stats at a grade, as the game computes them (tools/probes/probe_skill_stats2.txt):
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
    # (a players pass's budget, the cards': a first tree is ~100 calls - 90 ms in one pass, a player joining)
    if _later():
        return []
    _items_pass["built"] += 1
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
    Its text (tools/probes/probe_weapon_card2.txt): the Description (a $NUMBER$ placeholder), else NoConstraintText
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
    if item is not None and (shown := try_(lambda: games.GAME.items.card_line_value(entry, p, item))) is not None:
        line["dv"], line["dp"] = shown  # the number as the game shows it (its profile's card_line_value)
    elif item is not None and (current := _attribute_value(item, try_(lambda: p.Attribute))) is not None:
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


# A damage type's item card element frame (DamageType enum name -> "shock", "fire"...), learned from the weapons read
# (their ElementalFrame next to their damage type): the frames are the enum's names in lower case but Incendiary's
# ("fire" - notes.md; the card's sprite isn't in the enum's order: no index to go by) - not written down here, seen on
# the game's own items, and remembered (.cache/element_frames.json: once a fire weapon's been seen, in any session).
# Until one is seen: the enum's name.
FRAMES_FILE = paths.DATA / ".cache" / "element_frames.json"


def _load_frames() -> dict[str, str]:
    try:
        data = json.loads(FRAMES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


_element_frames: dict[str, str] = _load_frames()


def learn_frame(enum: str, frame: str) -> None:
    """A weapon's damage type next to its card frame: kept, and saved when it's new."""
    if not enum or not frame or _element_frames.get(enum) == frame:
        return
    _element_frames[enum] = frame
    try:
        FRAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
        FRAMES_FILE.write_text(json.dumps(_element_frames, sort_keys=True), encoding="utf-8")
    except OSError as ex:
        log_error("element frames", ex)


def element_frame(enum: str) -> str:
    """A damage type's card frame ("" for none): each game's way (games.GAME.items.damage_type_frame). The one place a damage
    type becomes its icon's frame (element_of, the collector's update of an object's "el")."""
    return games.GAME.items.damage_type_frame(enum)


def learned_frame(enum: str) -> str:
    """BL2's damage type frame: learned from the weapons seen (learn_frame), else the enum's name in lower case ("" for
    none) - games.GAME.items.damage_type_frame. Another source (another enum, a mapping found in the game's data) replaces
    this function's body, nothing else."""
    frame = _element_frames.get(enum) or _ENUM_FRAMES.get(enum) or enum.removeprefix("DAMAGE_TYPE_").lower()
    return "" if frame in ("", "none", "normal", "unknown") else frame
_explosions: dict[int, dict[str, Any]] = {}  # object definition address -> its explosion's element ({} none), static


def element_of(damage_type: Any, ctrl: Any = None) -> dict[str, str]:
    """A damage type's element for the page, as an item's: {"el": its card icon's frame, "eln": the game's name for it,
    "ecol": its HUDDamageColor} - those it has (a plain damage type: none)."""
    enum = _enum_name(try_(lambda: damage_type.DamageType, ""))
    out: dict[str, str] = {}
    if frame := element_frame(enum):
        out["el"] = frame
        out["et"] = enum  # (its damage type: the collector updates "el" once its frame's learned)
    if name := _element_name(damage_type, ctrl or get_pc()):
        out["eln"] = name
    colour = try_(lambda: damage_type.HUDDamageColor)
    rgb = tuple(try_(lambda c=c: int(getattr(colour, c)), 0) for c in ("R", "G", "B")) if colour is not None else ()
    if any(rgb):
        out["ecol"] = "#%02x%02x%02x" % rgb
    return out


# Behaviours that hand an interactive object's own loot out (its Loot / balance's lists): a container's
_LOOT_GIVERS = {"Behavior_AttachItems", "Behavior_DropItems", "Behavior_SpawnLootAroundPoint", "Behavior_SpawnLootAtPoints"}
_buffs: dict[int, int] = {}  # object definition address -> 2 skill + own item, 1 skill, 0 neither (buff_info), static


def _behavior_classes(definition: Any) -> set[str]:
    """Its definition's behaviours' classes (BehaviorProviderDefinition.BehaviorSequences[].BehaviorData2[].Behavior)."""
    found: set[str] = set()
    for seq in try_(lambda: list(definition.BehaviorProviderDefinition.BehaviorSequences), []) or []:
        for data in try_(lambda s=seq: list(s.BehaviorData2), []) or []:
            if (behavior := try_(lambda d=data: d.Behavior)) is not None:
                found.add(try_(lambda b=behavior: str(b.Class.Name), ""))
    return found


def buff_info(definition: Any, lootable: bool = False) -> bool:
    """A buff you use, not a container: its behaviours activate a skill (Behavior_ActivateSkill), none hands its own
    loot out (_LOOT_GIVERS), and it spawns an item of its own (Behavior_SpawnItems: the Pre-Sequel's Moxxtails' drink -
    all 8, the Ammo one's balance with no loot list) or has loot (`lootable`: a leftover chest list, never dropped - the
    Moxxtails', BL2's Tiny Tina shrines': 6 of 7, the Ammo shrine none). Isaiah's strongbox activates one too but drops
    its loot: a container; the other skill objects (a switch console, the Space Hurps, BL2's whiskey barrel...) spawn
    nothing, have no loot. Per definition, once (the behaviours; `lootable` on top)."""
    key = definition._get_address()
    if key not in _buffs:
        classes = _behavior_classes(definition)
        skill = "Behavior_ActivateSkill" in classes and not classes & _LOOT_GIVERS
        _buffs[key] = 2 if skill and "Behavior_SpawnItems" in classes else 1 if skill else 0
    return _buffs[key] == 2 or (_buffs[key] == 1 and lootable)


def explosion_info(definition: Any, ctrl: Any = None) -> dict[str, Any]:
    """An interactive object that explodes (a barrel): its definition's behaviours hold a Behavior_Explode
    (games.GAME.objects.behaviors - BL2: BehaviorProviderDefinition.BehaviorSequences[].BehaviorData2[].Behavior - the
    Pre-Sequel's barrels: bBarrelSource;
    the air dome generator, with health too: no behaviours) -> {"xp": 1, its explosion's element (element_of:
    Behavior_Explode.Definition.DamageTypeDef)}, {} if it doesn't. Per definition, once (static data)."""
    key = definition._get_address()
    if key not in _explosions:
        found: dict[str, Any] = {}
        for behavior in try_(lambda: games.GAME.objects.behaviors(definition), []) or []:  # (each game's way)
            if try_(lambda b=behavior: str(b.Class.Name), "") == "Behavior_Explode":
                damage_type = try_(lambda b=behavior: b.Definition.DamageTypeDef)
                found = {"xp": 1, **(element_of(damage_type, ctrl) if damage_type is not None else {})}
                break
        _explosions[key] = found
    return _explosions[key]


_discoverable: dict[int, bool] = {}  # object definition address -> discoverable's, static


def discoverable(definition: Any) -> bool:
    """A level challenge object a player discovers (a Vault symbol): its definition's behaviours hold a
    Behavior_DiscoverLevelChallengeObject (games.GAME.objects.behaviors - tools/probes/probe_discovery.txt: IO_VaultRoy's,
    IO_Telescope's, the treasure chests'). Per definition, once (static data)."""
    key = definition._get_address()
    if key not in _discoverable:
        _discoverable[key] = any(try_(lambda b=behavior: str(b.Class.Name), "") == "Behavior_DiscoverLevelChallengeObject"
                                 for behavior in try_(lambda: games.GAME.objects.behaviors(definition), []) or [])
    return _discoverable[key]


_plants: dict[int, dict[str, Any]] = {}  # object definition address -> plant_info's ({} not a plant), static


def _plant_damage_type(definition: Any) -> Any:
    """An elemental plant's damage type, where the game has it (each plant its own way - offline, both games' packages):
    a behaviour's - Behavior_Explode.Definition.DamageTypeDef (BL2's Firemelon), Behavior_FireBeam.DamageTypeDefinition
    (the Shock Cactus), the Behavior_SpawnProjectile's projectile's own Behavior_Explode (the Acidolus: its sack) - else
    its damage areas' (WillowDamageArea objects inside the definition, DamageTypeDefinition: the Pre-Sequel's Cryo Vine -
    no damage behaviour). None if none."""
    def from_behaviors(provider: Any, depth: int = 0) -> Any:
        for seq in try_(lambda: list(provider.BehaviorSequences), []) or []:
            for data in try_(lambda s=seq: list(s.BehaviorData2), []) or []:
                b = try_(lambda d=data: d.Behavior)
                kind = try_(lambda b=b: str(b.Class.Name), "") if b is not None else ""
                found = (try_(lambda b=b: b.Definition.DamageTypeDef) if kind == "Behavior_Explode"
                         else try_(lambda b=b: b.DamageTypeDefinition) if kind == "Behavior_FireBeam"
                         else from_behaviors(try_(lambda b=b: b.ProjectileDefinition.BehaviorProviderDefinition), depth + 1)
                         if kind == "Behavior_SpawnProjectile" and depth < 2 else None)
                if found is not None:
                    return found
        return None
    if (found := from_behaviors(try_(lambda: definition.BehaviorProviderDefinition))) is not None:
        return found
    key = definition._get_address()
    for area in try_(lambda: list(unrealsdk.find_all("WillowDamageArea", exact=False)), []) or []:
        if try_(lambda a=area: a.Outer._get_address() == key, False) and (dt := try_(lambda a=area: a.DamageTypeDefinition)) is not None:
            return dt
    return None


def plant_info(definition: Any, ctrl: Any = None) -> dict[str, Any]:
    """An elemental plant (the game's own group: its definition's Allegiance Allegiance_ElementalPlant - BL2's Firemelon,
    Acidolus, Shock Cactus, the Pre-Sequel's Cryo Vines; nothing else has it): like a barrel, but shot empty it
    recharges instead of being destroyed - {"xp": 1, "plant": 1, its element (element_of: _plant_damage_type)}, {} if
    it isn't one. Per definition, once."""
    key = definition._get_address()
    if key not in _plants:
        found: dict[str, Any] = {}
        if try_(lambda: str(definition.Allegiance.Name), "") == "Allegiance_ElementalPlant":
            damage_type = try_(lambda: _plant_damage_type(definition))
            found = {"xp": 1, "plant": 1, **(element_of(damage_type, ctrl) if damage_type is not None else {})}
        _plants[key] = found
    return _plants[key]


# The game's own misspelling: its DamageType enum has DAMAGE_TYPE_Incindiary (both games' WillowGame.upk), its text
# the key Incendiary (WillowMenu.int [DamageTypes]) - never matched, fire weapons and barrels had no element name. The
# one correction, the user's call (not a name table: the text still comes from the game).
_ENUM_TEXT_KEYS = {"Incindiary": "Incendiary"}
# ...and its card frame: every element's is its enum's name in lower case (ice, shock, corrosive...) but that one's,
# "fire" (seen on the game's fire weapons: their ElementalFrame) - the same correction, so a fire barrel has its icon
# before a fire weapon's been read (the user's call). A frame learned from the game's items still goes first.
_ENUM_FRAMES = {"DAMAGE_TYPE_Incindiary": "fire"}


def _element_name(damage_type: Any, ctrl: Any) -> str:
    """An element's name as the game writes it, in its language: WillowMenu.int's [DamageTypes] section
    (Incendiary=incendiary, Shock=shock, Corrosive=corrosive, Explosive=explosive, Amp=slag - lower case: the game
    puts them in sentences, "%d" in its mission hints), keyed by the damage type's DamageType enum without its
    DAMAGE_TYPE_ prefix (DAMAGE_TYPE_Shock -> Shock). Object.Localize(section, key, package): a lookup of the
    loaded localization, called once per element (cached). "" if it has none (UE3's "?INT?...?" = missing)."""
    key = _enum_name(try_(lambda: damage_type.DamageType, "")).removeprefix("DAMAGE_TYPE_")
    key = _ENUM_TEXT_KEYS.get(key, key)
    if not key:
        return ""
    if key not in _element_names:
        text = str(try_(lambda: ctrl.Localize("DamageTypes", key, "WillowMenu"), "") or "") if ctrl is not None else ""
        _element_names[key] = "" if text.startswith("?") else text.strip()
    return _element_names[key]


def _element_chance(weapon: Any) -> list[float] | None:
    """A weapon's elemental effect chance, the card's way (tools/probes/probe_element_chance.txt): its element's base
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
    """An item's card lines, as the game's item card shows them (tools/probes/probe_weapon_card.txt): a weapon's
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


_card_keys_done = [0]  # steps done (_card_keys: one per players pass)


CARD_KEY_FINDS = (("manufacturer", "ManufacturerDefinition", "FlashLabelName"),
                  ("type", "WeaponTypeDefinition", "ScaleformFrameName"))


def _card_keys() -> None:
    """Once a session: the game's keys for the item card icons, from the loaded definitions - every manufacturer's
    FlashLabelName, every weapon type's ScaleformFrameName (gamecards.py picks the sprites labelled with them), the
    elements'. A step per call - per players pass (each find_all walks every object: all of them in one pass were
    74 ms, the first players pass's hitch)."""
    step = _card_keys_done[0]
    if step > len(CARD_KEY_FINDS):
        return
    _card_keys_done[0] += 1
    if step < len(CARD_KEY_FINDS):
        kind, cls, prop = CARD_KEY_FINDS[step]
        keys = {str(try_(lambda d=d: getattr(d, prop), "") or "") for d in try_(lambda c=cls: list(unrealsdk.find_all(c, exact=False)), []) or []
                if not d.Name.startswith("Default__")}
        assets.set_keys(kind, keys - {"", "None"})
        return
    # the elements': the damage types' DamageType enum, its names without DAMAGE_TYPE_ (Shock, Amp: slag...) - the
    # element list's frames ("shock", "amp"; a weapon's ElementalFrame picks one) - the enum's type from the class's
    # default object (a find_all only for it walked every object)
    default = try_(lambda: unrealsdk.find_class("WillowDamageTypeDefinition").ClassDefaultObject)
    enum = type(try_(lambda: default.DamageType)) if default is not None else None
    members = getattr(enum, "__members__", None) or {}
    assets.set_keys("element", {name.removeprefix("DAMAGE_TYPE_") for name in members} - {"", "MAX"})


def _skill_bonuses(pawn: Any) -> dict[str, int]:
    """The skill ranks the equipped items add (a class mod's "+2 Steady", blue in the skill screen:
    tools/probes/probe_skill_bonus.txt): an item's ItemCardModifierStats[] = {AttributePresentation, ModifierValue}
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
    bonuses = bonuses or {}
    # (a class mod swapped: the bonuses change, not the points)
    cache_key = (points, tuple(sorted((k, tuple(map(tuple, v))) for k, v in bonuses.items())))
    cached = _skills_cache.get(ctrl)
    # (unknown points - another player's on the host: the cached tree until its refresh time, not every pass)
    if cached is not None and cached[0] == cache_key and (points is not None or time.monotonic() < cached[2]):
        player.update(cached[1])
        return
    skipped = _items_pass["skipped"]
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
            **({"ic": ic} if (ic := skill_icon(d)) else {}),
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
    if _items_pass["skipped"] == skipped:  # (complete - else again at the next pass, its stats cached so far kept)
        _skills_cache.put(ctrl, (cache_key, result, time.monotonic() + SKILLS_UNKNOWN_EVERY))
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
        # ones (Krieg: "_Bloodlust" the stack counter, "FireStatusDetector"... - tools/probes/probe_skill_layout.txt).
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


_class_names = PerObject()  # controller / player info -> _class_name() (checked alive: util.PerObject)


def _class_name(ctrl: Any, pri: Any) -> dict[str, Any]:
    """_class_name_uncached(), once per player (a player's class never changes)."""
    owner = ctrl if ctrl is not None else pri
    if owner is None:
        return _class_name_uncached(ctrl, pri)
    if (cached := _class_names.get(owner)) is None:
        cached = _class_name_uncached(ctrl, pri)
        if cached.get("cls") and not cached.get("clsRaw"):  # only the game's name (not yet loaded: again next time)
            _class_names.put(owner, cached)
    return cached


def _class_name_uncached(ctrl: Any, pri: Any) -> dict[str, Any]:
    """{"cls": class, "char": character} - the game's localized class name ("Gunzerker" / "Défourailleur") and
    character name ("Salvador"), each game's way (games.GAME.pawns.class_name); else the class definition's
    object name, flagged made-up ("clsRaw")."""
    out = dict(try_(lambda: games.GAME.pawns.class_name(ctrl, pri), {}) or {})
    if out.get("cls"):
        return out
    raw = def_name(try_(lambda: ctrl.PlayerClass) if ctrl is not None else None)
    return {**out, "cls": raw, "clsRaw": 1} if raw else {**out, "cls": ""}


def class_identifiers(ctrl: Any, pri: Any) -> dict[str, Any]:
    """BL2's class / character names (games.GAME.pawns.class_name): the player info (shared with everyone: works for others on
    a client too) or the class definition points at the *character* (PlayerNameIdentifierDefinition: "Salvador"), whose
    CharacterClassId is the class (PlayerClassIdentifierDefinition: "Gunzerker") - seen in game. Those it has."""
    character = try_(lambda: pri.CharacterNameIdDef) or try_(lambda: ctrl.PlayerClass.CharacterNameId)
    class_id = try_(lambda: character.CharacterClassId)
    out: dict[str, Any] = {}
    if name := try_(lambda: str(character.LocalizedCharacterName), ""):
        out["char"] = name
    if text := try_(lambda: str(class_id.LocalizedClassNameNonCaps), ""):
        out["cls"] = text
    return out


def read_players(world_info: Any, me: Any, pc: Any = None) -> list[dict[str, Any]]:
    """Every player pawn in the level, with what can be read of their gear and skills."""
    for cache in (_backpack_cache, _equipped_cache):
        cache.sweep()  # the items destroyed since (sold, used, gone with a level)
    _items_pass.update(deadline=time.perf_counter() + ITEMS_SECONDS, built=0, left=False, skipped=0)
    players_parts.clear()

    def part(name: str, since: float) -> float:  # (this part's time; the next one starts now)
        now = time.perf_counter()
        players_parts[name] = players_parts.get(name, 0.0) + now - since
        return now

    players = []
    me_addr = addr(me) if me is not None else None
    # Who hosts: us unless we're a client (NetMode 3); then the party leader (the host's player info
    # has bIsPartyLeader on a client: tools/probes/probe_coop.txt)
    client = try_(lambda: int(world_info.NetMode), 0) == 3
    pawn = world_info.PawnList
    for _ in range(1000):
        if pawn is None:
            break
        try:
            # the class first (cheap): the player info (slow reads) only for players
            pri = player_info(pawn) if "PlayerPawn" in str(pawn.Class.Name) else None  # the vehicle's while driving
            if pri is None and me is not None and pc is not None and addr(pawn) == me_addr:
                # (ours without one: the controller's own - a driver pawn may have none in a vehicle, nor its seat:
                # tools/probes/probe_bl1_driving.txt - left out, the list lost us)
                pri = try_(lambda: pc.PlayerReplicationInfo)
            if pri is not None and not field(pawn, "bDeleteMe"):
                mark = time.perf_counter()
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
                mark = part("player", mark)
                _card_keys()
                mark = part("card keys", mark)
                _inventory(pawn, player)
                mark = part("inventory", mark)
                games.GAME.skills.read(ctrl, player, try_(lambda p=pawn: _skill_bonuses(p), {}))  # (each game's tree)
                part("skills", mark)
                players.append(player)
        except Exception as ex:  # noqa: BLE001
            log_error("inspect player", ex)
        pawn = try_(lambda p=pawn: field(p, "NextPawn"))
    _items_pass["deadline"] = float("inf")  # (the pass over: cards asked elsewhere are built)
    players.sort(key=lambda p: (not p["local"], p["n"].lower()))
    return players
