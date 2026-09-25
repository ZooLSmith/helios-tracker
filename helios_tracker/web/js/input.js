// Mouse / touch / keyboard on the map: wheel and pinch zoom, drag pan, hover, click, shortcuts.
import { $ } from "./dom.js";
import { invalidate, invalidateNow } from "./scheduler.js";
import { refreshTooltip } from "./tooltip.js";
import { saveSettings, settings } from "./settings.js";
import { S } from "./state.js";
import { openDetail } from "./ui/detail.js";
import { closeInspector, openInspector } from "./ui/inspector.js";
import { H, W, canvas, fit, resetSpin, screenToMapDelta, spinAt, stopFollow, zoomAt } from "./view.js";

const TWIST_START = 10; // degrees two fingers must turn before the map turns with them

// The marker under the cursor. First what the pointer is ON (inside a marker): among those, by layer - an item lying on
// its container, a player by a chest: loot > quest points / givers > pawns > area objectives > objects - then the last
// drawn (the visible one). Only when it's on none: the nearest centre within `radius` (the layer a tie-break). (The
// layer used to come first: a pickup 10 px away beat the chest right under the pointer - the user saw clicks land
// "below" what they aimed at.) A quest giver's "!" and a point objective (drawn over the NPC they're on) before the
// pawns: their panel links the NPC; an area objective (a big circle) after them. The panel's Nearby list (detail.js)
// reaches the others stacked there.
const HIT_LAYER = { loot: 4, directive: 3.5, point: 3.5, me: 3, player: 3, enemy: 3, npc: 3, vehicle: 3, objective: 2 };
export function hitAt(x, y, radius) {
  let best = null, bestKey = null;
  S.hits.forEach((h, order) => {
    const d = Math.hypot(h.sx - x, h.sy - y);
    if (d >= radius) return;
    const inside = d <= (h.r || 4) + 1.5;
    const kind = h.kind === "objective" && !h.item.rad ? "point" : h.kind;
    const layer = HIT_LAYER[kind] || 1;
    const key = inside ? [1, layer, order] : [0, -d, layer];
    if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] &&
        (key[1] > bestKey[1] || (key[1] === bestKey[1] && key[2] > bestKey[2])))) { best = h; bestKey = key; }
  });
  return best;
}

function clickAt(x, y) {
  const best = hitAt(x, y, 14);
  if (!best) return; // (the empty map: nothing - the drawer only closes with its own button)
  if (best.kind === "me" || best.kind === "player") openInspector(best.item.i);
  else openDetail(best.kind, best.item.i);
}

export function initInput() {
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015)));
  }, { passive: false });

  const pointers = new Map();
  let pinch = null;
  let downAt = null;
  let orbit = false; // a right-drag / Shift+drag turns the map (horizontal) and, tilted, tilts it (vertical)
  canvas.addEventListener("contextmenu", (e) => e.preventDefault()); // (the right button orbits)
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    if (!pointers.size) orbit = e.button === 2 || e.shiftKey;
    downAt = pointers.size || e.button === 2 ? null : { x: e.clientX, y: e.clientY, t: performance.now() };
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    canvas.classList.add("dragging");
    if (pointers.size === 2) { // two fingers: pinch zooms, a twist turns the map (past TWIST_START: not by accident)
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), zoom: S.view.zoom, angle: Math.atan2(b.y - a.y, b.x - a.x), twisting: false };
    }
  });
  canvas.addEventListener("pointermove", (e) => {
    S.mouse = { x: e.clientX, y: e.clientY };
    refreshTooltip(); // the tooltip / coordinates at once (at full speed: not capped by the Refresh rate)
    invalidate();
    const prev = pointers.get(e.pointerId);
    if (!prev) return;
    const cur = { x: e.clientX, y: e.clientY };
    pointers.set(e.pointerId, cur);
    if (pointers.size === 2 && pinch) {
      const [a, b] = [...pointers.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y), mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      zoomAt(mx, my, (pinch.zoom * d / pinch.d) / S.view.zoom);
      const angle = Math.atan2(b.y - a.y, b.x - a.x);
      const turn = (((angle - pinch.angle) * 180 / Math.PI) + 540) % 360 - 180; // degrees since the last step (or the start)
      if (!pinch.twisting && Math.abs(turn) > TWIST_START) { pinch.twisting = true; pinch.angle = angle; }
      else if (pinch.twisting) { spinAt(mx, my, -turn); pinch.angle = angle; } // (the map turns with the fingers: a larger spin turns it the other way)
      return;
    }
    if (pointers.size === 1 && orbit && (cur.x !== prev.x || cur.y !== prev.y)) {
      const v = settings.view;
      if (!(v.rotate && v.follow)) v.spin = (v.spin + (cur.x - prev.x) * 0.4) % 360; // (Rotate: the heading turns it)
      if (v.threeD) v.tilt3d = Math.min(80, Math.max(0, v.tilt3d - (cur.y - prev.y) * 0.3)); // (tilted only)
      saveSettings();
      invalidateNow(); // (the user orbiting: not capped by the Refresh rate)
      return;
    }
    if (pointers.size === 1 && (cur.x !== prev.x || cur.y !== prev.y)) {
      stopFollow();
      const [dx, dy] = screenToMapDelta(cur.x - prev.x, cur.y - prev.y);
      S.view.cx -= dx;
      S.view.cy -= dy;
      invalidateNow(); // (the user dragging: not capped by the Refresh rate)
    }
  });
  const release = (e) => {
    if (e.type === "pointerup" && downAt && pointers.size === 1 &&
        Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) < 5 && performance.now() - downAt.t < 300) {
      clickAt(e.clientX, e.clientY); // a click: not a drag, not a hold
    }
    downAt = null;
    pointers.delete(e.pointerId);
    if (pointers.size < 2) pinch = null;
    if (!pointers.size) canvas.classList.remove("dragging");
  };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", release);
  canvas.addEventListener("pointerleave", () => { S.mouse = null; refreshTooltip(); invalidate(); });
  canvas.addEventListener("dblclick", (e) => zoomAt(e.clientX, e.clientY, 2));

  window.addEventListener("keydown", (e) => {
    // typing in a field (the mission search...) or a menu: not a shortcut
    if (["SELECT", "INPUT", "TEXTAREA"].includes(e.target.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    if (k === "escape") { closeInspector(); return; }
    if (k === "f") { $("follow").click(); }
    else if (k === "r") { $("rotate").click(); } // (only while following: greyed out otherwise)
    else if (k === "3") { $("threeD").click(); } // Tilt
    else if (k === "n") { resetSpin(); } // the map turned back (the compass)
    else if (k === "c") { $("coords-on").click(); } // Show coordinates
    else if (k === "0") { stopFollow(); fit(); }
    else if (k === "+" || k === "=") zoomAt(W / 2, H / 2, 1.25);
    else if (k === "-") zoomAt(W / 2, H / 2, 0.8);
  });
}
