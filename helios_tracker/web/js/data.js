// The game's data: the SSE stream (/events) and what each event does to the state.
import { $ } from "./dom.js";
import { decodeTexture } from "./dxt.js";
import { setVariant, t } from "./i18n.js";
import { objectCategory, setRarityTable } from "./model.js";
import { invalidate } from "./scheduler.js";
import { settings } from "./settings.js";
import { S, findDetail, itemById, pawnPos } from "./state.js";
import { renderCutscene } from "./ui/cutscene.js";
import { renderDetail } from "./ui/detail.js";
import { restoreDrawer } from "./ui/drawer.js";
import { closeInspector, renderInspector } from "./ui/inspector.js";
import { renderMission } from "./ui/mission.js";
import { renderMissionLog } from "./ui/missionlog.js";
import { renderMotion } from "./ui/panel.js";
import { renderShops, renderShopsView } from "./ui/shops.js";
import { patternTiming, renderPlayers } from "./ui/players.js";
import { renderLayers } from "./ui/layers.js";
import { isLive, setMessage, setPaused, setStatus } from "./ui/status.js";

const RETRY_MS = 2000; // lost the game: how often to check whether it's back

export function connect() {
  for (const k of Object.keys(stores)) delete stores[k]; // (a new stream: every record channel starts whole)
  const es = new EventSource("/events");
  es.onopen = () => setStatus("live", "status.live");
  // Lost the connection (game closed, mod reloaded, server restarted): no half-stale reconnect -
  // wait until the server answers again, then reload the page (a plain F5: fresh state and code)
  es.onerror = () => {
    es.close();
    onCutscene({}); // the game's gone: no cutscene counted on (a video plays with the server still up - its end would come)
    setStatus("bad", "status.bad");
    reloadWhenBack();
  };
  const on = (name, fn) => es.addEventListener(name, (e) => {
    if (es.readyState === EventSource.OPEN && !isLive()) setStatus("live", "status.live");
    fn(JSON.parse(e.data));
  });
  // a record channel: only what changed comes (server.py Hub); out of step (a bug): a new stream, everything again
  const onRecords = (name, list, fn) => on(name, (msg) => {
    const whole = keyed(name, list, msg);
    if (whole) fn(whole);
    else { console.warn("record channel out of step, reconnecting:", name, msg.b, stores[name]?.v); es.close(); connect(); }
  });
  on("level", onLevel);
  onRecords("state", "pawns", onState);
  onRecords("objects", "objects", onObjects);
  on("areas", onAreas);
  on("cutscene", onCutscene);
  onRecords("players", "players", onPlayers);
  on("missions", onMissions);
  onRecords("missiondefs", "missions", onMissionDefs);
  onRecords("missionlog", "missions", onMissionLog);
  onRecords("shops", "machines", onShops);
  on("shoptimer", onShopTimer);
  on("lootpools", onLootPools);
  on("assets", onAssets);
  onRecords("items", "items", onItems);
  onRecords("pickups", "pickups", onPickups);
  onRecords("pawninfo", "pawns", onPawnInfo);
}

/** The record channels' records as the page has them: name -> {v: version, meta: its own fields, recs: id -> record}. */
const stores = {};

/** Merges a record channel's message (server.py _Records: {v, b, m, set, del, o, rep | full}) into what the page has;
 *  returns the channel whole ({...its fields, [list]: records in order} - what the handlers always got), or null when
 *  it doesn't follow the version the page has. A record changed from the version before: only its changed fields,
 *  "-" the ones it lost (a flag gone: gone here too); from further back ("rep") or new: whole. Records are never
 *  changed in place: a new object each time (a handler may hold the old one). */
export function keyed(name, list, msg) {
  let store = stores[name];
  if (msg.full) store = stores[name] = { v: msg.v, meta: msg.m, recs: new Map() };
  else if (!store || msg.b !== store.v) return null;
  else { store.v = msg.v; store.meta = msg.m; }
  for (const id of msg.del || []) store.recs.delete(id);
  for (const r of msg.set || []) {
    const id = Array.isArray(r) ? String(r[0]) : r.i;
    const old = store.recs.get(id);
    if (!old || msg.full || msg.rep || Array.isArray(r)) { store.recs.set(id, r); continue; }
    const { "-": lost, ...fields } = r;
    const merged = { ...old, ...fields };
    for (const k of lost || []) delete merged[k];
    store.recs.set(id, merged);
  }
  if (msg.o) store.recs = new Map(msg.o.filter((id) => store.recs.has(id)).map((id) => [id, store.recs.get(id)]));
  return { ...store.meta, [list]: [...store.recs.values()] };
}

function reloadWhenBack() {
  setTimeout(async () => {
    try {
      const res = await fetch("/", { cache: "no-store" }); // the page itself (small; the server has no HEAD)
      if (res.ok) { location.reload(); return; }
    } catch { /* still down */ }
    reloadWhenBack();
  }, RETRY_MS);
}

function onLevel(level) {
  setVariant(level.game); // (the Pre-Sequel's words for its labels: i18n.js)
  invalidate();
  const changed = !S.level || S.level.id !== level.id;
  if (changed) {
    S.images = []; S.fogBlob = null; S.pawns.clear(); S.pawnInfo = {}; S.groundItems = new Map(); S.pickups = []; S.objects = []; S.areas = []; S.fogSeen = null; S.explored = false; S.fitted = false; S.fallback = null;
    S.players = []; renderPlayers(); renderInspector();
    S.missions = { tracked: null, markers: [] }; renderMission();
    S.shops = null; S.shopTimer = null; renderShops();
  }
  const wasReady = S.level && S.level.id === level.id && S.level.status === "ready";
  const gameChanged = (S.level?.game || "") !== (level.game || "");
  S.level = level;
  if (gameChanged) renderLayers(); // (a game's own layers: the Pre-Sequel's oxygen - model.js layerInGame)
  if (level.rarity) setRarityTable(level.rarity);
  renderLevel();
  renderMessage();
  if (level.status === "ready" && !wasReady) loadImages(level);
}

/** The message over the map: the level's (loading, no map...). */
function renderMessage() {
  const level = S.level;
  const inMenu = !!level.map && level.map.toLowerCase() === "menumap";
  if (level.status === "loading") setMessage("msg.loading");
  else if (level.status === "none") setMessage(inMenu ? "msg.menu" : "msg.noMap");
  else if (level.status === "error") setMessage("msg.mapError", { error: level.error });
  else setMessage(null);
}

/** A cutscene on the game's PC: a video (the collector's ClientPlayBinkMovie hook: the game renders nothing
 *  meanwhile - no updates) or an in-engine one (the script's cinematic mode, its Matinee's length if found) -
 *  the Info tab's Cutscene bar counts it here, from its start; {} once it's over. */
let videoTimer = 0;
function onCutscene(msg) {
  // (a video, or an in-engine scene; paused: stopped at pos, s)
  S.video = msg.video || msg.scene
    ? { len: msg.len ?? null, at: msg.at, paused: !!msg.paused, pos: msg.pos ?? 0, name: msg.name || "" } : null;
  clearInterval(videoTimer);
  // (the time text; the bar is a CSS animation) - its own timer, the one exception to "refreshes follow the Refresh
  // rate setting" (AGENTS.md): no game updates reach the page while a video plays, so the frames would freeze it
  if (S.video) videoTimer = setInterval(renderCutscene, 250);
  renderCutscene();
}

/** The panel's level name, its area level and the tab title - from S.level, in the page's language
 *  (again on a language change: panel.js). */
export function renderLevel() {
  const level = S.level;
  if (!level) return;
  // the game's name for the level (the map screen's); "raw": made up from the map file's name - marked " ?"
  // the main menu's map ("menumap", no game name): "Main menu", not a made-up level name
  const inMenu = !!level.map && level.map.toLowerCase() === "menumap";
  const levelText = inMenu ? t("level.menu") : level.name ? level.name + (level.raw ? " ?" : "") : level.map || "—";
  $("level").textContent = levelText;
  // the area's level (its missions' regions' game stage, the game's): "Lv 13", or a range
  const lv = level.lv;
  $("levelLv").textContent = lv ? t(lv[0] === lv[1] ? "level.lv" : "level.lvRange", { n: lv[0], m: lv[1] }) : "";
  document.title = (level.name && !inMenu ? levelText + " · " : "") + "Helios Tracker";
}

/** A texture from the server, decoded onto a canvas. */
async function loadTexture(img) {
  const res = await fetch(img.url);
  if (!res.ok) throw new Error(res.status + " " + res.statusText);
  const data = new Uint8Array(await res.arrayBuffer());
  const rgba = decodeTexture(img.format, img.width, img.height, data);
  // a sub-image (its movie draws a part of the texture: "crop" [x, y, w, h] px - the Pre-Sequel's ComFacility_P): that part
  const [cx, cy, cw, ch] = img.crop || [0, 0, img.width, img.height];
  const c = document.createElement("canvas");
  c.width = cw; c.height = ch;
  c.getContext("2d").putImageData(new ImageData(rgba, img.width, img.height), -cx, -cy);
  return { canvas: c, bounds: img.bounds };
}

async function loadImages(level) {
  const out = [];
  for (const img of level.images) {
    try {
      out.push(await loadTexture(img));
    } catch (err) {
      console.error("map image", img.name, err);
      setMessage("msg.imageError", { error: err.message });
    }
  }
  let fog = null;
  if (level.fog) { // the fog of war piece: without it, just no fog
    try { fog = await loadTexture(level.fog); } catch (err) { console.error("fog of war", err); }
  }
  if (S.level && S.level.id === level.id) {
    S.images = out;
    S.fogBlob = fog;
    S.fitted = false;
    invalidate();
  }
}

function onState(st) {
  if (!S.level || st.level !== S.level.id) return;
  invalidate();
  const now = performance.now();
  if (st.hz > 0) { // the game's update rate: interpolate exactly from one update to the next
    if (S.hz !== st.hz) { S.hz = st.hz; renderMotion(); patternTiming(settings.view.motion, S.hz); } // (updates only: steps at it)
    S.interval = 1000 / st.hz;
  } else if (S.lastState) S.interval = S.interval * 0.8 + Math.min(1000, now - S.lastState) * 0.2;
  S.lastState = now;
  const seen = new Set();
  S.meId = null;
  for (const row of st.pawns) {
    // its description (kind, name, level, max health / shield: the "pawninfo" channel, sent on change) with what moves -
    // one not described yet waits for it (drawn half-known, it has no layer)
    const info = S.pawnInfo[row[0]];
    if (!info) continue;
    const p = { ...info, ...movingOf(row, info) };
    seen.add(p.i);
    if (p.k === "me") S.meId = p.i;
    // Rebuilt from each state (not merged into the old one): a field the game stopped sending,
    // like the made-up-name flag "raw" once the real name is known, must go away
    const old = S.pawns.get(p.i);
    const from = old && !old.rs === !p.rs ? pawnPos(old, now) : p; // respawn start / end: no slide
    S.pawns.set(p.i, { ...p, fx: from.x, fy: from.y, fz: from.z, fr: from.r, fh: from.h, fs: from.s, t0: now });
  }
  for (const id of S.pawns.keys()) if (!seen.has(id)) S.pawns.delete(id);
  setPaused(st.paused);
  if (!S.level.center && !S.fallback && S.meId) {
    const me = S.pawns.get(S.meId);
    S.fallback = { center: [me.x, me.y], upp: 128, north: 0 };
  }
  closeIfGone();
  restoreDrawer("state");
}

/** A state's pawn row, compact (collector.py: the stream's bulk): [id, x, y, z, health if not full, {the rest} if
 *  any] - the shield in the rest, when not full. Full: the max from its description (hf / sf: to follow a new max). */
export function movingOf(row, info) {
  const [i, x, y, z, ...more] = row;
  const h = typeof more[0] === "number" ? more.shift() : undefined;
  const extra = more[0] || {};
  const p = { ...extra, i, x, y, z };
  if (info.m > 0) { p.h = h ?? info.m; if (h === undefined) p.hf = 1; }
  if (info.sm > 0) { p.s = extra.s ?? info.sm; if (extra.s === undefined) p.sf = 1; }
  if (info.om > 0) { p.ox = extra.ox ?? info.om; p.vac = extra.vac ? 1 : 0; } // (a player's oxygen - the Pre-Sequel's Oz meter; vac: in a vacuum)
  return p;
}

/** The drawer shows a map object (loot, a pawn, a marker) that isn't there any more (picked up,
 *  killed, done): close it. */
function closeIfGone() {
  if (S.detail && !findDetail()) closeInspector();
}

/** The level's pickups (sent when they change: one appears / goes / moves - thrown, dropped). */
function onPickups(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.pickups = msg.pickups;
  closeIfGone();
  refreshLootDetail();
  invalidate();
}

/** The gear pickups' items (their cards: stats, parts - built by the collector a few per update, sent once each). */
function onItems(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.groundItems = new Map(msg.items.map((it) => [it.i, it]));
  refreshLootDetail();
}

// The drawer shows a pickup: again when its record changed (records are new objects only when they change: keyed) - its
// item's card came in, it rolled (its distance). `render`: offline_check's counter (no DOM there)
let lootShown = null;
export function refreshLootDetail(render = renderDetail) {
  if (!S.detail || S.detail.kind !== "loot") { lootShown = null; return; }
  const found = findDetail(); // (the pickup itself)
  if (!found) return;
  const card = itemById(found.it);
  if (found === lootShown?.item && card === lootShown?.card) return;
  lootShown = { item: found, card };
  render();
}

/** The pawns' descriptions (kind, name, level, max health / shield - sent when they change); the pawns on the map get them at once (a
 *  real name that came in, a level up), without waiting for their next move. */
function onPawnInfo(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.pawnInfo = Object.fromEntries(msg.pawns.map((p) => [p.i, p]));
  for (const [id, p] of S.pawns) {
    const info = S.pawnInfo[id];
    if (!info) continue;
    const { raw, ...rest } = p; // (the made-up-name flag: only if the description still has it)
    const full = { // full health / shield: the new max (a level up - no state follows if nothing moved)
      ...(p.hf && info.m > 0 ? { h: info.m, fh: info.m } : {}), ...(p.sf && info.sm > 0 ? { s: info.sm, fs: info.sm } : {}) };
    S.pawns.set(id, { ...rest, ...info, ...full });
  }
  invalidate();
}

function onObjects(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  for (const o of msg.objects) o.cat = objectCategory(o);
  msg.objects.sort((a, b) => a.z - b.z); // drawn bottom to top: a higher object covers a lower one
  S.objects = msg.objects;
  if (S.detail) { if (findDetail()) renderDetail(); else closeInspector(); }
  restoreDrawer("objects");
  invalidate();
}

/** The level's discovery areas: {k, x, y, z, r, n?: the game's name, u?: discovered}; seen: the fog
 *  pieces discovered (by name); full: all of it explored. */
function onAreas(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.areas = msg.areas;
  S.fogSeen = new Set(msg.seen || []);
  S.explored = !!msg.full;
  invalidate();
}

function onPlayers(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.players = msg.players;
  renderPlayers();
  renderInspector();
  restoreDrawer("players");
}

// The mission log, in two payloads (the whole playthrough's missions: kept across levels): the
// definitions (static, when the list changes) and the live part (status, progress, levels, rewards)
let logDefs = null, logLive = null;
function onMissionDefs(msg) {
  logDefs = new Map(msg.missions.map((m) => [m.i, m]));
  mergeLog();
}
function onMissionLog(msg) {
  logLive = msg;
  mergeLog();
}
function mergeLog() {
  if (!logDefs || !logLive) return;
  S.log = { ...logLive, missions: logLive.missions.filter((l) => logDefs.has(l.i)).map((l) => ({ ...logDefs.get(l.i), ...l })) };
  renderMission();
  if (S.missionView) renderMissionLog();
  restoreDrawer("log");
}

/** The level's vending machines and their stock (shops.py: when it changes - a sale, a restock). */
function onShops(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.shops = { client: !!msg.client, machines: msg.machines };
  renderShops();
  if (S.shopView) renderShopsView();
  if (S.detail) renderDetail(); // (a machine's panel: its stock's count)
  restoreDrawer("shops");
}

/** What the server can serve from the game's files now (__init__.py: the item card icons once indexed and their keys
 *  known) - the map's gear icons wait for it. */
function onAssets(msg) {
  S.assets = msg;
  invalidate();
}

/** The pools the containers' loot odds reach (static game data, not per level: only ever grows). */
function onLootPools(msg) {
  S.lootPools = msg.pools;
  if (S.detail) renderDetail(); // (an open container's odds: its pools' entries)
}

/** The shops' restock timer: the game's count (sent again when the page's would drift from it). */
function onShopTimer(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  const first = !S.shopTimer;
  S.shopTimer = { left: msg.left, rate: msg.rate, at: performance.now(), paused: !!msg.paused }; // (paused: held)
  if (first) renderShops(); // (its countdown line; then only its text, every second)
}

function onMissions(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.missions = msg;
  renderMission();
  closeIfGone();
  restoreDrawer("missions");
  invalidate();
}
