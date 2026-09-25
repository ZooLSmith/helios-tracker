// The canvas and the view: size, map px <-> screen px, zoom, fit, follow.
import { $ } from "./dom.js";
import { largestFreeRect, mapTurn, worldToMap } from "./geo.js";
import { invalidate, invalidateNow } from "./scheduler.js";
import { saveSettings, settings } from "./settings.js";
import { S, frame, pawnPos, trackedPawn } from "./state.js";
import { syncRotate } from "./ui/panel.js";

export let canvas = null, ctx = null;
export let W = 0, H = 0, dpr = 1; // CSS px, device pixel ratio

// Following: the player goes at the centre of the largest part of the map no panel covers (the
// panel, the inspector), not the window's - where the most is seen around them. The panels' rects
// are measured when they change size (a ResizeObserver: opening / closing / collapsing), not per frame.
const OCCLUDERS = ["panel", "inspector"];
let freeCenter = null; // screen px, null = the window's centre
const followOffset = { x: 0, y: 0 }; // the player's screen offset from the centre, eased towards freeCenter's
const GLIDE_S = 0.15; // the ease's time constant (s): ~0.5 s to settle, whatever the frame rate
let lastGlide = 0;

export function initView() {
  canvas = $("map");
  ctx = canvas.getContext("2d");
  window.addEventListener("resize", resize);
  if (typeof ResizeObserver === "function") {
    const watch = new ResizeObserver(() => { measureFree(); invalidate(); });
    for (const id of OCCLUDERS) if ($(id)) watch.observe($(id));
  }
  resize();
}

function resize() {
  dpr = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
  measureFree();
  invalidate();
}

function measureFree() {
  const rects = [];
  for (const id of OCCLUDERS) {
    const el = $(id);
    if (!el) continue;
    const r = el.getBoundingClientRect(); // (display: none: 0 x 0, ignored)
    if (r.width > 0 && r.height > 0) rects.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
  }
  const free = largestFreeRect(W, H, rects);
  freeCenter = { x: free.x + free.w / 2, y: free.y + free.h / 2 };
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
  const f = frame();
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const img of S.images) {
    const [a, b, c, d] = img.bounds;
    x0 = Math.min(x0, a); x1 = Math.max(x1, b); y0 = Math.min(y0, c); y1 = Math.max(y1, d);
  }
  if (!isFinite(x0)) { // no image: around the player
    const me = S.pawns.get(S.meId);
    if (!f || !me) return;
    const [mx, my] = worldToMap(f, me.x, me.y);
    x0 = mx - 60; x1 = mx + 60; y0 = my - 60; y1 = my + 60;
  }
  S.view.cx = (x0 + x1) / 2; S.view.cy = (y0 + y1) / 2;
  // the map's box as the view turns it (a level with a north offset: its map screen's turn, see mapTurn)
  const a = f ? mapTurn(f) : 0, c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
  const w = (x1 - x0) * c + (y1 - y0) * s, h = (x1 - x0) * s + (y1 - y0) * c;
  if (!keepZoom || !S.zoomed) { S.view.zoom = Math.min(W / w, H / h) * 0.92; saveZoom(); }
  S.fitted = S.zoomed = true;
  invalidate();
}

export function centerOnTarget() {
  const f = frame(), target = trackedPawn(); // the "Who" player, else the host
  if (!f || !target) return;
  const p = pawnPos(target, performance.now());
  if (target.rs === 2) return; // respawning, the game doesn't say where: stay where we are
  // Eased towards the free area's centre (a panel opening glides the map over, no jump), by time -
  // in the frames the Movement setting draws anyway (never asks for more): "updates only" jumps
  const goal = freeCenter ? { x: freeCenter.x - W / 2, y: freeCenter.y - H / 2 } : { x: 0, y: 0 };
  const now = performance.now(), dt = Math.min(0.5, (now - lastGlide) / 1000);
  lastGlide = now;
  const k = settings.view.motion ? 1 - Math.exp(-dt / GLIDE_S) : 1;
  followOffset.x += (goal.x - followOffset.x) * k;
  followOffset.y += (goal.y - followOffset.y) * k;
  if (Math.abs(goal.x - followOffset.x) < 0.5 && Math.abs(goal.y - followOffset.y) < 0.5) {
    followOffset.x = goal.x; followOffset.y = goal.y;
  }
  // The player at that screen offset: the view centre is that far from them (on the map, turned)
  const [mx, my] = worldToMap(f, p.x, p.y);
  const [dx, dy] = screenToMapDelta(followOffset.x, followOffset.y);
  S.view.cx = mx - dx; S.view.cy = my - dy;
}

export function zoomAt(sx, sy, factor) {
  const [mx, my] = toMap(sx, sy);
  S.view.zoom = Math.min(80, Math.max(0.05, S.view.zoom * factor));
  saveZoom();
  invalidateNow(); // (the user zooming: not capped by the Refresh rate)
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
