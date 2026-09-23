// What things are: layers, rarities, names, object categories. Pure (no DOM): tested offline under Node.

// Per-layer settings: what each one is (the panel builds its controls from this) and its default.
// A layer lists the ones that apply to it (LAYERS[].settings) and may change a default.
export const LAYER_SETTINGS = {
  names: { type: "bool", def: false }, // names next to the markers
  floors: { type: "choice", options: ["show", "dim", "hide"], def: "dim", tip: "set.floorsTip" }, // more than FLOOR_UU above / below
  size: { type: "range", min: 50, max: 200, step: 10, def: 100 }, // marker size, %
  range: { type: "choice", options: [0, 25, 50, 100, 200], def: 0, select: true }, // max distance from "Who", m (0: any)
  trackedOnly: { type: "bool", def: false }, // objectives: only the tracked mission's
};
const COMMON = ["names", "floors", "size", "range"];

// RarityLevel -> [name key, colour] (names confirmed by the user in game; colours still ours - the
// game's own table is in the backlog). The inspector shows the number next to the name.
const RARITY = {
  0: ["misc", "#9aa7ad"], 1: ["common", "#f2f2f2"], 2: ["uncommon", "#45d145"], 3: ["rare", "#3b8dff"],
  4: ["epic", "#b45cff"], 5: ["legendary", "#ff9a1f"], 6: ["etech", "#ff4fd2"], 500: ["pearl", "#3fefff"],
};
export function rarity(q) { return RARITY[q] || (q > 500 ? ["pearl", "#3fefff"] : ["unknown", "#e0e0e0"]); }
const RARITY_COLOR = Object.fromEntries(Object.values(RARITY));

// The panel's categories, in order
export const LAYER_GROUPS = ["characters", "loot", "world"];

// Gear on the ground: a layer per rarity (misc: rarity 0 and unknown levels), in the Gear folder
const LOOT_RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "etech", "pearl", "misc"];
// Other pickups: a layer per kind (the collector's "pk", from the game's inventory card), in the
// Pickups folder; anything else (ECHO logs, eridium until probed...) is "other"
const PICKUP_KINDS = [["ammo", "#d8c07a"], ["cash", "#6fd46f"], ["health", "#ff6f7d"], ["other", "#9aa7ad"]];

// Map layers, in panel order within their category. "on": shown by default; toggle: false = can't
// be hidden (players), only configured. folder: a row holding the layers whose parent it is (no
// settings of its own; its box turns them all on / off). rarity: named by the game's rarity.
// legacy: the id whose on / off the old storage kept (the single Loot layer, now one per rarity).
export const LAYERS = [
  { id: "player", group: "characters", color: "#f4f4f4", toggle: false, settings: ["names", "floors", "size"], defaults: { names: true } },
  { id: "enemy", group: "characters", color: "#ff4b3e", on: true, settings: COMMON },
  { id: "npc", group: "characters", color: "#63e06a", on: true, settings: COMMON },
  { id: "vehicle", group: "characters", color: "#c08bff", on: true, settings: COMMON },
  { id: "gear", group: "loot", color: "#ffb52e", folder: true, settings: [] },
  ...LOOT_RARITIES.map((r) => ({ id: "loot." + r, group: "loot", parent: "gear", legacy: "loot", rarity: r, color: RARITY_COLOR[r], on: true, settings: COMMON })),
  // not gear: no real rarity (made-up levels, for their colour in game)
  { id: "pickups", group: "loot", color: "#d8c07a", folder: true, settings: [] },
  ...PICKUP_KINDS.map(([k, color]) => ({ id: "pickup." + k, group: "loot", parent: "pickups", legacy: "loot", color, on: true, settings: COMMON,
    ...(k === "other" ? { tip: "layer.pickup.otherTip" } : {}) })),
  { id: "containers", group: "loot", color: "#e2c170", folder: true, settings: [] },
  { id: "chest", group: "loot", parent: "containers", color: "#ff6b2c", on: true, settings: COMMON }, // orange-red, like the red chests
  { id: "weaponchest", group: "loot", parent: "containers", color: "#e8943a", on: true, settings: COMMON },
  { id: "container", group: "loot", parent: "containers", color: "#e2c170", on: false, settings: COMMON }, // the other ones
  { id: "looted", group: "loot", parent: "containers", color: "#56646d", on: false, settings: COMMON }, // opened: nothing left to find
  { id: "objective", group: "world", color: "#7cf58a", on: true, settings: ["names", "floors", "size", "trackedOnly"] },
  { id: "vendor", group: "world", color: "#4fd1c5", on: true, settings: COMMON },
  { id: "station", group: "world", color: "#f0f0f0", on: false, settings: COMMON },
  { id: "other", group: "world", color: "#7f8f99", on: false, settings: COMMON },
];
export const LAYER_COLOR = Object.fromEntries(LAYERS.map((l) => [l.id, l.color]));

/** The translation key of a layer's name. */
export const layerNameKey = (l) => (l.rarity ? "rarity." + l.rarity : "layer." + l.id);

/** The layer of a pickup: its rarity's for gear, else its kind's ("pickup.ammo"...). */
export function lootLayer(p) {
  if (!isGear(p.c)) return "pickup." + (PICKUP_KINDS.some(([k]) => k === p.pk) ? p.pk : "other");
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
  if (/fasttravel|fast travel|travelstation|newu|respawn|quickchange|customiz/.test(s)) return "station";
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
