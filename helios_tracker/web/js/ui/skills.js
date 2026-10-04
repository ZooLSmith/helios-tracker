// The inspector's Skills tab: one tab per tree, the game's grid layout.
import { esc, nameHtml } from "../dom.js";
import { num, numUpTo, t } from "../i18n.js";
import { cleanGameText as cleanText, nameText } from "../model.js";
import { icon } from "../icons.js";
import { S } from "../state.js";
import { tipAttrs, tipSections } from "./hovertip.js";

/** A skill's stat line as the game shows it (inspector.py _skill_stats: the game's text and value): the value
 *  (x 100 as a percentage; always positive / its own sign, a "+" unless told not to; rounded to an int, or to
 *  its precision) dropped into the text's $NUMBER$ (else before it). */
export function skillStatText(f) {
  const [before, number, after] = skillStatParts(f);
  return before + number + after;
}

/** skillStatText in parts: [the text before the value, the value, the text after] - the value emphasised
 *  apart (the BONUSES). No value shown (bDontDisplayNumber): ["the text", "", ""]. */
export function skillStatParts(f) {
  let number;
  if (f.dv != null) { // the number as the game shows it, worked out by the mod (a game's card lines: its profile's card_line_value)
    const n = num(f.pos ? Math.abs(f.dv) : f.dv, f.dp || 0);
    number = `${f.dv > 0 && !f.np ? "+" : ""}${f.pct ? t("unit.percent", { n }) : n}`;
  } else {
    // an item's line tied to one of its attributes: that attribute's current value (the shot cost: 2, not the +1)
    let v = f.cur != null ? f.cur : f.inv && f.v ? 1 / f.v : f.v;
    if (f.pct && f.cur == null) v *= 100;
    if (f.pos) v = Math.abs(v);
    const n = f.fl ? numUpTo(v, f.fp ?? 1) : num(Math.round(v));
    const plus = v > 0 && !f.np ? "+" : "";
    number = `${plus}${f.pct && f.cur == null ? t("unit.percent", { n }) : n}`;
  }
  // the prefix / suffix around the value (game text: "Consumes" 2 "ammo per shot."), a space on each side
  const pre = f.pre ? cleanText(f.pre) + " " : "", suf = f.suf ? " " + cleanText(f.suf) : "";
  const text = cleanText(f.d);
  if (f.nn) return [text.replace(/\$NUMBER\$\s*/g, "").trim(), "", ""];
  const at = text.indexOf("$NUMBER$");
  if (at < 0) return [pre, number, suf + (text ? " " + text : "")];
  return [text.slice(0, at) + pre, number, suf + text.slice(at + "$NUMBER$".length).replace(/\$NUMBER\$/g, number)];
}

/** A skill's tooltip, in sections: its rank and state; its stats now; "Next level" and the next rank's (what a
 *  point would give); its description. */
function skillTip(sk, state) {
  // an item's bonus ranks, per item like the game's: "+2 skill points from <the class mod>" - only once the skill
  // has a point of its own (said when it has none)
  const bonus = (sk.bs || []).map(([n, item]) => (item ? t("skills.bonusFrom", { n, item }) : t("skills.bonus", { n })));
  if (bonus.length && !sk.g) bonus.push(t("skills.bonusNeedsPoint"));
  return tipSections(nameText(sk), [
    { kind: "meta", lines: [`${t("skills.rank", { n: sk.g, m: sk.m })} · ${state}`] },
    { kind: "meta bonus", lines: bonus },
    { kind: "stats", lines: (sk.fx || []).map(skillStatParts) }, // (the values emphasised)
    { kind: "stats next", head: t("skills.next"), lines: (sk.fxn || []).map(skillStatParts) },
    { kind: "desc", lines: [cleanText(sk.d)] },
  ]);
}

/** The bonuses of every invested skill, added up: the lines of the same stat (the same game text and display)
 *  summed - "Gun Damage" from three skills: one total - in the order they first come (tree by tree). A sum:
 *  the game combines some modifiers differently (scales vs. adds), so it's a guide. */
export function bonusLines(trees, parts = false) {
  const sums = new Map();
  for (const b of trees) {
    const skills = b.tiers ? b.tiers.flatMap((tier) => tier.cells) : b.skills || [];
    for (const sk of skills) {
      if (!sk || !(sk.g > 0)) continue; // (an item's bonus ranks count only with a point of its own)
      for (const f of sk.fx || []) {
        const { v, ...look } = f;
        const key = JSON.stringify(look);
        const line = sums.get(key);
        if (line) line.v += v; else sums.set(key, { ...f });
      }
    }
  }
  return [...sums.values()].map(parts ? skillStatParts : skillStatText);
}

function recapHtml(trees) {
  const lines = bonusLines(trees, true); // (in parts: only the value emphasised)
  return lines.length ? `<div class="group">${esc(t("skills.recap"))}</div>` +
    `<div class="srecap">${lines.map(([before, value, after]) =>
      `<div class="srline">${esc(before)}${value ? `<b class="sval">${esc(value)}</b>` : ""}${esc(after)}</div>`).join("")}</div>` : "";
}

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
      `<button data-stab="${i}" class="tree${Math.min(i, 2)}${i === sel ? " on" : ""}" title="${esc(nameText(b))}">` + // (its tree's colour)
      `${b.n ? nameHtml(b) : `<span class="nm">${esc(t("skills.other"))}</span>`}` +
      `<span class="spts">· ${esc(num(b.pts))}</span></button>`).join("") + `</div>`;
    html += `<div class="branch">${skillGrid(trees[sel], sel)}</div>`;
    html += recapHtml(trees); // under the tabs and the grid: the bonuses of every tree, added up
  }
  for (const b of trees.length ? [] : p.skills) {
    html += `<div class="branch"><div class="bhead">${b.n ? nameHtml(b) : esc(t("skills.other"))}<span class="bpts">${esc(t("skills.pts", { n: b.pts }))}</span></div>`;
    for (const sk of b.skills) {
      const pips = Array.from({ length: Math.max(sk.m, 0) }, (_, i) => `<i class="${i < sk.g ? "on" : ""}"></i>`).join("");
      html += `<div class="skill${sk.g ? "" : " zero"}"${skillTip(sk, t(sk.m > 0 && sk.g >= sk.m ? "skills.maxed" : "skills.open"))}>` +
        `<span class="tier">${esc(t("skills.tier", { n: sk.t }))}</span><span class="sname">${nameHtml(sk)}</span>` +
        `<span class="pips">${pips}</span><span class="muted">${sk.g}/${sk.m}</span></div>`;
    }
    html += "</div>";
  }
  return html;
}

/** A tree's grid, coloured as its place (index: 0 left - green, 1 middle - blue, 2 right - red, like the game),
 *  filled with its colour from the top down by its points, like the game's: its points over the points that unlock
 *  its last tier (every earlier tier's need: 25 in BL2) - full when the capstone opens. The user's samples, in game
 *  (6 rows): 5 points = just past the first row (1.2), 8 = 2 rows (1.9), 11 = 3 (2.6), 12 = the bottom of the 3rd
 *  (2.9), 26 = all; 0: none. Greyscale below. (Not by tiers unlocked, nor per row by the next tier's 5: 12 showed
 *  mid-row 3.) */
function skillGrid(b, index) {
  const cols = Math.max(1, ...b.tiers.map((tier) => tier.cells.length));
  let unlocked = 0, needed = 0, toLast = 0;
  b.tiers.forEach((tier, i) => {
    if (b.pts >= needed) unlocked++;
    if (i === b.tiers.length - 1) toLast = needed; // (the points its last tier needs)
    needed += tier.need;
  });
  const rows = b.tiers.length;
  if (!b.pts) unlocked = 0;
  const frac = toLast > 0 ? Math.min(1, Math.max(0, b.pts / toLast)) : unlocked >= rows ? 1 : 0;
  // the edge: the grid's 5 px padding (3px: in its gaps) + that share of the rest; none / all: 0 / 100 %
  const fill = frac <= 0 ? "0%" : frac >= 1 ? "100%" : `calc(3px + ${+frac.toFixed(4)} * (100% - 6px))`;
  // half-width columns, each cell two of them: a row with fewer cells than the grid's columns centred (BL1's trees: two
  // columns, their last tier one skill - in the middle, as the game's; BL2's rows: every column, empty ones too)
  let need = 0, html = `<div class="sgrid tree${Math.min(index, 2)}" style="grid-template-columns: repeat(${cols * 2}, 1fr);` +
    ` --fill: ${fill}"${tipAttrs("", t("skills.tiers", { n: unlocked, m: rows, pts: num(b.pts) }))}>`;
  for (const tier of b.tiers) {
    const locked = b.pts < need; // points in this branch needed to reach the tier
    const short = tier.cells.length < cols; // (centred: its first cell that many half-columns in)
    for (let c = 0; c < (short ? tier.cells.length : cols); c++) {
      const sk = tier.cells[c];
      const at = short && c === 0 ? ` style="grid-column: ${cols - tier.cells.length + 1} / span 2"` : "";
      if (!sk) { html += `<div class="scell empty"${at}></div>`; continue; }
      const pips = Array.from({ length: Math.max(sk.m, 0) }, (_, i) => `<i class="${i < sk.g ? "on" : ""}"></i>`).join("");
      // maxed / points in it (an outline: done / in progress) / none; locked (its tier out of reach: greyed, a
      // lock) or open (points can go in now: not maxed, its tier reached)
      const maxed = sk.m > 0 && sk.g >= sk.m;
      const state = maxed ? "maxed invested" : sk.g ? "invested" : "zero";
      // boosted: an item gives it bonus ranks (counting or not yet): a second, blue outline like the game's
      const cls = ["scell", state, locked ? "locked" : maxed ? "" : "open", sk.b ? "boosted" : ""].filter(Boolean).join(" ");
      const tip = t(locked ? "skills.locked" : maxed ? "skills.maxed" : "skills.open");
      html += `<div class="${cls}"${at}${skillTip(sk, tip)}>` +
        (locked ? `<span class="slock">${icon("lock")}</span>` : "") +
        // its icon (the game's, from the mod: /icon/...png) - greyed until it has points, like the game's; tinted
        // with its tree's colour through a layer masked by the icon itself (--ic)
        (sk.ic ? `<span class="sicon" style="--ic: url('/icon/${encodeURIComponent(sk.ic)}.png')">` +
          `<img src="/icon/${encodeURIComponent(sk.ic)}.png" alt="" loading="lazy" draggable="false"></span>` : "") +
        `<div class="sn">${nameHtml(sk)}</div>` +
        `<div class="sg"><span class="pips">${pips}</span><span>${sk.g}/${sk.m}` +
        `${sk.b ? `<span class="sbonus${sk.g ? "" : " idle"}">${esc(t("skills.plus", { n: sk.b }))}</span>` : ""}</span></div></div>`;
    }
    need += tier.need;
  }
  return html + "</div>";
}
