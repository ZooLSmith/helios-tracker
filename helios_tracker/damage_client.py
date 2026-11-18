"""
The damage log on a co-op client (notes.md "A co-op client"; design.md "Damage log"): none of the host's hooks run
there - a hit is the server's (TakeDamage). What a client has, and how each is logged - strict, plus the totals (the
user, 2026-11-18): no hit is given an amount by timing.
- **Every hit's effects played on its victim** (GAME.damage.client_hit - PlayHit): who dealt it, the element, no amount.
  Another's: not logged (the user: no "?" rows - its amount is in the victim's unexplained loss, below); its victim read.
- **The local player's damage numbers** (client_number - ~1 ms after the hit's PlayHit, at its location): that hit's
  amount and a crit - its row in full; none came, the hit did nothing (an enemy we can't damage - the user saw "?"
  for it): no row, as the host's hit for nothing. The game gives one figure: split as the victim's shield then its health, by the
  shield it had (its replicated value, less what our numbers already took from it).
- **What the victims lost that no full row explains** (their replicated health and shield, GAME.damage.vitals - read
  at the collector's tick): one row per victim per SETTLE_MS from the "unattributed" actor - the totals right, who dealt
  it not said (the host's hits, a burn's ticks, an enemy's on a player).
- **An enemy's death** (client_gone - TornOff): a "died" event, as a death outside a hit (no killing blow known).

No game named here (the reads are the profile's); the rows and ids are the log's (damage.py DamageLog - this plugs into
it: its hooks' roles "client_*", its tick).
"""

from typing import Any

from . import games

PAIR_MS = 100  # a damage number's hit: its PlayHit this recent at most (seen ~1 ms before)
PAIR_DISTANCE = 200.0  # ... and this close to the number's location (seen within ~10 units)
SETTLE_MS = 1000  # a victim's unexplained loss: one row per this
CREDIT_MS = 2000  # a full row's amount not seen in the victim's health by then: no longer expected
FORGET_MS = 60000  # a victim not hit for this long, nothing left to settle: no longer read


class _Victim:
    """A victim being read: its replicated health / shield last seen, what our full rows took from it not seen yet
    (credit), what it lost that nothing explains yet (lost) and since when."""

    __slots__ = ("credit_at", "credit_h", "credit_s", "health", "id", "last_hit", "lost_h", "lost_s", "pointer", "shield",
                 "since")

    def __init__(self, pointer: Any, actor_id: int, vitals: tuple[float, float], now: int) -> None:
        self.pointer, self.id = pointer, actor_id
        self.health, self.shield = vitals
        self.credit_h = self.credit_s = self.lost_h = self.lost_s = 0.0
        self.credit_at = self.since = 0
        self.last_hit = now


class ClientReads:
    """The client's hooks' bodies (on_hit, on_object_hit, on_number, on_gone - the roles "client_hit"... damage.py routes here) and its
    tick (the victims read, the unexplained losses settled). The game thread only."""

    def __init__(self, log: Any) -> None:
        self.log = log
        self._me = 0  # the local player's pawn's address (read at the tick: a hit's attacker compared to it)
        self._me_id = 0
        self._pending: list[tuple[int, list[Any], tuple[float, float, float], _Victim | None]] = []  # our hits, a number to come
        self._victims: dict[int, _Victim] = {}
        self._unattributed = 0

    # region The hooks' bodies (inside the game's calls: reads only)

    def on_object_hit(self, obj: Any, args: Any) -> None:
        if games.GAME.damage.object_has_health(obj):  # (an object without health: not logged - the host's rule)
            self.on_hit(obj, args)

    def on_hit(self, obj: Any, args: Any) -> None:
        attacker, element, location = games.GAME.damage.client_hit(args)
        log = self.log
        now = log._ms()
        victim = self._victim(obj, now)  # (its health read before this hit lands: a PlayHit comes first)
        if attacker is None or attacker._get_address() != self._me:
            return  # (another's: its amount unknown - not logged; what it took, the victim's unexplained loss)
        row = [now, self._me_id, victim.id, 0.0, 0.0, 0, 0, log._id(log._elements, element)]
        self._pending.append((now, row, location, victim))  # (its amount: the damage number right after it)

    def on_number(self, obj: Any, args: Any) -> None:  # noqa: ARG002 - (a static event: obj the class default)
        amount, crit, element, location = games.GAME.damage.client_number(args)
        log = self.log
        now = log._ms()
        found = None
        for item in self._pending:
            dx, dy, dz = (a - b for a, b in zip(item[2], location, strict=True))
            if now - item[0] <= PAIR_MS and dx * dx + dy * dy + dz * dz <= PAIR_DISTANCE * PAIR_DISTANCE:
                found = item  # (the latest that fits: hits come in order)
        flags = 1 if crit else 0  # (damage.CRIT)
        if found is None:  # (a number without its hit - not seen: ours, whom unknown)
            if self._me_id:
                log._queue.append(("h", [now, self._me_id, 0, round(amount, 1), 0.0, flags, 0, log._id(log._elements, element)]))
            return
        self._pending.remove(found)
        log.stats["hits"] += 1
        row, victim = found[1], found[3]
        shield = min(amount, max(0.0, victim.shield - victim.credit_s))
        health = amount - shield
        victim.credit_h += health
        victim.credit_s += shield
        victim.credit_at = now
        row[3], row[4], row[5] = round(health, 1), round(shield, 1), flags
        if element is not None:
            row[7] = log._id(log._elements, element)
        log._queue.append(("h", row))

    def on_gone(self, obj: Any, args: Any) -> None:  # noqa: ARG002
        victim = self._victims.get(obj._get_address())
        if victim is not None:  # (one we saw hit: else nothing of it is in the log)
            self.log._event([self.log._ms(), "died", victim.id, 0, -1])

    def _victim(self, obj: Any, now: int) -> _Victim:
        address = obj._get_address()
        actor_id = self.log._actor(obj)
        victim = self._victims.get(address)
        if victim is None or victim.id != actor_id or victim.pointer() is None:
            from unrealsdk.unreal import WeakPointer  # noqa: PLC0415

            victim = self._victims[address] = _Victim(WeakPointer(obj), actor_id, games.GAME.damage.vitals(obj), now)
        victim.last_hit = now
        return victim

    # endregion
    # region The tick (the collector's)

    def tick(self) -> None:
        """Who we are; our hits whose number never came dropped (they did nothing); every victim read - what it lost
        past our full rows settled."""
        from mods_base import get_pc  # noqa: PLC0415

        log = self.log
        me = games.GAME.pawns.local(get_pc())
        self._me = me._get_address() if me is not None else 0
        self._me_id = log._actor(me) if me is not None else 0
        now = log._ms()
        self._pending = [p for p in self._pending if now - p[0] <= PAIR_MS]
        for address, victim in list(self._victims.items()):
            obj = victim.pointer()
            if obj is None:
                self._settle(victim, now, force=True)
                del self._victims[address]
                continue
            self._read(victim, games.GAME.damage.vitals(obj), now)
            if now - victim.last_hit > FORGET_MS and not (victim.lost_h or victim.lost_s):
                del self._victims[address]

    def _read(self, victim: _Victim, vitals: tuple[float, float], now: int) -> None:
        health, shield = vitals
        lost_h, lost_s = max(0.0, victim.health - health), max(0.0, victim.shield - shield)  # (a rise: regen, a recharge)
        victim.health, victim.shield = health, shield
        if victim.credit_h or victim.credit_s:
            if now - victim.credit_at > CREDIT_MS:
                victim.credit_h = victim.credit_s = 0.0
            taken_h, taken_s = min(lost_h, victim.credit_h), min(lost_s, victim.credit_s)
            victim.credit_h -= taken_h
            victim.credit_s -= taken_s
            lost_h, lost_s = lost_h - taken_h, lost_s - taken_s
        if lost_h > 0.05 or lost_s > 0.05:
            if not (victim.lost_h or victim.lost_s):
                victim.since = now
            victim.lost_h += lost_h
            victim.lost_s += lost_s
        self._settle(victim, now)

    def _settle(self, victim: _Victim, now: int, force: bool = False) -> None:
        if not (victim.lost_h or victim.lost_s) or (not force and now - victim.since < SETTLE_MS):
            return
        if not self._unattributed:
            self._unattributed = self.log.reserve_actor({"k": "unattributed"})
        self.log._queue.append(("h", [victim.since, self._unattributed, victim.id, round(victim.lost_h, 1),
                                      round(victim.lost_s, 1), 0, 0, 0]))
        victim.lost_h = victim.lost_s = 0.0

    def level_changed(self) -> None:
        """A new level: what was pending settled, the victims dropped (our hits still without a number: nothing)."""
        now = self.log._ms()
        for victim in self._victims.values():
            self._settle(victim, now, force=True)
        self._victims, self._pending = {}, []

    # endregion
