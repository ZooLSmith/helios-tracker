# Dev probe (in game): writes probe_damage_lean.py's results from what it collected, when its own end failed (its
# first version: `lines += ...` in _tick made `lines` a local - UnboundLocalError after the hooks were removed).
# Run in the same console, after the probe: it reads the probe's globals (events, timing, named, kills...).
# Appends to tools/probes/probe_damage_lean.txt
#   py exec(open(r"<repo>\tools\probes\probe_damage_lean_report.py").read())
_remove()  # noqa: F821 - (already removed by the failed end: harmless)
_out = [f"== 2. {len(events)} hits in {DURATION:.0f} s; the busiest second: {max(per_second.values(), default=0)}",  # noqa: F821
        "-- our hooks' bodies (calls, mean us, max us, total ms)"]
for _label, (_n, _total, _top) in sorted(timing.items()):  # noqa: F821
    _out.append(f"   {_label}: {_n} calls, {_total / _n * 1e6:.1f} us mean, {_top * 1e6:.1f} us max, {_total * 1e3:.1f} ms")
_out.append(f"-- the first {len(named)} hits, named")  # noqa: F821
_out.extend(named)  # noqa: F821
_out.append("-- deaths and objects killed")
_out.extend(kills or ["   (none)"])  # noqa: F821
_out.append(f"-- open TakeDamage calls left on the stack: {len(causers)} (should be 0)")  # noqa: F821
_out.append("== done (written by probe_damage_lean_report.py)")
with OUT.open("a", encoding="utf-8") as _f:  # noqa: F821
    _f.write("\n".join(_out) + "\n")
print(f"[helios probe] {OUT.stem}: report written - {OUT}")  # noqa: F821
