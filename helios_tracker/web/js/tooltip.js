// The hover tooltip and the world X / Y under the cursor.
import { $, classHtml, esc, nameHtml } from "./dom.js";
import { UU_PER_METER, mapToWorld } from "./geo.js";
import { money, t, num } from "./i18n.js";
import { hitAt } from "./input.js";
import { isGear, poolKinds, rainbowAt, rarity, shownHealth, shownMaxHealth } from "./model.js";
import { settings } from "./settings.js";
import { S, itemById, trackedPawn } from "./state.js";
import { pickupAmount, pickupIconHtml, rarityName } from "./ui/items.js";
import { H, W, panelRects, toMap } from "./view.js";

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

// Item card icons that failed to load (their URL): their text instead from then on - the tooltip is rebuilt each frame,
// a fallback made in place wouldn't last (load errors don't bubble: caught on the way down, once)
const failedIcons = new Set();
let watchingIcons = false;
const iconOk = (url) => !failedIcons.has(url);

function renderTooltip(mePos, f) {
  const tip = $("tip"), coords = $("coords");
  if (!watchingIcons) {
    watchingIcons = true;
    tip.addEventListener("error", (e) => {
      if (e.target instanceof HTMLImageElement) { failedIcons.add(e.target.getAttribute("src")); refreshTooltip(); }
    }, true);
  }
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
    tip.classList.remove("hasicon", "hasgear"); // (no pickup icon: the last one's room gone)
    tip.innerHTML = `<b>${it.objective ? nameHtml(it.objective) : nameHtml(it.mission)}</b>` + lines.join("");
    placeTip(tip);
    return;
  }
  if (it.loot && it.loot.length) { // a container: the details (its pools) are in the click panel
    lines.push(`<span class="tl">${esc(t("tip.contentsCount", { n: poolKinds(it.loot).length }))}</span>`);
  }
  // Loot: rarity only means something for gear - cash / ammo carry fake levels (e.g. 181) for colour
  const gear = best.kind === "loot" && isGear(it.c);
  // gear with its item's record (the collector's, by id - the backpack's for a dropped one): a mini card - its rarity,
  // type, maker, level, element, price; its card lines and stats in the click panel
  const card = gear ? itemById(it.it) : null;
  // (its maker at the bottom - its logo, else its name there; its element's icon beside it, else its name as a line)
  const cardIcon = (kind, key) => (card && S.assets.cards && /^[A-Za-z0-9_]+$/.test(key || "") && iconOk(`/cardicon/${kind}/${key}.png`) ? key : "");
  const brandKey = cardIcon("manufacturer", card?.mf);
  // its element's icon: gear's (its card), or an object's that explodes (a barrel: its explosion's - collector.py)
  const elementSrc = card || (it.el ? it : null);
  const elementKey = elementSrc && S.assets.cards && /^[A-Za-z0-9_]+$/.test(elementSrc.el || "") &&
    iconOk(`/cardicon/element/${elementSrc.el}.png`) ? elementSrc.el : "";
  const kindHtml = card ? esc([rarityName(it.q), card.type || t("kind." + card.k, null, card.k)].filter(Boolean).join(" · "))
    : best.kind === "loot" ? (gear ? esc(rarityName(it.q)) + " · " : "") + classHtml(it.c || "Pickup")
    : best.kind === "other" ? classHtml(it.c)
    : (best.kind === "me" || best.kind === "player") && S.players.some((p) => p.i === it.i && p.host) ? esc(t("tip.host"))
    : it.boss ? esc(t("tip.boss")) // (its AI class's bBoss)
    : esc(t("tip." + best.kind, null, best.kind));
  lines.push(`<span class="tl">${kindHtml}</span>`);
  if (it.ms) lines.push(`<span class="tl">${esc(t(it.ms.k === "gives" ? "tip.givesMission" : "tip.forMission", { n: it.ms.n }))}</span>`);
  if (it.rs) lines.push(`<span class="tl">${esc(t("tip.respawning"))}</span>`);
  else if (it.dd) lines.push(`<span class="tl">${esc(t("vital.dead"))}</span>`);
  else if (it.dn) lines.push(`<span class="tl">${esc(t("vital.ffyl"))}</span>`);
  else if (it.ct) lines.push(`<span class="tl">${esc(t("vital.cutscene"))}</span>`);
  else if (it.mn) lines.push(`<span class="tl">${esc(t("vital.menu"))}</span>`);
  if (it.l && (best.kind !== "loot" || gear)) lines.push(`<span class="tl">${esc(t("insp.level", { n: it.l }))}</span>`);
  if (card) {
    // its element (the game's name) and price - no card lines, no stats (the user's call: "Burst fire while zoomed",
    // "Consumes 2 ammo" - all in the click panel)
    if (card.eln && !elementKey) lines.push(`<span class="tl">${esc(card.eln)}</span>`);
    if (card.v) lines.push(`<span class="tl">${esc(t("tip.worth", { p: money(card.v) }))}</span>`);
  }
  // money / ammo on the ground: how much it gives (the collector's, from its definition: amounts.py)
  if (best.kind === "loot" && !gear && it.am) lines.push(`<span class="tl">${esc(pickupAmount(it))}</span>`);
  if (it.sm > 0) lines.push(`<span class="tl">${esc(t("tip.shield", { s: Math.round(it.s), m: Math.round(it.sm) }))}</span>`);
  if (it.m > 0) lines.push(`<span class="tl">${esc(t("tip.health", { h: shownHealth(it.h), m: shownMaxHealth(it.m) }))}</span>`);
  if (!card && it.xp && it.eln && !elementKey) lines.push(`<span class="tl">${esc(it.eln)}</span>`); // (an exploding object: its element's name - no icon)
  if (mePos && it !== trackedPawn()) { // not the tracked player itself
    const dist = Math.hypot(pos.x - mePos.x, pos.y - mePos.y, pos.z - mePos.z) / UU_PER_METER;
    const dz = (pos.z - mePos.z) / UU_PER_METER;
    let text = t("tip.away", { d: Math.round(dist) });
    if (Math.abs(dz) >= 3) text += ", " + t(dz > 0 ? "tip.above" : "tip.below", { d: Math.round(Math.abs(dz)) });
    lines.push(`<span class="tl">${esc(text)}</span>`);
  }
  // (a pickup's own icon - the game's, too detailed for the map's marker - in the tooltip's bottom right corner, big
  // enough to read; the text keeps clear of it: .hasicon)
  const tipIcon = best.kind === "loot" && !gear ? pickupIconHtml(it, "tpicon") : "";
  // gear: its manufacturer's logo (its item card's: the type is the map marker already) in its rarity's colour, pastel
  // as the card's (its white fill multiplied, its outline kept), along the bottom - wide, under the text; from its
  // item's record (once read)
  // its rarity's colour - effervescent's cycling, from the frames' clock as its map marker (the tooltip: rebuilt each
  // frame, at the Refresh rate)
  const [tierName, tierColor] = gear ? rarity(it.q || 0) : ["", ""];
  const gearColor = tierName === "effervescent" ? rainbowAt(performance.now()) : tierColor;
  const brandHtml = brandKey ? `<span class="tptint" style="--src:url('/cardicon/manufacturer/${brandKey}.png');--c:${gearColor}">` +
    `<img src="/cardicon/manufacturer/${brandKey}.png" crossorigin="anonymous" alt="" draggable="false"></span>`
    : card?.maker ? `<span class="tpbrand" style="--c:${gearColor}">${esc(card.maker)}</span>` : ""; // (no logo: its name, there)
  // its element's icon beside it, as the game draws it (the card's: untinted)
  const elementHtml = elementKey ? `<img class="tpelement" src="/cardicon/element/${elementKey}.png" crossorigin="anonymous" alt="" ` +
    `draggable="false">` : "";
  const gearIcon = brandHtml || elementHtml ? `<span class="tpicons">${elementHtml}${brandHtml}</span>` : "";
  tip.classList.toggle("hasicon", !!tipIcon);
  tip.classList.toggle("hasgear", !!gearIcon);
  // (gear's name in its rarity's colour, as the game's card)
  const titleStyle = gear ? ` style="color:${gearColor}"` : "";
  tip.innerHTML = `<b${titleStyle}>${nameHtml(it)}</b>` + lines.join("") + tipIcon + gearIcon;
  placeTip(tip);
}

// The coordinates by the cursor, above and right of it (the tooltip: below) - kept inside the window (the drawer
// open used to hide them in the bottom right corner)
/** Where a box (w x h) by the cursor goes: the first of `spots` ([x, y] top-left corners, in order of preference) that
 *  fits the window and covers no panel (the panel, the open drawer: the tooltip went under the drawer); none clear, the
 *  one covering the least. Kept `margin` inside the window. */
function placeBox(w, h, spots, margin) {
  const rects = panelRects();
  let best = null, bestCover = Infinity;
  for (const [sx, sy] of spots) {
    const x = Math.max(margin, Math.min(W - w - margin, sx)), y = Math.max(margin, Math.min(H - h - margin, sy));
    let cover = 0;
    for (const r of rects) {
      const ox = Math.min(x + w, r.right) - Math.max(x, r.left), oy = Math.min(y + h, r.bottom) - Math.max(y, r.top);
      if (ox > 0 && oy > 0) cover += ox * oy;
    }
    if (cover < bestCover) { best = [x, y]; bestCover = cover; }
    if (!cover) break;
  }
  return best;
}

function placeCoords(coords) {
  const cw = coords.offsetWidth, ch = coords.offsetHeight, { x, y } = S.mouse;
  // above right of the cursor (the tooltip: below), else above left, below right, below left
  const [left, top] = placeBox(cw, ch, [[x + 14, y - ch - 6], [x - 14 - cw, y - ch - 6], [x + 14, y + 6], [x - 14 - cw, y + 6]], 4);
  coords.style.left = left + "px";
  coords.style.top = top + "px";
}

function placeTip(tip) {
  tip.style.display = "block";
  const tw = tip.offsetWidth, th = tip.offsetHeight, { x, y } = S.mouse;
  // below right of the cursor, else below left, above right, above left - clear of the panels
  const [left, top] = placeBox(tw, th, [[x + 14, y + 14], [x - 14 - tw, y + 14], [x + 14, y - 14 - th], [x - 14 - tw, y - 14 - th]], 8);
  tip.style.left = left + "px";
  tip.style.top = top + "px";
}
