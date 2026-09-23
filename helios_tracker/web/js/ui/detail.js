// The detail panel: a clicked object (not a player), in the inspector's drawer.
import { $, classHtml, esc, nameHtml } from "../dom.js";
import { UU_PER_METER } from "../geo.js";
import { num, t } from "../i18n.js";
import { isGear, nameText } from "../model.js";
import { S, findDetail, pawnPos, trackedPawn } from "../state.js";
import { saveDrawer } from "./drawer.js";
import { renderInspector } from "./inspector.js";
import { rarityName } from "./items.js";
import { renderPlayers } from "./players.js";

export function openDetail(kind, id) {
  S.detail = { kind, id };
  S.inspect = null;
  S.missionView = null;
  $("inspector").classList.add("open");
  saveDrawer();
  renderPlayers();
  renderInspector(true);
}

export function renderDetail(resetScroll) {
  const body = $("ibody"), scroll = body.scrollTop;
  $("itabs").style.display = "none";
  const it = findDetail(), kind = S.detail.kind;
  if (!it) {
    $("iwho").textContent = "";
    $("isub").textContent = "";
    body.innerHTML = `<div class="note">${esc(t("detail.gone"))}</div>`;
    return;
  }
  const mission = kind === "objective" || kind === "directive";
  $("iwho").innerHTML = mission ? nameHtml(it.objective || it.mission) : nameHtml(it);
  const gear = kind === "loot" && isGear(it.c);
  const kindText = kind === "loot" ? (gear ? rarityName(it.q) + " · " : "") + nameText({ n: String(it.c || "Pickup"), raw: 1 })
    : t("tip." + kind, null, kind);
  $("isub").textContent = [kindText, it.l && (kind !== "loot" || gear) ? t("insp.level", { n: it.l }) : ""]
    .filter(Boolean).join(" · ");
  const rows = [];
  const me = trackedPawn(); // the tracked player
  if (me && me !== it) {
    const pos = it.fx !== undefined ? pawnPos(it, performance.now()) : it;
    rows.push([t("detail.distance"), t("unit.meters", { n: num(Math.hypot(pos.x - me.x, pos.y - me.y, pos.z - me.z) / UU_PER_METER, 0) })]);
  }
  if (it.sm > 0) rows.push([t("detail.shield"), `${num(Math.round(it.s))} / ${num(Math.round(it.sm))}`]);
  if (it.m > 0) rows.push([t("detail.health"), `${num(Math.round(it.h))} / ${num(Math.round(it.m))}`]);
  if (mission) {
    rows.push([t("detail.mission"), null, nameHtml(it.mission)]);
    if (it.rad) rows.push([t("detail.area"), t("unit.meters", { n: num(it.rad / UU_PER_METER, 0) })]);
    rows.push([t("detail.tracked"), t(it.tracked ? "detail.yes" : "detail.no")]);
  }
  if (it.lootable) rows.push([t("detail.status"), t(it.looted ? "detail.looted" : "detail.unlooted")]);
  if (it.slots) rows.push([t("detail.slots"), num(it.slots)]);
  if (it.lists && it.lists.length) rows.push([t("detail.lists"), null, it.lists.map((n) => nameHtml({ n, raw: 1 })).join(", ")]);
  if (it.c && kind !== "loot") rows.push([t("item.class"), null, classHtml(it.c)]);
  if (it.d) rows.push([t("detail.definition"), it.d]);
  let html = `<div class="kv">` + rows.map(([k, v, h]) => `<span>${esc(k)}</span><span>${h ?? esc(v)}</span>`).join("") + `</div>`;
  if (it.loot && it.loot.length) { // every pool its loot is rolled from, one per line
    html += `<div class="group">${esc(t("detail.contents"))}</div><div class="plist">` +
      it.loot.map((n) => `<div>${nameHtml({ n: String(n).replace(/^Pool_/, ""), raw: 1 })}</div>`).join("") + `</div>`;
  }
  body.innerHTML = html;
  body.scrollTop = resetScroll ? 0 : scroll;
}
