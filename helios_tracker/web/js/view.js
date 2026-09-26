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
let freeRect = null; // the largest part of the screen no panel covers (the compass sits in its bottom-right corner)
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
  freeRect = free;
}

// map px <-> screen px: screen = R(-rot) * (map - centre) * zoom + screen centre (canvas y-down:
// a positive angle turns clockwise); rot = the target's heading, so it points up. The 3D view tilts that plane
// (S.view.tilt, an orthographic camera): screen y squashed by cos(tilt), a height h (map px above the map's plane)
// lifting a point by h sin(tilt). toMap / screenToMapDelta stay on the plane (h = 0).
const rotate = (x, y, a) => { const c = Math.cos(a), s = Math.sin(a); return [x * c - y * s, x * s + y * c]; };
export const toScreen = (mx, my, h = 0) => {
  const [x, y] = rotate(mx - S.view.cx, my - S.view.cy, -S.view.rot);
  return [x * S.view.zoom + W / 2, (y * Math.cos(S.view.tilt) - h * Math.sin(S.view.tilt)) * S.view.zoom + H / 2];
};
export const screenToMapDelta = (dx, dy) => rotate(dx / S.view.zoom, dy / (S.view.zoom * Math.cos(S.view.tilt)), S.view.rot);
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
  // the map's box as the view turns it (a level with a north offset: its map screen's turn, see mapTurn; the 3D view's
  // spin) and tilts it (squashed by cos(tilt))
  const v = settings.view, a = (f ? mapTurn(f) : 0) + (!(v.rotate && v.follow) ? v.spin * Math.PI / 180 : 0);
  const c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
  const w = (x1 - x0) * c + (y1 - y0) * s, h = ((x1 - x0) * s + (y1 - y0) * c) * Math.cos(S.view.tilt);
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
  // The player at that screen offset: the view centre is that far from them (on the map, turned; in the 3D view their
  // marker is lifted by their height above the map's plane - the plane point under them sits that much lower)
  const [mx, my] = worldToMap(f, p.x, p.y);
  const lift = (p.z - S.view.ground) / f.upp * Math.sin(S.view.tilt) * S.view.zoom;
  const [dx, dy] = screenToMapDelta(followOffset.x, followOffset.y + lift);
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

// The compass (#north): shown while the user has turned the map (and the heading doesn't own the turn, and the drawer
// isn't open - on a phone it's a page over the map; beside it, pointless), its needle
// pointing north on screen, in the free area's bottom-right corner; a click / N turns the map back (resetSpin). Written
// only when something changed (it's called every frame).
let northShown = null;
export function refreshNorth() {
  const el = $("north");
  if (!el) return;
  const v = settings.view;
  const drawer = $("inspector");
  const show = !(v.rotate && v.follow) && Math.abs(((v.spin % 360) + 540) % 360 - 180) > 0.5 &&
    !(drawer && drawer.classList.contains("open"));
  if (!show) {
    if (northShown !== "") { el.hidden = true; northShown = ""; }
    return;
  }
  const r = freeRect || { x: 0, y: 0, w: W, h: H };
  const state = `${Math.round(r.x + r.w)},${Math.round(r.y + r.h)},${(-S.view.rot * 180 / Math.PI).toFixed(1)}`;
  if (state === northShown) return;
  northShown = state;
  el.hidden = false;
  el.style.left = `${Math.round(r.x + r.w - el.offsetWidth - 16)}px`;
  el.style.top = `${Math.round(r.y + r.h - el.offsetHeight - 16)}px`;
  el.firstElementChild.style.transform = `rotate(${(-S.view.rot * 180 / Math.PI).toFixed(1)}deg)`; // (map up = north: turned by -rot)
}

/** Turns the map by `deg` (the user's turn: settings.view.spin) around the screen point (sx, sy) - it stays under it (a
 *  two-finger twist). Not while the heading owns the turn (Follow + Rotate). */
export function spinAt(sx, sy, deg) {
  const v = settings.view;
  if (v.rotate && v.follow) return;
  spinBack = null;
  const [mx, my] = toMap(sx, sy);
  v.spin = (v.spin + deg) % 360;
  S.view.rot += deg * Math.PI / 180; // (now: the frame sets it from the spin again)
  if (!v.follow) { // the point under the fingers stays there
    const [nx, ny] = toMap(sx, sy);
    S.view.cx += mx - nx; S.view.cy += my - ny;
  }
  saveSettings();
  invalidateNow();
}

// Leaving Follow + Rotate: the heading's turn eased back to north around the player's point - they stay where they are
// on screen, the map turns under them. From the frames (draw.js, before the turn is set): at the Refresh rate; "updates
// only": at once. A turn of the user's meanwhile (a drag, a twist) ends it.
const SPIN_BACK_S = 0.08; // its time constant (s): settled in ~0.25 s
let spinBack = null; // {mx, my: the player's map point, last: the previous step's time}

export function easeSpinBack(f) {
  if (!spinBack) return;
  const v = settings.view;
  if (v.follow) { spinBack = null; return; }
  const now = performance.now(), dt = Math.min(0.5, (now - spinBack.last) / 1000);
  spinBack.last = now;
  const k = v.motion ? 1 - Math.exp(-dt / SPIN_BACK_S) : 1;
  const [x0, y0] = toScreen(spinBack.mx, spinBack.my);
  v.spin = Math.abs(v.spin * (1 - k)) < 0.2 ? 0 : v.spin * (1 - k);
  S.view.rot = mapTurn(f) + v.spin * Math.PI / 180;
  const [x1, y1] = toScreen(spinBack.mx, spinBack.my); // (turned: moved - the view follows it back)
  const [dx, dy] = screenToMapDelta(x1 - x0, y1 - y0);
  S.view.cx += dx; S.view.cy += dy;
  if (v.spin) invalidate();
  else { spinBack = null; saveSettings(); }
}

/** The user turns the map: the ease back to north (leaving Follow) stops where it is. */
export function cancelSpinBack() { spinBack = null; }

/** The map back to its usual orientation (the game's map screen's): the user's turn dropped. */
export function resetSpin() {
  settings.view.spin = 0;
  saveSettings();
  invalidateNow();
}

export function stopFollow() {
  if (!settings.view.follow) return;
  // Rotate was turning the map to their heading: it turns back north (the user's call) - around the player, eased
  // (easeSpinBack): dropped at once, the map swung around the screen's centre and the player (off-centre: the free
  // area's) was thrown aside with it (the user: "the camera jumps")
  const f = frame(), target = trackedPawn();
  if (settings.view.rotate && f) {
    const deg = (S.view.rot - mapTurn(f)) * 180 / Math.PI;
    settings.view.spin = ((deg % 360) + 540) % 360 - 180; // (where it is now, as a turn to undo)
    const p = target && target.rs !== 2 ? pawnPos(target, performance.now()) : null;
    if (p) {
      const [mx, my] = worldToMap(f, p.x, p.y);
      spinBack = { mx, my, last: performance.now() };
    } else settings.view.spin = 0;
  }
  settings.view.follow = false;
  $("follow").checked = false;
  saveSettings();
  syncRotate();
}
