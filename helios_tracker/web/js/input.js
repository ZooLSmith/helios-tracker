// Mouse / touch / keyboard on the map: wheel and pinch zoom, drag pan, hover, click, shortcuts.
import { $ } from "./dom.js";
import { invalidate, invalidateNow } from "./scheduler.js";
import { refreshTooltip } from "./tooltip.js";
import { S } from "./state.js";
import { openDetail } from "./ui/detail.js";
import { closeInspector, openInspector } from "./ui/inspector.js";
import { H, W, canvas, fit, screenToMapDelta, stopFollow, zoomAt } from "./view.js";

// The marker under the cursor: the one drawn on top wins (an item lying on its container, a player
// next to a chest...), the nearest among those. Drawn bottom to top: objects, quest markers,
// loot, pawns - pawns are small, loot is what you look for: loot first. A quest giver's "!" and a point
// objective (drawn over the NPC they're on) before the pawns: their panel links the NPC; an area
// objective (a big circle) after them.
const HIT_LAYER = { loot: 4, directive: 3.5, point: 3.5, me: 3, player: 3, enemy: 3, npc: 3, vehicle: 3, objective: 2 };
export function hitAt(x, y, radius) {
  // Rank: the layer (loot > pawns > quest markers > objects), then being inside the marker - the
  // last drawn of those, i.e. the visible one - then the nearest centre
  let best = null, bestKey = null;
  S.hits.forEach((h, order) => {
    const d = Math.hypot(h.sx - x, h.sy - y);
    if (d >= radius) return;
    const inside = d <= (h.r || 4) + 1.5;
    const kind = h.kind === "objective" && !h.item.rad ? "point" : h.kind;
    const key = [HIT_LAYER[kind] || 1, inside ? 1 : 0, inside ? order : -d];
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
  canvas.addEventListener("pointerdown", (e) => {
    canvas.setPointerCapture(e.pointerId);
    downAt = pointers.size ? null : { x: e.clientX, y: e.clientY, t: performance.now() };
    pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    canvas.classList.add("dragging");
    if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), zoom: S.view.zoom };
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
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2, (pinch.zoom * d / pinch.d) / S.view.zoom);
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
    else if (k === "c") { $("coords-on").click(); } // Show coordinates
    else if (k === "0") { stopFollow(); fit(); }
    else if (k === "+" || k === "=") zoomAt(W / 2, H / 2, 1.25);
    else if (k === "-") zoomAt(W / 2, H / 2, 0.8);
  });
}
