// Everything the page remembers, as one object in localStorage ("helios.settings", JSON):
//   layers: { <layer id>: { on, names, floors, size, range, ... } }   (model.js: LAYERS, LAYER_SETTINGS;
//           gear per rarity: "loot.common", "loot.rare"...; pickups per kind: "pickup.ammo"...)
//   view:   the map (zoom, follow, rotate, who, movement)
//   ui:     the page (language, open tabs, open layer panels, collapsed categories, what the drawer shows)
// Loading validates every value against the defaults (unknown / invalid ones are dropped), so the
// shape can change without breaking saved settings. Never throws: private mode, blocked storage
// or Node (the offline check) just get the defaults.
import { LAYERS, LAYER_SETTINGS } from "./model.js";

const KEY = "helios.settings";

export function layerDefaults(layer) {
  const out = layer.toggle === false ? {} : { on: layer.on };
  for (const k of layer.settings) out[k] = layer.defaults?.[k] ?? LAYER_SETTINGS[k].def;
  return out;
}

export function defaults() {
  return {
    layers: Object.fromEntries(LAYERS.filter((l) => !l.folder).map((l) => [l.id, layerDefaults(l)])), // folders: no settings
    view: {
      zoom: 0, // 0: never zoomed, fit the map
      follow: false, rotate: false,
      coords: false, // the world X / Y by the cursor (tooltip.js)
      target: "me", // "Who": "me" (the host) or a player's name
      // Movement: 0 = only redraw on a change (markers jump), a number = interpolated at most that
      // many fps, "smooth" = every frame. 30 by default: smooth enough, and lighter next to the game
      // (the compositor, the GPU) than the monitor's rate
      motion: 30,
      // how see-through the map's background / the map image / the panels are, % (look.js)
      bgOpacity: 100, mapOpacity: 100, panelOpacity: 90,
      uiScale: 100, // the interface size, % (70-200: look.js)
      markerScale: 100, // every map marker's size (and its label, bars), % (50-200: look.js)
      theme: "default", // the page's colours (look.js THEMES; themes.css)
    },
    ui: { lang: "auto", panelTab: "info", inspectorTab: "info", openLayers: [], closedGroups: [], showLockedMissions: false,
      missionGroup: "chain", missionGoal: "xp",
      missionFiltersClosed: false, // the mission list's filters folded away (more room for the list)
      panelCollapsed: false, // the left panel folded (its title row and the level only)
      closedInfo: [], // the Info tab's sections folded (their data-sec: "mission", "shops", "players")
      shopTab: "weapons", // the vending machines' tab (a machine kind: shops.py KINDS)
      // what the drawer shows, reopened on a refresh (ui/drawer.js): {} (closed), { k: "player", name },
      // { k: "mission", id } ("": the list), { k: "shops", id } ("": no machine first), { k: "detail", kind, id }
      drawer: {} },
  };
}

/** A layer setting's value, if valid for its schema (else undefined). */
function validSetting(key, v) {
  const s = LAYER_SETTINGS[key];
  if (key === "on" || s.type === "bool") return typeof v === "boolean" ? v : undefined;
  if (s.type === "choice") return s.options.includes(v) ? v : undefined;
  if (s.type === "range") return typeof v === "number" && isFinite(v) ? Math.min(s.max, Math.max(s.min, v)) : undefined;
  return undefined;
}

/** Saved settings (any shape) merged over the defaults: only known keys, only valid values. */
export function merge(saved) {
  const out = defaults();
  if (!saved || typeof saved !== "object") return out;
  for (const [id, cfg] of Object.entries(out.layers)) {
    const src = saved.layers?.[id];
    if (!src || typeof src !== "object") continue;
    for (const k of Object.keys(cfg)) {
      const v = validSetting(k, src[k]);
      if (v !== undefined) cfg[k] = v;
    }
  }
  for (const group of ["view", "ui"]) {
    for (const [k, def] of Object.entries(out[group])) {
      const v = saved[group]?.[k];
      if (v === undefined || v === null) continue;
      if (Array.isArray(def) ? Array.isArray(v) : typeof v === typeof def || (k === "motion" && ["number", "string"].includes(typeof v))) {
        out[group][k] = Array.isArray(def) ? v.filter((x) => typeof x === "string") : v;
      }
    }
  }
  return out;
}

/** The old one-key-per-setting storage ("helios.<key>"), read through get(key, default). */
export function fromLegacy(get) {
  const layers = {};
  const labels = get("labels", false), height = get("height", true);
  for (const l of LAYERS) {
    const cfg = layers[l.id] = {};
    const on = get("layer." + (l.legacy || l.id), null); // the old single Loot layer: every rarity
    if (typeof on === "boolean") cfg.on = on;
    if (labels && l.id !== "player") cfg.names = true; // the old global Names
    if (!height) cfg.floors = "show"; // the old global "Dim other floors" off
  }
  return {
    layers,
    view: {
      zoom: get("zoom", 0), follow: !!get("follow", false), rotate: !!get("rotate", false), target: get("target", "me"),
      motion: get("motion", get("smooth", true) ? "smooth" : 0),
    },
    ui: { lang: get("lang", null), panelTab: get("ptab", null), inspectorTab: get("tab", null) }, // only what was saved (null: the new default)
  };
}

function load() {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw !== null) return merge(JSON.parse(raw));
    const get = (k, d) => { const v = localStorage.getItem("helios." + k); return v === null ? d : JSON.parse(v); };
    return merge(fromLegacy(get));
  } catch {
    return defaults();
  }
}

export const settings = load();

let saveTimer = 0;
/** Writes the settings (debounced: sliders and zoom change many times a second). */
export function saveSettings() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(KEY, JSON.stringify(settings)); } catch { /* private mode */ }
  }, 250);
}

/** A layer's settings (the live object: change it, then saveSettings()). */
export const layerCfg = (id) => settings.layers[id];
