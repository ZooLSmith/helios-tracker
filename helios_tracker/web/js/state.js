// The page's state (one object, S) and read-only queries on it. Modules change S directly, then
// call invalidate() (scheduler.js) for a redraw and the ui/ render functions for the HTML.
import { LAYERS } from "./model.js";
import { store } from "./store.js";

export const S = {
  level: null, images: [], // [{canvas, bounds}]
  pawns: new Map(), pickups: [], objects: [],
  meId: null, fallback: null, // map frame for areas without a tactical map
  interval: 100, lastState: 0, hz: 0, // hz: the game's updates per second (sent with each state)
  // rot: map rotation (rad, the target's heading); zoom kept across reloads
  view: { cx: 0, cy: 0, zoom: store.get("zoom", 1), rot: 0 }, fitted: false, zoomed: store.get("zoom", 0) > 0,
  follow: !!store.get("follow", false), labels: store.get("labels", false), height: store.get("height", true),
  rotate: store.get("rotate", false), target: store.get("target", "me"), // "me" (the host) or a player's name
  // Movement: 0 = only redraw on a change (markers jump), a number = interpolated at most that many
  // fps, "smooth" = every frame. The old checkbox ("smooth": true / false) carries over.
  motion: store.get("motion", store.get("smooth", true) ? "smooth" : 0),
  lastDraw: 0,
  pending: false, // a frame is requested
  minRarity: store.get("minRarity", 1),
  layers: Object.fromEntries(LAYERS.map((l) => [l.id, store.get("layer." + l.id, l.on)])),
  hits: [], mouse: null, counts: {},
  missions: { tracked: null, markers: [] },
  // inspect: the inspected player { id, name } (ids change when a level loads);
  // detail: a clicked map object { kind, id }
  players: [], inspect: null, detail: null,
  tab: store.get("tab", "gear"), expanded: new Set(), skillTab: null, // null: the tree with the most points
};

/** The level's transform, or a fallback centred where we first saw the player. */
export function frame() {
  if (S.level && S.level.center) return S.level;
  return S.fallback;
}

/** Position, heading, shield and health, interpolated between the last two states. */
export function pawnPos(p, now) {
  if (!S.motion) return { x: p.x, y: p.y, z: p.z, r: p.r, h: p.h, s: p.s }; // "updates only": no interpolation
  const t = Math.min(1, (now - p.t0) / Math.max(16, S.interval));
  const lerp = (from, to) => (from === undefined || to === undefined ? to : from + (to - from) * t);
  let dr = (((p.r - p.fr) % 65536) + 98304) % 65536 - 32768; // shortest turn
  return { x: lerp(p.fx, p.x), y: lerp(p.fy, p.y), z: lerp(p.fz, p.z), r: p.fr + dr * t, h: lerp(p.fh, p.h), s: lerp(p.fs, p.s) };
}

/** The "Who" player's pawn (the host by default). */
export function targetPawn() {
  if (S.target === "me") return S.meId ? S.pawns.get(S.meId) : null;
  const player = S.players.find((p) => !p.local && p.n === S.target);
  return player ? S.pawns.get(player.i) : null;
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
