// Marker shapes and labels, in screen px on the canvas (view.js's ctx).
import { ctx } from "./view.js";

// Colours shared with the CSS (read once the stylesheets are in: initColors)
export const COLORS = {};
export function initColors() {
  const css = getComputedStyle(document.documentElement);
  for (const k of ["bg", "grid", "shield", "health", "dead", "menu"]) COLORS[k] = css.getPropertyValue("--" + k).trim();
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
  ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.75)"; ctx.stroke();
}

export function ring(x, y, r, color, k = 1) { // a hollow ring (NPCs): a dark outline under the colour, to read on any map
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.lineWidth = 2.4 * k; ctx.strokeStyle = "rgba(0,0,0,.6)"; ctx.stroke();
  ctx.lineWidth = 1.3 * k; ctx.strokeStyle = color; ctx.stroke();
}

export function diamond(x, y, r, fill) {
  ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.8)"; ctx.stroke();
}

export function bang(x, y, fill, k = 1) { // quest giver / turn-in: a "!" badge (k: size factor)
  ctx.beginPath(); ctx.arc(x, y, 7 * k, 0, Math.PI * 2);
  ctx.fillStyle = fill; ctx.fill(); ctx.lineWidth = 1.5; ctx.strokeStyle = "#1a1200"; ctx.stroke();
  ctx.fillStyle = "#1a1200"; ctx.font = `700 ${11 * k}px 'Segoe UI', system-ui, sans-serif`; ctx.textAlign = "center";
  ctx.fillText("!", x, y + 4 * k); ctx.textAlign = "left";
}

export function triangle(x, y, r, fill) { // loot
  ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r * 0.9, y + r * 0.7); ctx.lineTo(x - r * 0.9, y + r * 0.7); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill();
  ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.8)"; ctx.stroke();
}

export function square(x, y, r, fill) {
  ctx.fillStyle = fill; ctx.fillRect(x - r, y - r, 2 * r, 2 * r);
  ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.8)"; ctx.strokeRect(x - r, y - r, 2 * r, 2 * r);
}

// The global marker size (Settings: Map markers): the labels' font and offset follow it (set per frame)
let markerScale = 1;
export function setMarkerScale(s) { markerScale = s; }

export function label(x, y, text, color, raw) { // raw: a made-up name ending in " ?", the "?" drawn dimmer
  const main = raw ? text.slice(0, -2) : text, s = markerScale;
  ctx.font = `600 ${11 * s}px 'Segoe UI', system-ui, sans-serif`;
  x += 8 * s - 8; y += 4 * s - 4; // (the offsets below: 8 right, 4 down, at 100 %)
  ctx.lineWidth = 3; ctx.strokeStyle = "rgba(5,10,14,.9)"; ctx.fillStyle = color;
  ctx.strokeText(main, x + 8, y + 4); ctx.fillText(main, x + 8, y + 4);
  if (!raw) return;
  const alpha = ctx.globalAlpha, qx = x + 8 + ctx.measureText(main + " ").width;
  ctx.globalAlpha = alpha * 0.7;
  ctx.strokeText("?", qx, y + 4); ctx.fillText("?", qx, y + 4);
  ctx.globalAlpha = alpha;
}

export function respawnRing(x, y, r, color) { // a dashed ring around a player: respawning here, or crippled (red)
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.setLineDash([3, 3]); ctx.lineWidth = 1.5; ctx.strokeStyle = color; ctx.stroke(); ctx.setLineDash([]);
}

export function menuBadge(x, y, k = 1) { // a player in a menu: a "..." pill at the top right of their arrow
  const w = 13 * k, h = 7 * k, bx = x + 6 * k, by = y - 13 * k;
  ctx.beginPath(); ctx.roundRect(bx, by, w, h, h / 2);
  ctx.fillStyle = COLORS.menu; ctx.fill(); ctx.lineWidth = 1; ctx.strokeStyle = "rgba(0,0,0,.8)"; ctx.stroke();
  ctx.fillStyle = "#0b1116";
  for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(bx + w * (i + 1) / 4, by + h / 2, 1.1 * k, 0, Math.PI * 2); ctx.fill(); }
}

export function vitalBars(x, y, p, k = 1) { // health, and the shield above it when there is one (k: the marker's size)
  const w = 16 * k, bh = 2 * k, gap = 3 * k, clamp = (v) => Math.max(0, Math.min(1, v));
  const bars = [];
  if (p.sm > 0) bars.push([COLORS.shield, clamp(p.s / p.sm)]);
  if (p.m > 0) bars.push([COLORS.health, clamp(p.h / p.m)]);
  let top = y + 7 * k;
  ctx.fillStyle = "rgba(0,0,0,.7)"; ctx.fillRect(x - w / 2 - 1, top - 1, w + 2, bars.length * gap + 1);
  for (const [color, frac] of bars) {
    ctx.fillStyle = color; ctx.fillRect(x - w / 2, top, w * frac, bh);
    top += gap;
  }
}
