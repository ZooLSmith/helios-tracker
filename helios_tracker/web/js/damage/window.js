// The damage log's time window: one for the whole page (design.md - every damage view shows it), and its control - a
// thin track over the time the hits are kept, two handles, the window between them. Live (the default): the right
// handle at the end, the window sliding with the game, its width kept (its end reads "now"); the right handle dragged
// back: frozen - back to the end: live again (the user: no button for it). The window itself dragged moves both
// handles, its width kept (the user); a click on the track elsewhere centres it there. Its times relative ("60 s ago" -
// the user). Reusable: any view builds one with rangeHtml() and refreshes it from the frames with refreshRange();
// step 4's timeline goes under it.
import { esc } from "../dom.js";
import { t } from "../i18n.js";

export const MIN_WIDTH = 1000;
/** The window: live (its width, ms) or frozen (t1 / t2: the log's ms). */
export const damageWindow = { live: true, width: 60000, t1: 0, t2: 0 };

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

/** How long ago a time of the log was: "now", "45 s ago", "3 min ago" (whole minutes from 2 min on). */
export function agoText(store, ms) {
  const s = Math.max(0, Math.round((store.now() - ms) / 1000));
  return s < 1 ? t("dmg.now") : s < 120 ? t("dmg.agoS", { n: s }) : t("dmg.agoMin", { n: Math.round(s / 60) });
}

/** The control's HTML (one per view: data-dmrange binds it). */
export function rangeHtml() {
  return `<div class="dmrange" data-dmrange><div class="dmtrack" data-tip="${esc(t("dmg.windowTip"))}">` +
    `<div class="dmsel"></div><div class="dmh lo" tabindex="0"></div><div class="dmh hi" tabindex="0"></div></div>` +
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
}

/** Binds a control built from rangeHtml(); `changed()` when the user moves the window. */
export function bindRange(root, store, changed) {
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
  const from = agoText(store, t1), to = damageWindow.live ? t("dmg.now") : agoText(store, t2);
  if (root.querySelector(".dmfrom").textContent !== from) root.querySelector(".dmfrom").textContent = from;
  if (root.querySelector(".dmto").textContent !== to) root.querySelector(".dmto").textContent = to;
}
