// The damage log's time range: the Recap and Log tabs' (design.md "The rework": shared - one fight recapped, then its
// lines; Realtime has its own "last N s" slider), and its control - a thin track over the time the hits are kept, two
// handles, the window between them. Live (the default): the right
// handle at the end, the window sliding with the game, its width kept (its end reads "now"); the right handle dragged
// back: frozen - back to the end: live again (the user: no button for it). The window itself dragged moves both
// handles, its width kept (the user); a click on the track elsewhere centres it there. Its times the clock's
// ("10:30:12" - "now" live: the user, absolute for a stretch of time; relative is Realtime's). Right under the track, a 2 px heatmap of the damage over the same time (the user's idea): where the
// fights were, at a glance. Reusable: any view builds one with rangeHtml() and refreshes it from the frames with refreshRange();
// step 4's timeline goes under it.
import { esc } from "../dom.js";
import { t } from "../i18n.js";
import { saveSettings, settings } from "../settings.js";
import { clockText } from "./parts.js";

export const MIN_WIDTH = 1000;
/** The window: live (its width, ms) or frozen (t1 / t2: the log's ms). Its width the one last picked (the user: not
 *  60 s each time) - settings.ui.damageWindow, opened live: that much time up to now. */
export const damageWindow = { live: true, width: 60000, t1: 0, t2: 0 };
let restored = false;

/** The window now: [t1, t2] (the log's ms). */
export function windowSpan(store) {
  if (damageWindow.live) { const end = store.now(); return [end - damageWindow.width, end]; }
  return [damageWindow.t1, damageWindow.t2];
}

/** The range's bounds: the whole time hits are kept (Keep hits for), up to now - always that size, hits or not (the
 *  user: sized from the first hit, a fresh session's track kept rescaling). */
function bounds(store) {
  const end = store.now();
  return [end - Math.max(store.keepMs, MIN_WIDTH), end];
}

/** The control's HTML (one per view: data-dmrange binds it). */
export function rangeHtml() {
  return `<div class="dmrange" data-dmrange><div class="dmtrack" data-tip="${esc(t("dmg.windowTip"))}">` +
    `<div class="dmsel"></div><div class="dmh lo" tabindex="0"></div><div class="dmh hi" tabindex="0"></div></div><canvas class="dmheat"></canvas>` +
    `<div class="dmrangebar"><span class="dmfrom"></span><span class="dmto"></span></div></div>`;
}

// The scale each control was last drawn on ([min, max], the log's ms): kept still while a handle's held - time goes on
// meanwhile, and "now" would slip from under the pointer (the user saw both handles drift left)
const scales = new WeakMap();

/** Sets the window from [a, b] on the control's scale: at its end (give or take half a percent) live. */
function setWindow(root, a, b) {
  const [min, max] = scales.get(root);
  if (b >= max - (max - min) / 200) Object.assign(damageWindow, { live: true, width: Math.max(MIN_WIDTH, max - a) });
  else Object.assign(damageWindow, { live: false, t1: a, t2: b });
  settings.ui.damageWindow = Math.round(damageWindow.live ? damageWindow.width : b - a); // (remembered: saved, debounced)
  saveSettings();
}

/** Binds a control built from rangeHtml(); `changed()` when the user moves the window. */
export function bindRange(root, store, changed) {
  if (!restored) { // (the first time this page: the width last picked, live)
    restored = true;
    Object.assign(damageWindow, { live: true, width: Math.max(MIN_WIDTH, Number(settings.ui.damageWindow) || 60000) });
  }
  const track = root.querySelector(".dmtrack");
  refreshRange(root, store);
  const span = () => {
    const [min, max] = scales.get(root);
    let [a, b] = damageWindow.live ? [max - damageWindow.width, max] : [damageWindow.t1, damageWindow.t2];
    a = Math.max(a, min);
    return [min, max, a, Math.max(b, a + MIN_WIDTH)];
  };
  const apply = (a, b) => { setWindow(root, a, b); refreshRange(root, store, false); changed(); };
  // what's dragged: a handle ("lo" / "hi") or the window ("move": its width kept)
  let drag = null;
  track.onpointerdown = (e) => {
    if (e.button !== 0) return;
    const [min, max, a, b] = span(), rect = track.getBoundingClientRect();
    const at = (x) => min + ((x - rect.left) / Math.max(1, rect.width)) * (max - min);
    const handle = e.target.closest(".dmh");
    const what = handle ? (handle.classList.contains("lo") ? "lo" : "hi") : "move";
    let from = at(e.clientX);
    if (what === "move" && !e.target.closest(".dmsel")) { // the track elsewhere: the window centred there first
      const w = b - a, c = Math.min(max - w / 2, Math.max(min + w / 2, from));
      apply(c - w / 2, c + w / 2);
    }
    const [, , a0, b0] = span();
    drag = { what, at, from, a0, b0, min, max };
    root.dataset.held = what; // (the frames leave the scale alone: refreshDamageView)
    track.setPointerCapture(e.pointerId);
    e.preventDefault();
  };
  track.onpointermove = (e) => {
    if (!drag) return;
    const { what, at, from, a0, b0, min, max } = drag, x = Math.min(max, Math.max(min, at(e.clientX)));
    if (what === "lo") apply(Math.min(x, b0 - MIN_WIDTH), b0);
    else if (what === "hi") apply(a0, Math.max(x, a0 + MIN_WIDTH));
    else {
      const d = Math.min(max - b0, Math.max(min - a0, at(e.clientX) - from));
      apply(a0 + d, b0 + d);
    }
  };
  track.onpointerup = track.onpointercancel = () => { drag = null; delete root.dataset.held; };
  // the keyboard: a handle focused, the arrows move it by a hundredth of the track (Shift: a tenth)
  for (const h of root.querySelectorAll(".dmh")) {
    h.onkeydown = (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const [min, max, a, b] = span(), step = ((max - min) / (e.shiftKey ? 10 : 100)) * (e.key === "ArrowLeft" ? -1 : 1);
      if (h.classList.contains("lo")) apply(Math.min(b - MIN_WIDTH, Math.max(min, a + step)), b);
      else apply(a, Math.min(max, Math.max(a + MIN_WIDTH, b + step)));
      e.preventDefault();
    };
  }
}

/** The control's handles and times, as the window is now (the frames: live, it slides). `scale` false (being
 *  dragged): its scale left as it was - only the window on it and the times. */
export function refreshRange(root, store, scale = true) {
  if (scale || !scales.has(root)) scales.set(root, bounds(store));
  const [min, max] = scales.get(root);
  let [t1, t2] = damageWindow.live ? [max - damageWindow.width, max] : [damageWindow.t1, damageWindow.t2];
  t1 = Math.max(t1, min); // (a frozen window older than what's kept: its hits are gone)
  const pct = (v) => (max > min ? Math.min(100, Math.max(0, (100 * (v - min)) / (max - min))) : 0);
  const sel = root.querySelector(".dmsel");
  sel.style.left = `${pct(t1)}%`;
  sel.style.width = `${pct(t2) - pct(t1)}%`;
  root.querySelector(".dmh.lo").style.left = `${pct(t1)}%`;
  root.querySelector(".dmh.hi").style.left = `${pct(t2)}%`;
  drawHeat(root, store, min, max);
  const from = clockText(store, t1), to = damageWindow.live ? t("dmg.now") : clockText(store, t2);
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
