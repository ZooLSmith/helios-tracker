# Dev tool: writes the website's English (assets/i18n/en.js) into its pages (_work/web_documentation/*.html), so the
# HTML itself holds the text - search engines and anything without JavaScript read it there (Google renders the
# script late, if at all). The pages keep their keys: i18n.js still swaps the text for the visitor's language.
# Run it after editing en.js or a page's keys; --check only says which pages are out of date (exit 1).
#   python tools/site_text.py [--check]
import html
import json
import re
import subprocess
import sys
from html.parser import HTMLParser

import project

ROOT = project.ROOT / "_work" / "web_documentation"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# i18n.js's ATTRS: data-i18n-<name> -> the attribute it fills
ATTRS = {"data-i18n-title": "title", "data-i18n-label": "aria-label", "data-i18n-placeholder": "placeholder",
         "data-i18n-content": "content", "data-i18n-alt": "alt"}


def english() -> dict:
    # en.js is a module (export default {...}): Node reads it, as the browser does
    url = (ROOT / "assets" / "i18n" / "en.js").as_uri()
    out = subprocess.run(["node", "--input-type=module", "-e",
                          f"const m = await import({json.dumps(url)}); console.log(JSON.stringify(m.default));"],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


class Spans(HTMLParser):
    """The edits a page needs: (start, end, text) - an element's content, or a start tag rewritten."""

    def __init__(self, source: str, catalog: dict):
        super().__init__(convert_charrefs=False)
        self.source, self.catalog = source, catalog
        self.lines = [0]
        for m in re.finditer("\n", source):
            self.lines.append(m.end())
        self.stack = []  # [tag, content start, key or None]
        self.inside = 0  # how many data-i18n elements we're in (their content is replaced whole)
        self.edits = []

    def at(self) -> int:
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def text(self, key: str) -> str:
        if key not in self.catalog:
            raise SystemExit(f"no English for {key!r}")
        return self.catalog[key]

    def handle_starttag(self, tag, attrs):
        start = self.at()
        raw = self.get_starttag_text()
        end = start + len(raw)
        attrs = dict(attrs)
        if not self.inside:
            tag_text = raw
            for data, attr in ATTRS.items():
                if data in attrs:
                    value = html.escape(self.text(attrs[data]), quote=True)
                    filled, n = re.subn(rf'(\s{re.escape(attr)}=")[^"]*(")', lambda m: m[1] + value + m[2], tag_text)
                    tag_text = filled if n else re.sub(r"\s*/?>$", lambda m: f' {attr}="{value}"' + m[0], tag_text)
            if tag_text != raw:
                self.edits.append((start, end, tag_text))
        if tag in VOID or raw.endswith("/>"):
            return
        key = attrs.get("data-i18n") if not self.inside else None
        self.stack.append([tag, end, key])
        if key is not None:
            self.inside += 1

    def handle_endtag(self, tag):
        while self.stack:
            open_tag, content, key = self.stack.pop()
            if key is not None:
                self.inside -= 1
                if open_tag == tag:
                    self.edits.append((content, self.at(), self.text(key)))
            if open_tag == tag:
                return


def fill(source: str, catalog: dict) -> str:
    parser = Spans(source, catalog)
    parser.feed(source)
    parser.close()
    for start, end, text in sorted(parser.edits, reverse=True):
        source = source[:start] + text + source[end:]
    return source


project.require(ROOT if ROOT.is_dir() else None, "The site's worktree (git worktree add _work/web_documentation documentation)")
check = "--check" in sys.argv[1:]
catalog = english()
stale = []
for page in sorted(ROOT.glob("*.html")):
    raw = page.read_bytes()  # (bytes: the file's own line endings kept)
    source = raw.decode("utf-8")
    filled = fill(source, catalog)
    if filled != source:
        stale.append(page.name)
        if not check:
            page.write_bytes(filled.encode("utf-8"))
if check:
    print("out of date: " + ", ".join(stale) if stale else "every page has its English")
    sys.exit(1 if stale else 0)
print("written: " + ", ".join(stale) if stale else "nothing to write")
