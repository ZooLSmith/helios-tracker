// The game's data: the SSE stream (/events) and what each event does to the state.
import { $ } from "./dom.js";
import { decodeTexture } from "./dxt.js";
import { t } from "./i18n.js";
import { objectCategory, setRarityTable } from "./model.js";
import { invalidate } from "./scheduler.js";
import { settings } from "./settings.js";
import { S, findDetail, pawnPos } from "./state.js";
import { renderCutscene } from "./ui/cutscene.js";
import { renderDetail } from "./ui/detail.js";
import { restoreDrawer } from "./ui/drawer.js";
import { closeInspector, renderInspector } from "./ui/inspector.js";
import { renderMission } from "./ui/mission.js";
import { renderMissionLog } from "./ui/missionlog.js";
import { renderMotion } from "./ui/panel.js";
import { renderShops, renderShopsView } from "./ui/shops.js";
import { patternTiming, renderPlayers } from "./ui/players.js";
import { isLive, setMessage, setPaused, setStatus } from "./ui/status.js";

const RETRY_MS = 2000; // lost the game: how often to check whether it's back

export function connect() {
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
  on("level", onLevel);
  on("state", onState);
  on("objects", onObjects);
  on("areas", onAreas);
  on("cutscene", onCutscene);
  on("players", onPlayers);
  on("missions", onMissions);
  on("missiondefs", onMissionDefs);
  on("missionlog", onMissionLog);
  on("shops", onShops);
  on("shoptimer", onShopTimer);
  on("lootpools", onLootPools);
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
  invalidate();
  const changed = !S.level || S.level.id !== level.id;
  if (changed) {
    S.images = []; S.fogBlob = null; S.pawns.clear(); S.pickups = []; S.objects = []; S.areas = []; S.fogSeen = null; S.explored = false; S.fitted = false; S.fallback = null;
    S.players = []; renderPlayers(); renderInspector();
    S.missions = { tracked: null, markers: [] }; renderMission();
    S.shops = null; S.shopTimer = null; renderShops();
  }
  const wasReady = S.level && S.level.id === level.id && S.level.status === "ready";
  S.level = level;
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
  const c = document.createElement("canvas");
  c.width = img.width; c.height = img.height;
  c.getContext("2d").putImageData(new ImageData(rgba, img.width, img.height), 0, 0);
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
  for (const p of st.pawns) {
    seen.add(p.i);
    if (p.k === "me") S.meId = p.i;
    // Rebuilt from each state (not merged into the old one): a field the game stopped sending,
    // like the made-up-name flag "r" once the real name is known, must go away
    const old = S.pawns.get(p.i);
    const from = old && !old.rs === !p.rs ? pawnPos(old, now) : p; // respawn start / end: no slide
    S.pawns.set(p.i, { ...p, fx: from.x, fy: from.y, fz: from.z, fr: from.r, fh: from.h, fs: from.s, t0: now });
  }
  for (const id of S.pawns.keys()) if (!seen.has(id)) S.pawns.delete(id);
  S.pickups = st.pickups;
  setPaused(st.paused);
  if (!S.level.center && !S.fallback && S.meId) {
    const me = S.pawns.get(S.meId);
    S.fallback = { center: [me.x, me.y], upp: 128, north: 0 };
  }
  closeIfGone();
  restoreDrawer("state");
}

/** The drawer shows a map object (loot, a pawn, a marker) that isn't there any more (picked up,
 *  killed, done): close it. */
function closeIfGone() {
  if (S.detail && !findDetail()) closeInspector();
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
