"""
The damage log: every hit, read where the game handles it - who dealt it, who took it, how much (health, shield), a
crit, its element, what with -, the killing blow, the effects (a burn) applied and ended, a player downed, back up by a
second wind, bled out, revived, respawned (design.md "Damage log", notes.md "Damage: where a hit can be read").

No game named here: what's hooked and how a hit reads is the profile's (games.GAME.damage). The hooks do next to
nothing - property reads into a frame, no names, no JSON -; the collector's tick drains them (tick()): what's new
named (game calls: once per actor / weapon - the collector's namers), one batch published on the hub's event channel
"damage" (kept: a page catching up gets it - server._Events).

**One record per hit, built while the game handles it**: the hit's TakeDamage opens a frame (a stack: they nest), what
runs inside belongs to it - the read, an effect applied, the killing blow, a player downed, a second wind - and its
end closes it. Every link is the game's call order, never a guess.
A co-op client runs none of it (the server's): its own hooks and reads, damage_client.py - into the same rows.

**Ids: the log's own** (1, 2... per kind), not the map's (addresses: reused once something's gone - an hour's log would
mix enemies): an address -> (a WeakPointer, its id), the pointer dead = a new id. A player keeps theirs across
respawns (their controller: GAME.damage.identity).

A batch: {"q": its sequence (the hub's), "h": [hits], "v": [events], "a" / "w" / "e": definitions new or changed}:
- a hit: [t, attacker, target, health, shield, flags, what, element] (+ count: a folded one's; + 0, extras: a hit with
  any - DamageLog._extra: {"o": overkill, "g": slag's share, "by": who slagged it}) - t ms since the log's
  start (the hub's "t0": its epoch ms), attacker / target "a" ids (0: none), what a "w" id (the causer - a weapon, a
  grenade's explosion, a melee... - else the damage source; 0: none), element an "e" id (0: none); flags below;
- an event: [t, kind, actor, other, hit, ...] - hit: the index in this batch's "h" of the hit it happened in (-1: none):
  "fx+" an effect applied (actor its victim, other the instigator; + what, the effect - a "w" id), "fx-" one ended
  (the same), "down" a player downed (other: by whom), "wind" a second wind (the hit: the kill that gave it), "dead"
  bled out, "up" back up (+ "revive" / "respawn"), "died" a death outside any hit (no killing blow), "level" (+ its name);
- definitions: "a" {id: {"k": kind, "n": name, "raw"?: 1, "m"?: its map id, "boss"?, "o"?: a player's number in the
  game - PRI.PlayerID, the same on every page: their colours}}, "w" {id: {"n", "raw"?}},
  "e" {id: {"d": its definition's name, "el"?, "eln"?, "ecol"? - inspector.element_of}} - sent again when they change
  (a player respawned: their "m"); an actor without an object ("k": "unattributed" - a client's: reserve_actor).
"""

import json
import math
import time
from typing import Any

from . import games
from .damage_client import ClientReads
from .frames import FRAMES, REPORT_EVERY
from .paths import DIAGNOSTICS
from .util import log, log_error

CHANNEL = "damage"
HOOK_ID = "helios_tracker_damage"
FOLD_MS = 250  # a flood's hits (crushing: one every few tenths of a millisecond) summed per this span (the user: fine)
MAX_FRAMES = 64  # open hits: more is a POST missed (hooks added mid-call) - the stack dropped

# A hit's flags
CRIT = 1
TICK = 2  # an effect's damage (a burn's tick)
KILL = 4  # the killing blow (Died ran inside it; an object: destroyed by it)
EFFECT = 8  # it applied an effect (ApplyStatusEffect ran inside it)
DOWNED = 16  # it downed its target (a player: Fight For Your Life)
SECOND_WIND = 32  # it gave a downed player a second wind (the kill)
FOLDED = 64  # a flood's hits summed: the row's count after its element
HEAL = 128  # a heal, not damage: its amounts given back (an ally's hit converted to healing - HealDamage inside it)


def _amount(value: float) -> float:
    """An amount the page can read (JSON has no NaN / infinity: 0 for those)."""
    return value if math.isfinite(value) else 0.0


def _rounded(row: list[Any]) -> list[Any]:
    """A flood's row, its sums rounded (once: rounding each hit's adds its error)."""
    row[3], row[4] = round(row[3], 1), round(row[4], 1)
    return row


class _Ids:
    """Game objects -> the log's ids of one kind, by address, each with a WeakPointer: an entry whose object is gone (or
    another object at its address since) is never returned. `fresh`: ids to name at the tick (id -> a WeakPointer)."""

    def __init__(self) -> None:
        self.entries: dict[int, tuple[Any, int]] = {}
        self.next = 1
        self.fresh: dict[int, Any] = {}

    def find(self, address: int) -> int:
        entry = self.entries.get(address)
        return entry[1] if entry is not None and entry[0]() is not None else 0

    def add(self, obj: Any, address: int, known: int = 0, named: Any = None) -> int:
        """`obj`'s entry: id `known` (another object's - a player's pawn: their controller's) or a new one; `named` the
        object its definition is read from (default: obj) - named at the tick."""
        from unrealsdk.unreal import WeakPointer  # noqa: PLC0415 - (the game's: imported on the first new object)

        if not known:
            known = self.next
            self.next += 1
        self.entries[address] = (WeakPointer(obj), known)
        self.fresh[known] = WeakPointer(named if named is not None else obj)
        return known

    def prune(self) -> None:
        """Entries whose object is gone, dropped (a level change: else they'd pile up all session)."""
        self.entries = {a: e for a, e in self.entries.items() if e[0]() is not None}


class DamageLog:
    """The log: its hooks (start / stop), the frames of the hits being handled, the queue of what's done, the ids;
    tick() drains it into a batch. The game thread only (the hooks, the collector's tick). The collector sets the
    namers: name_actor(actor or None, identity), name_what(obj), name_element(damage type) -> a definition (dict)."""

    def __init__(self, hub: Any) -> None:
        self.hub = hub
        self.enabled = True  # the Damage Log option (set_enabled)
        self.name_actor: Any = lambda actor, identity: {}
        self.name_what: Any = lambda obj: {}
        self.name_element: Any = lambda obj: {}
        self._t0 = time.perf_counter()
        self.t0_epoch = int(time.time() * 1000)  # (the batches' times: ms since this - the page's clock)
        self._hooked: list[tuple[str, Any]] = []
        self._frames: list[list[Any]] = []
        self._queue: list[tuple[Any, ...]] = []  # ("h", row) / ("v", event, the row of the hit it happened in or None)
        self._floods: dict[tuple[int, int, int, int], list[Any]] = {}  # (attacker, target, what, element) -> its row
        self._down: dict[int, str] = {}  # a downed player's actor id -> "down" / "wind" (a second wind) / "dead"
        self._actors, self._what, self._elements = _Ids(), _Ids(), _Ids()
        self._sent: dict[tuple[str, int], dict[str, Any]] = {}
        self._reserved: dict[int, dict[str, Any]] = {}  # actor ids without an object -> their definitions (sent once)
        self._client: ClientReads | None = None  # a co-op client's hooks' bodies and reads (start)
        self.stats: dict[str, Any] = {}
        self.reset_stats()
        self.diagnostics = DIAGNOSTICS  # (the measures reported in the log: debug only - _report)
        self._next_report = 0.0

    # region Switching

    def set_enabled(self, on: bool) -> None:
        """The Damage Log option: off - the hooks removed, what's kept dropped (the hub's history too: a new session)."""
        self.enabled = on
        if not on:
            self.stop()
            self._queue, self._floods, self._down = [], {}, {}
            self._actors, self._what, self._elements = _Ids(), _Ids(), _Ids()
            self._sent, self._reserved = {}, {}
            self.hub.clear_events(CHANNEL)

    def start(self, client: bool = False) -> None:
        """The profile's hooks added (a reload's first removed: the same id - add_hook keeps an old one) - a co-op
        client's own (`client`: the host's never run there - damage_client.py)."""
        from unrealsdk.hooks import Type, add_hook, remove_hook  # noqa: PLC0415

        self.stop()
        self._client = ClientReads(self) if client else None
        for path, pre, role in games.GAME.damage.hooks(client):
            kind = Type.PRE if pre else Type.POST
            remove_hook(path, kind, HOOK_ID)
            add_hook(path, kind, HOOK_ID, self._handler(role))
            self._hooked.append((path, kind))

    def stop(self) -> None:
        if self._hooked:
            from unrealsdk.hooks import remove_hook  # noqa: PLC0415

            for path, kind in self._hooked:
                remove_hook(path, kind, HOOK_ID)
        self._hooked = []
        self._frames = []
        if self._client is not None:
            self._client.level_changed()  # (what it had pending: queued)
            self._client = None

    @property
    def hooked(self) -> bool:
        return bool(self._hooked)

    @property
    def client(self) -> bool:
        """Hooked as a co-op client (damage_client.py)."""
        return self._client is not None

    def reserve_actor(self, definition: dict[str, Any]) -> int:
        """An actor id without a game object (a client's "unattributed"), its definition sent with the next batch."""
        actor_id = self._actors.next
        self._actors.next += 1
        self._reserved[actor_id] = definition
        return actor_id

    def _handler(self, role: str) -> Any:
        # (a client's roles: its own bodies - damage_client.py on_<role>)
        body = getattr(self._client, "on_" + role[7:]) if role.startswith("client_") else getattr(self, "_on_" + role)
        failed: set[type] = set()
        def hook(obj: Any, args: Any, ret: Any, func: Any) -> None:  # noqa: ARG001
            with FRAMES.ours():
                start = time.perf_counter()
                try:
                    body(obj, args)
                except Exception as ex:  # noqa: BLE001 - (logged once per role and type: a hit a frame isn't a flood)
                    if type(ex) not in failed:
                        failed.add(type(ex))
                        log_error(f"damage {role}", ex)
                self._measure(role, start, time.perf_counter() - start)

        return hook

    def _measure(self, role: str, start: float, spent: float) -> None:
        """A hook's time: in all, its role's, its second's (the busiest second: what a hitch is made of)."""
        stats = self.stats
        stats["hook_s"] += spent
        stats["hook_calls"] += 1
        if spent > stats["hook_max_s"]:
            stats["hook_max_s"] = spent
        r = stats["roles"].get(role)
        if r is None:
            r = stats["roles"][role] = [0, 0.0, 0.0]  # calls, total s, max s
        r[0] += 1
        r[1] += spent
        if spent > r[2]:
            r[2] = spent
        second = int(start)
        if second != stats["second"]:
            stats["second"], stats["second_s"], stats["second_calls"] = second, 0.0, 0
        stats["second_s"] += spent
        stats["second_calls"] += 1
        if stats["second_s"] > stats["worst_second_s"]:
            stats["worst_second_s"], stats["worst_second_calls"] = stats["second_s"], stats["second_calls"]

    def reset_stats(self) -> None:
        """The measures from zero (after each report: _report)."""
        self.stats = {"hits": 0, "events": 0, "batches": 0, "hook_s": 0.0, "hook_max_s": 0.0, "hook_calls": 0,
                      "roles": {}, "second": -1, "second_s": 0.0, "second_calls": 0, "worst_second_s": 0.0,
                      "worst_second_calls": 0, "tick_s": 0.0, "tick_max_s": 0.0, "ticks": 0, "drains": 0,
                      "since": time.perf_counter()}

    # endregion
    # region The hooks' bodies (the game thread, inside the game's calls: reads only)

    def _ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def _actor(self, obj: Any) -> int:
        """Its actor id (0: None) - a new one named at the tick."""
        if obj is None:
            return 0
        address = obj._get_address()
        if found := self._actors.find(address):
            return found
        identity = games.GAME.damage.identity(obj)
        if identity._get_address() == address:
            return self._actors.add(obj, address)
        # (a player's pawn: their controller's id - named again from it, the new pawn's map id)
        return self._actors.add(obj, address, self._actor(identity), identity)

    def _id(self, ids: _Ids, obj: Any) -> int:
        if obj is None:
            return 0
        address = obj._get_address()
        return ids.find(address) or ids.add(obj, address)

    def _top(self, obj: Any) -> list[Any] | None:
        """The open frame of a hit on `obj` (the innermost), None if it isn't the one being handled."""
        if self._frames and self._frames[-1][0] == obj._get_address():
            return self._frames[-1]
        return None

    def _open(self, obj: Any, args: Any) -> list[Any]:
        if len(self._frames) >= MAX_FRAMES:
            self._frames = []
        # [victim address, its row, its flags, its events, the causer, killed before (an object)]
        frame = [obj._get_address(), None, 0, [], None, False]
        self._frames.append(frame)  # (first: a failing read below leaves the stack paired with the POST)
        frame[4] = games.GAME.damage.causer(args)
        return frame

    def _on_open(self, obj: Any, args: Any) -> None:
        self._open(obj, args)

    def _on_object_open(self, obj: Any, args: Any) -> None:
        frame = self._open(obj, args)
        frame[5] = games.GAME.damage.object_killed(obj)

    def _on_read(self, obj: Any, args: Any) -> None:
        self._read(obj, args, self._top(obj))

    def _read(self, victim: Any, args: Any, frame: list[Any] | None) -> list[Any] | None:
        damage = games.GAME.damage
        instigator, health, shield, crit, element, source, kind, previous, amplified = damage.hit(args)
        causer = frame[4] if frame is not None else None
        # who dealt it: the game's instigator - but a barrel's fire is the barrel's (the user: shown as its own source,
        # like an enemy - not the player who set it off), as the game ties it (GAME.damage.owner)
        owner = damage.owner(causer)
        attacker, target = self._actor(owner if owner is not None else instigator), self._actor(victim)
        what = self._id(self._what, causer if causer is not None else source)
        element_id = self._id(self._elements, element)
        flags = (CRIT if crit else 0) | (TICK if kind == 1 else 0)
        t = self._ms()
        self.stats["hits"] += 1
        if kind == 2:  # a flood: summed per FOLD_MS (its row queued when its span is over - _flush_floods)
            key = (attacker, target, what, element_id)
            row = self._floods.get(key)
            if row is not None and t - row[0] >= FOLD_MS:
                self._queue_flood(self._floods.pop(key))
                row = None
            if row is None:
                row = self._floods[key] = [t, attacker, target, 0.0, 0.0, flags | FOLDED, what, element_id, 0]
            row[3] += _amount(health)  # (rounded once its span is over: _flush_floods)
            row[4] += _amount(shield)
            row[8] += 1
        else:
            row = [t, attacker, target, round(_amount(health), 1), round(_amount(shield), 1), flags, what, element_id]
            extra = self._extra(victim, _amount(health), _amount(previous), _amount(amplified))
            if extra:
                row.extend((0, extra))  # (its count: a folded row's only)
        if frame is not None:
            frame[1] = row
        elif kind != 2:
            if row[3] or row[4]:  # (a read outside its TakeDamage: done at once - a hit for nothing not logged)
                self._queue.append(("h", row))
        return row

    def _extra(self, victim: Any, health: float, previous: float, amplified: float) -> dict[str, Any]:
        """A hit's extras ({} none - most hits): "o" its overkill (the health it dealt past what was left: the game's
        amounts aren't clamped - a kill's contribution stops at the kill, its damage dealt doesn't: the user), "g" the
        share of it slag's bonus made (GAME.damage.hit), "by" who slagged the target (actor ids - the ones whose slag
        is running on it: GAME.damage.amplifiers - read for such a hit only)."""
        extra: dict[str, Any] = {}
        if previous > 0 and health > previous:
            extra["o"] = round(health - previous, 1)
        if amplified > 0:
            extra["g"] = round(amplified, 4)
            by = sorted({self._actor(x) for x in games.GAME.damage.amplifiers(victim) if x is not None} - {0})
            if by:
                extra["by"] = by
        return extra

    def _on_close(self, obj: Any, args: Any) -> None:
        if (frame := self._top(obj)) is None:
            return  # (a POST without its PRE: the hooks added mid-call)
        self._frames.pop()
        self._close(frame)

    def _on_object_close(self, obj: Any, args: Any) -> None:
        if (frame := self._top(obj)) is None:
            return
        self._frames.pop()
        if not games.GAME.damage.object_has_health(obj):
            self._close(frame)  # (an object without health: not logged at all - the user; its events, if any, unlinked)
            return
        self._read(obj, args, frame)
        if not frame[5] and games.GAME.damage.object_killed(obj):
            frame[2] |= KILL
        self._close(frame)

    def _close(self, frame: list[Any]) -> None:
        row = frame[1]
        if row is not None and not row[3] and not row[4] and not (row[5] | frame[2]) & (FOLDED | KILL | DOWNED | SECOND_WIND):
            row = None  # (a hit for nothing: not logged - the user; one that killed / downed / gave a second wind kept)
        if row is not None:
            row[5] |= frame[2]
            if row[5] & HEAL and not row[5] & FOLDED:
                del row[8:]  # (a heal: no overkill, no slag - its amounts are what it gave back)
            if not row[5] & FOLDED:  # (a flood's row: queued at its span's end)
                self._queue.append(("h", row))
        for event in frame[3]:
            self._queue.append(("v", event, row))
            self.stats["events"] += 1

    def _event(self, event: list[Any], frame: list[Any] | None = None) -> None:
        """An event: in its hit's frame (queued after the hit, linked to it), else at once (no hit)."""
        if frame is not None:
            frame[3].append(event)
        else:
            self._queue.append(("v", event, None))
            self.stats["events"] += 1

    def _on_died(self, obj: Any, args: Any) -> None:
        if (frame := self._top(obj)) is not None:
            frame[2] |= KILL
        else:  # (a death outside any hit: a fall, out of the world - no killing blow)
            self._event([self._ms(), "died", self._actor(obj), 0, -1])

    def _effect(self, kind: str, obj: Any, args: Any) -> None:
        damage = games.GAME.damage
        victim, instigator, causer, effect = (damage.effect_started if kind == "fx+" else damage.effect_ended)(obj, args)
        frame = self._top(victim) if kind == "fx+" else None
        if frame is not None:
            frame[2] |= EFFECT
        self._event([self._ms(), kind, self._actor(victim), self._actor(instigator), -1, self._id(self._what, causer),
                     self._id(self._what, effect)], frame)

    def _on_effect_start(self, obj: Any, args: Any) -> None:
        self._effect("fx+", obj, args)

    def _on_effect_end(self, obj: Any, args: Any) -> None:
        self._effect("fx-", obj, args)

    def _on_healed(self, obj: Any, args: Any) -> None:
        healer, amount, shield = games.GAME.damage.healed(args)
        amount = round(_amount(amount), 1)
        row = [self._ms(), self._actor(healer), self._actor(obj), 0.0 if shield else amount, amount if shield else 0.0,
               HEAL, 0, 0]
        if (frame := self._top(obj)) is not None:
            frame[2] |= HEAL
            # (a hit converted to healing runs no damage-taken skill events - no read, no row (the user saw no heal at
            # all): HealDamage's own amount the hit's row, what dealt it the hit's causer; a read after it replaces it)
            if frame[1] is None:
                row[6] = self._id(self._what, frame[4])
                frame[1] = row
                self.stats["hits"] += 1
            return
        # a heal outside any hit (not seen yet - regen calls nothing): its own row, nothing dealt it
        self._queue.append(("h", row))
        self.stats["hits"] += 1

    def _on_downed(self, obj: Any, args: Any) -> None:
        player = self._actor(obj)
        frame = self._top(obj)
        if frame is not None:
            frame[2] |= DOWNED
        self._down[player] = "down"
        self._event([self._ms(), "down", player, self._actor(games.GAME.damage.downed_by(args)), -1], frame)

    def _on_second_wind(self, obj: Any, args: Any) -> None:
        # ClientOnRevived inside a hit's TakeDamage - the kill that gave it (on another pawn: the top frame, whoever's);
        # outside one: not a second wind (a revive? - not seen yet: GoFromInjuredToHealthy says it)
        if not self._frames:
            return
        frame = self._frames[-1]
        frame[2] |= SECOND_WIND
        player = self._actor(obj)
        self._down[player] = "wind"
        self._event([self._ms(), "wind", player, 0, -1], frame)

    def _on_dead_state(self, obj: Any, args: Any) -> None:
        if games.GAME.damage.dead_state_start(args):
            player = self._actor(obj)
            self._down[player] = "dead"
            self._event([self._ms(), "dead", player, 0, -1])

    def _on_healthy(self, obj: Any, args: Any) -> None:
        player = self._actor(obj)
        state = self._down.pop(player, None)
        if state in ("down", "dead"):  # (after a second wind: said already; never down: a level's start...)
            self._event([self._ms(), "up", player, 0, -1, "respawn" if state == "dead" else "revive"])

    # endregion
    # region The tick (the collector's): drained into a batch

    def tick(self, active: bool, client: bool = False) -> None:
        """Each collector tick: the hooks on while a page is open, the option on and the game has the log (`active`: a
        page and a level) - a co-op client's (`client`: the hooks swapped when it changes), its reads; what's queued
        published."""
        want = active and self.enabled and games.DAMAGE in games.GAME.features
        if want and (not self._hooked or client != self.client):
            self.start(client)
        elif not want and self._hooked:
            self.stop()
        if self._client is not None:
            start = time.perf_counter()
            self._client.tick()  # (the victims' health read: game reads, the tick's)
            self.stats["tick_s"] += time.perf_counter() - start
        if self._reserved or self._queue or self._floods or self._actors.fresh or self._what.fresh or self._elements.fresh:
            start = time.perf_counter()
            self._drain()  # (the tick's work: naming what's new - game calls -, the batch's JSON, publishing)
            spent = time.perf_counter() - start
            stats = self.stats
            stats["tick_s"] += spent
            stats["drains"] += 1
            if spent > stats["tick_max_s"]:
                stats["tick_max_s"] = spent
        if self._hooked:
            self.stats["ticks"] += 1
        self._report(time.monotonic())

    def level_changed(self, name: str) -> None:
        """A new level: a mark in the log; the floods closed, the open frames dropped, the gone objects' ids pruned."""
        if not self.enabled:
            return
        self._flush_floods(force=True)
        self._frames = []
        if self._client is not None:
            self._client.level_changed()
        for ids in (self._actors, self._what, self._elements):
            ids.prune()
        self._event([self._ms(), "level", 0, 0, -1, name])

    def _flush_floods(self, force: bool = False) -> None:
        now = self._ms()
        for key, row in list(self._floods.items()):
            if force or now - row[0] >= FOLD_MS:
                del self._floods[key]
                self._queue_flood(row)

    def _queue_flood(self, row: list[Any]) -> None:
        """A flood's row, its span over: queued - unless it summed to nothing (not logged: the user)."""
        row = _rounded(row)
        if row[3] or row[4]:
            self._queue.append(("h", row))

    def _definitions(self) -> dict[str, dict[str, Any]]:
        """The new ids named (game calls: here, never in a hook), those that changed since last sent."""
        out: dict[str, dict[str, Any]] = {}
        for key, value in self._reserved.items():
            if self._sent.get(("a", key)) != value:
                self._sent[("a", key)] = value
                out.setdefault("a", {})[key] = value
        self._reserved = {}
        for kind, ids in (("a", self._actors), ("w", self._what), ("e", self._elements)):
            fresh, ids.fresh = ids.fresh, {}
            for key, pointer in fresh.items():
                obj = pointer()
                if obj is None:
                    value = {"n": "?", "raw": 1} if (kind, key) not in self._sent else None  # (gone before named)
                elif kind == "a":
                    value = self.name_actor(games.GAME.damage.actor(obj), obj)
                elif kind == "w":
                    value = self.name_what(obj)
                else:
                    value = self.name_element(obj)
                if value is not None and self._sent.get((kind, key)) != value:
                    self._sent[(kind, key)] = value
                    out.setdefault(kind, {})[key] = value
        return out

    def _drain(self) -> None:
        self._flush_floods()
        defs = self._definitions()
        if not self._queue and not defs:
            return
        hits: list[list[Any]] = []
        events: list[list[Any]] = []
        index: dict[int, int] = {}
        for item in self._queue:
            if item[0] == "h":
                index[id(item[1])] = len(hits)
                hits.append(item[1])
            else:
                event, row = item[1], item[2]
                event[4] = index.get(id(row), -1) if row is not None else -1
                events.append(event)
        self._queue = []
        batch: dict[str, Any] = {}
        if hits:
            batch["h"] = hits
        if events:
            batch["v"] = events
        batch.update(defs)
        self.stats["batches"] += 1
        self.hub.publish_events(CHANNEL, json.dumps(batch, separators=(",", ":")), defs, self.t0_epoch)

    def _report(self, now: float) -> None:
        """Every REPORT_EVERY s (frames.py's), debug only (paths.DIAGNOSTICS): the measures in the mod's log, when hits
        came - then from zero (each report its own span)."""
        if not self.diagnostics or now < self._next_report:
            return
        first = not self._next_report
        self._next_report = now + REPORT_EVERY
        if first:
            return  # (the first span starts here: the measures since the mod's start kept)
        if self.stats["hook_calls"]:
            log(self.summary())
        self.reset_stats()

    def summary(self) -> str:
        """The report's line: counts, our hooks' time - in all, the busiest second, per role -, the tick's (draining:
        naming, JSON, publishing), since the last report."""
        s = self.stats
        span = max(1e-9, time.perf_counter() - s["since"])
        mean = s["hook_s"] / s["hook_calls"] * 1e6 if s["hook_calls"] else 0.0
        tick_mean = s["tick_s"] / s["drains"] * 1e3 if s["drains"] else 0.0
        roles = ", ".join(f"{role} {calls}x {total / calls * 1e6:.1f} us (max {top * 1e6:.0f})"
                          for role, (calls, total, top) in sorted(s["roles"].items(), key=lambda kv: -kv[1][1]))
        return (f"damage log in the last {span:.0f} s: {s['hits']} hits ({s['hits'] / span:.1f}/s), {s['events']} events, "
                f"{s['batches']} batches; hooks {s['hook_calls']} calls, {mean:.1f} us mean, {s['hook_max_s'] * 1e6:.0f} us "
                f"max, {s['hook_s'] * 1e3:.1f} ms ({s['hook_s'] / span * 1e3:.2f} ms/s), busiest second "
                f"{s['worst_second_s'] * 1e3:.2f} ms ({s['worst_second_calls']} calls) [{roles}]; tick {s['drains']} drains, "
                f"{tick_mean:.2f} ms mean, {s['tick_max_s'] * 1e3:.2f} ms max, {s['tick_s'] * 1e3:.1f} ms "
                f"({s['tick_s'] / span * 1e3:.2f} ms/s); ids {self._actors.next - 1} actors, {self._what.next - 1} what, "
                f"{self._elements.next - 1} elements, open frames {len(self._frames)}")

    # endregion
