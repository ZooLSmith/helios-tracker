// Translations: catalogs in ../i18n/; t("key", {vars}) with English fallback, numbers formatted
// per language. Static HTML uses data-i18n / data-i18n-title (applyI18n).
import CATALOG from "../i18n/index.js";
import { saveSettings, settings } from "./settings.js";

export { CATALOG };
export let langPref = settings.ui.lang; // "auto" = the browser's
export let lang = pickLang(langPref);

function pickLang(pref) {
  if (pref !== "auto" && CATALOG[pref]) return pref;
  const langs = typeof navigator === "undefined" ? [] : navigator.languages || [navigator.language || "en"];
  for (const l of langs) {
    const base = String(l).toLowerCase().split("-")[0];
    if (CATALOG[base]) return base;
  }
  return "en";
}

/** Switches language (a code or "auto"), remembers it and re-translates the static HTML. */
export function setLanguage(pref) {
  langPref = pref;
  lang = pickLang(pref);
  settings.ui.lang = pref;
  saveSettings();
  applyI18n();
}

// The game the mod runs in ("tps": the Pre-Sequel - the level message's "game", data.js): a label with a twin for it
// ("group.relic.tps": "OZ KITS", the Pre-Sequel's own word - its Oz kits are BL2's relics' class) uses the twin
let variant = "";
export function setVariant(game) { variant = game || ""; }

export function t(key, vars, fallback) {
  const alt = variant ? (CATALOG[lang] || {})[`${key}.${variant}`] ?? (CATALOG.en || {})[`${key}.${variant}`] : undefined;
  let text = alt ?? (CATALOG[lang] || {})[key] ?? (CATALOG.en || {})[key] ?? fallback ?? key;
  if (vars) text = text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? (typeof vars[k] === "number" ? num(vars[k]) : vars[k]) : m));
  return text;
}

export const num = (n, digits = 0) => new Intl.NumberFormat(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
/** Cash: "$ 1,234" - a narrow no-break space after the "$" (thin, and never on another line than the number;
 *  the "$" drawn from the fallback font: base.css). */
export const money = (n) => "$\u202f" + num(n);
/** A number with at most `digits` decimals, no trailing zeros ("0.4", "12"). */
export const numUpTo = (n, digits) => new Intl.NumberFormat(lang, { maximumFractionDigits: digits }).format(n);
/** A number short when it's big (10,000 and up: "1.7M", "850K" - the language's own compact form), else in full. */
export const numShort = (n) => (Math.abs(n) >= 10000
  ? new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 }).format(n) : num(n));

export function applyI18n() {
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-title]")) el.title = t(el.dataset.i18nTitle);
}
