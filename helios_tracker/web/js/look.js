// How the page looks: how see-through the map's background, the map image and the panels are
// (%) and the interface's size - the Settings tab (in OBS: its browser source's "Interact" window).
// The map textures are cut out already (transparent outside the playable area, no baked background
// - checked on the game's files): background 0 % leaves only the level's shape, and the page itself
// transparent (OBS shows the scene through; a normal browser tab never does).
import { settings } from "./settings.js";

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, Math.round(v)));
// Each setting's range, % (the panels never fully clear: their text needs something behind it)
export const LOOK_RANGES = { bgOpacity: [0, 100], mapOpacity: [0, 100], panelOpacity: [20, 100], uiScale: [70, 200],
  markerScale: [50, 200] };
const DEFAULTS = { bgOpacity: 100, mapOpacity: 100, panelOpacity: 90, uiScale: 100, markerScale: 100 };

/** The settings, clamped to their ranges: { bg, map, panel, ui, marker } in % (marker: every map
 *  marker's size - on top of its layer's own - with its label, bars, rings). */
export function look() {
  const v = (key) => clamp(settings.view[key] ?? DEFAULTS[key], ...LOOK_RANGES[key]);
  return { bg: v("bgOpacity"), map: v("mapOpacity"), panel: v("panelOpacity"), ui: v("uiScale"), marker: v("markerScale") };
}

/** "#0b1116" + 0.4 -> "rgba(11, 17, 22, 0.4)". */
export function withAlpha(hex, alpha) {
  const n = parseInt(String(hex).trim().replace("#", ""), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const PANEL_RGB = "#0c1319"; // the panels' colour (base.css --panel's, at the panels' opacity)

/** The page's own background (behind the canvas: as see-through as the map's), the panels'
 *  background (the left panel, the drawer, the tooltips, the status), and the interface size (CSS
 *  zoom on the panel, the drawer, the status: not the canvas - its mouse coordinates would be off;
 *  e.g. Steam's overlay browser has no zoom of its own). */
export function applyLook(bgColor) {
  if (typeof document === "undefined") return;
  const lk = look(), root = document.documentElement.style;
  root.setProperty("--page-bg", withAlpha(bgColor, lk.bg / 100));
  root.setProperty("--panel", withAlpha(PANEL_RGB, lk.panel / 100));
  root.setProperty("--ui-zoom", String(lk.ui / 100));
}
