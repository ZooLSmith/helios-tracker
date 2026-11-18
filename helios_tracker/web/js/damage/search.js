// The damage log's search: every word of a query in a line's text - its actors' names, what with, the element's name,
// its tags (crit, kill...) as shown -, case and accents ignored. Reusable by any damage view: searchWords(query) once,
// then hitMatches / eventMatches / nameMatches per line.
import { foldText } from "../missions.js";
import { prettyRaw } from "../model.js";
import { t } from "../i18n.js";
import { FLAG } from "./store.js";

/** A query's words, folded (none: everything matches). */
export const searchWords = (query) => foldText(query).split(/\s+/).filter(Boolean);

const defText = (def) => (def ? (def.raw ? prettyRaw(def.n) : def.n || "") : "");
const all = (words, text) => words.every((w) => text.includes(w));

// (the words of a hit's tags: their names as shown)
const TAG_KEYS = [[FLAG.HEAL, "dmg.heal"], [FLAG.KILL, "dmg.kill"], [FLAG.CRIT, "dmg.crit"], [FLAG.DOWNED, "dmg.downed"], [FLAG.WIND, "dmg.wind"],
  [FLAG.EFFECT, "dmg.effect"], [FLAG.TICK, "dmg.tick"]];

/** An actor's name (folded): one def -> its text, cached per definition object. */
const folded = new WeakMap();
function nameOf(def) {
  if (!def) return "";
  let s = folded.get(def);
  if (s === undefined) folded.set(def, s = foldText(defText(def)));
  return s;
}

export function nameMatches(words, def) { return !words.length || all(words, nameOf(def)); }

export function hitMatches(words, store, h) {
  if (!words.length) return true;
  const el = store.elements.get(h.e);
  const text = [nameOf(store.actors.get(h.a)), nameOf(store.actors.get(h.v)), nameOf(store.whats.get(h.w)),
    foldText(el?.eln || ""), ...TAG_KEYS.filter(([bit]) => h.f & bit).map(([, key]) => foldText(t(key)))].join(" ");
  return all(words, text);
}

export function eventMatches(words, store, e, label) {
  if (!words.length) return true;
  const text = [nameOf(store.actors.get(e.actor)), nameOf(store.actors.get(e.other)),
    e.kind === "fx+" || e.kind === "fx-" ? nameOf(store.whats.get(e.rest[1])) : "", e.kind === "level" ? foldText(e.rest[0]) : "",
    foldText(label)].join(" ");
  return all(words, text);
}
