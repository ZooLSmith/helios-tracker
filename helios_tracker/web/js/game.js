// The game the mod runs in: what the level message says (games.py's profile - its "game" key and "features") and each
// game's own data on the page. Nothing else on the page names a game: it asks here (hasFeature, gameData).
// - A system a game doesn't have: a feature it lacks (a layer's "needs": its row hidden, games.py's same names).
// - Data that differs (its rarity tiers, a currency's sign): a field of gameData(), BL2's unless the game sets its own.
// Its label variants ("group.relic.tps") and colour tokens ("--layer-pickup-eridium-tps") are keyed by gameKey().
// Pure (no DOM, no imports: model.js and i18n.js's settings read it): tested offline under Node.

// RarityLevel colour entry -> tier name. The game sends its table with the level (model.js setRarityTable): its colour
// per level and its colour entry - levels sharing an entry are one tier (5 and 7-10: legendary,
// tools/probes/probe_rarity3.txt). The names are ours (the game has none for rarities: the user confirmed them in
// game), by colour entry; an entry without one shows its number ("Rarity 503") in its colour.
const TIER_BY_ENTRY = { 0: "misc", 1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary", 6: "etech",
  7: "legendary", 12: "pearl", 13: "seraph", 17: "effervescent" };
// The rarities every game has (their gear layers: model.js LOOT_RARITIES)
const RARITIES = ["common", "uncommon", "rare", "epic", "legendary", "misc"];

const BL2 = {
  tierByEntry: TIER_BY_ENTRY,
  rarities: [...RARITIES, "etech", "pearl", "seraph", "effervescent"], // the gear layers it shows
  rarityLayer: {}, // a tier shown in another tier's layer
  eridiumGlyph: "", // its eridium's map marker: a plain dot ("": no sign)
  // a chest's tier from its own definition's name (2: the big chest, 1: a weapon chest), before the loot lists' names
  // (model.js chestTier: BL2's tiers are in its loot lists' names - EpicChest..., WeaponChest...)
  chestByDefinition: [],
};
const DATA = {
  bl2: BL2,
  // The Pre-Sequel's table (its Startup.upk GD_Globals.General.Globals RarityLevelColors, offline): 19 entries - 505
  // one (entry 17: BL2 has none, its 506 there), 506 entry 18; 501's pink (entry 13, BL2's Seraph's) is its Glitch; no
  // pearlescent, no effervescent (the user) - 500 / 505 / 506 unnamed ("Rarity 500"). Its E-tech gear in the
  // Legendary layer (its one E-tech item: the Monster Trap, a mission grenade mod - the user; the item keeps its own
  // rarity: name, colour). Moonstones: an "m" disc (the game's own sign for them: a small m).
  tps: { ...BL2, tierByEntry: { 0: "misc", 1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary", 6: "etech",
    7: "legendary", 13: "glitch" }, rarities: [...RARITIES, "glitch"], rarityLayer: { etech: "legendary" }, eridiumGlyph: "m" },
  aodk: { ...BL2, rarities: RARITIES }, // (BL2's engine; its own gear not checked: the common tiers only)
  // (its rarities not checked yet: .agent/bl1.md). Its big red chest: InteractiveObj_TreasureChest (up to 6 items -
  // the user; its balances ObjectGrade_TreasureChest*); its StrongBox / Crate_Metal: not seen yet, plain containers
  // its rarity table (gd_globals RarityLevelColors, offline): entries 0 (-1..1) / 1 (2..4) white, 2 green, 3 blue,
  // 4 purple, 5-7 three legendary shades (50..100), 12 pearl (500); 8-11 the pickups' (170 / 171 / 180-190: not gear)
  bl1: { ...BL2, rarities: [...RARITIES, "pearl"], chestByDefinition: [[/treasurechest/i, 2]],
    tierByEntry: { 0: "misc", 1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary", 6: "legendary", 7: "legendary",
      12: "pearl" } },
};
const UNKNOWN = { ...BL2, rarities: RARITIES }; // before the level message (or a game the page doesn't know)

let key = "";
let features = new Set();

/** The level message's game ("bl2", "tps"...) and its features (games.py): whether the game changed. */
export function setGame(game, list) {
  const next = new Set(Array.isArray(list) ? list : []);
  const changed = (game || "") !== key || next.size !== features.size || [...next].some((f) => !features.has(f));
  key = game || "";
  features = next;
  return changed;
}
export const gameKey = () => key;
/** Whether the game has a system ("oxygen", "discovery"...: games.py's features). */
export const hasFeature = (f) => features.has(f);
/** The game's own page data (BL2's where it has none of its own). */
export const gameData = () => DATA[key] || UNKNOWN;
