// The damage log's Realtime tab (view.js - design.md "The rework", the user's ideas): what's being done to the enemies
// now. A card per enemy / object taking damage - no player cards (the focus is what we do to them); one not hit for
// RECENT_MS gone (the user: no "how far back" slider - enemies die; a limit for a fight left behind). Its bar
// (bars.js): its pool (max health + shield), filled by what it's lost, split by who took it off - over its whole life
// (store.js lives). Ordered by a fading score (its damage taken, halved every 10 s: a fight going on rises), its pool breaking
// ties; a new order waits SWAP_MS (a thin bar fills meanwhile: the swap coming) so the cards don't jump at every hit.
// The cards move to their new place in JS from the frames - the Refresh rate setting's (smooth: gliding, N fps:
// stepped, updates only: at once - no CSS transition running behind its back). Anything that dies: translucent, its
// name struck through, gone FADE_MS later, the others moving up. Under its bar, while it's on the map and alive, its
// shield and health side by side - the Info tab's player bars (playerinfo.js barRow - the user: the usual widgets),
// updated in place (their pattern's animation never restarted by a redraw).
import { esc } from "../dom.js";
import { num, t } from "../i18n.js";
import { shownHealth, shownMaxHealth } from "../model.js";
import { settings } from "../settings.js";
import { S } from "../state.js";
import { barRow } from "../ui/playerinfo.js";
import { amountText } from "./amount.js";
import { barHtml, legendHtml } from "./bars.js";
import { actorHtml, isPlayer, maxPool, poolLeft } from "./parts.js";

export const RECENT_MS = 120000; // a card not hit for this long: gone (a fight left behind)
const FADE_MS = 10000; // a dead one's card kept this long (the user: 4 s was too short)
const SWAP_MS = 1500; // a new order waits this long
const GLIDE_MS = 140; // the cards' move: its time constant (smooth / N fps)
const CARDS = 60;

/** The deaths outside a hit (a fall, bled out): actor -> time - as of the kept events. */
function deaths(store) {
  const out = new Map();
  for (const e of store.events) if (e.kind === "died" || e.kind === "dead") out.set(e.actor, Math.max(out.get(e.actor) ?? -Infinity, e.t));
  return out;
}

/** The cards to show at `now` (the log's ms), in their order: [{id, life, score, pool, filled, dead}]. */
export function realtimeEntries(store, now, recentMs = RECENT_MS) {
  const died = deaths(store), out = [];
  for (const [id, life] of store.lives) {
    if (isPlayer(store, id) || life.total <= 0) continue;
    const death = Math.max(life.death, died.get(id) ?? -Infinity);
    const dead = death > -Infinity;
    if (dead ? now - death >= FADE_MS : life.last < now - recentMs) continue;
    const pool = maxPool(store, id), left = dead ? 0 : poolLeft(store, id);
    // (what it's lost: its pool less what it has left, known while it's on the map; else what was taken off it)
    const filled = dead ? 1 : pool > 0 ? (left != null ? (pool - left) / pool : life.total / pool) : 1;
    out.push({ id, life, score: store.score(life, now), pool, filled, dead });
  }
  out.sort((a, b) => b.score - a.score || b.pool - a.pool || a.id - b.id);
  return out.slice(0, CARDS);
}

// (its amount: what it lost - the contributions, overkill out: the user - never its damage taken in full)
const cardHtml = (store, e) => `<div class="dmrline"><span class="dmwho">${actorHtml(store, e.id)}</span>` +
  `<span class="dmramt">${esc(amountText(e.pool > 0 ? Math.min(e.life.total, e.pool) : e.life.total))}</span></div>${barHtml(store, e.life.parts, e.filled, 1, true)}`;

/** Its shield and health now: [[cls, label, value, fraction]...] - none off the map or dead (parts.js poolLeft's
 *  source: the map pawn's h / s, full when the record leaves them out). */
function vitals(store, e) {
  const def = store.actors.get(e.id), pawn = def?.m ? S.pawns.get(def.m) : null;
  if (e.dead || !pawn || !(pawn.m > 0)) return [];
  const out = [];
  if (pawn.sm > 0) {
    const s = Math.max(0, pawn.s ?? pawn.sm);
    out.push(["sh", t("detail.shield"), `${num(Math.round(s))} / ${num(Math.round(pawn.sm))}`, s / pawn.sm]);
  }
  const h = Math.max(0, pawn.h ?? pawn.m);
  out.push(["hp", t("detail.health"), `${num(shownHealth(h))} / ${num(shownMaxHealth(pawn.m))}`, h / pawn.m]);
  return out;
}

/** The card's bars, written in place: built when which bars it has changes, else only their fill and value. */
function drawVitals(box, bars) {
  const kinds = bars.map((b) => b[0]).join();
  if (box.dataset.kinds !== kinds) {
    box.dataset.kinds = kinds;
    box.innerHTML = bars.map(([cls, label, value, fraction]) => barRow(label, value, fraction, cls)).join("");
    return;
  }
  bars.forEach(([, , value, fraction], i) => {
    const bar = box.children[i], width = `${(Math.max(0, Math.min(1, fraction)) * 100).toFixed(1)}%`;
    if (bar.firstElementChild.style.width !== width) bar.firstElementChild.style.width = width;
    const v = bar.querySelector(".ibv");
    if (v.textContent !== value) v.textContent = value;
  });
}

// The tab's DOM, kept between frames: a card per actor (its element, its HTML as last written, its offset gliding to 0)
let box = null, cards = new Map(), order = [], pendingSince = 0, lastAnim = 0, legendShown = "";

/** The tab's list built in `list` (emptied): the legend, the swap bar, the cards. */
export function buildRealtime(list) {
  list.innerHTML = `<div class="dmlegendbox"></div><div class="dmswap"><i></i></div><div class="dmrt"></div>`;
  box = list;
  cards = new Map();
  order = [];
  pendingSince = 0;
  legendShown = "";
}

/** The cards as the store is now (view.js, throttled). */
export function updateRealtime(store, now = store.now()) {
  if (!box?.isConnected) return;
  const rt = box.querySelector(".dmrt");
  const entries = realtimeEntries(store, now);
  const want = entries.map((e) => e.id), byId = new Map(entries.map((e) => [e.id, e]));
  const seen = new Set();
  for (const e of entries) for (const id of e.life.parts.keys()) seen.add(id);
  const legend = legendHtml(store, seen);
  if (legend !== legendShown) { legendShown = legend; box.querySelector(".dmlegendbox").innerHTML = legend; }
  // the order: the cards kept keep theirs until the new one has waited SWAP_MS; a new card goes to its place at once
  const kept = order.filter((id) => byId.has(id)), wanted = want.filter((id) => order.includes(id));
  let next = kept;
  if (wanted.join() !== kept.join()) {
    if (!pendingSince) pendingSince = now;
    if (now - pendingSince >= SWAP_MS) { next = wanted; pendingSince = 0; }
  } else pendingSince = 0;
  next = next.slice();
  for (const id of want) if (!next.includes(id)) next.splice(Math.min(want.indexOf(id), next.length), 0, id);
  // FLIP: where each card was, the new order laid out, each moved back by the difference - then glided to 0
  const before = new Map();
  for (const [id, c] of cards) before.set(id, c.el.offsetTop + c.off);
  for (const [id, c] of cards) if (!byId.has(id)) { c.el.remove(); cards.delete(id); }
  for (const id of next) {
    let c = cards.get(id);
    if (!c) {
      const el = document.createElement("div");
      el.className = "dmrcard";
      el.innerHTML = `<div class="dmrtop"></div><div class="dmrvit"></div>`;
      c = { el, top: el.firstElementChild, vit: el.lastElementChild, html: "", off: 0 };
      cards.set(id, c);
    }
    const e = byId.get(id), html = cardHtml(store, e);
    if (html !== c.html) { c.html = html; c.top.innerHTML = html; }
    drawVitals(c.vit, vitals(store, e));
    c.el.classList.toggle("dead", e.dead);
    rt.appendChild(c.el); // (moved: in the new order)
  }
  for (const [id, c] of cards) if (before.has(id)) c.off = before.get(id) - c.el.offsetTop;
  order = next;
  if (!cards.size && !rt.querySelector(".note")) rt.innerHTML = `<div class="note">${esc(t("dmg.noEnemies"))}</div>`;
  else if (cards.size) rt.querySelector(".note")?.remove();
  const swap = box.querySelector(".dmswap > i");
  const w = pendingSince ? `${Math.min(100, (100 * (now - pendingSince)) / SWAP_MS).toFixed(0)}%` : "0%";
  if (swap.style.width !== w) swap.style.width = w;
  animateRealtime(performance.now(), true);
}

/** The cards' glide, every frame (draw.js -> view.js): each offset towards 0 - at once with "updates only". */
export function animateRealtime(at, now = false) {
  if (!box?.isConnected) return;
  const dt = lastAnim ? Math.min(200, at - lastAnim) : 16;
  lastAnim = at;
  const k = settings.view.motion && !now ? 1 - Math.exp(-dt / GLIDE_MS) : settings.view.motion ? 0 : 1;
  for (const c of cards.values()) {
    if (!c.off && !c.el.style.transform) continue;
    c.off -= c.off * k;
    if (Math.abs(c.off) < 0.5) c.off = 0;
    c.el.style.transform = c.off ? `translateY(${c.off.toFixed(1)}px)` : "";
  }
}
