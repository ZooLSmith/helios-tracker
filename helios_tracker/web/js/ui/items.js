// Items in the inspector (gear, backpack): one expandable card each, grouped by kind.
import { classHtml, esc, nameHtml } from "../dom.js";
import { money, num, numUpTo, t } from "../i18n.js";
import { rarity } from "../model.js";
import { S } from "../state.js";
import { tipSections } from "./hovertip.js";
import { skillStatParts } from "./skills.js";

const KIND_ORDER = ["weapon", "shield", "grenade", "classmod", "relic", "usable", "mission", "item"];

export function rarityName(q) {
  const [key] = rarity(q || 0);
  return t("rarity." + key, { n: q || 0 });
}

/** [key, card value, current value, extra] (inspector.py _stats: the item's own, and with the owner's bonuses -
 *  skills, class mod, relic) -> [label, the card's value, "the current one with bonuses (+N %)" when they change
 *  it]. Raw numbers from the game, formatted here. */
function statRow([key, base, now, extra]) {
  const one = (x) => num(x, 1);
  const format = {
    damage: (x) => num(x) + (extra > 1 ? " " + t("unit.times", { n: num(extra) }) : ""),
    fireRate: (x) => t("unit.perSecond", { n: one(x) }),
    reload: (x) => t("unit.seconds", { n: one(x) }),
    fuse: (x) => t("unit.seconds", { n: one(x) }),
    blastRadius: (x) => t("unit.meters", { n: one(x) }),
    elementChance: (x) => t("unit.percent", { n: numUpTo(x, 1) }), // (the card's: 16.8 %)
  }[key] || ((x) => num(x));
  const changed = now != null && base && Math.abs(now - base) / Math.abs(base) >= 0.005;
  const delta = changed ? Math.round((now / base - 1) * 100) : 0;
  const d = (delta > 0 ? "+" : "") + t("unit.percent", { n: num(delta) });
  const sub = changed ? t("stat.withBonuses", { n: format(now), d }) : "";
  // its tooltip (the tile cuts the line short): the card's value, then with bonuses - the values emphasised
  const tip = tipSections(t("stat." + key), [
    { kind: "stats", lines: [[t("stat.cardValue") + " ", format(base), ""]] },
    ...(changed ? [{ kind: "stats", lines: [[t("stat.withBonusesLabel") + " ", format(now), ` (${d})`]] }] : []),
  ]);
  return [t("stat." + key), format(base), sub, tip];
}

// "DamageRadius_ExtraLarge" in group "DamageRadius" -> "Extra Large"; "SMG_Barrel_Hyperion" -> "Hyperion"
function tidyPart(tech, group) {
  const g = String(group || "").toLowerCase().replace(/\d+$/, "");
  const toks = String(tech).split("_");
  const i = g ? toks.findIndex((tok) => tok.toLowerCase().replace(/\d+$/, "") === g) : -1;
  const rest = (i >= 0 ? toks.slice(i + 1) : toks).join(" ");
  return (rest || String(tech)).replace(/([a-z])([A-Z])/g, "$1 $2");
}

// [slot, technical name, group, localized name]: labelled by the part's role (its package
// group) when we know it, else by the slot; the game's own name when it has one
function partRow([slot, tech, group, text]) {
  const label = t("role." + group, null, "") || t("part." + slot, null, slot);
  return [label, text || tidyPart(tech, group), tech];
}

/** An item's card lines (the game's: "High elemental effect chance.", "Consumes 2 ammo per shot.", a unique's
 *  red text): the values emphasised, each in the game's colour when it has one. */
function cardLinesHtml(it) {
  return (it.card || []).map((f) => {
    const [before, value, after] = skillStatParts(f);
    const colour = /^#[0-9a-f]{6}$/i.test(f.col || "") ? ` style="color:${f.col}"` : "";
    return `<div class="icline"${colour}>${esc(before)}${value ? `<b class="sval">${esc(value)}</b>` : ""}${esc(after)}</div>`;
  }).join("");
}

/** Its stats as a grid of tiles (label small, value big), like the game's card - the element's damage per second
 *  a tile too, named by its frame ("shock ?": the game has no display name for it). */
function statTilesHtml(it) {
  const tiles = (it.stats || []).map(statRow);
  // its element's damage, labelled with the game's name for it ("shock": its localization - capitalised here)
  const element = it.eln ? it.eln.charAt(0).toLocaleUpperCase() + it.eln.slice(1) : t("stat.elementDamage");
  if (it.edps) tiles.push([element, t("unit.perSecond", { n: num(it.edps, 1) }), "", "", "element"]);
  const elementChance = (it.stats || []).findIndex(([key]) => key === "elementChance");
  if (elementChance >= 0) tiles[elementChance][4] = "element";
  // the element's tiles (its chance, its damage) in the game's colour for it (no name: the game has none - its icon later)
  const colour = /^#[0-9a-f]{6}$/i.test(it.ecol || "") ? `color:${it.ecol}` : "";
  return tiles.map(([k, v, sub, tip, role]) => `<div class="istat"${tip || ""}>` +
    `<span class="islabel">${esc(k)}</span><span class="isvalue"${role === "element" && colour ? ` style="${colour}"` : ""}>${esc(v)}</span>` +
    `${sub ? `<span class="issub">${esc(sub)}</span>` : ""}</div>`).join("");
}

/** A fold of the expanded item: its header (a count) and rows, open when remembered (S.itemFolds). */
function foldHtml(it, key, title, rows) {
  if (!rows.length) return "";
  const open = S.itemFolds.has(`${it.i}:${key}`);
  const kv = rows.map(([k, v, tip, html]) =>
    `<span>${esc(k)}</span><span${tip ? ` title="${esc(tip)}"` : ""}>${html ?? esc(v)}</span>`).join("");
  return `<div class="ifold${open ? " open" : ""}" data-fold="${key}"><div class="ifhead">${esc(title)}` +
    `<span class="ifcount">${esc(num(rows.length))}</span></div><div class="kv">${kv}</div></div>`;
}

function itemHtml(it) {
  const [, color] = rarity(it.q || 0);
  const meta = [it.type || t("kind." + it.k, null, it.k), it.maker, it.l ? t("item.level", { n: it.l }) : "",
    it.v ? money(it.v) : ""].filter(Boolean).join(" · "); // (no equip slot: obvious)
  // expanded: its card's lines, its stats (tiles), then folded away - its parts, the technical details
  const card = cardLinesHtml(it), stats = statTilesHtml(it);
  const parts = foldHtml(it, "parts", t("item.parts"), (it.parts || []).map(partRow));
  const details = foldHtml(it, "details", t("item.details"), [
    [t("item.rarityLevel"), t("item.rarityGuess", { n: String(it.q), name: rarityName(it.q) })],
    [t("item.class"), null, it.c, classHtml(it.c)]]);
  return `<div class="item${S.expanded.has(it.i) ? " expanded" : ""}" data-id="${esc(it.i)}" style="--c:${color}">` +
    `<div class="iname">${nameHtml(it)}</div><div class="imeta">${esc(meta)}</div>` +
    `<div class="idetail">${card ? `<div class="icard">${card}</div>` : ""}` +
    `${stats ? `<div class="istats">${stats}</div>` : ""}${parts}${details}</div></div>`;
}

export function itemsByKind(items) {
  const groups = new Map();
  for (const k of KIND_ORDER) groups.set(k, []);
  for (const it of items) (groups.get(it.k) || groups.get("item")).push(it);
  let html = "";
  for (const [k, list] of groups) {
    if (!list.length) continue;
    list.sort((a, b) => (b.q || 0) - (a.q || 0) || (b.l || 0) - (a.l || 0) || a.n.localeCompare(b.n));
    html += `<div class="group">${esc(t("group." + k))} · ${num(list.length)}</div>` + list.map(itemHtml).join("");
  }
  return html;
}
