// The panel's Layers tab: categories (plain headings that fold), a row per layer (enabled, count, settings) and
// its settings panel under it, built from model.js's LAYER_SETTINGS. A folder layer (Gear,
// Pickups, Containers) is a row that folds / turns on and off the layers under it. Rebuilt on any
// structural change (fold, open / close, language); one set of delegated handlers on #layers.
import { $, esc } from "../dom.js";
import { t } from "../i18n.js";
import { icon } from "../icons.js";
import { LAYERS, LAYER_GROUPS, LAYER_SETTINGS, layerInGame, layerNameKey } from "../model.js";
import { invalidate } from "../scheduler.js";
import { layerCfg, saveSettings, settings } from "../settings.js";
import { S } from "../state.js";
import { tipAttrs } from "./hovertip.js";

// The layer's marker as drawn on the map (12 px SVG)
function layerIcon(l) {
  const c = l.color, o = `style="stroke: var(--map-outline)" stroke-width="1"`;
  const triangle = `<polygon points="6,1.5 10.5,9.5 1.5,9.5" fill="${c}" ${o}/>`;
  const dot = `<circle cx="6" cy="6" r="3.5" fill="${c}" ${o}/>`;
  // mission items, quest givers: the map's small "!" badge (a disc with a dark "!")
  const bang = `<circle cx="6" cy="6" r="5" fill="${c}" ${o}/><rect x="5.25" y="2.6" width="1.5" height="4.4" rx=".5" style="fill: var(--map-ink)"/>` +
    `<circle cx="6" cy="8.8" r=".85" style="fill: var(--map-ink)"/>`;
  // money: the map's "$" disc
  const coin = `<circle cx="6" cy="6" r="5" fill="${c}" ${o}/><text x="6" y="6.4" text-anchor="middle" dominant-baseline="middle" ` +
    `font-size="8" font-weight="700" font-family="'Segoe UI', system-ui, sans-serif" style="fill: var(--map-ink)">$</text>`;
  const shape = l.rarity ? triangle : l.id === "pickup.mission" || l.id === "giver" ? bang : l.id === "pickup.cash" ? coin
    : l.id.startsWith("pickup") ? dot : {
    player: `<polygon points="6,1 10.3,10.8 6,8.3 1.7,10.8" fill="${c}" ${o}/>`,
    enemy: `<polygon points="6,1 11,6 6,11 1,6" fill="${c}" ${o}/>`,
    npc: `<circle cx="6" cy="6" r="3.9" fill="none" style="stroke: var(--map-outline-soft)" stroke-width="2.3"/><circle cx="6" cy="6" r="3.9" fill="none" stroke="${c}" stroke-width="1.3"/>`,
    vehicle: `<rect x="1.5" y="1.5" width="9" height="9" fill="${c}" ${o}/>`,
    objective: `<polygon points="6,1 11,6 6,11 1,6" fill="${c}" ${o}/><circle cx="6" cy="6" r="1.5" style="fill: var(--map-ink)"/>`,
    gear: triangle,
    chest: `<rect x="0.5" y="0.5" width="11" height="11" fill="${c}" ${o}/>`,
    weaponchest: `<rect x="1.5" y="1.5" width="9" height="9" fill="${c}" ${o}/>`,
    other: `<rect x="3.5" y="3.5" width="5" height="5" fill="${c}" ${o}/>`,
    vaultsymbol: `<circle cx="6" cy="6" r="4" fill="none" stroke="${c}" stroke-width="2"/><circle cx="6" cy="6" r="1.4" fill="${c}"/>`,
    // what explodes: the map's burst
    explosive: `<polygon points="6.00,0.40 7.40,3.58 10.85,3.20 8.80,6.00 10.85,8.80 7.40,8.42 6.00,11.60 4.60,8.42 1.15,8.80 3.20,6.00 1.15,3.20 4.60,3.58" fill="${c}" ${o} stroke-linejoin="round"/>`,
    // an oxygen source: the map's diamond with a white "O2"
    oxygen: `<polygon points="6,0.2 11.8,6 6,11.8 0.2,6" fill="${c}" ${o}/><text x="5.2" y="6.4" text-anchor="middle" ` +
      `dominant-baseline="middle" font-size="5.8" font-weight="700" font-family="'Segoe UI', system-ui, sans-serif" fill="#fff">O` +
      `<tspan font-size="3.8" dy="1.3">2</tspan></text>`,
    looted: `<rect x="3.5" y="3.5" width="5" height="5" fill="${c}" opacity=".6" ${o}/>`,
  }[l.id] || `<rect x="2.5" y="2.5" width="7" height="7" fill="${c}" ${o}/>`; // containers, vendors, stations
  return `<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">${shape}</svg>`;
}

const optionText = (key, v) => (key === "range" ? (v ? t("unit.meters", { n: v }) : t("set.range.0")) : t(`set.${key}.${v}`));
const layerName = (l) => esc(t(layerNameKey(l)));
const foldKey = (id) => "layer:" + id; // a folder's entry in ui.closedGroups (next to the categories')

function settingHtml(l, key) {
  const s = LAYER_SETTINGS[key], v = layerCfg(l.id)[key], name = esc(t("set." + key));
  const attrs = `data-layer="${l.id}" data-set="${key}"`;
  if (key === "nameSize" && l.settings.includes("names")) return ""; // (on the Names row: below)
  if (key === "names" && l.settings.includes("nameSize")) {
    // Names and their size on one row: the box, then the size's slider (no label: its tooltip says it)
    const size = layerCfg(l.id).nameSize, sizeAttrs = `data-layer="${l.id}" data-set="nameSize"`;
    return `<div class="cset"><label class="row cnames"><input type="checkbox" ${attrs}${v ? " checked" : ""}><span>${name}</span></label>` +
      `<input type="range" ${sizeAttrs} min="${LAYER_SETTINGS.nameSize.min}" max="${LAYER_SETTINGS.nameSize.max}" ` +
      `step="${LAYER_SETTINGS.nameSize.step}" value="${size}"${tipAttrs("", t("set.nameSize"))}>` +
      `<span class="cval">${esc(t("unit.percent", { n: size }))}</span></div>`;
  }
  if (s.type === "bool") {
    return `<label class="row cset"><input type="checkbox" ${attrs}${v ? " checked" : ""}><span>${name}</span></label>`;
  }
  if (s.type === "range") {
    return `<div class="cset"><span class="clabel">${name}</span><input type="range" ${attrs} min="${s.min}" max="${s.max}" step="${s.step}" value="${v}">` +
      `<span class="cval">${esc(t("unit.percent", { n: v }))}</span></div>`;
  }
  if (s.select) {
    return `<div class="cset"><span class="clabel">${name}</span><select ${attrs}>` +
      s.options.map((o) => `<option value="${o}"${o === v ? " selected" : ""}>${esc(optionText(key, o))}</option>`).join("") + `</select></div>`;
  }
  return `<div class="cset"${s.tip ? ` title="${esc(t(s.tip))}"` : ""}><span class="clabel">${name}</span><span class="seg">` +
    s.options.map((o) => `<button ${attrs} data-value="${o}" class="${o === v ? "on" : ""}">${esc(optionText(key, o))}</button>`).join("") +
    `</span></div>`;
}

function folderHtml(l) {
  const closed = settings.ui.closedGroups.includes(foldKey(l.id));
  const children = LAYERS.filter((c) => c.parent === l.id && layerInGame(c, S.level?.game));
  return `<div class="lrow lfolder"><label class="row"><input type="checkbox" class="lbox" data-folder="${l.id}">` +
    `<span class="sw">${layerIcon(l)}</span><span class="lname">${layerName(l)}</span><span class="count" data-count="${l.id}"></span></label>` +
    `<button class="lcfg" data-fold="${foldKey(l.id)}">${icon(closed ? "chevronRight" : "chevronDown")}</button></div>` +
    (closed ? "" : `<div class="lsub">${children.map(rowHtml).join("")}</div>`);
}

function rowHtml(l) {
  if (l.folder) return folderHtml(l);
  const cfg = layerCfg(l.id), open = settings.ui.openLayers.includes(l.id);
  const check = l.toggle === false ? `<span class="nocheck"></span>` // can't be hidden: settings only
    : `<input type="checkbox" data-layer="${l.id}" data-set="on"${cfg.on ? " checked" : ""}>`;
  const tip = l.tip ? ` title="${esc(t(l.tip))}"` : "";
  return `<div class="lrow${open ? " open" : ""}"><label class="row"${tip}>${check}<span class="sw">${layerIcon(l)}</span>` +
    `<span class="lname">${layerName(l)}</span><span class="count" data-count="${l.id}"></span></label>` +
    `<button class="lcfg" data-open="${l.id}" title="${esc(t("layers.configure"))}">${icon("tune")}</button></div>` +
    (open ? `<div class="lcfgbox">${l.settings.map((k) => settingHtml(l, k)).join("")}</div>` : "");
}

export function renderLayers() {
  const box = $("layers");
  box.innerHTML = LAYER_GROUPS.map((g) => {
    const closed = settings.ui.closedGroups.includes(g);
    return `<div class="lgroup${closed ? " closed" : ""}"><div class="lghead" data-fold="${g}">` +
      `<span class="lgname">${esc(t("lgroup." + g))}</span><span class="lgfold">${icon(closed ? "chevronRight" : "chevronDown")}</span></div>` +
      `<div class="lgbody">${LAYERS.filter((l) => l.group === g && !l.parent && layerInGame(l, S.level?.game)).map(rowHtml).join("")}</div></div>`;
  }).join("");
  syncBoxes();
  invalidate(); // the counts are filled by the next frame
}

// The layers a folder's box turns on and off
const boxLayers = (box) => LAYERS.filter((l) => l.toggle !== false && !l.folder && l.parent === box.dataset.folder);

function syncBoxes() { // checked: every layer on; indeterminate: some
  for (const box of $("layers").querySelectorAll(".lbox")) {
    const ons = boxLayers(box).map((l) => layerCfg(l.id).on);
    box.checked = ons.every(Boolean);
    box.indeterminate = !box.checked && ons.some(Boolean);
  }
}

function setLayersOn(layers, on) {
  for (const l of layers) if (l.toggle !== false && !l.folder) layerCfg(l.id).on = on;
  saveSettings();
  renderLayers();
}

const toggleIn = (list, item) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

export function initLayers() {
  const box = $("layers");
  box.addEventListener("click", (e) => {
    const el = e.target.closest("[data-open], [data-fold], button[data-value]");
    if (!el) return;
    if (el.dataset.open) settings.ui.openLayers = toggleIn(settings.ui.openLayers, el.dataset.open);
    else if (el.dataset.fold) settings.ui.closedGroups = toggleIn(settings.ui.closedGroups, el.dataset.fold);
    else { // a choice
      const s = LAYER_SETTINGS[el.dataset.set];
      layerCfg(el.dataset.layer)[el.dataset.set] = s.options.find((o) => String(o) === el.dataset.value);
    }
    saveSettings();
    renderLayers();
  });
  box.addEventListener("change", (e) => {
    const el = e.target;
    if (el.classList.contains("lbox")) { setLayersOn(boxLayers(el), el.checked); return; }
    const { layer, set } = el.dataset;
    if (!layer) return;
    const s = LAYER_SETTINGS[set];
    layerCfg(layer)[set] = el.type === "checkbox" ? el.checked : s.options.find((o) => String(o) === el.value);
    saveSettings();
    syncBoxes();
    invalidate();
  });
  box.addEventListener("input", (e) => { // a slider, while it's dragged: no rebuild
    const el = e.target;
    if (el.type !== "range") return;
    layerCfg(el.dataset.layer)[el.dataset.set] = +el.value;
    el.nextElementSibling.textContent = t("unit.percent", { n: +el.value });
    saveSettings();
    invalidate();
  });

  $("layersAll").onclick = () => setLayersOn(LAYERS, true);
  $("layersNone").onclick = () => setLayersOn(LAYERS, false);
  // Collapse: every layer's settings closed, every category and folder folded
  $("layersClose").onclick = () => {
    settings.ui.openLayers = [];
    settings.ui.closedGroups = [...LAYER_GROUPS, ...LAYERS.filter((l) => l.folder).map((l) => foldKey(l.id))];
    saveSettings();
    renderLayers();
  };
  renderLayers();
}
