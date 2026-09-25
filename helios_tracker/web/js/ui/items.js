// Items in the inspector (gear, backpack): one expandable card each, grouped by kind.
import { classHtml, esc, nameHtml } from "../dom.js";
import { money, num, numUpTo, t } from "../i18n.js";
import { rarity } from "../model.js";
import { S } from "../state.js";
import { tipAttrs, tipSections } from "./hovertip.js";
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
    // (its element's line without a colour of its own - fire's: the damage type's, elementColour)
    const col = f.col || (f.el ? elementColour(it) : "");
    const colour = /^#[0-9a-f]{6}$/i.test(col || "") ? ` style="color:${col}"` : "";
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
  // the element's tiles (its chance, its damage) in the element's colour, like the game's card (the item's --etint:
  // its element line's colour, else the damage type's)
  return tiles.map(([k, v, sub, tip, role]) => `<div class="istat"${tip || ""}>` +
    `<span class="islabel">${esc(k)}</span><span class="isvalue${role === "element" ? " iselement" : ""}">${esc(v)}</span>` +
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

const elementTints = new Map(); // an element icon's url -> its art's colour ("rgb(...)"), or "" (none found)

// An item's element colour, the game's: its element's card line's (the damage type's own line - "el" - in its
// TextColor: shock's blue), else the damage type's HUDDamageColor (the hit markers': fire's line has none); ""
// without either (a relic: the page measures its element icon - elementIconLoaded)
function elementColour(it) {
  const col = (it.card || []).find((l) => l.el)?.col || it.ecol || "";
  return /^#[0-9a-f]{6}$/i.test(col) ? col : "";
}

// The element icon's own colour (its saturated, opaque pixels, weighted by saturation - not its white outline or
// its shading's black): the last fallback for the type icon's tint.
function artColour(img) {
  const w = img.naturalWidth, h = img.naturalHeight;
  if (!w || !h) return "";
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, w, h).data;
  let r = 0, gr = 0, b = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) {
    if (d[i + 3] < 200) continue;
    const sat = Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]);
    if (sat < 60) continue;
    r += d[i] * sat; gr += d[i + 1] * sat; b += d[i + 2] * sat; n += sat;
  }
  return n ? `rgb(${Math.round(r / n)} ${Math.round(gr / n)} ${Math.round(b / n)})` : "";
}

// An item's element icon loaded (the inspector's load listener): without a game colour for its element, its art's
// (measured once, kept) on its type icon
export function elementIconLoaded(img) {
  const item = img.closest(".item");
  if (!item || item.style.getPropertyValue("--etint")) return;
  const src = img.getAttribute("src");
  if (!elementTints.has(src)) elementTints.set(src, artColour(img));
  if (elementTints.get(src)) item.style.setProperty("--etint", elementTints.get(src));
}

function itemHtml(it, ownerLevel) {
  const [tier, color] = rarity(it.q || 0);
  // (no equip slot: obvious; no maker when its logo's there - the footer's, its name the logo's tooltip; its level
  // and price in the card's top right)
  const logo = it.mf && /^[A-Za-z0-9_]+$/.test(it.mf);
  const meta = [it.type || t("kind." + it.k, null, it.k), logo ? "" : it.maker].filter(Boolean).join(" · ");
  const price = it.v ? `<span class="iprice">${esc(money(it.v))}</span>` : "";
  // its level, top right - red above its owner's (the game's rule: not equippable yet)
  const tooHigh = it.l && ownerLevel && it.l > ownerLevel;
  const level = it.l ? `<span class="ilvl${tooHigh ? " toohigh" : ""}"${tooHigh ? tipAttrs("", t("item.levelTooHigh", { n: ownerLevel })) : ""}>` +
    `${esc(t("item.level", { n: it.l }))}</span>` : "";
  // expanded: its card's lines, its stats (tiles), then folded away - its parts, the technical details
  const card = cardLinesHtml(it), stats = statTilesHtml(it);
  const parts = foldHtml(it, "parts", t("item.parts"), (it.parts || []).map(partRow));
  const details = foldHtml(it, "details", t("item.details"), [
    [t("item.rarityLevel"), t("item.rarityGuess", { n: String(it.q), name: rarityName(it.q) })],
    [t("item.class"), null, it.c, classHtml(it.c)]]);
  // its item card icons (the game's: gamecards.py), along the card's bottom like the game's (smaller while folded):
  // the manufacturer's logo, the element's, the type's - each dropped if the game has none (or the key's odd); the
  // logo missing: the maker's name instead
  const icon = (kind, key, text = "") => (key && /^[A-Za-z0-9_]+$/.test(key)
    ? `<img class="ii-${kind}" src="/cardicon/${kind}/${key}.png" crossorigin="anonymous" alt="${esc(text)}"${text ? ` title="${esc(text)}"` : ""} ` +
      `loading="lazy" draggable="false" onerror="${text
        ? "this.replaceWith(Object.assign(document.createElement('span'), {className: 'ii-text', textContent: this.alt}))"
        : "this.remove()"}">` : "");
  // (the element by the type icon, not between: the game's middle spot looked odd - the user's call). Tinted, with
  // an element: the type icon's white fill in the element's colour (--etint, made pastel), the element's art a
  // little paler to match - a masked copy of the icon over it (css: .iitint)
  const tinted = (html, kind, key) => (html && it.el
    ? `<span class="iitint ${kind}" style="--src:url('/cardicon/${kind}/${key}.png')">${html}</span>` : html);
  // the element's colour (--etint: the type icon): the game's (elementColour), else its icon's art's once seen
  const tint = it.el ? elementColour(it) || elementTints.get(`/cardicon/element/${it.el}.png`) || "" : "";
  const kind = tinted(icon("element", it.el), "element", it.el) + tinted(icon("type", it.wt), "type", it.wt);
  // the manufacturer's logo: its white fill a little in the rarity's colour (--c; css: .iitint.brand)
  const brand = icon("manufacturer", it.mf, it.maker || "");
  const icons = (brand ? `<span class="iitint brand" style="--src:url('/cardicon/manufacturer/${it.mf}.png')">${brand}</span>` : "") +
    (kind ? `<span class="iikind">${kind}</span>` : "");
  // (effervescent - the game's RARITY_Rainbow: its name's colour cycling like the game's; css: .item.rainbow)
  return `<div class="item${S.expanded.has(it.i) ? " expanded" : ""}${tier === "effervescent" ? " rainbow" : ""}" data-id="${esc(it.i)}" ` +
    `style="--c:${color}${tint ? `;--etint:${esc(tint)}` : ""}">` +
    `<div class="ihd"><div class="itext"><div class="iname">${nameHtml(it)}</div><div class="imeta">${esc(meta)}</div></div>` +
    `${level || price ? `<div class="iside">${level}${price}</div>` : ""}</div>` +
    `<div class="idetail">${card ? `<div class="icard">${card}</div>` : ""}` +
    `${stats ? `<div class="istats">${stats}</div>` : ""}${parts}${details}</div>` +
    `${icons ? `<div class="iicons">${icons}</div>` : ""}</div>`;
}

/** `ownerLevel`: its owner's level (their items above it: marked - itemHtml). */
export function itemsByKind(items, ownerLevel = 0) {
  const groups = new Map();
  for (const k of KIND_ORDER) groups.set(k, []);
  for (const it of items) (groups.get(it.k) || groups.get("item")).push(it);
  let html = "";
  for (const [k, list] of groups) {
    if (!list.length) continue;
    list.sort((a, b) => (b.q || 0) - (a.q || 0) || (b.l || 0) - (a.l || 0) || a.n.localeCompare(b.n));
    html += `<div class="group">${esc(t("group." + k))} · ${num(list.length)}</div>` + list.map((it) => itemHtml(it, ownerLevel)).join("");
  }
  return html;
}
