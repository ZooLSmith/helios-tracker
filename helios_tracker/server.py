"""
The web side: a small threaded HTTP server (stdlib only) serving the page, the map images and a
Server-Sent Events stream.

No SDK imports and no UObjects here, ever: the game thread publishes plain JSON strings / bytes to
the Hub, the server threads only read them.

    GET /             the page (web/index.html; every file is read from disk on each request)
    GET /<path>.js|css|png|svg|woff2   its modules / stylesheets / images / fonts under web/ (js/, js/ui/, i18n/,
                             css/, img/, fonts/: the title's "H", ours)
    GET /events       SSE stream: "level", "state" (what moves), "pawninfo", "pickups", "objects", "players"... events,
                      each the latest JSON - record channels only what changed since the page's version (Hub)
    GET /image/<level>/<n>   raw texture data of map image n of level <level> (decoded by the page)
    GET /font/<slug>.ttf     the game's UI fonts, rebuilt as TrueType (gamefonts.py; 404 until extracted)
    GET /icon/<path>.png     a skill icon ("SharedSkillIcons_Soldier.SkillIcon-Able": gameicons.py, files only)
    GET /cardicon/<kind>/<key>.png   an item card icon: kind manufacturer / type / element, the game's key ("maliwan",
                             "pistol", "shock")
    GET /texture/<path>.png  an always-loaded texture by its object path (a pickup's own icon: gameicons)
"""

import json
import re
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import bl1map, games, paths
from .frames import FRAMES
from .gameicons import icon_png, texture_by_path

# The page's files: paths.read("web/...") (a folder, or inside the .sdkmod).
# Files served from web/: lowercase names, folders allowed, no dots but the extension (no "..")
STATIC = re.compile(r"/(?:[a-z0-9_-]+/)*[a-z0-9_-]+\.(js|css|png|svg|woff2)")
TYPES = {"js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "png": "image/png",
         "svg": "image/svg+xml", "woff2": "font/woff2"}
FONT = re.compile(r"/font/([a-z0-9-]+)\.ttf")
ICON = re.compile(r"/icon/((?:UI_[A-Za-z0-9]+_)?SharedSkillIcons_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+)\.png", re.I)
MENU_ICON = re.compile(r"/icon/(menu(?:\.[A-Za-z0-9_]+){5})\.png")  # a menu movie's icon (bl1map.MENU_ICON: BL1's skills)
CARD_ICON = re.compile(r"/cardicon/(manufacturer|type|element)/([A-Za-z0-9_]+)\.png")
TEXTURE = re.compile(r"/texture/([A-Za-z0-9_]+(?:\.[A-Za-z0-9_-]+)+)\.png")  # an always-loaded texture by path (gameicons)
SCAN_WAIT = 30.0  # s a font / icon request waits for the game files' index (gamescan) before giving up
# Pages from these origins may read everything here (CORS): the project's site - its /live/ page opens the map through
# a tunnel from a stable address, so the page's settings (localStorage: per origin) survive the tunnel's changing
# ones - and pages on this PC (localhost, 127.0.0.1, any port: a local preview of the site)
SITE_ORIGINS = ("https://helios-tracker.zoolsmith.com", "https://zoolsmith.github.io")  # (the site: its domain, GitHub's own address)
LOCAL_ORIGIN = re.compile(r"http://(?:localhost|127\.0\.0\.1)(?::\d+)?")
KEEPALIVE = 10.0  # s between SSE comments when nothing changes (detects closed tabs)


_SEP = (",", ":")
_MISSING = object()
HISTORY = 64  # versions of a record channel whose changes are kept (~6 s of states): a page further behind gets it whole


class _Records:
    """A record channel (objects, pickups, the pawns...): its records by id (a dict's "i", a row's first item), and what
    changed at each version - a page gets only the changes since the version it has (the stream re-sent every list
    whole for one record changing: 140 objects for a chest opened, the pickups 10 times a second while one rolled).

    A message: {"v": version, "b": the version it applies to, "m": the channel's own fields (level...), "set": records
    added / changed, "del": ids gone, "o": every id in order (only when the order changed - not just appended)}. From the
    version before: a changed dict record carries only its changed fields, "-": the ones it lost; from further back
    ("rep": 1) the records whole; a page too far behind (or new): "full": 1, everything. data.js keyed() merges them."""

    def __init__(self, list_key: str) -> None:
        self.list_key = list_key  # the page's list of them in the message ("objects", "pawns"...)
        self.version = 0
        # id -> the record as last published, in order: a shallow copy (the collector changes some in place - a
        # container's "looted": the same dict would compare equal to itself); nested parts come from caches, not edited
        self.recs: dict[str, Any] = {}
        self._json: dict[str, str] = {}  # id -> its JSON, made when a message needs it whole (a new page, one behind)
        self.meta: dict[str, Any] | None = None  # its own fields but the stamp: what counts as a change
        self.meta_json = "{}"
        self.history: deque[tuple[int, frozenset[str], bool]] = deque(maxlen=HISTORY)  # (version, ids touched, reordered)
        self.step = ""  # the last version's message from the one before (what an up-to-date page gets)

    def update(self, records: list[Any], meta: dict[str, Any], stamp: dict[str, Any]) -> bool:
        """The records now; False (no new version) if nothing changed. The stamp (the state's time) goes out with a
        change, never makes one. Compared as objects, not JSON: a json.dumps per record, 10 times a second for the
        state's 50 pawns, made the game stutter again (8x the cost)."""
        new: dict[str, Any] = {}
        for r in records:
            if isinstance(r, list):
                new[str(r[0])] = list(r)
            else:
                new[str(r["i"])] = dict(r)
        old = self.recs
        changed = [rid for rid, r in new.items() if old.get(rid, _MISSING) != r]  # (in the new order)
        gone = sorted(rid for rid in old if rid not in new) if len(new) - len(changed) < len(old) else []
        # the order: kept, the new ones at the end - what a page merging them gets without "o"
        reordered = [rid for rid in old if rid in new] + [rid for rid in new if rid not in old] != list(new)
        if self.version and not changed and not gone and not reordered and meta == self.meta:
            return False
        parts = []
        for rid in changed:
            r = new[rid]
            self._json.pop(rid, None)
            was = old.get(rid)
            if isinstance(r, dict) and isinstance(was, dict):  # its changed fields only (a player: 40 KB, "equipped" changed)
                part = {"i": r["i"], **{k: v for k, v in r.items() if k != "i" and was.get(k, _MISSING) != v}}
                if lost := [k for k in was if k not in r]:
                    part["-"] = lost
                parts.append(json.dumps(part, separators=_SEP))
            else:
                parts.append(self._rec_json(rid, r))
        for rid in gone:
            self._json.pop(rid, None)
        self.version += 1
        self.recs, self.meta = new, dict(meta)
        self.meta_json = json.dumps({**meta, **stamp}, separators=_SEP)
        self.history.append((self.version, frozenset(changed) | frozenset(gone), reordered))
        self.step = self._message(self.version - 1, parts, gone, reordered)
        return True

    def _rec_json(self, rid: str, r: Any) -> str:
        j = self._json.get(rid)
        if j is None:
            j = self._json[rid] = json.dumps(r, separators=_SEP)
        return j

    def _message(self, base: int, parts: list[str], gone: list[str], reordered: bool, whole: bool = False) -> str:
        out = f'{{"v":{self.version},"b":{base},"m":{self.meta_json},"set":[{",".join(parts)}]'
        if gone:
            out += ',"del":' + json.dumps(gone, separators=_SEP)
        if reordered:
            out += ',"o":' + json.dumps(list(self.recs), separators=_SEP)
        return out + (',"rep":1}' if whole else "}")

    def since(self, seen: int | None) -> str:
        """The message for a page that has version `seen` (None: nothing yet)."""
        if seen == self.version - 1:
            return self.step
        if seen is not None and self.history and self.history[0][0] - 1 <= seen < self.version:
            touched: set[str] = set()
            reordered = False
            for version, ids, moved in self.history:
                if version > seen:
                    touched |= ids
                    reordered |= moved
            FRAMES.server_count("catch-up")
            parts = [self._rec_json(rid, r) for rid, r in self.recs.items() if rid in touched]
            gone = sorted(rid for rid in touched if rid not in self.recs)  # (gone since - or came and went: the page ignores those)
            return self._message(seen, parts, gone, reordered, whole=True)
        FRAMES.server_count("snapshot")
        return f'{{"v":{self.version},"full":1,"m":{self.meta_json},"set":[{",".join(self._rec_json(rid, r) for rid, r in self.recs.items())}]}}'

    def snapshot(self) -> dict[str, Any]:
        """Everything, as one message of the old kind: its own fields + the list (tools, the offline check)."""
        return {**json.loads(self.meta_json), self.list_key: list(self.recs.values())}


class Hub:
    """Latest payload per channel, with versions; SSE handlers wait for changes. Record channels (publish_records):
    each page gets the changes since the version it has."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._channels: dict[str, tuple[int, str]] = {}  # (a record channel: its last version's changes)
        self._records: dict[str, _Records] = {}
        self._images: dict[tuple[int, int], bytes] = {}
        self.fonts: dict[str, bytes] | None = None  # the game's fonts by slug (None: not extracted yet)
        self.closed = False
        self.clients = 0  # open SSE streams: the collector does nothing while there are none

    def connected(self, delta: int) -> None:
        with self._cond:
            self.clients += delta

    def publish(self, channel: str, payload: str) -> None:
        with self._cond:
            version = self._channels.get(channel, (0, ""))[0] + 1
            self._channels[channel] = (version, payload)
            self._cond.notify_all()

    def publish_records(self, channel: str, list_key: str, records: list[Any], meta: dict[str, Any] | None = None,
                        stamp: dict[str, Any] | None = None) -> bool:
        """A record channel's records now (dicts with an "i", or rows [id, ...]) and its own fields (meta: the level...);
        only what changed goes out (_Records). False if nothing did."""
        with self._cond:
            recs = self._records.get(channel)
            if recs is None or recs.list_key != list_key:
                recs = self._records[channel] = _Records(list_key)
            if not recs.update(records, meta or {}, stamp or {}):
                return False
            self._channels[channel] = (recs.version, recs.step)
            self._cond.notify_all()
            return True

    def latest(self, channel: str) -> str:
        """A channel's latest payload whole (a record channel: all its records - its snapshot)."""
        with self._cond:
            recs = self._records.get(channel)
            return json.dumps(recs.snapshot(), separators=_SEP) if recs is not None else self._channels[channel][1]

    def set_images(self, level: int, images: list[bytes]) -> None:
        """Replaces all images (only the current level's are kept)."""
        with self._cond:
            self._images = {(level, i): data for i, data in enumerate(images)}

    def image(self, level: int, index: int) -> bytes | None:
        with self._cond:
            return self._images.get((level, index))

    def wait(self, seen: dict[str, int], timeout: float) -> list[tuple[str, str]]:
        """Channels newer than `seen` (updated in place), waiting up to `timeout` for one."""
        with self._cond:
            self._cond.wait_for(lambda: self.closed or self._newer(seen), timeout)
            start = time.perf_counter()
            out = []
            for channel, (version, payload) in self._channels.items():
                if seen.get(channel) != version:
                    recs = self._records.get(channel)
                    out.append((channel, recs.since(seen.get(channel)) if recs is not None else payload))
                    seen[channel] = version
            if out:  # (the messages built under the lock: the collector's publish waits meanwhile)
                FRAMES.server_work("stream", time.perf_counter() - start)
            return out

    def _newer(self, seen: dict[str, int]) -> bool:
        return any(seen.get(c) != v for c, (v, _) in self._channels.items())

    def open(self) -> None:
        with self._cond:
            self.closed = False

    def close(self) -> None:
        """Ends every SSE stream (the payloads are kept, for the next server)."""
        with self._cond:
            self.closed = True
            self._cond.notify_all()


class _Handler(BaseHTTPRequestHandler):
    server: "TrackerServer"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # no per-request console spam

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/events":  # (a stream: its messages are timed as they're built - Hub.wait)
            try:
                self._events()
            except (ConnectionError, TimeoutError):
                pass  # tab closed / navigated away
            return
        games.GAME.wait_for_assets(path, SCAN_WAIT)  # (the game's files not read yet: a page just opened - games.py)
        start = time.perf_counter()  # (after the waits: they hold no GIL - the work from here may)
        try:
            self._get(path)
        finally:
            FRAMES.server_work("request", time.perf_counter() - start)

    def _get(self, path: str) -> None:
        try:
            if path in ("/", "/index.html"):
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", paths.read("web/index.html") or b"")
            elif (m := STATIC.fullmatch(path)) and (data := paths.read("web" + path)) is not None:
                self._send(HTTPStatus.OK, TYPES[m[1]], data)
            elif path.startswith("/image/"):
                self._image(path)
            elif (m := FONT.fullmatch(path)) and (data := (self.server.hub.fonts or {}).get(m[1])) is not None:
                self._send(HTTPStatus.OK, "font/ttf", data)
            elif (m := MENU_ICON.fullmatch(path)) and (data := bl1map.menu_icon_png(m[1])) is not None:
                self._send(HTTPStatus.OK, "image/png", data)
            elif (m := ICON.fullmatch(path)) and (data := icon_png(m[1])) is not None:
                self._send(HTTPStatus.OK, "image/png", data)
            elif (m := CARD_ICON.fullmatch(path)) and (data := games.GAME.card_icon_png(m[1], m[2])) is not None:
                self._send(HTTPStatus.OK, "image/png", data)
            elif (m := TEXTURE.fullmatch(path)) and (data := texture_by_path(m[1])) is not None:
                self._send(HTTPStatus.OK, "image/png", data)
            else:
                self._send(HTTPStatus.NOT_FOUND, "text/plain", b"not found")
        except (ConnectionError, TimeoutError):
            pass  # tab closed / navigated away

    def _cors(self) -> None:
        """The CORS header for an allowed page's origin (see SITE_ORIGINS); none for anyone else."""
        origin = self.headers.get("Origin", "")
        if origin in SITE_ORIGINS or LOCAL_ORIGIN.fullmatch(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, status: HTTPStatus, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _image(self, path: str) -> None:
        try:
            level, index = (int(p) for p in path.split("/")[2:4])
        except ValueError:
            self._send(HTTPStatus.BAD_REQUEST, "text/plain", b"bad image path")
            return
        data = self.server.hub.image(level, index)
        if data is None:
            self._send(HTTPStatus.NOT_FOUND, "text/plain", b"no such image (level changed?)")
        else:
            self._send(HTTPStatus.OK, "application/octet-stream", data)

    def _events(self) -> None:
        hub = self.server.hub
        self.send_response(HTTPStatus.OK)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        seen: dict[str, int] = {}
        hub.connected(1)
        try:
            while not hub.closed:
                updates = hub.wait(seen, KEEPALIVE)
                if hub.closed:
                    return
                if not updates:
                    self.wfile.write(b": keepalive\n\n")
                sent = 0
                for channel, payload in updates:
                    data = f"event: {channel}\ndata: {payload}\n\n".encode()
                    sent += len(data)
                    self.wfile.write(data)
                self.wfile.flush()
                if sent:
                    FRAMES.server_work("write", 0.0, sent)  # (the bytes; the write itself waits without the GIL)
        finally:
            hub.connected(-1)


class TrackerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # on Windows SO_REUSEADDR would let a stale server keep the port
    # The listen backlog (default 5): Windows refuses connections beyond it. A tunnel / proxy
    # (cloudflared) opens one per file of the page at once - 30+ modules - while the accept thread waits
    # for the game thread (it holds the GIL during its ticks): refused, the proxy answers 502
    request_queue_size = 128

    def __init__(self, host: str, port: int, hub: Hub) -> None:
        self.hub = hub
        super().__init__((host, port), _Handler)
        hub.open()
        self._thread = threading.Thread(target=self.serve_forever, kwargs={"poll_interval": 0.25},
                                        name="helios_tracker http", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return self.server_address[1]

    def stop(self) -> None:
        self.hub.close()  # ends the SSE loops
        self.shutdown()  # waits for serve_forever to return (<= poll_interval)
        self.server_close()
        self._thread.join(2.0)
