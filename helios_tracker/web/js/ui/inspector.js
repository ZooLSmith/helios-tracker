// The right drawer: a player's Gear / Backpack / Skills (or a clicked object: detail.js, the
// mission log: missionlog.js, the vending machines: shops.js).
import { $, esc } from "../dom.js";
import { num, t } from "../i18n.js";
import { nameText } from "../model.js";
import { invalidate } from "../scheduler.js";
import { saveSettings, settings } from "../settings.js";
import { S, findPlayer } from "../state.js";
import { renderDetail } from "./detail.js";
import { saveDrawer } from "./drawer.js";
import { renderTargets } from "./panel.js";
import { elementIconLoaded, itemsByKind } from "./items.js";
import { renderMissionLog } from "./missionlog.js";
import { renderShopsView } from "./shops.js";
import { alignPatterns, playerSub, renderPlayers } from "./players.js";
import { playerInfoHtml } from "./playerinfo.js";
import { skillsHtml } from "./skills.js";

export function openInspector(id) {
  const p = S.players.find((q) => q.i === id);
  if (!p) return;
  S.inspect = { id: p.i, name: p.n };
  S.detail = null;
  S.missionView = null;
  S.shopView = null;
  S.skillTab = null; // back to their tree with the most points
  $("inspector").classList.add("open");
  saveDrawer();
  renderPlayers();
  renderInspector(true);
}

export function closeInspector() {
  S.inspect = null;
  S.detail = null;
  S.missionView = null;
  S.shopView = null;
  $("inspector").classList.remove("open");
  saveDrawer();
  renderPlayers();
}

export function renderInspector(resetScroll) {
  const box = $("inspector");
  if (!S.missionView) { // (the mission list's layout - its own scroll - and its filters' chevron)
    $("ibody").classList.remove("mlistview");
    $("ifold").hidden = true;
  }
  if (S.missionView) { renderMissionLog(resetScroll); return; }
  if (S.shopView) { renderShopsView(resetScroll); return; }
  if (S.detail) { renderDetail(resetScroll); return; }
  $("itabs").style.display = "";
  if (!S.inspect) { box.classList.remove("open"); return; }
  const body = $("ibody");
  const scroll = body.scrollTop;
  const p = findPlayer();
  for (const b of $("itabs").querySelectorAll("button")) b.classList.toggle("on", b.dataset.tab === settings.ui.inspectorTab);
  if (!p) {
    $("iwho").textContent = S.inspect.name;
    $("isub").textContent = "";
    body.innerHTML = `<div class="note">${esc(t("insp.gone"))}</div>`;
    return;
  }
  $("iwho").textContent = p.host ? t("who.host", { name: nameText(p) }) : nameText(p);
  $("isub").textContent = playerSub(p);
  let html = "";
  const tab = settings.ui.inspectorTab;
  if (tab === "info") {
    html = playerInfoHtml(p);
  } else if (tab === "gear") {
    if (p.inventory === "partial") {
      html += `<div class="note">${esc(t("why.inventory." + (p.inventoryWhy || "unavailable")))} ${esc(t("insp.heldOnly"))}</div>`;
    }
    html += (p.equipped || []).length ? itemsByKind(p.equipped, p.lvl) : `<div class="muted">${esc(t("insp.nothing"))}</div>`;
  } else if (tab === "backpack") {
    if (p.inventory !== "full") html = `<div class="note">${esc(t("why.inventory." + (p.inventoryWhy || "unavailable")))}</div>`;
    else if (p.backpackWhy) {
      html = (p.slots ? `<div class="muted">${esc(t("insp.slots", { n: num(p.slots[0]), max: num(p.slots[1]) }))}</div>` : "") +
        `<div class="note">${esc(t("why.backpack." + p.backpackWhy))}</div>`;
    }
    else html = `<div class="muted">${esc(p.slots ? t("insp.slots", { n: num(p.slots[0]), max: num(p.slots[1]) })
      : t("insp.items", { n: p.backpack.length }))}</div>` +
      (p.backpack.length ? itemsByKind(p.backpack, p.lvl) : "");
  } else {
    html = skillsHtml(p);
  }
  body.innerHTML = html;
  alignPatterns(body); // (rebuilt bars: their patterns carry on, not start over)
  body.dataset.info = tab === "info" ? html : "";
  body.scrollTop = resetScroll ? 0 : scroll;
  for (const b of body.querySelectorAll(".stabs button")) {
    b.onclick = () => { S.skillTab = +b.dataset.stab; renderInspector(); };
  }
  bindItems(body);
}

/** A Copy button's code (an item's Gibbed code) to the clipboard: "Copied" on it until the pointer leaves. Without
 *  the clipboard API (the page opened by another machine's address: not a secure context) the old copy command on the
 *  code selected; that failing too, the code stays selected and the button says to copy it by hand. */
function copyCode(btn) {
  const said = (key) => {
    btn.textContent = t(key);
    btn.onmouseleave = () => { btn.textContent = t("item.copy"); btn.onmouseleave = null; };
  };
  const byHand = () => {
    const code = btn.parentElement.querySelector("code"), range = document.createRange();
    range.selectNodeContents(code);
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { /* (unsupported) */ }
    said(ok ? "item.copied" : "item.copyByHand");
  };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(btn.dataset.copy).then(() => said("item.copied"), byHand);
  else byHand();
}

/** The item cards in `body` (items.js): a click opens one, its header closes it; a fold's header its fold. */
export function bindItems(body) {
  for (const el of body.querySelectorAll(".item")) {
    el.onclick = (e) => {
      const id = el.dataset.id;
      const copy = e.target.closest(".icopy"); // (its Gibbed code's Copy button)
      if (copy) {
        copyCode(copy);
        return;
      }
      // a fold's header (Parts, Details): that fold opens / closes, not the item; inside an open item: nothing
      const head = e.target.closest(".ifhead");
      if (head) {
        const fold = head.parentElement, key = `${id}:${fold.dataset.fold}`;
        if (S.itemFolds.has(key)) S.itemFolds.delete(key); else S.itemFolds.add(key);
        fold.classList.toggle("open");
        return;
      }
      // folded: anywhere opens it; open: its header closes it - only it (drawer.css: its hover / pointer the same)
      if (S.expanded.has(id) && !e.target.closest(".ihd")) return;
      if (S.expanded.has(id)) S.expanded.delete(id); else S.expanded.add(id);
      el.classList.toggle("expanded");
    };
  }
}

let nextInfo = 0, infoState = 0;
/** From the frames: the Info tab follows the game's data - only when a new update arrived (the
 *  game's rate) or Follow changed, at most every 250 ms, and the DOM only touched when its content changed. */
export function refreshPlayerInfo(now) {
  if (!S.inspect || S.detail || S.missionView || S.shopView || settings.ui.inspectorTab !== "info") return;
  // (a new game update - or Follow / the tracked player changed: its Follow button - "Following" stayed after a drag
  // let go, no update coming while nothing moves: the stream sends changes only)
  const state = `${S.lastState}|${settings.view.follow}|${settings.view.target}`;
  if (now < nextInfo || state === infoState) return;
  nextInfo = now + 250;
  infoState = state;
  const p = findPlayer();
  if (!p) return;
  const html = playerInfoHtml(p), body = $("ibody");
  if (body.dataset.info !== html) { body.dataset.info = html; body.innerHTML = html; alignPatterns(body); }
}

export function initInspector() {
  for (const b of $("itabs").querySelectorAll("button")) {
    b.onclick = () => { settings.ui.inspectorTab = b.dataset.tab; saveSettings(); S.skillTab = null; renderInspector(true); };
  }
  $("iclose").onclick = closeInspector;
  // the Info tab's "Track": that player as "Who" (Settings), like choosing them there; then "Follow": the Settings
  // box's click (F's: centred, remembered, Rotate enabled)
  $("inspector").addEventListener("click", (e) => {
    const btn = e.target instanceof Element ? e.target.closest("[data-track], [data-follow]") : null;
    if (!btn) return;
    if (btn.dataset.track != null) {
      settings.view.target = btn.dataset.track;
      saveSettings();
      renderTargets();
      renderPlayers();
      invalidate();
    } else {
      $("follow").click();
    }
    renderInspector();
  });
  // an item's element icon loaded: its colour for its type icon (load doesn't bubble: captured)
  $("inspector").addEventListener("load", (e) => {
    if (e.target instanceof HTMLImageElement && e.target.classList.contains("ii-element")) elementIconLoaded(e.target);
  }, true);
}
