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
from .server import Hub
from .tacmap import MapImage, load_tactical_map
from .util import addr, call_str, def_name, exp_level, log, log_error, named, try_

MOVIE_SCALE = 4  # movie px per volume "pixel": UnrealUnitsPerPixel is 32, the fit gave 128 uu / px
LEVEL_CHECK_EVERY = 1.0  # s
SCAN_EVERY = 120.0  # s between full pickup scans: a safety net, new ones come from the spawn hook
                    # (each find_all walks every object in the game: ~10 ms, a hitch - measured)
HEALTH_EVERY = 4  # updates between health reads of a pawn (function calls: the costly part of an update)
OBJECTS_EVERY = 120.0  # s between full interactive object scans: a safety net (~11 ms); objects that
                       # spawn / get their balance / are destroyed later come from hooks
PLAYERS_EVERY = 2.0  # s between player inspections (gear, backpack, skills)
MISSIONS_EVERY = 1.0  # s between quest marker reads (owners can move: escorts, NPCs)
MAX_PAWNS = 1000  # PawnList walk guard
SLOW_MS = 4.0  # a task taking longer than this on the game thread is reported (it can cause a hitch)
SLOW_REPORT_EVERY = 30.0  # s between console reports of slow tasks


class _Timings:
    """Measures the collector's tasks; reports the slow ones to the console now and then."""

    def __init__(self) -> None:
        self._slow: dict[str, list[float]] = {}
        self._next_report = 0.0

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
            log(f"slow game-thread tasks (> {SLOW_MS:.0f} ms) in the last {SLOW_REPORT_EVERY:.0f} s: {', '.join(parts)}")
            self._slow.clear()


def cooked_dir() -> Path | None:
    """WillowGame/CookedPCConsole of this install (the mod folder may be a junction elsewhere)."""
    candidates = [Path(sys.executable).parent.parent.parent]  # Binaries/Win32/Borderlands2.exe
    candidates += list(Path(__file__).absolute().parents)  # sdk_mods/helios_tracker/... (unresolved)
    for base in candidates:
        d = base / "WillowGame" / "CookedPCConsole"
        if d.is_dir():
            return d
    return None


def pretty_map_name(name: str) -> str:
    """ "SouthernShelf_P" -> "Southern Shelf" (fallback; no localized lookup)."""
    base = name.removesuffix("_P").removesuffix("_p").replace("_", " ")
    out = []
    for i, ch in enumerate(base):
        if i and ch.isupper() and base[i - 1].islower():
            out.append(" ")
        out.append(ch)
    return "".join(out)


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
        self._hook_seen = False
        self.reset()

    def reset(self) -> None:
        """Forget the level (re-detected, and re-published, on the next tick)."""
        self._level_key = None
        self._next_level_check = 0.0
        self._clear_contents()

    def _clear_contents(self) -> None:
        self._next_scan = 0.0
        self._next_objects = 0.0
        self._next_players = 0.0
        self._players_json = ""
        self._next_missions = 0.0
        self._missions_json = ""
        self._tracker: WeakPointer | None = None  # the MissionTracker, found at each scan
        self._active = False  # a page was connected last tick
        self._pickups: dict[int, WeakPointer] = {}  # by address: from scans and the spawn hook
        self._health: dict[int, tuple[float, float]] = {}  # pawn address -> (health, max), read every HEALTH_EVERY
        self._state_n = 0
        self._info: dict[int, dict[str, Any]] = {}  # per-actor cached name/kind, by address
        self._objects_json = "[]"
        # Interactive objects don't move or get renamed: each record is built once per level
        self._object_records: dict[tuple[int, str], dict[str, Any] | None] = {}
        self._objects: dict[tuple[int, str], dict[str, Any]] = {}  # what the objects payload shows
        self._objects_dirty = False  # hooks changed it: publish on the next tick (batched)

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
            self._next_scan = self._next_objects = self._next_players = self._next_missions = 0.0
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
        if self._objects_dirty:
            self._objects_dirty = False
            run("objects", self._publish_objects)
        if now >= self._next_players and not heavy:
            self._next_players = now + PLAYERS_EVERY
            run("players", self._publish_players)
        if now >= self._next_missions:
            self._next_missions = now + MISSIONS_EVERY
            run("missions", self._publish_missions)

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
        level: dict[str, Any] = {"id": level_id, "map": name, "name": pretty_map_name(name), "images": []}
        if vol is None or movie is None:
            level["status"] = "none"
        else:
            c = vol.BrushComponent.Bounds.Origin
            level.update(
                status="loading",
                center=[c.X, c.Y],
                upp=vol.UnrealUnitsPerPixel * MOVIE_SCALE,
                north=vol.NorthOffsetInDegreesClockwise,
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
            cooked = cooked_dir()
            if cooked is None:
                raise FileNotFoundError("couldn't find WillowGame/CookedPCConsole")
            images = self._images.get(cooked / f"{map_name}.upk", movie)
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
                if key not in records:
                    records[key] = self._object_record(io) if self._in_world(io) else None
                if (record := records[key]) is not None and not io.bHidden and not io.bDeleteMe:
                    objects[key] = record
            except Exception as ex:  # noqa: BLE001
                log_error("interactive object", ex)
        self._objects = objects
        if self._tracker is None or self._tracker() is None:  # one per game: only look it up again if gone
            self._tracker = next(
                (WeakPointer(t) for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")),
                None,
            )
        self._publish_objects()

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

    def object_destroyed(self, io: Any) -> None:
        key = (io._get_address(), str(io.Name))
        self._object_records.pop(key, None)
        if self._objects.pop(key, None) is not None:
            self._objects_dirty = True

    @staticmethod
    def _object_record(io: Any) -> dict[str, Any]:
        loc = io.Location
        definition = try_(lambda: io.InteractiveObjectDefinition)
        # The game's name for it, in the game's language (e.g. "Incendiary Barrel"): the balance's
        # DefaultDisplayName, else what targeting it shows
        balance = try_(lambda: io.BalanceDefinitionState.BalanceDefinition)
        display = try_(lambda: str(balance.DefaultDisplayName), "") or call_str(io.GetTargetName)
        return {
            "i": addr(io),
            **named(display, def_name(definition), call_str(io.GetHumanReadableName), str(io.Class.Name)),
            "d": str(definition.Name) if definition is not None else "",
            "c": io.Class.Name,
            "x": round(loc.X),
            "y": round(loc.Y),
            "z": round(loc.Z),
        }

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
            name = named(try_(lambda: str(pawn.PlayerReplicationInfo.PlayerName), ""), "Player")
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
        name = call_str(inv.GetShortHumanReadableName) if inv is not None else ""
        info = {
            "i": f"{addr:x}",
            **named(name, def_name(inv.Class) if inv is not None else "", str(p.Class.Name)),
            "c": inv.Class.Name if inv is not None else "",
            "q": try_(lambda: int(p.InventoryRarityLevel), 0),
        }
        if inv is not None and (level := exp_level(inv)):
            info["l"] = level
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
        pawns = []
        health = {}
        pawn = wi.PawnList
        for n in range(MAX_PAWNS):
            if pawn is None:
                break
            try:
                if not pawn.bDeleteMe and not pawn.bIsDead:
                    info = self._pawn_info(pawn, me)
                    loc = pawn.Location
                    # Health: 2 function calls per pawn, so each pawn is read every HEALTH_EVERY
                    # updates (staggered), new ones at once
                    key = pawn._get_address()
                    hp = self._health.get(key)
                    if hp is None or (n + self._state_n) % HEALTH_EVERY == 0:
                        hp_max = try_(pawn.GetMaxHealth, 0)
                        hp = (try_(pawn.GetHealth, 0) if hp_max else 0, hp_max)
                    health[key] = hp
                    pawns.append(
                        {
                            **info,
                            "x": round(loc.X),
                            "y": round(loc.Y),
                            "z": round(loc.Z),
                            "r": view_yaw if info["k"] == "me" else pawn.Rotation.Yaw,
                            "h": hp[0],
                            "m": hp[1],
                        },
                    )
            except Exception as ex:  # noqa: BLE001
                log_error("pawn", ex)
            pawn = try_(lambda p=pawn: p.NextPawn)
        self._health = health  # drops the pawns that are gone
        pickups = []
        for key, ptr in list(self._pickups.items()):
            p = ptr()
            if p is None:
                del self._pickups[key]
                continue
            try:
                if p.bDeleteMe or p.bHidden:
                    continue
                loc = p.Location
                pickups.append({**self._pickup_info(p), "x": round(loc.X), "y": round(loc.Y), "z": round(loc.Z)})
            except Exception as ex:  # noqa: BLE001
                log_error("pickup", ex)
        state = {"level": self.level_id, "t": round(now, 3), "pawns": pawns, "pickups": pickups}
        self.hub.publish("state", json.dumps(state, separators=(",", ":")))

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

    def _publish_players(self) -> None:
        wi = ENGINE.GetCurrentWorldInfo()
        pc = get_pc(possibly_loading=True)
        if wi is None or pc is None:
            return
        players = read_players(wi, try_(lambda: pc.MyWillowPawn))
        players_json = json.dumps({"level": self.level_id, "players": players}, separators=(",", ":"))
        if players_json != self._players_json:  # gear rarely changes: only send changes
            self._players_json = players_json
            self.hub.publish("players", players_json)

    # endregion
