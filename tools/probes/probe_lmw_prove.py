# Dev probe (in game): the Loot Midget World crash, made on purpose - proves collector._levels holds. The mod's level
# merges load other maps' persistent levels outside the world (a Tundra Express chandelier's GetTargetName crashed
# Helios Tracker in Three Horns - Divide); this loads one the same way (unrealsdk.load_package: Tundra Express's map
# package, its level never added to the world), then runs the collector's own object scan and record building - the path
# that crashed - at once (its scan is every 120 s). Expected: Tundra Express's objects found, none of the world's, each
# record None (skipped: no game function called on it), the map's own objects built as usual. Before the fix this
# crashed the game.
# Run it in any map but Tundra Express (Three Horns - Divide), Helios Tracker on.
# Writes probe_lmw_prove.txt in the mod's data folder (sdk_mods/.helios_tracker; overwrites; after each section)
#   py exec(open(r"<repo>\tools\probes\probe_lmw_prove.py").read())
import sys
from collections import Counter

import unrealsdk
from mods_base import ENGINE

from helios_tracker.paths import DATA

OUT = DATA / "probe_lmw_prove.txt"
PACKAGE = "TundraExpress_P"
lines: list[str] = []


def _write() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


wi = ENGINE.GetCurrentWorldInfo()
current = str(wi.GetStreamingPersistentMapName())
lines.append(f"current map: {current}")
_write()
if current.lower() == PACKAGE.lower():
    raise RuntimeError("in Tundra Express itself: run it in another map")

package = unrealsdk.load_package(PACKAGE)
lines.append(f"loaded {package._path_name()}")
_write()

collector = sys.modules["helios_tracker"]._collector
collector._world_levels = None  # (this tick's levels: read again)
levels = collector._levels()
ios = [io for io in unrealsdk.find_all("WillowInteractiveObject", exact=False) if not io.Name.startswith("Default__")]
outside = [io for io in ios if io.Outer is not None and io.Outer.Class.Name == "Level"
           and io.Outer._get_address() not in levels]
lines.append(f"interactive objects: {len(ios)}, in a level outside the world's: "
             f"{len(outside)} {dict(Counter(io.Outer._path_name() for io in outside))}")
lines.append(f"collector._in_world on them: {dict(Counter(collector._in_world(io) for io in outside))}")
_write()

lines.append("\nthe collector's scan and record building (the path that crashed)...")
_write()
collector._scan_objects()
rounds = 0
while collector._pending_records and rounds < 10000:
    collector._build_pending_records()
    rounds += 1
lines.append(f"built in {rounds} rounds, pending left {len(collector._pending_records)}")
records = collector._object_records
outside_keys = {(io._get_address(), str(io.Name)) for io in outside}
outside_records = [records.get(key, "<none: not scanned>") for key in outside_keys]
lines.append(f"their records: {dict(Counter('None (skipped)' if r is None else str(r)[:60] for r in outside_records))}")
own = [records.get((io._get_address(), str(io.Name))) for io in ios
       if io.Outer is not None and io.Outer.Class.Name == "Level" and io.Outer._get_address() in levels]
lines.append(f"the map's own objects: {len(own)}, records built {sum(r is not None for r in own)}")
lines.append("\nstill running: the fix holds")
_write()
