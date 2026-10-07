"""
The level challenge objects placed in a map's packages (files only: no SDK, no UObjects - the worker's): each one's
position, number in its challenge group and challenge. A co-op client's objects have neither (NumberInChallengeGroup 1
on all, AssociatedChallenge None - tools/probes/probe_vault_client.txt, probe_vault_save.txt: NM_Client), but the
positions of the map's own (tools/probes/check_challenge_numbers.txt: Sanctuary_P.upk's five Vault symbols, the host's
numbers - probe_vault_discovered.txt).
"""

import json
import struct
from pathlib import Path
from typing import Any

from .... import gamework
from ....formats.upk import Package

CLASSES = ("WillowInteractiveObject",)  # the placed actors read (the Vault symbols, the ECHO recorders)
PROPS_FROM = 4  # a placed actor's properties: after its state frame and net index - 26 bytes in Sanctuary_P (not
PROPS_UNTIL = 96  # worked out: the first offset whose list parses with a Location - _actor_properties)


def placed(packages: list[Path]) -> list[list[Any]]:
    """The level challenge objects placed in these packages (a map's: its persistent level's and its streaming
    levels'): [[x, y, z, number, challenge path], ...] - worked out by the worker, cached on disk per package set."""
    data = gamework.asset({"fn": gamework.fn(placed_job), "paths": [str(p) for p in packages]}, packages)
    return json.loads(data) if data else []


class _NamesFirst(Package):
    """A package whose export table is read only when asked (read_exports): its names first - a map's packages mostly
    have no level challenge object, and their export tables were most of the job's time (Sanctuary's 18: 1.6 of 2.7 s,
    LZO). Not kept open (upk.opened's: the worker's other jobs' packages) - one job per map, its result cached."""

    def _read_exports(self, count: int, offset: int) -> None:
        self._exports_at = (count, offset)
        self.exports = []

    def read_exports(self) -> None:
        Package._read_exports(self, *self._exports_at)


def placed_job(paths: list[str]) -> bytes:
    out: list[list[Any]] = []
    for path in paths:
        pkg = _NamesFirst(Path(path))
        try:
            if "AssociatedChallenge" not in pkg.names:
                continue  # (no object of it has one: its exports not read)
            pkg.read_exports()
            start = [PROPS_FROM]  # (the last actor's properties' offset: tried first - _actor_properties)
            for i in range(len(pkg.exports)):
                if pkg.class_name(i) not in CLASSES:
                    continue
                props = _actor_properties(pkg, pkg.export_data(i), start)
                if props is None or "AssociatedChallenge" not in props or "Location" not in props:
                    continue
                challenge = pkg.ref_path(struct.unpack_from("<i", props["AssociatedChallenge"][1])[0])
                x, y, z = struct.unpack_from("<fff", props["Location"][1])
                # (a ByteProperty; not written: its default, 1 - Sanctuary's first symbol)
                number = int.from_bytes(props["NumberInChallengeGroup"][1], "little") if "NumberInChallengeGroup" in props else 1
                if challenge:
                    out.append([round(x), round(y), round(z), number, challenge])
        finally:
            pkg.close()
    return json.dumps(out).encode()


def _actor_properties(pkg: Any, data: bytes, start: list[int]) -> dict[str, tuple[str, bytes]] | None:
    """A placed actor's tagged properties: after its state frame (a size of its own), the first offset whose list
    parses to its end with a Location or a definition - `start`'s first (the last actor's: the same frame, mostly),
    then the others, `start` set to the one found; None if none does."""
    for o in (start[0], *range(PROPS_FROM, min(len(data), PROPS_UNTIL))):
        try:
            props, _end = pkg.properties(data, o)
        except Exception:  # noqa: BLE001, S112 - not the list's start
            continue
        if "Location" in props or "InteractiveObjectDefinition" in props:
            start[0] = o
            return props
    return None
