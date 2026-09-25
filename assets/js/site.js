// The site's extras, all at runtime (the pages work without them): search, theme, copy buttons, heading links.
// Search: the pages are the ones the navigation lists (.side a) - fetched and indexed by section on the first
// search, in the browser; nothing is generated beforehand.

import { LANGUAGES, remember, ui } from "./languages.js";

const LANG = document.documentElement.lang.toLowerCase().split("-")[0];
const STR = ui(LANG);
const THEMES = [["default", "ECHO-2"], ["hyperion", "Hyperion"], ["vladof", "Vladof"]];
const THEME_KEY = "helios.site.theme";

// ---- icon menus (language, theme): a button with an icon, a small list of choices under it ----

// The icons: 12 x 12 inline SVGs drawn with currentColor, like the tracker's (its js/icons.js)
const ICONS = {
  language: `<circle cx="6" cy="6" r="4.8" fill="none" stroke="currentColor" stroke-width="1.1"/>` +
    `<ellipse cx="6" cy="6" rx="2.1" ry="4.8" fill="none" stroke="currentColor" stroke-width="1.1"/>` +
    `<path d="M1.4 4.4h9.2M1.4 7.6h9.2" stroke="currentColor" stroke-width="1.1"/>`,
  theme: `<circle cx="6" cy="6" r="4.8" fill="none" stroke="currentColor" stroke-width="1.1"/>` +
    `<path d="M6 1.2a4.8 4.8 0 0 0 0 9.6Z" fill="currentColor"/>`,
  menu: `<path d="M1.8 3.2h8.4M1.8 6h8.4M1.8 8.8h8.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>`,
  check: `<path d="M2.4 6.4 4.9 8.9 9.7 3.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
};
const svg = (name) => `<svg class="icon" viewBox="0 0 12 12" aria-hidden="true">${ICONS[name]}</svg>`;

// items: [{value, text, lang?}]; onPick(value) - the menu closes, the checked item follows the pick
function iconMenu({ icon, label, items, current, onPick }) {
  const wrap = document.createElement("div");
  wrap.className = "menu";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button";
  button.innerHTML = svg(icon);
  button.setAttribute("aria-label", label);
  button.title = label;
  button.setAttribute("aria-haspopup", "menu");
  button.setAttribute("aria-expanded", "false");
  const list = document.createElement("ul");
  list.className = "menu-list";
  list.setAttribute("role", "menu");
  list.setAttribute("aria-label", label);
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
    b.append(item.text);
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

// ---- theme (the tracker's own three) ----

function initTheme() {
  const tools = document.querySelector(".top-tools");
  if (!tools) return;
  const current = document.documentElement.dataset.theme || "default";
  tools.append(iconMenu({
    icon: "theme", label: STR.theme, current,
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
    button.textContent = STR.copy;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(pre.innerText.trimEnd());
        button.textContent = STR.copied;
        setTimeout(() => { button.textContent = STR.copy; }, 1500);
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
    a.setAttribute("aria-label", STR.link);
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

// A page's sections: {url, id, page, title, text}, split at its h1 / h2 / h3
function sections(doc, url) {
  const main = doc.querySelector("main");
  if (!main) return [];
  const h1 = main.querySelector("h1");
  const page = (h1?.getAttribute("aria-label") || h1?.textContent || doc.title).trim();
  const out = [];
  let cur = null;
  const start = (h) => {
    cur = { url, id: h.id || "", page, title: (h.getAttribute?.("aria-label") || h.textContent).replace(/#$/, "").trim(), text: "" };
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
    s.head = fold(s.title + " " + s.page);
  }
  return out;
}

let indexPromise = null;
function buildIndex() {
  indexPromise ??= (async () => {
    const pages = [...new Set([...document.querySelectorAll(".side a[href]")].map((a) => a.href.split("#")[0]))];
    const results = await Promise.all(pages.map(async (url) => {
      const res = await fetch(url);
      if (!res.ok) return [];
      return sections(new DOMParser().parseFromString(await res.text(), "text/html"), url);
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
  if (!tools || !document.querySelector(".side a[href]")) return;
  const box = document.createElement("div");
  box.className = "search";
  box.setAttribute("role", "search");
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = STR.placeholder;
  input.setAttribute("aria-label", STR.search);
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
      if (!indexPromise) message(STR.loading);
      index = await buildIndex();
    } catch {
      indexPromise = null;
      message(STR.offline);
      return;
    }
    if (input.value.trim() !== query) return; // typed on meanwhile
    const hits = search(index, query);
    if (!hits.length) { message(`${STR.none} “${query}”`); return; }
    list.replaceChildren();
    for (const { s, terms } of hits) {
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = s.url + (s.id ? "#" + s.id : "");
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
    } else if (e.key === "Escape") { close(); input.blur(); }
  });
  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.nodeName) || document.activeElement?.isContentEditable;
    if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); input.focus(); }
  });
  document.addEventListener("click", (e) => { if (!box.contains(e.target)) close(); });
}

// ---- language: an icon menu of languages.js's list (the page's static link, to the site's language choice, is
// its no-JS fallback) - the same page in the picked language, else that language's home page ----

function initLanguage() {
  const link = document.querySelector("a.lang");
  const tools = document.querySelector(".top-tools");
  if (!tools) return;
  // this page's path inside its language's folder ("install.html", "dev/probes.html")
  const parts = location.pathname.split("/");
  const at = parts.lastIndexOf(LANG);
  if (at === -1) return;
  const root = parts.slice(0, at).join("/") + "/";
  const page = parts.slice(at + 1).join("/") || "index.html";
  const menu = iconMenu({
    icon: "language", label: STR.language, current: LANG,
    items: LANGUAGES.map((l) => ({ value: l.code, text: l.name, lang: l.code })),
    async onPick(code) {
      if (code === LANG) return;
      remember(code);
      let target = `${root}${code}/${page}`;
      try {
        const res = await fetch(target, { method: "HEAD" });
        if (!res.ok) target = `${root}${code}/`;
      } catch { /* offline check failed: try the page anyway */ }
      location.href = target + location.search + location.hash; // (?path=: the questionnaire's answers)
    },
  });
  if (link) link.replaceWith(menu);
  else tools.append(menu);
}

// ---- the questionnaire (share.html): one step at a time, the answers' keys as the URL's path
// (?path=elsewhere/upto50/account) - Back / Forward walk it, a link reopens it, the language switch keeps it. The
// steps are the page's HTML (each language's own text; without JS they read as a tree of links). ----

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
  trail.setAttribute("aria-label", quiz.dataset.soFar);
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

  function render(focus) {
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
      again.textContent = quiz.dataset.restart;
      again.addEventListener("click", (e) => { e.preventDefault(); go([]); });
      trail.append(again);
    }
    trail.hidden = !taken.length;
    if (focus) step.querySelector("h2").focus();
    else if (location.hash) {
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
    copy.textContent = STR.copy;
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(link.href);
        copy.textContent = STR.copied;
        setTimeout(() => { copy.textContent = STR.copy; }, 1500);
      } catch { /* no clipboard: the link can still be selected */ }
    });
    box.querySelector(".nojs").hidden = true;
    const err = document.createElement("p");
    err.className = "live-err";
    err.id = `live-err-${n}`;
    err.setAttribute("role", "alert");
    err.hidden = true;
    input.closest("label").after(err);
    input.setAttribute("aria-describedby", err.id);
    const show = (message) => {
      err.textContent = message || "";
      err.hidden = !message;
      input.setAttribute("aria-invalid", String(!!message));
    };
    input.addEventListener("input", () => {
      let text = input.value.trim();
      out.hidden = true;
      if (!text) { show(""); return; }
      const at = text.match(/[?&]at=([^&#\s]+)/); // a site link pasted back: its tunnel's address
      if (at) text = decodeURIComponent(at[1]);
      const host = text.replace(/^[a-z]+:\/\//i, "").replace(/[/?#].*$/, "");
      if (LOCAL.test(host)) { show(STR.linkLocal); return; }
      if (!/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}(:\d{1,5})?$/i.test(host)) { show(STR.linkBad); return; }
      show("");
      link.href = link.textContent = `${location.origin}/live/?at=${host}`;
      out.hidden = false;
    });
  });
}

// ---- small screens: the page menu (.side) as a drawer, opened by a button at the left of the top bar (CSS shows
// the button and makes .side a drawer only on small screens, only with JS: html.js) ----

function initNav() {
  const side = document.querySelector(".side");
  const top = document.querySelector(".top");
  if (!side || !top) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button nav-toggle";
  button.innerHTML = svg("menu");
  button.setAttribute("aria-label", STR.pages);
  button.title = STR.pages;
  button.setAttribute("aria-controls", side.id);
  button.setAttribute("aria-expanded", "false");
  const shade = document.createElement("div");
  shade.className = "nav-shade";
  side.tabIndex = -1;
  const set = (open, refocus) => {
    document.documentElement.classList.toggle("nav-open", open);
    button.setAttribute("aria-expanded", String(open));
    if (open) side.focus(); // (Tab then goes through its links)
    else if (refocus) button.focus();
  };
  button.addEventListener("click", () => set(!document.documentElement.classList.contains("nav-open"), false));
  shade.addEventListener("click", () => set(false, false));
  side.addEventListener("click", (e) => { if (e.target.closest("a")) set(false, false); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.documentElement.classList.contains("nav-open")) set(false, true);
  });
  top.prepend(button);
  document.body.append(shade);
}

// ---- the scroller: focused on load, so the keyboard scrolls it (the page itself doesn't scroll) ----

function initScroller() {
  const page = document.querySelector(".page");
  if (page && (!document.activeElement || document.activeElement === document.body)) page.focus({ preventScroll: true });
}

initScroller();
initNav();
initQuiz();
initLiveMaker();
initSearch();
initLanguage();
initTheme();
initCopy();
initAnchors();
