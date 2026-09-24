// Items in the inspector (gear, backpack): one expandable card each, grouped by kind.
import { classHtml, esc, nameHtml } from "../dom.js";
import { money, num, t } from "../i18n.js";
import { prettyRaw, rarity } from "../model.js";
import { S } from "../state.js";
import { skillStatParts } from "./skills.js";

const KIND_ORDER = ["weapon", "shield", "grenade", "classmod", "relic", "usable", "mission", "item"];

export function rarityName(q) {
  const [key] = rarity(q || 0);
  return t("rarity." + key, { n: q || 0 });
}

function statRow([key, v, extra]) { // raw numbers from the game, formatted here
  const one = (x) => num(x, 1);
  const value = {
    damage: () => num(v) + (extra > 1 ? " " + t("unit.times", { n: num(extra) }) : ""),
    fireRate: () => t("unit.perSecond", { n: one(v) }),
    reload: () => t("unit.seconds", { n: one(v) }),
    fuse: () => t("unit.seconds", { n: one(v) }),
    blastRadius: () => t("unit.meters", { n: one(v) }),
    elementChance: () => t("unit.times", { n: num(v, 2) }),
  }[key];
  return [t("stat." + key), value ? value() : num(v)];
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

function itemHtml(it) {
  const [, color] = rarity(it.q || 0);
  const meta = [it.type || t("kind." + it.k, null, it.k), it.maker, it.l ? t("item.level", { n: it.l }) : "",
    it.v ? money(it.v) : ""].filter(Boolean).join(" · "); // (no equip slot: obvious)
  const rows = [...(it.stats || []).map(statRow),
    // its element: the game's frame name, no display name in the game - marked as a guess ("shock ?")
    ...(it.el ? [[t("stat.element"), prettyRaw(it.el)]] : []),
    ...(it.edps ? [[t("stat.elementDamage"), t("unit.perSecond", { n: num(it.edps, 1) })]] : []),
    [t("item.rarityLevel"), t("item.rarityGuess", { n: String(it.q), name: rarityName(it.q) })],
    ...(it.parts || []).map(partRow), [t("item.class"), null, it.c, classHtml(it.c)]];
  const kv = rows.map(([k, v, title, html]) =>
    `<span>${esc(k)}</span><span${title ? ` title="${esc(title)}"` : ""}>${html ?? esc(v)}</span>`).join("");
  // its card's lines (the game's: "High elemental effect chance.", a red text...): the values emphasised
  const card = (it.card || []).map((f) => {
    const [before, value, after] = skillStatParts(f);
    // (the game's colour for it, when it has one: an element's, a unique's red text)
    const colour = /^#[0-9a-f]{6}$/i.test(f.col || "") ? ` style="color:${f.col}"` : "";
    return `<div class="icline"${colour}>${esc(before)}${value ? `<b class="sval">${esc(value)}</b>` : ""}${esc(after)}</div>`;
  }).join("");
  return `<div class="item${S.expanded.has(it.i) ? " expanded" : ""}" data-id="${esc(it.i)}" style="--c:${color}">` +
    `<div class="iname">${nameHtml(it)}</div><div class="imeta">${esc(meta)}</div>` +
    `<div class="idetail">${card ? `<div class="icard">${card}</div>` : ""}<div class="kv">${kv}</div></div></div>`;
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
