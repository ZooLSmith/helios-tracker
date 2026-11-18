// The damage log's time range: the Recap and Log tabs' (design.md "The rework": shared - one fight recapped, then its
// lines; Realtime has its own "last N s" slider), and its control - a thin track over the time the hits are kept (Keep
// hits for, up to now), two handles, the window between them. The window is a place on the track (its ends: shares of
// it), not times: it slides with the game, its handles staying where they were put (the user: a window frozen at its
// times drifted left as time went on, squashed at the track's start). The window itself dragged moves both handles,
// its width kept (the user); a click on the track elsewhere centres it there. Under it, its ends' clock times
// ("10:30:12 PM", both - no "now": the user; absolute for a stretch of time, relative is Realtime's). Right under the
// track, a 6 px heatmap of the damage over the same time (the user's idea): where the fights were, at a glance.
// Reusable: any view builds one with rangeHtml() and refreshes it from the frames with refreshRange().
import { esc } from "../dom.js";
import { t } from "../i18n.js";
import { saveSettings, settings } from "../settings.js";
import { clockText } from "./parts.js";

export const MIN_WIDTH = 1000; // the window's narrowest, ms
/** The window: its ends as shares of the track (0: Keep hits for ago, 1: now) - settings.ui.damageFrom / damageTo, the
 *  last picked (the user: not 60 s each time). */
export const damageWindow = { f1: 0, f2: 1 };
let restored = false;

/** The track's bounds: the whole time hits are kept (Keep hits for), up to now - always that size, hits or not (the
 *  user: sized from the first hit, a fresh session's track kept rescaling). */
function bounds(store) {
  const end = store.now();
  return [end - Math.max(store.keepMs, MIN_WIDTH), end];
}

/** The window now: [t1, t2] (the log's ms). */
export function windowSpan(store) {
  const [min, max] = bounds(store), w = max - min;
  return [min + damageWindow.f1 * w, min + damageWindow.f2 * w];
}

/** The control's HTML (one per view: data-dmrange binds it). */
export function rangeHtml() {
  return `<div class="dmrange" data-dmrange><div class="dmtrack" data-tip="${esc(t("dmg.windowTip"))}">` +
    `<div class="dmsel"></div><div class="dmh lo" tabindex="0"></div><div class="dmh hi" tabindex="0"></div></div><canvas class="dmheat"></canvas>` +
    `<div class="dmrangebar"><span class="dmfrom"></span><span class="dmto"></span></div></div>`;
}

const clamp01 = (v) => Math.min(1, Math.max(0, v));

/** Binds a control built from rangeHtml(); `changed()` when the user moves the window. */
export function bindRange(root, store, changed) {
  if (!restored) { // (the first time this page: the window last picked)
    restored = true;
    const f1 = clamp01(Number(settings.ui.damageFrom) || 0), f2 = clamp01(Number(settings.ui.damageTo) || 1);
    Object.assign(damageWindow, f2 > f1 ? { f1, f2 } : { f1: 0, f2: 1 });
  }
  const track = root.querySelector(".dmtrack");
  refreshRange(root, store);
  const minShare = () => { const [min, max] = bounds(store); return Math.min(1, MIN_WIDTH / (max - min)); };
  const apply = (a, b) => {
    Object.assign(damageWindow, { f1: clamp01(a), f2: clamp01(b) });
    settings.ui.damageFrom = Math.round(damageWindow.f1 * 1e4) / 1e4; // (remembered: saved, debounced)
    settings.ui.damageTo = Math.round(damageWindow.f2 * 1e4) / 1e4;
    saveSettings();
    refreshRange(root, store);
    changed();
  };
  // what's dragged: a handle ("lo" / "hi") or the window ("move": its width kept)
  let drag = null;
  track.onpointerdown = (e) => {
    if (e.button !== 0) return;
    const rect = track.getBoundingClientRect();
    const at = (x) => clamp01((x - rect.left) / Math.max(1, rect.width));
    const handle = e.target.closest(".dmh");
    const what = handle ? (handle.classList.contains("lo") ? "lo" : "hi") : "move";
    const from = at(e.clientX);
    if (what === "move" && !e.target.closest(".dmsel")) { // the track elsewhere: the window centred there first
      const w = damageWindow.f2 - damageWindow.f1, c = Math.min(1 - w / 2, Math.max(w / 2, from));
      apply(c - w / 2, c + w / 2);
    }
    drag = { what, at, from, a0: damageWindow.f1, b0: damageWindow.f2 };
    root.dataset.held = what; // (the cursor: drawer.css)
    track.setPointerCapture(e.pointerId);
    e.preventDefault();
  };
  track.onpointermove = (e) => {
    if (!drag) return;
    const { what, at, from, a0, b0 } = drag, x = at(e.clientX), m = minShare();
    if (what === "lo") apply(Math.min(x, b0 - m), b0);
    else if (what === "hi") apply(a0, Math.max(x, a0 + m));
    else {
      const d = Math.min(1 - b0, Math.max(-a0, x - from));
      apply(a0 + d, b0 + d);
    }
  };
  track.onpointerup = track.onpointercancel = () => { drag = null; delete root.dataset.held; };
  // the keyboard: a handle focused, the arrows move it by a hundredth of the track (Shift: a tenth)
  for (const h of root.querySelectorAll(".dmh")) {
    h.onkeydown = (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const { f1: a, f2: b } = damageWindow, m = minShare();
      const step = (e.shiftKey ? 0.1 : 0.01) * (e.key === "ArrowLeft" ? -1 : 1);
      if (h.classList.contains("lo")) apply(Math.min(b - m, a + step), b);
      else apply(a, Math.max(a + m, b + step));
      e.preventDefault();
    };
  }
}

/** The control's handles (where they were put), its times (sliding with the game) and its heatmap. */
export function refreshRange(root, store) {
  const [min, max] = bounds(store), [t1, t2] = windowSpan(store);
  const p1 = `${(100 * damageWindow.f1).toFixed(2)}%`, p2 = `${(100 * damageWindow.f2).toFixed(2)}%`;
  const sel = root.querySelector(".dmsel");
  sel.style.left = p1;
  sel.style.width = `${(100 * (damageWindow.f2 - damageWindow.f1)).toFixed(2)}%`;
  root.querySelector(".dmh.lo").style.left = p1;
  root.querySelector(".dmh.hi").style.left = p2;
  drawHeat(root, store, min, max);
  const from = clockText(store, t1), to = clockText(store, t2);
  if (root.querySelector(".dmfrom").textContent !== from) root.querySelector(".dmfrom").textContent = from;
  if (root.querySelector(".dmto").textContent !== to) root.querySelector(".dmto").textContent = to;
}

const heatShown = new WeakMap(); // a control -> what its heatmap was drawn from (drawn again only on a change)

/** The heatmap under the track: the damage dealt (store.heat: per second, not on oneself) in a column per pixel over
 *  [min, max], the accent's opacity the square root of its share of the busiest column (a small fight still shows). */
function drawHeat(root, store, min, max) {
  const canvas = root.querySelector(".dmheat");
  if (!canvas) return;
  const width = canvas.clientWidth;
  const key = `${store.count}|${Math.floor(min / 1000)}|${Math.floor(max / 1000)}|${width}`;
  if (!width || heatShown.get(root) === key) return;
  heatShown.set(root, key);
  if (canvas.width !== width) canvas.width = width;
  canvas.height = 1; // (stretched to its CSS height)
  const bins = new Float64Array(width), span = Math.max(1, max - min);
  for (const [sec, amount] of store.heat) {
    const x = Math.floor(((sec * 1000 + 500 - min) / span) * width);
    if (x >= 0 && x < width) bins[x] += amount;
  }
  let top = 0;
  for (const v of bins) if (v > top) top = v;
  const g = canvas.getContext("2d");
  g.clearRect(0, 0, width, 1);
  if (!top) return;
  g.fillStyle = getComputedStyle(canvas).color; // (its CSS: the accent - a theme's own)
  for (let x = 0; x < width; x++) {
    if (!bins[x]) continue;
    g.globalAlpha = Math.max(0.15, Math.sqrt(bins[x] / top));
    g.fillRect(x, 0, 1, 1);
  }
}
