"""Small helpers shared by the game-side modules (collector, inspector)."""

import os
import time
import traceback
from pathlib import Path
from typing import Any

# Diagnostics (errors with tracebacks, slow tasks) also go here: the game console can't be copied.
# Kept across sessions (a crash doesn't lose it) until it grows past LOG_MAX_BYTES.
# HELIOS_TRACKER_LOG overrides the path (tools/offline_check.py: a temp file, not the real log)
LOG_FILE = Path(os.environ.get("HELIOS_TRACKER_LOG") or Path(__file__).with_name("helios_tracker.log"))
LOG_MAX_BYTES = 1_000_000


def log(message: str) -> None:
    """To the console and the log file (timestamped)."""
    print(f"[helios_tracker] {message}")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def start_log() -> None:
    """Called when the mod loads: marks the session, and starts over if the file got big."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.unlink()
    except OSError:
        pass
    log("---- loaded ----")


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


# (class address, property name) -> the property: looked up once per class. Cleared on every level
# change (clear_fields): the engine unloads packages then - a class freed, another one at its address,
# would get a stale property. The script classes read per update most likely stay loaded, but this
# doesn't rely on it
_fields: dict[tuple[int, str], Any] = {}


def clear_fields() -> None:
    """Forgets the looked-up properties (a level change: packages may have been unloaded)."""
    _fields.clear()


def field(obj: Any, name: str) -> Any:
    """obj.<name>, ~10x cheaper for the per-update reads: a property read by name costs 15-24 us (the
    name looked up through the class chain), the property looked up once then `_get_field` 1-2 us
    (tools/probe_perf.txt). Raises like obj.<name> if there's no such property. Plain Python objects
    (the offline check's fakes): getattr."""
    get = getattr(type(obj), "_get_field", None)
    if get is None:
        return getattr(obj, name)
    cls = obj.Class
    key = (cls._get_address(), name)
    prop = _fields.get(key)
    if prop is None:
        prop = _fields[key] = cls._find(name)
    return get(obj, prop)


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
PRESENTATION_KINDS = {"Credits": "cash", "Health": "health", "GrenadeAmmo": "ammo"}
# Per item definition (static game data, set when the item spawns - never changes): kind. Never
# cleared; keyed by definition, not by pickup (a destroyed pickup's address can be reused).
_pickup_kinds: dict[int, str] = {}


def pickup_kind(inv: Any) -> str:
    """ "ammo" / "cash" / "health" for a usable item (a non-gear pickup), "" for anything else.
    Weapons / gear / mission items aren't looked at; each definition is resolved once."""
    if inv is None or inv.Class.Name != "WillowUsableItem":
        return ""
    item_def = try_(lambda: inv.DefinitionData.ItemDefinition)
    if item_def is None:
        return ""
    key = item_def._get_address()
    if (kind := _pickup_kinds.get(key)) is None:
        name = try_(lambda: str(item_def.Presentation.Name), "")
        kind = _pickup_kinds[key] = "ammo" if name.startswith("WeaponAmmo_") else PRESENTATION_KINDS.get(name, "")
    return kind


def player_info(pawn: Any) -> Any:
    """A player pawn's PlayerReplicationInfo - its vehicle's while it drives one (the vehicle takes
    it over: seen in game, the driver pawn's is None meanwhile)."""
    return try_(lambda: pawn.PlayerReplicationInfo) or try_(lambda: pawn.DrivenVehicle.PlayerReplicationInfo)


def item_name(inv: Any) -> str:
    """An inventory item's name, in the game's language: its full name (weapons, gear), else its
    definition's ItemName - e.g. usable items (cash, ammo, health vials) have no full name."""
    if inv is None:
        return ""
    return (
        call_str(inv.GetShortHumanReadableName)
        or try_(lambda: str(inv.GeneratedItemName), "")
        or try_(lambda: str(inv.DefinitionData.ItemDefinition.ItemName), "")
    )


def addr(obj: Any) -> str:
    """Stable id of a live object (its address, hex) - also the page's marker ids."""
    return f"{obj._get_address():x}"
