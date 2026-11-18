// What the damage views share: an actor's name with its map marker, its pool (max health + shield) and what's left of
// it, the sources' colours, a time, what dealt a hit as icons (an item card's type, the element), the tags of a hit.
import { esc, nameHtml } from "../dom.js";
import { LAYERS, cardIconKey, prettyRaw } from "../model.js";
import { S } from "../state.js";
import { layerIcon } from "../ui/layers.js";
import { FLAG } from "./store.js";

// An actor's map layer (its marker beside its name): a pawn's by its kind; an object's by its category - the map's own
// (data.js onObjects: objectCategory), read off its record while it's on the map, kept once seen (a barrel blown up
// leaves the map); not seen there: the plain "other" one
const PAWN_LAYERS = { me: "player", player: "player", enemy: "enemy", npc: "npc", vehicle: "vehicle" };

function actorLayer(def) {
  if (def.k === "object" && !def.cat && def.m) {
    const o = S.objects.find((x) => x.i === def.m);
    if (o) { def.cat = o.cat; if (o.ecol) def.ecol = o.ecol; }
  }
  const id = PAWN_LAYERS[def.k] || (def.k === "object" ? def.cat || "other" : null);
  const layer = id && LAYERS.find((l) => l.id === id);
  if (!layer) return null;
  // (what explodes: in its element's colour, as on the map - draw.js)
  return id === "explosive" && def.ecol ? { ...layer, color: def.ecol } : layer;
}

// (a player: no marker - the user: their name is enough)
export const actorHtml = (store, id) => {
  const def = store.actors.get(id);
  if (!def) return `<span class="dma">?</span>`;
  const layer = def.k === "me" || def.k === "player" ? null : actorLayer(def);
  return `<span class="dma ${esc(def.k || "")}">${layer ? `<span class="sw">${layerIcon(layer)}</span>` : ""}${nameHtml(def)}</span>`;
};

/** An actor's pool - its max health + max shield, the damage it takes to kill it (the user: a shield can't be bypassed):
 *  its map pawn's ("m", "sm"), read while it's on the map and kept once seen (dead, it leaves the map) - the biggest
 *  seen (some gain max health); 0 unknown (never seen on the map, an object). */
export function maxPool(store, id) {
  const def = store.actors.get(id);
  if (!def) return 0;
  const pawn = def.m ? S.pawns.get(def.m) : null;
  const pool = pawn ? Math.max(0, pawn.m || 0) + Math.max(0, pawn.sm || 0) : 0;
  if (pool > 0 && !(def.mp >= pool)) def.mp = pool;
  return def.mp || 0;
}

/** What an actor has left (health + shield) while it's on the map; null unknown (off the map, an object). */
export function poolLeft(store, id) {
  const def = store.actors.get(id);
  const pawn = def?.m ? S.pawns.get(def.m) : null;
  return pawn && pawn.m > 0 ? Math.max(0, pawn.h ?? pawn.m) + Math.max(0, pawn.sm > 0 ? pawn.s ?? pawn.sm : 0) : null;
}

export const isPlayer = (store, id) => PLAYER_KIND.has(store.actors.get(id)?.k);
const PLAYER_KIND = new Set(["me", "player"]);

// The sources' colours (design.md: a bar split by who - dataviz's categorical slots 1-4, validated on the panels' dark
// surface: blue, orange, aqua, yellow - a player each, never by rank, by their number in the game (the definition's "o":
// PRI.PlayerID, the same on every player's page - the page's own player first gave everyone blue on their own page, the
// user), the ones without one after by their log id; one player's ids - a pawn respawned on a client - one colour;
// anyone else - an enemy, a barrel, the world - one neutral grey)
const SLOTS = 4;

/** A source's colour: "var(--dm-p1)".."var(--dm-p4)" for the players, "var(--dm-other)" for the rest. */
export function sourceColor(store, id) {
  const slot = playerSlots(store).get(id);
  return slot !== undefined ? `var(--dm-p${(slot % SLOTS) + 1})` : "var(--dm-other)";
}

/** Each player id's colour slot: the rank of their number among the players' (cached: the definitions only grow - a
 * player's again, its number the same). */
function playerSlots(store) {
  if (store._slotsAt !== store.actors.size) {
    store._slotsAt = store.actors.size;
    const key = (id, def) => def.o ?? `#${id}`;
    const players = [...store.actors].filter(([, d]) => PLAYER_KIND.has(d.k))
      .sort(([a, da], [b, db]) => (da.o ?? Infinity) - (db.o ?? Infinity) || a - b);
    const ranks = new Map();
    store._slots = new Map(players.map(([id, d]) => {
      const k = key(id, d);
      if (!ranks.has(k)) ranks.set(k, ranks.size);
      return [id, ranks.get(k)];
    }));
  }
  return store._slots;
}

/** The players' ids in the colours' order: "me" first, then by id. */
export function playerOrder(store) {
  if (store._playersAt !== store.actors.size) { // (cached: the definitions only grow)
    store._playersAt = store.actors.size;
    store._players = [...store.actors].filter(([, d]) => PLAYER_KIND.has(d.k))
      .sort(([a, da], [b, db]) => (da.k === "me" ? 0 : 1) - (db.k === "me" ? 0 : 1) || a - b).map(([id]) => id);
  }
  return store._players;
}

export const defName = (def) => (def ? (def.raw ? prettyRaw(def.n) : def.n || "") : "");

export const actorName = (store, id) => defName(store.actors.get(id)) || "?";

export const clockText = (store, ms) => new Date(store.t0 + ms).toLocaleTimeString(globalThis.document?.documentElement.lang || undefined,
  { hour: "2-digit", minute: "2-digit", second: "2-digit" });

// An item card icon (the game's art, /cardicon/: items.js's) - only when the game's card art is served; one the game
// hasn't (a 404 - each one stalls the page a few ms, the user saw it, and the log's lines are drawn again and again)
// kept in failedIcons: never asked for again, its fallback drawn instead (an element's: its colour's dot)
const failedIcons = new Set();
const iconUrl = (kind, key) => `/cardicon/${kind}/${encodeURIComponent(key)}.png`;
const iconOk = (kind, key) => !!(S.assets?.cards && cardIconKey(key) && !failedIcons.has(iconUrl(kind, key)));
export const dotHtml = (colour) => (/^#[0-9a-f]{6}$/i.test(colour || "") ? `<span class="dmel" style="background:${colour}"></span>` : "");
const cardImg = (kind, key) => `<img class="dmi ${kind}" src="${iconUrl(kind, key)}" alt="" draggable="false">`;

/** Records the list's icons that failed to load (their error, caught on the way down: it doesn't bubble). */
export function watchIcons(list) {
  list.addEventListener("error", (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    failedIcons.add(img.getAttribute("src"));
    img.remove(); // (this time: the next drawing draws the fallback)
  }, true);
}

/** An element's icon (its item card's), else its colour's dot; "" none. */
export function elementIcon(store, e) {
  const el = store.elements.get(e);
  return el ? (iconOk("element", el.el) ? cardImg("element", el.el) : dotHtml(el.ecol)) : "";
}

/** What dealt it, as icons (the user: no names in the line - its tooltip has them): a weapon's type icon (its item
 *  card's), the element's; nothing for what has no type (a melee, an explosion, a fire left on the ground - the user:
 *  no "?"). */
export function whatIcons(store, w, e) {
  const def = store.whats.get(w);
  const type = def && iconOk("type", def.wt) ? cardImg("type", def.wt) : "";
  const elem = elementIcon(store, e);
  return type || elem ? `<span class="dmwhat">${type}${elem}</span>` : "";
}

export const TAGS = [[FLAG.HEAL, "dmg.heal", "heal"], [FLAG.KILL, "dmg.kill", "kill"], [FLAG.CRIT, "dmg.crit", "crit"], [FLAG.DOWNED, "dmg.downed", "down"],
  [FLAG.WIND, "dmg.wind", "wind"], [FLAG.EFFECT, "dmg.effect", "fx"], [FLAG.TICK, "dmg.tick", "tick"]];
