// A damage bar (the Realtime and Recap tabs - design.md, the user's LoL picture): an enemy's pool (max health + shield)
// as a track, filled from the left by the damage taken, split by who took it off - a segment per source in its colour
// (parts.js sourceColor), its hits plain, its ticks striped one way, the slag it brought (its share of others' hits -
// store.js contribution) striped the other way; the segments 2 px apart. Each segment's tooltip: who, how much, its
// share. A legend of the sources above the list (dataviz: identity never by colour alone).
import { esc } from "../dom.js";
import { t } from "../i18n.js";
import { tipSections } from "../ui/hovertip.js";
import { amountText } from "./amount.js";
import { actorName, isPlayer, playerOrder, sourceColor } from "./parts.js";

const KINDS = ["hits", "ticks", "slag"]; // (store.js contribution's parts: 0, 1, 2)

/** A part's label: slag's the game's own name for its element when a slag hit brought it (its damage type's enum,
 *  DAMAGE_TYPE_Amp - inspector.element_of's "et"; the game text rule), else ours. */
export function partLabel(store, kind) {
  if (kind === 2) for (const el of store.elements.values()) if (el.et === "DAMAGE_TYPE_Amp" && el.eln) return el.eln;
  return t("dmg.part." + KINDS[kind]);
}

/** Contributions (Map source -> [hits, ticks, slag]) -> [{source, kind, amount}], the biggest source first, its parts
 *  together; and their sum. */
export function segments(parts) {
  const bySource = [...parts].map(([source, p]) => ({ source, p, sum: p[0] + p[1] + p[2] })).filter((x) => x.sum > 0)
    .sort((a, b) => b.sum - a.sum || a.source - b.source);
  const out = [];
  let total = 0;
  for (const { source, p } of bySource) {
    for (let kind = 0; kind < 3; kind++) if (p[kind] > 0) out.push({ source, kind, amount: p[kind] });
    total += p[0] + p[1] + p[2];
  }
  return { list: out, total };
}

const LABEL_FROM = 0.1; // a segment this share of the track or more: its amount written in it (labels)

/** A bar's HTML. `filled`: the share of the track the damage fills (0-1: what's missing of the pool - all of it dead);
 *  `width`: the track's share of the row (Recap: the pool against the biggest listed; 1 otherwise); `labels`: a tall
 *  bar, each segment's amount written in it when it has the room (Realtime - the user: else only on hover). */
export function barHtml(store, parts, filled, width = 1, labels = false) {
  const { list, total } = segments(parts);
  const fill = Math.max(0, Math.min(1, filled));
  const bySource = new Map();
  for (const s of list) bySource.set(s.source, (bySource.get(s.source) || 0) + s.amount);
  const segs = list.map((s) => {
    const share = total > 0 ? s.amount / total : 0;
    const tip = tipSections(actorName(store, s.source), [{ kind: "stats", lines: [
      `${partLabel(store, s.kind)}: ${amountText(s.amount)}`,
      t("unit.percent", { n: Math.round((100 * (bySource.get(s.source) || 0)) / total) }),
    ] }]);
    const label = labels && share * fill >= LABEL_FROM ? `<b>${esc(amountText(s.amount))}</b>` : "";
    return `<i class="dmseg k${s.kind}" style="flex-grow:${(share * 1000).toFixed(1)};--c:${sourceColor(store, s.source)}"${tip}>${label}</i>`;
  }).join("");
  return `<div class="dmbarbox" style="width:${(100 * Math.max(0, Math.min(1, width))).toFixed(1)}%">` +
    `<div class="dmtrackbar${labels ? " big" : ""}"><div class="dmfill" style="width:${(100 * fill).toFixed(2)}%">${segs}</div></div></div>`;
}

/** The legend: the players in their colours (their order: parts.js), "others" in grey - the sources in `seen` only. */
export function legendHtml(store, seen) {
  const players = playerOrder(store).filter((id) => seen.has(id));
  const others = [...seen].some((id) => !isPlayer(store, id));
  if (!players.length && !others) return "";
  const item = (color, label) => `<span class="dmkey"><i style="--c:${color}"></i>${esc(label)}</span>`;
  return `<div class="dmlegend">${players.map((id) => item(sourceColor(store, id), actorName(store, id))).join("")}` +
    `${others ? item("var(--dm-other)", t("dmg.others")) : ""}` +
    `<span class="dmkey"><i class="k1"></i>${esc(partLabel(store, 1))}</span>` +
    `<span class="dmkey"><i class="k2"></i>${esc(partLabel(store, 2))}</span></div>`;
}

/** How much a share is ("12 %"). */
export const percentText = (part, whole) => t("unit.percent", { n: whole > 0 ? Math.round((100 * part) / whole) : 0 });

