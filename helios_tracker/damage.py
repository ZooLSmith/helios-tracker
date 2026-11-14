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

**Ids: the log's own** (1, 2... per kind), not the map's (addresses: reused once something's gone - an hour's log would
mix enemies): an address -> (a WeakPointer, its id), the pointer dead = a new id. A player keeps theirs across
respawns (their controller: GAME.damage.identity).

A batch: {"q": its sequence (the hub's), "h": [hits], "v": [events], "a" / "w" / "e": definitions new or changed}:
- a hit: [t, attacker, target, health, shield, flags, what, element] (+ count: a folded one's) - t ms since the log's
  start (the hub's "t0": its epoch ms), attacker / target "a" ids (0: none), what a "w" id (the causer - a weapon, a
  grenade's explosion, a melee... - else the damage source; 0: none), element an "e" id (0: none); flags below;
- an event: [t, kind, actor, other, hit, ...] - hit: the index in this batch's "h" of the hit it happened in (-1: none):
  "fx+" an effect applied (actor its victim, other the instigator; + what, the effect - a "w" id), "fx-" one ended
  (the same), "down" a player downed (other: by whom), "wind" a second wind (the hit: the kill that gave it), "dead"
  bled out, "up" back up (+ "revive" / "respawn"), "died" a death outside any hit (no killing blow), "level" (+ its name);
- definitions: "a" {id: {"k": kind, "n": name, "raw"?: 1, "m"?: its map id, "boss"?}}, "w" {id: {"n", "raw"?}},
  "e" {id: {"d": its definition's name, "el"?, "eln"?, "ecol"? - inspector.element_of}} - sent again when they change
  (a player respawned: their "m").
"""

import json
import math
import time
from typing import Any

from . import games
from .frames import FRAMES
from .util import log_error

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
        self.stats = {"hits": 0, "events": 0, "batches": 0, "hook_s": 0.0, "hook_max_s": 0.0, "hook_calls": 0}

    # region Switching

    def set_enabled(self, on: bool) -> None:
        """The Damage Log option: off - the hooks removed, what's kept dropped (the hub's history too: a new session)."""
        self.enabled = on
        if not on:
            self.stop()
            self._queue, self._floods, self._down = [], {}, {}
            self._actors, self._what, self._elements = _Ids(), _Ids(), _Ids()
            self._sent = {}
            self.hub.clear_events(CHANNEL)

    def start(self) -> None:
        """The profile's hooks added (a reload's first removed: the same id - add_hook keeps an old one)."""
        from unrealsdk.hooks import Type, add_hook, remove_hook  # noqa: PLC0415

        self.stop()
        for path, pre, role in games.GAME.damage.hooks():
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

    @property
    def hooked(self) -> bool:
        return bool(self._hooked)

    def _handler(self, role: str) -> Any:
        body = getattr(self, "_on_" + role)
        failed: set[type] = set()
        stats = self.stats

        def hook(obj: Any, args: Any, ret: Any, func: Any) -> None:  # noqa: ARG001
            with FRAMES.ours():
                start = time.perf_counter()
                try:
                    body(obj, args)
                except Exception as ex:  # noqa: BLE001 - (logged once per role and type: a hit a frame isn't a flood)
                    if type(ex) not in failed:
                        failed.add(type(ex))
                        log_error(f"damage {role}", ex)
                spent = time.perf_counter() - start
                stats["hook_s"] += spent
                stats["hook_calls"] += 1
                if spent > stats["hook_max_s"]:
                    stats["hook_max_s"] = spent

        return hook

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
        instigator, health, shield, crit, element, source, kind = damage.hit(args)
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
                self._queue.append(("h", _rounded(self._floods.pop(key))))
                row = None
            if row is None:
                row = self._floods[key] = [t, attacker, target, 0.0, 0.0, flags | FOLDED, what, element_id, 0]
            row[3] += _amount(health)  # (rounded once its span is over: _flush_floods)
            row[4] += _amount(shield)
            row[8] += 1
        else:
            row = [t, attacker, target, round(_amount(health), 1), round(_amount(shield), 1), flags, what, element_id]
        if frame is not None:
            frame[1] = row
        elif kind != 2:
            self._queue.append(("h", row))  # (a read outside its TakeDamage: done at once)
        return row

    def _on_close(self, obj: Any, args: Any) -> None:
        if (frame := self._top(obj)) is None:
            return  # (a POST without its PRE: the hooks added mid-call)
        self._frames.pop()
        self._close(frame)

    def _on_object_close(self, obj: Any, args: Any) -> None:
        if (frame := self._top(obj)) is None:
            return
        self._frames.pop()
        row = self._read(obj, args, frame)
        if row is not None and not row[3] and not row[4] and not row[5] & FOLDED:
            frame[1] = None  # (an object hit for nothing - one that takes no damage: not a hit to log)
        elif not frame[5] and games.GAME.damage.object_killed(obj):
            frame[2] |= KILL
        self._close(frame)

    def _close(self, frame: list[Any]) -> None:
        row = frame[1]
        if row is not None:
            row[5] |= frame[2]
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

    def tick(self, active: bool) -> None:
        """Each collector tick: the hooks on while a page is open, the option on and the game has the log (`active`: a
        page and a level); what's queued published."""
        want = active and self.enabled and games.DAMAGE in games.GAME.features
        if want and not self._hooked:
            self.start()
        elif not want and self._hooked:
            self.stop()
        if self._queue or self._floods or self._actors.fresh or self._what.fresh or self._elements.fresh:
            self._drain()

    def level_changed(self, name: str) -> None:
        """A new level: a mark in the log; the floods closed, the open frames dropped, the gone objects' ids pruned."""
        if not self.enabled:
            return
        self._flush_floods(force=True)
        self._frames = []
        for ids in (self._actors, self._what, self._elements):
            ids.prune()
        self._event([self._ms(), "level", 0, 0, -1, name])

    def _flush_floods(self, force: bool = False) -> None:
        now = self._ms()
        for key, row in list(self._floods.items()):
            if force or now - row[0] >= FOLD_MS:
                del self._floods[key]
                self._queue.append(("h", _rounded(row)))

    def _definitions(self) -> dict[str, dict[str, Any]]:
        """The new ids named (game calls: here, never in a hook), those that changed since last sent."""
        out: dict[str, dict[str, Any]] = {}
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

    def summary(self) -> str:
        """The console's line (tools/probes/damage_log_stats.py): counts, our hooks' time."""
        s = self.stats
        mean = s["hook_s"] / s["hook_calls"] * 1e6 if s["hook_calls"] else 0.0
        return (f"damage log: {'on' if self.enabled else 'off'}, hooks {'in' if self._hooked else 'out'}; {s['hits']} hits, "
                f"{s['events']} events, {s['batches']} batches; hooks {s['hook_calls']} calls, {mean:.1f} us mean, "
                f"{s['hook_max_s'] * 1e6:.0f} us max, {s['hook_s'] * 1e3:.1f} ms in all; ids: {self._actors.next - 1} actors, "
                f"{self._what.next - 1} what, {self._elements.next - 1} elements; open frames {len(self._frames)}")

    # endregion
