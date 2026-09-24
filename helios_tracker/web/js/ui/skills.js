// The inspector's Skills tab: one tab per tree, the game's grid layout.
import { esc, nameHtml } from "../dom.js";
import { num, t } from "../i18n.js";
import { cleanGameText as cleanText, nameText } from "../model.js";
import { icon } from "../icons.js";
import { S } from "../state.js";
import { tipAttrs } from "./hovertip.js";

export function skillsHtml(p) {
  if (!p.skills) return `<div class="note">${esc(t("why.skills." + (p.skillsWhy || "unavailable")))}</div>`;
  let html = "";
  // The trees with a layout: one tab each. The rest (the root branch: just the action skill) isn't
  // shown - unless no tree has a layout, then everything is listed as a fallback
  const trees = p.skills.filter((b) => b.tiers && b.tiers.length && !b.root);
  if (trees.length) {
    const most = trees.reduce((best, b, i) => (b.pts > trees[best].pts ? i : best), 0);
    const sel = S.skillTab == null ? most : Math.min(Math.max(0, S.skillTab), trees.length - 1);
    html += `<div class="stabs">` + trees.map((b, i) =>
      `<button data-stab="${i}" class="${i === sel ? "on" : ""}" title="${esc(nameText(b))}">` +
      `${b.n ? nameHtml(b) : `<span class="nm">${esc(t("skills.other"))}</span>`}` +
      `<span class="spts">· ${esc(num(b.pts))}</span></button>`).join("") + `</div>`;
    html += `<div class="branch">${skillGrid(trees[sel], sel)}</div>`;
  }
  for (const b of trees.length ? [] : p.skills) {
    html += `<div class="branch"><div class="bhead">${b.n ? nameHtml(b) : esc(t("skills.other"))}<span class="bpts">${esc(t("skills.pts", { n: b.pts }))}</span></div>`;
    for (const sk of b.skills) {
      const pips = Array.from({ length: Math.max(sk.m, 0) }, (_, i) => `<i class="${i < sk.g ? "on" : ""}"></i>`).join("");
      html += `<div class="skill${sk.g ? "" : " zero"}"${tipAttrs(nameText(sk), t("skills.rank", { n: sk.g, m: sk.m }), cleanText(sk.d))}>` +
        `<span class="tier">${esc(t("skills.tier", { n: sk.t }))}</span><span class="sname">${nameHtml(sk)}</span>` +
        `<span class="pips">${pips}</span><span class="muted">${sk.g}/${sk.m}</span></div>`;
    }
    html += "</div>";
  }
  return html;
}

/** A tree's grid, coloured as its place (index: 0 left - green, 1 middle - blue, 2 right - red, like the game),
 *  filled with its colour from the top down to its last unlocked tier, like the game's (a screenshot: 11 points
 *  = 3 of 6 rows, 8 = 2, 26 = all - each tier needs its predecessors' points, tier.need, 5 in BL2; not the
 *  points / every skill's max ranks: ~90, when 25 reach the last tier) - but none with no point in the tree
 *  (its first tier is open, nothing's in it). Greyscale below. */
function skillGrid(b, index) {
  const cols = Math.max(1, ...b.tiers.map((tier) => tier.cells.length));
  let unlocked = 0, needed = 0;
  for (const tier of b.tiers) {
    if (b.pts >= needed) unlocked++;
    needed += tier.need;
  }
  const rows = b.tiers.length;
  if (!b.pts) unlocked = 0;
  // the edge: in the middle of the gap under the last unlocked row - every row the same height (drawer.css), the
  // grid's 5 px padding and 4 px gaps: 3px + unlocked x (100% - 6px) / rows; none / all: 0 / 100 %
  const fill = !unlocked ? "0%" : unlocked >= rows ? "100%" : `calc(3px + ${unlocked} * (100% - 6px) / ${rows})`;
  let need = 0, html = `<div class="sgrid tree${Math.min(index, 2)}" style="grid-template-columns: repeat(${cols}, 1fr);` +
    ` --fill: ${fill}"${tipAttrs("", t("skills.tiers", { n: unlocked, m: rows, pts: num(b.pts) }))}>`;
  for (const tier of b.tiers) {
    const locked = b.pts < need; // points in this branch needed to reach the tier
    for (let c = 0; c < cols; c++) {
      const sk = tier.cells[c];
      if (!sk) { html += `<div class="scell empty"></div>`; continue; }
      const pips = Array.from({ length: Math.max(sk.m, 0) }, (_, i) => `<i class="${i < sk.g ? "on" : ""}"></i>`).join("");
      // maxed / points in it (an outline: done / in progress) / none; locked (its tier out of reach: greyed, a
      // lock) or open (points can go in now: not maxed, its tier reached)
      const maxed = sk.m > 0 && sk.g >= sk.m;
      const state = maxed ? "maxed invested" : sk.g ? "invested" : "zero";
      const cls = ["scell", state, locked ? "locked" : maxed ? "" : "open"].filter(Boolean).join(" ");
      const tip = t(locked ? "skills.locked" : maxed ? "skills.maxed" : "skills.open");
      html += `<div class="${cls}"${tipAttrs(nameText(sk), `${t("skills.rank", { n: sk.g, m: sk.m })} · ${tip}`, cleanText(sk.d))}>` +
        (locked ? `<span class="slock">${icon("lock")}</span>` : "") + `<div class="sn">${nameHtml(sk)}</div>` +
        `<div class="sg"><span class="pips">${pips}</span><span>${sk.g}/${sk.m}</span></div></div>`;
    }
    need += tier.need;
  }
  return html + "</div>";
}
