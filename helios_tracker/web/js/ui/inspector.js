// The right drawer: a player's Gear / Backpack / Skills (or a clicked object: detail.js).
import { $, esc } from "../dom.js";
import { t } from "../i18n.js";
import { nameText } from "../model.js";
import { S, findPlayer } from "../state.js";
import { store } from "../store.js";
import { renderDetail } from "./detail.js";
import { itemsByKind } from "./items.js";
import { playerSub, renderPlayers } from "./players.js";
import { skillsHtml } from "./skills.js";

export function openInspector(id) {
  const p = S.players.find((q) => q.i === id);
  if (!p) return;
  S.inspect = { id: p.i, name: p.n };
  S.detail = null;
  S.skillTab = null; // back to their tree with the most points
  $("inspector").classList.add("open");
  renderPlayers();
  renderInspector(true);
}

export function closeInspector() {
  S.inspect = null;
  S.detail = null;
  $("inspector").classList.remove("open");
  renderPlayers();
}

export function renderInspector(resetScroll) {
  const box = $("inspector");
  if (S.detail) { renderDetail(resetScroll); return; }
  $("itabs").style.display = "";
  if (!S.inspect) { box.classList.remove("open"); return; }
  const body = $("ibody");
  const scroll = body.scrollTop;
  const p = findPlayer();
  for (const b of $("itabs").querySelectorAll("button")) b.classList.toggle("on", b.dataset.tab === S.tab);
  if (!p) {
    $("iwho").textContent = S.inspect.name;
    $("isub").textContent = "";
    body.innerHTML = `<div class="note">${esc(t("insp.gone"))}</div>`;
    return;
  }
  $("iwho").textContent = p.local ? t("insp.host", { name: nameText(p) }) : nameText(p);
  $("isub").textContent = playerSub(p);
  let html = "";
  if (S.tab === "gear") {
    if (p.inventory === "partial") {
      html += `<div class="note">${esc(t("why.inventory." + (p.inventoryWhy || "unavailable")))} ${esc(t("insp.heldOnly"))}</div>`;
    }
    html += (p.equipped || []).length ? itemsByKind(p.equipped) : `<div class="muted">${esc(t("insp.nothing"))}</div>`;
  } else if (S.tab === "backpack") {
    if (p.inventory !== "full") html = `<div class="note">${esc(t("why.inventory." + (p.inventoryWhy || "unavailable")))}</div>`;
    else html = `<div class="muted">${esc(t("insp.items", { n: p.backpack.length }))}</div>` +
      (p.backpack.length ? itemsByKind(p.backpack) : "");
  } else {
    html = skillsHtml(p);
  }
  body.innerHTML = html;
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

export function initInspector() {
  for (const b of $("itabs").querySelectorAll("button")) {
    b.onclick = () => { S.tab = b.dataset.tab; store.set("tab", S.tab); S.skillTab = null; renderInspector(true); };
  }
  $("iclose").onclick = closeInspector;
}
