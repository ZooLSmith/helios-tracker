# Dev (in game): the damage log's counts and its hooks' cost, in the console (helios_tracker/damage.py summary()) - its
# hits, events, batches; our hooks' calls, mean / max time; the ids given; the open frames (0 between hits).
# The page's catch-up, by hand: http://127.0.0.1:8777/damage?since=0 (the batches as JSON).
#   py exec(open(r"<repo>\tools\probes\damage_log_stats.py").read())
import sys

print("[helios] " + sys.modules["helios_tracker"]._collector.damage.summary())
