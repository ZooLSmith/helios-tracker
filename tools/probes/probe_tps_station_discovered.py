# Dev probe (in game, the Pre-Sequel), instant: whether WillowPlayerController.IsStationDiscovered(StationDefinition)
# -> bool tells the fast travel stations a player unlocked - TPS's controller has no ActivatedTeleportersList (BL2's)
# nor any field listing them (probe_fast_travel_tps.txt); the function was found by probe_tps_stations.txt (its
# signature). The one function called: that one, on each FastTravelStationDefinition loaded. Compare with the fast
# travel menu's stations (open it in game: probe_fast_travel_tps.txt had Airstrip, Spaceport, Ma_Deck13_FT,
# MoonSurfaceFastTravel, ComFacility, Outlands2, Outlands, WreckCrater, EridianSlaughter in Outlands_P2).
# Writes tools/probes/probe_tps_station_discovered.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_tps_station_discovered.py").read())
import sys
import time
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_tps_station_discovered.txt"
lines: list[str] = []


def _flush() -> None:
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    lines.append(f"map: {ENGINE.GetCurrentWorldInfo().GetStreamingPersistentMapName()}")
    pc = get_pc()
    stations = sorted((s for s in unrealsdk.find_all("FastTravelStationDefinition", exact=True)
                       if not s.Name.startswith("Default__")), key=lambda s: str(s.Name))
    found = []
    started = time.perf_counter()
    for s in stations:
        try:
            yes = bool(pc.IsStationDiscovered(s))
        except Exception as ex:  # noqa: BLE001
            lines.append(f"   {s.Name}: <{type(ex).__name__}: {ex}>")
            _flush()
            continue
        if yes:
            found.append(str(s.Name))
        lines.append(f"   {s.Name} ({s.StationLevelName}): {yes}")
    ms = (time.perf_counter() - started) * 1000
    lines.insert(1, f"== {len(found)} of {len(stations)} discovered ({ms:.2f} ms for all): {found}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
_flush()
print(f"[helios probe] probe_tps_station_discovered: done - {OUT}")
