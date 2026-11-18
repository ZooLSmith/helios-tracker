# Dev (in game): the damage log's counts and its cost, in the console (helios_tracker/damage.py summary()) - its hits
# (per second), events, batches; our hooks' calls, mean / max time, ms per second, the busiest second, each hook role's;
# the tick's draining (naming what's new, the JSON, publishing); the ids given; the open frames (0 between hits) - since
# the mod's start or the last reset (damage_log_reset.py: measure one fight alone).
# The page's side: in the browser's console, heliosDamagePerf() (web/js/damage/perf.js).
# The page's catch-up, by hand: http://127.0.0.1:8777/damage?since=0 (the batches as JSON).
#   py exec(open(r"<repo>\tools\probes\damage_log_stats.py").read())
import sys

for line in sys.modules["helios_tracker"]._collector.damage.summary().splitlines():
    print("[helios] " + line)
