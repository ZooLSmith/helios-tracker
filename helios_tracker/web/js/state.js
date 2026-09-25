// The page's live state (one object, S) and read-only queries on it. Modules change S directly,
// then call invalidate() (scheduler.js) for a redraw and the ui/ render functions for the HTML.
// What's remembered across reloads is in settings.js, not here.
import { settings } from "./settings.js";

export const S = {
  level: null, images: [], // [{canvas, bounds}]
  pawns: new Map(), pickups: [], objects: [],
  areas: [], explored: false, // the level's discovery areas (names, fog of war: data.js onAreas), all of it explored
  fogBlob: null, // the game's fog of war piece: {canvas, bounds} (placed per area: S.level.fog.pieces)
  video: null, // a cutscene playing (a video / an in-engine one): {len (s, or null), at (epoch s), paused, pos (s), name} - data.js onCutscene
  fogSeen: null, // the fog pieces discovered (a Set of names; null: not known yet)
  meId: null, fallback: null, // map frame for areas without a tactical map
  interval: 100, lastState: 0, hz: 0, // hz: the game's updates per second (sent with each state)
  // rot: map rotation (rad, the target's heading); the zoom is kept across reloads
  view: { cx: 0, cy: 0, zoom: settings.view.zoom || 1, rot: 0 }, fitted: false, zoomed: settings.view.zoom > 0,
  lastDraw: 0,
  pending: false, // a frame is requested
  hits: [], mouse: null,
  missions: { tracked: null, markers: [] },
  log: null, // the mission log (every mission of the playthrough: not per level)
  // the drawer shows the log: { id, history } - id: a mission's details, null: the tree; history:
  // where Back goes ({ id, scroll }, the last one first)
  missionView: null,
  // the level's vending machines (shops.py): {client, machines: [{i, n, k, x, y, z, cur?, items, feat?}]}; the restock
  // timer: {left (s, when it came), rate, at (performance.now())}; the drawer shows them: { id } (a machine to show first)
  shops: null, shopTimer: null, shopView: null,
  // inspect: the inspected player { id, name } (ids change when a level loads);
  // detail: a clicked map object { kind, id }
  players: [], inspect: null, detail: null,
  expanded: new Set(), skillTab: null, // null: the tree with the most points
  itemFolds: new Set(), // an expanded item's open folds: "<item id>:parts" / "<item id>:details" (ui/items.js)
};

/** The level's transform, or a fallback centred where we first saw the player. */
export function frame() {
  if (S.level && S.level.center) return S.level;
  return S.fallback;
}

/** Position, heading, shield and health, interpolated between the last two states. */
export function pawnPos(p, now) {
  if (!settings.view.motion) return { x: p.x, y: p.y, z: p.z, r: p.r, h: p.h, s: p.s }; // "updates only": no interpolation
  const t = Math.min(1, (now - p.t0) / Math.max(16, S.interval));
  const lerp = (from, to) => (from === undefined || to === undefined ? to : from + (to - from) * t);
  let dr = (((p.r - p.fr) % 65536) + 98304) % 65536 - 32768; // shortest turn
  return { x: lerp(p.fx, p.x), y: lerp(p.fy, p.y), z: lerp(p.fz, p.z), r: p.fr + dr * t, h: lerp(p.fh, p.h), s: lerp(p.fs, p.s) };
}

/** The "Who" player's pawn (the host by default). */
export function targetPawn() {
  const target = settings.view.target;
  if (target === "me") return S.meId ? S.pawns.get(S.meId) : null;
  const player = S.players.find((p) => !p.local && p.n === target);
  return player ? S.pawns.get(player.i) : null;
}

/** The tracked player's pawn: the "Who" player, else the host (the yellow arrow, what distances,
 *  heights and follow / rotate are relative to). */
export function trackedPawn() {
  return targetPawn() || (S.meId ? S.pawns.get(S.meId) : null);
}

/** Whether a players-list entry is the tracked player (the host unless "Who" names one who's here). */
export function isTrackedPlayer(p) {
  const target = settings.view.target;
  const named = target !== "me" && S.players.some((q) => !q.local && q.n === target);
  return named ? !p.local && p.n === target : !!p.local;
}

/** The inspected player (by id, else by name: ids change when a level loads). */
export function findPlayer() {
  if (!S.inspect) return null;
  return S.players.find((p) => p.i === S.inspect.id) || S.players.find((p) => p.n === S.inspect.name) || null;
}

/** The clicked map object, if it's still there. */
export function findDetail() {
  const d = S.detail;
  if (!d) return null;
  if (d.kind === "loot") return S.pickups.find((p) => p.i === d.id);
  if (d.kind === "objective" || d.kind === "directive") return S.missions.markers.find((m) => m.i === d.id);
  return S.objects.find((o) => o.i === d.id) || S.pawns.get(d.id) || null;
}
