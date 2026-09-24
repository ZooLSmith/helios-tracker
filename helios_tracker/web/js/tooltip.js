// The hover tooltip and the world X / Y under the cursor.
import { $, classHtml, esc, nameHtml } from "./dom.js";
import { UU_PER_METER, mapToWorld } from "./geo.js";
import { t, num } from "./i18n.js";
import { hitAt } from "./input.js";
import { isGear, poolKinds } from "./model.js";
import { settings } from "./settings.js";
import { S, trackedPawn } from "./state.js";
import { rarityName } from "./ui/items.js";
import { H, W, toMap } from "./view.js";

// The last frame's context: the tooltip also follows the pointer between frames (refreshTooltip: at full speed,
// whatever the Refresh rate - someone's using the page), from that frame's markers (S.hits)
let lastFrame = null;

/** From each frame (draw.js): the markers may have moved under the pointer. */
export function tooltip(mePos, f) {
  lastFrame = { mePos, f };
  renderTooltip(mePos, f);
}

/** From the pointer (input.js): at once, not at the next frame. */
export function refreshTooltip() {
  if (lastFrame) renderTooltip(lastFrame.mePos, lastFrame.f);
}

function renderTooltip(mePos, f) {
  const tip = $("tip"), coords = $("coords");
  if (!S.mouse) { tip.style.display = "none"; coords.textContent = ""; return; }
  const [wx, wy] = mapToWorld(f, ...toMap(S.mouse.x, S.mouse.y));
  // (the coordinates: only when asked for - Settings, off by default)
  coords.textContent = settings.view.coords ? `X ${num(Math.round(wx))}  Y ${num(Math.round(wy))}` : "";
  if (settings.view.coords) placeCoords(coords);
  const best = hitAt(S.mouse.x, S.mouse.y, 12);
  if (!best) { tip.style.display = "none"; return; }
  const it = best.item, pos = best.pos || it;
  const lines = [];
  if (best.kind === "objective" || best.kind === "directive") {
    lines.push(`<span class="tl">${esc(t("tip." + best.kind))}${it.rad ? " · " + esc(t("tip.area", { d: Math.round(it.rad / UU_PER_METER) })) : ""}</span>`);
    // (a quest giver: every mission it has, one per line - the ones to hand in marked)
    for (const m of it.list || [it.mission]) {
      lines.push(`<span class="tl">${nameHtml(m)}${m.end ? " · " + esc(t("detail.handIn")) : ""}${it.tracked && !it.list ? " · " + esc(t("tip.tracked")) : ""}</span>`);
    }
    if (mePos) lines.push(`<span class="tl">${esc(t("tip.away", { d: Math.round(Math.hypot(it.x - mePos.x, it.y - mePos.y, it.z - mePos.z) / UU_PER_METER) }))}</span>`);
    tip.innerHTML = `<b>${it.objective ? nameHtml(it.objective) : nameHtml(it.mission)}</b>` + lines.join("");
    placeTip(tip);
    return;
  }
  if (it.loot && it.loot.length) { // a container: the details (its pools) are in the click panel
    lines.push(`<span class="tl">${esc(t("tip.contentsCount", { n: poolKinds(it.loot).length }))}</span>`);
  }
  // Loot: rarity only means something for gear - cash / ammo carry fake levels (e.g. 181) for colour
  const gear = best.kind === "loot" && isGear(it.c);
  const kindHtml = best.kind === "loot" ? (gear ? esc(rarityName(it.q)) + " · " : "") + classHtml(it.c || "Pickup")
    : best.kind === "other" ? classHtml(it.c)
    : (best.kind === "me" || best.kind === "player") && S.players.some((p) => p.i === it.i && p.host) ? esc(t("tip.host"))
    : esc(t("tip." + best.kind, null, best.kind));
  lines.push(`<span class="tl">${kindHtml}</span>`);
  if (it.ms) lines.push(`<span class="tl">${esc(t(it.ms.k === "gives" ? "tip.givesMission" : "tip.forMission", { n: it.ms.n }))}</span>`);
  if (it.rs) lines.push(`<span class="tl">${esc(t("tip.respawning"))}</span>`);
  else if (it.dd) lines.push(`<span class="tl">${esc(t("vital.dead"))}</span>`);
  else if (it.dn) lines.push(`<span class="tl">${esc(t("vital.ffyl"))}</span>`);
  else if (it.ct) lines.push(`<span class="tl">${esc(t("vital.cutscene"))}</span>`);
  else if (it.mn) lines.push(`<span class="tl">${esc(t("vital.menu"))}</span>`);
  if (it.l && (best.kind !== "loot" || gear)) lines.push(`<span class="tl">${esc(t("insp.level", { n: it.l }))}</span>`);
  if (it.sm > 0) lines.push(`<span class="tl">${esc(t("tip.shield", { s: Math.round(it.s), m: Math.round(it.sm) }))}</span>`);
  if (it.m > 0) lines.push(`<span class="tl">${esc(t("tip.health", { h: Math.round(it.h), m: Math.round(it.m) }))}</span>`);
  if (mePos && it !== trackedPawn()) { // not the tracked player itself
    const dist = Math.hypot(pos.x - mePos.x, pos.y - mePos.y, pos.z - mePos.z) / UU_PER_METER;
    const dz = (pos.z - mePos.z) / UU_PER_METER;
    let text = t("tip.away", { d: Math.round(dist) });
    if (Math.abs(dz) >= 3) text += ", " + t(dz > 0 ? "tip.above" : "tip.below", { d: Math.round(Math.abs(dz)) });
    lines.push(`<span class="tl">${esc(text)}</span>`);
  }
  tip.innerHTML = `<b>${nameHtml(it)}</b>` + lines.join("");
  placeTip(tip);
}

// The coordinates by the cursor, above and right of it (the tooltip: below) - kept inside the window (the drawer
// open used to hide them in the bottom right corner)
function placeCoords(coords) {
  const cw = coords.offsetWidth, ch = coords.offsetHeight;
  coords.style.left = Math.max(4, Math.min(W - cw - 4, S.mouse.x + 14)) + "px";
  coords.style.top = Math.max(4, S.mouse.y - ch - 6) + "px";
}

function placeTip(tip) {
  tip.style.display = "block";
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = Math.min(W - tw - 8, S.mouse.x + 14) + "px";
  tip.style.top = Math.min(H - th - 8, S.mouse.y + 14) + "px";
}
