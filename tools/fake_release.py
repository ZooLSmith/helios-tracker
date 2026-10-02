# Dev tool: a local stand-in for the public repo's GitHub releases, to test the mod's updater without publishing.
# Builds the working tree's .sdkmod with another version in its pyproject (default: ours, patch + 1), serves it the
# way GitHub's API does (/releases/latest: tag_name, html_url, assets[].browser_download_url), and points the game's
# updater at it (sdk_mods/.helios_tracker/update_source.txt - removed again on Ctrl+C).
#   python tools/fake_release.py [0.2.0] [tps] [--delay 2]   (--delay: seconds before each answer, like a slow network)
# In game (running the .sdkmod: tools/use_sdkmod.bat): the mod's options, Check for Updates -> the dialogs.
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import build_sdkmod
import project

PORT = 8780
ASSET = "helios_tracker.sdkmod"

args = sys.argv[1:]
delay = float(args[args.index("--delay") + 1]) if "--delay" in args else 0.0
key = "tps" if "tps" in args else "game"
pyproject = (project.ROOT / "helios_tracker" / "pyproject.toml").read_text(encoding="utf-8")
ours = re.search(r'(?m)^version = "(\d+)\.(\d+)\.(\d+)"$', pyproject)
version = next((a for a in args if re.fullmatch(r"\d+\.\d+\.\d+", a)), None)
version = version or f"{ours[1]}.{ours[2]}.{int(ours[3]) + 1}"
base = f"http://127.0.0.1:{PORT}"

sdkmod = build_sdkmod.build(project.ROOT / "_work" / "fake_release" / ASSET, version)
release = json.dumps({
    "tag_name": f"v{version}",
    "html_url": f"{base}/releases/v{version}",
    "assets": [{"name": ASSET, "browser_download_url": f"{base}/download/v{version}/{ASSET}"}],
}).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        time.sleep(delay)
        if self.path == "/releases/latest":
            body, kind = release, "application/json"
        elif self.path == f"/download/v{version}/{ASSET}":
            body, kind = sdkmod.read_bytes(), "application/octet-stream"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *a: object) -> None:  # noqa: A002
        print(f"  {self.address_string()} {format % a}")


data = project.require(project.path(key), f"The game ({key})") / "sdk_mods" / ".helios_tracker"
data.mkdir(parents=True, exist_ok=True)
pointer = data / "update_source.txt"
pointer.write_text(f"{base}/releases/latest\n", encoding="utf-8")
print(f"release v{version} at {base}/releases/latest (the updater points here: {pointer}) - Ctrl+C to stop")
try:
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
except KeyboardInterrupt:
    pass
finally:
    pointer.unlink(missing_ok=True)
    print("stopped; the updater points at GitHub again")
