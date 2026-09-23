// The hover tooltip and the world X / Y under the cursor.
import { $, classHtml, esc, nameHtml } from "./dom.js";
import { UU_PER_METER, mapToWorld } from "./geo.js";
import { t, num } from "./i18n.js";
import { hitAt } from "./input.js";
import { isGear, poolKinds } from "./model.js";
import { S, trackedPawn } from "./state.js";
import { rarityName } from "./ui/items.js";
import { H, W, toMap } from "./view.js";

export function tooltip(mePos, f) {
  const tip = $("tip"), coords = $("coords");
  if (!S.mouse) { tip.style.display = "none"; coords.textContent = ""; return; }
  const [wx, wy] = mapToWorld(f, ...toMap(S.mouse.x, S.mouse.y));
  coords.textContent = `X ${num(Math.round(wx))}  Y ${num(Math.round(wy))}`;
  const best = hitAt(S.mouse.x, S.mouse.y, 12);
  if (!best) { tip.style.display = "none"; return; }
  const it = best.item, pos = best.pos || it;
  const lines = [];
  if (best.kind === "objective" || best.kind === "directive") {
    lines.push(`<span class="tl">${esc(t("tip." + best.kind))}${it.rad ? " · " + esc(t("tip.area", { d: Math.round(it.rad / UU_PER_METER) })) : ""}</span>`);
    lines.push(`<span class="tl">${nameHtml(it.mission)}${it.tracked ? " · " + esc(t("tip.tracked")) : ""}</span>`);
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
    : best.kind === "other" ? classHtml(it.c) : esc(t("tip." + best.kind, null, best.kind));
  lines.push(`<span class="tl">${kindHtml}</span>`);
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

function placeTip(tip) {
  tip.style.display = "block";
  const tw = tip.offsetWidth, th = tip.offsetHeight;
  tip.style.left = Math.min(W - tw - 8, S.mouse.x + 14) + "px";
  tip.style.top = Math.min(H - th - 8, S.mouse.y + 14) + "px";
}
