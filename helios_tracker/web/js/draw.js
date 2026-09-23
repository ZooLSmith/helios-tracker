// One frame: the map images, then the markers bottom to top (quest areas, objects, quest markers,
// loot, pawns); records what's where (S.hits) for hover / click, updates the layer counts.
import { UU_PER_METER, worldToMap, yawToAngle } from "./geo.js";
import { FLOOR_UU, LAYERS, LAYER_COLOR, chestTier, isGear, nameText, rarity } from "./model.js";
import { COLORS, arrow, bang, diamond, dot, label, square, triangle, vitalBars } from "./shapes.js";
import { S, frame, pawnPos, targetPawn } from "./state.js";
import { tooltip } from "./tooltip.js";
import { updatePlayerVitals } from "./ui/players.js";
import { H, W, centerOnTarget, ctx, dpr, fit, toScreen } from "./view.js";

function drawGrid(f) { // areas without a map: a 10 m grid so movement still reads (map transform set)
  const step = 10 * UU_PER_METER / f.upp; // map px
  if (step * S.view.zoom < 6) return;
  const r = Math.hypot(W, H) / 2 / S.view.zoom; // covers the screen whatever the rotation
  const x0 = Math.floor((S.view.cx - r) / step) * step, y0 = Math.floor((S.view.cy - r) / step) * step;
  ctx.strokeStyle = COLORS.grid;
  ctx.lineWidth = 1 / S.view.zoom;
  ctx.beginPath();
  for (let x = x0; x < S.view.cx + r; x += step) { ctx.moveTo(x, S.view.cy - r); ctx.lineTo(x, S.view.cy + r); }
  for (let y = y0; y < S.view.cy + r; y += step) { ctx.moveTo(S.view.cx - r, y); ctx.lineTo(S.view.cx + r, y); }
  ctx.stroke();
}

export function draw() {
  const now = performance.now();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = COLORS.bg;
  ctx.fillRect(0, 0, W, H);
  const f = frame();
  if (!f) return;
  if (!S.fitted && (S.images.length || S.meId)) fit(true); // first time: fits; after a level change: keeps the zoom
  if (S.follow) centerOnTarget();
  const target = S.rotate ? targetPawn() : null; // the map turns so their heading points up
  S.view.rot = target ? yawToAngle(f, pawnPos(target, now).r) : 0;

  // map images (and the grid), in movie px
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.translate(W / 2, H / 2); ctx.rotate(-S.view.rot); ctx.scale(S.view.zoom, S.view.zoom);
  ctx.translate(-S.view.cx, -S.view.cy);
  ctx.imageSmoothingEnabled = S.view.zoom < 4;
  for (const img of S.images) {
    const [x0, x1, y0, y1] = img.bounds;
    ctx.drawImage(img.canvas, x0, y0, x1 - x0, y1 - y0);
  }
  if (!S.images.length) drawGrid(f);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const me = S.meId && S.pawns.get(S.meId);
  // Distances / heights are relative to the "Who" player (the host by default)
  const ref = targetPawn() || me;
  const mePos = ref ? pawnPos(ref, now) : null;
  const objColor = LAYER_COLOR.objective;
  // quest areas ("somewhere in this circle"): under every marker
  if (S.layers.objective) {
    for (const mk of S.missions.markers) {
      if (!mk.rad) continue;
      const [sx, sy] = toScreen(...worldToMap(f, mk.x, mk.y));
      const r = mk.rad / f.upp * S.view.zoom;
      if (sx + r < 0 || sy + r < 0 || sx - r > W || sy - r > H) continue;
      ctx.globalAlpha = mk.tracked ? 1 : 0.5;
      ctx.beginPath(); ctx.arc(sx, sy, Math.max(r, 3), 0, Math.PI * 2);
      ctx.fillStyle = "rgba(124, 245, 138, 0.13)"; ctx.fill();
      ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; ctx.strokeStyle = objColor; ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.globalAlpha = 1;
  }
  const hits = [];
  const counts = Object.fromEntries(LAYERS.map((l) => [l.id, 0]));
  const place = (x, y) => toScreen(...worldToMap(f, x, y));
  const visible = (sx, sy) => sx > -20 && sy > -20 && sx < W + 20 && sy < H + 20;
  const floorAlpha = (z) => (S.height && mePos && Math.abs(z - mePos.z) > FLOOR_UU ? 0.4 : 1);

  // interactive objects
  // Below the level's mapped volume: fallen off the map (still a real actor): not shown
  const offMap = (z) => S.level && S.level.zmin != null && z < S.level.zmin;
  for (const o of S.objects) {
    if (offMap(o.z)) continue;
    counts[o.cat]++;
    if (!S.layers[o.cat]) continue;
    const [sx, sy] = place(o.x, o.y);
    if (!visible(sx, sy)) continue;
    ctx.globalAlpha = floorAlpha(o.z) * (o.cat === "looted" ? 0.55 : 1);
    // Containers (looted ones too, just dimmed): chests biggest, others by how many items they spawn
    const tier = chestTier(o);
    const size = o.cat === "other" ? 2.5 : tier === 2 ? 7 : tier === 1 ? 5.5 : o.slots ? 2.5 + Math.min(o.slots, 4) * 0.6 : 3.5;
    square(sx, sy, size, LAYER_COLOR[o.cat]);
    if (S.labels && o.cat !== "other") label(sx, sy, nameText(o), LAYER_COLOR[o.cat], o.raw);
    hits.push({ sx, sy, r: size, kind: o.cat, item: o });
  }
  // quest markers: point objectives, quest givers; areas are hit-tested at their centre too
  for (const mk of S.missions.markers) {
    counts.objective++;
    if (!S.layers.objective) continue;
    const [sx, sy] = place(mk.x, mk.y);
    if (!visible(sx, sy)) continue;
    ctx.globalAlpha = mk.tracked ? 1 : 0.55;
    if (mk.k === "directive") bang(sx, sy, objColor);
    else if (!mk.rad) { diamond(sx, sy, 10, objColor); ctx.beginPath(); ctx.arc(sx, sy, 3, 0, Math.PI * 2); ctx.fillStyle = "#1a1200"; ctx.fill(); }
    if (S.labels && mk.objective) label(sx, sy, nameText(mk.objective), objColor, mk.objective.raw);
    hits.push({ sx, sy, r: mk.k === "directive" || mk.rad ? 7 : 10, kind: mk.k, item: mk });
  }
  ctx.globalAlpha = 1;
  // loot
  for (const p of S.pickups) {
    if (offMap(p.z)) continue;
    const tier = p.q || 0;
    // The rarity filter is for gear; other pickups (cash, ammo...: fake rarity levels) only with the
    // first two options
    if (isGear(p.c) ? tier < S.minRarity && !(S.minRarity === 1 && tier === 0) : S.minRarity > 1) continue;
    counts.loot++;
    if (!S.layers.loot) continue;
    const [sx, sy] = place(p.x, p.y);
    if (!visible(sx, sy)) continue;
    const [, color] = rarity(tier);
    ctx.globalAlpha = floorAlpha(p.z);
    if (isGear(p.c)) triangle(sx, sy, tier >= 5 ? 6.5 : 5, color);
    else dot(sx, sy, 3.5, LAYER_COLOR.loot); // not gear (ammo, cash, ECHO logs...): no rarity colour
    if (S.labels) label(sx, sy, nameText(p), color, p.raw);
    hits.push({ sx, sy, r: 6, kind: "loot", item: p });
  }
  // pawns, players on top
  const order = { npc: 0, enemy: 1, vehicle: 2, player: 3, me: 4 };
  const pawns = [...S.pawns.values()].sort((a, b) => order[a.k] - order[b.k]);
  for (const p of pawns) {
    const layer = p.k === "me" ? "player" : p.k;
    if (p.k !== "me") counts[layer] = (counts[layer] || 0) + 1;
    if (p.k !== "me" && !S.layers[layer]) continue;
    const pos = pawnPos(p, now);
    const [sx, sy] = place(pos.x, pos.y);
    if (!visible(sx, sy) && p.k !== "me") continue;
    ctx.globalAlpha = p.k === "me" ? 1 : floorAlpha(pos.z);
    const angle = yawToAngle(f, pos.r) - S.view.rot;
    if (p.k === "me" || p.k === "player") {
      if (p.k === "me") arrow(sx, sy, angle, 9, "#ffcc33", "#1a1200");
      else { arrow(sx, sy, angle, 8, LAYER_COLOR.player, "#00131a"); label(sx, sy, nameText(p), LAYER_COLOR.player, p.raw); }
      if ((p.m > 0 && p.h < p.m) || (p.sm > 0 && p.s < p.sm)) vitalBars(sx, sy + 3, { ...p, h: pos.h, s: pos.s });
    }
    else if (p.k === "vehicle") square(sx, sy, 5, LAYER_COLOR.vehicle);
    else {
      if (p.k === "enemy") diamond(sx, sy, 5, LAYER_COLOR.enemy); // like the game's minimap
      else dot(sx, sy, 3.5, LAYER_COLOR[p.k]);
      if ((p.m > 0 && p.h < p.m) || (p.sm > 0 && p.s < p.sm)) vitalBars(sx, sy, { ...p, h: pos.h, s: pos.s });
      if (S.labels) label(sx, sy, nameText(p), LAYER_COLOR[p.k], p.raw);
    }
    hits.push({ sx, sy, r: 6, kind: p.k, item: p, pos });
  }
  ctx.globalAlpha = 1;
  S.hits = hits;

  for (const [id, n] of Object.entries(counts)) {
    const el = document.querySelector(`[data-count="${id}"]`);
    if (el && el.textContent !== String(n)) el.textContent = String(n);
  }
  tooltip(mePos, f);
  updatePlayerVitals(now); // with the frames: follows the Movement setting
}
