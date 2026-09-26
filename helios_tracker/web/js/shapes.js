// Marker shapes and labels, in screen px on the canvas (view.js's ctx).
import { tokenColor, tokenRaw } from "./look.js";
import { setLayerColors } from "./model.js";
import { S } from "./state.js";
import { invalidate } from "./scheduler.js";
import { ctx } from "./view.js";

// Colours shared with the CSS (read once the stylesheets are in: initColors)
export const COLORS = {};
const TOKENS = { bg: "bg", grid: "grid", shield: "shield", health: "health", dead: "dead", menu: "menu", objective: "objective",
  tracked: "map-tracked", playerEdge: "map-player-edge", outline: "map-outline", outlineSoft: "map-outline-soft",
  ink: "map-ink", halo: "map-halo", barBack: "map-bar-back" };
export function initColors() {
  for (const [k, token] of Object.entries(TOKENS)) COLORS[k] = tokenColor("--" + token);
  COLORS.mapFilter = tokenRaw("--map-filter") || "none"; // (the theme's map tint: draw.js mapCanvas)
  setLayerColors(tokenColor);
}

export function arrow(x, y, angle, size, fill, stroke) {
  ctx.save();
  ctx.translate(x, y); ctx.rotate(angle);
  ctx.beginPath();
  ctx.moveTo(0, -size); ctx.lineTo(size * 0.72, size * 0.8); ctx.lineTo(0, size * 0.38); ctx.lineTo(-size * 0.72, size * 0.8);
  ctx.closePath();
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 1.5; ctx.strokeStyle = stroke; ctx.stroke();
  ctx.restore();
}

export function dot(x, y, r, fill) {
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 1; ctx.strokeStyle = COLORS.outline; ctx.stroke();
}

export function ring(x, y, r, color, k = 1) { // a hollow ring (NPCs): a dark outline under the colour, to read on any map
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.lineWidth = 2.4 * k; ctx.strokeStyle = COLORS.outlineSoft; ctx.stroke();
  ctx.lineWidth = 1.3 * k; ctx.strokeStyle = color; ctx.stroke();
}

export function diamond(x, y, r, fill) {
  ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 1; ctx.strokeStyle = COLORS.outline; ctx.stroke();
}

export function bang(x, y, fill, k = 1) { // quest giver / turn-in: a "!" badge (k: size factor)
  ctx.beginPath(); ctx.arc(x, y, 7 * k, 0, Math.PI * 2);
  ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = 1.5; ctx.strokeStyle = COLORS.ink; ctx.stroke();
  ctx.fillStyle = COLORS.ink; ctx.font = `700 ${11 * k}px 'Segoe UI', system-ui, sans-serif`; ctx.textAlign = "center";
  ctx.fillText("!", x, y + 4 * k); ctx.textAlign = "left";
}

export function coin(x, y, fill, k = 1) { // cash: a disc with a dark "$" (the "!" badge's look, smaller)
  ctx.save();
  ctx.beginPath(); ctx.arc(x, y, 5.5 * k, 0, Math.PI * 2);
  ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = 1.2; ctx.strokeStyle = COLORS.ink; ctx.stroke();
  ctx.fillStyle = COLORS.ink; ctx.font = `700 ${9 * k}px 'Segoe UI', system-ui, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText("$", x, y + 0.5 * k);
  ctx.restore();
}

export function burst(x, y, fill, k = 1) { // what explodes (a barrel): a 6-spike burst in its element's colour
  const outer = 7.5 * k, inner = 3.8 * k;
  ctx.save();
  ctx.beginPath();
  for (let i = 0; i < 12; i++) {
    const r = i % 2 ? inner : outer, a = -Math.PI / 2 + i * Math.PI / 6;
    const px = x + r * Math.cos(a), py = y + r * Math.sin(a);
    if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
  }
  ctx.closePath();
  ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = 1.2; ctx.lineJoin = "round"; ctx.strokeStyle = COLORS.ink; ctx.stroke();
  ctx.restore();
}

export function jumpMark(x, y, fill, k = 1) { // a jump pad (the Pre-Sequel's): a disc with a white up chevron
  const r = 7 * k;
  ctx.save();
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = 1.2; ctx.strokeStyle = COLORS.ink; ctx.stroke();
  ctx.beginPath(); ctx.moveTo(x - 3.6 * k, y + 1.8 * k); ctx.lineTo(x, y - 2.4 * k); ctx.lineTo(x + 3.6 * k, y + 1.8 * k);
  ctx.lineWidth = 2 * k; ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.strokeStyle = "#fff"; ctx.stroke();
  ctx.restore();
}

export function oxygenMark(x, y, fill, k = 1) { // an oxygen source (the Pre-Sequel's): a diamond with a white "O2"
  const r = 9 * k;
  ctx.save();
  ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = 1.2; ctx.strokeStyle = COLORS.ink; ctx.stroke();
  ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.font = `700 ${8.5 * k}px 'Segoe UI', system-ui, sans-serif`;
  ctx.fillText("O", x - 1.4 * k, y + 0.4 * k);
  ctx.font = `700 ${5.5 * k}px 'Segoe UI', system-ui, sans-serif`; // (the 2: a subscript)
  ctx.fillText("2", x + 3.6 * k, y + 2.5 * k);
  ctx.restore();
}

// The game's icons on the map, loaded once each (asked for only once the server can find them - its "assets" event:
// the game's files indexed... before, a 404; then a missing one is missing: the caller's own marker)
const images = new Map(); // url -> {img, ok: true loaded / false loading / null none}
function gameImage(url, ready) {
  if (!ready) return null;
  let entry = images.get(url);
  if (!entry) {
    const img = new Image();
    entry = { img, ok: false };
    img.crossOrigin = "anonymous";
    img.onload = () => { entry.ok = true; invalidate(); };
    img.onerror = () => { entry.ok = null; };
    img.src = url;
    images.set(url, entry);
  }
  return entry.ok ? entry.img : null;
}

// Gear's type icons (the game's item card art: /cardicon/type/<key>.png, gamecards.py), tinted per colour: its white
// fill multiplied into the rarity's colour, its black outline kept (the card's own look)
const tintedIcons = new Map(); // "key|colour" -> a canvas
function typeIconImage(key) {
  return gameImage(`/cardicon/type/${encodeURIComponent(key)}.png`, S.assets.cards);
}
function tintedIcon(key, color) {
  const img = typeIconImage(key);
  if (!img) return null;
  const id = key + "|" + color;
  let c = tintedIcons.get(id);
  if (!c) {
    if (tintedIcons.size > 300) tintedIcons.clear(); // (effervescent's colour cycles: no endless cache)
    c = document.createElement("canvas");
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    const g = c.getContext("2d");
    g.drawImage(img, 0, 0);
    g.globalCompositeOperation = "multiply"; g.fillStyle = color; g.fillRect(0, 0, c.width, c.height);
    g.globalCompositeOperation = "destination-in"; g.drawImage(img, 0, 0); // (its own shape: no colour around it)
    tintedIcons.set(id, c);
  }
  return c;
}

/** Gear on the ground as its item card's type icon (a rifle, a shield...) in its rarity's colour, `h` px high (wide ones
 *  capped); false (nothing drawn) until the icon's loaded / if the game has none - the caller draws its triangle. */
export function typeIcon(x, y, key, color, h) {
  if (!key || !/^[A-Za-z0-9_]+$/.test(key)) return false;
  const c = tintedIcon(key, color);
  if (!c || !c.width || !c.height) return false;
  const w = Math.min(h * c.width / c.height, h * 2.4), hh = w * c.height / c.width;
  ctx.drawImage(c, x - w / 2, y - hh / 2, w, hh);
  return true;
}

export function triangle(x, y, r, fill) { // loot
  ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r * 0.9, y + r * 0.7); ctx.lineTo(x - r * 0.9, y + r * 0.7); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 1; ctx.strokeStyle = COLORS.outline; ctx.stroke();
}

export function square(x, y, r, fill) {
  ctx.fillStyle = fill; ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
  ctx.lineWidth = 1; ctx.strokeStyle = COLORS.outline; ctx.strokeRect(x - r, y - r, 2 * r, 2 * r);
}

/** A chest (the big ones, the weapon chests): a wide box, its lid a line near the top, a latch on it - `r` its half
 *  height, like square()'s. */
export function chest(x, y, r, fill) {
  const w = r * 1.35, top = y - r, lid = y - r * 0.3;
  ctx.fillStyle = fill; ctx.fillRect(x - w, top, 2 * w, 2 * r);
  ctx.lineWidth = 1; ctx.strokeStyle = COLORS.outline; ctx.strokeRect(x - w, top, 2 * w, 2 * r);
  ctx.beginPath(); ctx.moveTo(x - w, lid); ctx.lineTo(x + w, lid); ctx.strokeStyle = COLORS.ink; ctx.lineWidth = 1; ctx.stroke();
  ctx.beginPath(); ctx.arc(x, lid, Math.max(1.1, r * 0.22), 0, Math.PI * 2); ctx.fillStyle = COLORS.ink; ctx.fill();
}

// The global marker size (Settings: Map markers): the labels' font and offset follow it (set per frame)
let markerScale = 1;
export function setMarkerScale(s) { markerScale = s; }

// raw: a made-up name ending in " ?", the "?" drawn dimmer; k: its layer's Name size (the text only: it stays by
// its marker)
export function label(x, y, text, color, raw, k = 1) {
  const main = raw ? text.slice(0, -2) : text, s = markerScale;
  ctx.font = `600 ${11 * s * k}px 'Segoe UI', system-ui, sans-serif`;
  x += 8 * s - 8; y += 4 * s - 4 + (k - 1) * 4 * s; // (the offsets below: 8 right, 4 down, at 100 %; bigger text: lower)
  ctx.lineWidth = 3 * Math.max(0.6, k); ctx.strokeStyle = COLORS.halo; ctx.fillStyle = color;
  ctx.strokeText(main, x + 8, y + 4); ctx.fillText(main, x + 8, y + 4);
  if (!raw) return;
  const alpha = ctx.globalAlpha, qx = x + 8 + ctx.measureText(main + " ").width;
  ctx.globalAlpha = alpha * 0.7;
  ctx.strokeText("?", qx, y + 4); ctx.fillText("?", qx, y + 4);
  ctx.globalAlpha = alpha;
}

export function areaName(x, y, text, color, k = 1) { // an area's name, centred on it (the map screen's style)
  ctx.font = `600 ${13 * k}px 'Segoe UI', system-ui, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.lineWidth = 3.5 * k; ctx.lineJoin = "round"; ctx.strokeStyle = COLORS.halo; ctx.fillStyle = color;
  ctx.strokeText(text, x, y); ctx.fillText(text, x, y);
  ctx.textAlign = "start"; ctx.textBaseline = "alphabetic"; ctx.lineJoin = "miter";
}

/** The selected marker (its panel open): four corner brackets around it, half-size `s` - no marker uses brackets, so
 *  it reads at any zoom; a dark outline under the colour, like the rings. */
export function brackets(x, y, s, color, k = 1) {
  const arm = Math.max(3, s * 0.45);
  ctx.beginPath();
  for (const [dx, dy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) {
    const cx = x + dx * s, cy = y + dy * s;
    ctx.moveTo(cx - dx * arm, cy); ctx.lineTo(cx, cy); ctx.lineTo(cx, cy - dy * arm);
  }
  ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.lineWidth = 3.4 * k; ctx.strokeStyle = COLORS.outlineSoft; ctx.stroke();
  ctx.lineWidth = 1.7 * k; ctx.strokeStyle = color; ctx.stroke();
  ctx.lineCap = "butt"; ctx.lineJoin = "miter";
}

/** A dashed line from (x0, y0) to (x1, y1), stopping `gap0` / `gap1` px short of each end (their markers stay clear):
 *  from the tracked player to the selected marker. Nothing when they're too close. */
export function leader(x0, y0, x1, y1, gap0, gap1, color, k = 1) {
  const d = Math.hypot(x1 - x0, y1 - y0);
  if (d <= gap0 + gap1 + 4) return;
  const ux = (x1 - x0) / d, uy = (y1 - y0) / d;
  ctx.beginPath(); ctx.moveTo(x0 + ux * gap0, y0 + uy * gap0); ctx.lineTo(x1 - ux * gap1, y1 - uy * gap1);
  ctx.setLineDash([5 * k, 4 * k]);
  ctx.lineWidth = 3 * k; ctx.strokeStyle = COLORS.outlineSoft; ctx.stroke();
  ctx.lineWidth = 1.4 * k; ctx.strokeStyle = color; ctx.stroke();
  ctx.setLineDash([]);
}

export function respawnRing(x, y, r, color) { // a dashed ring around a player: respawning here, or crippled (red)
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.setLineDash([3, 3]); ctx.lineWidth = 1.5; ctx.strokeStyle = color; ctx.stroke(); ctx.setLineDash([]);
}

export function menuBadge(x, y, k = 1) { // a player in a menu: a "..." pill at the top right of their arrow
  const w = 13 * k, h = 7 * k, bx = x + 6 * k, by = y - 13 * k;
  ctx.beginPath(); ctx.roundRect(bx, by, w, h, h / 2);
  ctx.fillStyle = COLORS.menu; ctx.fill(); ctx.lineWidth = 1; ctx.strokeStyle = COLORS.outline; ctx.stroke();
  ctx.fillStyle = COLORS.bg;
  for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(bx + w * (i + 1) / 4, by + h / 2, 1.1 * k, 0, Math.PI * 2); ctx.fill(); }
}

export function vitalBars(x, y, p, k = 1) { // health, and the shield above it when there is one (k: the marker's size)
  const w = 16 * k, bh = 2 * k, gap = 3 * k, clamp = (v) => Math.max(0, Math.min(1, v));
  const bars = [];
  if (p.sm > 0) bars.push([COLORS.shield, clamp(p.s / p.sm)]);
  if (p.m > 0) bars.push([COLORS.health, clamp(p.h / p.m)]);
  let top = y + 7 * k;
  ctx.fillStyle = COLORS.barBack; ctx.fillRect(x - w / 2 - 1, top - 1, w + 2, bars.length * gap + 1);
  for (const [color, frac] of bars) {
    ctx.fillStyle = color; ctx.fillRect(x - w / 2, top, w * frac, bh);
    top += gap;
  }
}
