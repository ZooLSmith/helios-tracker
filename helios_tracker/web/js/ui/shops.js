// The Shops pane: the Info tab's section (its heading: the restock countdown with a timer icon, "All"; its body: the
// NEAR_COUNT closest machines, their item of the day) and the drawer -
// the level's vending machines, a tab per kind (named by the vending menu's own titles: "Marcus Munitions"...), each
// tab: each machine, the closest to the tracked player first, with its item of the day and its stock at the machine's
// prices, then what every machine of that kind always sells (ammo, health vials: a price list) (shops.py; the items'
// cards: items.js).
import { $, esc, nameHtml } from "../dom.js";
import { UU_PER_METER } from "../geo.js";
import { money, num, t } from "../i18n.js";
import { icon } from "../icons.js";
import { saveSettings, settings } from "../settings.js";
import { rarity } from "../model.js";
import { S, isTrackedPlayer, trackedPawn } from "../state.js";
import { saveDrawer } from "./drawer.js";
import { bindItems, renderInspector } from "./inspector.js";
import { itemHtml } from "./items.js";
import { renderPlayers } from "./players.js";

const KIND_ORDER = ["weapons", "items", "health", "other"]; // (no black market: shops.py leaves it out)
// each kind's tab in a skill tree's colours (drawer.css .stabs .treeN, the user's call): weapons red, ammo /
// grenades green, shields / health blue
const KIND_TREE = { weapons: "tree2", items: "tree0", health: "tree1" };
const NEAR_COUNT = 2; // the Info tab's Shops section: the closest machines listed

/** Seconds until the shops restock: the game's last figure counted down since - held while the game is paused (its
 *  timer stands still) - or null: not known yet. */
export function restockLeft() {
  const tm = S.shopTimer;
  if (!tm) return null;
  return tm.paused ? tm.left : Math.max(0, tm.left - ((performance.now() - tm.at) / 1000) * tm.rate);
}

function clock(s) {
  const whole = Math.ceil(s);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function timerText() {
  const s = restockLeft();
  return s == null ? "" : s > 0 ? t("shops.restockIn", { t: clock(s) }) : t("shops.restocking");
}

/** The countdowns shown - "Restock in 12:34" (the drawer's) and the bare "12:34" (the Info heading's, by its timer
 *  icon) - their text again (the DOM only touched when it changed). */
function tickTimers() {
  const s = restockLeft();
  for (const [sel, text] of [["[data-shop-timer]", timerText()], ["[data-shop-clock]", s == null ? "" : clock(s)]]) {
    for (const el of document.querySelectorAll(sel)) if (el.textContent !== text) el.textContent = text;
  }
}

const machines = () => (S.shops ? S.shops.machines : []);
const kindsHere = () => KIND_ORDER.filter((k) => machines().some((m) => m.k === k));

/** Opens the list: on a machine's tab, that machine first (id), else the last tab looked at. */
export function openShops(id = null) {
  const m = id ? machines().find((x) => x.i === id) : null;
  S.shopView = { id: m ? m.i : null };
  if (m) { settings.ui.shopTab = m.k; saveSettings(); }
  S.inspect = null;
  S.detail = null;
  S.missionView = null;
  $("inspector").classList.add("open");
  saveDrawer();
  renderPlayers();
  renderInspector(true);
}

const distance = (m, me) => (me ? Math.hypot(m.x - me.x, m.y - me.y, m.z - me.z) : 0);

/** The Info section's body: the NEAR_COUNT machines closest to the tracked player - a row each (its name, its
 *  distance; its item of the day, in its rarity's colour), a click opens the list on it. */
function nearHtml() {
  const list = [...machines()];
  if (!list.length) return `<div class="muted">${esc(t(S.shops ? "shops.none" : "shops.waiting"))}</div>`;
  const me = trackedPawn();
  if (me) list.sort((a, b) => distance(a, me) - distance(b, me));
  return list.slice(0, NEAR_COUNT).map((m) => {
    const dist = me ? `<span class="shnd">${esc(t("unit.meters", { n: num(distance(m, me) / UU_PER_METER, 0) }))}</span>` : "";
    const feat = m.feat ? `<div class="shnf" style="color:${rarity(m.feat.q || 0)[1]}">${icon("star")}<span>${nameHtml(m.feat)}</span></div>` : "";
    return `<div class="shnear" data-open-shop="${esc(m.i)}"><div class="shnh"><span class="shnn">${nameHtml(m)}</span>${dist}</div>${feat}</div>`;
  }).join("");
}

let nearShown = "";
function renderNear() {
  const html = nearHtml();
  if (html !== nearShown) { nearShown = html; $("shops").innerHTML = html; }
}

/** The Info tab's Shops section: its heading's countdown and "All", the closest machines. */
export function renderShops() {
  $("shopsAll").hidden = !machines().length;
  $("shopsTimer").hidden = !S.shopTimer;
  renderNear();
  tickTimers();
}
const priceText = (v, cur) => (cur ? t("currency." + cur, { n: num(v) }) : money(v));

/** What every machine of a kind always sells (ammo, health vials): the closest one's names and prices, one list. */
function basicsHtml(list) {
  const from = list.find((m) => m.basics && m.basics.length);
  if (!from) return "";
  return `<div class="group">${esc(t("shops.always"))}</div><div class="shbasics">` + from.basics.map((b) =>
    `<div class="shb"><span class="shbn">${nameHtml(b)}</span>${b.v != null ? `<span class="shbv">${esc(priceText(b.v, from.cur))}</span>` : ""}</div>`)
    .join("") + `</div>`;
}

/** A machine's item of the day then its stock (the item cards: bindItems after), or a note when it has none. */
function stockHtml(m, level) {
  const items = m.cur ? m.items.map((it) => ({ ...it, cur: m.cur })) : m.items; // (the price's currency: items.js)
  const feat = m.feat && (m.cur ? { ...m.feat, cur: m.cur } : m.feat);
  let html = "";
  if (feat) html += `<div class="group shfeat">${icon("star")} ${esc(t("shops.featured"))}</div>` + itemHtml(feat, level);
  if (items.length) html += `<div class="group">${esc(t("shops.stock"))} · ${num(items.length)}</div>` + items.map((it) => itemHtml(it, level)).join("");
  else if (!feat && !(m.basics && m.basics.length)) {
    html += `<div class="note">${esc(t(S.shops.client ? "shops.clientEmpty" : "shops.empty"))}</div>`;
  }
  return html;
}

const playerLevel = () => (S.players.find(isTrackedPlayer) || {}).lvl || 0; // (items above it: marked, like a backpack's)

/** A machine's panel (detail.js: a vending machine clicked on the map) - what it sells, as in the list: its item of
 *  the day, its stock, then its price list; "" if it isn't one of the listed machines. Its items' cards: bindItems. */
export function machineStockHtml(id) {
  const m = machines().find((x) => x.i === id);
  return m ? stockHtml(m, playerLevel()) + basicsHtml([m]) : "";
}

function machineHtml(m, me, level) {
  const dist = me ? `<span class="shdist">${esc(t("unit.meters", { n: num(distance(m, me) / UU_PER_METER, 0) }))}</span>` : "";
  return `<div class="shmachine" data-machine="${esc(m.i)}"><div class="shhead">` +
    `<a class="mlink" data-open-detail="${esc(m.i)}" data-kind="vendor" title="${esc(t("shops.onMap"))}">${nameHtml(m)}</a>${dist}</div>` +
    stockHtml(m, level) + `</div>`;
}

/** The drawer's list: a tab per kind of machine, the chosen kind's machines. */
export function renderShopsView(resetScroll) {
  const body = $("ibody"), scroll = body.scrollTop;
  $("itabs").style.display = "none";
  $("iwho").textContent = t("shops.title");
  $("isub").innerHTML = `<span data-shop-timer>${esc(timerText())}</span>`;
  const kinds = kindsHere();
  if (!kinds.length) {
    body.innerHTML = `<div class="note">${esc(t(S.shops ? "shops.none" : "shops.waiting"))}</div>`;
    return;
  }
  const tab = kinds.includes(settings.ui.shopTab) ? settings.ui.shopTab : kinds[0];
  const me = trackedPawn();
  const byKind = (k) => {
    const list = machines().filter((m) => m.k === k);
    if (me) list.sort((a, b) => distance(a, me) - distance(b, me));
    return list;
  };
  // (a tab: the kind's name - its closest machine's, the game's title - and how many machines)
  const tabs = `<div class="stabs">` + kinds.map((k) => {
    const list = byKind(k);
    return `<button class="${[KIND_TREE[k], k === tab ? "on" : ""].filter(Boolean).join(" ")}" data-shop-tab="${k}"><span class="nm">${nameHtml(list[0])}</span>` +
      (list.length > 1 ? `<span class="shtc">${num(list.length)}</span>` : "") + `</button>`;
  }).join("") + `</div>`;
  const list = byKind(tab);
  const level = playerLevel();
  // (what they always sell after the machines: the stock is what changes - the user's call)
  body.innerHTML = tabs + list.map((m) => machineHtml(m, me, level)).join("") + basicsHtml(list);
  bindItems(body);
  const first = resetScroll && S.shopView.id ? body.querySelector(`[data-machine="${CSS.escape(S.shopView.id)}"]`) : null;
  if (first) first.scrollIntoView({ block: "start" });
  else body.scrollTop = resetScroll ? 0 : scroll;
}

export function initShops() {
  $("shopsAll").addEventListener("click", () => openShops());
  $("shops").addEventListener("click", (e) => { // a nearby machine: the list, on it
    const row = e.target instanceof Element ? e.target.closest("[data-open-shop]") : null;
    if (row) openShops(row.dataset.openShop);
  });
  $("inspector").addEventListener("click", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-open-shop], [data-shop-tab], [data-detail-back]") : null;
    if (!el) return;
    if (el.dataset.detailBack != null) { openShops(S.detail && S.detail.back ? S.detail.back.id : null); return; } // (detail.js)
    if (el.dataset.openShop) { openShops(el.dataset.openShop); return; } // a machine's panel (detail.js): its stock
    settings.ui.shopTab = el.dataset.shopTab;
    saveSettings();
    S.shopView.id = null;
    renderShopsView(true);
  });
  renderShops();
}

let nextTick = 0;
/** From the frames (draw.js): the countdowns and the closest machines (the player moves) follow the Refresh rate
 *  setting - only on frames the page draws (with "Updates only": the game's updates), at most every 250 ms. */
export function refreshShops(now) {
  if (!S.shops || now < nextTick) return;
  nextTick = now + 250;
  tickTimers();
  renderNear();
}
