// Small DOM / HTML helpers.
import { prettyRaw } from "./model.js";

export const $ = (id) => document.getElementById(id);

export function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

/** One element, whatever the container; a made-up name: words, then a dim "?". */
export function nameHtml(o) {
  return o.raw ? `<span class="nm">${esc(prettyRaw(o.n).slice(0, -2))}&nbsp;<span class="raw">?</span></span>`
    : `<span class="nm">${esc(o.n || "?")}</span>`;
}

/** A game class name, as a made-up name: "WillowInteractiveObject" -> "Interactive Object" + dim "?". */
export function classHtml(c) { return c ? nameHtml({ n: c, raw: 1 }) : ""; } // prettyRaw drops "Willow"
