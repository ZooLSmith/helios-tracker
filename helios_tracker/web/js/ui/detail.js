// The detail panel: a clicked object (not a player), in the inspector's drawer.
import { $, esc, nameHtml } from "../dom.js";
import { UU_PER_METER } from "../geo.js";
import { num, t } from "../i18n.js";
import { icon } from "../icons.js";
import { isGear, nameText, rarity, shownHealth, shownMaxHealth } from "../model.js";
import { S, findDetail, isTrackedPlayer, itemById, onSale, pawnPos, trackedPawn } from "../state.js";
import { saveDrawer } from "./drawer.js";
import { bindItems, renderInspector } from "./inspector.js";
import { itemHtml, pickupAmount, pickupIconHtml, priceText, rarityName } from "./items.js";
import { renderPlayers } from "./players.js";
import { oddsHtml } from "./odds.js";
import { machineStockHtml } from "./shops.js";

/** Opens an object's / marker's panel. From the vending machines' list: a back button to it (`back`: that machine
 *  first on return - shops.js). */
export function openDetail(kind, id) {
  S.detail = { kind, id, back: S.shopView ? { k: "shops", id } : null };
  S.inspect = null;
  S.missionView = null;
  S.shopView = null;
  $("inspector").classList.add("open");
  saveDrawer();
  renderPlayers();
  renderInspector(true);
}

/** A link to a mission in the mission log (the drawer's delegated click: missionlog.js). */
const missionLink = (id, name) => `<a class="mlink" data-open-mission="${esc(id)}">${nameHtml(name)}</a>`;
/** A quest giver's listed mission ({i, n, end}): its link, "to hand in" after it for one ready. */
const listedLink = (e) => missionLink(e.i, e) + (e.end ? ` <span class="muted">· ${esc(t("detail.handIn"))}</span>` : "");

/** Who a quest giver's "!" is on (its "by": an NPC or an object, e.g. the bounty board) and the kind its
 *  panel opens as, or null (not known here). */
function giverOf(id) {
  const pawn = S.pawns.get(id);
  if (pawn) return { item: pawn, kind: pawn.k };
  const obj = S.objects.find((o) => o.i === id);
  return obj ? { item: obj, kind: obj.cat } : null;
}

const AT_UU = 300; // an objective point "at" an object / NPC: within 3 m of it

/** What an objective point sits on (a teleporter, a chest, an NPC...): the nearest object / non-player
 *  pawn within AT_UU, as giverOf, or null. */
function objectiveAt(mk) {
  let best = null, bestD = AT_UU;
  const consider = (item, kind) => {
    const d = Math.hypot(item.x - mk.x, item.y - mk.y, item.z - mk.z);
    if (d < bestD) { best = { item, kind }; bestD = d; }
  };
  for (const o of S.objects) consider(o, o.cat);
  for (const p of S.pawns.values()) if (p.k === "npc" || p.k === "vehicle") consider(p, p.k);
  return best;
}

/** A link opening an NPC's / object's panel (the drawer's delegated click: missionlog.js). */
const detailLink = (at) => `<a class="mlink" data-open-detail="${esc(at.item.i)}" data-kind="${esc(at.kind)}">${nameHtml(at.item)}</a>`;

/** What a map thing is, as its panel's header says it: a pickup's rarity and class, else its kind ("Big chest"). */
function kindText(kind, it) {
  if (it.boss) return t("tip.boss"); // (its AI class's bBoss)
  if (kind !== "loot") return t("tip." + kind, null, kind);
  return (isGear(it.c) ? rarityName(it.q) + " · " : "") + nameText({ n: String(it.c || "Pickup"), raw: 1 });
}

// The Nearby list: what's this close to the shown thing - across (on the map: the user's "1 m or so") and in height
// (apart: a quest marker floats above its NPC's head, a pawn's position is its middle - measured in 3D, Marcus under
// his "!" was out; the user saw it). Another floor stays out.
const NEAR_UU = 1.5 * UU_PER_METER, NEAR_HEIGHT_UU = 3 * UU_PER_METER;

const openedCards = new Set(); // ground items whose card was opened once for them (then as the user leaves it)

/** Everything on the map within NEAR_UU across (and NEAR_HEIGHT_UU in height) of `it` (objects, loot, pawns, point
 *  objectives / quest givers; not itself), the closest first: [{ item, kind, d }] - the markers stacked there, one
 *  click away (the map's click picks one). */
function nearby(it) {
  const at = it.fx !== undefined ? pawnPos(it, performance.now()) : it, out = [];
  const consider = (item, kind) => {
    if (item === it || item.x == null) return;
    const pos = item.fx !== undefined ? pawnPos(item, performance.now()) : item;
    const d = Math.hypot(pos.x - at.x, pos.y - at.y);
    if (d <= NEAR_UU && Math.abs(pos.z - at.z) <= NEAR_HEIGHT_UU) out.push({ item, kind, d });
  };
  for (const o of S.objects) consider(o, o.cat);
  for (const p of S.pickups) consider(p, "loot");
  for (const p of S.pawns.values()) if (p.rs !== 2) consider(p, p.k); // (respawning: its position means nothing)
  for (const mk of S.missions.markers) if (!mk.rad) consider(mk, mk.k);
  return out.sort((a, b) => a.d - b.d);
}

/** The Nearby list: each one's name (a link to its panel), its kind, how far. */
function nearbyHtml(it) {
  const list = nearby(it);
  if (!list.length) return "";
  return `<div class="group">${esc(t("detail.nearby"))} · ${num(list.length)}</div><div class="nblist">` + list.map(({ item, kind, d }) => {
    const name = kind === "objective" || kind === "directive" ? nameHtml(item.objective || item.mission) : nameHtml(item);
    const color = kind === "loot" && isGear(item.c) ? ` style="color:${rarity(item.q || 0)[1]}"` : "";
    return `<div class="nbrow"><a class="mlink" data-open-detail="${esc(item.i)}" data-kind="${esc(kind)}"${color}>${name}</a>` +
      `<span class="nbkind">${esc(kindText(kind, item))} · ${esc(t("unit.meters", { n: num(d / UU_PER_METER, 1) }))}</span></div>`;
  }).join("") + `</div>`;
}

export function renderDetail(resetScroll) {
  const body = $("ibody"), scroll = body.scrollTop;
  $("itabs").style.display = "none";
  const it = findDetail(), kind = S.detail.kind;
  if (!it) {
    $("iwho").textContent = "";
    $("isub").textContent = "";
    body.innerHTML = `<div class="note">${esc(t("detail.gone"))}</div>`;
    return;
  }
  const mission = kind === "objective" || kind === "directive";
  const back = S.detail.back ? `<button class="mback" data-detail-back title="${esc(t("shops.back"))}">${icon("back")}</button>` : "";
  const gear = kind === "loot" && isGear(it.c);
  // (gear's name in its rarity's colour, as the game's card)
  const whoName = mission ? nameHtml(it.objective || it.mission) : nameHtml(it);
  $("iwho").innerHTML = back + (gear ? `<span style="color:${rarity(it.q || 0)[1]}">${whoName}</span>` : whoName);
  $("isub").textContent = [kindText(kind, it), it.l && (kind !== "loot" || gear) ? t("insp.level", { n: it.l }) : ""]
    .filter(Boolean).join(" · ");
  const rows = [];
  const me = trackedPawn(); // the tracked player
  if (me && me !== it) {
    const pos = it.fx !== undefined ? pawnPos(it, performance.now()) : it;
    rows.push([t("detail.distance"), t("unit.meters", { n: num(Math.hypot(pos.x - me.x, pos.y - me.y, pos.z - me.z) / UU_PER_METER, 0) })]);
  }
  if (kind === "loot" && !gear && it.am) rows.push([t("detail.amount"), pickupAmount(it)]); // money / ammo: how much
  if (it.sm > 0) rows.push([t("detail.shield"), `${num(Math.round(it.s))} / ${num(Math.round(it.sm))}`]);
  if (it.m > 0) rows.push([t("detail.health"), `${num(shownHealth(it.h))} / ${num(shownMaxHealth(it.m))}`]);
  // an object that explodes (a barrel): its element - the item cards' icon, the game's name (collector.py: its explosion's)
  if (it.xp && (it.el || it.eln)) {
    const elIcon = it.el && /^[A-Za-z0-9_]+$/.test(it.el) ? `<img class="dpelement" src="/cardicon/element/${it.el}.png" ` +
      `crossorigin="anonymous" alt="" draggable="false" onerror="this.remove()"> ` : "";
    rows.push([t("detail.element"), it.eln || "", elIcon + esc(it.eln || "")]);
  }
  if (mission) {
    // its mission(s): links to them in the mission log (a quest giver can have several: "list" - the ones
    // to hand in marked); a quest giver's: who gives them, a link to their panel
    if (it.list && it.list.length > 1) rows.push([t("detail.missions"), null, it.list.map(listedLink).join("<br>")]);
    else rows.push([t("detail.mission"), null, it.list ? listedLink(it.list[0]) : it.mi ? missionLink(it.mi, it.mission) : nameHtml(it.mission)]);
    const by = kind === "directive" && it.by ? giverOf(it.by) : null;
    if (by) rows.push([t("detail.giver"), null, detailLink(by)]);
    const at = kind === "objective" && !it.rad ? objectiveAt(it) : null; // (a point, not an area)
    if (at) rows.push([t("detail.at"), null, detailLink(at)]);
    if (it.rad) rows.push([t("detail.area"), t("unit.meters", { n: num(it.rad / UU_PER_METER, 0) })]);
    rows.push([t("detail.tracked"), t(it.tracked ? "detail.yes" : "detail.no")]);
  }
  // an NPC / object giving missions (its quest-giver markers): links to them in the mission log
  const gives = kind === "directive" || kind === "objective" ? []
    : S.missions.markers.filter((m) => m.k === "directive" && m.by === it.i && m.mi).flatMap((m) => m.list || [{ i: m.mi, ...m.mission }]);
  if (gives.length) rows.push([t("detail.missions"), null, gives.map(listedLink).join("<br>")]);
  // the objective points on it ("Speak to...": within AT_UU): the objective, a link to its mission
  const on = kind === "directive" || kind === "objective" || kind === "loot" ? []
    : S.missions.markers.filter((m) => m.k === "objective" && !m.rad && Math.hypot(m.x - it.x, m.y - it.y, m.z - it.z) < AT_UU);
  if (on.length) rows.push([t("detail.objectives"), null, on.map((m) => (m.objective ? nameHtml(m.objective) + " · " : "") +
    (m.mi ? missionLink(m.mi, m.mission) : nameHtml(m.mission))).join("<br>")]);
  if (it.ms) { // a mission item: the mission it gives / is for - a link to it in the mission log
    rows.push([t(it.ms.k === "gives" ? "detail.givesMission" : "detail.forMission"), null,
      `<a class="mlink" data-open-mission="${esc(it.ms.i)}">${esc(it.ms.n)}</a>` + (it.ms.o ? ` · ${esc(it.ms.o)}` : "")]);
  }
  // a vending machine: its stock, a link to it in the Shops list (shops.js)
  const shop = kind === "vendor" && S.shops ? S.shops.machines.find((m) => m.i === it.i) : null;
  if (shop) {
    const n = shop.items.length + (shop.feat ? 1 : 0);
    rows.push([t("detail.stock"), null, `<a class="mlink" data-open-shop="${esc(shop.i)}">${esc(t("detail.stockItems", { n: num(n) }))}</a>`]);
  }
  // something on sale on it (a Moxxtail's drink, a pickup you pay for): its price
  const sale = kind !== "loot" ? onSale(it) : undefined;
  if (sale && priceText(sale.cost)) rows.push([t("detail.price"), priceText(sale.cost)]);
  if (it.lootable) rows.push([t("detail.status"), t(it.looted ? "detail.looted" : "detail.unlooted")]);
  if (it.slots) rows.push([t("detail.slots"), num(it.slots)]);
  // the technical rows (its loot lists, class, definition): folded away at the bottom ("Details", like an item's - the
  // user's call: debug more than information), as the game names them - exact, not prettified (WillowInteractiveObject,
  // the definition's full path)
  const tech = [];
  if (it.lists && it.lists.length) tech.push([t("detail.lists"), it.lists.join(", ")]);
  if (it.c) tech.push([t("item.class"), String(it.c)]);
  if (it.d) tech.push([t("detail.definition"), it.dp || it.d]);
  const kvHtml = (list) => `<div class="kv">` + list.map(([k, v, h]) => `<span>${esc(k)}</span><span>${h ?? esc(v)}</span>`).join("") + `</div>`;
  // a fold (its header: the title, a count), closed until opened - remembered per object (S.itemFolds, as items')
  const fold = (key, title, count, inner) => `<div class="ifold${S.itemFolds.has(`${it.i}:${key}`) ? " open" : ""}" data-fold="${key}" ` +
    `data-id="${esc(it.i)}"><div class="ifhead">${esc(title)}<span class="ifcount">${esc(num(count))}</span></div>${inner}</div>`;
  // gear on the ground: its item's card (stats, parts - the collector's, like a backpack's: the same item by id), open
  // the first time it's shown; not read yet (a few per update): a note
  let itemCard = "";
  if (gear) {
    const card = itemById(it.it);
    if (card && !openedCards.has(card.i)) { openedCards.add(card.i); S.expanded.add(card.i); }
    const level = (S.players.find(isTrackedPlayer) || {}).lvl || 0; // (above it: marked, like a backpack's)
    itemCard = card ? itemHtml(card, level) : `<div class="note">${esc(t("detail.itemPending"))}</div>`;
  }
  // (right under its rows: what's stacked with it - the map's click may have picked a neighbour)
  // a pickup's own icon (the game's: cash, eridium, health, an ammo type), big, above its rows
  const bigIcon = kind === "loot" && !gear ? pickupIconHtml(it, "dpicon") : "";
  let html = (bigIcon ? `<div class="dpicons">${bigIcon}</div>` : "") + (rows.length ? kvHtml(rows) : "") + itemCard + nearbyHtml(it);
  // what it can hold: its chances when the collector worked them out (odds.js), else the pools' names
  const pools = it.odds && it.odds.length ? oddsHtml(it)
    : (it.loot || []).map((n) => `<div>${nameHtml({ n: String(n).replace(/^Pool_/, ""), raw: 1 })}</div>`).join("");
  const poolCount = it.odds && it.odds.length ? it.odds.length : (it.loot || []).length;
  if (kind === "vendor") {
    // a vending machine: what it sells, right here (the shops payload has it) - as in the vending list; the pools it
    // rolls from are technical next to that: folded away at the bottom, like an item's parts
    html += machineStockHtml(it.i);
    if (pools) html += fold("pools", t("detail.contents"), poolCount, `<div class="plist">${pools}</div>`);
  } else if (pools) { // every pool its loot is rolled from, one per line (a container: the only hint of what it drops)
    html += `<div class="group">${esc(t("detail.contents"))}</div><div class="plist">${pools}</div>`;
  }
  if (tech.length) html += fold("tech", t("item.details"), tech.length, kvHtml(tech));
  body.innerHTML = html;
  bindItems(body); // (its items' cards: open / close)
  for (const fold of body.querySelectorAll(":scope > .ifold")) { // (its own folds: the pools, the details)
    fold.querySelector(".ifhead").onclick = () => {
      const key = `${fold.dataset.id}:${fold.dataset.fold}`;
      if (S.itemFolds.has(key)) S.itemFolds.delete(key); else S.itemFolds.add(key);
      fold.classList.toggle("open");
    };
  }
  body.scrollTop = resetScroll ? 0 : scroll;
}
