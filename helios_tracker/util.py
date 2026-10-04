"""Small helpers shared by the game-side modules (collector, inspector)."""

import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .paths import DATA

# Diagnostics (errors with tracebacks, slow tasks) also go here: the game console can't be copied.
# Kept across sessions (a crash doesn't lose it) until it grows past LOG_MAX_BYTES.
# One per game (start_log: helios_tracker_bl2.log...): a dev install is one folder for every game (the junction).
# HELIOS_TRACKER_LOG overrides the path (tools/offline_check.py: a temp file, not the real log)
LOG_FILE = Path(os.environ.get("HELIOS_TRACKER_LOG") or DATA / "helios_tracker.log")
LOG_MAX_BYTES = 1_000_000


def log(message: str) -> None:
    """To the console and the log file (timestamped)."""
    print(f"[helios_tracker] {message}")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def start_log(game: str) -> None:
    """Called when the mod loads, with the game's key (games.GAME.key: "bl2", "tps"...): its own log and crash log
    (helios_tracker_bl2.log, helios_crash_bl2.log); marks the session, and starts over if the file got big."""
    global LOG_FILE, CRASH_FILE  # noqa: PLW0603 - (set once per load: the game is known by then)
    if not os.environ.get("HELIOS_TRACKER_LOG"):
        LOG_FILE = DATA / f"helios_tracker_{game}.log"
    CRASH_FILE = LOG_FILE.with_name(f"helios_crash_{game}.log")
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.unlink()
    except OSError:
        pass
    log("---- loaded ----")
    start_crash_log()


CRASH_FILE = LOG_FILE.with_name("helios_crash.log")
_CRASH_ATTR = "_helios_tracker_crash_log"  # sys attribute: the open file, across module reloads


def start_crash_log() -> None:
    """faulthandler: on a native crash (access violation...) the Python stack of every thread goes to
    helios_crash.log - the line that called into the game when it died (the game's own dump only
    shows "from Python"). The file stays open (faulthandler writes to it at the crash); a reload
    closes the previous one. Also written for exceptions the game handles itself (it keeps running):
    only the last entry before a crash matters."""
    import faulthandler  # noqa: PLC0415

    previous = getattr(sys, _CRASH_ATTR, None)
    try:
        f = CRASH_FILE.open("a", encoding="utf-8")
        f.write(f"---- {time.strftime('%Y-%m-%d %H:%M:%S')} loaded ----\n")
        f.flush()
        faulthandler.enable(file=f, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        return
    setattr(sys, _CRASH_ATTR, f)
    if previous is not None:
        try:
            previous.close()
        except OSError:
            pass


class ErrorLog:
    """Logs each distinct error once (per-frame code would flood the logs otherwise)."""

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def __call__(self, where: str, ex: BaseException) -> None:
        key = f"{where}: {type(ex).__name__}: {ex}"
        if key not in self._seen:
            self._seen.add(key)
            log(key + "\n" + "".join(traceback.format_exception(ex)).rstrip())


log_error = ErrorLog()


def try_(fn, default=None):  # noqa: ANN001, ANN201
    """fn(), or `default` if it raises (missing property, None in a chain, ...)."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


def _str_result(r: Any) -> str:
    """A string out of a call result: plain, or the first non-empty string of an out-param tuple."""
    if isinstance(r, str):
        return r
    if isinstance(r, tuple):
        return next((v for v in r if isinstance(v, str) and v), "")
    return ""


# Class address -> property name -> the property: looked up once per class. Cleared on every level
# change (clear_fields): the engine unloads packages then - a class freed, another one at its address,
# would get a stale property. The script classes read per update most likely stay loaded, but this
# doesn't rely on it
_fields: dict[int, dict[str, Any]] = {}  # class address -> property name -> property


# A level change: what's kept per level forgets it (the collector calls level_changed - _clear_contents). Each such cache
# registers its reset where it's defined (on_level_change): nothing works out by itself that the level changed (BL1's
# exits once did, by the area's name - stale after a save-quit-continue in the same area: profiles.md "Level changes").
_level_resets: list[Any] = []


def on_level_change(reset: Any) -> Any:
    """Registers a reset (a function, no arguments) to call at each level change; returns it."""
    _level_resets.append(reset)
    return reset


def level_changed() -> None:
    """A new level: every registered reset (one failing doesn't stop the others - logged)."""
    for reset in list(_level_resets):
        try:
            reset()
        except Exception as ex:  # noqa: BLE001
            log_error("level reset", ex)


def clear_fields() -> None:
    """Forgets the looked-up properties (a level change: packages may have been unloaded)."""
    _fields.clear()


on_level_change(clear_fields)


def _prop(cls: Any, props: dict[str, Any], name: str) -> Any:
    """The class's property `name`, looked up once - a missing one too: remembered as its error, raised again each
    time (BL2 has none of the Pre-Sequel's OxygenPool: its lookup through the class chain, ~100 us, ran for every
    player on every update - 12 % of the state update, tools/probes/probe_profile.txt)."""
    prop = props.get(name)
    if prop is None:
        try:
            prop = cls._find(name)
        except Exception as ex:  # noqa: BLE001
            prop = ex
        props[name] = prop
    if isinstance(prop, Exception):
        raise type(prop)(*prop.args)
    return prop


_struct_types: dict[type, bool] = {}  # Python type -> a WrappedStruct (its fields' owner: _type) - else a UObject (Class)


def _owner(obj: Any) -> Any:
    """Where obj's properties are found: a struct's type (WrappedStruct._type), an object's class - which one told by
    its Python type, once (a UObject's missing attribute would cost a by-name lookup each time)."""
    kind = type(obj)
    if (is_struct := _struct_types.get(kind)) is None:
        is_struct = _struct_types[kind] = hasattr(kind, "_type")
    return obj._type if is_struct else obj.Class


def reader(obj: Any) -> Any:
    """field() bound to one object: `get = reader(pawn); get("Location")`. Its class and the class's properties
    looked up once for all the reads - field()'s own overhead (obj.Class, its address, the cache key) was a third of
    the state update with 50 pawns ~10 reads each (tools/probes/probe_profile.txt). Plain Python objects: getattr."""
    get = getattr(type(obj), "_get_field", None)
    if get is None:
        return lambda name: getattr(obj, name)
    cls = _owner(obj)
    props = _fields.get(cls_key := cls._get_address())
    if props is None:
        props = _fields[cls_key] = {}

    def read(name: str) -> Any:
        return get(obj, _prop(cls, props, name))

    return read


class PerObject:
    """Values by a game object (its address), each kept with a WeakPointer to it: an entry whose object is gone -
    destroyed, even with another object at its address since - is never returned (inspector._ItemCache's way). For the
    caches keyed by a controller / player info: a new character's controller at a freed one's address got the old one's
    skill tree (the audit, 2026-10-03 - profiles.md "Caches")."""

    def __init__(self) -> None:
        self._entries: dict[int, tuple[Any, Any]] = {}

    def get(self, obj: Any) -> Any:
        entry = self._entries.get(obj._get_address())
        return entry[1] if entry is not None and entry[0]() is not None else None

    def put(self, obj: Any, value: Any) -> Any:
        from unrealsdk.unreal import WeakPointer  # noqa: PLC0415 - (util: no SDK at module level - release.py)

        self._entries[obj._get_address()] = (WeakPointer(obj), value)
        return value


def field(obj: Any, name: str) -> Any:
    """obj.<name>, ~10x cheaper for the per-update reads: a property read by name costs 15-24 us (the
    name looked up through the class chain), the property looked up once then `_get_field` 1-2 us
    (tools/probes/probe_perf.txt). Objects and structs (a WrappedStruct: its _type's fields - the stubs: "look up
    the UField beforehand via struct._type._find(), then pass it to _get_field"). Raises like obj.<name> if there's no
    such property. Plain Python objects (the offline check's fakes): getattr."""
    get = getattr(type(obj), "_get_field", None)
    if get is None:
        return getattr(obj, name)
    cls = _owner(obj)
    props = _fields.get(cls_key := cls._get_address())
    if props is None:
        props = _fields[cls_key] = {}
    return get(obj, _prop(cls, props, name))


def call_str(fn) -> str:  # noqa: ANN001
    """The string fn() gives - trying fn() then fn("") (a string out param, e.g.
    GetTargetName(out string TargetName)): the first non-empty one. fn() can succeed and return
    nothing when the text only comes back through the out param."""
    for args in ((), ("",)):
        try:
            if text := _str_result(fn(*args)):
                return text
        except Exception:  # noqa: BLE001, S112 - TypeError: wrong arguments; anything else: try the next
            continue
    return ""


def def_name(obj: Any) -> str:
    """ "CharClass_Bullymong" / a definition object -> a readable-ish name from its object name."""
    if obj is None:
        return ""
    name = str(obj.Name)
    for prefix in ("CharClass_", "CharacterClass_", "InteractiveObj_", "IO_", "Class_"):
        name = name.removeprefix(prefix)
    return name.replace("_", " ")


def named(game_text: str, *fallbacks: str) -> dict[str, Any]:
    """{"n": name} - the game's own text if any, else the first fallback plus "raw": 1 (a
    made-up name from an object / class name: the page formats it and marks it as a guess).
    Not "r": that's the pawns' rotation in the state payload."""
    if game_text:
        return {"n": game_text}
    return {"n": next((f for f in fallbacks if f), "?"), "raw": 1}


def exp_level(obj: Any) -> int:
    """Level of a pawn / vehicle / item: GetExpLevel(), else its ExpLevel property (0 if none)."""
    for fn in (lambda: obj.GetExpLevel(), lambda: obj.ExpLevel):
        level = try_(fn)
        if isinstance(level, int) and level > 0:
            return level
    return 0


# A usable item's kind, by its definition's inventory card (Presentation): the game's own grouping
# (probe_pickups.py: GD_InventoryPresentations.Definitions.Credits / Health / WeaponAmmo_* / GrenadeAmmo)
PRESENTATION_KINDS = {"Credits": "cash", "Health": "health", "GrenadeAmmo": "ammo", "Oxygen": "oxygen"}
# ("Oxygen": the Pre-Sequel's Oxygen Canister - GD_BuffDrinks.A_Item.BuffDrink_OxygenInstant, presentation
# GD_InventoryPresentations.Definitions.Oxygen, icon fx_shared_items.Textures.OxygenCannister_Particle - Startup.upk)
# The "Credits" presentation is shared by every currency: the definition's FormOfCurrency tells them
# apart (seen in game, tools/probes/probe_eridium.py: GD_Currency.A_Item.EridiumStick = CURRENCY_Eridium).
# Other currencies (not seen yet: Seraph crystals, Torgue tokens...) stay "other".
CURRENCY_KINDS = {"CURRENCY_Credits": "cash", "CURRENCY_Eridium": "eridium"}
# Per item definition (static game data, set when the item spawns - never changes): kind. Never
# cleared; keyed by definition, not by pickup (a destroyed pickup's address can be reused).
_pickup_kinds: dict[int, str] = {}


def pickup_kind(inv: Any) -> str:
    """ "ammo" / "cash" / "eridium" / "health" / "oxygen" for a usable item (a non-gear pickup), "mission" for a
    mission item (WillowMissionItem: ECHO logs, Princess Fluffybutt... - tools/probes/probe_pickups.txt), ""
    for anything else. Weapons / gear aren't looked at; each definition is resolved once."""
    if inv is None:
        return ""
    if inv.Class.Name == "WillowMissionItem":
        return "mission"
    if inv.Class.Name != "WillowUsableItem":
        return ""
    item_def = try_(lambda: inv.DefinitionData.ItemDefinition)
    if item_def is None:
        return ""
    key = item_def._get_address()
    if (kind := _pickup_kinds.get(key)) is None and try_(lambda: bool(item_def.bMissionItem), False):
        # a mission item as a usable item - its definition says so (Borderlands 1's: no WillowMissionItem class -
        # Z0_MissionData's ID_SpareVendingPart "Power Coupling": bMissionItem, the MissionObject presentation)
        kind = _pickup_kinds[key] = "mission"
    if kind is None:
        name = try_(lambda: str(item_def.Presentation.Name), "")
        kind = "ammo" if name.startswith("WeaponAmmo_") else PRESENTATION_KINDS.get(name, "")
        if kind == "cash":
            currency = getattr(try_(lambda: item_def.FormOfCurrency), "name", "CURRENCY_Credits")
            kind = CURRENCY_KINDS.get(currency, "")
        _pickup_kinds[key] = kind
    return kind


# The game's rarity per RarityLevel: its colour entry and colour (games.py rarity_table: each game's own way)
_rarity: dict[str, list[Any]] = {}


def rarity_table() -> dict[str, list[Any]]:
    """{"level": [colour entry index, "#rrggbb"]} for the rarity levels the game colours (read once:
    static game data; again later while the globals aren't loaded)."""
    if _rarity:
        return _rarity
    import unrealsdk  # noqa: PLC0415 - game only

    from . import games  # noqa: PLC0415

    globals_def = try_(lambda: unrealsdk.find_object("GlobalsDefinition", "GD_Globals.General.Globals"))
    if globals_def is None:
        return {}
    _rarity.update(try_(lambda: games.GAME.rarity_table(globals_def), {}) or {})
    return _rarity


def player_info(pawn: Any) -> Any:
    """A player pawn's PlayerReplicationInfo - its vehicle's while it drives one (the vehicle takes
    it over: seen in game, the driver pawn's is None meanwhile)."""
    return try_(lambda: pawn.PlayerReplicationInfo) or try_(lambda: pawn.DrivenVehicle.PlayerReplicationInfo)


def item_name(inv: Any) -> str:
    """An inventory item's name, in the game's language: its full name (weapons, gear), else its
    definition's ItemName - e.g. usable items (cash, ammo, health vials) have no full name. Mission
    items name themselves by their class's generic MissionItemString ("Mission Item" - tools/
    probe_pickups.txt: an ECHO log): their definition's ItemName then ("Data Log")."""
    if inv is None:
        return ""
    own = try_(lambda: str(inv.DefinitionData.ItemDefinition.ItemName), "")
    short = call_str(inv.GetShortHumanReadableName)
    if short and own and short == try_(lambda: str(inv.MissionItemString), ""):
        return own
    return short or try_(lambda: str(inv.GeneratedItemName), "") or own


def addr(obj: Any) -> str:
    """Stable id of a live object (its address, hex) - also the page's marker ids."""
    return f"{obj._get_address():x}"
