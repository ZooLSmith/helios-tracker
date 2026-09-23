// What things are: layers, rarities, names, object categories. Pure (no DOM): tested offline under Node.

// Map layers, in panel order; "on" = shown by default
export const LAYERS = [
  { id: "player", color: "#3fd5ff", on: true },
  { id: "enemy", color: "#ff4b3e", on: true },
  { id: "npc", color: "#63e06a", on: true },
  { id: "vehicle", color: "#c08bff", on: true },
  { id: "objective", color: "#7cf58a", on: true },
  { id: "loot", color: "#ffb52e", on: true },
  { id: "chest", color: "#ff6b2c", on: true }, // orange-red, like the red chests
  { id: "weaponchest", color: "#e8943a", on: true },
  { id: "container", color: "#e2c170", on: false },
  { id: "vendor", color: "#4fd1c5", on: true },
  { id: "station", color: "#f0f0f0", on: false },
  { id: "other", color: "#7f8f99", on: false },
  { id: "looted", color: "#56646d", on: false }, // opened containers: nothing left to find
];
export const LAYER_COLOR = Object.fromEntries(LAYERS.map((l) => [l.id, l.color]));

export const FLOOR_UU = 600; // "another floor": more than this above / below me

// RarityLevel -> [name key, colour] (names confirmed by the user in game; colours still ours - the
// game's own table is in the backlog). The inspector shows the number next to the name.
const RARITY = {
  0: ["misc", "#9aa7ad"], 1: ["common", "#f2f2f2"], 2: ["uncommon", "#45d145"], 3: ["rare", "#3b8dff"],
  4: ["epic", "#b45cff"], 5: ["legendary", "#ff9a1f"], 6: ["etech", "#ff4fd2"], 500: ["pearl", "#3fefff"],
};
export function rarity(q) { return RARITY[q] || (q > 500 ? ["pearl", "#3fefff"] : ["unknown", "#e0e0e0"]); }

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

/** Real gear (goes into the backpack) vs other pickups, by the item's class. */
const GEAR_CLASSES = ["WillowWeapon", "WillowShield", "WillowGrenadeMod", "WillowClassMod", "WillowArtifact"];
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

/** Numbered variants of a pool merged: "Pool_Money_1", "Pool_Money_2" -> "Money". */
export function poolKinds(pools) {
  return [...new Set(pools.map((n) => String(n).replace(/^Pool_/, "").replace(/_?\d+$/, "")))];
}
