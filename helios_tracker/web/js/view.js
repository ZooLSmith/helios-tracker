// The canvas and the view: size, map px <-> screen px, zoom, fit, follow.
import { $ } from "./dom.js";
import { worldToMap } from "./geo.js";
import { invalidate } from "./scheduler.js";
import { saveSettings, settings } from "./settings.js";
import { S, frame, pawnPos, trackedPawn } from "./state.js";
import { syncRotate } from "./ui/panel.js";

export let canvas = null, ctx = null;
export let W = 0, H = 0, dpr = 1; // CSS px, device pixel ratio

export function initView() {
  canvas = $("map");
  ctx = canvas.getContext("2d");
  window.addEventListener("resize", resize);
  resize();
}

function resize() {
  dpr = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  invalidate();
}

// map px <-> screen px: screen = R(-rot) * (map - centre) * zoom + screen centre (canvas y-down:
// a positive angle turns clockwise); rot = the target's heading, so it points up
const rotate = (x, y, a) => { const c = Math.cos(a), s = Math.sin(a); return [x * c - y * s, x * s + y * c]; };
export const toScreen = (mx, my) => {
  const [x, y] = rotate(mx - S.view.cx, my - S.view.cy, -S.view.rot);
  return [x * S.view.zoom + W / 2, y * S.view.zoom + H / 2];
};
export const screenToMapDelta = (dx, dy) => rotate(dx / S.view.zoom, dy / S.view.zoom, S.view.rot);
export const toMap = (sx, sy) => {
  const [x, y] = screenToMapDelta(sx - W / 2, sy - H / 2);
  return [x + S.view.cx, y + S.view.cy];
};

function saveZoom() { settings.view.zoom = S.view.zoom; saveSettings(); } // remembered

export function fit(keepZoom = false) { // keepZoom: only re-centre (a level change keeps the zoom)
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const img of S.images) {
    const [a, b, c, d] = img.bounds;
    x0 = Math.min(x0, a); x1 = Math.max(x1, b); y0 = Math.min(y0, c); y1 = Math.max(y1, d);
  }
  if (!isFinite(x0)) { // no image: around the player
    const f = frame(), me = S.pawns.get(S.meId);
    if (!f || !me) return;
    const [mx, my] = worldToMap(f, me.x, me.y);
    x0 = mx - 60; x1 = mx + 60; y0 = my - 60; y1 = my + 60;
  }
  S.view.cx = (x0 + x1) / 2; S.view.cy = (y0 + y1) / 2;
  if (!keepZoom || !S.zoomed) { S.view.zoom = Math.min(W / (x1 - x0), H / (y1 - y0)) * 0.92; saveZoom(); }
  S.fitted = S.zoomed = true;
  invalidate();
}

export function centerOnTarget() {
  const f = frame(), target = trackedPawn(); // the "Who" player, else the host
  if (!f || !target) return;
  const p = pawnPos(target, performance.now());
  if (target.rs === 2) return; // respawning, the game doesn't say where: stay where we are
  [S.view.cx, S.view.cy] = worldToMap(f, p.x, p.y);
}

export function zoomAt(sx, sy, factor) {
  const [mx, my] = toMap(sx, sy);
  S.view.zoom = Math.min(80, Math.max(0.05, S.view.zoom * factor));
  saveZoom();
  invalidate();
  if (settings.view.follow) return; // zoom around the followed player
  const [dx, dy] = screenToMapDelta(sx - W / 2, sy - H / 2); // keep the point under the cursor
  S.view.cx = mx - dx;
  S.view.cy = my - dy;
}

export function stopFollow() {
  if (!settings.view.follow) return;
  settings.view.follow = false;
  $("follow").checked = false;
  saveSettings();
  syncRotate();
}
