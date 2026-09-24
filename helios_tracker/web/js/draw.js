// One frame: the map images, then the markers bottom to top (quest areas, objects, quest markers,
// loot, pawns), each styled by its layer's settings; records what's where (S.hits) for hover /
// click, updates the layer counts.
import { UU_PER_METER, worldToMap, yawToAngle } from "./geo.js";
import { FLOOR_UU, LAYERS, LAYER_COLOR, chestTier, isGear, lootLayer, nameText, rainbowAt, rarity } from "./model.js";
import { look, withAlpha } from "./look.js";
import { missionItemWanted } from "./missions.js";
import { settings } from "./settings.js";
import { COLORS, areaName, arrow, bang, diamond, dot, label, menuBadge, respawnRing, ring, setMarkerScale, square, triangle, vitalBars } from "./shapes.js";
import { S, frame, pawnPos, trackedPawn } from "./state.js";
import { tooltip } from "./tooltip.js";
import { refreshPlayerInfo } from "./ui/inspector.js";
import { updatePlayerVitals } from "./ui/players.js";
import { H, W, centerOnTarget, ctx, dpr, fit, toScreen } from "./view.js";

/** The mission log by mission id (mission items check their mission): rebuilt only when the log changes. */
let byIdFor = null, byIdMap = null;
function logById() {
  if (!S.log) return null;
  if (byIdFor !== S.log) { byIdFor = S.log; byIdMap = new Map(S.log.missions.map((m) => [m.i, m])); }
  return byIdMap;
}

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

// The fog of war, the game's (tools/dump_tacmap_movie.txt): its blob (a soft dark cloud) over every
// area not discovered yet, where the level's map movie places it (one per area, by its short name);
// the map screen hides an area's once it's discovered. Drawn in the map's transform (movie px), on a
// canvas of its own masked by the map images (the pieces reach past the map: only where it has pixels),
// then over the map. -> how many pieces are still fogged.
let fogCanvas = null;
function drawFog(lk, opacity) {
  const blob = S.fogBlob, pieces = S.level && S.level.fog ? S.level.fog.pieces : [];
  if (!blob || !pieces.length || S.explored || !S.fogSeen) return 0;
  const todo = pieces.filter(([name]) => !S.fogSeen.has(name));
  if (!todo.length) return 0;
  const w = Math.round(W * dpr), h = Math.round(H * dpr);
  if (!fogCanvas) fogCanvas = document.createElement("canvas");
  if (fogCanvas.width !== w || fogCanvas.height !== h) { fogCanvas.width = w; fogCanvas.height = h; }
  const fc = fogCanvas.getContext("2d"), m = ctx.getTransform(), [x0, x1, y0, y1] = blob.bounds;
  fc.globalCompositeOperation = "source-over";
  fc.setTransform(1, 0, 0, 1, 0, 0); fc.clearRect(0, 0, w, h);
  fc.imageSmoothingEnabled = true;
  for (const [, [a, b, c, d, e, g]] of todo) { // the pieces
    fc.setTransform(m.multiply(new DOMMatrix([a, b, c, d, e, g])));
    fc.drawImage(blob.canvas, x0, y0, x1 - x0, y1 - y0);
  }
  fc.globalCompositeOperation = "destination-in"; // kept only where the map is
  fc.setTransform(m);
  fc.imageSmoothingEnabled = ctx.imageSmoothingEnabled;
  for (const img of S.images) { const [ix0, ix1, iy0, iy1] = img.bounds; fc.drawImage(img.canvas, ix0, iy0, ix1 - ix0, iy1 - iy0); }
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = lk.map / 100 * opacity;
  ctx.drawImage(fogCanvas, 0, 0);
  ctx.restore();
  return todo.length;
}

export function draw() {
  const now = performance.now();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // the background around the map, as opaque as asked (0: none - an overlay, OBS shows through)
  const lk = look();
  const G = lk.marker / 100; // every marker's size (Settings: Map markers), on top of its layer's
  setMarkerScale(G); // the labels and bars too (shapes.js)
  ctx.clearRect(0, 0, W, H);
  if (lk.bg > 0) { ctx.fillStyle = withAlpha(COLORS.bg, lk.bg / 100); ctx.fillRect(0, 0, W, H); }
  const f = frame();
  if (!f) return;
  if (!S.fitted && (S.images.length || S.meId)) fit(true); // first time: fits; after a level change: keeps the zoom
  const tracked = trackedPawn();
  // Rotate: only while following - the map turns so their heading points up
  const target = settings.view.rotate && settings.view.follow ? tracked : null;
  S.view.rot = target ? yawToAngle(f, pawnPos(target, now).r) : 0;
  if (settings.view.follow) centerOnTarget(); // (after the rotation: the player's offset is on screen)

  // map images (and the grid), in movie px
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.translate(W / 2, H / 2); ctx.rotate(-S.view.rot); ctx.scale(S.view.zoom, S.view.zoom);
  ctx.translate(-S.view.cx, -S.view.cy);
  ctx.imageSmoothingEnabled = S.view.zoom < 4;
  ctx.globalAlpha = lk.map / 100; // the map image itself (cut out: transparent outside the level)
  for (const img of S.images) {
    const [x0, x1, y0, y1] = img.bounds;
    ctx.drawImage(img.canvas, x0, y0, x1 - x0, y1 - y0);
  }
  ctx.globalAlpha = 1;
  if (!S.images.length) drawGrid(f);
  const L = settings.layers;
  // (the areas payload first: before it, which areas are discovered isn't known - no fog rather than all)
  const fogLeft = L.fog.on !== false && S.images.length ? drawFog(lk, (L.fog.opacity ?? 100) / 100) : 0;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // Distances / heights are relative to the tracked player (the host by default)
  const mePos = tracked ? pawnPos(tracked, now) : null;
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
    return { alpha: otherFloor && cfg.floors === "dim" ? 0.4 : 1, k: (cfg.size ?? 100) / 100 * G, names: !!cfg.names };
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
    ctx.fillStyle = objColor; ctx.globalAlpha *= 0.13; ctx.fill(); ctx.globalAlpha /= 0.13;
    ctx.setLineDash([6, 4]); ctx.lineWidth = 1.5; ctx.strokeStyle = objColor; ctx.stroke(); ctx.setLineDash([]);
  }
  ctx.globalAlpha = 1;
  // the areas' names (the game's): under every marker, the ones not discovered yet dimmed
  for (const a of S.areas) {
    if (!a.n) continue; // fog of war only: no name
    counts.area++;
    if (L.area.on === false) continue;
    const [sx, sy] = toScreen(...worldToMap(f, a.x, a.y));
    if (sx < -200 || sy < -40 || sx > W + 200 || sy > H + 40) continue;
    ctx.globalAlpha = (a.u ? 0.95 : 0.45) * (L.area.opacity ?? 100) / 100;
    areaName(sx, sy, a.n, LAYER_COLOR.area, (L.area.size ?? 100) / 100 * G);
  }
  counts.fog = fogLeft;
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
    if (o.cat === "vaultsymbol") { // a ring and a dot: not a container (squares)
      ctx.beginPath(); ctx.arc(sx, sy, 4.5 * st.k, 0, Math.PI * 2);
      ctx.lineWidth = 2.5 * st.k; ctx.strokeStyle = COLORS.outline; ctx.stroke();
      ctx.lineWidth = 1.6 * st.k; ctx.strokeStyle = LAYER_COLOR[o.cat]; ctx.stroke();
      dot(sx, sy, 1.6 * st.k, LAYER_COLOR[o.cat]);
    } else square(sx, sy, size, LAYER_COLOR[o.cat]);
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
    else if (!mk.rad) { diamond(sx, sy, 10 * st.k, objColor); ctx.beginPath(); ctx.arc(sx, sy, 3 * st.k, 0, Math.PI * 2); ctx.fillStyle = COLORS.ink; ctx.fill(); }
    if (st.names && mk.objective) label(sx, sy, nameText(mk.objective), objColor, mk.objective.raw);
    hits.push({ sx, sy, r: (mk.k === "directive" || mk.rad ? 7 : 10) * st.k, kind: mk.k, item: mk });
  }
  ctx.globalAlpha = 1;
  // loot: styled by its rarity's layer (gear), or the pickups' (ammo, cash...)
  const byId = logById();
  for (const p of S.pickups) {
    if (p.ms && !missionItemWanted(p.ms, byId)) continue; // a mission item placed ahead (its step not reached / done)
    if (offMap(p.z)) continue;
    const layer = lootLayer(p), st = style(layer, p);
    if (!st) continue;
    const [sx, sy] = place(p.x, p.y);
    if (!visible(sx, sy)) continue;
    const tier = p.q || 0;
    const [tierName, tierColor] = rarity(tier);
    // effervescent: the game's rainbow, its hue from the clock (moves as frames are drawn, at the Refresh rate)
    const color = tierName === "effervescent" ? rainbowAt(now) : tierColor;
    ctx.globalAlpha = st.alpha;
    if (isGear(p.c)) triangle(sx, sy, (tier >= 5 ? 6.5 : 5) * st.k, color);
    // a mission item: a "!" (like quest givers), as big as a legendary's triangle (6.5 px: 7 x 0.93)
    else if (layer === "pickup.mission") bang(sx, sy, LAYER_COLOR[layer], 0.93 * st.k);
    else dot(sx, sy, 3.5 * st.k, LAYER_COLOR[layer]); // not gear (ammo, cash...): its kind's colour, no rarity
    if (st.names) label(sx, sy, nameText(p), isGear(p.c) ? color : LAYER_COLOR[layer], p.raw);
    hits.push({ sx, sy, r: 6 * st.k, kind: "loot", item: p });
  }
  // pawns: players on top, the tracked one last
  const order = { npc: 0, enemy: 1, vehicle: 2, player: 3, me: 3 };
  const rank = (p) => (p === tracked ? 4 : order[p.k]);
  const pawns = [...S.pawns.values()].sort((a, b) => rank(a) - rank(b));
  for (const p of pawns) {
    if (p.rs === 2) continue; // respawning, the game doesn't say where: its position means nothing
    const pos = pawnPos(p, now);
    const isPlayer = p.k === "me" || p.k === "player", layer = isPlayer ? "player" : p.k; // the host is one of the players
    const st = style(layer, pos);
    if (!st) continue;
    const [sx, sy] = place(pos.x, pos.y);
    if (!visible(sx, sy) && p !== tracked) continue;
    ctx.globalAlpha = st.alpha * (p.rs || p.dd ? 0.5 : 1); // respawning (at their New-U) / dead (their body): faded
    const angle = yawToAngle(f, pos.r) - S.view.rot;
    const hurt = (p.m > 0 && p.h < p.m) || (p.sm > 0 && p.s < p.sm);
    if (isPlayer) { // the tracked player: the yellow arrow; the others white
      if (p === tracked) arrow(sx, sy, angle, 9 * st.k, COLORS.tracked, COLORS.ink);
      else arrow(sx, sy, angle, 8 * st.k, LAYER_COLOR.player, COLORS.playerEdge);
      if (hurt && !p.rs && !p.dd) vitalBars(sx, sy + 3 * st.k, { ...p, h: pos.h, s: pos.s }, st.k);
      if (p.rs) respawnRing(sx, sy, 12 * st.k, p === tracked ? COLORS.tracked : LAYER_COLOR.player);
      else if (p.dd) respawnRing(sx, sy, 12 * st.k, COLORS.dead); // died: grey, where their body is
      // crippled (down, fighting for their life): the same ring, red
      else if (p.dn || (p.m > 0 && pos.h <= 0 && !(p.sm > 0 && pos.s > 0))) respawnRing(sx, sy, 12 * st.k, COLORS.health);
      else if (p.mn) menuBadge(sx, sy, st.k); // in a menu
    }
    else if (p.k === "vehicle") square(sx, sy, 5 * st.k, LAYER_COLOR.vehicle);
    else {
      if (p.k === "enemy") diamond(sx, sy, 5 * st.k, LAYER_COLOR.enemy); // like the game's minimap
      else ring(sx, sy, 4.5 * st.k, LAYER_COLOR[p.k], st.k); // NPCs: a hollow ring (pickups are dots, mission items a filled "!")
      if (hurt) vitalBars(sx, sy, { ...p, h: pos.h, s: pos.s }, st.k);
    }
    if (st.names) label(sx, sy, nameText(p), p === tracked ? COLORS.tracked : LAYER_COLOR[layer], p.raw);
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
  updatePlayerVitals(now); // with the frames: follows the Refresh rate setting
  refreshPlayerInfo(now);
}
