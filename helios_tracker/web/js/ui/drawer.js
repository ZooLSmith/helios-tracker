// What the right drawer shows, remembered (settings.ui.drawer) so a page refresh (F5) opens it again:
// a player (by name: ids change when a level loads), a mission's details or the mission list, a map
// object (by id: the game's object, still the same one after a refresh). Restored once the data it
// needs has arrived; if it's gone: its category's list - the mission list for a mission, the Players
// list (the Info tab) for a player; a map object (picked up, killed...) or a quest marker: closed
// (their list is the map).
import { saveSettings, settings } from "../settings.js";
import { S, findDetail } from "../state.js";
import { openDetail } from "./detail.js";
import { openInspector } from "./inspector.js";
import { openMissionLog } from "./missionlog.js";
import { showPanelTab } from "./panel.js";

/** Remembers what the drawer shows now (called on every open / close / move inside it). */
export function saveDrawer() {
  pending = null; // opened / closed by hand before the restore: that wins
  const d = S.inspect ? { k: "player", name: S.inspect.name }
    : S.missionView ? { k: "mission", id: S.missionView.id || "" }
    : S.detail ? { k: "detail", kind: S.detail.kind, id: S.detail.id }
    : {};
  if (JSON.stringify(d) === JSON.stringify(settings.ui.drawer)) return;
  settings.ui.drawer = d;
  saveSettings();
}

// What's left to restore (null: done); the payloads seen since the page loaded
let pending = settings.ui.drawer && settings.ui.drawer.k ? { ...settings.ui.drawer } : null;
const got = new Set();

/** From data.js, after each payload (its name: "players", "log", "state", "objects", "missions"):
 *  reopens the remembered drawer once what it needs is in. */
export function restoreDrawer(payload) {
  if (!pending) return;
  got.add(payload);
  const d = pending;
  if (d.k === "player") {
    if (!got.has("players")) return;
    pending = null;
    const p = S.players.find((q) => q.n === d.name);
    if (p) openInspector(p.i);
    else showPanelTab("info"); // gone: the Players list
  } else if (d.k === "mission") {
    if (!got.has("log")) return;
    pending = null;
    const id = typeof d.id === "string" && S.log.missions.some((m) => m.i === d.id) ? d.id : null;
    openMissionLog(id); // gone (or the list itself): the list
  } else if (d.k === "detail" && typeof d.id === "string") {
    const was = S.detail;
    S.detail = { kind: d.kind, id: d.id }; // findDetail looks it up by kind
    const found = findDetail();
    S.detail = was;
    if (found) { pending = null; openDetail(d.kind, d.id); return; }
    // not there: given up once every payload it could be in has come
    if (!["state", "objects", "missions"].every((k) => got.has(k))) return;
    saveDrawer(); // forgotten
  } else {
    pending = null;
  }
}
