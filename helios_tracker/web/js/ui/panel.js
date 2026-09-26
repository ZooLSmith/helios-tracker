// The left panel: its tabs, the Settings tab ("Who", view, movement, language). The Layers tab is
// layers.js.
import { $, esc } from "../dom.js";
import { renderLevel } from "../data.js";
import { LOOK_RANGES, THEMES, applyLook, look, setThemeAttr, themeName } from "../look.js";
import { COLORS, initColors } from "../shapes.js";
import { CATALOG, langPref, setLanguage, t } from "../i18n.js";
import { icon } from "../icons.js";
import { invalidate } from "../scheduler.js";
import { saveSettings, settings } from "../settings.js";
import { S } from "../state.js";
import { centerOnTarget, fit, resetSpin, stopFollow } from "../view.js";
import { renderInspector } from "./inspector.js";
import { renderLayers } from "./layers.js";
import { renderMission } from "./mission.js";
import { patternTiming, renderPlayers } from "./players.js";
import { refreshStatus } from "./status.js";

const MOTIONS = [0, 5, 10, 15, 20, 30, 60, "smooth"];

export function renderMotion() {
  const box = $("motion");
  box.innerHTML = MOTIONS.map((m) => `<option value="${m}">${esc(
    m === 0 ? (S.hz ? t("motion.updatesRate", { n: S.hz }) : t("motion.updates"))
      : m === "smooth" ? t("motion.smooth") : t("motion.fps", { n: m }))}</option>`).join("");
  box.value = String(settings.view.motion);
}

export function renderTargets() { // "Who": the mod's player ("me"), then the others (by name: ids change per level)
  // By name, the host marked: anyone may be looking at the page ("you" would mean nothing)
  const box = $("target"), target = settings.view.target;
  const label = (p) => (p.host ? t("who.host", { name: p.n }) : p.n);
  const others = S.players.filter((p) => !p.local), self = S.players.find((p) => p.local);
  const names = others.map((p) => p.n);
  const saved = target !== "me" && !names.includes(target) ? [target] : []; // saved, not here now
  box.innerHTML = `<option value="me">${esc(self ? label(self) : t("who.player"))}</option>` +
    others.map((p) => `<option value="${esc(p.n)}">${esc(label(p))}</option>`).join("") +
    saved.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  box.value = target;
}

/** Rotate only means something while following: greyed out otherwise. */
export function syncRotate() {
  const box = $("rotate");
  box.disabled = !settings.view.follow;
  box.closest("label").classList.toggle("off", box.disabled);
}

const TO_TOP_AFTER = 150; // px down a tab's content before the "back to top" button shows
const tabScroll = {}; // each tab's scroll, kept across tab switches (a hidden tab loses its own)

/** What scrolls in the shown tab: its content (the tabs and Layers' buttons stay above). */
const panelScroller = () => document.querySelector(".ptab.on .pscroll");

/** The panel's "back to top" button: shown once down the tab's content a bit, over its top right. */
function syncPanelToTop() {
  const list = panelScroller(), btn = $("pToTop");
  const show = !!list && !$("panel").classList.contains("collapsed") && list.scrollTop > TO_TOP_AFTER;
  if (btn.classList.contains("on") !== show) btn.classList.toggle("on", show);
  if (show) btn.style.top = `${list.offsetTop + 6}px`;
}

export function showPanelTab(name) {
  if (!document.querySelector(`.ptab[data-ptab="${name}"]`)) name = "info";
  const was = panelScroller();
  if (was) tabScroll[settings.ui.panelTab] = was.scrollTop;
  settings.ui.panelTab = name;
  saveSettings();
  for (const el of document.querySelectorAll("#ptabs button, .ptab")) el.classList.toggle("on", el.dataset.ptab === name);
  const now = panelScroller();
  if (now) now.scrollTop = tabScroll[name] || 0;
  syncPanelToTop();
}

// The page shown again in another language (the Language box, or the game's on "Auto": data.js) - set by initPanel
let languageRenders = () => {};
export function languageChanged() { languageRenders(); }

export function initPanel() {
  const bindBox = (id, key) => {
    const el = $(id);
    el.checked = settings.view[key];
    el.onchange = () => {
      // (Follow off: through stopFollow - Rotate's turn kept, no jump; a drag / the fit key go the same way)
      if (key === "follow" && !el.checked) { stopFollow(); invalidate(); return; }
      settings.view[key] = el.checked; saveSettings(); invalidate();
      if (key === "follow" && el.checked) centerOnTarget();
    };
  };
  bindBox("follow", "follow"); bindBox("rotate", "rotate"); bindBox("threeD", "threeD"); bindBox("coords-on", "coords");
  $("north").onclick = resetSpin; // (the compass on the map: shown once it's turned, or turning with the heading)
  syncRotate();
  $("follow").addEventListener("change", syncRotate);
  renderMotion();
  $("motion").onchange = (e) => {
    const v = e.target.value;
    settings.view.motion = v === "smooth" ? v : +v;
    saveSettings();
    patternTiming(settings.view.motion, S.hz);
    invalidate();
  };
  patternTiming(settings.view.motion, S.hz);
  $("target").onchange = (e) => { settings.view.target = e.target.value; saveSettings(); renderPlayers(); invalidate(); };
  // How see-through: the map's background, the map image, the panels; and the interface size
  for (const [id, key] of [["bgOpacity", "bg"], ["mapOpacity", "map"], ["panelOpacity", "panel"], ["uiScale", "ui"], ["markerScale", "marker"]]) {
    const el = $(id), [min, max] = LOOK_RANGES[id];
    el.min = min; el.max = max;
    const show = () => {
      const v = look()[key];
      el.value = v;
      $(id + "Val").textContent = t("unit.percent", { n: v });
    };
    const apply = () => { settings.view[id] = +el.value; saveSettings(); show(); applyLook(COLORS.bg); invalidate(); };
    // (the size: applied on release - resizing the panel while dragging moves the slider under the pointer)
    if (key === "ui") { el.oninput = () => { $(id + "Val").textContent = t("unit.percent", { n: +el.value }); }; el.onchange = apply; }
    else el.oninput = apply;
    show();
  }
  $("fit").onclick = () => fit();

  // Theme: the page's colours (themes.css); the canvas' and the layer icons' read again. Map colours: its tint
  // (the theme's --map-filter) or the game's blue
  const themeBox = $("theme"), mapColorsBox = $("mapColors");
  const renderThemes = () => {
    themeBox.innerHTML = THEMES.map((n) => `<option value="${n}">${esc(t("theme." + n))}</option>`).join("");
    themeBox.value = themeName(settings.view.theme);
    mapColorsBox.innerHTML = ["theme", "game"].map((n) => `<option value="${n}">${esc(t("mapColors." + n))}</option>`).join("");
    mapColorsBox.value = settings.view.mapColors === "game" ? "game" : "theme";
  };
  renderThemes();
  themeBox.onchange = () => {
    settings.view.theme = themeName(themeBox.value); saveSettings();
    setThemeAttr(settings.view.theme); initColors(); applyLook(COLORS.bg); renderLayers(); invalidate();
  };
  mapColorsBox.onchange = () => { settings.view.mapColors = mapColorsBox.value; saveSettings(); invalidate(); };

  const langBox = $("lang");
  languageRenders = () => { renderThemes(); refreshStatus(); renderLevel(); renderPlayers(); renderTargets(); renderMotion(); renderLayers(); renderInspector(); renderMission(); invalidate(); };
  langBox.innerHTML = `<option value="auto" data-i18n="lang.auto"></option>` +
    Object.keys(CATALOG).map((c) => `<option value="${c}">${esc(CATALOG[c]["lang.name"] || c)}</option>`).join("");
  langBox.value = CATALOG[langPref] ? langPref : "auto";
  langBox.onchange = () => { setLanguage(langBox.value); languageChanged(); };

  // The Info tab's sections (Mission, Shops, Players): a click on the heading folds / unfolds one (its buttons do their own
  // thing) - remembered, like the Layers tab's categories
  const foldSection = (sec) => {
    const closed = settings.ui.closedInfo.includes(sec.dataset.sec);
    sec.classList.toggle("closed", closed);
    sec.querySelector(".isfold").innerHTML = icon(closed ? "chevronRight" : "chevronDown");
  };
  for (const sec of document.querySelectorAll(".isec")) {
    foldSection(sec);
    sec.querySelector(".ishead").addEventListener("click", (e) => {
      if (e.target.closest("button")) return;
      const key = sec.dataset.sec, list = settings.ui.closedInfo;
      settings.ui.closedInfo = list.includes(key) ? list.filter((k) => k !== key) : [...list, key];
      saveSettings();
      foldSection(sec);
    });
  }

  // Tabs, collapse
  for (const b of $("ptabs").querySelectorAll("button")) b.onclick = () => showPanelTab(b.dataset.ptab);
  showPanelTab(settings.ui.panelTab);
  // Folded or not: remembered (a refresh keeps it)
  const fold = (collapsed) => {
    $("panel").classList.toggle("collapsed", collapsed);
    $("collapse").innerHTML = icon(collapsed ? "chevronRight" : "chevronDown");
  };
  fold(!!settings.ui.panelCollapsed);
  $("collapse").onclick = () => {
    settings.ui.panelCollapsed = !settings.ui.panelCollapsed;
    saveSettings();
    fold(settings.ui.panelCollapsed);
    syncPanelToTop();
  };
  // The tab's content scrolling (scroll doesn't bubble: caught on the way down): its "back to top" button
  $("panel").addEventListener("scroll", (e) => { if (e.target.classList.contains("pscroll")) syncPanelToTop(); }, true);
  $("pToTop").onclick = () => { const list = panelScroller(); if (list) list.scrollTo({ top: 0, behavior: "smooth" }); };
}
