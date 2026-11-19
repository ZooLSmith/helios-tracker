"""
How to get to a map fast travel doesn't reach - for the mission log's places: Fink's Slaughterhouse is a map of its own
(BanditSlaughter_P, no station - tools/probes/probe_station_maps.txt), its one way in from The Fridge: "Given at Fink's
Slaughterhouse · via The Fridge".

The game's data, nothing guessed (games.GAME.world.travel_network: static, read once): the ways between maps (the exits,
the level lists' connections) and the fast travel stations' maps. For a map no station is in: the nearest maps with one,
counted in maps walked through (the exits: the data has no distances inside a map) - every one at that count (Sanctuary
Hole: Caustic Caverns and Three Horns - Divide, one exit each). The stations the player unlocked first (the controller's
list: games.GAME.world.unlocked_stations), else any (a station not found yet still says which way). A map with a station
of its own gets nothing, whatever leads to it (Sanctuary: one way in, its own station).
"""

from collections.abc import Callable, Iterable
from typing import Any

from . import games
from .util import try_


def _nearest(target: str, into: dict[str, set[str]], wanted: set[str]) -> tuple[set[str], int]:
    """The maps of `wanted` the fewest exits away from `target` (walking to it), and that count; (set(), 0) if none."""
    seen, ring, steps = {target}, {target}, 0
    while ring:
        ring = {a for b in ring for a in into.get(b, ()) if a not in seen}
        seen |= ring
        steps += 1
        if hits := ring & wanted:
            return hits, steps
    return set(), 0


def via_maps(links: Iterable[tuple[str, str]], stations: Iterable[tuple[str, str]],
             unlocked: Iterable[str]) -> dict[str, tuple[list[str], int]]:
    """For every map without a fast travel station (lower case): (the nearest maps with one - their spelling, sorted -
    and how many exits from there). `links`: (from map, to map) - a map's link to itself left out (the level lists have
    some: VOGChamber_P); `stations`: (station name, its map); `unlocked`: the station names the player activated."""
    spelling: dict[str, str] = {}
    into: dict[str, set[str]] = {}
    for a, b in links:
        a_key, b_key = a.lower(), b.lower()
        if not a_key or not b_key or "none" in (a_key, b_key) or a_key == b_key:
            continue
        spelling.setdefault(a_key, a)
        spelling.setdefault(b_key, b)
        into.setdefault(b_key, set()).add(a_key)
    unlocked = set(unlocked)
    stations = [(n, m.lower()) for n, m in stations if m and m.lower() != "none"]  # (Tundra Train's: in "None")
    with_station = {m for _, m in stations}
    with_unlocked = {m for n, m in stations if n in unlocked}
    out = {}
    for target in spelling:
        if target in with_station:
            continue
        maps, steps = _nearest(target, into, with_unlocked)
        if not maps:
            maps, steps = _nearest(target, into, with_station)
        if maps:
            out[target] = (sorted(spelling[m] for m in maps), steps)
    return out


class Travel:
    """The "via" table, for the mission log's payload: {map (lower case): {"v": [the maps' names as the game shows them],
    "n": exits from there}} - rebuilt when the player's unlocked stations change (one array read per check)."""

    def __init__(self) -> None:
        self._network: tuple[list[tuple[str, str]], list[tuple[str, str]]] | None = None
        self._unlocked: frozenset[str] | None = None
        self.via: dict[str, dict[str, Any]] = {}

    def update(self, pc: Any, name: Callable[[str], str]) -> bool:
        """Checks the stations unlocked; True if the table changed. `name`: a map's name as the game shows it
        (collector.level_name) - a map without one left out."""
        if games.TRAVELHINTS not in games.GAME.features or pc is None:
            return False
        if self._network is None:
            self._network = try_(games.GAME.world.travel_network) or ([], [])  # (a failure: logged once, not retried)
        unlocked = frozenset(try_(lambda: games.GAME.world.unlocked_stations(pc), []) or [])
        if unlocked == self._unlocked:
            return False
        self._unlocked = unlocked
        via = {}
        for target, (maps, steps) in via_maps(*self._network, unlocked).items():
            if titles := sorted({t for m in maps if (t := name(m))}):
                via[target] = {"v": titles, "n": steps}
        changed, self.via = via != self.via, via
        return changed
