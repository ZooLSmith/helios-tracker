// The left panel: its tabs, the Settings tab ("Who", view, movement, language). The Layers tab is
// layers.js.
import { $, esc } from "../dom.js";
import { CATALOG, langPref, setLanguage, t } from "../i18n.js";
import { invalidate } from "../scheduler.js";
import { saveSettings, settings } from "../settings.js";
import { S } from "../state.js";
import { centerOnTarget, fit } from "../view.js";
import { renderInspector } from "./inspector.js";
import { renderLayers } from "./layers.js";
import { renderMission } from "./mission.js";
import { renderPlayers } from "./players.js";
import { refreshStatus } from "./status.js";

const MOTIONS = [0, 5, 10, 15, 20, 30, 60, "smooth"];

export function renderMotion() {
  const box = $("motion");
  box.innerHTML = MOTIONS.map((m) => `<option value="${m}">${esc(
    m === 0 ? (S.hz ? t("motion.updatesRate", { n: S.hz }) : t("motion.updates"))
      : m === "smooth" ? t("motion.smooth") : t("motion.fps", { n: m }))}</option>`).join("");
  box.value = String(settings.view.motion);
}

export function renderTargets() { // "Who": the host, then the other players (by name: ids change per level)
  const box = $("target"), target = settings.view.target;
  const names = S.players.filter((p) => !p.local).map((p) => p.n);
  if (target !== "me" && !names.includes(target)) names.push(target); // saved, not here now
  box.innerHTML = `<option value="me">${esc(t("who.host"))}</option>` +
    names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  box.value = target;
}

/** Rotate only means something while following: greyed out otherwise. */
export function syncRotate() {
  const box = $("rotate");
  box.disabled = !settings.view.follow;
  box.closest("label").classList.toggle("off", box.disabled);
}

function showPanelTab(name) {
  if (!document.querySelector(`.ptab[data-ptab="${name}"]`)) name = "info";
  settings.ui.panelTab = name;
  saveSettings();
  for (const el of document.querySelectorAll("#ptabs button, .ptab")) el.classList.toggle("on", el.dataset.ptab === name);
}

export function initPanel() {
  const bindBox = (id, key) => {
    const el = $(id);
    el.checked = settings.view[key];
    el.onchange = () => {
      settings.view[key] = el.checked; saveSettings(); invalidate();
      if (key === "follow" && el.checked) centerOnTarget();
    };
  };
  bindBox("follow", "follow"); bindBox("rotate", "rotate");
  syncRotate();
  $("follow").addEventListener("change", syncRotate);
  renderMotion();
  $("motion").onchange = (e) => {
    const v = e.target.value;
    settings.view.motion = v === "smooth" ? v : +v;
    saveSettings();
    invalidate();
  };
  $("target").onchange = (e) => { settings.view.target = e.target.value; saveSettings(); renderPlayers(); invalidate(); };
  $("fit").onclick = () => fit();

  const langBox = $("lang");
  langBox.innerHTML = `<option value="auto" data-i18n="lang.auto"></option>` +
    Object.keys(CATALOG).map((c) => `<option value="${c}">${esc(CATALOG[c]["lang.name"] || c)}</option>`).join("");
  langBox.value = CATALOG[langPref] ? langPref : "auto";
  langBox.onchange = () => {
    setLanguage(langBox.value);
    refreshStatus(); renderPlayers(); renderTargets(); renderMotion(); renderLayers(); renderInspector(); renderMission(); invalidate();
  };

  // Tabs, collapse
  for (const b of $("ptabs").querySelectorAll("button")) b.onclick = () => showPanelTab(b.dataset.ptab);
  showPanelTab(settings.ui.panelTab);
  $("collapse").onclick = () => {
    $("panel").classList.toggle("collapsed");
    $("collapse").textContent = $("panel").classList.contains("collapsed") ? "▸" : "▾";
  };
}
