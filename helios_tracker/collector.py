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
import sys
import threading
import time
from pathlib import Path
from typing import Any

import unrealsdk
from mods_base import ENGINE, get_pc
from unrealsdk.unreal import WeakPointer

from .inspector import read_players
from .missions import MissionLog
from .skills import SkillReader
from .server import Hub
from .tacmap import MapImage, load_tactical_map
from .util import (addr, call_str, clear_fields, def_name, exp_level, field, item_name, log, log_error, named,
                   pickup_kind, player_info, rarity_table, try_)

MOVIE_SCALE = 4  # movie px per volume "pixel": UnrealUnitsPerPixel is 32, the fit gave 128 uu / px
LEVEL_CHECK_EVERY = 1.0  # s
SCAN_EVERY = 120.0  # s between full pickup scans: a safety net, new ones come from the spawn hook
                    # (each find_all walks every object in the game: ~10 ms, a hitch - measured)
HEALTH_EVERY = 4  # updates between health reads of a pawn (function calls: the costly part of an update)
OBJECTS_EVERY = 120.0  # s between full interactive object scans: a safety net (~11 ms); objects that
                       # spawn / get their balance / are destroyed later come from hooks
PLAYERS_EVERY = 2.0  # s between player inspections (gear, backpack, skills)
MISSIONS_EVERY = 1.0  # s between quest marker reads (owners can move: escorts, NPCs); also the
                      # mission log's fast pass (the tracked / active missions only)
MISSION_LOG_EVERY = 5.0  # s between full mission log passes (every mission's status: ~290 entries)
MAX_PAWNS = 1000  # PawnList walk guard
LOOTED_EVERY = 1.0  # s between checks of unlooted containers (two property reads each, round robin)
LOOTED_PER_PASS = 60
SLOW_MS = 4.0  # a task taking longer than this on the game thread is reported (it can cause a hitch)
RECORDS_SECONDS = 0.002  # per tick, building the records of newly found interactive objects (a scan's backlog)
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


def pretty_map_name(name: str) -> str:
    """ "SouthernShelf_P" -> "Southern Shelf" (fallback; no localized lookup)."""
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
    """Extracted map images per (package file, mtime, movie): revisiting a level is free."""

    def __init__(self, size: int = 4) -> None:
        self._size = size
        self._items: dict[tuple[str, float, str], list[MapImage]] = {}
        self._lock = threading.Lock()

    def get(self, pkg_file: Path, movie: str) -> list[MapImage]:
        key = (str(pkg_file).lower(), pkg_file.stat().st_mtime, movie.lower())
        with self._lock:
            if key in self._items:
                return self._items[key]
        images = load_tactical_map(pkg_file, movie)
        with self._lock:
            self._items[key] = images
            while len(self._items) > self._size:
                del self._items[next(iter(self._items))]
        return images


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
        self._next_scan = 0.0
        self._next_objects = 0.0
        self._next_players = 0.0
        self._players_json = ""
        self._next_missions = 0.0
        self._missions_json = ""
        self._tracker: WeakPointer | None = None  # the MissionTracker, found at each scan
        self._next_log = 0.0
        self._log = MissionLog()
        self._active = False  # a page was connected last tick
        self._pickups: dict[int, WeakPointer] = {}  # by address: from scans and the spawn hook
        # pawn address -> (health, max, shield, shield max), read every HEALTH_EVERY updates
        self._health: dict[int, tuple[float, float, float, float]] = {}
        self._skills = SkillReader()  # every player's action skill, timed effects, melee cooldown
        self._state_n = 0
        self._info: dict[int, dict[str, Any]] = {}  # per-actor cached name/kind, by address
        self._objects_json = "[]"
        # Interactive objects don't move or get renamed: each record is built once per level
        self._object_records: dict[tuple[int, str], dict[str, Any] | None] = {}
        self._objects: dict[tuple[int, str], dict[str, Any]] = {}  # what the objects payload shows
        self._objects_dirty = False  # hooks changed it: publish on the next tick (batched)
        # objects a scan found, their record not built yet: built a few per tick (a level's first scan
        # has hundreds: one long hitch otherwise)
        self._pending_records: dict[tuple[int, str], WeakPointer] = {}
        self._unlooted: dict[tuple[int, str], WeakPointer] = {}  # lootable containers not opened yet
        self._next_looted = 0.0

    # region Level

    def tick(self, now: float) -> None:
        run = self._timings.run
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
            self._next_scan = self._next_objects = self._next_players = self._next_missions = self._next_log = 0.0
            self._log.dirty = self._log.defs_dirty = True  # the new page needs the log
            self._objects_json = self._players_json = self._missions_json = ""
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
        if now >= self._next_looted and self._unlooted:
            self._next_looted = now + LOOTED_EVERY
            run("looted", self._check_looted)

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
        level: dict[str, Any] = {"id": level_id, "map": name, "name": pretty_map_name(name), "images": [],
                                 "rarity": try_(rarity_table, {}) or {}}  # the game's rarity colours
        if vol is None or movie is None:
            level["status"] = "none"
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

    def _set_level(self, level: dict[str, Any]) -> None:
        with self._lock:
            if level["id"] != self.level_id:
                return  # a newer level already
            self._level = level
            self.hub.publish("level", json.dumps(level))

    def _extract(self, level: dict[str, Any], map_name: str, movie: str) -> None:
        """Background thread: files only, no UObjects."""
        level_id = level["id"]
        try:
            package = package_path(f"{map_name}.upk")  # the base game's, or a DLC's
            if package is None:
                raise FileNotFoundError(f"couldn't find {map_name}.upk (WillowGame/CookedPCConsole, DLC/*/*/Content)")
            images = self._images.get(package, movie)
        except Exception as ex:  # noqa: BLE001
            log_error("map extraction", ex)
            level.update(status="error", error=f"{type(ex).__name__}: {ex}")
            self._set_level(level)
            return
        self.hub.set_images(level_id, [img.data for img in images])
        level["images"] = [
            {
                "url": f"/image/{level_id}/{n}",
                "name": img.name,
                "format": img.format,
                "width": img.width,
                "height": img.height,
                "bounds": img.bounds,
            }
            for n, img in enumerate(images)
        ]
        level["status"] = "ready" if images else "none"
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
        chain, cached per class."""
        cls = pawn.Class
        key = ("seat", str(cls.Name))
        if key not in self._classes:
            c, seat = cls, False
            while c is not None and not seat:
                seat = "WeaponPawn" in str(c.Name)
                c = try_(lambda c=c: c.SuperField)
            self._classes[key] = seat
        return self._classes[key]

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
        for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
            try:
                key = (io._get_address(), str(io.Name))
                if key not in records:  # new: its record is built later, a few per tick
                    self._pending_records.setdefault(key, WeakPointer(io))
                    continue
                if (record := records[key]) is not None and not io.bHidden and not io.bDeleteMe:
                    objects[key] = record
                    if record.get("lootable") and not record.get("looted"):
                        self._unlooted.setdefault(key, WeakPointer(io))
            except Exception as ex:  # noqa: BLE001
                log_error("interactive object", ex)
        self._objects = objects
        if self._tracker is None or self._tracker() is None:  # one per game: only look it up again if gone
            self._tracker = next(
                (WeakPointer(t) for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")),
                None,
            )
        self._publish_objects()

    def _build_pending_records(self) -> None:
        """The records of objects a scan found, within RECORDS_SECONDS per tick; shown as they're built."""
        deadline = time.perf_counter() + RECORDS_SECONDS
        records = self._object_records
        while self._pending_records and time.perf_counter() < deadline:
            key, ptr = next(iter(self._pending_records.items()))
            del self._pending_records[key]
            io = ptr()
            if io is None or key in records:
                continue
            try:
                records[key] = self._object_record(io) if self._in_world(io) else None
                if (record := records[key]) is not None and not io.bHidden and not io.bDeleteMe:
                    self._objects[key] = record
                    self._objects_dirty = True
                    if record.get("lootable") and not record.get("looted"):
                        self._unlooted.setdefault(key, WeakPointer(io))
            except Exception as ex:  # noqa: BLE001
                log_error("interactive object", ex)

    def _publish_objects(self) -> None:
        objects = list(self._objects.values())
        objects_json = json.dumps({"level": self.level_id, "objects": objects}, separators=(",", ":"))
        if objects_json != self._objects_json:
            self._objects_json = objects_json
            self.hub.publish("objects", objects_json)

    # From hooks (game thread): objects that spawn / get their balance (display name) / go away after
    # the level loaded - e.g. hazards spawned when an area activates. Before the level is known, or
    # with no page open, they're left to the next scan.

    def object_spawned(self, io: Any) -> None:
        if self._level_key is None or not self.hub.clients or not self._in_world(io):
            return
        key = (io._get_address(), str(io.Name))
        self._object_records[key] = record = self._object_record(io)
        if not io.bHidden:
            self._objects[key] = record
            self._objects_dirty = True
            if record.get("lootable") and not record.get("looted"):
                self._unlooted[key] = WeakPointer(io)

    def object_destroyed(self, io: Any) -> None:
        key = (io._get_address(), str(io.Name))
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
            if self._is_looted(io):
                record["looted"] = 1  # in place: the published list holds this dict
                changed = True
            else:
                self._unlooted[key] = WeakPointer(io)  # to the back of the queue
        if changed:
            self._publish_objects()

    @staticmethod
    def _is_looted(io: Any) -> bool:
        """Opened (verified in game, tools/probe_containers.txt): an opened container's animation
        state is 7 and it's no longer usable (bCanBeUsed[0] 1 -> 0); unopened ones are 4 / usable."""
        return try_(lambda: int(io.SimpleAnimState), 0) == 7 and not try_(lambda: io.bCanBeUsed[0], 1)

    @staticmethod
    def _lootable(io: Any, balance: Any) -> bool:
        """Has loot: its own Loot configurations, or its balance's default loot / loot lists."""
        return bool(
            try_(lambda: len(io.Loot), 0)
            or (balance is not None and (try_(lambda: len(balance.DefaultLoot), 0)
                                         or try_(lambda: len(balance.DefaultIncludedLootLists), 0))),
        )

    @staticmethod
    def _object_record(io: Any) -> dict[str, Any]:
        loc = io.Location
        definition = try_(lambda: io.InteractiveObjectDefinition)
        # The game's name for it, in the game's language (e.g. "Incendiary Barrel"): the balance's
        # DefaultDisplayName, else what targeting it shows
        balance = try_(lambda: io.BalanceDefinitionState.BalanceDefinition)
        display = try_(lambda: str(balance.DefaultDisplayName), "") or call_str(io.GetTargetName)
        record = {
            "i": addr(io),
            **named(display, def_name(definition), call_str(io.GetHumanReadableName), str(io.Class.Name)),
            "d": str(definition.Name) if definition is not None else "",
            "c": io.Class.Name,
            "x": round(loc.X),
            "y": round(loc.Y),
            "z": round(loc.Z),
        }
        if Collector._lootable(io, balance):
            record["lootable"] = 1
            if try_(lambda: io.bCanBeUsed[0], 0):
                record["usable"] = 1  # for the usability hook: usable, then not = opened
            pools, slots, lists = loot_info(io, balance)
            if pools:
                record["loot"] = pools
            if lists:
                record["lists"] = lists  # the page: an "Epic..." list = a chest
            if slots:
                record["slots"] = slots  # the page sizes containers by it
            if Collector._is_looted(io):
                record["looted"] = 1
        return record

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
            # What the game shows when aiming at it; else the map's name, or the transformed variant
            # (the AIPawnBalanceDefinition's per-playthrough DisplayName behind all three)
            game_name = next((text for fn in ("GetTargetName", "GetMapDisplayName", "GetTransformedName")
                              if hasattr(pawn, fn) and (text := call_str(getattr(pawn, fn)))), "")
            name = named(game_name, def_name(try_(lambda: pawn.AIClass)), str(pawn.Class.Name))
        info = {"i": f"{addr:x}", "k": kind, **name}
        if level := exp_level(pawn):  # re-read at each scan (enemies can level up)
            info["l"] = level
        self._info[addr] = info
        return info

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
        if kind := pickup_kind(inv):  # ammo / cash / eridium / health (the page's pickup layers)
            info["pk"] = kind
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
        self._skills.update(pc, try_(lambda: float(wi.TimeSeconds), 0.0), now)
        t_skills = time.perf_counter()
        players = []  # player pawns seen this update (the skill reader forgets the others)
        pawns = []
        health = {}
        pawn = wi.PawnList
        for n in range(MAX_PAWNS):
            if pawn is None:
                break
            try:
                # Vehicle seats (a turret's gunner seat...) are pawns of their own, at the vehicle: the
                # vehicle and its passengers are already shown
                # (field(): the per-update reads through properties looked up once - ~10x cheaper)
                if not field(pawn, "bDeleteMe") and not field(pawn, "bIsDead") and not self._is_seat(pawn):
                    info = self._pawn_info(pawn, me)
                    loc = field(pawn, "Location")
                    # Health / shield: function calls, so each pawn is read every HEALTH_EVERY
                    # updates (staggered), new ones at once
                    key = pawn._get_address()
                    # Driving, a player's properties go wrong (seen: max health = health): the functions
                    driving = info["k"] in ("me", "player") and try_(lambda p=pawn: field(p, "DrivenVehicle")) is not None
                    if driving and not self._drive_logged:
                        self._drive_logged = True
                        self._check_driving(pawn)
                    hp = None if driving else self._vitals_vars(pawn)  # cheap properties: every update
                    if hp is None:  # no usable properties: function calls, staggered
                        hp = self._health.get(key)
                        if hp is None or (n + self._state_n) % HEALTH_EVERY == 0:
                            hp = self._vitals(pawn)
                    health[key] = hp
                    if len(self._vars_logged) < 3:
                        self._check_vitals(pawn)
                    # A player respawning (dead, the New-U effect): the game parks the pawn somewhere,
                    # hidden - show where they'll come back instead (rs 1), or nothing if it doesn't say
                    # (rs 2: the position is meaningless)
                    is_player = info["k"] in ("me", "player")
                    if is_player:
                        players.append(pawn)
                    respawning, spot = self._respawn_state(pawn) if is_player else (False, None)
                    down = self._down_state(pawn) if is_player and not respawning else ""
                    skills = self._skills.player(pawn, now) if is_player else {}
                    if spot is not None:
                        loc = spot
                    pawns.append(
                        {
                            **info,
                            "x": round(loc.X),
                            "y": round(loc.Y),
                            "z": round(loc.Z),
                            "r": view_yaw if info["k"] == "me" else field(pawn, "Rotation").Yaw,
                            "h": hp[0],
                            "m": hp[1],
                            **({"s": hp[2], "sm": hp[3]} if hp[3] else {}),
                            **({"rs": 1 if spot is not None else 2} if respawning else {}),
                            **({"dn": 1} if down == "crippled" else {"dd": 1} if down == "dead" else {}),
                            **({"mn": 1} if is_player and self._in_menu(pawn) else {}),
                            **skills,
                        },
                    )
            except Exception as ex:  # noqa: BLE001
                log_error("pawn", ex)
            pawn = try_(lambda p=pawn: field(p, "NextPawn"))
        t_pawns = time.perf_counter()
        self._health = health  # drops the pawns that are gone
        self._skills.forget({a for a in (try_(lambda p=p: field(p, "Controller")._get_address()) for p in players) if a})
        pickups = []
        for key, ptr in list(self._pickups.items()):
            p = ptr()
            if p is None:
                del self._pickups[key]
                continue
            try:
                if field(p, "bDeleteMe") or field(p, "bHidden"):
                    continue
                loc = field(p, "Location")
                pickups.append({**self._pickup_info(p), "x": round(loc.X), "y": round(loc.Y), "z": round(loc.Z)})
            except Exception as ex:  # noqa: BLE001
                log_error("pickup", ex)
        t_pickups = time.perf_counter()
        state = {"level": self.level_id, "t": round(now, 3), "hz": self.rate, "pawns": pawns, "pickups": pickups}
        self.hub.publish("state", json.dumps(state, separators=(",", ":")))
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
    def _vitals_vars(pawn: Any) -> tuple[float, float, float, float] | None:
        """(health, max, shield, max shield) from the pawn's replicated properties - plain reads, much
        cheaper than the function calls. Verified on the player pawn (2026-09-23): HealthVar /
        HealthMaxVar exact, ShieldVar / ShieldMaxVar the shield rounded down. None if unusable."""
        hp_max = try_(lambda: float(field(pawn, "HealthMaxVar")), 0.0)
        if not hp_max:
            return None
        sh_max = try_(lambda: float(field(pawn, "ShieldMaxVar")), 0.0)
        return (
            try_(lambda: float(field(pawn, "HealthVar")), 0.0),
            hp_max,
            try_(lambda: float(field(pawn, "ShieldVar")), 0.0) if sh_max else 0.0,
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
        markers = []
        for entry in try_(lambda: list(tracker.MissionWaypoints), []):
            mission = try_(lambda e=entry: e.Mission)
            for comp in try_(lambda e=entry: list(e.Waypoints), []):
                try:
                    if comp is None or not comp.bActive or (owner := comp.Owner) is None:
                        continue
                    loc = owner.Location
                    objective = try_(lambda c=comp: c.WaypointInfo.LinkedObjective)
                    marker = {
                        "i": addr(comp),
                        "k": "directive" if "Directive" in str(comp.Class.Name) else "objective",
                        "x": round(loc.X),
                        "y": round(loc.Y),
                        "z": round(loc.Z),
                        "rad": try_(lambda o=owner: int(owner.AreaRadius), 0) or 0,
                        "tracked": mission is not None and mission._get_address() == active_addr,
                        "mission": named(try_(lambda m=mission: str(m.MissionName), ""), def_name(mission)),
                    }
                    if objective is not None:
                        marker["objective"] = named(try_(lambda o=objective: str(o.ProgressMessage), ""), def_name(objective))
                    markers.append(marker)
                except Exception as ex:  # noqa: BLE001
                    log_error("mission marker", ex)
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
        if self._log.defs_dirty:  # the definitions: static, only when the list changes (large: texts)
            self.hub.publish("missiondefs", json.dumps(self._log.defs_payload(), separators=(",", ":")))
        if self._log.dirty:  # the live part: small
            self.hub.publish("missionlog", json.dumps(self._log.payload(self.level_id), separators=(",", ":")))

    def _publish_players(self) -> None:
        wi = ENGINE.GetCurrentWorldInfo()
        pc = get_pc(possibly_loading=True)
        if wi is None or pc is None:
            return
        players = read_players(wi, try_(lambda: pc.MyWillowPawn), pc)
        players_json = json.dumps({"level": self.level_id, "players": players}, separators=(",", ":"))
        if players_json != self._players_json:  # gear rarely changes: only send changes
            self._players_json = players_json
            self.hub.publish("players", players_json)

    # endregion
