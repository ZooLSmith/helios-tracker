// One frame: the map images, then the markers bottom to top (quest areas, objects, quest markers,
// loot, pawns), each styled by its layer's settings; records what's where (S.hits) for hover /
// click, updates the layer counts.
import { UU_PER_METER, worldToMap, yawToAngle } from "./geo.js";
import { FLOOR_UU, LAYERS, LAYER_COLOR, chestTier, isGear, lootLayer, nameText, rarity } from "./model.js";
import { settings } from "./settings.js";
import { COLORS, arrow, bang, diamond, dot, label, square, triangle, vitalBars } from "./shapes.js";
import { S, frame, pawnPos, trackedPawn } from "./state.js";
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
  if (settings.view.follow) centerOnTarget();
  const tracked = trackedPawn();
  // Rotate: only while following - the map turns so their heading points up
  const target = settings.view.rotate && settings.view.follow ? tracked : null;
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

  // Distances / heights are relative to the tracked player (the host by default)
  const mePos = tracked ? pawnPos(tracked, now) : null;
  const L = settings.layers;
  const counts = Object.fromEntries(LAYERS.map((l) => [l.id, 0]));
  // How a marker of layer `id` at `pos` shows: null = not at all (out of range, hidden on another
  // floor, layer off), else its alpha, size factor and whether its name shows. Counted in the
  // layer's count when it passes the layer's filters (whether the layer is on or not).
  const style = (id, pos, count = true) => {
    const cfg = L[id];
    if (cfg.range && mePos && Math.hypot(pos.x - mePos.x, pos.y - mePos.y, pos.z - mePos.z) > cfg.range * UU_PER_METER) return null;
    const otherFloor = !!mePos && Math.abs(pos.z - mePos.z) > FLOOR_UU;
    if (otherFloor && cfg.floors === "hide") return null;
    if (count) counts[id]++;
    if (cfg.on === false) return null;
    return { alpha: otherFloor && cfg.floors === "dim" ? 0.4 : 1, k: (cfg.size ?? 100) / 100, names: !!cfg.names };
  };
  const questShown = (mk) => mk.tracked || !L.objective.trackedOnly;
  const objColor = LAYER_COLOR.objective;
  // quest areas ("somewhere in this circle"): under every marker
  for (const mk of S.missions.markers) {
    if (!mk.rad || !questShown(mk)) continue;
    const st = style("objective", mk, false);
    if (!st) continue;
    const [sx, sy] = toScreen(...worldToMap(f, mk.x, mk.y));
    const r = mk.rad / f.upp * S.view.zoom;
    if (sx + r < 0 || sy + r < 0 || sx - r > W || sy - r > H) continue;
    ctx.globalAlpha = (mk.tracked ? 1 : 0.5) * st.alpha;
    ctx.beginPath(); ctx.arc(sx, sy, Math.max(r, 3), 0, Math.PI * 2);
    ctx.fillStyle = "rgba(124, 245, 138, 0.13)"; ctx.fill();
    ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; ctx.strokeStyle = objColor; ctx.stroke(); ctx.setLineDash([]);
  }
  ctx.globalAlpha = 1;
  const hits = [];
  const place = (x, y) => toScreen(...worldToMap(f, x, y));
  const visible = (sx, sy) => sx > -20 && sy > -20 && sx < W + 20 && sy < H + 20;

  // interactive objects
  // Below the level's mapped volume: fallen off the map (still a real actor): not shown
  const offMap = (z) => S.level && S.level.zmin != null && z < S.level.zmin;
  for (const o of S.objects) {
    if (offMap(o.z)) continue;
    const st = style(o.cat, o);
    if (!st) continue;
    const [sx, sy] = place(o.x, o.y);
    if (!visible(sx, sy)) continue;
    ctx.globalAlpha = st.alpha * (o.cat === "looted" ? 0.55 : 1);
    // Containers (looted ones too, just dimmed): chests biggest, others by how many items they spawn
    const tier = chestTier(o);
    const size = st.k * (o.cat === "other" ? 2.5 : tier === 2 ? 7 : tier === 1 ? 5.5 : o.slots ? 2.5 + Math.min(o.slots, 4) * 0.6 : 3.5);
    square(sx, sy, size, LAYER_COLOR[o.cat]);
    if (st.names) label(sx, sy, nameText(o), LAYER_COLOR[o.cat], o.raw);
    hits.push({ sx, sy, r: size, kind: o.cat, item: o });
  }
  // quest markers: point objectives, quest givers; areas are hit-tested at their centre too
  for (const mk of S.missions.markers) {
    if (!questShown(mk)) continue;
    const st = style("objective", mk);
    if (!st) continue;
    const [sx, sy] = place(mk.x, mk.y);
    if (!visible(sx, sy)) continue;
    ctx.globalAlpha = (mk.tracked ? 1 : 0.55) * st.alpha;
    if (mk.k === "directive") bang(sx, sy, objColor, st.k);
    else if (!mk.rad) { diamond(sx, sy, 10 * st.k, objColor); ctx.beginPath(); ctx.arc(sx, sy, 3 * st.k, 0, Math.PI * 2); ctx.fillStyle = "#1a1200"; ctx.fill(); }
    if (st.names && mk.objective) label(sx, sy, nameText(mk.objective), objColor, mk.objective.raw);
    hits.push({ sx, sy, r: (mk.k === "directive" || mk.rad ? 7 : 10) * st.k, kind: mk.k, item: mk });
  }
  ctx.globalAlpha = 1;
  // loot: styled by its rarity's layer (gear), or the pickups' (ammo, cash...)
  for (const p of S.pickups) {
    if (offMap(p.z)) continue;
    const layer = lootLayer(p), st = style(layer, p);
    if (!st) continue;
    const [sx, sy] = place(p.x, p.y);
    if (!visible(sx, sy)) continue;
    const tier = p.q || 0;
    const [, color] = rarity(tier);
    ctx.globalAlpha = st.alpha;
    if (isGear(p.c)) triangle(sx, sy, (tier >= 5 ? 6.5 : 5) * st.k, color);
    else dot(sx, sy, 3.5 * st.k, LAYER_COLOR[layer]); // not gear (ammo, cash...): its kind's colour, no rarity
    if (st.names) label(sx, sy, nameText(p), isGear(p.c) ? color : LAYER_COLOR[layer], p.raw);
    hits.push({ sx, sy, r: 6 * st.k, kind: "loot", item: p });
  }
  // pawns: players on top, the tracked one last
  const order = { npc: 0, enemy: 1, vehicle: 2, player: 3, me: 3 };
  const rank = (p) => (p === tracked ? 4 : order[p.k]);
  const pawns = [...S.pawns.values()].sort((a, b) => rank(a) - rank(b));
  for (const p of pawns) {
    const pos = pawnPos(p, now);
    const isPlayer = p.k === "me" || p.k === "player", layer = isPlayer ? "player" : p.k; // the host is one of the players
    const st = style(layer, pos);
    if (!st) continue;
    const [sx, sy] = place(pos.x, pos.y);
    if (!visible(sx, sy) && p !== tracked) continue;
    ctx.globalAlpha = st.alpha;
    const angle = yawToAngle(f, pos.r) - S.view.rot;
    const hurt = (p.m > 0 && p.h < p.m) || (p.sm > 0 && p.s < p.sm);
    if (isPlayer) { // the tracked player: the yellow arrow; the others white
      if (p === tracked) arrow(sx, sy, angle, 9 * st.k, "#ffcc33", "#1a1200");
      else arrow(sx, sy, angle, 8 * st.k, LAYER_COLOR.player, "#00131a");
      if (hurt) vitalBars(sx, sy + 3 * st.k, { ...p, h: pos.h, s: pos.s });
    }
    else if (p.k === "vehicle") square(sx, sy, 5 * st.k, LAYER_COLOR.vehicle);
    else {
      if (p.k === "enemy") diamond(sx, sy, 5 * st.k, LAYER_COLOR.enemy); // like the game's minimap
      else dot(sx, sy, 3.5 * st.k, LAYER_COLOR[p.k]);
      if (hurt) vitalBars(sx, sy, { ...p, h: pos.h, s: pos.s });
    }
    if (st.names) label(sx, sy, nameText(p), p === tracked ? "#ffcc33" : LAYER_COLOR[layer], p.raw);
    hits.push({ sx, sy, r: 6 * st.k, kind: p.k, item: p, pos });
  }
  ctx.globalAlpha = 1;
  S.hits = hits;

  for (const l of LAYERS) if (l.parent) counts[l.parent] += counts[l.id]; // a folder: its layers' total

  for (const [id, n] of Object.entries(counts)) {
    const el = document.querySelector(`[data-count="${id}"]`);
    if (el && el.textContent !== String(n)) el.textContent = String(n);
  }
  tooltip(mePos, f);
  updatePlayerVitals(now); // with the frames: follows the Movement setting
}
