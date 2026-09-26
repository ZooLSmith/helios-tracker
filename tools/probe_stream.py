# Dev probe (in game), 30 s in the background: what the event stream (/events) carries - per channel, how many
# messages and bytes a second the Hub publishes, and the "state" message broken down (pawns, pickups, the players'
# skill fields, the rest; what changed between two in a row) and, for the objects / mission log / players / shops, which
# records and fields changed from one message to the next. Reads the Hub's latest payloads only (no game calls).
# Keep the map page open (the collector does nothing without one), stand still a while, then move a little.
# Writes tools/probe_stream.txt (overwrites; at the end)
#   py exec(open(r"<repo>\tools\probe_stream.py").read())
import builtins
import json
import sys
import time
from pathlib import Path

from unrealsdk.hooks import Type, add_hook, remove_hook

MOD = sys.modules["helios_tracker"]
OUT = Path(MOD.__file__).resolve().parents[1] / "tools" / "probe_stream.txt"
RUN_FOR = 30.0
HOOK_ID = "helios_probe_stream"
RENDER = "WillowGame.WillowGameViewportClient:PostRender"
hub = MOD._hub  # noqa: SLF001
st = {"start": time.perf_counter(), "seen": {}, "msgs": {}, "bytes": {}, "states": [], "prev": None, "same": 0,
      "posonly": 0}


def _size(v) -> int:  # noqa: ANN001
    return len(json.dumps(v, separators=(",", ":")))


DIFFED = {"objects": "objects", "missionlog": "missions", "players": "players", "shops": "machines", "pickups": "pickups"}  # channel -> its list
st["last"] = {}
st["diffs"] = []
st["pickups"] = {"msgs": 0, "added": 0, "gone": 0, "fields": {}, "who": {}, "delta": {}, "names": {}}  # its changes, summed


def _records(msg: dict, key: str) -> dict:
    items = msg.get(key) or []
    return {str(r.get("i", n)): r for n, r in enumerate(items)} if isinstance(items, list) else {}


def _diff(channel: str, old: dict, new: dict, now: float) -> None:
    key = DIFFED[channel]
    a, b = _records(old, key), _records(new, key)
    added, gone = len(b.keys() - a.keys()), len(a.keys() - b.keys())
    fields = {}
    changed = 0
    for i in a.keys() & b.keys():
        if a[i] == b[i]:
            continue
        changed += 1
        for f in set(a[i]) | set(b[i]):
            if a[i].get(f) != b[i].get(f):
                fields[f] = fields.get(f, 0) + 1
    other = sorted(k for k in set(old) | set(new) if k != key and old.get(k) != new.get(k))
    if channel == "pickups":  # (every update at times: summed up at the end, not a line each)
        agg = st["pickups"]
        agg["msgs"] += 1
        agg["added"] += added
        agg["gone"] += gone
        for i in a.keys() & b.keys():
            for f in set(a[i]) | set(b[i]):
                if a[i].get(f) != b[i].get(f):
                    agg["fields"][f] = agg["fields"].get(f, 0) + 1
                    agg["who"][i] = agg["who"].get(i, 0) + 1
                    if f in ("x", "y", "z") and isinstance(a[i].get(f), (int, float)) and isinstance(b[i].get(f), (int, float)):
                        agg["delta"][f] = max(agg["delta"].get(f, 0), abs(b[i][f] - a[i][f]))
                        agg["names"][i] = b[i].get("n") or b[i].get("k") or "?"
        return
    st["diffs"].append(f"  {now:5.1f} s {channel}: {len(b)} records, {changed} changed (fields {dict(sorted(fields.items(), key=lambda kv: -kv[1]))}), "
                       f"+{added} -{gone}{f', other keys changed {other}' if other else ''}")


def _extra(p) -> dict:  # noqa: ANN001
    """A state pawn's fields past its position / health: rows [id, x, y, z, health?, {the rest}?], or older dicts."""
    if isinstance(p, list):
        return p[-1] if isinstance(p[-1], dict) else {}
    return p


def _tick(*_args) -> None:  # noqa: ANN002
    now = time.perf_counter() - st["start"]
    if now > RUN_FOR:
        _finish()
        return
    for channel, (version, payload) in list(hub._channels.items()):  # noqa: SLF001
        if st["seen"].get(channel) == version:
            continue
        missed = version - st["seen"].get(channel, version - 1)  # (several between two frames: counted, sized as this one)
        st["seen"][channel] = version
        st["msgs"][channel] = st["msgs"].get(channel, 0) + missed
        st["bytes"][channel] = st["bytes"].get(channel, 0) + missed * len(payload)
        if channel in DIFFED:  # what changed from the previous one: which records, which of their fields
            new = json.loads(hub.latest(channel))  # (a record channel sends changes: diffed whole)
            old = st["last"].get(channel)
            st["last"][channel] = new
            if old is not None:
                _diff(channel, old, new, now)
        if channel == "state":
            s = json.loads(hub.latest(channel))
            pawns, pickups = s.get("pawns", []), s.get("pickups", [])
            extras = [_extra(p) for p in pawns]
            skills = sum(_size({k: e[k] for k in ("ak", "ps", "mk") if k in e}) for e in extras)
            st["states"].append((len(payload), _size(pawns), _size(pickups), skills, len(pawns), len(pickups)))
            prev = st["prev"]
            if prev is not None:
                strip = lambda d: {k: v for k, v in d.items() if k != "t"}  # noqa: E731
                if strip(s) == strip(prev):
                    st["same"] += 1
                else:  # only positions / yaw moved?
                    def static(d):  # noqa: ANN001, ANN202
                        return [[p[0] if isinstance(p, list) else p.get("i"),
                                 {k: v for k, v in _extra(p).items() if k not in ("i", "x", "y", "z", "r", "h", "s")}]
                                for p in d.get("pawns", [])], d.get("pickups", [])
                    if static(s) == static(prev):
                        st["posonly"] += 1
            st["prev"] = s


def _finish() -> None:
    remove_hook(RENDER, Type.POST, HOOK_ID)
    secs = time.perf_counter() - st["start"]
    lines = [f"over {secs:.1f} s (page clients: {hub.clients})", "channel: messages/s, KB/s, average message size"]
    for ch in sorted(st["bytes"], key=lambda c: -st["bytes"][c]):
        n, b = st["msgs"][ch], st["bytes"][ch]
        lines.append(f"  {ch:12s} {n / secs:6.1f}/s  {b / secs / 1024:8.1f} KB/s  avg {b / max(n, 1) / 1024:7.1f} KB")
    total = sum(st["bytes"].values())
    lines.append(f"  total {total / secs / 1024:.1f} KB/s = {total / secs * 60 / 1024 / 1024:.1f} MB a minute")
    if st["states"]:
        n = len(st["states"])
        avg = [sum(x[i] for x in st["states"]) / n for i in range(6)]
        lines += ["state message (averages): "
                  f"{avg[0] / 1024:.1f} KB = pawns {avg[1] / 1024:.1f} KB ({avg[4]:.0f} of them; players' skill fields "
                  f"{avg[3] / 1024:.2f} KB) + pickups {avg[2] / 1024:.1f} KB ({avg[5]:.0f} of them) + the rest",
                  f"consecutive states: identical but the time {st['same']}, only positions / yaw / health changed "
                  f"{st['posonly']}, of {n - 1}"]
    pk = st["pickups"]
    if pk["msgs"]:
        top = sorted(pk["who"].items(), key=lambda kv: -kv[1])[:8]
        lines += [f"pickups: {pk['msgs']} changes, +{pk['added']} -{pk['gone']}, fields changed {pk['fields']}, "
                  f"largest move per update {pk['delta']}",
                  "  most changed: " + ", ".join(f"{pk['names'].get(i, i)} ({i}) {n}x" for i, n in top)]
    if st["diffs"]:
        lines += ["what changed from one message to the next (objects, mission log, players, shops):", *st["diffs"]]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


# What's already there counts as seen, not sent (counted once at the start, a 231 KB mission list read as 7.7 KB/s);
# the diffed channels start from it, so their first change is diffed too
st["seen"] = {c: v for c, (v, _) in list(hub._channels.items())}  # noqa: SLF001
for _channel in DIFFED:
    if _channel in st["seen"]:
        st["last"][_channel] = json.loads(hub.latest(_channel))
remove_hook(RENDER, Type.POST, HOOK_ID)
add_hook(RENDER, Type.POST, HOOK_ID, _tick)
builtins.helios_stream_stop = _finish
print(f"probe_stream: {RUN_FOR:.0f} s, writing {OUT}")
