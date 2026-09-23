// The game's data: the SSE stream (/events) and what each event does to the state.
import { $ } from "./dom.js";
import { decodeTexture } from "./dxt.js";
import { objectCategory, setRarityTable } from "./model.js";
import { invalidate } from "./scheduler.js";
import { S, findDetail, pawnPos } from "./state.js";
import { renderDetail } from "./ui/detail.js";
import { restoreDrawer } from "./ui/drawer.js";
import { closeInspector, renderInspector } from "./ui/inspector.js";
import { renderMission } from "./ui/mission.js";
import { renderMissionLog } from "./ui/missionlog.js";
import { renderMotion } from "./ui/panel.js";
import { renderPlayers } from "./ui/players.js";
import { isLive, setMessage, setStatus } from "./ui/status.js";

const RETRY_MS = 2000; // lost the game: how often to check whether it's back

export function connect() {
  const es = new EventSource("/events");
  es.onopen = () => setStatus("live", "status.live");
  // Lost the connection (game closed, mod reloaded, server restarted): no half-stale reconnect -
  // wait until the server answers again, then reload the page (a plain F5: fresh state and code)
  es.onerror = () => {
    es.close();
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
  on("players", onPlayers);
  on("missions", onMissions);
  on("missiondefs", onMissionDefs);
  on("missionlog", onMissionLog);
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
    S.images = []; S.pawns.clear(); S.pickups = []; S.objects = []; S.fitted = false; S.fallback = null;
    S.players = []; renderPlayers(); renderInspector();
    S.missions = { tracked: null, markers: [] }; renderMission();
  }
  const wasReady = S.level && S.level.id === level.id && S.level.status === "ready";
  S.level = level;
  if (level.rarity) setRarityTable(level.rarity);
  $("level").textContent = level.name || level.map || "—";
  document.title = (level.name ? level.name + " · " : "") + "Helios Tracker";
  if (level.status === "loading") setMessage("msg.loading");
  else if (level.status === "none") setMessage(level.map && level.map.toLowerCase() === "menumap" ? "msg.menu" : "msg.noMap");
  else if (level.status === "error") setMessage("msg.mapError", { error: level.error });
  else setMessage(null);
  if (level.status === "ready" && !wasReady) loadImages(level);
}

async function loadImages(level) {
  const out = [];
  for (const img of level.images) {
    try {
      const res = await fetch(img.url);
      if (!res.ok) throw new Error(res.status + " " + res.statusText);
      const data = new Uint8Array(await res.arrayBuffer());
      const rgba = decodeTexture(img.format, img.width, img.height, data);
      const c = document.createElement("canvas");
      c.width = img.width; c.height = img.height;
      c.getContext("2d").putImageData(new ImageData(rgba, img.width, img.height), 0, 0);
      out.push({ canvas: c, bounds: img.bounds });
    } catch (err) {
      console.error("map image", img.name, err);
      setMessage("msg.imageError", { error: err.message });
    }
  }
  if (S.level && S.level.id === level.id) {
    S.images = out;
    S.fitted = false;
    invalidate();
  }
}

function onState(st) {
  if (!S.level || st.level !== S.level.id) return;
  invalidate();
  const now = performance.now();
  if (st.hz > 0) { // the game's update rate: interpolate exactly from one update to the next
    if (S.hz !== st.hz) { S.hz = st.hz; renderMotion(); }
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

function onMissions(msg) {
  if (!S.level || msg.level !== S.level.id) return;
  S.missions = msg;
  renderMission();
  closeIfGone();
  restoreDrawer("missions");
  invalidate();
}
