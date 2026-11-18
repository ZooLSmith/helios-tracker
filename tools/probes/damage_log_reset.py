# Dev (in game): the damage log's measures from zero (damage_log_stats.py prints them) - reset, fight, print: that
# fight's cost alone. The page's: heliosDamagePerf.reset() in the browser's console.
#   py exec(open(r"<repo>\tools\probes\damage_log_reset.py").read())
import sys

sys.modules["helios_tracker"]._collector.damage.reset_stats()
print("[helios] damage log: measures reset")
