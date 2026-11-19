// The damage log in the drawer (the Info tab's Damage section's "All", as Mission's / Shops'), laid out as the mission
// log: on top its tabs, then the tab's own filters, then its list, scrolling alone. Three tabs, one job each
// (settings.ui.damageTab - design.md "The rework"):
// - Realtime: what's being done to the enemies now - a card each, its bar split by who (realtime.js);
// - Recap: who did what over a stretch - the enemies' bars and what they took, a tab per player (recap.js);
// - Log: every line, newest first - each hit (who -> whom, how much, what with, its element, crit, killing blow,
//   a heal...) and what happened outside a hit (an effect applied by a splash, one ended, a player bled out / back up,
//   a map change).
// Recap and Log share their filters: a search (search.js) and the time range (window.js - clock times; the user: one
// fight recapped, then its lines).
// Built once (the search keeps its focus: the players' updates redraw the drawer); its list and the range's handles
// drawn again from the frames (draw.js), throttled, the DOM written only when the text changed; Realtime's cards
// glide every frame.
import { $, esc } from "../dom.js";
import { num, t } from "../i18n.js";
import { saveSettings, settings } from "../settings.js";
import { S } from "../state.js";
import { saveDrawer } from "../ui/drawer.js";
import { tipSections } from "../ui/hovertip.js";
import { renderInspector } from "../ui/inspector.js";
import { queryHtml, showFold } from "../ui/listfold.js";
import { renderPlayers } from "../ui/players.js";
import { amountText, amountWidth, isShortened } from "./amount.js";
import { animateRealtime, buildRealtime, updateRealtime } from "./realtime.js";
import { bindRecap, recapHtml } from "./recap.js";
import { TAGS, actorHtml, actorName, clockText, defName, watchIcons, whatIcons } from "./parts.js";
import { eventMatches, hitMatches, searchWords } from "./search.js";
import { FLAG, damageStore } from "./store.js";
import { virtualList } from "./vlist.js";
import { bindRange, rangeHtml, refreshRange, windowSpan } from "./window.js";

const VIEWS = ["realtime", "recap", "log"];
const ROWS = 20000; // the log's lines at most (only those in view are drawn: vlist.js)
const EVERY_MS = 250;

let lastAt = -Infinity, builtKey = "", listShown = "", vlist = null;

export function openDamageLog() {
  S.damageView = { query: "", tab: "enemies", more: new Set() }; // (tab, more: the Recap's - recap.js)
  S.inspect = null;
  S.detail = null;
  S.missionView = null;
  S.shopView = null;
  $("inspector").classList.add("open");
  saveDrawer();
  renderPlayers();
  renderInspector(true);
}

const viewOf = () => (VIEWS.includes(settings.ui.damageTab) ? settings.ui.damageTab : "realtime");

export function renderDamageView(resetScroll) {
  const body = $("ibody"), store = damageStore, view = viewOf();
  $("itabs").style.display = "none";
  $("iwho").textContent = t("dmg.title");
  showQuery(); // (no "N hits kept" - the user: pointless)
  body.classList.add("mlistview"); // (the list scrolls alone, under the search and the views: the mission log's)
  const key = `${view}|${t("dmg.view.log")}`; // (built again for another view, another language)
  if (key !== builtKey || !$("dmList")) {
    builtKey = key;
    const tabs = `<div class="mtools"><span class="seg">` + VIEWS.map((v) =>
      `<button data-dmview="${v}" class="${v === view ? "on" : ""}">${esc(t("dmg.view." + v))}</button>`).join("") + `</span></div>`;
    const filters = view === "realtime" ? ""
      : `<input type="search" id="dmSearch" class="msearch" placeholder="${esc(t("dmg.search"))}"` +
        ` value="${esc(S.damageView.query || "")}">${rangeHtml()}`;
    body.innerHTML = `<div class="mfilters">${tabs}${filters}</div><div id="dmList" class="damage"></div>`;
    for (const b of body.querySelectorAll("[data-dmview]")) {
      b.onclick = () => { settings.ui.damageTab = b.dataset.dmview; saveSettings(); renderDamageView(true); };
    }
    if (view !== "realtime") {
      $("dmSearch").oninput = (e) => { S.damageView.query = e.target.value; showQuery(); drawList(true); };
      bindRange(body.querySelector("[data-dmrange]"), store, () => drawList(false));
    }
    listShown = "";
    watchIcons($("dmList"));
    vlist = view === "log" ? virtualList($("dmList")) : null;
    if (view === "recap") bindRecap($("dmList"), S.damageView, () => drawList(false));
    if (view === "realtime") buildRealtime($("dmList"));
  }
  showFold("damageFold", body.querySelector(".mfilters")); // (the views and filters folded away or not: listfold.js)
  drawList(resetScroll);
}

/** Under the title: the search while the filters are folded away (Realtime has none). */
const showQuery = () => {
  $("isub").innerHTML = viewOf() === "realtime" ? "" : queryHtml("damageFold", S.damageView.query || "");
};

/** The view's list as the window and the search are now. */
function drawList(resetScroll) {
  const list = $("dmList");
  if (!list) return;
  const store = damageStore;
  if (viewOf() === "realtime") { updateRealtime(store); return; }
  const [t1, t2] = windowSpan(store), words = searchWords(S.damageView.query || "");
  list.style.setProperty("--dmamt", amountWidth(store.maxHit)); // (as wide as the biggest hit yet: amount.js)
  if (vlist) {
    const items = logItems(store, ROWS, t1, t2, words);
    if (items.length) vlist.set(items.length, (i) => itemHtml(store, items[i]), resetScroll);
    else vlist.set(1, () => emptyHtml(store, words), resetScroll);
    return;
  }
  const html = recapHtml(store, t1, t2, words, S.damageView);
  if (html !== listShown) { listShown = html; list.innerHTML = html; }
  if (resetScroll) list.scrollTop = 0;
}

/** From draw.js' frame: the window's handles (live: it slides) and the list. */
export function refreshDamageView(now) {
  if (!S.damageView) return;
  animateRealtime(now); // (every frame: the cards' glide - the Refresh rate's)
  if (now - lastAt < EVERY_MS) return;
  lastAt = now;
  if (!$("dmList")) return;
  const range = document.querySelector("#ibody [data-dmrange]");
  if (range) refreshRange(range, damageStore); // (its times slide with the game: window.js)
  drawList(false);
}

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
    `<span class="dmamt${h.f & FLAG.HEAL ? " heal" : h.s && !h.h ? " shield" : ""}">${esc(amountText(h.h + h.s))}</span></div>`;
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
