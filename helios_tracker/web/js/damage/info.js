// The Info tab's Damage section (below Players): a quick summary - who dealt the most damage in the last minute, 4
// lines at most (a name, a bar: their share, the amount); its heading's "All" opens the log in the drawer (view.js).
// Hidden without the session's "damage" feature (the mod's Damage Log option off, a game without it). Drawn from the
// frames (draw.js), throttled, the DOM written only when its text changed.
import { $, esc } from "../dom.js";
import { hasFeature } from "../game.js";
import { numShort, t } from "../i18n.js";
import { settings } from "../settings.js";
import { damageStore } from "./store.js";
import { actorHtml, openDamageLog } from "./view.js";

const TOP = 4;
const WINDOW_MS = 60000;
const EVERY_MS = 1000; // (the window slides: drawn again even without a new hit)

let lastAt = -Infinity, shownHtml = "", shown = null, bound = false;

/** Drawn again at the next frame (the language...). */
export function damageInfoChanged() { lastAt = -Infinity; shownHtml = ""; }

/** From draw.js' frame: the section shown / hidden with the feature, the store's expiry, the summary. */
export function refreshDamageInfo(now) {
  const on = hasFeature("damage");
  if (on !== shown) {
    shown = on;
    for (const id of ["damageSec", "keepHitsRow"]) { const el = $(id); if (el) el.hidden = !on; }
    if (!bound) { bound = true; $("damageAll").addEventListener("click", () => openDamageLog()); }
    damageInfoChanged();
  }
  if (!on || now - lastAt < EVERY_MS) return;
  lastAt = now;
  const store = damageStore;
  store.setKeep(settings.view.keepHits);
  store.expire();
  $("damageAll").hidden = !store.count && !store.events.length;
  const html = summaryHtml(store);
  if (html !== shownHtml) { shownHtml = html; $("damage").innerHTML = html; }
}

/** The ones who dealt the most damage in the last minute (health and shields), the most first - to others only. */
export function summaryHtml(store, end = store.now()) {
  const dealt = new Map();
  let total = 0;
  store.forEachHit(end - WINDOW_MS, end, (h) => {
    if (!h.a || h.a === h.v) return; // (no attacker; one's own damage on oneself: not "dealt" - the user)
    const amount = h.h + h.s;
    dealt.set(h.a, (dealt.get(h.a) || 0) + amount);
    total += amount;
  });
  const top = [...dealt].sort((a, b) => b[1] - a[1]).slice(0, TOP);
  if (!top.length || total <= 0) return `<div class="muted">${esc(t("dmg.quiet"))}</div>`;
  return top.map(([id, amount]) => `<div class="dmsum"><span class="dmwho">${actorHtml(store, id)}</span>` +
    `<span class="dmbar"><i style="width:${(100 * amount / top[0][1]).toFixed(1)}%"></i></span>` +
    `<span class="dmamt" data-tip="${esc(t("unit.percent", { n: Math.round(100 * amount / total) }))}">${esc(numShort(Math.round(amount)))}</span></div>`).join("");
}
