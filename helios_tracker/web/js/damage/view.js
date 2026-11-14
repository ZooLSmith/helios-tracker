// The damage log in the drawer (the Info tab's Damage section's "All", as Mission's / Shops'), laid out as the mission
// log: on top the filters of the whole pane - a search (search.js), the time window (window.js: one for the page) -,
// then its views, then the view's list, scrolling alone. Two views (settings.ui.damageTab):
// - Overview: the actors in the window - what each dealt and took (one's own damage on oneself left out); step 4 adds
//   the timeline under the window's handles;
// - Log: every line, newest first - each hit (who -> whom, how much, what with, its element, crit, killing blow...)
//   and what happened outside a hit (an effect applied by a splash, one ended, a player bled out / back up, a map
//   change).
// Built once (the search keeps its focus: the players' updates redraw the drawer); its list and the window's handles
// drawn again from the frames (draw.js), throttled, the DOM written only when the text changed.
import { $, esc, nameHtml } from "../dom.js";
import { num, t } from "../i18n.js";
import { amountText, amountWidth, isShortened } from "./amount.js";
import { LAYERS, cardIconKey, prettyRaw } from "../model.js";
import { saveSettings, settings } from "../settings.js";
import { S } from "../state.js";
import { saveDrawer } from "../ui/drawer.js";
import { tipSections } from "../ui/hovertip.js";
import { renderInspector } from "../ui/inspector.js";
import { layerIcon } from "../ui/layers.js";
import { renderPlayers } from "../ui/players.js";
import { eventMatches, hitMatches, nameMatches, searchWords } from "./search.js";
import { FLAG, damageStore } from "./store.js";
import { virtualList } from "./vlist.js";
import { bindRange, rangeHtml, refreshRange, windowSpan } from "./window.js";

const VIEWS = ["overview", "log"];
const ROWS = 20000; // the log's lines at most (only those in view are drawn: vlist.js)
const ACTORS = 100; // the overview's actors at most
const EVERY_MS = 250;

let lastAt = -Infinity, builtKey = "", listShown = "", vlist = null;

export function openDamageLog() {
  S.damageView = { query: "" };
  S.inspect = null;
  S.detail = null;
  S.missionView = null;
  S.shopView = null;
  $("inspector").classList.add("open");
  saveDrawer();
  renderPlayers();
  renderInspector(true);
}

const viewOf = () => (VIEWS.includes(settings.ui.damageTab) ? settings.ui.damageTab : "overview");

export function renderDamageView(resetScroll) {
  const body = $("ibody"), store = damageStore, view = viewOf();
  $("itabs").style.display = "none";
  $("iwho").textContent = t("dmg.title");
  $("isub").textContent = store.count ? t("dmg.kept", { n: store.count }) : "";
  body.classList.add("mlistview"); // (the list scrolls alone, under the search and the views: the mission log's)
  const key = `${view}|${t("dmg.view.log")}`; // (built again for another view, another language)
  if (key !== builtKey || !$("dmList")) {
    builtKey = key;
    body.innerHTML = `<div class="mfilters"><input type="search" id="dmSearch" class="msearch" placeholder="${esc(t("dmg.search"))}"` +
      ` value="${esc(S.damageView.query || "")}">${rangeHtml()}<div class="mtools"><span class="seg">` + VIEWS.map((v) =>
      `<button data-dmview="${v}" class="${v === view ? "on" : ""}">${esc(t("dmg.view." + v))}</button>`).join("") +
      `</span></div></div><div id="dmList" class="damage"></div>`;
    for (const b of body.querySelectorAll("[data-dmview]")) {
      b.onclick = () => { settings.ui.damageTab = b.dataset.dmview; saveSettings(); renderDamageView(true); };
    }
    $("dmSearch").oninput = (e) => { S.damageView.query = e.target.value; drawList(true); };
    bindRange(body.querySelector("[data-dmrange]"), store, () => drawList(false));
    listShown = "";
    watchIcons($("dmList"));
    vlist = view === "log" ? virtualList($("dmList")) : null;
  }
  drawList(resetScroll);
}

/** The view's list as the window and the search are now. */
function drawList(resetScroll) {
  const list = $("dmList");
  if (!list) return;
  const store = damageStore, [t1, t2] = windowSpan(store), words = searchWords(S.damageView.query || "");
  list.style.setProperty("--dmamt", amountWidth(store.maxHit)); // (as wide as the biggest hit yet: amount.js)
  if (vlist) {
    const items = logItems(store, ROWS, t1, t2, words);
    if (items.length) vlist.set(items.length, (i) => itemHtml(store, items[i]), resetScroll);
    else vlist.set(1, () => emptyHtml(store, words), resetScroll);
    return;
  }
  const html = actorsHtml(store, t1, t2, words);
  if (html !== listShown) { listShown = html; list.innerHTML = html; }
  if (resetScroll) list.scrollTop = 0;
}

/** From draw.js' frame: the window's handles (live: it slides) and the list. */
export function refreshDamageView(now) {
  if (!S.damageView || now - lastAt < EVERY_MS) return;
  lastAt = now;
  const range = document.querySelector("#ibody [data-dmrange]");
  if (!range) return;
  if (!range.dataset.held) refreshRange(range, damageStore); // (not under a dragged handle: window.js)
  const sub = damageStore.count ? t("dmg.kept", { n: damageStore.count }) : "";
  if ($("isub").textContent !== sub) $("isub").textContent = sub;
  drawList(false);
}

/** The overview: the actors in the window - what each dealt and took (not on themselves), the most first. */
export function actorsHtml(store, t1, t2, words = []) {
  const totals = new Map(); // id -> [dealt, taken]
  const add = (id, side, amount) => {
    if (!id) return;
    let v = totals.get(id);
    if (!v) totals.set(id, v = [0, 0]);
    v[side] += amount;
  };
  store.forEachHit(t1, t2, (h) => {
    if (h.a === h.v) return;
    add(h.a, 0, h.h + h.s);
    add(h.v, 1, h.h + h.s);
  });
  const rows = [...totals].filter(([id]) => nameMatches(words, store.actors.get(id)))
    .sort((a, b) => b[1][0] + b[1][1] - (a[1][0] + a[1][1])).slice(0, ACTORS);
  if (!rows.length) return `<div class="note">${esc(t(totals.size ? "dmg.noMatch" : "dmg.quietWindow"))}</div>`;
  return `<div class="dmactor dmhead"><span></span><span>${esc(t("dmg.dealt"))}</span><span>${esc(t("dmg.taken"))}</span></div>` +
    rows.map(([id, [dealt, taken]]) => `<div class="dmactor"><span class="dmwho">${actorHtml(store, id)}</span>` +
      `<span class="dmamt">${dealt ? esc(amountText(dealt)) : ""}</span>` +
      `<span class="dmamt taken">${taken ? esc(amountText(taken)) : ""}</span></div>`).join("");
}

// An actor's map layer (its marker beside its name): a pawn's by its kind; an object's by its category - the map's own
// (data.js onObjects: objectCategory), read off its record while it's on the map, kept once seen (a barrel blown up
// leaves the map); not seen there: the plain "other" one
const PAWN_LAYERS = { me: "player", player: "player", enemy: "enemy", npc: "npc", vehicle: "vehicle" };

function actorLayer(def) {
  if (def.k === "object" && !def.cat && def.m) {
    const o = S.objects.find((x) => x.i === def.m);
    if (o) { def.cat = o.cat; if (o.ecol) def.ecol = o.ecol; }
  }
  const id = PAWN_LAYERS[def.k] || (def.k === "object" ? def.cat || "other" : null);
  const layer = id && LAYERS.find((l) => l.id === id);
  if (!layer) return null;
  // (what explodes: in its element's colour, as on the map - draw.js)
  return id === "explosive" && def.ecol ? { ...layer, color: def.ecol } : layer;
}

export const actorHtml = (store, id) => {
  const def = store.actors.get(id);
  if (!def) return `<span class="dma">?</span>`;
  const layer = actorLayer(def);
  return `<span class="dma ${esc(def.k || "")}">${layer ? `<span class="sw">${layerIcon(layer)}</span>` : ""}${nameHtml(def)}</span>`;
};

const defName = (def) => (def ? (def.raw ? prettyRaw(def.n) : def.n || "") : "");

const clockText = (store, ms) => new Date(store.t0 + ms).toLocaleTimeString(globalThis.document?.documentElement.lang || undefined,
  { hour: "2-digit", minute: "2-digit", second: "2-digit" });


// An item card icon (the game's art, /cardicon/: items.js's) - only when the game's card art is served; one the game
// hasn't (a 404 - each one stalls the page a few ms, the user saw it, and the log's lines are drawn again and again)
// kept in failedIcons: never asked for again, its fallback drawn instead (an element's: its colour's dot)
const failedIcons = new Set();
const iconUrl = (kind, key) => `/cardicon/${kind}/${encodeURIComponent(key)}.png`;
const iconOk = (kind, key) => !!(S.assets?.cards && cardIconKey(key) && !failedIcons.has(iconUrl(kind, key)));
const dotHtml = (colour) => (/^#[0-9a-f]{6}$/i.test(colour || "") ? `<span class="dmel" style="background:${colour}"></span>` : "");
const cardImg = (kind, key) => `<img class="dmi ${kind}" src="${iconUrl(kind, key)}" alt="" draggable="false">`;

/** Records the list's icons that failed to load (their error, caught on the way down: it doesn't bubble). */
function watchIcons(list) {
  list.addEventListener("error", (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    failedIcons.add(img.getAttribute("src"));
    img.remove(); // (this time: the next drawing draws the fallback)
  }, true);
}

/** What dealt it, as icons (the user: no names in the line - its tooltip has them): a weapon's type icon (its item
 *  card's), the element's; nothing for what has no type (a melee, an explosion, a fire left on the ground - the user:
 *  no "?"). */
function whatIcons(store, w, e) {
  const def = store.whats.get(w), el = store.elements.get(e);
  const type = def && iconOk("type", def.wt) ? cardImg("type", def.wt) : "";
  const elem = el ? (iconOk("element", el.el) ? cardImg("element", el.el) : dotHtml(el.ecol)) : "";
  return type || elem ? `<span class="dmwhat">${type}${elem}</span>` : "";
}

const TAGS = [[FLAG.KILL, "dmg.kill", "kill"], [FLAG.CRIT, "dmg.crit", "crit"], [FLAG.DOWNED, "dmg.downed", "down"],
  [FLAG.WIND, "dmg.wind", "wind"], [FLAG.EFFECT, "dmg.effect", "fx"], [FLAG.TICK, "dmg.tick", "tick"]];

const actorName = (store, id) => defName(store.actors.get(id)) || "?";

/** A hit's line: who -> whom, its tags, what with (icons), the amount; the details in its tooltip (the page's own -
 *  hovertip.js: what with, who -> whom, when; the element, health / shield). */
function hitHtml(store, h) {
  const el = store.elements.get(h.e);
  const tags = TAGS.filter(([bit]) => h.f & bit).map(([, key, cls]) => `<span class="dmtag ${cls}">${esc(t(key))}</span>`).join("") +
    (h.f & FLAG.FOLDED ? `<span class="dmtag">×${num(h.c)}</span>` : "");
  const tip = tipSections(defName(store.whats.get(h.w)) || actorName(store, h.a), [
    { kind: "meta", lines: [`${actorName(store, h.a)} → ${actorName(store, h.v)}`, clockText(store, h.t)] },
    { kind: "stats", lines: [isShortened(h.h + h.s) ? num(Math.round(h.h + h.s)) : "", el?.eln || "",
      h.h && h.s ? t("dmg.split", { h: num(Math.round(h.h)), s: num(Math.round(h.s)) }) : h.s ? t("dmg.shield") : ""] },
  ]);
  return `<div class="dmrow${h.f & FLAG.KILL ? " kill" : ""}"${tip}>` +
    `<span class="dmwho">${actorHtml(store, h.a)}<span class="dmarrow">→</span>${actorHtml(store, h.v)}</span>` +
    `<span class="dmtags">${tags}</span>${whatIcons(store, h.w, h.e) || "<span></span>"}` +
    `<span class="dmamt${h.s && !h.h ? " shield" : ""}">${esc(amountText(h.h + h.s))}</span></div>`;
}

const EVENT_KEYS = { "fx+": "dmg.fxOn", "fx-": "dmg.fxOff", down: "dmg.downed", wind: "dmg.wind", dead: "dmg.bledOut",
  died: "dmg.died", level: "dmg.level" };

const eventKey = (e) => (e.kind === "up" ? (e.rest[0] === "respawn" ? "dmg.respawned" : "dmg.revived") : EVENT_KEYS[e.kind] || e.kind);

/** What happened outside a hit: who (<- by whom), what it was; an effect's name in its tooltip. */
function eventHtml(store, e) {
  let who = e.kind === "level" ? `<span class="nm">${esc(e.rest[0] || "")}</span>` : actorHtml(store, e.actor);
  if (e.other) who += `<span class="dmarrow">←</span>${actorHtml(store, e.other)}`;
  const fx = e.kind === "fx+" || e.kind === "fx-";
  const tip = tipSections(t(eventKey(e)), [
    { kind: "meta", lines: [fx ? defName(store.whats.get(e.rest[1])) : "", clockText(store, e.t)] },
  ]);
  return `<div class="dmrow ev ${esc(e.kind.replace(/\W/g, ""))}"${tip}><span class="dmwho">${who}</span>` +
    `<span class="dmtags"><span class="dmtag">${esc(t(eventKey(e)))}</span></span><span></span><span class="dmamt"></span></div>`;
}

/** The latest `rows` lines in the window matching the search, newest first: the hits and the events outside a hit (one
 *  inside a hit is its tag), a time heading each time the second changes (the user: no time column) - as items
 *  ({head} | {hit} | {event}: drawn by itemHtml, only those in view - vlist.js). */
export function logItems(store, rows, t1 = -Infinity, t2 = Infinity, words = []) {
  const hits = [];
  store.eachHitBack(t1, t2, (h) => {
    if (hitMatches(words, store, h)) hits.push(h);
    return hits.length < rows;
  });
  const events = [];
  for (let i = store.events.length - 1; i >= 0 && events.length < rows; i--) {
    const e = store.events[i];
    if (e.t > t2) continue;
    if (e.t < t1) break;
    if (e.hit < 0 && eventMatches(words, store, e, t(eventKey(e)))) events.push(e);
  }
  const items = [];
  let a = 0, b = 0, n = 0, heading = "";
  while (n < rows && (a < hits.length || b < events.length)) {
    const isHit = b >= events.length || (a < hits.length && hits[a].t >= events[b].t);
    const item = isHit ? hits[a++] : events[b++];
    const when = clockText(store, item.t);
    if (when !== heading) { heading = when; items.push({ head: when }); }
    items.push(isHit ? { hit: item } : { event: item });
    n++;
  }
  return items;
}

/** A log item's HTML (logItems'). */
export const itemHtml = (store, item) => (item.head != null ? `<div class="dmtime">${esc(item.head)}</div>`
  : item.hit ? hitHtml(store, item.hit) : eventHtml(store, item.event));

const emptyHtml = (store, words) =>
  `<div class="note">${esc(t(words.length ? "dmg.noMatch" : store.count ? "dmg.quietWindow" : "dmg.none"))}</div>`;

/** The log's lines as one HTML (every one: the tests'). */
export function linesHtml(store, rows, t1 = -Infinity, t2 = Infinity, words = []) {
  return logItems(store, rows, t1, t2, words).map((item) => itemHtml(store, item)).join("") || emptyHtml(store, words);
}
