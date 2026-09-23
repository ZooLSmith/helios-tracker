// The right drawer: a player's Gear / Backpack / Skills (or a clicked object: detail.js, the
// mission log: missionlog.js).
import { $, esc } from "../dom.js";
import { num, t } from "../i18n.js";
import { nameText } from "../model.js";
import { saveSettings, settings } from "../settings.js";
import { S, findPlayer } from "../state.js";
import { renderDetail } from "./detail.js";
import { itemsByKind } from "./items.js";
import { renderMissionLog } from "./missionlog.js";
import { playerSub, renderPlayers } from "./players.js";
import { playerInfoHtml } from "./playerinfo.js";
import { skillsHtml } from "./skills.js";

export function openInspector(id) {
  const p = S.players.find((q) => q.i === id);
  if (!p) return;
  S.inspect = { id: p.i, name: p.n };
  S.detail = null;
  S.missionView = null;
  S.skillTab = null; // back to their tree with the most points
  $("inspector").classList.add("open");
  renderPlayers();
  renderInspector(true);
}

export function closeInspector() {
  S.inspect = null;
  S.detail = null;
  S.missionView = null;
  $("inspector").classList.remove("open");
  renderPlayers();
}

export function renderInspector(resetScroll) {
  const box = $("inspector");
  if (S.missionView) { renderMissionLog(resetScroll); return; }
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
    html += (p.equipped || []).length ? itemsByKind(p.equipped) : `<div class="muted">${esc(t("insp.nothing"))}</div>`;
  } else if (tab === "backpack") {
    if (p.inventory !== "full") html = `<div class="note">${esc(t("why.inventory." + (p.inventoryWhy || "unavailable")))}</div>`;
    else if (p.backpackWhy) {
      html = (p.slots ? `<div class="muted">${esc(t("insp.slots", { n: num(p.slots[0]), max: num(p.slots[1]) }))}</div>` : "") +
        `<div class="note">${esc(t("why.backpack." + p.backpackWhy))}</div>`;
    }
    else html = `<div class="muted">${esc(p.slots ? t("insp.slots", { n: num(p.slots[0]), max: num(p.slots[1]) })
      : t("insp.items", { n: p.backpack.length }))}</div>` +
      (p.backpack.length ? itemsByKind(p.backpack) : "");
  } else {
    html = skillsHtml(p);
  }
  body.innerHTML = html;
  body.dataset.info = tab === "info" ? html : "";
  body.scrollTop = resetScroll ? 0 : scroll;
  for (const b of body.querySelectorAll(".stabs button")) {
    b.onclick = () => { S.skillTab = +b.dataset.stab; renderInspector(); };
  }
  for (const el of body.querySelectorAll(".item")) {
    el.onclick = () => {
      const id = el.dataset.id;
      if (S.expanded.has(id)) S.expanded.delete(id); else S.expanded.add(id);
      el.classList.toggle("expanded");
    };
  }
}

let nextInfo = 0, infoState = 0;
/** From the frames: the Info tab follows the game's data - only when a new update arrived (the
 *  game's rate), at most every 250 ms, and the DOM only touched when its content changed. */
export function refreshPlayerInfo(now) {
  if (!S.inspect || S.detail || S.missionView || settings.ui.inspectorTab !== "info") return;
  if (now < nextInfo || S.lastState === infoState) return;
  nextInfo = now + 250;
  infoState = S.lastState;
  const p = findPlayer();
  if (!p) return;
  const html = playerInfoHtml(p), body = $("ibody");
  if (body.dataset.info !== html) { body.dataset.info = html; body.innerHTML = html; }
}

export function initInspector() {
  for (const b of $("itabs").querySelectorAll("button")) {
    b.onclick = () => { settings.ui.inspectorTab = b.dataset.tab; saveSettings(); S.skillTab = null; renderInspector(true); };
  }
  $("iclose").onclick = closeInspector;
}
