// What things are: layers, rarities, names, object categories. Pure (no DOM): tested offline under Node.

// Per-layer settings: what each one is (the panel builds its controls from this) and its default.
// A layer lists the ones that apply to it (LAYERS[].settings) and may change a default.
export const LAYER_SETTINGS = {
  names: { type: "bool", def: false }, // names next to the markers
  floors: { type: "choice", options: ["show", "dim", "hide"], def: "dim", tip: "set.floorsTip" }, // more than FLOOR_UU above / below
  size: { type: "range", min: 50, max: 200, step: 10, def: 100 }, // marker size, %
  opacity: { type: "range", min: 10, max: 100, step: 5, def: 100 }, // area names, fog of war: how opaque, %
  range: { type: "choice", options: [0, 25, 50, 100, 200], def: 0, select: true }, // max distance from "Who", m (0: any)
  trackedOnly: { type: "bool", def: false }, // objectives: only the tracked mission's
};
const COMMON = ["names", "floors", "size", "range"];

// RarityLevel -> [name key, colour]. The game's own, sent with the level (setRarityTable): its colour
// per level and its colour entry - levels sharing an entry are one tier (5 and 7-10: legendary,
// tools/probe_rarity3.txt). The names are ours (the game has none for rarities: the user confirmed
// them in game), by colour entry; an entry without one shows its number ("Rarity 503") in its colour.
const TIER_BY_ENTRY = { 0: "misc", 1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary", 6: "etech",
  7: "legendary", 12: "pearl", 13: "seraph", 17: "effervescent" };
// Before the game's table (or without it): the usual levels, in the game's colours
const RARITY = {
  0: ["misc", "#cdc1af"], 1: ["common", "#ffffff"], 2: ["uncommon", "#3dd20b"], 3: ["rare", "#3c8eff"],
  4: ["epic", "#a83fe5"], 5: ["legendary", "#ffb400"], 6: ["etech", "#ca00a8"], 500: ["pearl", "#00ffff"],
  501: ["seraph", "#ff9ab8"], 506: ["effervescent", "#f2ffa1"],
};
let gameRarity = {}; // "level" -> [colour entry, "#rrggbb"]
export function setRarityTable(table) { gameRarity = table && typeof table === "object" ? table : {}; }
export function rarity(q) {
  const game = gameRarity[String(q)];
  if (game) return [TIER_BY_ENTRY[game[0]] || "unknown", game[1]];
  return RARITY[q] || (q > 500 ? ["pearl", RARITY[500][1]] : ["unknown", "#e0e0e0"]);
}
const RARITY_COLOR = Object.fromEntries(Object.values(RARITY));

// The effervescent rarity's rainbow (the game's RARITY_Rainbow) at a time (ms, the page's clock): its hue goes round
// once per cycle - the drawer's name (drawer.css, 3 s) and the map's markers in step. Called per frame drawn only
// (never a frame of its own: it moves at the Refresh rate)
export const RAINBOW_CYCLE = 3000;
export function rainbowAt(ms) {
  return `hsl(${Math.round(((ms % RAINBOW_CYCLE) / RAINBOW_CYCLE) * 360)} 65% 80%)`; // (pastel, like the game's: not saturated)
}

// The panel's categories, in order
export const LAYER_GROUPS = ["characters", "loot", "world"];

// Gear on the ground: a layer per rarity (misc: rarity 0 and unknown levels), in the Gear folder
const LOOT_RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "etech", "pearl", "seraph", "effervescent", "misc"];
// Other pickups: a layer per kind (the collector's "pk", from the game's inventory card; "mission": a
// mission item - ECHO logs, objects an objective asks for - in the objectives' green), in the Pickups
// folder; anything else (other currencies...) is "other"
const PICKUP_KINDS = ["ammo", "cash", "eridium", "health", "mission", "other"];

// Map layers, in panel order within their category. "on": shown by default; toggle: false = can't
// be hidden (players), only configured. folder: a row holding the layers whose parent it is (no
// settings of its own; its box turns them all on / off). rarity: named by the game's rarity.
// legacy: the id whose on / off the old storage kept (the single Loot layer, now one per rarity).
export const LAYERS = [
  { id: "player", group: "characters", toggle: false, settings: ["names", "floors", "size"], defaults: { names: true } },
  { id: "enemy", group: "characters", on: true, settings: COMMON },
  { id: "npc", group: "characters", on: true, settings: COMMON },
  { id: "vehicle", group: "characters", on: true, settings: COMMON },
  { id: "gear", group: "loot", folder: true, settings: [] },
  ...LOOT_RARITIES.map((r) => ({ id: "loot." + r, group: "loot", parent: "gear", legacy: "loot", rarity: r, color: RARITY_COLOR[r], on: true, settings: COMMON })),
  // not gear: no real rarity (made-up levels, for their colour in game)
  { id: "pickups", group: "loot", folder: true, settings: [] },
  ...PICKUP_KINDS.map((k) => ({ id: "pickup." + k, group: "loot", parent: "pickups", legacy: "loot", on: true, settings: COMMON,
    ...(k === "other" ? { tip: "layer.pickup.otherTip" } : {}) })),
  { id: "containers", group: "loot", folder: true, settings: [] },
  { id: "chest", group: "loot", parent: "containers", on: true, settings: COMMON },
  { id: "weaponchest", group: "loot", parent: "containers", on: true, settings: COMMON },
  { id: "container", group: "loot", parent: "containers", on: false, settings: COMMON }, // the other ones
  { id: "looted", group: "loot", parent: "containers", on: false, settings: COMMON }, // opened: nothing left to find
  { id: "objective", group: "world", on: true, settings: ["names", "floors", "size", "trackedOnly"] },
  // NPCs with a mission to give / take back: the game's yellow "!" (its directive markers, or worked out
  // from the NPCs' own mission lists - collector _npc_givers)
  { id: "giver", group: "world", on: true, settings: COMMON },
  { id: "vendor", group: "world", on: true, settings: COMMON },
  // the Cult of the Vault symbols (IO_VaultRoy: clicked to discover, a challenge - tools/probe_directors.txt;
  // discovered ones not told apart yet)
  { id: "vaultsymbol", group: "world", on: true, settings: COMMON },
  { id: "station", group: "world", on: false, settings: COMMON },
  // the level's areas (the game's discovery areas, tools/probe_discovery.txt): their names, the ones not
  // discovered yet dimmed; the fog of war: the game's fog pieces over the areas not discovered (its count)
  { id: "area", group: "world", on: true, settings: ["size", "opacity"] },
  { id: "fog", group: "world", on: false, settings: ["opacity"] },
  { id: "other", group: "world", on: false, settings: COMMON },
];
export const LAYER_COLOR = Object.fromEntries(LAYERS.map((l) => [l.id, l.color]));

/** The layers' colours, from the page's tokens (base.css --layer-<id>, "." as "-"): read(name) -> the value
 *  (shapes.js initColors). The rarity layers keep the game's. */
export function setLayerColors(read) {
  for (const l of LAYERS) {
    if (l.rarity) continue;
    const c = read("--layer-" + l.id.replace(".", "-"));
    if (c) { l.color = c; LAYER_COLOR[l.id] = c; }
  }
}

/** The translation key of a layer's name. */
export const layerNameKey = (l) => (l.rarity ? "rarity." + l.rarity : "layer." + l.id);

/** The layer of a pickup: its rarity's for gear, else its kind's ("pickup.ammo"...). */
export function lootLayer(p) {
  if (!isGear(p.c)) return "pickup." + (PICKUP_KINDS.includes(p.pk) ? p.pk : "other");
  const [key] = rarity(p.q || 0);
  return LOOT_RARITIES.includes(key) ? "loot." + key : "loot.misc";
}

export const FLOOR_UU = 600; // "another floor": more than this above / below me

/** A made-up name from an object / class name, readable and marked as a guess:
 *  "BullymongPile" -> "Bullymong Pile ?", "WillowAIPawn" -> "AI Pawn ?" (no-break space; the
 *  engine's "Willow" class prefix dropped). */
export function prettyRaw(s) {
  const words = String(s || "").replace(/^Willow(?=[A-Z_])/, "").replace(/_/g, " ")
    .replace(/([a-z\d])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/\s+/g, " ").trim();
  return (words || "?") + " ?";
}

/** Display text of anything with a name ("n"), made-up ones ("raw": 1) prettified. */
export function nameText(o) { return o.raw ? prettyRaw(o.n) : String(o.n || "?"); }

/** Real gear (goes into the inventory, has a real rarity) vs other pickups, by the item's class.
 *  Customization items (skins, heads: probe_pickups.py - RarityLevel 2 on a vehicle skin) count. */
const GEAR_CLASSES = ["WillowWeapon", "WillowShield", "WillowGrenadeMod", "WillowClassMod", "WillowArtifact",
  "WillowUsableCustomizationItem"];
export function isGear(cls) { return GEAR_CLASSES.some((g) => String(cls || "").startsWith(g)); }

/** Chest tier from the game's loot list names: 2 = an "Epic" list (the red chests: EpicChestRedLoot),
 *  1 = a "WeaponChest" one (metal crates, bandit weapon chests: WeaponChestWhiteLoot...), 0 = none. */
export function chestTier(o) {
  const lists = o.lists || [];
  return lists.some((l) => /epic/i.test(l)) ? 2 : lists.some((l) => /weaponchest/i.test(l)) ? 1 : 0;
}

/** Interactive objects -> category, from their definition / class name. */
export function objectCategory(o) {
  if (o.looted) return "looted";
  // The game's loot lists are named by tier: an "Epic" one (EpicChestRedLoot...) = a chest
  const tier = chestTier(o);
  if (tier) return tier === 2 ? "chest" : "weaponchest";
  const s = (o.d + " " + o.n + " " + o.c).toLowerCase();
  if (/vending|vendor|shop/.test(s)) return "vendor";
  if (/vaultroy|vaultsymbol/.test(s)) return "vaultsymbol"; // before "container": "Vault..." isn't a vault chest
  // machines you use: fast travel, New-U, Quick Change, the Catch-A-Ride terminals (vehicle spawns)
  if (/fasttravel|fast travel|travelstation|newu|respawn|quickchange|customiz|catcharide|catch-a-ride|vehiclespawn/.test(s)) return "station";
  if (/chest|lockbox|lootable|loot|safe|cache|box|crate|locker|dumpster|toilet|cooler|cabinet|stash|pile/.test(s)) return "container";
  return "other";
}

/** Game text as plain text: its markup dropped - "[place]Sanctuary[-place]" -> "Sanctuary", HTML-ish
 *  tags too (descriptions can hold a <br>: a space here). For HTML with the line breaks: gameTextHtml. */
export function cleanGameText(s) {
  return String(s || "").replace(/<br\s*\/?>/gi, " ").replace(/<\/?[a-z][^<>]*>/gi, "").replace(/\[-?[a-z_]+\]/gi, "")
    .replace(/\s+/g, " ").trim();
}

/** Numbered variants of a pool merged: "Pool_Money_1", "Pool_Money_2" -> "Money". */
export function poolKinds(pools) {
  return [...new Set(pools.map((n) => String(n).replace(/^Pool_/, "").replace(/_?\d+$/, "")))];
}
