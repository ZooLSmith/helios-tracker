// The inspector's Skills tab: one tab per tree, the game's grid layout.
import { esc, nameHtml } from "../dom.js";
import { num, t } from "../i18n.js";
import { cleanGameText as cleanText, nameText } from "../model.js";
import { S } from "../state.js";

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
    html += `<div class="branch">${skillGrid(trees[sel])}</div>`;
  }
  for (const b of trees.length ? [] : p.skills) {
    html += `<div class="branch"><div class="bhead">${b.n ? nameHtml(b) : esc(t("skills.other"))}<span class="bpts">${esc(t("skills.pts", { n: b.pts }))}</span></div>`;
    for (const sk of b.skills) {
      const pips = Array.from({ length: Math.max(sk.m, 0) }, (_, i) => `<i class="${i < sk.g ? "on" : ""}"></i>`).join("");
      html += `<div class="skill${sk.g ? "" : " zero"}" title="${esc(cleanText(sk.d))}">` +
        `<span class="tier">${esc(t("skills.tier", { n: sk.t }))}</span><span class="sname">${nameHtml(sk)}</span>` +
        `<span class="pips">${pips}</span><span class="muted">${sk.g}/${sk.m}</span></div>`;
    }
    html += "</div>";
  }
  return html;
}

function skillGrid(b) {
  const cols = Math.max(1, ...b.tiers.map((tier) => tier.cells.length));
  let need = 0, html = `<div class="sgrid" style="grid-template-columns: repeat(${cols}, 1fr)">`;
  for (const tier of b.tiers) {
    const locked = b.pts < need; // points in this branch needed to reach the tier
    for (let c = 0; c < cols; c++) {
      const sk = tier.cells[c];
      if (!sk) { html += `<div class="scell empty"></div>`; continue; }
      const pips = Array.from({ length: Math.max(sk.m, 0) }, (_, i) => `<i class="${i < sk.g ? "on" : ""}"></i>`).join("");
      const cls = ["scell", sk.g ? "invested" : "zero", locked ? "locked" : ""].filter(Boolean).join(" ");
      html += `<div class="${cls}" title="${esc(cleanText(sk.d))}"><div class="sn">${nameHtml(sk)}</div>` +
        `<div class="sg"><span class="pips">${pips}</span><span>${sk.g}/${sk.m}</span></div></div>`;
    }
    need += tier.need;
  }
  return html + "</div>";
}
