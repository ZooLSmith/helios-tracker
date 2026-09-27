# Dev tool: serves the website's worktree (_work/web_documentation) like GitHub Pages does - its links have no .html
# (/install is install.html), which python -m http.server doesn't know.
#   python tools/site_preview.py [port]      (default 8000; then http://localhost:8000/)
import http.server
import os
import sys
from functools import partial

import project

ROOT = project.ROOT / "_work" / "web_documentation"


class CleanUrls(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        file = super().translate_path(path)
        if not os.path.exists(file) and os.path.isfile(file + ".html"):
            return file + ".html"
        return file

    def send_error(self, code, message=None, explain=None):
        # a missing page: the site's own 404.html, as GitHub Pages serves it
        page = ROOT / "404.html"
        if code == 404 and page.is_file():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)


project.require(ROOT if ROOT.is_dir() else None, "The site's worktree (git worktree add _work/web_documentation documentation)")
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
print(f"http://localhost:{port}/  ({ROOT})")
http.server.ThreadingHTTPServer(("127.0.0.1", port), partial(CleanUrls, directory=str(ROOT))).serve_forever()
