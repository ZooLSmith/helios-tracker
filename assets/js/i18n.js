// Translations, the tracker page's way (its js/i18n.js): catalogs in ../i18n/, t("key", {vars}) with English
// fallback. The pages hold no text: their elements name a key and applyI18n fills them -
//   data-i18n             the element's content (HTML: the catalogs are ours, with links and <strong> in them);
//                         an empty string hides it (.i18n-empty: a note only one language needs)
//   data-i18n-title / -label / -placeholder / -content / -alt   the title / aria-label / placeholder / content / alt
// The language: the visitor's pick (localStorage), "auto" = the first of the browser's that the site has.
import CATALOG from "../i18n/index.js";

export { CATALOG };
const KEY = "helios.site.lang";

function stored() {
  try { return localStorage.getItem(KEY) || "auto"; } catch { return "auto"; } // (private mode)
}

function pickLang(pref) {
  if (pref !== "auto" && CATALOG[pref]) return pref;
  for (const l of navigator.languages?.length ? navigator.languages : [navigator.language || "en"]) {
    const base = String(l).toLowerCase().split("-")[0];
    if (CATALOG[base]) return base;
  }
  return "en";
}

export let langPref = CATALOG[stored()] ? stored() : "auto";
export let lang = pickLang(langPref);

/** Switches language (a code or "auto"), remembers it and re-translates the page ("i18n" event: what the site
 *  built itself from the text - the questionnaire's trail, the search's index - follows it). */
export function setLanguage(pref) {
  langPref = pref;
  lang = pickLang(pref);
  try { localStorage.setItem(KEY, pref); } catch { /* this visit only */ }
  applyI18n();
}

export function t(key, vars) {
  let text = (CATALOG[lang] || {})[key] ?? CATALOG.en[key] ?? key;
  if (vars) text = text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return text;
}

const ATTRS = [["i18nTitle", "title"], ["i18nLabel", "aria-label"], ["i18nPlaceholder", "placeholder"], ["i18nContent", "content"], ["i18nAlt", "alt"]];

/** Translates a document (this page, or one the search fetched). */
export function applyI18n(doc = document) {
  doc.documentElement.lang = lang;
  for (const el of doc.querySelectorAll("[data-i18n]")) {
    const text = t(el.dataset.i18n);
    el.innerHTML = text;
    el.classList.toggle("i18n-empty", !text); // (not .hidden: the questionnaire's data-when owns that)
  }
  for (const [data, attr] of ATTRS) {
    for (const el of doc.querySelectorAll(`[data-${data.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase())}]`)) el.setAttribute(attr, t(el.dataset[data]));
  }
  if (doc === document) {
    doc.documentElement.classList.add("i18n"); // (site.css: the page shows once it has its text)
    doc.dispatchEvent(new Event("i18n"));
  }
}
