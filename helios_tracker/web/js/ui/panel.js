// The left panel: tabs, layer toggles, loot filter, "Who" / view settings, language.
import { $, esc } from "../dom.js";
import { CATALOG, langPref, setLanguage, t } from "../i18n.js";
import { LAYERS } from "../model.js";
import { invalidate } from "../scheduler.js";
import { S } from "../state.js";
import { store } from "../store.js";
import { centerOnTarget, fit } from "../view.js";
import { renderInspector } from "./inspector.js";
import { renderMission } from "./mission.js";
import { renderPlayers } from "./players.js";
import { refreshStatus } from "./status.js";

const MOTIONS = [0, 5, 10, 15, 20, 30, 60, "smooth"];

// The layer's marker as drawn on the map (12 px SVG)
function layerIcon(l) {
  const c = l.color, o = `stroke="rgba(0,0,0,.8)" stroke-width="1"`;
  const shape = {
    player: `<polygon points="6,1 10.3,10.8 6,8.3 1.7,10.8" fill="${c}" ${o}/>`,
    enemy: `<polygon points="6,1 11,6 6,11 1,6" fill="${c}" ${o}/>`,
    npc: `<circle cx="6" cy="6" r="3.5" fill="${c}" ${o}/>`,
    vehicle: `<rect x="1.5" y="1.5" width="9" height="9" fill="${c}" ${o}/>`,
    objective: `<polygon points="6,1 11,6 6,11 1,6" fill="${c}" ${o}/><circle cx="6" cy="6" r="1.5" fill="#1a1200"/>`,
    loot: `<polygon points="6,1.5 10.5,9.5 1.5,9.5" fill="${c}" ${o}/>`,
    chest: `<rect x="0.5" y="0.5" width="11" height="11" fill="${c}" ${o}/>`,
    weaponchest: `<rect x="1.5" y="1.5" width="9" height="9" fill="${c}" ${o}/>`,
    other: `<rect x="3.5" y="3.5" width="5" height="5" fill="${c}" ${o}/>`,
    looted: `<rect x="3.5" y="3.5" width="5" height="5" fill="${c}" opacity=".6" ${o}/>`,
  }[l.id] || `<rect x="2.5" y="2.5" width="7" height="7" fill="${c}" ${o}/>`; // containers, vendors, stations
  return `<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">${shape}</svg>`;
}

export function renderMotion() {
  const box = $("motion");
  box.innerHTML = MOTIONS.map((m) => `<option value="${m}">${esc(
    m === 0 ? (S.hz ? t("motion.updatesRate", { n: S.hz }) : t("motion.updates"))
      : m === "smooth" ? t("motion.smooth") : t("motion.fps", { n: m }))}</option>`).join("");
  box.value = String(S.motion);
}

export function renderTargets() { // "Who": the host, then the other players (by name: ids change per level)
  const box = $("target");
  const names = S.players.filter((p) => !p.local).map((p) => p.n);
  if (S.target !== "me" && !names.includes(S.target)) names.push(S.target); // saved, not here now
  box.innerHTML = `<option value="me">${esc(t("who.host"))}</option>` +
    names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  box.value = S.target;
}

function showPanelTab(name) {
  if (!document.querySelector(`.ptab[data-ptab="${name}"]`)) name = "info";
  store.set("ptab", name);
  for (const el of document.querySelectorAll("#ptabs button, .ptab")) el.classList.toggle("on", el.dataset.ptab === name);
}

export function initPanel() {
  // Layers
  const layerBoxes = [];
  for (const l of LAYERS) {
    const row = document.createElement("label");
    row.className = "row";
    row.innerHTML = `<input type="checkbox"><span class="sw">${layerIcon(l)}</span><span data-i18n="layer.${l.id}"></span><span class="count" data-count="${l.id}"></span>`;
    const box = row.querySelector("input");
    box.checked = S.layers[l.id];
    box.onchange = () => { S.layers[l.id] = box.checked; store.set("layer." + l.id, box.checked); invalidate(); };
    $("layers").appendChild(row);
    layerBoxes.push([l.id, box]);
  }
  const setAllLayers = (on) => {
    for (const [id, box] of layerBoxes) {
      box.checked = on; S.layers[id] = on; store.set("layer." + id, on);
    }
    invalidate();
  };
  $("layersAll").onclick = () => setAllLayers(true);
  $("layersNone").onclick = () => setAllLayers(false);
  $("rarity").value = String(S.minRarity);
  $("rarity").onchange = (e) => { S.minRarity = +e.target.value; store.set("minRarity", S.minRarity); invalidate(); };

  // Settings
  const bindBox = (id, key) => {
    const el = $(id);
    el.checked = S[key];
    el.onchange = () => {
      S[key] = el.checked; store.set(key, el.checked); invalidate();
      if (key === "follow" && el.checked) centerOnTarget();
    };
  };
  bindBox("follow", "follow"); bindBox("rotate", "rotate");
  bindBox("labels", "labels"); bindBox("height", "height");
  renderMotion();
  $("motion").onchange = (e) => {
    const v = e.target.value;
    S.motion = v === "smooth" ? v : +v;
    store.set("motion", S.motion);
    invalidate();
  };
  $("target").onchange = (e) => { S.target = e.target.value; store.set("target", S.target); invalidate(); };
  $("fit").onclick = () => fit();

  const langBox = $("lang");
  langBox.innerHTML = `<option value="auto" data-i18n="lang.auto"></option>` +
    Object.keys(CATALOG).map((c) => `<option value="${c}">${esc(CATALOG[c]["lang.name"] || c)}</option>`).join("");
  langBox.value = CATALOG[langPref] ? langPref : "auto";
  langBox.onchange = () => {
    setLanguage(langBox.value);
    refreshStatus(); renderPlayers(); renderTargets(); renderMotion(); renderInspector(); renderMission(); invalidate();
  };

  // Tabs, collapse
  for (const b of $("ptabs").querySelectorAll("button")) b.onclick = () => showPanelTab(b.dataset.ptab);
  showPanelTab(store.get("ptab", "info"));
  $("collapse").onclick = () => {
    $("panel").classList.toggle("collapsed");
    $("collapse").textContent = $("panel").classList.contains("collapsed") ? "▸" : "▾";
  };
}
