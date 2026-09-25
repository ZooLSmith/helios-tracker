"""
The web side: a small threaded HTTP server (stdlib only) serving the page, the map images and a
Server-Sent Events stream.

No SDK imports and no UObjects here, ever: the game thread publishes plain JSON strings / bytes to
the Hub, the server threads only read them.

    GET /             the page (web/index.html; every file is read from disk on each request)
    GET /<path>.js|css|png|svg|woff2   its modules / stylesheets / images / fonts under web/ (js/, js/ui/, i18n/,
                             css/, img/, fonts/: the title's "H", ours)
    GET /events       SSE stream: "level", "state", "objects", "players" events, each the latest JSON
    GET /image/<level>/<n>   raw texture data of map image n of level <level> (decoded by the page)
    GET /font/<slug>.ttf     the game's UI fonts, rebuilt as TrueType (gamefonts.py; 404 until extracted)
    GET /icon/<path>.png     a skill icon ("SharedSkillIcons_Soldier.SkillIcon-Able": gameicons.py, files only)
    GET /cardicon/<kind>/<key>.png   an item card icon: kind manufacturer / type / element, the game's key ("maliwan",
                             "pistol", "shock")
"""

import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import gamescan
from .gamecards import card_png
from .gameicons import icon_png

WEB_DIR = Path(__file__).parent / "web"
# Files served from WEB_DIR: lowercase names, folders allowed, no dots but the extension (no "..")
STATIC = re.compile(r"/(?:[a-z0-9_-]+/)*[a-z0-9_-]+\.(js|css|png|svg|woff2)")
TYPES = {"js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "png": "image/png",
         "svg": "image/svg+xml", "woff2": "font/woff2"}
FONT = re.compile(r"/font/([a-z0-9-]+)\.ttf")
ICON = re.compile(r"/icon/((?:UI_[A-Za-z0-9]+_)?SharedSkillIcons_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+)\.png", re.I)
CARD_ICON = re.compile(r"/cardicon/(manufacturer|type|element)/([A-Za-z0-9_]+)\.png")
SCAN_WAIT = 30.0  # s a font / icon request waits for the game files' index (gamescan) before giving up
# Pages from these origins may read everything here (CORS): the project's site - its /live/ page opens the map through
# a tunnel from a stable address, so the page's settings (localStorage: per origin) survive the tunnel's changing
# ones - and pages on this PC (localhost, 127.0.0.1, any port: a local preview of the site)
SITE_ORIGINS = ("https://helios-tracker.zoolsmith.com", "https://zoolsmith.github.io")  # (the site: its domain, GitHub's own address)
LOCAL_ORIGIN = re.compile(r"http://(?:localhost|127\.0\.0\.1)(?::\d+)?")
KEEPALIVE = 10.0  # s between SSE comments when nothing changes (detects closed tabs)


class Hub:
    """Latest payload per channel, with versions; SSE handlers wait for changes."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._channels: dict[str, tuple[int, str]] = {}
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
            out = []
            for channel, (version, payload) in self._channels.items():
                if seen.get(channel) != version:
                    seen[channel] = version
                    out.append((channel, payload))
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
        if path.startswith(("/font/", "/icon/", "/cardicon/")) and not gamescan.ready():
            gamescan.wait(SCAN_WAIT)  # (the game's files not indexed yet: a page just opened - its scan's running)
        try:
            if path in ("/", "/index.html"):
                self._send(HTTPStatus.OK, "text/html; charset=utf-8", (WEB_DIR / "index.html").read_bytes())
            elif (m := STATIC.fullmatch(path)) and (WEB_DIR / path[1:]).is_file():
                self._send(HTTPStatus.OK, TYPES[m[1]], (WEB_DIR / path[1:]).read_bytes())
            elif path == "/events":
                self._events()
            elif path.startswith("/image/"):
                self._image(path)
            elif (m := FONT.fullmatch(path)) and (data := (self.server.hub.fonts or {}).get(m[1])) is not None:
                self._send(HTTPStatus.OK, "font/ttf", data)
            elif (m := ICON.fullmatch(path)) and (data := icon_png(m[1])) is not None:
                self._send(HTTPStatus.OK, "image/png", data)
            elif (m := CARD_ICON.fullmatch(path)) and (data := card_png(m[1], m[2])) is not None:
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
                for channel, payload in updates:
                    self.wfile.write(f"event: {channel}\ndata: {payload}\n\n".encode())
                self.wfile.flush()
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
