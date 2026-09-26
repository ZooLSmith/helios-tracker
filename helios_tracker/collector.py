"""
Game side: reads the current level and what's in it, and publishes plain JSON to the Hub.

Runs on the game thread only (from the PostRender hook). Nothing here is kept across frames except
WeakPointers; the map image extraction goes to a background thread, which only reads files.

World -> map (verified in game on Sanctuary and Southern Shelf, fits within 0.07 movie px):
    c = volume.BrushComponent.Bounds.Origin, upp = volume.UnrealUnitsPerPixel * 4
    movie x = (Y - c.Y) / upp, movie y = -(X - c.X) / upp      (world +X = map up, +Y = right)
The page does the conversion; the level payload carries c, upp and the volume's north offset.
"""

import json
import math
import sys
import struct
import threading
import time
from pathlib import Path
from typing import Any

import unrealsdk
import mods_base
from mods_base import ENGINE, get_pc
from unrealsdk.unreal import WeakPointer

from .amounts import pickup_amount
from .inspector import buff_info, element_frame, explosion_info, ground_item, is_gear, plant_info, read_players
from . import lootodds
from .missions import MissionLog, mission_id
from .missions import objective_index as _mission_index
from .shops import ShopReader
from .skills import SkillReader
from .server import Hub
from .tacmap import MapFog, MapImage, load_fog, load_tactical_map
from .util import (addr, call_str, clear_fields, def_name, exp_level, field, item_name, log, log_error, named,
                   pickup_kind, player_info, rarity_table, reader, try_)

MOVIE_SCALE = 4  # movie px per volume "pixel": UnrealUnitsPerPixel is 32, the fit gave 128 uu / px
LEVEL_CHECK_EVERY = 1.0  # s
SCAN_EVERY = 120.0  # s between full pickup scans: a safety net, new ones come from the spawn hook
                    # (each find_all walks every object in the game: ~10 ms, a hitch - measured)
ITEMS_PER_UPDATE = 1  # gear pickups' item records built per state update (function calls, parts: a few ms each)
HEALTH_EVERY = 4  # updates between health reads of a pawn (function calls: the costly part of an update)
OBJECTS_EVERY = 120.0  # s between full interactive object scans: a safety net (~11 ms); objects that
                       # spawn / get their balance / are destroyed later come from hooks
PLAYERS_EVERY = 2.0  # s between player inspections (gear, backpack, skills)
MISSIONS_EVERY = 1.0  # s between quest marker reads (owners can move: escorts, NPCs); also the
                      # mission log's fast pass (the tracked / active missions only)
MISSION_LOG_EVERY = 5.0  # s between full mission log passes (every mission's status: ~290 entries)
MAX_PAWNS = 1000  # PawnList walk guard
VIDEO_GAP = 2.0  # s without a tick: the frames stopped - a video played (ticks: at least 1 per s otherwise)
VIDEO_SPARE = 5.0  # s past a video's length: over even if the frames never stopped
SCENE_RECHECK = 1.0  # s: an in-engine cutscene's Matinees - how long they still play - read this often
SCENE_DRIFT = 0.5  # s: the page's count this far from the scene's real position - sent again
AREAS_EVERY = 1.0  # s between reads of the discovered areas (pc.DiscoveredWorldAreas: ~50 structs)
LOOTED_EVERY = 1.0  # s between checks of unlooted containers (two property reads each, round robin)
LOOTED_PER_PASS = 60
SHOPS_EVERY = 2.0  # s between vending machine reads (their stock: new items only after a sale / restock)
SHOPS_RETRY = 0.1  # s: item records left to build (a few ms per pass) - the next pass this soon
SLOW_MS = 4.0  # a task taking longer than this on the game thread is reported (it can cause a hitch)
RECORDS_SECONDS = 0.002  # per tick, building the records of newly found interactive objects (a scan's backlog)
INCOMPLETE_EVERY = 1.0  # s between retries of object records built before their definition arrived
SLOW_REPORT_EVERY = 30.0  # s between console reports of slow tasks


class _Timings:
    """Measures the collector's tasks; reports the slow ones to the console now and then."""

    def __init__(self) -> None:
        self._slow: dict[str, list[float]] = {}
        self._sizes: dict[str, int] = {}  # context for the report (largest seen): pawns, pickups...
        self._next_report = 0.0

    def add(self, name: str, ms: float) -> None:
        """A part of a slow task (e.g. "state.pawns"): reported with the tasks."""
        self._slow.setdefault(name, []).append(ms)

    def size(self, name: str, n: int) -> None:
        self._sizes[name] = max(n, self._sizes.get(name, 0))

    def run(self, name: str, fn, *args: Any) -> None:  # noqa: ANN001
        start = time.perf_counter()
        try:
            fn(*args)
        except Exception as ex:  # noqa: BLE001
            log_error(name, ex)
        ms = (time.perf_counter() - start) * 1000
        if ms > SLOW_MS:
            self._slow.setdefault(name, []).append(ms)
        now = time.monotonic()
        if self._slow and now >= self._next_report:
            self._next_report = now + SLOW_REPORT_EVERY
            parts = [f"{n} max {max(v):.1f} ms ({len(v)}x)" for n, v in sorted(self._slow.items())]
            sizes = f" [up to {', '.join(f'{v} {k}' for k, v in sorted(self._sizes.items()))}]" if self._sizes else ""
            log(f"slow game-thread tasks (> {SLOW_MS:.0f} ms) in the last {SLOW_REPORT_EVERY:.0f} s: {', '.join(parts)}{sizes}")
            self._slow.clear()
            self._sizes.clear()


def _game_name() -> str:
    """The game the mod runs in, for the page ("bl2", "tps": its labels' Pre-Sequel variants - i18n.js), "" unknown."""
    return try_(lambda: mods_base.Game.get_current().name.lower(), "") or ""


GAME = _game_name()


def _vital(value: float) -> float:
    """A current health / shield value for the page: truncated to a tenth (enough for the bars; the page rounds it as
    the game does - down for health, and a truncated tenth rounds down / to the nearest like the exact value: 57.96
    rounded to 58.0 first showed 58 where the game shows 57), 100 not "100.0"."""
    value = math.floor(float(value or 0) * 10) / 10
    return int(value) if value.is_integer() else value


def _vital_max(value: float) -> float:
    """A max health / shield for the page (sent on change, so precise costs nothing): the page rounds it as the current
    value - a tenth rounded first could push it past the next whole number."""
    value = round(float(value or 0), 4)
    return int(value) if value.is_integer() else value


def cooked_dir() -> Path | None:
    """WillowGame/CookedPCConsole of this install (the mod folder may be a junction elsewhere)."""
    candidates = [Path(sys.executable).parent.parent.parent]  # Binaries/Win32/Borderlands2.exe
    candidates += list(Path(__file__).absolute().parents)  # sdk_mods/helios_tracker/... (unresolved)
    for base in candidates:
        d = base / "WillowGame" / "CookedPCConsole"
        if d.is_dir():
            return d
    return None


# DLC packages: <game>/DLC/<code name>/{Lic,Compat}/Content/*.upk (seen: DLC/Sage/Lic/Content/
# Sage_Underground_P.upk) - file name (lower case) -> path, listed once (the DLCs don't change while
# the game runs)
_dlc_packages: dict[str, Path] | None = None


def package_path(file_name: str) -> Path | None:
    """A cooked package by file name: the base game's (WillowGame/CookedPCConsole), else a DLC's. Files
    only (the map extraction thread)."""
    global _dlc_packages  # noqa: PLW0603
    cooked = cooked_dir()
    if cooked is None:
        return None
    if (path := cooked / file_name).is_file():
        return path
    if _dlc_packages is None:
        _dlc_packages = {}
        for content in sorted((cooked.parent.parent / "DLC").glob("*/*/Content")):
            for pkg in content.glob("*.upk"):
                _dlc_packages.setdefault(pkg.name.lower(), pkg)
    return _dlc_packages.get(file_name.lower())


def movie_length(name: str) -> float | None:
    """A cutscene video's length (s), from its Bink file's header (frames, then the frame rate as
    numerator / denominator at 28 / 32): <game>/WillowGame/Movies/<name>.bik, else a DLC's
    (DLC/<code name>/<Lic...>/Movies: Orchid_Intro.bik, 1948 frames at 29.97 = 65.0 s - the 65 s the game
    rendered nothing, tools/probe_cutscene_watch.txt). None if not found / not a Bink file. The game names some with
    their extension ('TC_Marcus.bik', 'MegaIntro' without): dropped first (it looked for 'TC_Marcus.bik.bik')."""
    cooked = cooked_dir()
    if name and name.lower().endswith(".bik"):
        name = name[:-4]
    if cooked is None or not name:
        return None
    game = cooked.parent.parent
    for folder in [game / "WillowGame" / "Movies", *sorted((game / "DLC").glob("*/*/Movies"))]:
        path = folder / f"{name}.bik"
        if path.is_file():
            with path.open("rb") as fh:
                head = fh.read(36)
            if len(head) < 36 or head[:3] not in (b"BIK", b"KB2"):
                return None
            frames = struct.unpack_from("<I", head, 8)[0]
            num, den = struct.unpack_from("<II", head, 28)
            return round(frames * den / num, 1) if num and den and frames else None
    return None


# map name -> the level's name as the game shows it ("" if no list knows it)
_level_names: dict[str, str] = {}


def level_name(map_name: str) -> str:
    """The level's name as the game shows it (the map screen's): LevelDependencyList
    .GetFriendlyLevelNameFromMapName - one list for the base game (GD_Globals.General.LevelList) and
    one per DLC, each knowing only its own maps (tools/probe_area.txt: "Ice_P" -> "Three Horns -
    Divide"). Cached per map; "" if none knows it."""
    if (cached := _level_names.get(map_name)) is None:
        cached = ""
        for lst in try_(lambda: list(unrealsdk.find_all("LevelDependencyList", exact=False)), []) or []:
            if str(lst.Name).startswith("Default__"):
                continue
            if cached := try_(lambda lst=lst: str(lst.GetFriendlyLevelNameFromMapName(map_name)), "") or "":
                break
        _level_names[map_name] = cached
    return cached


def current_playthrough() -> int:
    """The playthrough, 0-based (Normal 0, True Vault Hunter 1...), -1 if unknown: the game replication info's
    CurrentPlaythrough (tools/probe_loot_odds2.txt - a property there; the controller only has a GetCurrentPlaythrough
    function: reading pc.CurrentPlaythrough failed silently, ammo amounts and the enemies' playthrough names with it)."""
    return try_(lambda: int(ENGINE.GetCurrentWorldInfo().GRI.CurrentPlaythrough), -1)


def pawn_display_name(pawn: Any) -> str:
    """An AI pawn's name as the game shows it, from properties only (no function call: the name
    functions crashed the game): its AIPawnBalanceDefinition's PlayThroughs[].DisplayName - the entry
    of the current playthrough (current_playthrough, 0-based; the entries' PlayThrough is 1-based) if it
    has a name, else the first one that has. "" if none."""
    balance = try_(lambda: pawn.BalanceDefinitionState.BalanceDefinition)
    entries = try_(lambda: list(balance.PlayThroughs), []) or [] if balance is not None else []
    names = [(try_(lambda e=e: int(e.PlayThrough), 0), try_(lambda e=e: str(e.DisplayName), "") or "") for e in entries]
    current = current_playthrough()
    return next((n for pt, n in names if n and pt == current + 1), "") or next((n for _, n in names if n), "")


def pickup_mission(inv: Any) -> dict[str, str] | None:
    """The mission a mission item is tied to (tools/probe_pickups.txt): the one it gives (its
    MissionItemDefinition.MissionDirective - an ECHO log that starts "No Hard Feelings"; "k": "gives"),
    else the one whose objective it's for (AssociatedMissionObjective, its mission = the objective's
    Outer; "k": "for", "o": the objective). {"i": mission id, "n": its name (the game's), "k", "o"?}."""
    item_def = try_(lambda: inv.DefinitionData.ItemDefinition)
    if item_def is None:
        return None
    if (mission := try_(lambda: item_def.MissionDirective)) is not None:
        return {"i": mission_id(mission), "n": try_(lambda: str(mission.MissionName), "") or def_name(mission), "k": "gives"}
    objective = try_(lambda: item_def.AssociatedMissionObjective)
    mission = try_(lambda: objective.Outer) if objective is not None else None
    if mission is None or not hasattr(mission, "MissionName"):
        return None
    out = {"i": mission_id(mission), "n": try_(lambda: str(mission.MissionName), "") or def_name(mission), "k": "for",
           "o": try_(lambda: str(objective.ProgressMessage), "") or ""}
    # its objective's index in the mission (the page shows the item only while that objective is to do)
    if (index := try_(lambda: _mission_index(mission).get(objective._get_address()))) is not None:
        out["oi"] = index
    return out


def pretty_map_name(name: str) -> str:
    """ "SouthernShelf_P" -> "Southern Shelf": when the game has no name for the level (made up: marked raw)."""
    base = name.removesuffix("_P").removesuffix("_p").replace("_", " ")
    out = []
    for i, ch in enumerate(base):
        if i and ch.isupper() and base[i - 1].islower():
            out.append(" ")
        out.append(ch)
    return "".join(out)


# balance definition address -> (item pool names, most items one opening spawns, loot list names)
# - static per type
_loot_info: dict[int, tuple[list[str], int, list[str]]] = {}


def _configs_info(configs: Any) -> tuple[list[str], int]:
    """Loot configurations [{ConfigurationName, Weight, ItemAttachments[{ItemPool}]}] -> their pool
    names, and the most item slots (attachments: one item each) any single configuration has."""
    pools, slots = [], 0
    for cfg in try_(lambda: list(configs), []) or []:
        attachments = try_(lambda c=cfg: list(c.ItemAttachments), []) or []
        slots = max(slots, len(attachments))
        for att in attachments:
            if (pool := try_(lambda a=att: a.ItemPool)) is not None:
                pools.append(str(pool.Name))
    return pools, slots


def loot_info(io: Any, balance: Any) -> tuple[list[str], int, list[str]]:
    """What a container can hold, as (item pools, most items per opening, loot list names): its
    loot is rolled from those pools when it's opened (the items themselves only exist then). From
    its balance (per type, cached) - default loot + the loot lists it includes (named by the game's
    tier: EpicChestRedLoot, WeaponChestWhiteLoot...) - else the object's own Loot."""
    key = try_(lambda: balance._get_address()) if balance is not None else None
    if key is not None and key not in _loot_info:
        pools, slots = _configs_info(try_(lambda: balance.DefaultLoot))
        lists = []
        for lst in try_(lambda: list(balance.DefaultIncludedLootLists), []) or []:
            lists.append(str(lst.Name))
            more, more_slots = _configs_info(try_(lambda l=lst: l.LootData))
            pools += more
            slots = max(slots, more_slots)
        _loot_info[key] = (list(dict.fromkeys(pools)), slots, lists)  # pools unique, in order
    if key is not None and (_loot_info[key][0] or _loot_info[key][2]):
        return _loot_info[key]
    pools, slots = _configs_info(try_(lambda: io.Loot))
    return list(dict.fromkeys(pools)), slots, []


class _ImageCache:
    """Extracted map images and fog of war per (package file, mtime, movie): revisiting a level is free."""

    def __init__(self, size: int = 4) -> None:
        self._size = size
        self._items: dict[tuple[str, float, str], tuple[list[MapImage], MapFog | None]] = {}
        self._lock = threading.Lock()

    def get(self, pkg_file: Path, movie: str) -> tuple[list[MapImage], MapFog | None]:
        key = (str(pkg_file).lower(), pkg_file.stat().st_mtime, movie.lower())
        with self._lock:
            if key in self._items:
                return self._items[key]
        images = load_tactical_map(pkg_file, movie)
        try:
            fog = load_fog(pkg_file, movie)
        except Exception as ex:  # noqa: BLE001 - the map still shows without its fog
            log_error("fog of war extraction", ex)
            fog = None
        with self._lock:
            self._items[key] = (images, fog)
            while len(self._items) > self._size:
                del self._items[next(iter(self._items))]
        return images, fog


class Collector:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        # Unique across mod reloads (not 0, 1, 2...): an open page must see a reloaded mod's first
        # level as a new one, or it keeps its old pawns
        self.level_id = int(time.time() * 1000) % 1_000_000_000
        self._lock = threading.Lock()  # guards level_id / _level against the extraction thread
        self._level: dict[str, Any] | None = None
        self._level_key: tuple[str, str | None] | None = None
        self._images = _ImageCache()
        self.on_page: Any = None  # called when a page connects (the mod sets it: the game files' scan)
        self._video_at = 0.0  # a cutscene video started (monotonic time): cleared once the frames come back
        self._video_len: float | None = None
        self._video_gap = False  # the frames stopped since it started (the video playing)
        self._last_tick = 0.0
        # an in-engine cutscene (the script's cinematic mode): {"seq": its Matinee (WeakPointer) or None, "next"}
        self._scene: dict[str, Any] | None = None
        self._interps: tuple[int, list[Any]] | None = None  # (level id, the level's Matinees: WeakPointers)
        self._classes: dict[str, Any] = {}
        self._timings = _Timings()
        self.rate = 10.0  # updates per second (the mod's option; sent so the page can align on it)
        self._hook_seen = False
        self._usability_hook_seen = False
        self._vars_logged: set[str] = set()  # pawn kinds whose health / shield "Var" properties were compared
        self._drive_logged = False  # a driving player's health properties vs functions: logged once
        self.reset()

    def reset(self) -> None:
        """Forget the level (re-detected, and re-published, on the next tick)."""
        self._level_key = None
        self._next_level_check = 0.0
        self._clear_contents()

    def _clear_contents(self) -> None:
        clear_fields()  # a new level: packages may have been unloaded (the property cache re-fills at once)
        self._seats: dict[int, bool] = {}  # class address -> a vehicle seat's (_is_seat; addresses: per level, as above)
        self._areas = []
        self._areas_json = ""
        self._next_scan = 0.0
        self._next_objects = 0.0
        self._next_players = 0.0
        self._next_missions = 0.0
        self._missions_json = ""
        self._tracker: WeakPointer | None = None  # the MissionTracker, found at each scan
        # A co-op client: the level's WillowWaypoint actors (no waypoint components there: the
        # markers are worked out from them - _client_markers), found at each objects scan
        self._waypoints: list[WeakPointer] = []
        self._client = False  # a co-op client (set at each objects scan): containers opened by their state alone
        # NPCs giving / taking back missions (their MissionDirectives: tools/probe_directors.txt), by
        # pawn address -> (the pawn, [(mission, begins, ends)]): a co-op client's quest-giver markers
        self._givers: dict[int, tuple[WeakPointer, list[tuple[Any, bool, bool]]]] = {}
        self._next_log = 0.0
        self._log = MissionLog()
        self._active = False  # a page was connected last tick
        self._pickups: dict[int, WeakPointer] = {}  # by address: from scans and the spawn hook
        self._gear_classes: dict[int, bool] = {}  # item class address -> gear (cards on the map; per level: addresses)
        # pawn address -> (health, max, shield, shield max), read every HEALTH_EVERY updates
        self._health: dict[int, tuple[float, float, float, float]] = {}
        self._skills = SkillReader()  # every player's action skill, timed effects, melee cooldown
        self._state_n = 0
        self._info: dict[int, dict[str, Any]] = {}  # per-actor cached name/kind, by address
        # pawns the game has had as its boss (GRI.BossPawn, the boss bar's) this level: (level id, address)
        self._boss_pawns: set[tuple[Any, int]] = set()
        self._pools_sent: tuple[int, int] | None = None  # (lootodds.version, POOLS' size) when last sent (None: send it)
        # Interactive objects don't move or get renamed: each record is built once per level
        self._object_records: dict[tuple[int, str], dict[str, Any] | None] = {}
        self._objects: dict[tuple[int, str], dict[str, Any]] = {}  # what the objects payload shows
        self._objects_dirty = False  # hooks changed it: publish on the next tick (batched)
        # objects a scan found, their record not built yet: built a few per tick (a level's first scan
        # has hundreds: one long hitch otherwise)
        self._pending_records: dict[tuple[int, str], WeakPointer] = {}
        self._incomplete: dict[tuple[int, str], WeakPointer] = {}  # records built before their definition: built again
        self._next_incomplete = 0.0
        self._unlooted: dict[tuple[int, str], WeakPointer] = {}  # lootable containers not opened yet
        self._domes: dict[tuple[int, str], WeakPointer] = {}  # the Pre-Sequel's air dome bubbles: their on / off re-read
        self._damageable: dict[tuple[int, str], WeakPointer] = {}  # objects with health (barrels...): re-read
        self._next_looted = 0.0
        # The level's discovery areas (static records, found by the objects scan) and the areas payload
        self._areas: list[dict[str, Any]] = []
        self._areas_json = ""
        self._next_areas = 0.0
        self._shops = ShopReader()  # the level's vending machines (from the objects scan / spawn hook)
        self._next_shops = 0.0

    # region Level

    def tick(self, now: float) -> None:
        run = self._timings.run
        # A cutscene video: the game renders no frame while one plays - frames again after a gap: it's over
        # (or skipped). Frames can go on for a moment after its start (a fade): those don't end it.
        if self._video_at:
            if self._last_tick and now - self._last_tick > VIDEO_GAP:
                self._video_gap = True
            over = self._video_gap or (self._video_len is not None and now - self._video_at > self._video_len + VIDEO_SPARE)
            if over:
                log(f"cutscene video over after {now - self._video_at:.1f} s (frames stopped: {self._video_gap})")
                self._video_at, self._video_gap = 0.0, False
                self.hub.publish("cutscene", "{}")
        self._last_tick = now
        if now >= self._next_level_check:
            self._next_level_check = now + LEVEL_CHECK_EVERY
            run("level", self._check_level)
        if self._level_key is None:
            return
        if not self.hub.clients:  # no page open: only follow the level
            self._active = False
            return
        if not self._active:  # a page just connected: fresh objects and players now
            self._active = True
            if self.on_page is not None:  # (the mod: the game files' scan, once)
                self.on_page()
            self._next_scan = self._next_objects = self._next_players = self._next_missions = self._next_log = 0.0
            self._log.dirty = self._log.defs_dirty = True  # the new page needs the log
            self._missions_json = self._areas_json = ""  # (the record channels: the Hub sends a new page everything)
            self._pools_sent = None
            self._shops.resend()
            self._next_shops = 0.0
        # At most one heavy task (scans / players) per tick: they'd add up into one hitch
        heavy = False
        if now >= self._next_scan:
            self._next_scan = now + SCAN_EVERY
            run("scan pickups", self._scan)
            heavy = True
        if now >= self._next_objects and not heavy:
            self._next_objects = now + OBJECTS_EVERY
            run("scan objects", self._scan_objects)
            self._next_missions = 0.0  # it (re)finds the mission tracker: read the markers now
            heavy = True
        run("state", self._publish_state, now)
        if self._incomplete and now >= self._next_incomplete:  # built before their definition: again (not every 120 s)
            self._next_incomplete = now + INCOMPLETE_EVERY
            for key, ptr in list(self._incomplete.items()):
                if ptr() is None:  # gone meanwhile
                    del self._incomplete[key]
                else:
                    self._pending_records.setdefault(key, ptr)
        if self._pending_records:
            run("object records", self._build_pending_records)
        if self._objects_dirty:
            self._objects_dirty = False
            run("objects", self._publish_objects)
        if now >= self._next_players and not heavy:
            self._next_players = now + PLAYERS_EVERY
            run("players", self._publish_players)
            heavy = True
        # The mission log's full pass: a slice per tick until it's done (never one long hitch)
        if self._tracker is not None and (self._log.in_cycle or (now >= self._next_log and not heavy)):
            if not self._log.in_cycle:
                self._next_log = now + MISSION_LOG_EVERY
            run("mission log", self._full_log)
        if now >= self._next_missions:
            self._next_missions = now + MISSIONS_EVERY
            run("missions", self._publish_missions)
        if now >= self._next_areas and (self._areas or (self._level or {}).get("fog")):
            self._next_areas = now + AREAS_EVERY
            run("areas", self._publish_areas)
        if now >= self._next_shops and not heavy:
            self._next_shops = now + SHOPS_EVERY
            run("shops", self._publish_shops, now)
        if now >= self._next_looted and (self._unlooted or self._domes or self._damageable):
            self._next_looted = now + LOOTED_EVERY
            if self._unlooted:
                run("looted", self._check_looted)
            if self._domes:
                run("domes", self._check_domes)
            if self._damageable:
                run("object health", self._check_health)

    def _check_level(self) -> None:
        wi = ENGINE.GetCurrentWorldInfo()
        if wi is None:
            return
        name = str(wi.GetStreamingPersistentMapName())
        info = wi.GetMapInfo()
        vol = info.TacticalMapVolume if info is not None else None
        movie = info.TacticalMapMovie if info is not None else None
        key = (name, vol._path_name() if vol is not None else None)
        if key == self._level_key:
            return
        self._clear_contents()
        self._level_key = key
        with self._lock:
            self.level_id += 1
            level_id = self.level_id
        game_name = level_name(name)
        level: dict[str, Any] = {"id": level_id, "map": name, "name": game_name or pretty_map_name(name), "images": [],
                                 "rarity": try_(rarity_table, {}) or {}}  # the game's rarity colours
        if not game_name:
            level["raw"] = 1  # a made-up name (the page marks it)
        if vol is None or movie is None:
            level["status"] = "none"
            log(f"no map for {name}: its map info {try_(lambda: info._path_name()) if info is not None else None},"
                f" TacticalMapVolume {vol is not None}, TacticalMapMovie {movie is not None}")
        else:
            bounds = vol.BrushComponent.Bounds
            c = bounds.Origin
            level.update(
                status="loading",
                center=[c.X, c.Y],
                upp=vol.UnrealUnitsPerPixel * MOVIE_SCALE,
                north=vol.NorthOffsetInDegreesClockwise,
                # The mapped level's vertical range (the volume's box): below it = fallen off the map
                # (the game only destroys what goes under KillZ, which can be far lower)
                zmin=round(c.Z - bounds.BoxExtent.Z),
                zmax=round(c.Z + bounds.BoxExtent.Z),
                killz=try_(lambda: round(wi.KillZ)),
            )
        self._set_level(level)
        if level["status"] == "loading":
            threading.Thread(
                target=self._extract,
                args=(dict(level), name, movie._path_name()),
                name="helios_tracker map",
                daemon=True,
            ).start()

    def _set_level(self, level: dict[str, Any], keep_lv: bool = True) -> None:
        with self._lock:
            if level["id"] != self.level_id:
                return  # a newer level already
            if keep_lv and "lv" not in level and self._level and self._level.get("id") == level["id"] and "lv" in self._level:
                level = {**level, "lv": self._level["lv"]}  # (the map thread's copy predates the area's level)
            self._level = level
            self.hub.publish("level", json.dumps({**level, **({"game": GAME} if GAME else {})}))

    def _extract(self, level: dict[str, Any], map_name: str, movie: str) -> None:
        """Background thread: files only, no UObjects."""
        level_id = level["id"]
        try:
            package = package_path(f"{map_name}.upk")  # the base game's, or a DLC's
            if package is None:
                raise FileNotFoundError(f"couldn't find {map_name}.upk (WillowGame/CookedPCConsole, DLC/*/*/Content)")
            images, fog = self._images.get(package, movie)
        except Exception as ex:  # noqa: BLE001
            log_error("map extraction", ex)
            level.update(status="error", error=f"{type(ex).__name__}: {ex}")
            self._set_level(level)
            return
        self.hub.set_images(level_id, [img.data for img in images] + ([fog.blob.data] if fog else []))
        if fog:  # the game's fog of war: its blob (the image after the map's) and where it goes, per area
            level["fog"] = {
                "url": f"/image/{level_id}/{len(images)}",
                "format": fog.blob.format,
                "width": fog.blob.width,
                "height": fog.blob.height,
                "bounds": fog.blob.bounds,
                "pieces": [[name.lower(), [round(v, 4) for v in matrix]] for name, matrix in fog.pieces],
            }
        level["images"] = [
            {
                "url": f"/image/{level_id}/{n}",
                "name": img.name,
                "format": img.format,
                "width": img.width,
                "height": img.height,
                "bounds": img.bounds,
                **({"crop": img.crop} if img.crop else {}),  # (a sub-image: the part of it drawn in bounds)
            }
            for n, img in enumerate(images)
        ]
        level["status"] = "ready" if images else "none"
        if not images:
            log(f"no map for {map_name}: {movie} in {package} held no image")
        self._set_level(level)

    # endregion
    # region Contents

    def _cls(self, name: str) -> Any:
        if name not in self._classes:
            self._classes[name] = try_(lambda: unrealsdk.find_class(name))
        return self._classes[name]

    def _is(self, obj: Any, cls_name: str) -> bool:
        cls = self._cls(cls_name)
        return cls is not None and obj.Class._inherits(cls)

    def _is_seat(self, pawn: Any) -> bool:
        """A vehicle seat pawn (WillowWeaponPawn: a turret's gunner seat...): by class name up the
        chain, cached per class (by address, not its name: read per pawn per update)."""
        cls = pawn.Class
        key = cls._get_address()
        if (seat := self._seats.get(key)) is None:
            c, seat = cls, False
            while c is not None and not seat:
                seat = "WeaponPawn" in str(c.Name)
                c = try_(lambda c=c: c.SuperField)
            self._seats[key] = seat
        return seat

    @staticmethod
    def _in_vacuum(pawn: Any) -> bool:
        """A player in a vacuum (the Pre-Sequel): their pawn's VacuumComponent (an OzVacuumComponent) State VS_InVacuum -
        VS_InAir inside an air dome that's on (tools/probe_dome_state.txt)."""
        state = try_(lambda: field(pawn, "VacuumComponent").State)
        return getattr(state, "name", state) == "VS_InVacuum"

    @staticmethod
    def _oxygen(pawn: Any) -> tuple[float, float] | None:
        """A player's oxygen (the Pre-Sequel's Oz meter): (current, max) from the pawn's OxygenPool, else their
        replicated one (PlayerReplicationInfo.OxygenPool: a co-op client's view of the others) - a pool reference
        whose Data (OzOxygenResourcePool) has CurrentValue / MaxValue (tools/probe_tps2.txt: 100 / 100). None without
        one (BL2) or a max of 0."""
        for ref in (try_(lambda: field(pawn, "OxygenPool")), try_(lambda: field(pawn, "PlayerReplicationInfo").OxygenPool)):
            data = try_(lambda r=ref: r.Data) if ref is not None else None
            top = try_(lambda d=data: float(d.MaxValue), 0.0) if data is not None else 0.0
            if top > 0:
                return try_(lambda d=data: float(d.CurrentValue), 0.0), top
        return None

    @staticmethod
    def _boost(vehicle: Any, world_now: float) -> list[float] | None:
        """A vehicle's boost (nitro) meter: [left, max] from its AfterburnerPool (tools/probe_vehicle.txt:
        a resource pool next to its HealthPool) - the pool's CurrentValue and MaxValue (else
        BaseMaxValue). None without one (or an empty max).
        Refilling (not boosting, not full): a third value, the seconds until full - it refills like a
        shield (tools/probe_boost.txt): OnIdleRegenerationDelay (5 s) after PoolIdleDelayStartTime (world
        time: when the boost stopped), then OnIdleRegenerationRate per second (20)."""
        pool = try_(lambda: field(vehicle, "AfterburnerPool").Data)
        if pool is None:
            return None
        cur = try_(lambda: float(pool.CurrentValue))
        top = try_(lambda: float(pool.MaxValue), 0.0) or try_(lambda: float(pool.BaseMaxValue), 0.0)
        if cur is None or not top:
            return None
        out = [round(cur, 1), round(top, 1)]
        rate = try_(lambda: float(pool.OnIdleRegenerationRate), 0.0)
        if cur < top and rate > 0 and not try_(lambda: field(vehicle, "AfterburnerEngaged"), False):
            wait = try_(lambda: float(pool.PoolIdleDelayStartTime) + float(pool.OnIdleRegenerationDelay) - world_now, 0.0)
            out.append(round(max(0.0, wait) + (top - cur) / rate, 1))
        return out

    def _seat_vehicle(self, seat: Any) -> Any:
        """The vehicle a seat pawn belongs to (a player on a turret: DrivenVehicle is the seat, which
        isn't on the map - its vehicle is): UE3's links, first that's a WillowVehicle - the seat's
        MyVehicle, what it's attached to (Base), its Owner. Property reads; None if none is."""
        for name in ("MyVehicle", "Base", "Owner"):
            v = try_(lambda n=name: field(seat, n))
            if v is not None and try_(lambda v=v: self._is(v, "WillowVehicle") and not self._is_seat(v), False):
                return v
        return None

    @staticmethod
    def _in_world(actor: Any) -> bool:
        """Placed/spawned in a level (not a template or a default object), and not being destroyed."""
        return (
            not actor.Name.startswith("Default__")
            and actor.Outer is not None
            and actor.Outer.Class.Name == "Level"
            and not actor.bDeleteMe
        )

    def _scan(self) -> None:
        """Every SCAN_EVERY: the pickups (their positions are read per tick)."""
        self._info = {}  # names / allegiances can change: re-resolved lazily
        self._pickups = {
            p._get_address(): WeakPointer(p)
            for p in unrealsdk.find_all("WillowPickup", exact=False)
            if try_(lambda p=p: self._in_world(p), False)
        }

    def movie_started(self, pc: Any, name: str, no_skip: bool) -> None:
        """From the ClientPlayBinkMovie hook: a cutscene video starts on this PC (tools/probe_cutscene_watch.txt:
        ClientPlayBinkMovie(MovieName='Orchid_Intro'), then not one frame for its 65 s - the collector, run
        from the frames, is silent meanwhile). Tells the page now, with its length (the file's) and start
        (epoch s: a page opened meanwhile counts from it); the first frame after it clears it (tick).
        Another player's controller (the host sends them theirs): not this PC's video, ignored."""
        me = get_pc(possibly_loading=True)
        if me is None or try_(lambda: pc._get_address() != me._get_address(), True):
            log(f"cutscene video {name!r} on another controller ({try_(lambda: pc.Name)}, ours: {try_(lambda: me.Name)}): ignored")
            return
        self._video_at, self._video_gap = time.monotonic(), False
        self._video_len = length = try_(lambda: movie_length(name))
        log(f"cutscene video {name!r}: {length} s" + (" (can't be skipped)" if no_skip else ""))
        self.hub.publish("cutscene", json.dumps({"video": name, "name": name, "len": length, "at": round(time.time(), 2),
                                                 **({"noskip": 1} if no_skip else {})}))

    def _check_scene(self, pc: Any, wi: Any, now: float) -> None:
        """An in-engine cutscene on this PC (a forced scene, no video): the level script's cinematic mode
        (tools/probe_cutscene_watch.txt: SetCinematicMode(bKismetSetCinematicMode=True) -> bCinematicMode and
        bKismetEnabledCinematicMode, the camera on a CameraActor; a cinematic mode not from the script - after
        a video, a respawn - doesn't count). A video's own cinematic mode: the video's (movie_started).
        Backgrounds are one too: the main menu's (the menu map's script, its Matinee = GRI.MenuMatinee - seen
        as a 1:40 "cutscene") and the character creation's idle (30.3 s, after the new game's intro): never
        one - no character in the world yet (a real cutscene has the player's pawn, hidden), or a menu open.
        Elapsed: counted here from its start (not a Matinee's Position: a scene plays several at once, some
        started before it - seen: a 30 s one found 13.9 s in, then another 19.6 s in - the bar jumped), not
        while paused (the game: WorldInfo.Pauser; its longest Matinee's Position not moving). Its length:
        elapsed + the most any of its Matinees still has to play (_matinees_left, every SCENE_RECHECK) - it can
        grow (a later shot), elapsed never jumps; no Matinee: none (the page counts up). Sent on its start,
        a pause / resume, a length changing by over a second, the page's count drifting (SCENE_DRIFT)."""
        if self._video_at:
            return
        pawn = try_(lambda: field(pc, "MyWillowPawn")) or try_(lambda: field(pc, "Pawn"))
        background = (str((self._level or {}).get("map", "")).lower() == "menumap" or pawn is None
                      or try_(lambda: self._in_menu(pawn), False))
        on = not background and try_(lambda: bool(field(pc, "bCinematicMode")) and bool(field(pc, "bKismetEnabledCinematicMode")), False)
        if not on:
            if self._scene is not None:
                log(f"in-engine cutscene over after {self._scene['played']:.1f} s")
                self._scene = None
                self.hub.publish("cutscene", "{}")
            return
        scene = self._scene
        if scene is None:
            scene = self._scene = {"played": 0.0, "t": now, "len": None, "next": 0.0, "seq": None, "pos": None,
                                   "moved": now, "sent": None, "name": ""}
        # Paused: the game, or its Matinee still playing but not moving; else this tick's time counted
        seq = scene["seq"]() if scene["seq"] is not None else None
        pos = try_(lambda: float(seq.Position)) if seq is not None and try_(lambda: bool(seq.bIsPlaying), False) else None
        if pos is not None and pos != scene["pos"]:
            scene["pos"], scene["moved"] = pos, now
        paused = try_(lambda: field(wi, "Pauser") is not None, False) or (pos is not None and now - scene["moved"] > 0.3)
        if not paused:
            scene["played"] += now - scene["t"]
        scene["t"] = now
        if now >= scene["next"]:  # its Matinees: how long the longest still plays, on top of elapsed
            scene["next"] = now + SCENE_RECHECK
            found = try_(self._matinees_left)
            if found:
                seq, left, pos = found
                scene["len"] = scene["played"] + left
                if scene["seq"] is None or scene["seq"]() is not seq:
                    scene["seq"], scene["pos"], scene["moved"] = WeakPointer(seq), pos, now
                    scene["name"] = try_(lambda: self._matinee_name(seq), "") or ""
                    log(f"in-engine cutscene {scene['name']!r}: {scene['len']:.1f} s ({scene['played']:.1f} s in;"
                        f" {seq.Name}: {left:.1f} s left)")
            elif scene["len"] is not None and scene["played"] >= scene["len"]:
                scene["len"] = None  # (past every Matinee: counted up)
        at, length, sent = time.time() - scene["played"], scene["len"], scene["sent"]
        if (sent is None or sent["paused"] != paused or (length is None) != (sent["len"] is None) or sent["name"] != scene["name"]
                or (length is not None and abs(length - sent["len"]) > 1.0) or (not paused and abs(at - sent["at"]) > SCENE_DRIFT)):
            scene["sent"] = {"paused": paused, "at": at, "len": length, "name": scene["name"]}
            self.hub.publish("cutscene", json.dumps({"scene": 1, "len": round(length, 1) if length else None, "at": round(at, 2),
                                                     **({"name": scene["name"]} if scene["name"] else {}),
                                                     **({"paused": 1, "pos": round(scene["played"], 2)} if paused else {})}))

    @staticmethod
    def _matinee_name(seq: Any) -> str:
        """What a cutscene's Matinee is called: its comment in the level's script (ObjComment, if the
        designers wrote one), else where it is in the script (its sequence's name + its own:
        "Main_Sequence.SeqAct_Interp_1"). Identifiers, not game text (the game shows none)."""
        comment = str(try_(lambda: seq.ObjComment, "") or "").strip()
        if comment:
            return comment
        outer = try_(lambda: str(seq.Outer.Name), "")
        return f"{outer}.{seq.Name}" if outer else str(seq.Name)

    def _matinees_left(self) -> tuple[Any, float, float] | None:
        """The Matinees playing now (SeqAct_Interp: playing, not looping - the day / night cycle's is,
        WillowSeqAct_DayNightCycle, left out, and the menu's background, GRI.MenuMatinee), with the InterpData
        plugged into them (a variable: its InterpLength, s): the one with the most left to play -> (it, s left
        over its PlayRate, its Position), or None. The level's Matinees: found once per level (a find_all),
        then only read."""
        level_id = self.level_id
        if self._interps is None or self._interps[0] != level_id:
            self._interps = (level_id, [WeakPointer(s) for s in unrealsdk.find_all("SeqAct_Interp", exact=False)
                                        if not s.Name.startswith("Default__") and "DayNight" not in str(s.Class.Name)])
        menu = try_(lambda: ENGINE.GetCurrentWorldInfo().GRI.MenuMatinee)
        menu_addr = try_(lambda: menu._get_address()) if menu is not None else None
        best = None
        for ptr in self._interps[1]:
            seq = ptr()
            if seq is None or not try_(lambda s=seq: bool(s.bIsPlaying) and not bool(s.bLooping), False):
                continue
            if menu_addr is not None and try_(lambda s=seq: s._get_address() == menu_addr, False):
                continue
            length = max((try_(lambda v=v: float(v.InterpLength), 0.0)
                          for link in try_(lambda s=seq: list(s.VariableLinks), []) or []
                          for v in try_(lambda k=link: list(k.LinkedVariables), []) or [] if v is not None), default=0.0)
            rate = try_(lambda s=seq: float(s.PlayRate), 1.0) or 1.0
            pos = try_(lambda s=seq: float(s.Position), 0.0)
            left = (length - pos) / rate
            if length > 0 and left > 0 and (best is None or left > best[1]):
                best = (seq, left, pos)
        return best

    def pickup_spawned(self, pickup: Any) -> None:
        """From the WillowPickup:PostBeginPlay hook: a new pickup (loot drop...), no scan needed."""
        if self._level_key is not None and self.hub.clients:
            if not self._hook_seen:
                self._hook_seen = True
                log("pickup spawn hook works (first new pickup seen)")
            self._pickups[pickup._get_address()] = WeakPointer(pickup)

    def _scan_objects(self) -> None:
        """Every OBJECTS_EVERY: interactive objects (static: records built once per level) and the
        mission tracker."""
        objects = {}
        records = self._object_records
        # the host's live designer attributes (common gear's weight modifier...): changed - the containers' odds again
        odds_changed = try_(lambda: lootodds.refresh(ENGINE.GetCurrentWorldInfo()), False)
        for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
            try:
                key = (io._get_address(), str(io.Name))
                if self._in_world(io):
                    self._shops.note(io)
                if key not in records or key in self._incomplete:  # new / built too early: (again) later, a few per tick
                    self._pending_records.setdefault(key, WeakPointer(io))
                    if key not in records:
                        continue
                if (record := records[key]) is not None and not io.bHidden and not io.bDeleteMe:
                    objects[key] = record
                    if record.get("lootable") and not record.get("looted"):
                        self._unlooted.setdefault(key, WeakPointer(io))
                    if "dome" in record:
                        self._domes.setdefault(key, WeakPointer(io))
                    if "m" in record:
                        self._damageable.setdefault(key, WeakPointer(io))
                    if odds_changed and "odds" in record:  # (in place: cached per type, a few to work out)
                        balance = try_(lambda io=io: io.BalanceDefinitionState.BalanceDefinition)
                        record["odds"] = try_(lambda io=io, b=balance: lootodds.container_odds(io, b)) or record["odds"]
            except Exception as ex:  # noqa: BLE001
                log_error("interactive object", ex)
        self._objects = objects
        if self._tracker is None or self._tracker() is None:  # one per game: only look it up again if gone
            self._tracker = next(
                (WeakPointer(t) for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")),
                None,
            )
        # A co-op client has no mission waypoint components: its markers come from the waypoint actors
        wi = ENGINE.GetCurrentWorldInfo()
        client = self._client = getattr(try_(lambda: wi.NetMode), "name", "") == "NM_Client"
        self._waypoints = [WeakPointer(w) for w in unrealsdk.find_all("WillowWaypoint", exact=False)
                           if not w.Name.startswith("Default__")] if client else []
        self._areas = [a for w in unrealsdk.find_all("WorldDiscoveryArea", exact=False)
                       if (a := try_(lambda w=w: self._area_record(w) if self._in_world(w) else None))]
        self._next_areas = 0.0
        self._publish_objects()

    @staticmethod
    def _area_record(area: Any) -> dict[str, Any]:
        """A discovery area (tools/probe_discovery.txt: WorldDiscoveryArea, a handful per level): its short
        name (the key pc.DiscoveredWorldAreas uses: CustomName if bUseCustomName, else
        DefaultWorldAreaShortName - 'SOUTHERNSHELF_PWDA_4'), the game's name for it (WorldAreaDisplayName,
        'Wreck Of The Ice Sickle'; empty for bForFogOfWarOnly ones: they only clear the map's fog),
        where and how big (DetectionRadius, uu)."""
        key = str(area.CustomName) if area.bUseCustomName else str(area.DefaultWorldAreaShortName)
        loc = area.Location
        name = str(area.WorldAreaDisplayName or "").strip()
        return {"k": key.lower(), "x": round(loc.X), "y": round(loc.Y), "z": round(loc.Z), "r": round(area.DetectionRadius),
                **({"n": name} if name and not area.bForFogOfWarOnly else {})}

    def _publish_areas(self) -> None:
        """The level's areas with the ones this player discovered: those in pc.DiscoveredWorldAreas[]
        ({DiscoveryName, HasBeenUncovered} - being listed is what counts: tools/probe_fog.txt, every entry
        HasBeenUncovered False, Glacial's too though fully explored; Southern Shelf: the 5 areas visited
        listed, the one not reached absent). A map in pc.FullyExploredAreas: all of it. On change."""
        pc = get_pc(possibly_loading=True)
        if pc is None:
            return
        found = {str(e.DiscoveryName).lower() for e in try_(lambda: list(pc.DiscoveredWorldAreas), []) or []}
        level = self._level or {}
        full = str(level.get("map", "")).lower() in {str(m).lower() for m in try_(lambda: list(pc.FullyExploredAreas), []) or []}
        areas = [{**a, **({"u": 1} if full or a["k"] in found else {})} for a in self._areas]
        # the fog pieces of the areas discovered, by name: whether their actor is loaded or not (a streamed
        # sublevel's: "SAGE_UNDERGROUND_DYNAMICWDA_5")
        seen = sorted(n for n, _ in (level.get("fog") or {}).get("pieces", []) if n in found)
        areas_json = json.dumps({"level": self.level_id, "areas": areas, "seen": seen, **({"full": 1} if full else {})},
                                separators=(",", ":"))
        if areas_json != self._areas_json:
            self._areas_json = areas_json
            self.hub.publish("areas", areas_json)

    def _build_pending_records(self) -> None:
        """The records of objects a scan found, within RECORDS_SECONDS per tick; shown as they're built."""
        deadline = time.perf_counter() + RECORDS_SECONDS
        records = self._object_records
        while self._pending_records and time.perf_counter() < deadline:
            key, ptr = next(iter(self._pending_records.items()))
            del self._pending_records[key]
            io = ptr()
            if io is None or (key in records and key not in self._incomplete):
                continue
            try:
                records[key] = self._object_record(io, self._client) if self._in_world(io) else None
                self._note_incomplete(key, io)
                self._note_giver(key[0], io, try_(lambda io=io: io.Directives))
                if (record := records[key]) is not None and not io.bHidden and not io.bDeleteMe:
                    self._objects[key] = record
                    self._objects_dirty = True
                    if record.get("lootable") and not record.get("looted"):
                        self._unlooted.setdefault(key, WeakPointer(io))
                    if "dome" in record:
                        self._domes.setdefault(key, WeakPointer(io))
                    if "m" in record:
                        self._damageable.setdefault(key, WeakPointer(io))
            except Exception as ex:  # noqa: BLE001
                log_error("interactive object", ex)

    def _publish_shops(self, now: float) -> None:
        """The vending machines' stock (when it changed) and the restock timer (when the page's count drifted)."""
        stock, timer = self._shops.read(ENGINE.GetCurrentWorldInfo(), get_pc(), self.level_id, self._client, now)
        if self._shops.pending:
            self._next_shops = now + SHOPS_RETRY
        if stock is not None:  # (a sale: only that machine goes out)
            payload = json.loads(stock)
            self.hub.publish_records("shops", "machines", payload.pop("machines"), payload)
        if timer is not None:
            self.hub.publish("shoptimer", timer)

    def _publish_objects(self) -> None:
        objects = list(self._objects.values())
        # the pools the containers' odds reach (lootodds.POOLS: static, only ever grows) - before the objects, so the
        # page has them when it shows an object's odds; sent again only when new ones came
        if (lootodds.version, len(lootodds.POOLS)) != self._pools_sent:
            self._pools_sent = (lootodds.version, len(lootodds.POOLS))
            self.hub.publish("lootpools", json.dumps({"pools": lootodds.POOLS}, separators=(",", ":")))
        self.hub.publish_records("objects", "objects", objects, {"level": self.level_id})  # (only what changed goes out)

    # From hooks (game thread): objects that spawn / get their balance (display name) / go away after
    # the level loaded - e.g. hazards spawned when an area activates. Before the level is known, or
    # with no page open, they're left to the next scan.

    def object_spawned(self, io: Any) -> None:
        if self._level_key is None or not self.hub.clients or not self._in_world(io):
            return
        key = (io._get_address(), str(io.Name))
        self._object_records[key] = record = self._object_record(io, self._client)
        self._note_incomplete(key, io)
        self._note_giver(key[0], io, try_(lambda: io.Directives))
        self._shops.note(io)
        if not io.bHidden:
            self._objects[key] = record
            self._objects_dirty = True
            if record.get("lootable") and not record.get("looted"):
                self._unlooted[key] = WeakPointer(io)
            if "dome" in record:
                self._domes[key] = WeakPointer(io)
            if "m" in record:
                self._damageable[key] = WeakPointer(io)

    def _note_incomplete(self, key: tuple[int, str], io: Any) -> None:
        """A record built before the object had its definition (it arrives a moment after the object
        - a co-op client, the host too after a level load): "Interactive Object ?", in "Other", not a
        container - retried every INCOMPLETE_EVERY until it has one (the full objects scan is only every
        OBJECTS_EVERY, 120 s: the first version waited for it - "2 min to sync")."""
        if try_(lambda: io.InteractiveObjectDefinition) is None:
            self._incomplete[key] = WeakPointer(io)
        else:
            self._incomplete.pop(key, None)

    def _note_giver(self, key: int, actor: Any, definition: Any) -> None:
        """An NPC's / object's missions it gives / takes back (a MissionDirectivesDefinition - an NPC's
        MissionDirectives, an interactive object's Directives: the bounty board, tools/probe_bounty.txt;
        static): kept for the quest-giver markers (_npc_givers)."""
        directives = [(d.MissionDefinition, bool(d.bBeginsMission), bool(d.bEndsMission))
                      for d in try_(lambda: list(definition.MissionDirectives), []) or []
                      if try_(lambda d=d: d.MissionDefinition) is not None]
        if directives:
            self._givers[key] = (WeakPointer(actor), directives)
        else:
            self._givers.pop(key, None)

    def object_destroyed(self, io: Any) -> None:
        key = (io._get_address(), str(io.Name))
        self._givers.pop(key[0], None)
        self._shops.forget(key)
        self._incomplete.pop(key, None)
        self._object_records.pop(key, None)
        self._unlooted.pop(key, None)
        if self._objects.pop(key, None) is not None:
            self._objects_dirty = True

    def object_usability_changed(self, io: Any) -> None:
        """From the SetUsability / Behavior_ChangeUsability hooks: opening a container turns its use
        off right away (the "opened" animation state only follows) - a lootable container that was
        usable and no longer is: looted now, no waiting for the round robin."""
        key = (io._get_address(), str(io.Name))
        record = self._object_records.get(key)
        if record is None or not record.get("lootable") or record.get("looted") or not record.get("usable"):
            return
        if not self._usability_hook_seen:
            self._usability_hook_seen = True
            log("usability hook works (first container use change seen)")
        if not try_(lambda: io.bCanBeUsed[0], 1):
            record["looted"] = 1
            self._unlooted.pop(key, None)
            self._objects_dirty = True  # published on the next tick

    def _check_looted(self) -> None:
        """Containers opened since: flagged looted (the page shows them in their own layer)."""
        changed = False
        for key in list(self._unlooted)[:LOOTED_PER_PASS]:
            io = self._unlooted.pop(key)()
            record = self._object_records.get(key)
            if io is None or record is None:
                continue
            if self._is_looted(io, self._client):
                record["looted"] = 1  # in place: the published list holds this dict
                changed = True
            else:
                self._unlooted[key] = WeakPointer(io)  # to the back of the queue
        if changed:
            self._publish_objects()

    def _check_domes(self) -> None:
        """The air domes switched on / off since (their generator's button): their record's "dome" updated."""
        changed = False
        for key, pointer in list(self._domes.items()):
            io, record = pointer(), self._object_records.get(key)
            if io is None or record is None:
                self._domes.pop(key, None)
                continue
            if (dome := self._dome(io)) is not None and dome != record.get("dome"):
                record["dome"] = dome  # in place: the published list holds this dict
                changed = True
        if changed:
            self._publish_objects()

    def _check_health(self) -> None:
        """Objects with health (barrels...): their health now ("h" - hurt, it goes down), and killed ("kd": an exploded
        barrel stays, its wreck at 0 health - the page leaves it out)."""
        changed = False
        for key, pointer in list(self._damageable.items()):
            io, record = pointer(), self._object_records.get(key)
            if io is None or record is None:
                self._damageable.pop(key, None)
                continue
            if (health := Collector._health(io)) is not None and health[0] != record.get("h"):
                record["h"] = health[0]  # in place: the published list holds this dict
                changed = True
            # its element's icon: the frame learned since (a fire weapon seen: "fire" for Incindiary - inspector.py)
            if (enum := record.get("et")) and (frame := element_frame(enum)) and frame != record.get("el"):
                record["el"] = frame
                changed = True
            if record.get("plant"):
                continue  # (an elemental plant shot empty recharges: followed on, never "kd" - the page dims it at 0)
            if not record.get("kd") and Collector._killed(io, record):
                record["kd"] = 1
                self._damageable.pop(key, None)  # (nothing more to follow)
                changed = True
        if changed:
            self._publish_objects()

    @staticmethod
    def _killed(io: Any, record: dict[str, Any]) -> bool:
        """An object with health killed: its bHasBeenKilled (WillowInteractiveObject's), or its health down to 0 (an
        exploded barrel: its object stays - its wreck, another model - at 0)."""
        return bool(try_(lambda: io.bHasBeenKilled, False)) or ("m" in record and record.get("h", 1) <= 0)

    @staticmethod
    def _health(io: Any) -> tuple[float, float] | None:
        """An interactive object's (health, max) for the page (_vital / _vital_max) - its Health / MaxHealth (both
        games: WillowInteractiveObject's), when its definition can take damage (bCanTakeDirectDamage /
        bCanTakeRadiusDamage) and its max is above 0; else None."""
        definition = try_(lambda: io.InteractiveObjectDefinition)
        if definition is None or not (try_(lambda: bool(definition.bCanTakeDirectDamage), False)
                                      or try_(lambda: bool(definition.bCanTakeRadiusDamage), False)):
            return None
        top = try_(lambda: float(io.MaxHealth), 0.0)
        if top <= 0:
            return None
        return _vital(try_(lambda: float(io.Health), 0.0)), _vital_max(top)

    @staticmethod
    def _dome(io: Any) -> list[int] | None:
        """An air dome bubble's (the Pre-Sequel's IO_AirDome_Bubble_*): [its radius (uu), 1 on / 0 off] - its
        CollisionComponent, a SphereComponent: Bounds.BoxExtent its radius (1500 x the object's DrawScale), bAttached
        whether it's on (False until its generator's button is pushed: tools/probe_dome_state.txt). None without it."""
        comp = try_(lambda: io.CollisionComponent)
        radius = try_(lambda: float(comp.Bounds.BoxExtent.X), 0.0) if comp is not None else 0.0
        if radius <= 0:
            return None
        return [round(radius), 1 if try_(lambda: bool(comp.bAttached), False) else 0]

    @staticmethod
    def _is_looted(io: Any, client: bool = False) -> bool:
        """Opened, and no longer usable (bCanBeUsed[0] 1 -> 0). Opened: its SimpleAnimState is a bitmask over its
        animations (SimpleAnimInfo[].AnimName - tools/probe_prelooted.txt: Open, Open_Vacuum, Opened(_Idle),
        Closed(_Idle)), the "Opened..." one's bit set: closed 8 (Closed), just opened 14, looted and the level
        reloaded 12, spawned looted 4 (Opened alone), BL2's 7 - the state 7 alone (the first rule) missed all but the
        last. Without an "Opened" animation: the state 7. A co-op client (tools/probe_client_containers.txt): the
        state (replicated) but bCanBeUsed stays 1 - it isn't sent: the state alone there."""
        state = try_(lambda: int(io.SimpleAnimState), 0)
        anims = [try_(lambda a=a: str(a.AnimName), "") for a in try_(lambda: list(io.SimpleAnimInfo), []) or []]
        opened_bits = [n for n, name in enumerate(anims) if name.lower().startswith("opened")]
        opened = any(state >> n & 1 for n in opened_bits) if opened_bits else state == 7
        return opened and (client or not try_(lambda: io.bCanBeUsed[0], 1))

    @staticmethod
    def _lootable(io: Any, balance: Any) -> bool:
        """Has loot: its own Loot configurations, or its balance's default loot / loot lists."""
        return bool(
            try_(lambda: len(io.Loot), 0)
            or (balance is not None and (try_(lambda: len(balance.DefaultLoot), 0)
                                         or try_(lambda: len(balance.DefaultIncludedLootLists), 0))),
        )

    @staticmethod
    def _object_record(io: Any, client: bool = False) -> dict[str, Any]:
        loc = io.Location
        definition = try_(lambda: io.InteractiveObjectDefinition)
        # The game's name for it, in the game's language (e.g. "Incendiary Barrel"): the balance's
        # DefaultDisplayName, else its definition's StatusMenuMapInfoBoxHeader (what the game's map shows on hover: the
        # Pre-Sequel's "Oxygen Source", "Air Dome Generator" - no balance name, no target name), else what targeting
        # it shows
        balance = try_(lambda: io.BalanceDefinitionState.BalanceDefinition)
        display = (try_(lambda: str(balance.DefaultDisplayName), "")
                   or (try_(lambda: str(definition.StatusMenuMapInfoBoxHeader), "") if definition is not None else "")
                   or call_str(io.GetTargetName))
        record = {
            "i": addr(io),
            **named(display, def_name(definition), call_str(io.GetHumanReadableName), str(io.Class.Name)),
            "d": str(definition.Name) if definition is not None else "",
            "dp": try_(lambda: str(definition._path_name()), "") if definition is not None else "",  # (its panel's Details: in full)
            "c": io.Class.Name,
            "x": round(loc.X),
            "y": round(loc.Y),
            "z": round(loc.Z),
        }
        # an air dome's bubble (the Pre-Sequel's): its breathable area and whether it's on (its definition "_On" either
        # way - the name isn't the state)
        if definition is not None and "AirDome_Bubble" in str(definition.Name) and (dome := Collector._dome(io)):
            record["dome"] = dome
        elif definition is not None and "AirDome_Generator" in str(definition.Name):
            record["dg"] = 1  # its generator (its button switches a dome on - its own state: none that changes)
        elif definition is not None and "OxygenCracks" in str(definition.Name):
            record["o2"] = 1  # an oxygen fissure (IO_OxygenCracks, _Large, _NoMesh: "Oxygen Source" - refills Oz kits)
        # health (barrels, generators... - "h" / "m", the pawns' names: the page's health lines and bars as theirs), and
        # whether it explodes (its behaviours: a Behavior_Explode - its element from the explosion's damage type)
        if (health := Collector._health(io)) is not None:
            record["h"], record["m"] = health
            if not record.get("plant") and Collector._killed(io, record):
                record["kd"] = 1  # (killed already: an exploded barrel's wreck)
        # an elemental plant (the game's allegiance for them: inspector.plant_info) - the explosives' layer, but it
        # recharges: not killed at 0 health (_check_health)
        if definition is not None and (plant := try_(lambda: plant_info(definition), {})):
            record.update(plant)
        elif definition is not None and (explosion := try_(lambda: explosion_info(definition), {})):
            record.update(explosion)
        # a buff you use (the Pre-Sequel's Moxxtails, BL2's shrines: inspector.buff_info) - not a container, whatever loot
        # list its balance has (the Moxxtails': EpicChestRedLoot, never handed out). The other objects activating a skill
        # (a switch console, the Space Hurps, BL2's whiskey barrel, the raid bosses' ooze / orb...) spawn nothing and have
        # no loot; BL2's Ammo shrine neither (no list: left as it was). (Not its price: bought ones, and golden chests
        # too (golden keys), cost something - bCostsToUse / CostsToUseAmount, 0 before they're unlocked.)
        # costs something to use (its primary use: bCostsToUse[0], CostsToUseAmount[0] - the slot machines' 85 credits,
        # tools/probe_moxxtail.txt): the page's machines you pay (not a container: golden chests cost golden keys)
        if try_(lambda: io.bCostsToUse[0], 0) and (cost := try_(lambda: int(io.CostsToUseAmount[0]), 0)) > 0:
            record["cost"] = cost
        lootable = Collector._lootable(io, balance)
        if definition is not None and try_(lambda: buff_info(definition, lootable), False):
            record["buff"] = 1
        elif lootable:
            record["lootable"] = 1
            if try_(lambda: io.bCanBeUsed[0], 0):
                record["usable"] = 1  # for the usability hook: usable, then not = opened
            pools, slots, lists = loot_info(io, balance)
            if odds := try_(lambda: lootodds.container_odds(io, balance)):
                record["odds"] = odds  # each configuration's chance, its pools (their entries: the lootpools payload)
            if pools:
                record["loot"] = pools
            if lists:
                record["lists"] = lists  # the page: an "Epic..." list = a chest
            if slots:
                record["slots"] = slots  # the page sizes containers by it
            if Collector._is_looted(io, client):
                record["looted"] = 1
        return record

    @staticmethod
    def _exit_text(station: Any) -> str:
        """A mission waypoint on a map exit (the objective is in another map: a LevelTransitionWaypointComponent on a
        LevelTravelStation - no objective of its own, no WaypointInfo: tools/probe_waypoint_exit.txt): the game's words
        for it - the station's LevelTravelMapDisplayName ("Exit to %s") with its TravelDefinition's destination's
        DisplayName ("Frostburn Canyon"), in the game's language. "" if it isn't one / has none."""
        text = try_(lambda: str(station.LevelTravelMapDisplayName), "") or ""
        dest = try_(lambda: str(station.TravelDefinition.DestinationStationDefinition.DisplayName), "") or ""
        if not text or not dest:
            return ""
        return text.replace("%s", dest) if "%s" in text else f"{text} {dest}"

    def _pawn_info(self, pawn: Any, me: Any) -> dict[str, Any]:
        addr = pawn._get_address()
        if (info := self._info.get(addr)) is not None:
            return info
        if me is not None and addr == me._get_address():
            kind = "me"
        elif self._is(pawn, "WillowPlayerPawn"):
            kind = "player"
        elif self._is(pawn, "WillowVehicle"):
            kind = "vehicle"
        elif me is not None and try_(lambda: pawn.IsEnemy(me), False):
            kind = "enemy"
        else:
            kind = "npc"
        if kind in ("me", "player"):
            name = named(try_(lambda: str(player_info(pawn).PlayerName), ""), "Player")
        elif kind == "vehicle":
            # Its own name (VehicleClassDefinition.DisplayName, localized) - GetTargetName gives the
            # driver's once someone drives it
            name = named(try_(lambda: str(pawn.VehicleDef.DisplayName), "") or call_str(pawn.GetCustomizableName),
                         def_name(try_(lambda: pawn.VehicleDef)), str(pawn.Class.Name))
        else:
            # Its balance's per-playthrough DisplayName: what GetTargetName / GetMapDisplayName /
            # GetTransformedName give - read as a property: calling those crashed the game (a native
            # fatal error from call_str here, helios_crash.log, 2026-09-23, Tundra Express)
            name = named(pawn_display_name(pawn), def_name(try_(lambda: pawn.AIClass)), str(pawn.Class.Name))
            self._note_giver(addr, pawn, try_(lambda: pawn.MissionDirectives))  # the missions it gives / takes back
        info = {"i": f"{addr:x}", "k": kind, **name}
        # a boss: its AI class says so (AIClassDefinition.bBoss - both games: few - the Pre-Sequel's 7 of 266), or the game
        # has had it as the boss of a boss bar this level (GRI.BossPawn: Deadlift - _note_boss)
        if kind not in ("me", "player", "vehicle") and ((self.level_id, addr) in self._boss_pawns
                                                         or try_(lambda: bool(pawn.AIClass.bBoss), False)):
            info["boss"] = 1
        if level := exp_level(pawn):  # re-read at each scan (enemies can level up)
            info["l"] = level
        self._info[addr] = info
        return info

    def _note_boss(self, wi: Any) -> None:
        """The boss bar's pawn (WillowGameReplicationInfo.BossPawn while bHasBossBar - replicated: a co-op client's too):
        a boss for the rest of the level - AIClassDefinition.bBoss marks only a few (not Deadlift, the Pre-Sequel's).
        Its cached description flagged at once (the pawninfo payload sends it)."""
        gri = try_(lambda: wi.GRI)
        if gri is None or not try_(lambda: bool(field(gri, "bHasBossBar")), False):
            return
        boss = try_(lambda: field(gri, "BossPawn"))
        if boss is None:
            return
        key = try_(lambda: boss._get_address(), 0)
        if key and (self.level_id, key) not in self._boss_pawns:
            self._boss_pawns.add((self.level_id, key))
            if (info := self._info.get(key)) is not None:
                info["boss"] = 1

    def _is_gear(self, inv: Any) -> bool:
        """inspector.is_gear, per item class (cached by its address)."""
        key = inv.Class._get_address()
        if (gear := self._gear_classes.get(key)) is None:
            gear = self._gear_classes[key] = bool(try_(lambda: is_gear(inv), False))
        return gear

    def _pickup_info(self, p: Any) -> dict[str, Any]:
        addr = p._get_address()
        if (info := self._info.get(addr)) is not None:
            return info
        inv = try_(lambda: p.Inventory)
        name = item_name(inv)
        info = {
            "i": f"{addr:x}",
            **named(name, def_name(inv.Class) if inv is not None else "", str(p.Class.Name)),
            "c": inv.Class.Name if inv is not None else "",
            "q": try_(lambda: int(p.InventoryRarityLevel), 0),
        }
        if inv is not None and (level := exp_level(inv)):
            info["l"] = level
        kind = pickup_kind(inv)
        # its own icon (the game's: its definition's PickupFlagIcon - fx_shared_items...Credits, Ammo_SMG...: the
        # tooltip / panel, served by /texture/<path>.png) - any usable item's, of a known kind or not ("other")
        if kind or (inv is not None and inv.Class.Name == "WillowUsableItem"):
            if (icon := try_(lambda: inv.DefinitionData.ItemDefinition.PickupFlagIcon)) is not None:
                if path := try_(lambda: str(icon._path_name()), ""):
                    info["fi"] = path
        if kind:  # ammo / cash / eridium / health / oxygen / mission (the page's pickup layers)
            info["pk"] = kind
            # how much it gives (the tooltip: "$ 22", "18 rounds") - worked out from its definition (amounts.py)
            if kind in ("cash", "eridium", "ammo"):
                if amount := try_(lambda: pickup_amount(inv, current_playthrough() + 1)):
                    info["am"] = amount
        if (mission := pickup_mission(inv)) is not None:
            info["ms"] = mission
        # a pickup you pay for, sitting on an interactive object (a Moxxtail's drink, once they're on sale: bCostsToPickUp,
        # 10 moonstones - its Base the Moxxtail, which lists it in Attached: tools/probe_moxxtail_link.txt): "on" that
        # object (the page shows the object, with this price: [amount, its CostsToPickUpType's name])
        if try_(lambda: bool(p.bCostsToPickUp), False) and (base := try_(lambda: p.Base)) is not None \
                and try_(lambda: self._is(base, "WillowInteractiveObject"), False):
            info["on"] = f"{base._get_address():x}"  # (its id, as the object's record's "i": `addr` here is the pickup's)
            info["cost"] = [try_(lambda: int(p.CostsToPickUpAmount), 0),
                            str(getattr(try_(lambda: p.CostsToPickUpType), "name", "") or "")]
        self._info[addr] = info
        return info

    def _publish_state(self, now: float) -> None:
        pc = get_pc(possibly_loading=True)
        wi = ENGINE.GetCurrentWorldInfo()
        if pc is None or wi is None:
            return
        me = try_(lambda: pc.MyWillowPawn)
        view_yaw = try_(lambda: pc.Rotation.Yaw, 0)
        self._state_n += 1
        t0 = time.perf_counter()
        world_now = try_(lambda: float(wi.TimeSeconds), 0.0)
        self._skills.update(pc, world_now, now)
        self._check_scene(pc, wi, now)
        all_cinematic = try_(lambda: bool(field(wi.GRI, "bAllInCinematicMode")), False)  # every player in a cutscene
        self._note_boss(wi)
        t_skills = time.perf_counter()
        players = []  # player pawns seen this update (the skill reader forgets the others)
        pawns = []
        infos: list[dict[str, Any]] = []  # id, kind, name, level, max health / shield: sent apart, on change
        health = {}
        pawn = wi.PawnList
        for n in range(MAX_PAWNS):
            if pawn is None:
                break
            try:
                # Vehicle seats (a turret's gunner seat...) are pawns of their own, at the vehicle: the
                # vehicle and its passengers are already shown
                # (reader(): the per-update reads through properties looked up once - ~10x cheaper)
                get = reader(pawn)
                if not get("bDeleteMe") and not get("bIsDead") and not self._is_seat(pawn):
                    key = pawn._get_address()
                    new = key not in self._info  # (its description not cached yet: first seen, or since the last scan)
                    info = self._pawn_info(pawn, me)
                    is_player = info["k"] in ("me", "player")
                    loc = get("Location")
                    # Driving, a player's properties go wrong (seen: max health = health): the functions
                    vehicle = try_(lambda: get("DrivenVehicle")) if is_player else None
                    driving = vehicle is not None
                    if driving and try_(lambda v=vehicle: self._is_seat(v), False):  # a turret / gunner seat: its vehicle (on the map)
                        vehicle = self._seat_vehicle(vehicle) or vehicle
                    if driving and not self._drive_logged:
                        self._drive_logged = True
                        self._check_driving(pawn)
                    # Health / shield: properties (cheap) every update - but the NPCs' (not fighting: 50 walking
                    # around Sanctuary) every HEALTH_EVERY, staggered, new ones at once
                    stagger = (n + self._state_n) % HEALTH_EVERY
                    if driving:
                        hp = None
                    elif info["k"] == "npc" and stagger and key in self._health:
                        hp = self._health[key]
                    else:
                        hp = self._vitals_vars(get)
                    if hp is None:  # no usable properties: function calls, staggered
                        hp = self._health.get(key)
                        if hp is None or not stagger:
                            hp = self._vitals(pawn)
                    elif is_player and hp[3] and try_(lambda: get("Controller")) is not None:
                        # a player's shield from the functions: ShieldVar / ShieldMaxVar drop the fraction (57.70 read
                        # 57, the game showed 58 - its log's "vitals check"); ours, or everyone's on the host (a
                        # co-op client: the replicated properties only)
                        hp = (hp[0], hp[1], try_(pawn.GetShieldStrength, hp[2]) or 0.0, try_(pawn.GetMaxShieldStrength, hp[3]) or hp[3])
                    health[key] = hp
                    if new and len(self._vars_logged) < 3:  # (not per update: function calls, and a kind never met
                        self._check_vitals(pawn)             # - no vehicle around - kept it running for every pawn)
                    # A player respawning (dead, the New-U effect): the game parks the pawn somewhere,
                    # hidden - show where they'll come back instead (rs 1), or nothing if it doesn't say
                    # (rs 2: the position is meaningless)
                    if is_player:
                        players.append(pawn)
                    respawning, spot = self._respawn_state(pawn) if is_player else (False, None)
                    down = self._down_state(pawn) if is_player and not respawning else ""
                    skills = self._skills.player(pawn, now) if is_player else {}
                    if spot is not None:
                        loc = spot
                    # Its description ("pawninfo": sent on change) with its max health / shield (they rarely change)
                    hp_max, sh_max = _vital_max(hp[1]), _vital_max(hp[3])
                    oxygen = self._oxygen(pawn) if is_player else None  # (the Pre-Sequel's Oz meter; BL2: none)
                    infos.append({**info, **({"m": hp_max} if hp_max else {}), **({"sm": sh_max} if sh_max else {}),
                                  **({"om": _vital_max(oxygen[1])} if oxygen else {})})
                    extra = {
                        # the heading: the players' only (their arrows; the others are dots)
                        **({"r": view_yaw if info["k"] == "me" else get("Rotation").Yaw} if is_player else {}),
                        **({"s": _vital(hp[2])} if sh_max and hp[2] < hp[3] else {}),  # the shield: when not full
                        **({"ox": _vital(oxygen[0])} if oxygen and oxygen[0] < oxygen[1] else {}),  # oxygen: when not full
                        **({"vac": 1} if oxygen and self._in_vacuum(pawn) else {}),  # in a vacuum (else in air)
                        **({"rs": 1 if spot is not None else 2} if respawning else {}),
                        **({"dn": 1} if down == "crippled" else {"dd": 1} if down == "dead" else {}),
                        **({"mn": 1} if is_player and self._in_menu(pawn) else {}),
                        **({"ct": 1} if is_player and (all_cinematic or self._in_cutscene(pawn)) else {}),
                        # a vehicle's boost [left, max, seconds to full?] (its AfterburnerPool), when it has one
                        **({"bo": bo} if info["k"] == "vehicle" and (bo := self._boost(pawn, world_now)) else {}),
                        # driving: the vehicle's pawn id (a marker of its own, with its health)
                        **({"dv": dv} if driving and (dv := try_(lambda v=vehicle: f"{v._get_address():x}")) else {}),
                        **skills,
                    }
                    # What moves, compact (50 NPCs walking around Sanctuary: the stream's bulk): [id, x, y, z], then
                    # the health when not full, then the rest when there's any - data.js onState reads it back
                    row: list[Any] = [info["i"], round(loc.X), round(loc.Y), round(loc.Z)]
                    if hp_max and hp[0] < hp[1]:
                        row.append(_vital(hp[0]))
                    if extra:
                        row.append(extra)
                    pawns.append(row)
            except Exception as ex:  # noqa: BLE001
                log_error("pawn", ex)
            pawn = try_(lambda p=pawn: field(p, "NextPawn"))
        t_pawns = time.perf_counter()
        self._health = health  # drops the pawns that are gone
        self._skills.forget({a for a in (try_(lambda p=p: field(p, "Controller")._get_address()) for p in players) if a})
        pickups = []
        items: dict[str, dict[str, Any]] = {}  # the gear pickups' items (their cards: "items"), by id
        budget = ITEMS_PER_UPDATE
        for key, ptr in list(self._pickups.items()):
            p = ptr()
            if p is None:
                del self._pickups[key]
                continue
            try:
                if field(p, "bDeleteMe") or field(p, "bHidden"):
                    continue
                loc = field(p, "Location")
                pickup = {**self._pickup_info(p), "x": round(loc.X), "y": round(loc.Y), "z": round(loc.Z)}
                # Gear: its item's record (its card: stats, parts - the page's panel when it's clicked; the backpack's
                # own, by the item's address: dropped / picked up, the same item) - built a few per update (function
                # calls: a boss's loot pile over a few updates); its type / element icons' keys on the map marker
                inv = try_(lambda p=p: field(p, "Inventory"))
                if inv is not None and self._is_gear(inv):
                    item, built = try_(lambda inv=inv: ground_item(inv, budget > 0), (None, False))
                    budget -= built
                    if item is not None:
                        items[item["i"]] = item
                        pickup["it"] = item["i"]
                        pickup.update({k: item[k] for k in ("wt", "el") if k in item})
                pickups.append(pickup)
            except Exception as ex:  # noqa: BLE001
                log_error("pickup", ex)
        t_pickups = time.perf_counter()
        # Three record channels by how often they change (the stream grew fast with nothing moving - the user:
        # everything went out 10 times a second), each sending only what changed (Hub.publish_records): the pickups, the
        # pawns' descriptions, the state - what moves (only the pawns that did, with the time). Descriptions and pickups
        # first: a new pawn's arrives with (or before) its first move (the page waits for it anyway).
        self.hub.publish_records("items", "items", list(items.values()), {"level": self.level_id})  # (before their pickups)
        self.hub.publish_records("pickups", "pickups", pickups, {"level": self.level_id})
        self.hub.publish_records("pawninfo", "pawns", infos, {"level": self.level_id})
        paused = try_(lambda: field(wi, "Pauser") is not None, False)  # the game paused (its menu)
        self.hub.publish_records("state", "pawns", pawns, {"level": self.level_id, "hz": self.rate, **({"paused": 1} if paused else {})},
                                 {"t": round(now, 3)})  # (the time: not a change)
        t_end = time.perf_counter()
        if (t_end - t0) * 1000 > SLOW_MS:  # slow: which part (and how many pawns / pickups)
            for part, a, b in (("skills", t0, t_skills), ("pawns", t_skills, t_pawns), ("pickups", t_pawns, t_pickups),
                               ("json", t_pickups, t_end)):
                if (ms := (b - a) * 1000) > 1.0:
                    self._timings.add("state." + part, ms)
            self._timings.size("pawns", len(pawns))
            self._timings.size("pickups", len(pickups))

    @staticmethod
    def _down_state(pawn: Any) -> str:
        """"crippled" (down, fighting for their life), "dead" (died: ragdoll / death camera, before the
        respawn) or "". Seen in game (tools/probe_respawn.txt): crippled = InjuredState
        INJURED_Targeted + InjuredDeadState INJUREDDEAD_None; dead = InjuredState still
        INJURED_Targeted, InjuredDeadState INJUREDDEAD_InitRagdoll; respawning / fine: INJURED_Not.
        Plain property reads."""
        injured = getattr(try_(lambda: field(pawn, "InjuredState")), "name", None)
        if injured is None or injured == "INJURED_Not":
            return ""
        dead = getattr(try_(lambda: field(pawn, "InjuredDeadState")), "name", None)
        return "dead" if dead not in (None, "INJUREDDEAD_None") else "crippled"

    @staticmethod
    def _in_menu(pawn: Any) -> bool:
        """Whether the player has a menu open. Seen in game (tools/probe_menu.txt, co-op host, every
        player): PlayerReplicationInfo.bGFxMenuOpen 1 while any menu is open, the pawn's
        bViewingStatusMenu too while it's the status menu (inventory, map, skills). Both replicated,
        plain property reads."""
        if try_(lambda: bool(field(pawn, "bViewingStatusMenu")), False):
            return True
        pri = try_(lambda: field(pawn, "PlayerReplicationInfo"))
        return pri is not None and try_(lambda: bool(field(pri, "bGFxMenuOpen")), False)

    @staticmethod
    def _in_cutscene(pawn: Any) -> bool:
        """Whether the player is in a cutscene: their controller's cinematic mode (tools/probe_cutscene_watch.txt:
        the level script's SeqAct_ToggleCinematicMode -> SetCinematicMode, bCinematicMode True, the HUD
        hidden, input ignored - a video's too). Controllers: everyone's on the host, only yours on a
        co-op client (the GRI's bAllInCinematicMode covers all of them). Property reads."""
        controller = try_(lambda: field(pawn, "Controller"))
        return controller is not None and try_(lambda: bool(field(controller, "bCinematicMode")), False)

    @staticmethod
    def _respawn_state(pawn: Any) -> tuple[bool, Any]:
        """(respawning, where they'll come back or None). Seen in game (tools/probe_respawn.txt, during
        the respawn effect): the pawn hidden, parked somewhere (where: up to the game - never assumed),
        bAwaitingInjuredRespawn set, AwaitingRespawnResurrectLocation = the spot (at
        AwaitingRespawnTravelStation, a ResurrectTravelStation). Plain property reads."""
        if not try_(lambda: field(pawn, "bHidden"), False):
            return False, None
        if not any(try_(lambda f=f: bool(field(pawn, f)), False)
                   for f in ("bAwaitingInjuredRespawn", "bIsAwaitingRespawn", "bAwaitingRespawn")):
            return False, None
        spot = try_(lambda: field(pawn, "AwaitingRespawnResurrectLocation"))
        if spot is None or (spot.X == 0 and spot.Y == 0 and spot.Z == 0):
            return True, None
        return True, spot

    @staticmethod
    def _vitals_vars(get: Any) -> tuple[float, float, float, float] | None:
        """(health, max, shield, max shield) from the pawn's replicated properties (get: its reader()) - plain
        reads, much cheaper than the function calls. Verified on the player pawn (2026-09-23): HealthVar /
        HealthMaxVar exact, ShieldVar / ShieldMaxVar the shield rounded down. None if unusable."""
        hp_max = try_(lambda: float(get("HealthMaxVar")), 0.0)
        if not hp_max:
            return None
        sh_max = try_(lambda: float(get("ShieldMaxVar")), 0.0)
        return (
            try_(lambda: float(get("HealthVar")), 0.0),
            hp_max,
            try_(lambda: float(get("ShieldVar")), 0.0) if sh_max else 0.0,
            sh_max,
        )

    def _check_driving(self, pawn: Any) -> None:
        """Once: a driving player's health properties next to the functions, in the log (to verify
        which to trust while driving)."""
        log(f"vitals check (player driving) on {pawn.Name}: GetHealth={try_(pawn.GetHealth)}"
            f" GetMaxHealth={try_(pawn.GetMaxHealth)} HealthVar={try_(lambda: pawn.HealthVar)}"
            f" HealthMaxVar={try_(lambda: pawn.HealthMaxVar)}; vehicle {try_(lambda: pawn.DrivenVehicle.Name)}"
            f" GetHealth={try_(lambda: pawn.DrivenVehicle.GetHealth())} GetMaxHealth={try_(lambda: pawn.DrivenVehicle.GetMaxHealth())}")

    def _vitals(self, pawn: Any) -> tuple[float, float, float, float]:
        """(health, max health, shield, max shield) from the functions; the shield only asked for
        when it has one. The fallback for pawns whose properties read 0."""
        hp_max = try_(pawn.GetMaxHealth, 0) or 0
        hp = try_(pawn.GetHealth, 0) if hp_max else 0
        sh_max = try_(pawn.GetMaxShieldStrength, 0) if hasattr(pawn, "GetMaxShieldStrength") else 0
        sh = try_(pawn.GetShieldStrength, 0) if sh_max else 0
        return (hp, hp_max, sh or 0, sh_max or 0)

    def _check_vitals(self, pawn: Any) -> None:
        """Once per pawn kind: the properties next to the functions, in the log (to verify them)."""
        name = str(pawn.Class.Name)
        kind = "player" if "PlayerPawn" in name else "vehicle" if "Vehicle" in name else "ai"
        if kind in self._vars_logged:
            return
        hp, hp_max, sh, sh_max = self._vitals(pawn)
        if hp_max:
            self._vars_logged.add(kind)
            log(
                f"vitals check ({kind}) on {pawn.Name}: GetHealth={hp} GetMaxHealth={hp_max}"
                f" HealthVar={try_(lambda: pawn.HealthVar)} HealthMaxVar={try_(lambda: pawn.HealthMaxVar)};"
                f" GetShieldStrength={sh} GetMaxShieldStrength={sh_max}"
                f" ShieldVar={try_(lambda: pawn.ShieldVar)} ShieldMaxVar={try_(lambda: pawn.ShieldMaxVar)}"
                f" bHasShieldVar={try_(lambda: pawn.bHasShieldVar)}",
            )

    def _client_markers(self, tracker: Any, active_addr: int | None) -> list[dict[str, Any]]:
        """The objective markers on a co-op client, where the game registers no waypoint components
        (tools/probe_client_markers.txt): from the level's WillowWaypoint actors, each carrying its
        WaypointInfo {LinkedObjective, ObjectiveSetRestrictions} (tools/probe_client_waypoints.txt).
        One is shown - as the host's active components are - when its objective's mission is picked up,
        the objective isn't done, and it belongs to the mission's current step: one of its restrictions
        is a current objective set (ActiveObjectiveSet / SubObjectiveSets), or with none, the objective
        is in one. Property reads only. No quest givers (a client has nothing for them)."""
        entries = try_(lambda: tracker.MissionList)
        if entries is None:
            return []
        by_mission = {a: n for n, a in self._log.entry_addresses()}  # mission address -> MissionList index
        steps: dict[int, tuple[set[int], set[int], tuple[int, ...]] | None] = {}  # per mission, read once

        def current(mission: Any) -> tuple[set[int], set[int], tuple[int, ...]] | None:
            """(its current sets, their objectives, its progress) if picked up, else None."""
            key = mission._get_address()
            if key not in steps:
                steps[key] = None
                n = by_mission.get(key)
                entry = try_(lambda: entries[n]) if n is not None else None
                status = str(getattr(try_(lambda: entry.Status), "name", "")) if entry is not None else ""
                if status not in ("", "MS_NotStarted", "MS_Complete"):
                    sets = [s for s in [try_(lambda: entry.ActiveObjectiveSet)] + list(try_(lambda: list(entry.SubObjectiveSets), []) or [])
                            if s is not None]
                    objectives = {o._get_address() for s in sets for o in try_(lambda s=s: list(s.ObjectiveDefinitions), []) or []
                                  if o is not None}
                    progress = tuple(int(v) for v in try_(lambda: list(entry.ObjectivesProgress), []) or [])
                    steps[key] = ({s._get_address() for s in sets}, objectives, progress)
            return steps[key]

        markers = []
        for ptr in self._waypoints:
            w = ptr()
            if w is None:
                continue
            try:
                info = try_(lambda w=w: w.WaypointInfo)
                objective = try_(lambda: info.LinkedObjective)
                mission = try_(lambda o=objective: o.Outer) if objective is not None else None
                if mission is None or not hasattr(mission, "ObjectiveDefs") or (step := current(mission)) is None:
                    continue
                sets, objectives, progress = step
                restrictions = {s._get_address() for s in try_(lambda: list(info.ObjectiveSetRestrictions), []) or [] if s is not None}
                if not (restrictions & sets if restrictions else objective._get_address() in objectives):
                    continue
                i = _mission_index(mission).get(objective._get_address())
                if i is not None and i < len(progress) and progress[i] >= (try_(lambda o=objective: int(o.ObjectiveCount), 1) or 1):
                    continue  # done
                loc = w.Location
                markers.append({
                    "i": addr(w),
                    "k": "objective",
                    "x": round(loc.X),
                    "y": round(loc.Y),
                    "z": round(loc.Z),
                    "rad": try_(lambda w=w: int(w.AreaRadius), 0) or 0,
                    "tracked": mission._get_address() == active_addr,
                    "mission": named(try_(lambda m=mission: str(m.MissionName), ""), def_name(mission)),
                    "objective": named(try_(lambda o=objective: str(o.ProgressMessage), ""), def_name(objective)),
                })
            except Exception as ex:  # noqa: BLE001
                log_error("client mission marker", ex)
        return markers

    def _npc_givers(self, active_addr: int | None, skip: set[int]) -> list[dict[str, Any]]:
        """Quest-giver markers ("!") worked out from the NPCs' / objects' own lists of missions they give /
        take back (_note_giver: NPCs, the bounty board) against the mission log - a mission it gives
        that can be picked up now, or one it takes back that's ready to hand in (MissionLog
        .giver_states). A co-op client has no directive waypoints at all, and the host's miss givers
        too (Sanctuary, 2026-09-24: Marcus offering Rock, Paper, Genocide, only the tracked objective
        registered). The same markers as the game's ("directive"), one per NPC / object: its first such
        mission ("mission" / "mi") and every one ("list": {i, n, end: 1 for one to hand in} - an NPC or
        the bounty board can have several); skip: the ones (addresses) that already have one from the
        game. Property reads only."""
        markers = []
        states = self._log.giver_states() if self._givers else {}
        for key, (ptr, directives) in list(self._givers.items()):
            giver = ptr()  # an NPC, or an object (the bounty board)
            if giver is None:
                del self._givers[key]
                continue
            if key in skip:
                continue
            try:
                listed, tracked = [], False
                for mission, begins, ends in directives:
                    mid = mission_id(mission)
                    state = states.get(mid, "")
                    if ((state == "begin" and begins) or (state == "end" and ends)) and all(e["i"] != mid for e in listed):
                        entry = {"i": mid, **named(try_(lambda m=mission: str(m.MissionName), ""), def_name(mission))}
                        if state == "end":
                            entry["end"] = 1
                        listed.append(entry)
                        tracked = tracked or mission._get_address() == active_addr
                if listed:
                    loc, first = giver.Location, listed[0]
                    markers.append({
                        "i": f"g{key:x}", "k": "directive", "x": round(loc.X), "y": round(loc.Y), "z": round(loc.Z),
                        "rad": 0, "tracked": tracked, "mission": {k: v for k, v in first.items() if k not in ("i", "end")},
                        "mi": first["i"], "by": f"{key:x}", "list": listed,
                    })
            except Exception as ex:  # noqa: BLE001
                log_error("quest giver", ex)
        return markers

    def _publish_missions(self) -> None:
        """Quest markers the game shows: every mission waypoint component that is bActive.

        Verified in game (tools/probe_missions.py): MissionTracker.MissionWaypoints[] = {Mission,
        Waypoints[]}, the waypoints being MissionObjectiveWaypointComponent (an objective: WaypointInfo.
        LinkedObjective) or MissionDirectiveWaypointComponent (a quest giver / turn-in, on an NPC);
        only the displayed ones are bActive. The marker sits on the component's Owner: a
        WillowWaypoint whose AreaRadius > 0 is an area ("somewhere in this circle"), 0 a point.
        """
        tracker = self._tracker() if self._tracker is not None else None
        if tracker is None:
            return
        active = try_(lambda: tracker.ActiveMission)
        active_addr = active._get_address() if active is not None else None
        markers, giver_npcs = [], set()
        states = None  # the log's missions to pick up / hand in (giver_states): read once, for the game's directives
        for entry in try_(lambda: list(tracker.MissionWaypoints), []):
            mission = try_(lambda e=entry: e.Mission)
            for comp in try_(lambda e=entry: list(e.Waypoints), []):
                try:
                    if comp is None or not comp.bActive or (owner := comp.Owner) is None:
                        continue
                    loc = owner.Location
                    objective = try_(lambda c=comp: c.WaypointInfo.LinkedObjective)
                    kind = "directive" if "Directive" in str(comp.Class.Name) else "objective"
                    if kind == "directive":
                        giver_npcs.add(owner._get_address())  # ("by": the page links the NPC / object)
                    marker = {
                        "i": addr(comp),
                        "k": kind,
                        "x": round(loc.X),
                        "y": round(loc.Y),
                        "z": round(loc.Z),
                        "rad": try_(lambda o=owner: int(owner.AreaRadius), 0) or 0,
                        "tracked": mission is not None and mission._get_address() == active_addr,
                        "mission": named(try_(lambda m=mission: str(m.MissionName), ""), def_name(mission)),
                    }
                    if mission is not None:
                        marker["mi"] = mission_id(mission)  # (the page links its mission in the log)
                    if kind == "directive":
                        marker["by"] = addr(owner)
                        # its mission ready to hand in: the page's turn-in "?" (the game's directive has no such flag)
                        if states is None:
                            states = try_(lambda: self._log.giver_states(), {}) or {}
                        if mission is not None and states.get(mission_id(mission)) == "end":
                            marker["end"] = 1
                    if objective is not None:
                        marker["objective"] = named(try_(lambda o=objective: str(o.ProgressMessage), ""), def_name(objective))
                    elif (exit_text := self._exit_text(owner)):
                        marker["objective"] = named(exit_text, "")  # (a map exit the objective is past: "Exit to ...")
                    markers.append(marker)
                except Exception as ex:  # noqa: BLE001
                    log_error("mission marker", ex)
        if not markers and self._waypoints:  # a co-op client: none registered here
            markers = self._client_markers(tracker, active_addr)
        markers += self._npc_givers(active_addr, giver_npcs)
        payload = {
            "level": self.level_id,
            "tracked": named(try_(lambda: str(active.MissionName), ""), def_name(active)) if active is not None else None,
            "markers": markers,
        }
        missions_json = json.dumps(payload, separators=(",", ":"))
        if missions_json != self._missions_json:
            self._missions_json = missions_json
            self.hub.publish("missions", missions_json)
        # The mission log's fast pass: the tracked / active missions' objectives, every second
        if not self._log.fast(tracker):
            self._next_log = 0.0  # the list changed (a mission started...): a full pass next tick
        self._publish_log()

    def _full_log(self) -> None:
        """One step of the full pass; published when the cycle completes."""
        tracker = self._tracker() if self._tracker is not None else None
        if tracker is not None and self._log.step(tracker, self._player_controllers):
            self._publish_log()
            self._update_area_level()

    def _update_area_level(self) -> None:
        """The level of the area the player is in, as the game has it: the game stage of the regions
        this map's missions use (tools/probe_region.txt: Tundra Express -> Tundra, stage 13; enemies
        12-15; a region not visited yet: -1, left out) - "lv": [lowest, highest] in the level payload,
        republished when it changes. A few function calls, after each full mission pass."""
        level = self._level
        pc = get_pc(possibly_loading=True)
        if not level or not level.get("map") or pc is None:
            return
        stages = sorted({s for r in self._log.map_regions(level["map"])
                         if (s := try_(lambda r=r: int(pc.GetGameStageFromRegion(r)), 0)) > 0})
        lv = [stages[0], stages[-1]] if stages else None
        if lv != level.get("lv"):
            self._set_level({**{k: v for k, v in level.items() if k != "lv"}, **({"lv": lv} if lv else {})}, keep_lv=False)

    @staticmethod
    def _player_controllers() -> list[Any]:
        """The local controller, then every other player's the game has here (the host has them all;
        a co-op client only its own)."""
        pcs, seen = [], set()
        local = get_pc(possibly_loading=True)
        wi = ENGINE.GetCurrentWorldInfo()
        pawn = try_(lambda: wi.PawnList)
        candidates = [local]
        for _ in range(MAX_PAWNS):
            if pawn is None:
                break
            if "PlayerPawn" in str(pawn.Class.Name):
                candidates.append(try_(lambda p=pawn: p.Controller))
            pawn = try_(lambda p=pawn: p.NextPawn)
        for pc in candidates:
            if pc is not None and hasattr(pc, "PlayerReplicationInfo") and pc._get_address() not in seen:
                seen.add(pc._get_address())
                pcs.append(pc)
        return pcs

    def _publish_log(self) -> None:
        """The mission log, only when something in it changed (definitions are cached: a change is
        a status / progress / current step / tracked mission)."""
        if self._log.defs_dirty:  # the definitions: static, only when the list changes (large: texts - the new ones go out)
            self.hub.publish_records("missiondefs", "missions", self._log.defs_payload()["missions"])
        if self._log.dirty:  # the live part: small
            live = self._log.payload(self.level_id)
            self.hub.publish_records("missionlog", "missions", live.pop("missions"), live)

    def _publish_players(self) -> None:
        wi = ENGINE.GetCurrentWorldInfo()
        pc = get_pc(possibly_loading=True)
        if wi is None or pc is None:
            return
        players = read_players(wi, try_(lambda: pc.MyWillowPawn), pc)
        self.hub.publish_records("players", "players", players, {"level": self.level_id})  # (only the fields that changed go out)

    # endregion
