// The site, at runtime: its text (i18n.js: the pages hold keys, the catalogs the words), search,
// language and theme, copy buttons, heading links. What it builds carries keys too (data-i18n...), so a language
// switch re-translates everything in place, like the tracker page.
// Search: the pages are PAGES - fetched, translated and indexed by section on the first search, in the browser;
// nothing is generated beforehand.

import { CATALOG, applyI18n, langPref, setLanguage, t } from "./i18n.js";

// The site's pages: [file, its label's key] - the bar's links and the footer's (the home: the logo), the search.
// The links without .html (GitHub Pages serves /install as install.html). A new page: here, and its keys in the
// catalogs.
const PAGES = [["index.html", null], ["install.html", "nav.install"], ["share.html", "nav.share"],
  ["troubleshooting.html", "nav.troubleshooting"]];
const THEMES = [["default", "ECHO-2"], ["hyperion", "Hyperion"], ["vladof", "Vladof"], ["dahl", "Dahl"], ["eridian", "Eridian"]]; // (the tracker's)
const THEME_KEY = "helios.site.theme";

// ---- icon menus (language, theme): a button with an icon, a small list of choices under it ----

// The icons: 12 x 12 inline SVGs drawn with currentColor, like the tracker's (its js/icons.js)
const ICONS = {
  language: `<circle cx="6" cy="6" r="4.8" fill="none" stroke="currentColor" stroke-width="1.1"/>` +
    `<ellipse cx="6" cy="6" rx="2.1" ry="4.8" fill="none" stroke="currentColor" stroke-width="1.1"/>` +
    `<path d="M1.4 4.4h9.2M1.4 7.6h9.2" stroke="currentColor" stroke-width="1.1"/>`,
  theme: `<circle cx="6" cy="6" r="4.8" fill="none" stroke="currentColor" stroke-width="1.1"/>` +
    `<path d="M6 1.2a4.8 4.8 0 0 0 0 9.6Z" fill="currentColor"/>`,
  search: `<circle cx="5.2" cy="5.2" r="3.6" fill="none" stroke="currentColor" stroke-width="1.2"/>` +
    `<path d="M7.9 7.9 10.6 10.6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>`,
  check: `<path d="M2.4 6.4 4.9 8.9 9.7 3.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
};
const svg = (name) => `<svg class="icon" viewBox="0 0 12 12" aria-hidden="true">${ICONS[name]}</svg>`;

// label: its key; items: [{value, text | textKey, lang?}]; onPick(value) - the menu closes, the checked item
// follows the pick
function iconMenu({ icon, label, items, current, onPick }) {
  const wrap = document.createElement("div");
  wrap.className = "menu";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button";
  button.innerHTML = svg(icon);
  button.dataset.i18nLabel = button.dataset.i18nTitle = label;
  button.setAttribute("aria-haspopup", "menu");
  button.setAttribute("aria-expanded", "false");
  const list = document.createElement("ul");
  list.className = "menu-list";
  list.setAttribute("role", "menu");
  list.dataset.i18nLabel = label;
  list.hidden = true;
  const entries = items.map((item) => {
    const li = document.createElement("li");
    li.setAttribute("role", "none");
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "menuitemradio");
    b.setAttribute("aria-checked", String(item.value === current));
    if (item.lang) b.lang = item.lang;
    b.innerHTML = svg("check");
    const text = document.createElement("span");
    if (item.textKey) text.dataset.i18n = item.textKey;
    else text.textContent = item.text;
    b.append(text);
    b.addEventListener("click", () => {
      for (const e of entries) e.setAttribute("aria-checked", String(e === b));
      close(true);
      onPick(item.value);
    });
    li.append(b);
    list.append(li);
    return b;
  });
  const open = () => {
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    (entries.find((e) => e.getAttribute("aria-checked") === "true") || entries[0]).focus();
  };
  const close = (refocus) => {
    if (list.hidden) return;
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    if (refocus) button.focus();
  };
  button.addEventListener("click", () => (list.hidden ? open() : close(false)));
  button.addEventListener("keydown", (e) => { if (e.key === "ArrowDown") { e.preventDefault(); open(); } });
  list.addEventListener("keydown", (e) => {
    const i = entries.indexOf(document.activeElement);
    const go = (j) => { e.preventDefault(); entries[(j + entries.length) % entries.length].focus(); };
    if (e.key === "ArrowDown") go(i + 1);
    else if (e.key === "ArrowUp") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(entries.length - 1);
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (e.key === "Tab") close(false);
  });
  document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) close(false); });
  wrap.append(button, list);
  return wrap;
}

// ---- theme (the tracker's own) ----

function initTheme() {
  const tools = document.querySelector(".top-tools");
  if (!tools) return;
  const current = document.documentElement.dataset.theme || "default";
  tools.append(iconMenu({
    icon: "theme", label: "ui.theme", current,
    items: THEMES.map(([value, text]) => ({ value, text })),
    onPick(id) {
      if (id === "default") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = id;
      try { localStorage.setItem(THEME_KEY, id); } catch { /* private mode: this visit only */ }
    },
  }));
}

// ---- code blocks: a copy button ----

function initCopy() {
  for (const pre of document.querySelectorAll(".code pre")) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy";
    button.dataset.i18n = "ui.copy";
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(pre.innerText.trimEnd());
        button.textContent = t("ui.copied");
        setTimeout(() => { button.textContent = t("ui.copy"); }, 1500);
      } catch { /* no clipboard (http, old browser): the text is still selectable */ }
    });
    pre.parentElement.append(button);
  }
}

// ---- headings: a "#" link to the section ----

function initAnchors() {
  for (const h of document.querySelectorAll("main h2[id], main h3[id]")) {
    const a = document.createElement("a");
    a.className = "anchor";
    a.href = "#" + h.id;
    a.textContent = "#";
    a.dataset.i18nLabel = "ui.link";
    h.append(a);
  }
}

// ---- search ----

// lower case, accents off ("Détails" -> "details"), one output char per input char where possible
const fold = (s) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

// A text folded with a map back to the original's positions (to cut and highlight the snippet in the original)
function foldMapped(text) {
  let folded = "";
  const at = [];
  for (let i = 0; i < text.length; i++) {
    const f = fold(text[i]);
    for (let j = 0; j < f.length; j++) { folded += f[j]; at.push(i); }
  }
  at.push(text.length);
  return { folded, at };
}

const SKIP = new Set(["SCRIPT", "STYLE", "NAV", "CANVAS", "SVG", "BUTTON", "NOSCRIPT"]);

// A heading's search keywords (data-search: a catalog key, never shown): the page's language's and the English
// ones (people type English words - "overlay", "stream" - in every language)
function keywords(key) {
  if (!key) return "";
  const here = t(key), en = CATALOG.en[key] ?? "";
  return here === key ? en : here === en ? here : here + " " + en;
}

// A page's sections: {url, id, page, title, text, keys}, split at its h1 / h2 / h3
function sections(doc, url) {
  const main = doc.querySelector("main");
  if (!main) return [];
  const h1 = main.querySelector("h1");
  const page = (h1?.getAttribute("aria-label") || h1?.textContent || doc.title).trim();
  const out = [];
  let cur = null;
  const start = (h) => {
    cur = { url, id: h.id || "", page, title: (h.getAttribute?.("aria-label") || h.textContent).replace(/#$/, "").trim(), text: "",
      keys: keywords(h.dataset?.search) };
    out.push(cur);
  };
  const walker = doc.createTreeWalker(main, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.nodeType === Node.TEXT_NODE) return NodeFilter.FILTER_ACCEPT;
      if (SKIP.has(node.nodeName.toUpperCase()) || node.classList.contains("anchor")) return NodeFilter.FILTER_REJECT;
      if (/^H[123]$/.test(node.nodeName)) { start(node); return NodeFilter.FILTER_REJECT; } // its text is the title
      return NodeFilter.FILTER_SKIP;
    },
  });
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!cur) start({ id: "", textContent: page });
    cur.text += n.nodeValue;
  }
  for (const s of out) {
    s.text = s.text.replace(/\s+/g, " ").trim();
    s.body = foldMapped(s.text);
    s.head = fold(s.title + " " + s.page + " " + s.keys);
  }
  return out;
}

let indexPromise = null; // (in the page's language: rebuilt after a switch)
document.addEventListener("i18n", () => { indexPromise = null; });
function buildIndex() {
  indexPromise ??= (async () => {
    const results = await Promise.all(PAGES.map(async ([file]) => {
      const url = new URL(file, document.baseURI).href;
      const res = await fetch(url);
      if (!res.ok) return [];
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      applyI18n(doc);
      return sections(doc, url);
    }));
    return results.flat();
  })();
  return indexPromise;
}

function count(hay, term) {
  let n = 0;
  for (let i = hay.indexOf(term); i !== -1; i = hay.indexOf(term, i + term.length)) n++;
  return n;
}

function search(index, query) {
  const terms = fold(query).split(/\s+/).filter((t) => t.length > 1 || /\d/.test(t));
  if (!terms.length) return [];
  const hits = [];
  for (const s of index) {
    let score = 0;
    let ok = true;
    for (const t of terms) {
      const inHead = count(s.head, t), inBody = count(s.body.folded, t);
      if (!inHead && !inBody) { ok = false; break; }
      score += inHead * 10 + Math.min(inBody, 8);
    }
    if (ok) hits.push({ s, score, terms });
  }
  return hits.sort((a, b) => b.score - a.score).slice(0, 8);
}

// The snippet: ~150 characters around the first term found, terms highlighted (DOM nodes: no HTML parsing)
function snippet(s, terms) {
  const el = document.createElement("span");
  el.className = "snippet";
  const { folded, at } = s.body;
  let first = -1;
  for (const t of terms) { const i = folded.indexOf(t); if (i !== -1 && (first === -1 || i < first)) first = i; }
  if (first === -1) { el.textContent = s.text.slice(0, 150) + (s.text.length > 150 ? "…" : ""); return el; }
  const from = Math.max(0, at[first] - 50), to = Math.min(s.text.length, from + 160);
  const ranges = [];
  for (const t of terms) {
    for (let i = folded.indexOf(t); i !== -1; i = folded.indexOf(t, i + t.length)) {
      const a = at[i], b = at[i + t.length];
      if (a >= from && b <= to) ranges.push([a, b]);
    }
  }
  ranges.sort((x, y) => x[0] - y[0]);
  let pos = from;
  if (from > 0) el.append("…");
  for (const [a, b] of ranges) {
    if (a < pos) continue;
    el.append(s.text.slice(pos, a));
    const mark = document.createElement("mark");
    mark.textContent = s.text.slice(a, b);
    el.append(mark);
    pos = b;
  }
  el.append(s.text.slice(pos, to) + (to < s.text.length ? "…" : ""));
  return el;
}

function initSearch() {
  const tools = document.querySelector(".top-tools");
  if (!tools) return;
  const box = document.createElement("div");
  box.className = "search";
  box.setAttribute("role", "search");
  const input = document.createElement("input");
  input.type = "search";
  input.dataset.i18nPlaceholder = "ui.placeholder";
  input.dataset.i18nLabel = "ui.search";
  input.setAttribute("aria-controls", "search-results");
  input.setAttribute("aria-expanded", "false");
  input.autocomplete = "off";
  const list = document.createElement("ul");
  list.id = "search-results";
  list.className = "search-results";
  list.setAttribute("role", "listbox");
  list.hidden = true;
  box.append(input, list);
  tools.prepend(box);
  // small screens: the box folded into a button, opening it over the bar's first row (site.css: .search-open)
  const top = document.querySelector(".top");
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "icon-button search-toggle";
  toggle.innerHTML = svg("search");
  toggle.dataset.i18nLabel = toggle.dataset.i18nTitle = "ui.search";
  toggle.setAttribute("aria-expanded", "false");
  box.after(toggle);
  const fold = (open) => {
    top?.classList.toggle("search-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    if (open) input.focus();
  };
  toggle.addEventListener("click", () => fold(true));

  let selected = -1;
  let timer = 0;
  const links = () => [...list.querySelectorAll("a")];
  const select = (i) => {
    const all = links();
    selected = all.length ? (i + all.length) % all.length : -1;
    all.forEach((a, j) => a.setAttribute("aria-selected", String(j === selected)));
    all[selected]?.scrollIntoView({ block: "nearest" });
  };
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); selected = -1; };
  const message = (text) => {
    list.replaceChildren();
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = text;
    list.append(li);
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  async function run() {
    const query = input.value.trim();
    if (!query) { close(); return; }
    let index;
    try {
      if (!indexPromise) message(t("ui.loading"));
      index = await buildIndex();
    } catch {
      indexPromise = null;
      message(t("ui.offline"));
      return;
    }
    if (input.value.trim() !== query) return; // typed on meanwhile
    const hits = search(index, query);
    if (!hits.length) { message(t("ui.none", { query })); return; }
    list.replaceChildren();
    for (const { s, terms } of hits) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = s.url.replace(/(?:index)?\.html$/, "") + (s.id ? "#" + s.id : ""); // (the links: no .html)
      a.setAttribute("role", "option");
      const title = document.createElement("span");
      title.className = "title";
      title.textContent = s.title;
      a.append(title);
      if (s.title !== s.page) {
        const where = document.createElement("span");
        where.className = "where";
        where.textContent = s.page;
        a.prepend(where);
      }
      a.append(snippet(s, terms));
      a.addEventListener("click", close);
      li.append(a);
      list.append(li);
    }
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    selected = -1;
  }

  input.addEventListener("focus", () => { buildIndex().catch(() => { indexPromise = null; }); }, { once: true });
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 120); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); select(selected + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); select(selected - 1); }
    else if (e.key === "Enter") {
      const target = links()[Math.max(selected, 0)];
      if (target) { e.preventDefault(); close(); location.href = target.href; }
    } else if (e.key === "Escape") { close(); input.blur(); fold(false); }
  });
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.nodeName) || document.activeElement?.isContentEditable;
    if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); input.focus(); }
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target) && !toggle.contains(e.target)) { close(); fold(false); } });
  document.addEventListener("i18n", close); // (its results: in the language before)
}

// ---- language: Auto (the browser's) or one of the catalogs, each named in its own language - the page
// re-translated in place (i18n.js setLanguage) ----

function initLanguage() {
  const tools = document.querySelector(".top-tools");
  if (!tools) return;
  tools.append(iconMenu({
    icon: "language", label: "ui.language", current: langPref,
    items: [{ value: "auto", textKey: "lang.auto" },
      ...Object.entries(CATALOG).map(([code, c]) => ({ value: code, text: c["lang.name"], lang: code }))],
    onPick: setLanguage,
  }));
}

// ---- the pages' links: in the bar (after the logo) and the footer, this one marked ----

function initPages() {
  const here = (location.pathname.split("/").pop() || "index").replace(/\.html$/, "");
  const list = (className) => {
    const ul = document.createElement("ul");
    if (className) ul.className = className;
    for (const [file, key] of PAGES) {
      if (!key) continue;
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = file.replace(/\.html$/, "");
      a.dataset.i18n = key;
      if (a.getAttribute("href") === here) a.setAttribute("aria-current", "page");
      li.append(a);
      ul.append(li);
    }
    return ul;
  };
  const brand = document.querySelector(".top .brand");
  if (brand) {
    const nav = document.createElement("nav");
    nav.className = "top-nav";
    nav.dataset.i18nLabel = "ui.pages";
    nav.append(list(""));
    brand.after(nav);
  }
  const foot = document.querySelector(".foot > div");
  if (foot) {
    const links = list("foot-links");
    const li = document.createElement("li");
    li.innerHTML = '<a href="https://github.com/ZooLSmith/helios-tracker" data-i18n="index.source"></a>';
    links.append(li);
    foot.append(links);
  }
}

// ---- the questionnaire (share.html): one step at a time, the answers' keys as the URL's path
// (?path=elsewhere/upto50/account) - Back / Forward walk it, a link reopens it, the language switch keeps it. The
// steps are the page's HTML, their words the catalogs' (the trail follows a language switch). ----

// The questionnaire's answer icons (12 x 12, currentColor), by answer key
const ANSWER_ICONS = {
    "pc": `<rect x="1.4" y="2" width="9.2" height="6.2" rx=".7" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 8.2v2.2M4.2 10.4h3.6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "home": `<path d="M1.6 6 6 2.2 10.4 6M2.9 5v5.2h6.2V5M5.1 10.2V7.6h1.8v2.6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "overlay": `<rect x="1.4" y="1.8" width="6.8" height="5" rx=".6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><rect x="3.8" y="5.2" width="6.8" height="5" rx=".6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" style="fill: currentColor; fill-opacity: .18"/>`,
    "stream": `<circle cx="6" cy="6" r="1.2" style="fill: currentColor"/><path d="M4 4a2.9 2.9 0 0 0 0 4M8 4a2.9 2.9 0 0 1 0 4M2.3 2.3a5.3 5.3 0 0 0 0 7.4M9.7 2.3a5.3 5.3 0 0 1 0 7.4" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "elsewhere": `<circle cx="6" cy="6" r="4.8" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><ellipse cx="6" cy="6" rx="2.1" ry="4.8" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M1.4 4.4h9.2M1.4 7.6h9.2" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "friends": `<circle cx="4.3" cy="4.1" r="1.6" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M1.4 10.2a2.9 2.9 0 0 1 5.8 0" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><circle cx="8.5" cy="4.6" r="1.3" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M7.9 7.5a2.4 2.4 0 0 1 2.9 2.7" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "anyone": `<path d="M5 7 7 5M4.4 5.4 3.1 6.7a1.7 1.7 0 0 0 2.4 2.4l1.3-1.3M7.6 6.6l1.3-1.3a1.7 1.7 0 0 0-2.4-2.4L5.2 4.2" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "upto50": `<path d="M1 8.6V3.4q0-.9.9-.9h7.6q1 0 1.4.9l.6 1.7v3.5Z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M2.4 4.2h1.7v1.6H2.4ZM5.2 4.2h1.7v1.6H5.2ZM8 4.2h1.5l.5 1.6H8Z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><circle cx="3.3" cy="8.9" r="1.05" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" style="fill: var(--card)"/><circle cx="8.6" cy="8.9" r="1.05" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" style="fill: var(--card)"/>`,
    "more": `<circle cx="6" cy="6" r="4.8" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><ellipse cx="6" cy="6" rx="2.1" ry="4.8" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M1.4 4.4h9.2M1.4 7.6h9.2" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`, // (the same globe as "People elsewhere")
    "domain": `<rect x="1.2" y="3.4" width="9.6" height="5.2" rx="1" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.1 6h.01M4.8 6h4.2" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "account": `<circle cx="6" cy="4" r="2" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/><path d="M2.5 10.5a3.5 3.5 0 0 1 7 0" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
    "no-account": `<path d="M6.8 1.2 2.6 6.9h3.2L5.2 10.8l4.2-5.7H6.2Z" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round"/>`,
};

function initQuiz() {
  const quiz = document.querySelector(".quiz");
  if (!quiz) return;
  const steps = new Map([...quiz.querySelectorAll(".step")].map((s) => [s.dataset.step, s]));
  const before = quiz.querySelector(".before");
  const start = "q:" + quiz.dataset.start;
  const trail = document.createElement("nav");
  trail.className = "trail";
  trail.dataset.i18nLabel = "share.soFar";
  quiz.prepend(trail);
  for (const s of steps.values()) s.querySelector("h2").tabIndex = -1;
  // each answer's icon, by its key (the cards: the same in every language)
  for (const a of quiz.querySelectorAll(".answers a[data-key]")) {
    const art = ANSWER_ICONS[a.dataset.key];
    if (art) a.insertAdjacentHTML("afterbegin", `<svg class="icon" viewBox="0 0 12 12" aria-hidden="true">${art}</svg>`);
  }

  const keysFromUrl = () => (new URLSearchParams(location.search).get("path") || "").split("/").filter(Boolean);
  const answer = (step, key) => steps.get(step)?.querySelector(`.answers a[data-key="${CSS.escape(key)}"]`);
  // the keys from the start: the answers taken (valid ones only) and the step they lead to
  function walk(keys) {
    let at = start;
    const taken = [];
    for (const key of keys) {
      const a = answer(at, key);
      if (!a || at.startsWith("r:")) break;
      taken.push({ key, label: a.textContent });
      at = a.dataset.next;
    }
    return { taken, at };
  }
  // the keys leading to a step (the tree has one way to each)
  function keysTo(target, at = start, keys = []) {
    if (at === target) return keys;
    if (!at.startsWith("q:")) return null;
    for (const a of steps.get(at)?.querySelectorAll(".answers a") || []) {
      const found = keysTo(target, a.dataset.next, [...keys, a.dataset.key]);
      if (found) return found;
    }
    return null;
  }
  const href = (keys, hash = "") => location.pathname + (keys.length ? "?path=" + keys.join("/") : "") + hash;

  // a link to a step, or to something inside one (a search result, #lan-firewall): its path, in the URL
  function fromHash() {
    const el = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null;
    const step = el?.closest(".quiz .step");
    if (!step) return false;
    const keys = keysTo(step.dataset.step);
    if (!keys) return false;
    history.replaceState(null, "", href(keys, el === step ? "" : location.hash));
    return true;
  }

  function render(focus, scroll = true) {
    const { taken, at } = walk(keysFromUrl());
    const step = steps.get(at) || steps.get(start);
    for (const s of steps.values()) s.classList.toggle("current", s === step);
    const internet = step.hasAttribute("data-internet");
    if (before) {
      before.classList.toggle("current", internet);
      if (internet) step.append(before);
    }
    // (an element for one answer only: data-when="<its key>")
    const keys = new Set(taken.map((t) => t.key));
    for (const el of quiz.querySelectorAll("[data-when]")) el.hidden = !keys.has(el.dataset.when);
    trail.replaceChildren();
    taken.forEach((t, i) => {
      const a = document.createElement("a");
      a.className = "chip";
      a.href = href(taken.slice(0, i).map((x) => x.key));
      a.textContent = t.label;
      a.addEventListener("click", (e) => { e.preventDefault(); go(taken.slice(0, i).map((x) => x.key)); });
      trail.append(a);
    });
    if (taken.length) {
      const again = document.createElement("a");
      again.className = "restart";
      again.href = href([]);
      again.textContent = t("share.restart");
      again.addEventListener("click", (e) => { e.preventDefault(); go([]); });
      trail.append(again);
    }
    trail.hidden = !taken.length;
    if (focus) step.querySelector("h2").focus();
    else if (scroll && location.hash) {
      const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
      if (target?.tagName === "DETAILS") target.open = true; // (a link to a folded extra: open it)
      target?.scrollIntoView();
    }
  }
  function go(keys) {
    history.pushState(null, "", href(keys));
    render(true);
  }

  quiz.addEventListener("click", (e) => {
    const a = e.target.closest(".answers a");
    if (!a) return;
    e.preventDefault();
    go([...walk(keysFromUrl()).taken.map((t) => t.key), a.dataset.key]);
  });
  addEventListener("popstate", () => render(false));
  document.addEventListener("i18n", () => render(false, false)); // (the trail: its answers' words)
  addEventListener("hashchange", () => { if (fromHash()) render(false); });
  if (!keysFromUrl().length) fromHash();
  render(false);
}

// ---- the link maker (share.html): a tunnel's address -> this site's /live/ link (the map opened from here: its
// settings kept whatever the tunnel's address) ----

function initLiveMaker() {
  const LOCAL = /^(localhost|127(\.\d+){3}|0\.0\.0\.0|10(\.\d+){3}|192\.168(\.\d+){2}|172\.(1[6-9]|2\d|3[01])(\.\d+){2}|\[?::1\]?)(:\d+)?$/i;
  document.querySelectorAll("[data-live-maker]").forEach((box, n) => {
    const input = box.querySelector("input"), out = box.querySelector(".live-out");
    const link = out.querySelector(".live-link"), copy = out.querySelector(".live-copy");
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(link.href);
        copy.textContent = t("ui.copied");
        setTimeout(() => { copy.textContent = t("ui.copy"); }, 1500);
      } catch { /* no clipboard: the link can still be selected */ }
    });
    const err = document.createElement("p");
    err.className = "live-err";
    err.id = `live-err-${n}`;
    err.setAttribute("role", "alert");
    err.hidden = true;
    input.closest("label").after(err);
    input.setAttribute("aria-describedby", err.id);
    let shown = ""; // (the message's key: said again in the new language after a switch)
    const show = (key) => {
      shown = key;
      err.textContent = key ? t(key) : "";
      err.hidden = !key;
      input.setAttribute("aria-invalid", String(!!key));
    };
    document.addEventListener("i18n", () => show(shown));
    input.addEventListener("input", () => {
      let text = input.value.trim();
      out.hidden = true;
      if (!text) { show(""); return; }
      const at = text.match(/[?&]at=([^&#\s]+)/); // a site link pasted back: its tunnel's address
      if (at) text = decodeURIComponent(at[1]);
      const host = text.replace(/^[a-z]+:\/\//i, "").replace(/[/?#].*$/, "");
      if (LOCAL.test(host)) { show("share.linkLocal"); return; }
      if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}(:\d{1,5})?$/i.test(host)) { show("share.linkBad"); return; }
      show("");
      link.href = link.textContent = `${location.origin}/live/?at=${host}`;
      out.hidden = false;
    });
  });
}

// ---- the overview's previews: the reel's screenshots twice in a row, the whole sliding left by one set and starting
// over (site.css .reel) - a seamless loop; its speed by how many there are. The copies: for the eye only ----

function initPreviews() {
  const reel = document.querySelector(".previews .reel");
  const shots = reel ? [...reel.querySelectorAll("figure")] : [];
  if (!shots.length) return;
  for (const f of shots) {
    const copy = f.cloneNode(true);
    copy.setAttribute("aria-hidden", "true");
    copy.querySelector("img")?.removeAttribute("data-i18n-alt");
    copy.querySelector("img")?.setAttribute("alt", "");
    reel.append(copy);
  }
  for (const a of reel.querySelectorAll("[aria-hidden] a")) a.tabIndex = -1; // (the copies: not twice in Tab's way)
  for (const el of reel.querySelectorAll("a, img")) el.draggable = false; // (the reel drags, not the link or image)
  initReelMotion(reel);
  // a click: the screenshot whole, in a dialog over the page (a click anywhere on it or around it, or Esc, closes it)
  const view = document.createElement("dialog");
  view.className = "shot-view";
  const img = document.createElement("img");
  view.append(img);
  document.body.append(view);
  view.addEventListener("click", () => view.close());
  reel.addEventListener("click", (e) => {
    const a = e.target.closest("a.shot");
    if (!a) return;
    e.preventDefault();
    const shot = a.querySelector("img");
    img.src = a.href;
    img.alt = shot.alt;
    view.classList.toggle("wide", shot.width > shot.height); // (a portrait phone turns a landscape one: site.css)
    view.showModal();
  });
}

// The reel's motion, every frame: a drift to the left (autoplay) and the pointer's drags, both eased - the reel's
// position (x) follows where it should be (target) by a lerp, the drift's speed eases towards what it should be
// (none under the pointer, while dragging or with reduced motion; AUTO otherwise), a flick's momentum fades out. One
// set's width wraps x (the copies after the set: the same picture). A drag past a few pixels is no click.
const REEL = { AUTO: 38, FOLLOW: 9, SPEED_EASE: 2.2, MOMENTUM_FADE: 3.2, FLICK_MAX: 2600, CLICK_SLOP: 6 }; // (px/s; per s)

function initReelMotion(reel) {
  const box = reel.parentElement;
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  let x = 0, target = 0, speed = 0, momentum = 0, period = 0;
  let over = false, drag = null, dragged = false, last = 0, frame = 0, visible = true;
  const measure = () => { period = (reel.scrollWidth + parseFloat(getComputedStyle(reel).columnGap || 0)) / 2; };
  measure();
  new ResizeObserver(measure).observe(reel);

  function tick(now) {
    const dt = Math.min(0.05, last ? (now - last) / 1000 : 0); // (a frame skipped: no jump)
    last = now;
    const want = over || drag || still.matches ? 0 : REEL.AUTO;
    speed += (want - speed) * (1 - Math.exp(-REEL.SPEED_EASE * dt));
    if (!drag) {
      target -= (speed + momentum) * dt;
      momentum *= Math.exp(-REEL.MOMENTUM_FADE * dt);
    }
    x += (target - x) * (1 - Math.exp(-REEL.FOLLOW * dt));
    if (period > 0) { // the loop: one set's width, both moved together (nothing seen jumps)
      const shift = x < -period ? period : x > 0 ? -period : 0;
      x += shift; target += shift;
      if (drag) drag.from += shift;
    }
    reel.style.transform = `translate3d(${x.toFixed(2)}px, 0, 0)`;
    frame = visible ? requestAnimationFrame(tick) : 0;
  }
  const run = () => { if (!frame) { last = 0; frame = requestAnimationFrame(tick); } };
  // off screen: no frames (back when it's seen again)
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) run(); }).observe(box);

  box.addEventListener("pointerenter", (e) => { if (e.pointerType === "mouse") over = true; });
  box.addEventListener("pointerleave", () => { over = false; });
  box.addEventListener("focusin", (e) => { if (e.target.matches(":focus-visible")) over = true; }); // (the keyboard's)
  box.addEventListener("focusout", () => { over = false; });
  box.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    drag = { id: e.pointerId, start: e.clientX, from: target, lastX: e.clientX, lastT: e.timeStamp, v: 0 };
    dragged = false;
    momentum = 0;
  });
  box.addEventListener("pointermove", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const dx = e.clientX - drag.start;
    if (!dragged && Math.abs(dx) > REEL.CLICK_SLOP) {
      dragged = true;
      box.setPointerCapture(e.pointerId);
      box.classList.add("dragging");
    }
    if (!dragged) return;
    target = drag.from + dx;
    const dt = (e.timeStamp - drag.lastT) / 1000;
    if (dt > 0) drag.v = drag.v * 0.6 + ((e.clientX - drag.lastX) / dt) * 0.4; // (the pointer's speed, smoothed)
    drag.lastX = e.clientX;
    drag.lastT = e.timeStamp;
  });
  const release = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (dragged && e.timeStamp - drag.lastT < 80) { // (a flick: thrown; held still first: not)
      momentum = Math.max(-REEL.FLICK_MAX, Math.min(REEL.FLICK_MAX, -drag.v));
    }
    drag = null;
    box.classList.remove("dragging");
  };
  box.addEventListener("pointerup", release);
  box.addEventListener("pointercancel", release);
  // a drag's own click (on release): not a click on the screenshot
  reel.addEventListener("click", (e) => { if (dragged) { e.preventDefault(); e.stopPropagation(); dragged = false; } }, true);
  run();
}

// ---- the scroller: focused on load, so the keyboard scrolls it (the page itself doesn't scroll) ----

function initScroller() {
  const page = document.querySelector(".page");
  if (page && (!document.activeElement || document.activeElement === document.body)) page.focus({ preventScroll: true });
}

initPages();
initPreviews();
initScroller();
initQuiz();
initLiveMaker();
initSearch();
initLanguage();
initTheme();
initCopy();
initAnchors();
applyI18n(); // (last: what the site built carries keys too)
