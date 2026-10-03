"""
Offline sanity check (plain Python, no game): imports helios_tracker with fake SDK modules, runs
its collectors against fake objects, extracts real tactical maps from the game's packages, serves
the page over HTTP and runs the page's JS modules under Node.

    python tools/offline_check.py

Catches import errors, typos and broken page modules - not in-game behaviour.
"""

import sys
import types
from pathlib import Path

import project

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# region Fake SDK


def _install_fakes() -> None:
    u = types.ModuleType("unrealsdk")
    for n in ("find_object", "find_enum", "make_struct", "construct_object", "load_package"):
        setattr(u, n, lambda *a, **k: None)
    u.find_all = lambda *a, **k: []
    hooks = types.ModuleType("unrealsdk.hooks")
    hooks.Type = type("Type", (), {"PRE": 0, "POST": 1, "POST_UNCONDITIONAL": 2})
    hooks.Block = object
    hooks.add_hook = hooks.remove_hook = lambda *a, **k: None
    unreal = types.ModuleType("unrealsdk.unreal")

    class WeakPointer:
        def __init__(self, o=None):  # noqa: ANN001, ANN204
            self.o = o

        def __call__(self):  # noqa: ANN204
            return self.o

        def replace(self, o):  # noqa: ANN001, ANN202
            self.o = o

    unreal.WeakPointer = WeakPointer
    unreal.UObject = unreal.BoundFunction = unreal.WrappedStruct = object
    u.hooks, u.unreal = hooks, unreal
    sys.modules.update({"unrealsdk": u, "unrealsdk.hooks": hooks, "unrealsdk.unreal": unreal})

    mb = types.ModuleType("mods_base")

    class Opt:
        def __init__(self, identifier, value=None, **kw):  # noqa: ANN001, ANN003, ANN204
            self.identifier, self.value = identifier, value
            self.__dict__.update(kw)

    class Nested(Opt):
        def __init__(self, identifier, children=(), **kw):  # noqa: ANN001, ANN003, ANN204
            super().__init__(identifier, None, children=children, **kw)

    mb.BoolOption = mb.SliderOption = mb.SpinnerOption = mb.DropdownOption = mb.ButtonOption = mb.HiddenOption = Opt
    mb.NestedOption = mb.GroupedOption = Nested
    def fake_hook(*a, **k):  # marks what it decorates: every hook must be in build_mod's list (checked)
        def mark(f):
            f._helios_hook = a[0] if a else True
            return f
        return mark
    mb.hook = fake_hook
    mb.build_mod = lambda **k: types.SimpleNamespace(**k)
    mb.Library = type("Library", (), {})
    mb.Mod = object
    mb.EInputEvent = types.SimpleNamespace(IE_Pressed=0, IE_Released=1, IE_Repeat=2)

    class FakeGame:  # mods_base.Game: the current game (a test switches it: FakeGame.current)
        current = types.SimpleNamespace(name="BL2")

        @classmethod
        def get_current(cls):  # noqa: ANN206
            return cls.current
    mb.Game = FakeGame

    class PC:
        class Pawn:
            DrivenVehicle = None

            def IsInjured(self):  # noqa: ANN202, N802
                return False

            def IsActionSkillRunning(self):  # noqa: ANN202, N802
                return False

        MyWillowPawn = Pawn()
        bViewingThirdPersonMenu = False
        SkillCooldownPool = types.SimpleNamespace(
            Data=types.SimpleNamespace(CurrentValue=12.3456, ConsumptionRate=1.0, ConsumptionRateModifierStack=[]),
        )
        WorldInfo = types.SimpleNamespace(TimeSeconds=100.0)
        ActionSkillTime = -1.0  # not running

        def GetActionSkillDuration(self):  # noqa: ANN202, N802
            return 24.0 if 0 <= self.ActionSkillTime < 1 else 0.0
        ExpPool = types.SimpleNamespace(Data=types.SimpleNamespace(CurrentValue=77851.0))
        PlayerReplicationInfo = types.SimpleNamespace(ExpLevel=12, ExpPointsNextLevelAt=78861)

        def GetExpPointsRequiredForLevel(self, level):  # noqa: ANN001, ANN202, N802
            return 70000

        def GetHUDMovie(self):  # noqa: ANN202, N802
            return ("hud", None)

    mb.get_pc = lambda **k: PC()
    mb.ENGINE = types.SimpleNamespace(GetCurrentWorldInfo=lambda: None)
    sys.modules["mods_base"] = mb
    uu = types.ModuleType("ui_utils")  # (the updater's dialog / bottom-left message: game UI, nothing to run here)
    uu.OptionBox = uu.OptionBoxButton = lambda *a, **k: types.SimpleNamespace(show=lambda *a: None, **k)
    uu.show_coop_message = uu.hide_coop_message = lambda *a: None
    sys.modules["ui_utils"] = uu


# endregion


GAME_COOKED = project.cooked_dir()  # project.json's game; None: the game file checks are skipped

# Run as an ES module: node test.mjs <web dir> <image file> <record channel scenarios (JSON)>
PAGE_TEST_JS = """
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
const [web, imageFile, recordsFile] = process.argv.slice(2);
const load = (file) => import(pathToFileURL(path.join(web, file)).href);
// Every module of the page: resolves each import (paths and names) and runs its top level, which
// must not touch the DOM (main.js's start() does the hookup)
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? walk(path.join(dir, e.name)) : e.name.endsWith(".js") ? [path.relative(web, path.join(dir, e.name))] : []);
const modules = walk(web);
for (const file of modules) await load(file);
const { decodeTexture } = await load("js/dxt.js");
const { worldToMap, mapToWorld, yawToAngle, largestFreeRect } = await load("js/geo.js");
// Follow: the largest part of the screen no panel covers (1600 x 900; the panel top-left, the inspector right)
const panel = { left: 12, top: 12, right: 268, bottom: 700 }, drawer = { left: 1208, top: 12, right: 1588, bottom: 888 };
const freeRects = [largestFreeRect(1600, 900, []), largestFreeRect(1600, 900, [panel]),
  largestFreeRect(1600, 900, [panel, drawer]), largestFreeRect(1600, 900, [{ ...panel, bottom: 60 }, drawer])];
const { prettyRaw, nameText } = await load("js/model.js");
const rgba = decodeTexture("PF_DXT5", 468, 512, fs.readFileSync(imageFile));
const level = { center: [-3072, -10240], upp: 128, north: 0 };
// probe_map2 samples (Sanctuary): world -> map px measured from the minimap
const samples = [[10635.4, 5702.0, 124.54, -107.11], [7093.2, -2801.0, 58.11, -79.46]];
let err = 0, back = 0;
for (const [x, y, mx, my] of samples) {
  const [a, b] = worldToMap(level, x, y);
  err = Math.max(err, Math.hypot(a - mx, b - my));
  for (const north of [0, 90]) { // map -> world undoes world -> map; the north offset moves nothing (notes.md)
    const turned = { ...level, north };
    const [wx, wy] = mapToWorld(turned, ...worldToMap(turned, x, y));
    back = Math.max(back, Math.hypot(wx - x, wy - y));
    const [ta, tb] = worldToMap(turned, x, y);
    err = Math.max(err, Math.hypot(ta - mx, tb - my));
  }
}
const right = yawToAngle(level, 16384);
const raw = ["BullymongPile", "WillowAIPawn", "Fire_Barrel02", "WillowInteractiveObject", "Willowtree"].map(prettyRaw)
  .concat([nameText({ n: "Zer0" })]);
// Settings: the old one-key-per-setting storage carries over; saved values are validated
const { merge, fromLegacy } = await load("js/settings.js");
const { LAYERS, LAYER_GROUPS, LAYER_SETTINGS, layerNameKey, lootLayer, rarity, setRarityTable } = await load("js/model.js");
const legacy = { "layer.enemy": false, "layer.loot": false, labels: true, height: false, zoom: 2.5, smooth: false, lang: "fr", tab: "skills" };
const migrated = merge(fromLegacy((k, d) => (k in legacy ? legacy[k] : d)));
const checked = merge({ layers: { enemy: { on: "yes", size: 999, floors: "nope", bogus: 1 }, nosuch: {} },
  view: { follow: 1, motion: 15 }, ui: { openLayers: ["loot", 3], drawer: { k: "mission", id: "M_Plan" } } });
const badDrawer = merge({ ui: { drawer: "player" } }).ui.drawer; // what the drawer shows: an object or nothing
// The translation keys the layer panel builds from the schema
const i18nKeys = [...LAYERS.map(layerNameKey), ...LAYERS.filter((l) => l.tip).map((l) => l.tip), ...LAYER_GROUPS.map((g) => "lgroup." + g)];
for (const [k, s] of Object.entries(LAYER_SETTINGS)) {
  i18nKeys.push("set." + k);
  if (s.tip) i18nKeys.push(s.tip);
  if (s.type === "choice" && !s.select) i18nKeys.push(...s.options.map((o) => `set.${k}.${o}`));
}
// Pickups -> layer: gear by rarity (unknown levels: misc), the rest by the collector's kind ("pk")
const lootLayers = [[1, "WillowWeapon"], [5, "WillowShield"], [500, "WillowArtifact"], [520, "WillowWeapon"], [0, "WillowClassMod"],
  [77, "WillowGrenadeMod"], [5, "WillowUsableItem"], [181, "", "cash"], [0, "WillowUsableItem", "ammo"], [171, "WillowUsableItem", "health"],
  [0, "WillowUsableItem", "bogus"], [2, "WillowUsableCustomizationItem"], [0, "WillowUsableItem", "eridium"]].map(([q, c, pk]) => lootLayer({ q, c, pk }));
// The game's rarity table (tools/probes/probe_rarity3.txt): 7-10 share legendary's colour entry; 503 has no name
setRarityTable({ "5": [5, "#ffb400"], "9": [7, "#ffb400"], "501": [13, "#ff9ab8"], "503": [15, "#9132c8"] });
const gameRarity = [5, 9, 501, 503].map((q) => rarity(q)).concat([lootLayer({ q: 9, c: "WillowWeapon" })]);
setRarityTable(null);
// The game (game.js: the level message's "game" and "features" - games.py): each game's own tiers and layers; a level
// message with the same game and features (in any order) isn't a change (the layers / colours not rebuilt)
const { setGame } = await load("js/game.js");
const { layerInGame } = await load("js/model.js");
const gameIds = ["loot.pearl", "loot.glitch", "loot.etech", "oxygen", "pickup.oxygen", "jumppad", "area", "fog", "enemy",
  "pickup.eridium", "vaultsymbol", "buff", "slots", "pickup.mission"];
const gameShown = () => gameIds.filter((id) => layerInGame(LAYERS.find((l) => l.id === id)));
const gameNone = gameShown(); // (before the level message: no game's own layers)
const gameSwitch = [setGame("tps", ["discovery", "oxygen", "jumppads", "tacmap"]), setGame("tps", ["tacmap", "jumppads", "oxygen", "discovery"])];
setRarityTable({ "501": [13, "#ff9ab8"], "6": [6, "#ca00a8"] });
const gameTps = { shown: gameShown(), glitch: rarity(501)[0], etech: lootLayer({ q: 6, c: "WillowWeapon" }) };
setGame("bl1", []);
const gameBl1 = gameShown();
// BL1's big chest: its own definition says it (no tier in its pools' names: Chest Weapons Pistols / Long Guns, Chest Ammo)
const { chestTier: gameChestTier } = await load("js/model.js");
gameBl1.push(gameChestTier({ d: "InteractiveObj_TreasureChest", loot: ["Pool_Chest_Weapons_Pistols", "Pool_Chest_Ammo"] }),
  gameChestTier({ d: "InteractiveObj_StrongBox" }));
// its rarity entry 0 (-1..1, white like entry 1): common (the wiki: common 0-4) - BL2's 0 is its beige "misc"
setRarityTable({ "0": [0, "#ffffff"], "3": [1, "#ffffff"] });
gameBl1.push(rarity(0)[0], rarity(3)[0]);
// its gear: also its one item class for shields, grenade mods, com decks (not its usable items: ammo, health)
const { isGear: gameIsGear, cardIconKey } = await load("js/model.js");
gameBl1.push(gameIsGear("WillowEquipAbleItem"), gameIsGear("WillowUsableItem"));
// card icon keys: "none" (the game's frame for no logo) and odd ones not fetched
gameBl1.push([cardIconKey("jakobs"), cardIconKey("none"), cardIconKey("None"), cardIconKey("a/b"), cardIconKey(undefined)]);
setGame("bl2", ["discovery", "tacmap"]);
const gameBl2 = { shown: gameShown(), seraph: rarity(501)[0], etech: lootLayer({ q: 6, c: "WillowWeapon" }) };
setGame("", []);
setRarityTable(null);
const gameOut = { gameNone, gameSwitch, gameTps, gameBl1, gameBl2 };
const unknownSettings = LAYERS.flatMap((l) => l.settings.filter((k) => !LAYER_SETTINGS[k]).map((k) => l.id + "." + k));
// Missions: state (available = every mission it needs done), the tree, objective states
const { missionTree, objectiveStates, missionCounts, missionAreas } = await load("js/missions.js");
const log = [
  { i: "a", num: 1, plot: 1, st: "Complete", deps: [] }, { i: "b", num: 2, plot: 1, st: "Active", deps: ["a"],
    obj: [{ c: 1 }, { c: 5 }, { c: 1, opt: 1 }], p: [1, 3], cur: [1, 2] },
  { i: "c", num: 3, plot: 1, st: "NotStarted", deps: ["b"] }, { i: "s1", num: 20, plot: 0, st: "NotStarted", deps: ["a"], kick: 1 },
  { i: "s3", num: 22, plot: 0, st: "NotStarted", deps: ["a"] },
  { i: "s2", num: 21, plot: 0, st: "NotStarted", deps: ["s1"] }, { i: "o", num: 30, plot: 0, st: "Complete", deps: [] },
  // ready to turn in (tools/probes/probe_turnin.txt), and a status the page doesn't know (shown by its name)
  { i: "x", num: 40, plot: 0, st: "RequiredObjectivesComplete", deps: ["gone"] }, { i: "r", num: 41, plot: 0, st: "ReadyToTurnIn", deps: [] },
  { i: "f", num: 42, plot: 0, st: "Failed", deps: [] },
  // every mission it needs done, but it waits on an objective of b (its ObjectiveDependency): locked
  { i: "w", num: 43, plot: 0, st: "NotStarted", deps: ["a"], wait: { o: "Reach the gate", m: "b" } }];
const tree = missionTree(log);
const { gameTextHtml } = await load("js/dom.js");
const { cleanGameText } = await load("js/model.js");
const gameText = [gameTextHtml("Go to [place]Sanctuary[-place].<br>Find <font color='#f00'>Roland</font> & <b>win</b><BR/><script>x</script>"),
  cleanGameText("Line one.<br>Line <i>two</i> [place]here[-place]")];
const flat = (nodes, d = 0) => nodes.flatMap((n) => [`${"-".repeat(d)}${n.m.i}:${n.state}`, ...flat(n.children, d + 1)]);
const areaLog = [{ i: "a", num: 5, st: "Complete", deps: [], area: "Sanctuary" }, { i: "b", num: 1, st: "Active", deps: [], area: "Shelf" },
  { i: "c", num: 9, st: "NotStarted", deps: [] }, { i: "d", num: 3, st: "NotStarted", deps: [], area: "Sanctuary", kick: 1 }];
const areas = missionAreas(areaLog).map((a) => `${a.area}:${a.nodes.map((n) => n.m.i).join("")}`);
const { searchMissions } = await load("js/missions.js");
const searchLog = [{ i: "a", num: 2, st: "Complete", deps: [], n: "Ménage à Liar's Berg", area: "Southern Shelf" },
  { i: "b", num: 1, st: "NotStarted", deps: ["x"], n: "Le bruit et la fourrure", area: "Southern Shelf", giver: "Hammerlock" }];
const search = ["menage", "SOUTHERN", "shelf hammer", "", "nothing"].map((q) => searchMissions(searchLog, q).map((n) => `${n.m.i}:${n.state}`).join(","));
// The player Info tab, from a pawn in the state: state, vitals, action skill, timed effects, melee cooldown
const { S } = await load("js/state.js");
const { playerInfoHtml } = await load("js/ui/playerinfo.js");
S.pawns.set("p1", { i: "p1", k: "me", h: 60, m: 100, s: 20, sm: 50, x: 0, y: 0, z: 0, r: 0,
  ak: ["a", 0.6, 12, "Gunzerking"], ps: [["Locked and Loaded - active", 3.4, 5.5]], mk: [0.5, 7.5] });
S.pawns.set("p2", { i: "p2", k: "player", h: 0, m: 100, s: 0, sm: 0, x: 0, y: 0, z: 0, r: 0, dn: 1 });
const infoHtml = [playerInfoHtml({ i: "p1", local: 1, lvl: 30, xp: [500, 1000] }), playerInfoHtml({ i: "p2" }), playerInfoHtml({ i: "gone" })];
// "Best now": doable (active / available / unknown) + locked one step away; ranked by goal, per level
const { rankMissions } = await load("js/missions.js");
const rwAt = (xp, cash, alt) => ({ "30": { xp, cash, cur: "Credits", ...(alt ? { alt } : {}) } });
const bestLog = [
  { i: "d", num: 1, st: "Complete", deps: [] },
  { i: "a", num: 2, st: "Active", deps: ["d"], obj: [{ c: 1 }, { c: 1 }], p: [1, 0], rw: rwAt(1000, 10) },
  { i: "v", num: 3, st: "NotStarted", deps: ["d"], kick: 1, obj: [{ c: 1 }, { c: 1 }, { c: 1 }], rw: rwAt(500, 400) },
  { i: "u", num: 4, st: "NotStarted", deps: ["d"], obj: [{ c: 1 }], rw: rwAt(300, 50, { xp: 2000, cash: 0 }) },
  { i: "l1", num: 5, st: "NotStarted", deps: ["a"], obj: [{ c: 1 }], rw: rwAt(100, 1) },
  { i: "l2", num: 6, st: "NotStarted", deps: ["l1"], rw: rwAt(9999, 9999) },
  // the biggest reward, but after "a": never listed above it (and its effort includes a's)
  { i: "l3", num: 13, st: "NotStarted", deps: ["a"], obj: [{ c: 1 }], rw: rwAt(9000, 0) },
  { i: "e", num: 7, st: "NotStarted", deps: ["d"], kick: 1 },
  // a DLC's first mission (needs nothing, never offered: unknown) - the ones after it stay out
  { i: "r", num: 8, st: "NotStarted", deps: [] }, { i: "rc", num: 9, st: "NotStarted", deps: ["r"], rw: rwAt(5000, 5000) },
  // DLCs: never-offered missions only once the DLC is started (x: DLC 1 not started; y: DLC 2 started by y0)
  { i: "x", num: 10, st: "NotStarted", deps: [], dlc: "DLC1", rw: rwAt(7000, 0) },
  { i: "y0", num: 11, st: "Complete", deps: [], dlc: "DLC2" }, { i: "y", num: 12, st: "NotStarted", deps: [], dlc: "DLC2" }];
const finishLog = [{ i: "f1", num: 1, st: "ReadyToTurnIn", deps: [], ml: 3, mlk: 1 }, { i: "f2", num: 2, st: "Active", deps: [], ml: 7, mlk: 1 },
  { i: "f3", num: 3, st: "NotStarted", deps: [], ml: 2 }, { i: "f4", num: 4, st: "Active", deps: [], ml: 1, mlk: 1 }];
const finish = rankMissions(finishLog, "finish", 8).rows.map((r) => `${r.m.i}:${r.score}`).join(",");
// missions the game rates hard / impossible for the player (3+ levels above): left out, counted;
// tough (1-2 above) stays
const highLog = [{ i: "ok", num: 1, st: "Active", deps: [], ml: 9, mlk: 1, rw: { "8": { xp: 100 } } },
  { i: "t2", num: 3, st: "Active", deps: [], ml: 10, mlk: 1, rw: { "8": { xp: 50 } } },
  { i: "h3", num: 4, st: "Active", deps: [], ml: 11, mlk: 1, rw: { "8": { xp: 9000 } } },
  { i: "dlc", num: 2, st: "Active", deps: [], ml: 30, mlk: 1, rw: { "8": { xp: 7890 } } },
  // locked, no level of its own (region never visited): the level of the missions it waits on
  { i: "dlcKid", num: 5, st: "NotStarted", deps: ["dlc"], rw: { "8": { xp: 9999 } } },
  { i: "okKid", num: 6, st: "NotStarted", deps: ["ok"], rw: { "8": { xp: 10 } } }];
const high = rankMissions(highLog, "effort", 8, { impossible: 5, hard: 3, tough: 1, normal: -3 });
const tooHigh = { rows: high.rows.map((r) => r.m.i), n: high.tooHigh, lv: high.minTooHigh, total: high.totalXp };
const best = Object.fromEntries(["xp", "cash", "effort"].map((g) => [g, rankMissions(bestLog, g, 30).rows.map((r) => r.m.i).join("")]));
const bestAt30 = rankMissions(bestLog, "xp", 30);
best.after = bestAt30.rows.find((r) => r.m.i === "l1").after;
best.total = bestAt30.totalXp;
best.otherLevel = rankMissions(bestLog, "xp", 12).rows.filter((r) => r.known).length;
const { missionDifficulty } = await load("js/missions.js");
const th = { impossible: 5, hard: 3, tough: 1, normal: -3 };
const difficulty = [[9, 4], [6, 4], [4, 4], [2, 4], [1, 5], [3, 0]].map(([ml, level]) => missionDifficulty({ ml }, level, th))
  .concat([missionDifficulty({ ml: 0 }, 8, th)]);
const { whereTo, isHere } = await load("js/missions.js");
const placeM = { area: "Sanctuary", map: "Sanctuary_P", tin: { a: "Southern Shelf", map: "SouthernShelf_P" }, go: { a: "Bay", map: "Bay_P" } };
const where = { active: whereTo(placeM, "active"), ready: whereTo(placeM, "ready"), available: whereTo(placeM, "available"),
  readyNoTin: whereTo({ area: "Sanctuary", map: "Sanctuary_P" }, "ready"), activeNoGo: whereTo({ area: "Sanctuary", map: "Sanctuary_P" }, "active"),
  none: whereTo({}, "active"), here: isHere(whereTo(placeM, "available"), { map: "sanctuary_p" }), notHere: isHere({ map: "Ice_P" }, { map: "Sanctuary_P" }) };
const { rewardFor } = await load("js/missions.js");
const rwM = { rw: { "12": { xp: 900 }, "15": { xp: 1100 } } };
const fallback = { own: rewardFor(rwM, 12), toLocal: rewardFor(rwM, 20, 15), toAny: rewardFor(rwM, 20, 30), none: rewardFor({}, 12, 15) };
const { missionItemWanted } = await load("js/missions.js");
// mission items placed ahead: shown only while their objective is to do (for) / their mission not started (gives)
const itemLog = new Map([
  ["act", { i: "act", st: "Active", obj: [{ c: 1 }, { c: 4 }, { c: 1 }], p: [1, 2, 0], cur: [1] }],
  ["new", { i: "new", st: "NotStarted" }], ["old", { i: "old", st: "Complete" }]]);
const items = [{ k: "for", i: "act", oi: 1 }, { k: "for", i: "act", oi: 2 }, { k: "for", i: "act", oi: 0 }, { k: "for", i: "new", oi: 0 },
  { k: "gives", i: "new" }, { k: "gives", i: "old" }, { k: "for", i: "nowhere", oi: 0 }].map((ms) => missionItemWanted(ms, itemLog));
const { look, withAlpha } = await load("js/look.js");
const { settings: lookSettings } = await load("js/settings.js");
const lookDefault = look();
lookSettings.view.bgOpacity = 140; lookSettings.view.mapOpacity = -5; lookSettings.view.uiScale = 900; lookSettings.view.panelOpacity = 3; lookSettings.view.markerScale = 1; // out of range: clamped
const lookClamped = look();
lookSettings.view.bgOpacity = 100; lookSettings.view.mapOpacity = 100; lookSettings.view.uiScale = 100; lookSettings.view.panelOpacity = 90; lookSettings.view.markerScale = 100;
const lookOut = { lookDefault, lookClamped, rgba: withAlpha("#0b1116", 0.4) };
const { objectCategory } = await load("js/model.js");
const { shownHealth, shownMaxHealth } = await load("js/model.js");
// health as the game's HUD shows it: rounded down (107.89: 107), the page's max the same (full reads full: "107 / 107")
const healthShown = [shownHealth(107.8), shownMaxHealth(107.8907), shownHealth(100), shownMaxHealth(100)].join(",");
// a label's Pre-Sequel twin (i18n.js setVariant: the level message's "game"): "group.relic.tps" - its Oz kits are BL2's
// relics' class; a label without one unchanged; no game: BL2's
const { setVariant: setGameVariant, t: tVariant } = await load("js/i18n.js");
setGameVariant("tps");
const variantWords = [tVariant("group.relic"), tVariant("currency.eridium", { n: 3 }), tVariant("group.weapon")];
setGameVariant("");
variantWords.push(tVariant("group.relic"));
// a mission's current step in its own order (m.cur: the set's ObjectiveDefinitions - the Pre-Sequel's "Marooned": Throw
// breaker, Power up jump pad, Kill Deadlift, Pick up digistruct key), in the slots it takes; the others where they are
const { objectiveStates: stepStates } = await load("js/missions.js");
const stepOrder = stepStates({ obj: [{ n: "Kill Deadlift", c: 1 }, { n: "Pick up digistruct key", c: 1 }, { n: "Use jump pad", c: 1 },
  { n: "Throw breaker", c: 1 }, { n: "Power up jump pad", c: 1 }], p: [0, 0, 1, 0, 0], cur: [3, 4, 0, 1] })
  .map((s) => `${s.o.n}:${s.state}`).join(",");
const vaultCat = objectCategory({ d: "IO_VaultRoy", n: "Vault Roy", c: "WillowInteractiveObject" })
  + "," + objectCategory({ d: "CatchARideTerminal", n: "Catch-A-Ride", c: "WillowVehicleSpawnStationTerminal" })
  + "," + objectCategory({ d: "InteractiveObj_HyperionAmmo", n: "Ammo", c: "WillowInteractiveObject", lootable: 1, lists: ["AmmoCrateLoot_Hyp"] })
  + "," + objectCategory({ d: "IO_AirDome_Bubble_On", n: "AirDome Bubble On", raw: 1, c: "WillowInteractiveObject", dome: [1687, 0] })
  + "," + objectCategory({ d: "IO_AirDome_Generator_On", n: "Air Dome Generator", c: "WillowInteractiveObject", dg: 1 })
  + "," + objectCategory({ d: "IO_OxygenCracks", n: "Oxygen Source", c: "WillowInteractiveObject", o2: 1 })
  + "," + objectCategory({ d: "IO_Geysers_Vertical", n: "Geysers Vertical", raw: 1, c: "OzPlayerJumpPad" })
  + "," + objectCategory({ d: "DrZed", n: "DrZed", raw: 1, c: "WillowInteractiveNPC" }) // (BL1's NPCs: objects)
  + "," + objectCategory({ d: "InteractiveObj_DahlEpic_LastRequests", c: "WillowInteractiveObject", lootable: 1, slots: 15,
    loot: ["Pool_EpicChest_Weapons_LongGuns", "Pool_Chest_Ammo"] }) // (no loot list: its pools say a big chest)
  + "," + objectCategory({ d: "InteractiveObject_SpeedMoxxtail", n: "Speed Moxxtail", c: "WillowInteractiveObject", buff: 1 })
  + "," + objectCategory({ d: "SlotMachine", n: "Slot Machine", c: "WillowInteractiveObject", cost: 85 })
  + "," + objectCategory({ d: "InteractiveObj_TreasureChest_Golden", c: "WillowInteractiveObject", cost: 1, lootable: 1,
    lists: ["EpicChestGoldenLoot"] }); // (costs a golden key: still a chest)
// The map's click / hover pick (input.js hitAt): what the pointer is ON wins over a nearer-layer marker merely close by
// (a chest under the pointer, a pickup 10 px off: the chest); both under it: the layer (an item on its chest: the item);
// on none: the nearest centre
const { S: hitState } = await load("js/state.js");
const { hitAt } = await load("js/input.js");
const hitChest = { sx: 100, sy: 100, r: 6, kind: "chest", item: { i: "chest" } };
const hitLoot = { sx: 110, sy: 100, r: 5, kind: "loot", item: { i: "loot" } };
const hitOnLoot = { sx: 101, sy: 101, r: 5, kind: "loot", item: { i: "onChest" } };
hitState.hits = [hitChest, hitLoot];
const hitPicks = [hitAt(100, 100, 14)?.item.i];
hitState.hits = [hitChest, hitOnLoot];
hitPicks.push(hitAt(100, 100, 14)?.item.i);
hitState.hits = [hitChest, hitLoot];
hitPicks.push(hitAt(108, 112, 14)?.item.i); // (on neither: the loot's centre is the nearest)
hitState.hits = [];
const { skillStatText } = await load("js/ui/skills.js");
const shotCostOut = skillStatText({ d: "", v: 1, cur: 2, np: 1, pre: "Consumes [skill]", suf: "ammo[-skill] per shot." });
const statsOut = [
  skillStatText({ d: "Gun Damage: $NUMBER$", v: 0.06, pct: 1, fl: 1, fp: 1 }),
  skillStatText({ d: "Reload Speed: $NUMBER$", v: -0.08, pct: 1, pos: 1 }),
  skillStatText({ d: "Shield Recharge Delay: $NUMBER$", v: -0.12, pct: 1, fl: 1, fp: 1 }),
  skillStatText({ d: "Regenerates $NUMBER$ of your Max Health / sec.", v: 0.004, pct: 1, pf: 1, fl: 1, fp: 1, np: 1, pos: 1 }),
  skillStatText({ d: "Turret Duration: $NUMBER$ seconds", v: 2, pos: 1 }),
  skillStatText({ d: "Cooldown: $NUMBER$ seconds", v: 42, np: 1 }),
];
const { bonusLines } = await load("js/ui/skills.js");
const gun = (v) => ({ d: "Gun Damage: $NUMBER$", v, pct: 1, fl: 1, fp: 1 });
const bonusOut = bonusLines([
  { tiers: [{ cells: [{ g: 2, m: 5, fx: [gun(0.12)] }, { g: 0, m: 5, fxn: [gun(0.05)] }] }] },
  { skills: [{ g: 1, m: 5, fx: [gun(0.07), { d: "Melee Damage: $NUMBER$", v: 0.06, pct: 1, fl: 1, fp: 1 }] }] },
]);
// A state's compact pawn rows (data.js movingOf): full health / shield left out - the max from the description
const { movingOf } = await load("js/data.js");
const rowsOut = [movingOf(["a", 1, 2, 3], { m: 100, sm: 50 }), movingOf(["b", 1, 2, 3, 40.5, { s: 10, r: 5 }], { m: 100, sm: 50 }),
  movingOf(["c", 1, 2, 3, { rs: 2 }], {})];
// The record channels (data.js keyed): the Hub's own messages, merged as the page does - each scenario's end result
// (null: a message out of step, refused)
const { keyed } = await load("js/data.js");
const deltaOut = JSON.parse(fs.readFileSync(recordsFile, "utf-8")).map((sc, n) => {
  let whole = null;
  for (const msg of sc.messages) whole = keyed(`scenario${n}`, sc.list, msg);
  return whole;
});
// An open loot panel (data.js refreshLootDetail, on the items / pickups updates): drawn again when its pickup's item
// card arrives, not when nothing changed (it once read the pickup as a hit's wrapper - found.item - and threw)
const { refreshLootDetail } = await load("js/data.js");
let lootDetailRenders = 0;
const countLootRender = () => { lootDetailRenders += 1; };
Object.assign(S, { detail: { kind: "loot", id: "lootP" }, pickups: [{ i: "lootP", it: "lootCard" }], groundItems: new Map() });
refreshLootDetail(countLootRender); // shown, its card not read yet: drawn
refreshLootDetail(countLootRender); // nothing changed: not again
S.groundItems = new Map([["lootCard", { i: "lootCard" }]]);
refreshLootDetail(countLootRender); // its card came: again
Object.assign(S, { detail: null, pickups: [], groundItems: new Map() });
const missionsOut = { deltaOut, lootDetailRenders, rowsOut, shotCostOut, bonusOut, statsOut, lookOut, vaultCat, healthShown, variantWords, stepOrder, hitPicks, items, fallback, where, tooHigh, finish, difficulty, best, search, infoHtml, areas, gameText, story: flat(tree.story), other: flat(tree.other), counts: missionCounts(log),
  objectives: objectiveStates(log[1]).map((s) => s.state) };
console.log(JSON.stringify({ sha: crypto.createHash("sha256").update(rgba).digest("hex"), err, back, right, raw, modules, missions: missionsOut,
  migrated, checked: { enemy: checked.layers.enemy, view: checked.view, openLayers: checked.ui.openLayers, drawer: checked.ui.drawer, badDrawer }, i18nKeys, unknownSettings, lootLayers, gameRarity, gameOut, freeRects }));
"""


def _dxt5_rgba(w: int, h: int, data: bytes) -> bytes:
    """Reference DXT5 decoder (independent of the page's), to compare checksums."""
    import struct  # noqa: PLC0415

    def c565(c: int) -> tuple[int, int, int]:
        return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31

    px = bytearray(w * h * 4)
    bw = (w + 3) // 4
    for bi in range(bw * ((h + 3) // 4)):
        blk = data[bi * 16 : bi * 16 + 16]
        bx, by = bi % bw * 4, bi // bw * 4
        a0, a1 = blk[0], blk[1]
        if a0 > a1:
            al = [a0, a1] + [((6 - k) * a0 + (k + 1) * a1) // 7 for k in range(6)]
        else:
            al = [a0, a1] + [((4 - k) * a0 + (k + 1) * a1) // 5 for k in range(4)] + [0, 255]
        abits = int.from_bytes(blk[2:8], "little")
        c0, c1, cb = struct.unpack_from("<HHI", blk, 8)
        r0, r1 = c565(c0), c565(c1)
        mix = [tuple((2 * a + b) // 3 for a, b in zip(r0, r1)), tuple((a + 2 * b) // 3 for a, b in zip(r0, r1))]
        cols = [r0, r1, *mix]
        for k in range(16):
            x, y = bx + k % 4, by + k // 4
            if x < w and y < h:
                o = (y * w + x) * 4
                px[o : o + 3] = bytes(cols[(cb >> (2 * k)) & 3])
                px[o + 3] = al[(abits >> (3 * k)) & 7]
    return bytes(px)


def bl1_map_alpha(img) -> float:  # noqa: ANN001
    """The share of a rendered BGRA map image that's (mostly) opaque."""
    alpha = img.data[3::4]
    return sum(1 for a in alpha if a > 128) / len(alpha)


def check_helios_tracker() -> None:  # noqa: PLR0915
    import enum  # noqa: PLC0415
    import hashlib  # noqa: PLC0415
    import http.client  # noqa: PLC0415
    import json  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    import time  # noqa: PLC0415

    import os  # noqa: PLC0415

    os.environ["HELIOS_TRACKER_LOG"] = tempfile.gettempdir() + "/helios_tracker_offline_check.log"
    import helios_tracker as m  # noqa: PLC0415
    from helios_tracker import collector as col  # noqa: PLC0415
    from helios_tracker.server import Hub, TrackerServer  # noqa: PLC0415
    from helios_tracker.tacmap import load_tactical_map  # noqa: PLC0415
    from helios_tracker.util import clear_fields, field, pickup_kind  # noqa: PLC0415
    from helios_tracker.util import reader as field_reader  # noqa: PLC0415 - ("reader": a SkillReader below)

    # Every @hook of the mod is in build_mod's hooks list (an explicit list: one left out never runs -
    # the cutscene video hook once was)
    defined = {n for n, f in vars(m).items() if getattr(f, "_helios_hook", None)}
    listed = {f.__name__ for f in m.mod.hooks}
    assert defined == listed, ("hooks defined but not in build_mod(hooks=...)", sorted(defined - listed), sorted(listed - defined))
    # "assets": what the server can serve from the game's files - the page asks for card icons only once "cards" is 1
    # (the files indexed + every kind's keys known: before, a 404 a map marker gave up on)
    from helios_tracker import gamecards as assets_cards  # noqa: PLC0415
    assets_saved = (dict(assets_cards._keys), assets_cards._index)
    assets_cards._index = None
    for assets_kind in assets_cards.KINDS:
        assets_cards.set_keys(assets_kind, set())
    assert json.loads(m._hub.latest("assets"))["cards"] == 0, m._hub.latest("assets")
    assets_cards.set_index({})
    for assets_kind in assets_cards.KINDS:
        assets_cards.set_keys(assets_kind, {"key"})
    assert json.loads(m._hub.latest("assets"))["cards"] == 1, ("indexed, keys known: sent", m._hub.latest("assets"))
    from helios_tracker import gameicons as assets_icons  # noqa: PLC0415
    assets_textures = assets_icons._textures
    assets_icons.set_textures({})
    m._publish_assets()
    assert json.loads(m._hub.latest("assets"))["textures"] == 1, ("the textures indexed: sent", m._hub.latest("assets"))
    assets_icons._textures = assets_textures
    assets_cards._keys.update(assets_saved[0])
    assets_cards._index = assets_saved[1]

    # field(): the property looked up once per class, then read with _get_field (tools/probes/probe_perf.txt)
    class FakeClass:
        finds = 0

        def _get_address(self) -> int:
            return 0x1234

        def _find(self, name: str) -> str:
            if name == "Missing":
                raise ValueError("no such property")
            FakeClass.finds += 1
            return "prop:" + name

    class FakeObject:
        Class = FakeClass()

        def _get_field(self, prop: str) -> str:
            return "value of " + prop

    obj = FakeObject()
    assert [field(obj, "HealthVar") for _ in range(3)] == ["value of prop:HealthVar"] * 3 and FakeClass.finds == 1, FakeClass.finds
    try:
        field(obj, "Missing")
        raise AssertionError("a missing property must raise")
    except ValueError:
        pass
    assert field(types.SimpleNamespace(x=5), "x") == 5, "plain objects: getattr"
    clear_fields()  # a level change
    field(obj, "HealthVar")
    assert FakeClass.finds == 2, "looked up again after clear_fields()"
    read_obj = field_reader(obj)  # field() bound to one object: the same cache
    assert read_obj("HealthVar") == "value of prop:HealthVar" and read_obj("ShieldVar") == "value of prop:ShieldVar", "reader()"
    assert FakeClass.finds == 3, ("reader(): one lookup per new property", FakeClass.finds)
    assert field_reader(types.SimpleNamespace(x=6))("x") == 6, "reader(), plain objects: getattr"


    # Pickup kinds: the definition's inventory card (Presentation), resolved once per definition
    class FakeDef:
        def __init__(self, card: str) -> None:
            self.Presentation = types.SimpleNamespace(Name=card) if card else None
            self.reads = 0

        def _get_address(self) -> int:
            return id(self)

    def usable(item_def, cls: str = "WillowUsableItem"):  # noqa: ANN001, ANN202
        return types.SimpleNamespace(Class=types.SimpleNamespace(Name=cls), DefinitionData=types.SimpleNamespace(ItemDefinition=item_def))

    cards = {"WeaponAmmo_SMG": "ammo", "GrenadeAmmo": "ammo", "Credits": "cash", "Health": "health", "Something": "", "": ""}
    defs = {card: FakeDef(card) for card in cards}
    got = {card: pickup_kind(usable(d)) for card, d in defs.items()}
    assert got == cards, got
    defs["Credits"].Presentation = None  # cached: the definition isn't read again
    assert pickup_kind(usable(defs["Credits"])) == "cash"
    assert pickup_kind(usable(FakeDef("Credits"), "WillowWeapon")) == "", "gear classified as a pickup kind"
    assert pickup_kind(None) == ""
    # every currency shares the "Credits" presentation: FormOfCurrency tells them apart (probe_eridium)
    for currency, kind in (("CURRENCY_Eridium", "eridium"), ("CURRENCY_Credits", "cash"), ("CURRENCY_SeraphCrystals", "")):
        coin = FakeDef("Credits")
        coin.FormOfCurrency = types.SimpleNamespace(name=currency)
        assert pickup_kind(usable(coin)) == kind, (currency, pickup_kind(usable(coin)))

    print("helios_tracker:")
    print(f"  options: {[getattr(o, 'identifier', o) for o in m.mod.options]}")
    assert col.pretty_map_name("SouthernShelf_P") == "Southern Shelf", col.pretty_map_name("SouthernShelf_P")
    # A mission item (tools/probes/probe_pickups.txt, an ECHO log): named by its definition, not the class's
    # generic "Mission Item"; the mission it gives (MissionDirective) / its objective's (AssociatedMissionObjective)
    echo_mission = types.SimpleNamespace(MissionName="No Hard Feelings", _path_name=lambda: "gd_z1_nohardfeelings.M_NoHardFeelings")
    echo = types.SimpleNamespace(GetShortHumanReadableName=lambda: "Mission Item", MissionItemString="Mission Item",
                                 DefinitionData=types.SimpleNamespace(ItemDefinition=types.SimpleNamespace(
                                     ItemName="Data Log", MissionDirective=echo_mission, AssociatedMissionObjective=None)))
    assert col.item_name(echo) == "Data Log", col.item_name(echo)
    echo.Class = types.SimpleNamespace(Name="WillowMissionItem")
    assert col.pickup_kind(echo) == "mission", "a mission item: the Mission items layer"
    assert col.pickup_mission(echo) == {"i": "gd_z1_nohardfeelings.M_NoHardFeelings", "n": "No Hard Feelings", "k": "gives"}
    part = types.SimpleNamespace(ProgressMessage="Collect parts", Outer=echo_mission)
    echo.DefinitionData.ItemDefinition.MissionDirective, echo.DefinitionData.ItemDefinition.AssociatedMissionObjective = None, part
    assert col.pickup_mission(echo) == {"i": "gd_z1_nohardfeelings.M_NoHardFeelings", "n": "No Hard Feelings", "k": "for", "o": "Collect parts"}
    # A vehicle's boost (tools/probes/probe_vehicle.txt: its AfterburnerPool): [left, max], MaxValue else BaseMaxValue
    boost = col.Collector._boost
    assert boost(types.SimpleNamespace(AfterburnerPool=types.SimpleNamespace(Data=types.SimpleNamespace(CurrentValue=30.0, MaxValue=100.0))), 0.0) == [30.0, 100.0]
    assert boost(types.SimpleNamespace(AfterburnerPool=types.SimpleNamespace(Data=types.SimpleNamespace(CurrentValue=5.0, MaxValue=0.0, BaseMaxValue=50.0))), 0.0) == [5.0, 50.0]
    assert boost(types.SimpleNamespace(), 0.0) is None, "no boost pool"
    # refilling like a shield (tools/probes/probe_boost.txt): the delay's rest, then (max - left) / rate
    def refill(engaged=False, cur=40.0):
        pool = types.SimpleNamespace(CurrentValue=cur, MaxValue=100.0, OnIdleRegenerationRate=20.0,
                                     OnIdleRegenerationDelay=5.0, PoolIdleDelayStartTime=100.0)
        return boost(types.SimpleNamespace(AfterburnerPool=types.SimpleNamespace(Data=pool), AfterburnerEngaged=engaged), 102.0)
    assert refill() == [40.0, 100.0, 6.0], ("waiting: 3 s of delay + 60 / 20", refill())
    assert boost(types.SimpleNamespace(AfterburnerPool=types.SimpleNamespace(Data=types.SimpleNamespace(
        CurrentValue=40.0, MaxValue=100.0, OnIdleRegenerationRate=20.0, OnIdleRegenerationDelay=5.0,
        PoolIdleDelayStartTime=100.0)), AfterburnerEngaged=False), 110.0) == [40.0, 100.0, 3.0], "refilling: the rate only"
    assert refill(engaged=True) == [40.0, 100.0], "boosting: no timer"
    assert refill(cur=100.0) == [100.0, 100.0], "full: no timer"
    # A pawn's name: its balance's PlayThroughs[].DisplayName - the current playthrough's (0-based on the game
    # replication info - not the controller: it only has a function - 1-based in the entries), else the first named one;
    # nothing: ""
    brute = types.SimpleNamespace(BalanceDefinitionState=types.SimpleNamespace(BalanceDefinition=types.SimpleNamespace(PlayThroughs=[
        types.SimpleNamespace(PlayThrough=1, DisplayName="Bruiser"), types.SimpleNamespace(PlayThrough=2, DisplayName="Badass Bruiser")])))
    saved_engine = col.ENGINE
    col.ENGINE = types.SimpleNamespace(GetCurrentWorldInfo=lambda: types.SimpleNamespace(GRI=types.SimpleNamespace(CurrentPlaythrough=1)))
    tvhm = col.pawn_display_name(brute)
    col.ENGINE = types.SimpleNamespace(GetCurrentWorldInfo=lambda: None)
    unknown_pt = col.pawn_display_name(brute)
    col.ENGINE = saved_engine
    assert (tvhm, unknown_pt, col.pawn_display_name(types.SimpleNamespace())) == ("Badass Bruiser", "Bruiser", ""), (tvhm, unknown_pt)
    # The level's name as the game shows it (tools/probes/probe_area.txt): a list per game / DLC, each knowing its maps
    lists = [types.SimpleNamespace(Name="Default__LevelDependencyList", GetFriendlyLevelNameFromMapName=lambda m: "wrong"),
             types.SimpleNamespace(Name="LevelList", GetFriendlyLevelNameFromMapName=lambda m: {"Ice_P": "Three Horns - Divide"}.get(m, "")),
             types.SimpleNamespace(Name="AlliumTG_LevelList", GetFriendlyLevelNameFromMapName=lambda m: {"Hunger_P": "Gluttony Gulch"}.get(m, ""))]
    saved_find_all = col.unrealsdk.find_all
    col.unrealsdk.find_all = lambda cls, exact=True: lists if cls == "LevelDependencyList" else []
    names = [col.level_name(m) for m in ("Ice_P", "Hunger_P", "Nowhere_P")]
    col.unrealsdk.find_all = saved_find_all
    col._level_names.clear()
    assert names == ["Three Horns - Divide", "Gluttony Gulch", ""], names
    if GAME_COOKED is None or not GAME_COOKED.is_dir():
        print("  game files not found (project.json's game): skipping the map / server checks")
        return
    # Map images straight from the game's packages
    from helios_tracker.tacmap import load_fog  # noqa: PLC0415
    for level_name, size in {"Sanctuary_P": (468, 512), "SouthernShelf_P": (876, 1024)}.items():
        t = time.perf_counter()
        (img,) = load_tactical_map(GAME_COOKED / f"{level_name}.upk", f"UI_TacticalMap_{level_name[:-2]}.{level_name}")
        assert (img.format, img.width, img.height) == ("PF_DXT5", *size), img
        # its fog of war (tools/probes/dump_tacmap_movie.txt): the shared blob, placed once per discovery area
        fog = load_fog(GAME_COOKED / f"{level_name}.upk", f"UI_TacticalMap_{level_name[:-2]}.{level_name}")
        assert fog is not None and (fog.blob.format, fog.blob.width, fog.blob.bounds) == ("PF_A8R8G8B8", 64, (-128.0, 128.0, -128.0, 128.0)), fog
        want = {"Sanctuary_P": ["SANCTUARY_PWDA_1", "SANCTUARY_PWDA_0"],
                "SouthernShelf_P": ["SOUTHERNSHELF_PWDA_1", "SOUTHERNSHELF_PWDA_0", "SOUTHERNSHELF_PWDA_2", "SOUTHERNSHELF_PWDA_5", "SOUTHERNSHELF_PWDA_3"]}
        assert [n for n, _ in fog.pieces] == want[level_name], fog.pieces
        if level_name == "SouthernShelf_P":
            assert fog.pieces[1][1] == (0.640625, 0.0, 0.0, 1.04791259765625, 110.0, 143.0), fog.pieces[1]
        print(f"  {level_name}: {img.name} {img.width}x{img.height} {img.format}, bounds {img.bounds}"
              f" ({time.perf_counter() - t:.2f} s)")
    # The game's UI fonts (tools/probes/find_fonts.txt: Startup.upk's UI_FontsEn.FontsEn, Scaleform compacted fonts)
    # rebuilt as TrueType: every table there, the glyphs and kerning kept
    import io  # noqa: PLC0415
    import struct  # noqa: PLC0415

    # The game files' scan (gamescan.py): one pass over the packages (fonts, card icons, skill icons) in gamework's
    # subinterpreter, its cache (a temp dir here), then a second session's: from the cache, nothing scanned
    import tempfile  # noqa: PLC0415

    from helios_tracker import gamefonts, gamescan, gamework  # noqa: PLC0415
    scan_tmp = tempfile.TemporaryDirectory()
    gamescan.CACHE = Path(scan_tmp.name) / "scan.json"
    gamework.ASSETS = Path(scan_tmp.name) / "assets"
    t = time.perf_counter()
    gamescan.run(GAME_COOKED)
    t_scan = time.perf_counter() - t
    assert gamescan.ready() and gamescan.CACHE.is_file()
    assert gamework.mode() == "subinterpreter", ("the scan beside the game's Python, not in it", gamework.mode())
    scanned = (dict(gamefonts.FONTS.catalogue), gamescan.packages(GAME_COOKED))
    gamescan._done.clear()
    t = time.perf_counter()
    gamescan.run(GAME_COOKED)
    t_cached = time.perf_counter() - t
    assert gamefonts.FONTS.catalogue == scanned[0] and t_cached < 1.0, ("the cache gives the same index, fast", t_cached)
    print(f"  game files scan: {len(scanned[1])} packages in {t_scan:.2f} s ({gamework.mode()}), from its cache {t_cached:.2f} s")
    t = time.perf_counter()
    font_lib = gamefonts.FONTS  # (the engine config's packages: no movie named)
    names = {s: entry[0] for s, entry in font_lib.catalogue.items()}
    assert {"willowbody": "WillowBody", "compacta-bd-bt": "Compacta Bd BT", "chintzy-cpu-brk": "Chintzy CPU BRK"}.items() <= names.items(), names
    assert font_lib.catalogue["willowbody"][1] == 293, ("the fullest WillowBody: the font library's", font_lib.catalogue["willowbody"])
    game_fonts = {s: (names[s], font_lib.get(s)) for s in ("willowbody", "compacta-bd-bt", "chintzy-cpu-brk")}  # (converted on demand)
    for slug, (_name, ttf) in game_fonts.items():
        n_tables = struct.unpack_from(">H", ttf, 4)[0]
        tags = {ttf[12 + 16 * i : 16 + 16 * i].decode() for i in range(n_tables)}
        assert ttf[:4] == b"\0\1\0\0" and {"head", "hhea", "maxp", "OS/2", "hmtx", "cmap", "loca", "glyf", "name", "post"} <= tags, (slug, tags)
    try:
        from fontTools.ttLib import TTFont  # noqa: PLC0415 - a dev check when it's installed
        body = TTFont(io.BytesIO(game_fonts["willowbody"][1]))
        glyph_a = body["glyf"][body.getBestCmap()[ord("A")]]
        assert body["maxp"].numGlyphs == 294 and glyph_a.numberOfContours == 2 and len(body["kern"].kernTables[0].kernTable) == 15, "WillowBody"
    except ImportError:
        pass
    print(f"  game fonts: {', '.join(f'{n} ({len(b) // 1024} KB)' for n, b in game_fonts.values())} ({time.perf_counter() - t:.2f} s)")
    # The skill icons (gameicons.py): the class packages' textures, as PNGs - Axton's, a DLC class's (Gaige)
    from helios_tracker import gameicons  # noqa: PLC0415
    t = time.perf_counter()  # (its index: the scan's)
    able = gameicons.icon_png("SharedSkillIcons_Soldier.SkillIcon-Able")
    assert able and able[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", able[16:24]) == (64, 64), "Able's icon"
    banner = gameicons.icon_png("SharedSkillIcons_Soldier.AAIcon-SoldierAA")
    assert banner and struct.unpack(">II", banner[16:24]) == (256, 128), "the action skill's banner"
    assert gameicons.icon_png("UI_Tulip_SharedSkillIcons_Mech.AAIcon-MechroAA"), "a texture named <movie>_I1 (Gaige's banner)"
    assert gameicons.icon_png("SharedSkillIcons_Soldier.SkillIcon-Willing"), "an icon only in Startup.upk (Willing)"
    icons = list(gameicons._index)
    assert len(icons) > 150 and any(k.startswith("ui_tulip_") for k in icons) and any(k.startswith("ui_lilac_") for k in icons), \
        ("every class's icons indexed, the DLC classes' (Gaige, Krieg) too", len(icons))
    assert gameicons.icon_png("SharedSkillIcons_Soldier.Nope") is None and gameicons.icon_png("../server.py") is None
    print(f"  skill icons: {len(icons)} indexed, Able {len(able)} bytes ({time.perf_counter() - t:.2f} s)")
    # A skill's icon path (skills.skill_icon): its SkillIcon movie's - or the Pre-Sequel's SkillIconTextureName in that
    # movie's package (its DLC classes' skills share one movie: Aurelia's "SkillIcon-Aurelia", 37 skills)
    from helios_tracker.skills import skill_icon  # noqa: PLC0415
    def icon_movie(path: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(_path_name=lambda: path)
    aurelia_icon = skill_icon(types.SimpleNamespace(SkillIcon=icon_movie("SharedSkillIcons_Cro_Aurelia.SkillIcon-Aurelia"),
                                                    SkillIconTextureName="SkillIcon-Avalanche"))
    assert aurelia_icon == "SharedSkillIcons_Cro_Aurelia.SkillIcon-Avalanche", aurelia_icon
    assert skill_icon(types.SimpleNamespace(SkillIcon=icon_movie("SharedSkillIcons_Soldier.SkillIcon-Able"))) == \
        "SharedSkillIcons_Soldier.SkillIcon-Able", "BL2: no SkillIconTextureName, the movie's path"
    assert skill_icon(types.SimpleNamespace(SkillIcon=icon_movie("SharedSkillIcons_Soldier.SkillIcon-Able"),
                                            SkillIconTextureName="None")) == "SharedSkillIcons_Soldier.SkillIcon-Able"
    assert skill_icon(types.SimpleNamespace(SkillIcon=None, SkillIconTextureName="SkillIcon-Avalanche")) == "", "no movie: none"
    gameicons._pngs.clear()
    t = time.perf_counter()
    assert gameicons.icon_png("SharedSkillIcons_Soldier.SkillIcon-Able") == able and time.perf_counter() - t < 0.2, \
        "an icon decoded once: from the disk cache next time"
    # A pickup's own icon (its PickupFlagIcon: an always-loaded texture, served by path): inline, and one whose pixels
    # are in a texture file cache (.tfc: the eridium's)
    t = time.perf_counter()
    flag_cash = gameicons.texture_by_path("fx_shared_items.Textures.ItemCards.Credits")
    flag_eridium = gameicons.texture_by_path("fx_shared_items.Textures.ItemCards.Eridium_Currency")
    assert flag_cash and struct.unpack(">II", flag_cash[16:24]) == (128, 128), "the cash pickup's icon"
    assert flag_eridium and struct.unpack(">II", flag_eridium[16:24]) == (128, 128), "the eridium's: its pixels in Textures.tfc"
    assert gameicons.texture_by_path("fx_shared_items.Nope") is None and gameicons.texture_by_path("../server.py") is None
    print(f"  pickup icons: {len(gameicons._textures)} textures indexed, cash / eridium (.tfc) ({time.perf_counter() - t:.2f} s)")
    # The item card icons (gamecards.py): the engine config's packages, the sprites labelled with the game's keys
    from helios_tracker import gamecards  # noqa: PLC0415
    card_packages = [p.name for p in gamecards.engine_packages(GAME_COOKED)]
    assert "WillowGame.upk" in card_packages and card_packages[-1] == "Startup.upk", card_packages
    t = time.perf_counter()
    assert gamecards.card_png("manufacturer", "maliwan") is None, "no keys yet: none (the collector gives them)"
    gamecards.set_keys("manufacturer", {"jakobs", "anshin", "atlas", "dahl", "gearbox", "hyperion", "maliwan", "tediore", "torgue", "vladof"})
    gamecards.set_keys("type", {"pistol", "shotgun", "smg", "ar", "sniper", "rocket"})  # (the six weapon types' frames)
    gamecards.set_keys("element", {"None", "Incendiary", "Shock", "Corrosive", "Explosive", "Amp"})  # (the damage types')
    maliwan, pistol = gamecards.card_png("manufacturer", "maliwan"), gamecards.card_png("type", "pistol")
    card_layers = {k: [(a.group, a.depth, a.size) for a in gamecards._choose(*k)]
                   for k in (("manufacturer", "maliwan"), ("type", "pistol"), ("element", "shock"), ("type", "shotgun"))}
    assert len(card_layers["manufacturer", "maliwan"]) == 2 and len(card_layers["type", "pistol"]) == 2, \
        ("two layers: the black outline under, the fill over", card_layers)
    assert maliwan and struct.unpack(">II", maliwan[16:24]) == (126, 29), "Maliwan's logo: its outline's size"
    assert pistol and struct.unpack(">II", pistol[16:24]) == (49, 33), "the item card's pistol (not the ammo's, 30 x 41)"
    shock = gamecards.card_png("element", "shock")
    assert shock and struct.unpack(">II", shock[16:24]) == (42, 42), "the item card's shock icon"
    card_shotgun = gamecards._choose("type", "shotgun")
    assert card_shotgun[0].group == gamecards._choose("type", "pistol")[0].group, "the shotgun from the card's type lists too"
    assert [bool(a.shape) for a in card_shotgun] == [True, False], \
        ("its outline a vector shape (drawn: _shape_rgba), its fill an atlas bitmap", card_shotgun)
    card_shotgun_png = gamecards.card_png("type", "shotgun")
    assert card_shotgun_png and struct.unpack(">II", card_shotgun_png[16:24]) == (81, 28), "the shotgun: its outline's size"
    assert gamecards.card_png("manufacturer", "../x") is None and gamecards.card_png("nope", "maliwan") is None
    assert all(a.rect[2] <= a.declared[0] and a.rect[3] <= a.declared[1] for arts in gamecards._index.values() for a in arts), \
        "every art inside its atlas (a plain image's id - the 8 x 4 scanlines, 1 - never taken for atlas 1)"
    print(f"  card icons: {len(gamecards._index)} labels from {len(card_packages)} packages ({time.perf_counter() - t:.2f} s)")
    gamework.stop()
    scan_tmp.cleanup()
    # A cutscene video's length from its Bink header (a DLC's: Captain Scarlett's intro, 65.0 s)
    real_game_dir = col.game_dir
    col.game_dir = lambda: GAME_COOKED.parent.parent
    if (GAME_COOKED.parent.parent / "DLC" / "Orchid").is_dir():
        assert col.movie_length("Orchid_Intro") == 65.0, col.movie_length("Orchid_Intro")
    # (the game names some with their extension: the Marcus intro came as 'TC_Marcus.bik' - its length was lost)
    if (GAME_COOKED.parent / "Movies" / "TC_Marcus.bik").is_file():
        assert col.movie_length("TC_Marcus.bik") == col.movie_length("TC_Marcus") == 19.3, col.movie_length("TC_Marcus.bik")
    assert col.movie_length("NoSuchMovie") is None
    # BL1 (project.json's bl1, the original game): its Movies found from the game folder - no CookedPCConsole there
    if (bl1_game := project.path("bl1")) is not None and (bl1_game / "WillowGame" / "Movies" / "VoG_Transition_Movie.bik").is_file():
        col.game_dir = lambda: bl1_game
        assert col.movie_length("VoG_Transition_Movie") == 70.2, col.movie_length("VoG_Transition_Movie")
    col.game_dir = real_game_dir
    # Vector shapes -> images (swfshape.py, BL1's map): a 10 x 10 square from (5, 5) in a 20 x 20 image - inside opaque,
    # outside clear, a border at half a pixel half covered
    from helios_tracker import swfshape  # noqa: PLC0415
    square_cover = swfshape._coverage([(5, 5, 5, 15), (15, 5, 15, 15)], 20, 20)
    assert square_cover[10 * 20 + 10] == 255 and square_cover[2 * 20 + 2] == 0 and square_cover[10 * 20 + 4] == 0, "a square's inside / outside"
    half_cover = swfshape._coverage([(5.5, 5, 5.5, 15), (15, 5, 15, 15)], 20, 20)
    assert half_cover[10 * 20 + 5] == 128 and half_cover[10 * 20 + 6] == 255, ("half a pixel: half its alpha", half_cover[10 * 20 + 5])
    square_shape = swfshape.Shape((5.0, 15.0, 5.0, 15.0), [(0, (41, 77, 93, 255))], [],
                                  [(0, 1, 0, [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0), (5.0, 5.0)])])
    sq_w, sq_h, sq_bgra, sq_bounds = swfshape.render([((1.0, 0.0, 0.0, 1.0, 0.0, 0.0), square_shape)], 2.0)
    assert (sq_w, sq_h, sq_bounds) == (20, 20, (5.0, 15.0, 5.0, 15.0)) and sq_bgra[(10 * 20 + 10) * 4:(10 * 20 + 10) * 4 + 4] == bytes((93, 77, 41, 255)), \
        ("a filled square, BGRA, 2 px per movie px", sq_w, sq_h, sq_bounds)
    # a line across it from a later style list (BL1's maps keep their lines there): over the fill, the fill beside it
    square_shape.lines.append((1, 1.0, (130, 173, 202, 255)))
    square_shape.edges.append((0, 0, 1, [(5.0, 10.0), (15.0, 10.0)]))
    sq_w, sq_h, sq_bgra, _ = swfshape.render([((1.0, 0.0, 0.0, 1.0, 0.0, 0.0), square_shape)], 2.0)
    assert sq_bgra[(10 * 20 + 10) * 4:(10 * 20 + 10) * 4 + 4] == bytes((202, 173, 130, 255)), "the line over the fill"
    assert sq_bgra[(4 * 20 + 10) * 4:(4 * 20 + 10) * 4 + 4] == bytes((93, 77, 41, 255)), "the fill beside the line"
    # strokes overlap (a quad per piece, a join per point): their union - no even-odd hole where two cross
    cross_cover = swfshape._coverage(swfshape._stroke([(2.0, 10.0), (18.0, 10.0)], 2.0) + swfshape._stroke([(10.0, 2.0), (10.0, 18.0)], 2.0),
                                     20, 20, nonzero=True)
    assert cross_cover[10 * 20 + 10] == 255 and cross_cover[2 * 20 + 2] == 0, "two crossing strokes: their crossing covered"
    # Borderlands 1's files (project.json's bl1, the original game): its packages (version 584: upk_bl1), a level's
    # map anchor, its map rendered from the menu movie's vector frame (bl1map.py)
    bl1_cooked = (project.path("bl1") / "WillowGame" / "CookedPC") if project.path("bl1") else None
    if bl1_cooked is not None and bl1_cooked.is_dir():
        from helios_tracker import bl1map, upk  # noqa: PLC0415
        from helios_tracker.upk_bl1 import Bl1Package  # noqa: PLC0415
        bl1_tex = Bl1Package(bl1_cooked / "Packages" / "Environments" / "Env_TacticalMaps.upk")
        bl1_arena_tex = upk._texture(bl1_tex, bl1_tex.find("Arid.arid-arena", "Texture2D"))
        assert bl1_arena_tex[:3] == ("PF_DXT1", 1024, 1024) and len(bl1_arena_tex[3]) == 1024 * 1024 // 2, bl1_arena_tex[:3]
        bl1_tex.close()
        bl1_level = Bl1Package(bl1_cooked / "Maps" / "Arid" / "W_Arid_Farmstead.umap")  # (raw-stored chunks)
        assert len(bl1_level.exports) == 7722, len(bl1_level.exports)
        bl1_level.close()
        bl1_arena = Bl1Package(bl1_cooked / "Maps" / "Arid" / "Arid_Arena_Coliseum_P.umap")
        bl1_anchor = next(i for i in range(len(bl1_arena.exports)) if bl1_arena.class_name(i) == "LevelLandmarkAnchor")
        bl1_anchor_props, _ = bl1_arena.actor_properties(bl1_arena.export_data(bl1_anchor))
        assert bl1_arena.ref_path(struct.unpack("<i", bl1_anchor_props["Texture"][1])[0]) == "Env_TacticalMaps.Arid.arid-arena"
        assert bl1_anchor_props["MapFrame"][1][4:-1] == b"arid_arena" and struct.unpack("<f", bl1_anchor_props["DrawScale"][1])[0] == 13.0
        bl1_arena.close()
        (bl1_arena_img,) = bl1map.load_map(bl1_cooked, "arid_arena")
        assert (bl1_arena_img.format, bl1_arena_img.width, bl1_arena_img.height) == ("PF_A8R8G8B8", 463, 906), (bl1_arena_img.width, bl1_arena_img.height)
        assert bl1_map_alpha(bl1_arena_img) > 0.3, "the arena's walkable area filled"
        (bl1_bunker_img,) = bl1map.load_map(bl1_cooked, "arid_bunker")  # (gradient fills)
        assert bl1_bunker_img.width == 1504, bl1_bunker_img.width
        assert bl1map.load_map(bl1_cooked, "no_such_frame") == []
        # a DLC area's map: its anchor's DLCMap, a movie of its own (the Underdome lobby's: dlc2_maps.dlcmap_lobby)
        if (bl1_cooked / "DLC" / "DLC2").is_dir():
            (bl1_lobby_img,) = bl1map.load_map(bl1_cooked, "dlcmap1", "dlc2_maps.dlcmap_lobby")
            assert bl1_lobby_img.width > 100 and bl1_map_alpha(bl1_lobby_img) > 0.1, (bl1_lobby_img.width, bl1_lobby_img.height)
            assert bl1map.load_map(bl1_cooked, "dlcmap1", "nope_maps.dlcmap_nope") == []
        # the skill menu's branch names (games.Borderlands1.branch_names): the "skills" clip's character frame's texts
        bl1_hunter = bl1map.clip_texts(bl1_cooked, "skills", "mordecai")
        assert bl1_hunter["tree1.text"] == "$<StringAliasMap:skills_hunter_branch1>" and bl1_hunter["tree3.text"].endswith("hunter_branch3>"), bl1_hunter
        assert bl1map.clip_texts(bl1_cooked, "skills", "roland")["tree2.text"].endswith("soldier_branch2>"), "no 'roland' label: the first frame"
        assert bl1map.clip_texts(bl1_cooked, "nope", "mordecai") == {}
        # its skill icons (games.Borderlands1.skill_icons): the cell's clip in the character's frame, its "on" frame drawn
        # (the drawing only: what its "on" and "off" frames both show - not their state's tile, notched at the
        # bottom right: transparent corners then)
        bl1_icon_w, bl1_icon_h, bl1_icon_px = bl1map.clip_icon(bl1_cooked, "skills", "mordecai", "icon17", "on", "off")
        assert max(bl1_icon_w, bl1_icon_h) == bl1map.ICON_SIZE and any(bl1_icon_px[3::4]), (bl1_icon_w, bl1_icon_h)
        assert bl1_icon_px[3] == 0, "the top left corner: no tile"
        assert bl1map.clip_icon(bl1_cooked, "skills", "mordecai", "icon99", "on", "off") is None
        assert bl1map.clip_icon(bl1_cooked, "skills", "mordecai", "icon17", "nope", "off") is None
        from helios_tracker import gamework as bl1_work  # noqa: PLC0415
        bl1_icon_png = bl1_work.run_job(json.dumps({"do": "menuicon", "cooked": str(bl1_cooked),
                                                    "parts": ["skills", "lilith", "icon24", "on", "off"]}))
        assert bl1_icon_png[:8] == b"\x89PNG\r\n\x1a\n", bl1_icon_png[:16]
        assert bl1map.MENU_ICON.fullmatch("menu.skills.mordecai.icon17.on.off") and not bl1map.MENU_ICON.fullmatch("menu.a.b")
        # its fonts: its font library's DefineFont3 (bl1fonts.py, swffont.py) - WillowBody, WillowHead, Brush Script Std
        from helios_tracker import bl1fonts  # noqa: PLC0415
        bl1_font_list = bl1fonts.catalogue(bl1_cooked)
        assert {"willowbody", "willowhead"} <= set(bl1_font_list) and bl1_font_list["willowbody"][5] == "swffont", bl1_font_list
        bl1_body = bl1fonts.font(*bl1_font_list["willowbody"][2:5])
        bl1_glyph_a = next(g for g in bl1_body.glyphs if g.code == ord("A"))
        assert bl1_body.em == 1024 and len(bl1_body.glyphs) > 200 and len(bl1_glyph_a.contours) == 2 and bl1_glyph_a.advance > 0, (
            bl1_body.em, len(bl1_body.glyphs), bl1_glyph_a)
        bl1_body_ttf = bl1_work.run_job(json.dumps({"do": "swffont", "package": str(bl1_font_list["willowbody"][2]),
                                                    "export": bl1_font_list["willowbody"][3], "n": bl1_font_list["willowbody"][4]}))
        assert bl1_body_ttf[:4] == b"\x00\x01\x00\x00" and b"glyf" in bl1_body_ttf[:400], bl1_body_ttf[:16]
        # its item card icons (games.Borderlands1.card_icon_png): the card movie's sprite holding a kind's keys - the
        # manufacturers' logos; the type's: the menus' item icon clip ("inicon": weapon types and items' ZippyFrame)
        bl1_brand_keys = ["anshin", "atlas", "corazza", "dahl", "eridan", "gearbox", "hyperion", "jakobs", "maliwan",
                          "pangolin", "s_and_s", "tediore", "torgue", "vladof"]
        bl1_logo_w, bl1_logo_h, bl1_logo_px = bl1map.card_icon(bl1_cooked, bl1_brand_keys, "jakobs")
        assert bl1_logo_w == bl1map.ICON_SIZE and bl1_logo_h < bl1_logo_w and any(bl1_logo_px[3::4]), (bl1_logo_w, bl1_logo_h)
        assert bl1map.item_icon(bl1_cooked, "sniper") and bl1map.item_icon(bl1_cooked, "shield") and bl1map.item_icon(bl1_cooked, "comm")
        assert bl1map.item_icon(bl1_cooked, "nope") is None
        # (its kind's square - placed with the first frame, "repeater", kept by the next ones - not drawn: only the
        # item's own drawing - the user)
        bl1_icons_movie = bl1map._menu_movie(bl1_cooked)
        bl1_icon_clip = next(c for tags in bl1_icons_movie.sprites.values() for code, body in tags if code == 26
                             for c, _m, n in [bl1map._place2(body)] if n and bl1map.ITEM_ICON.fullmatch(n))
        assert len(bl1_icons_movie.display_list(bl1_icon_clip, "sniper", carried=True)) == 2, "the square behind it too"
        assert len(bl1_icons_movie.display_list(bl1_icon_clip, "sniper")) == 1, "(its frame only places the rifle)"
        bl1_pistol_w, bl1_pistol_h, bl1_pistol_px = bl1map.item_icon(bl1_cooked, "repeater")
        assert bl1_pistol_px[3] == 0 and bl1_pistol_h < bl1_pistol_w, "the pistol without its square"
        assert bl1map.item_icon(bl1_cooked, "health"), "its cross: also what the empty frame after it shows"
        # its element icons: the card's "chemical" clip at the item's frame number (1: explosive, no level)
        assert bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, 1) and bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, 13)
        assert bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, 0) is None and bl1map.card_frame_icon(bl1_cooked, "nope", 1) is None
        assert bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, "fire1") and bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, "fire9") is None
        assert bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, "fire3")[:2] == bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, "fire0")[:2], (
            "a level's frame: its element's mark alone (moved a little: the number beside it), its number left out")
        assert bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, "fire1")[:2] == bl1map.card_frame_icon(bl1_cooked, bl1map.ELEMENT_CLIP, "fire0")[:2], (
            "the first level too (its frame moves the mark: still the mark alone)")
        bl1_element_png = bl1_work.run_job(json.dumps({"do": "cardframe", "cooked": str(bl1_cooked), "clip": "chemical", "frame": 6}))
        assert bl1_element_png[:8] == b"\x89PNG\r\n\x1a\n", bl1_element_png[:16]
        bl1_item_png = bl1_work.run_job(json.dumps({"do": "itemicon", "cooked": str(bl1_cooked), "label": "repeater"}))
        assert bl1_item_png[:8] == b"\x89PNG\r\n\x1a\n", bl1_item_png[:16]
        assert bl1map.card_icon(bl1_cooked, bl1_brand_keys, "corazza") is None, "no logo of its own in the movie"
        assert bl1map.card_icon(bl1_cooked, ["nope"], "jakobs") is None
        bl1_logo_png = bl1_work.run_job(json.dumps({"do": "cardicon", "cooked": str(bl1_cooked), "keys": bl1_brand_keys,
                                                    "label": "s_and_s"}))
        assert bl1_logo_png[:8] == b"\x89PNG\r\n\x1a\n", bl1_logo_png[:16]
        print(f"  BL1: packages (584), the arena's map anchor, its map rendered {bl1_arena_img.width} x {bl1_arena_img.height}")
    # A DLC map: its package is under DLC/<code name>/{Lic,Compat}/Content (gamedir.package_path)
    from helios_tracker import gamedir  # noqa: PLC0415
    real_cooked = gamedir.cooked_dir
    gamedir.cooked_dir = lambda: GAME_COOKED
    try:
        dlc = gamedir.package_path("Sage_Underground_P.upk")
        assert dlc is not None and "DLC" in dlc.parts, dlc
        assert gamedir.package_path("Sanctuary_P.upk") == GAME_COOKED / "Sanctuary_P.upk" and gamedir.package_path("Nope_P.upk") is None
        t = time.perf_counter()
        (img,) = load_tactical_map(dlc, "Sage_UI_TacticalMap_Undergrnd.Undergrnd_P")
        assert (img.format, img.width, img.height) == ("PF_DXT5", 1024, 644), img
        print(f"  Sage_Underground_P (DLC): {img.name} {img.width}x{img.height} ({time.perf_counter() - t:.2f} s)")
    finally:
        gamedir.cooked_dir = real_cooked
    # A map drawn from a part of its texture (a GFx DefineSubImage, its image's id 0): the Pre-Sequel's ComFacility_P
    tps_cooked = project.path("tps")
    tps_facility = tps_cooked / "WillowGame" / "CookedPCConsole" / "ComFacility_P.upk" if tps_cooked else None
    if tps_facility is not None and tps_facility.is_file():
        (facility_img,) = load_tactical_map(tps_facility, "UI_TacticalMap_ComFacility.ComFacility_P")
        assert (facility_img.width, facility_img.height, facility_img.crop) == (1024, 1024, (0, 0, 743, 644)), facility_img
        print(f"  ComFacility_P (the Pre-Sequel): {facility_img.name} {facility_img.width}x{facility_img.height}, the part drawn"
              f" {facility_img.crop}")

    # A level load through the collector (fake world); the map is extracted on its thread
    ns = types.SimpleNamespace
    # A respawning player (tools/probes/probe_respawn.txt): hidden + awaiting a respawn -> their New-U spot
    spot = ns(X=19361.0, Y=-27830.0, Z=1581.0)
    # Down states (tools/probes/probe_respawn.txt): crippled / dead / fine
    injured = enum.Enum("EInjuredStage", ["INJURED_Not", "INJURED_Targeted"], start=0)
    dead_state = enum.Enum("EInjuredDeadState", ["INJUREDDEAD_None", "INJUREDDEAD_InitRagdoll"], start=0)
    down_state = col.Collector._down_state
    assert down_state(ns(InjuredState=injured.INJURED_Targeted, InjuredDeadState=dead_state.INJUREDDEAD_None)) == "crippled"
    assert down_state(ns(InjuredState=injured.INJURED_Targeted, InjuredDeadState=dead_state.INJUREDDEAD_InitRagdoll)) == "dead"
    assert down_state(ns(InjuredState=injured.INJURED_Not, InjuredDeadState=dead_state.INJUREDDEAD_None)) == ""
    assert down_state(ns()) == "", "no InjuredState: fine"
    # In a menu (tools/probes/probe_menu.txt): the player info's bGFxMenuOpen (any menu), the pawn's
    # bViewingStatusMenu (the status menu)
    in_menu = col.Collector._in_menu
    assert in_menu(ns(bViewingStatusMenu=False, PlayerReplicationInfo=ns(bGFxMenuOpen=1)))
    assert in_menu(ns(bViewingStatusMenu=True, PlayerReplicationInfo=ns(bGFxMenuOpen=0)))
    assert not in_menu(ns(bViewingStatusMenu=False, PlayerReplicationInfo=ns(bGFxMenuOpen=0)))
    assert not in_menu(ns()), "no such properties: not in a menu"
    # Opened containers: state 7 + no longer usable (host); a client gets the state only (tools/probes/probe_client_containers.txt)
    opened_box, closed_box = ns(SimpleAnimState=7, bCanBeUsed=(1, 0)), ns(SimpleAnimState=4, bCanBeUsed=(1, 0))
    looted = col.Collector._is_looted
    assert (looted(opened_box), looted(opened_box, True), looted(closed_box, True)) == (False, True, False)
    assert looted(ns(SimpleAnimState=7, bCanBeUsed=(0, 0))), "host: opened and no longer usable"
    respawn_state = col.Collector._respawn_state
    # Health / shield values for the page: the current truncated to a tenth (57.96 rounded to 58.0 showed 58, the game
    # 57), the max precise (sent on change)
    assert (col._vital(57.96), col._vital(107.89068603515625), col._vital(100.0)) == (57.9, 107.8, 100)
    assert (col._vital_max(107.89068603515625), col._vital_max(57.695556640625), col._vital_max(100.0)) == (107.8907, 57.6956, 100)
    # a player's oxygen (the Pre-Sequel's Oz meter - tools/probes/probe_tps2.txt): the pawn's OxygenPool, else their replicated one
    oxygen_pool = types.SimpleNamespace(Data=types.SimpleNamespace(CurrentValue=40.0, MaxValue=100.0))
    assert col.Collector._oxygen(types.SimpleNamespace(OxygenPool=oxygen_pool)) == (40.0, 100.0)
    assert col.Collector._oxygen(types.SimpleNamespace(OxygenPool=None, PlayerReplicationInfo=types.SimpleNamespace(OxygenPool=oxygen_pool))) \
        == (40.0, 100.0), "a co-op client's view: the replicated pool"
    assert col.Collector._oxygen(types.SimpleNamespace(PlayerReplicationInfo=None)) is None, "BL2: no oxygen"
    # an air dome's bubble (tools/probes/probe_dome_state.txt): its sphere's extent the radius, bAttached on / off
    def dome_io(extent: float, attached: bool) -> types.SimpleNamespace:
        return types.SimpleNamespace(CollisionComponent=types.SimpleNamespace(
            Bounds=types.SimpleNamespace(BoxExtent=types.SimpleNamespace(X=extent)), bAttached=attached))
    assert col.Collector._dome(dome_io(1687.2, True)) == [1687, 1] and col.Collector._dome(dome_io(976.0, False)) == [976, 0]
    assert col.Collector._dome(types.SimpleNamespace(CollisionComponent=None)) is None, "no sphere: no dome"
    vacuum_state = enum.IntEnum("EVacuumState", ["VS_InAir", "VS_InVacuum"], start=0)
    assert col.Collector._in_vacuum(types.SimpleNamespace(VacuumComponent=types.SimpleNamespace(State=vacuum_state.VS_InVacuum)))
    assert not col.Collector._in_vacuum(types.SimpleNamespace(VacuumComponent=types.SimpleNamespace(State=vacuum_state.VS_InAir)))
    assert not col.Collector._in_vacuum(types.SimpleNamespace(VacuumComponent=None)), "BL2: never in a vacuum"
    # Skills (tools/probes/probe_passives.txt): the manager's running timed skills by player; the action skill
    # running / cooling down (its pool) / ready; timed passive effects; melee cooldown
    from helios_tracker.skills import SkillReader  # noqa: PLC0415

    skill_type = enum.Enum("ESkillType", ["SKILL_TYPE_Passive", "SKILL_TYPE_Action"], start=0)
    duration_type = enum.Enum("EEffectDurationType", ["DURATION_Infinite", "DURATION_Timed"], start=0)
    skill_state = enum.Enum("ESkillState", ["SKILL_Inactive", "SKILL_Active"], start=0)

    def skill_def(addr: int, name: str, kind, timed: bool = True):  # noqa: ANN001, ANN202
        return ns(_get_address=lambda: addr, SkillName=name, SkillType=kind,
                  DurationType=duration_type.DURATION_Timed if timed else duration_type.DURATION_Infinite)

    gunzerk = skill_def(0x901, "Gunzerking", skill_type.SKILL_TYPE_Action)
    buff = skill_def(0x902, "Locked and Loaded - active", skill_type.SKILL_TYPE_Passive)
    always = skill_def(0x903, "Quick Draw", skill_type.SKILL_TYPE_Passive, timed=False)
    player_pc = ns(_get_address=lambda: 0x950, SavedSkillTreeSkill=gunzerk, GetSkillCooldownTime=lambda: 42.0,
                   GetMeleeSkillCooldownTime=lambda: 15.0,
                   SkillCooldownPool=ns(Data=ns(CurrentValue=21.0, ConsumptionRate=2.0)),
                   MeleeSkillCooldownPool=ns(Data=ns(CurrentValue=0.0, ConsumptionRate=1.0)))

    def active(d, start: float, duration: float):  # noqa: ANN001, ANN202
        return ns(Definition=d, SkillState=skill_state.SKILL_Active, StartTime=start, Duration=duration, SkillInstigator=player_pc)

    manager = ns(ActiveSkills=[active(always, 0.0, 0.0), active(buff, 1630.0, 5.5)])
    player_pc.GetSkillManager = lambda: manager
    reader = SkillReader()
    reader.update(player_pc, 1631.0, 10.0)
    got = reader.player(ns(Controller=player_pc), 10.0)
    assert got == {"ak": ["c", 0.5, 10.5, "Gunzerking"], "ps": [["Locked and Loaded - active", 4.5, 5.5]]}, got
    manager.ActiveSkills.append(active(gunzerk, 1625.0, 20.0))  # the action skill running
    player_pc.SkillCooldownPool.Data.CurrentValue = 0.0
    player_pc.MeleeSkillCooldownPool.Data.CurrentValue = 7.5
    reader.update(player_pc, 1631.0, 10.5)
    got = reader.player(ns(Controller=player_pc), 10.5)
    assert got["ak"] == ["a", 0.7, 14.0, "Gunzerking"] and got["mk"] == [0.5, 7.5], got
    manager.ActiveSkills = []
    reader.update(player_pc, 1640.0, 11.0)
    assert reader.player(ns(Controller=player_pc), 11.0) == {"ak": ["r", "Gunzerking"], "mk": [0.5, 7.5]}
    assert reader.player(ns(Controller=None), 11.0) == {}, "no controller (co-op client)"
    driving = reader.player(ns(Controller=None, DrivenVehicle=ns(Controller=player_pc)), 11.0)
    assert driving == {"ak": ["r", "Gunzerking"], "mk": [0.5, 7.5]}, ("driving: the vehicle's controller", driving)
    # Another player, on the host (tools/probes/probe_action_skill.txt): no SavedSkillTreeSkill (the name: their
    # tree's action skill), their cooldown pool empty (the full cooldown from when their skill stopped
    # running - Phaselock's Duration said 120 s, it ended after 1 s)
    phaselock = skill_def(0x906, "Phaselock", skill_type.SKILL_TYPE_Action)
    other_pc = ns(_get_address=lambda: 0x960, SavedSkillTreeSkill=None, GetSkillCooldownTime=lambda: 13.0,
                  GetMeleeSkillCooldownTime=lambda: 0.0, PlayerSkillTree=ns(Skills=[ns(Definition=phaselock)]),
                  SkillCooldownPool=ns(Data=ns(CurrentValue=0.0, ConsumptionRate=1.0)))
    host = SkillReader()  # its own (the tests after this one go on with reader's clock)
    manager.ActiveSkills = [ns(Definition=phaselock, SkillState=skill_state.SKILL_Active, StartTime=2000.0,
                               Duration=120.0, SkillInstigator=other_pc)]
    host.update(player_pc, 2000.5, 12.0)
    assert host.player(ns(Controller=other_pc), 12.0)["ak"][::3] == ["a", "Phaselock"]
    manager.ActiveSkills = []
    host.update(player_pc, 2001.5, 13.0)  # stopped: last seen running at 2000.5
    got = host.player(ns(Controller=other_pc), 13.0)
    assert got == {"ak": ["c", 0.923, 12.0, "Phaselock"]}, ("another player's cooldown, computed", got)
    host.update(player_pc, 2014.0, 14.0)
    assert host.player(ns(Controller=other_pc), 14.0) == {"ak": ["r", "Phaselock"]}
    host.update(player_pc, 2005.0, 15.0)  # (still cooling at 2005, but:)
    host.update(player_pc, 3.0, 16.0)  # a level load: the world time restarted
    assert host.player(ns(Controller=other_pc), 16.0) == {"ak": ["r", "Phaselock"]}, "level load: not cooling"
    # not unlocked yet (the Pre-Sequel at Lv 1, tools/probes/probe_tps.txt): the tree's action skill at Grade 0 - its cooldown
    # reads a length, its pool empty: no "ak" (not "ready"); unlocked (Grade 1): ready
    cold_as_ice = skill_def(0x907, "Cold as Ice", skill_type.SKILL_TYPE_Action)
    locked_tree_skill = ns(Definition=cold_as_ice, Grade=0)
    locked_pc = ns(_get_address=lambda: 0x970, SavedSkillTreeSkill=cold_as_ice, GetSkillCooldownTime=lambda: 30.0,
                   GetMeleeSkillCooldownTime=lambda: 0.0, PlayerSkillTree=ns(Skills=[locked_tree_skill]),
                   SkillCooldownPool=ns(Data=ns(CurrentValue=0.0, ConsumptionRate=1.0)))
    locked_reader = SkillReader()
    locked_reader.update(locked_pc, 100.0, 20.0)
    assert locked_reader.player(ns(Controller=locked_pc), 20.0) == {}, "action skill not unlocked yet: nothing"
    locked_tree_skill.Grade = 1
    assert locked_reader.player(ns(Controller=locked_pc), 20.0 + 6.0) == {"ak": ["r", "Cold as Ice"]}, "unlocked: ready"
    # a nameless timed effect (an empty SkillName: three on a Pre-Sequel Lv 1 player): its object name, a guess ("raw" 1)
    nameless_skill = skill_def(0x908, "", skill_type.SKILL_TYPE_Passive)
    nameless_skill.Name = "Skill_LevelUp"
    nameless_skill._path_name = lambda: "GD_Test.Skills.Skill_LevelUp"
    manager.ActiveSkills = [ns(Definition=nameless_skill, SkillState=skill_state.SKILL_Active, StartTime=90.0, Duration=30.0,
                               SkillInstigator=locked_pc)]
    locked_pc.GetSkillManager = lambda: manager
    locked_reader.update(locked_pc, 100.0, 27.0)
    nameless_got = locked_reader.player(ns(Controller=locked_pc), 27.0)
    assert nameless_got["ps"] == [["Skill LevelUp", 20.0, 30.0, 1]], ("its object name, marked made up", nameless_got)
    manager.ActiveSkills = []
    # a hidden helper (Krieg's BloodOverdriveChild, dev text for a name, in no tree): shown as the tree
    # skill with its icon (tools/probes/probe_child_skill.txt)
    icon = ns(_path_name=lambda: "UI_Lilac_SharedSkillIcons_Psyc.SkillIcon-Psycho04")
    overdrive = skill_def(0x904, "Surcharge sanglante", skill_type.SKILL_TYPE_Passive, timed=False)
    overdrive.SkillIcon = icon
    child = skill_def(0x905, "Blood Overdrive Child - If you are reading this please bug it!", skill_type.SKILL_TYPE_Passive)
    child.SkillIcon = icon
    krieg_pc = ns(_get_address=lambda: 0x951, PlayerSkillTree=ns(Skills=[ns(Definition=overdrive)]))
    manager.ActiveSkills = [ns(Definition=child, SkillState=skill_state.SKILL_Active, StartTime=1640.0, Duration=8.0,
                               SkillInstigator=krieg_pc)]
    reader.update(player_pc, 1642.0, 12.0)
    assert reader._by_pc[0x951]["timed"] == [("Surcharge sanglante", 6.0, 8.0, False)], reader._by_pc
    assert respawn_state(ns(bHidden=True, bAwaitingInjuredRespawn=True, AwaitingRespawnResurrectLocation=spot)) == (True, spot)
    assert respawn_state(ns(bHidden=False, bAwaitingInjuredRespawn=True, AwaitingRespawnResurrectLocation=spot)) == (False, None)
    assert respawn_state(ns(bHidden=True, AwaitingRespawnResurrectLocation=spot)) == (False, None), "hidden alone"
    assert respawn_state(ns(bHidden=True, bIsAwaitingRespawn=True,
                            AwaitingRespawnResurrectLocation=ns(X=0.0, Y=0.0, Z=0.0))) == (True, None), "no spot"
    vol = ns(
        _path_name=lambda: "Sanctuary_P.TheWorld:PersistentLevel.WillowTacticalMapVolume_0",
        BrushComponent=ns(Bounds=ns(Origin=ns(X=-3072.0, Y=-10240.0, Z=4096.0), BoxExtent=ns(X=23552.0, Y=22528.0, Z=8192.0))),
        UnrealUnitsPerPixel=32.0,
        NorthOffsetInDegreesClockwise=0.0,
    )
    movie = ns(_path_name=lambda: "UI_TacticalMap_Sanctuary.Sanctuary_P")

    def pawn(addr: int, name: str, x: float, y: float, nxt: object = None, enemy: bool = False) -> object:
        return ns(
            _get_address=lambda: addr, Name=name, Class=ns(Name="WillowAIPawn", _get_address=lambda: 0xC100), bDeleteMe=False,
            bIsDead=False, bHidden=False,
            Location=ns(X=x, Y=y, Z=3690.0), Rotation=ns(Yaw=16384), GetMaxHealth=lambda: 100.0,
            GetHealth=lambda: 40.0, IsEnemy=lambda other: enemy, GetExpLevel=lambda: 12,
            GetShieldStrength=lambda: 25.0, GetMaxShieldStrength=lambda: 50.0 if enemy else 0.0,
            # the name: its balance's per-playthrough DisplayName (a property); the name functions
            # crashed the game - never called (they'd fail the check)
            BalanceDefinitionState=ns(BalanceDefinition=ns(PlayThroughs=[
                ns(PlayThrough=1, DisplayName=name.title()), ns(PlayThrough=2, DisplayName="Badass " + name.title())])),
            GetTargetName=lambda *a: (_ for _ in ()).throw(AssertionError("GetTargetName called on a pawn")),
            NextPawn=nxt, PlayerReplicationInfo=None,
        )

    # hidden (bHidden): not in the game's world - BL1's bus stop Claptrap, parked for a later scene: not shown
    hidden_npc = pawn(0x220, "claptrap", 9000.0, 3000.0)
    hidden_npc.bHidden = True
    seat = pawn(0x210, "seat", 10000.0, 3000.0, nxt=hidden_npc)  # a vehicle's turret seat: not shown
    seat.Class = ns(Name="WillowWeaponPawn", SuperField=None, _get_address=lambda: 0xC200)  # (seats: by class address)
    enemy = pawn(0x200, "bullymong", 10000.0, 3000.0, nxt=seat, enemy=True)
    me = pawn(0x100, "me", 10635.4, 5702.0, nxt=enemy)
    me.Class = ns(Name="WillowPlayerPawn", SuperField=None, _get_address=lambda: 0xC300)
    # Driving: the vehicle has taken the PlayerReplicationInfo (as seen in game)
    me.PlayerReplicationInfo = None
    me.DrivenVehicle = ns(PlayerReplicationInfo=ns(PlayerName="Zer0", ExpLevel=30, ExpPointsNextLevelAt=78861, CharacterNameIdDef=ns(
        Name="Assassin", LocalizedCharacterName="Zer0",
        CharacterClassId=ns(Name="Assassin", LocalizedClassNameNonCaps="Assassin"))))
    me.HealthVar, me.HealthMaxVar, me.ShieldVar, me.ShieldMaxVar = 141.0, 999.0, 60, 999  # (wrong while driving)
    # Driving: the functions, not the properties (seen: max health = health in a vehicle)
    me.GetHealth, me.GetMaxHealth = (lambda: 141.0), (lambda: 141.0)
    me.GetShieldStrength, me.GetMaxShieldStrength = (lambda: 60.0), (lambda: 120.0)
    def struct(**values: object) -> object:  # a WrappedStruct stand-in: _type._fields() + _get_field
        kinds = {int: "IntProperty"}
        fields = [ns(Name=k, Class=ns(Name=kinds.get(type(v), "ObjectProperty"))) for k, v in values.items()]
        return ns(_type=ns(_fields=lambda: iter(fields)), _get_field=lambda f: values[f.Name])

    weapon_data = struct(
        WeaponTypeDefinition=ns(Name="WT_SMG_Hyperion", Outer=ns(Name="A_Weapons"), Typename="Sub-Machine Gun"),
        ManufacturerDefinition=ns(Name="Hyperion", Outer=ns(Name="Manufacturers"),
                                  Grades=[ns(DisplayName="Hyperion"), ns(DisplayName="Hyperion+")]),
        ManufacturerGradeIndex=1,
        BarrelPartDefinition=ns(Name="SMG_Barrel_Hyperion", Outer=ns(Name="Barrel")),
        TitlePartDefinition=ns(Name="Title_Barrel_Hyperion", Outer=ns(Name="Title_Hyperion"), PartName="Bitch"),
    )
    serial_state = enum.IntEnum("SerialNumberState", ["SNS_Empty", "SNS_Encrypted", "SNS_Full"], start=0)
    weapon = ns(
        _get_address=lambda: 0x300, Class=ns(Name="WillowWeapon", SuperField=None), Inventory=None,
        GetShortHumanReadableName=lambda: "Unkempt Harold", RarityLevel=5, ExpLevel=30, MonetaryValue=4321,
        InstantHitDamage=512.4, ProjectilesPerShot=3.0, FireInterval=0.25, ClipSize=16.0, ReloadTime=2.25,
        QuickSelectSlot=1, DefinitionData=weapon_data,
        # its serial: a BL2 Law's (tools/probes/probe_serial2.txt: the packed bits, unique id 235059291, no check yet)
        CreateSerialNumber=lambda: ns(State=serial_state.SNS_Full, RunningCounter=309, Buffer=tuple(bytes.fromhex(
            "875bb8020effff008747024006814042c38885110d2301c6ffffffffd230feff4fc38840820de3ff"))),
    )
    shield = ns(
        _get_address=lambda: 0x301, Class=ns(Name="WillowShield", SuperField=None), Inventory=None,
        GetShortHumanReadableName=lambda: "Adaptive Shield", RarityLevel=2, ExpLevel=28, MonetaryValue=900,
        DefinitionData=None, GetZippyFrame=lambda: "Shield", ElementalFrame="None",  # (its card's type frame)
    )
    me.InvManager = ns(InventoryChain=weapon, ItemChain=None, Backpack=[shield])
    skill_def = ns(_get_address=lambda: 0x401, Name="Headsh0t", SkillName="Headsh0t", MaxGrade=5,
                   SkillDescription="[skill]Critical Hit[-skill] damage")
    branch = ns(  # the static layout: tier 1 = [skill, empty, empty]
        _get_address=lambda: 0x400, Name="Branch_Sniping", BranchName="Sniping",
        # (a hidden helper after the real skill, as Krieg's trees have: not in the grid)
        Tiers=[ns(Skills=[skill_def, ns(_get_address=lambda: 0x402, Name="_Helper")], PointsToUnlockNextTier=5)],
        Layout=ns(Tiers=[ns(bCellIsOccupied=[True, False, False])]),
    )
    skill = skill_def
    me.Controller = ns(
        _get_address=lambda: 0x110,
        ExpPool=ns(Data=ns(CurrentValue=77851.0)), GetExpPointsRequiredForLevel=lambda level: 70000,
        PlayerClass=ns(Name="CharClass_Assassin"),
        PlayerSkillTree=ns(  # as the game has it: PlayerSkillTree{Branch,Tier,Skill}Data, linked by index
            Branches=[ns(Definition=branch, TierIndices=[0], ParentBranchIndex=3)],  # a child of the root
            Tiers=[ns(TierNumber=1, ParentBranchIndex=0, SkillIndices=[0], bUnlocked=True)],
            Skills=[ns(Definition=skill, Grade=4, ParentTierIndex=0)],
            GetSkillPointsSpentInTree=lambda: 4,
        ),
    )
    wi = ns(
        GetStreamingPersistentMapName=lambda: "Sanctuary_P",
        GetMapInfo=lambda: ns(TacticalMapVolume=vol, TacticalMapMovie=movie),
        PawnList=me,
    )
    col.ENGINE = ns(GetCurrentWorldInfo=lambda: wi)
    col.get_pc = lambda **k: ns(MyWillowPawn=me, Rotation=ns(Yaw=0))
    gamedir.cooked_dir = lambda: GAME_COOKED
    barrel = ns(  # an interactive object whose display name comes from its balance definition
        Name="WillowInteractiveObject_3", Outer=ns(Class=ns(Name="Level")), bDeleteMe=False, bHidden=False,
        Location=ns(X=9000.0, Y=1000.0, Z=3690.0), InteractiveObjectDefinition=ns(Name="IO_FireBarrel"),
        BalanceDefinitionState=ns(BalanceDefinition=ns(DefaultDisplayName="Incendiary Barrel")),
        Class=ns(Name="WillowInteractiveObject"), _get_address=lambda: 0x500,
        GetTargetName=lambda: "", GetHumanReadableName=lambda: "",
    )
    # The mission tracker (as seen in game, tools/probes/probe_missions.txt): one tracked mission with an
    # active area objective and an inactive one, plus an active quest giver on an NPC
    # The mission log (tools/probes/probe_quests.txt): MissionList entries {MissionDef, Status,
    # ObjectivesProgress (per ObjectiveDefs entry), ActiveObjectiveSet}; a done story mission, the
    # tracked one (3 objectives, the current step = the last two), a side mission it unlocked
    # (available) and one needing the tracked mission (locked)
    status = enum.Enum("EMissionStatus", ["MS_NotStarted", "MS_Active", "MS_Complete"], start=0)
    secure = ns(Name="Securethetown", ProgressMessage="Sécuriser la ville", ObjectiveCount=1, _get_address=lambda: 0x650)
    kill = ns(Name="KillBandits", ProgressMessage="Tuer des bandits", ObjectiveCount=5, _get_address=lambda: 0x651)
    # (its station: set below, once the stations exist)
    extra = ns(Name="Bonus", ProgressMessage="Bonus", ObjectiveCount=1, bObjectiveIsOptional=True, _get_address=lambda: 0x652)

    # travel stations (tools/probes/probe_area.txt): the name the game shows, the map they're in
    shelf = ns(_get_address=lambda: 0x680, StationDisplayName="Southern Shelf", StationLevelName="SouthernShelf_P")
    sanctuary = ns(_get_address=lambda: 0x681, StationDisplayName="Sanctuary", StationLevelName="Sanctuary_P")
    bay = ns(_get_address=lambda: 0x682, StationDisplayName="Southern Shelf - Bay", StationLevelName="SouthernShelf_P")

    def mission_def(addr: int, path: str, name: str, number: int, plot: bool, deps: list, objectives: list = ()) -> object:
        return ns(_get_address=lambda: addr, _path_name=lambda: path, Name=path.split(".")[-1], MissionName=name,
                  MissionNumber=number, bPlotCritical=plot, Dependencies=deps, ObjectiveDefs=list(objectives),
                  MissionDescription="[place]Liar's Berg[-place] needs you.", MissionGiver="Claptrap", GameStage=3,
                  TravelStation=shelf if number < 20 else None, TurnInStation=sanctuary if number == 2 else None)

    kill.StationOverride = bay  # where that step is done (MissionObjectiveDefinition.StationOverride)
    henchman = mission_def(0x610, "GD_Episode02.M_Ep2_Henchman", "Aveugle", 1, True, [])
    mission = mission_def(0x600, "GD_Episode02.M_Ep2a_MoreGuns", "Ménage à Liar's Berg", 2, True, [henchman], [secure, kill, extra])
    mission.bGameStageLocked = True  # picked up: its level is set (GameStage 3 from mission_def)
    side = mission_def(0x620, "GD_Z1_Side.M_Side", "Side job", 20, False, [henchman])
    later = mission_def(0x630, "GD_Z1_Later.M_Later", "Later job", 21, False, [mission])
    log_entries = [
        ns(MissionDef=henchman, Status=status.MS_Complete, ObjectivesProgress=[]),
        ns(MissionDef=mission, Status=status.MS_Active, ObjectivesProgress=[1, 3, 0],
           ActiveObjectiveSet=ns(ObjectiveDefinitions=[kill, extra]), SubObjectiveSets=[]),
        ns(MissionDef=side, Status=status.MS_NotStarted, ObjectivesProgress=[], bHeardKickoff=True),
        ns(MissionDef=later, Status=status.MS_NotStarted, ObjectivesProgress=[]),
    ]
    area = ns(Location=ns(X=28354.0, Y=-12060.0, Z=3310.0), AreaRadius=2125)

    def waypoint(addr: int, owner: object, active: bool, objective: object = None, cls: str = "MissionObjectiveWaypointComponent") -> object:
        return ns(_get_address=lambda: addr, Class=ns(Name=cls), bActive=active, Owner=owner,
                  WaypointInfo=ns(LinkedObjective=objective))

    tracker = ns(Name="MissionTracker_0", ActiveMission=mission, MissionList=log_entries, MissionWaypoints=[ns(Mission=mission, Waypoints=[
        waypoint(0x700, area, True, secure),
        waypoint(0x701, ns(Location=ns(X=1.0, Y=2.0, Z=3.0), AreaRadius=0), False, ns(Name="MeetBrewster", ProgressMessage="x")),
        waypoint(0x702, ns(_get_address=lambda: 0x703, Location=ns(X=5.0, Y=6.0, Z=7.0)), True, cls="MissionDirectiveWaypointComponent"),
    ])])
    real_find_all = col.unrealsdk.find_all
    # the level's discovery areas (tools/probes/probe_discovery.txt): a named one, a fog of war only one
    def discovery(n, short, name, fog, r):
        return ns(Name=f"WorldDiscoveryArea_{n}", Outer=ns(Class=ns(Name="Level")), bDeleteMe=False, bUseCustomName=False,
                  CustomName="None", DefaultWorldAreaShortName=short, WorldAreaDisplayName=name, bForFogOfWarOnly=fog,
                  DetectionRadius=r, Location=ns(X=100.4, Y=-200.0, Z=30.0))
    areas_fake = [discovery(4, "SOUTHERNSHELF_PWDA_4", "Wreck Of The Ice Sickle", False, 4644.0),
                  discovery(3, "SOUTHERNSHELF_PWDA_3", "", True, 5908.1)]
    col.unrealsdk.find_all = lambda cls, exact=True: {"WillowInteractiveObject": [barrel], "MissionTracker": [tracker],
                                                     "WorldDiscoveryArea": areas_fake}.get(cls, [])
    hub = Hub()
    c = col.Collector(hub)
    c.tick(1000.0)
    assert "state" not in hub._channels, "collected with no page connected"
    hub.clients = 1  # a page is open
    c.tick(1001.0)
    c.tick(1001.1)  # one heavy task per tick: pickups, then objects, then players
    c.tick(1001.2)
    level: dict = {}
    for _ in range(100):
        level = json.loads(hub.latest("level"))
        if level["status"] != "loading":
            break
        time.sleep(0.05)
    assert level["status"] == "ready" and level["upp"] == 128.0 and level["center"] == [-3072.0, -10240.0], level
    # the game and its features, for the page (games.py -> game.js)
    assert level["game"] == "bl2" and level["features"] == ["discovery", "learnedelements", "missionsteps", "scan", "tacmap"], (level.get("game"), level.get("features"))
    # The games' profiles (games.py): one per game, by mods_base's name; each other game only what differs from BL2
    from helios_tracker import games as game_profiles  # noqa: PLC0415
    profile_bl2, profile_tps, profile_bl1 = (game_profiles.make_profile(n) for n in ("BL2", "TPS", "BL1"))
    assert type(game_profiles.GAME) is type(profile_bl2), "the fake mods_base's game: BL2"
    assert profile_tps.features == profile_bl2.features | {"oxygen", "jumppads"} and profile_tps.packages == "CookedPCConsole"
    assert profile_bl1.features == {"tacmap", "waypointmarkers", "fontlibrary"} and profile_bl1.packages == "CookedPC" and profile_bl1.gibbed_prefix == ""
    assert (profile_bl2.exe_depth, profile_bl1.exe_depth) == (2, 1), "Binaries/Win32/Borderlands2.exe, Binaries/Borderlands.exe"
    # BL1's world is "Loader" in every area: the area is its first LevelStreamingPersistent (tools/probes/probe_bl1.txt);
    # none (the main menu): the world's own package
    profile_wi = ns(GetStreamingPersistentMapName=lambda: "Sanctuary_P", _path_name=lambda: "Loader.TheWorld:PersistentLevel.WorldInfo_1",
                    StreamingLevels=[ns(Class=ns(Name="LevelStreamingPersistent"), PackageName="arid_p"),
                                     ns(Class=ns(Name="LevelStreamingKismet"), PackageName="arid_env")])
    assert profile_bl2.map_name(profile_wi) == "Sanctuary_P" and profile_bl1.map_name(profile_wi) == "arid_p"
    profile_menu = ns(_path_name=lambda: "menumap.TheWorld:PersistentLevel.WorldInfo_0", StreamingLevels=[])
    assert profile_bl1.map_name(profile_menu) == "menumap" and profile_bl1.level_key(profile_menu, "menumap") == ("menumap",)
    # BL1's pause: the escape menu's Pauser, or a status menu's bStatusMenuOnly (inventory, map, skills); its equipped
    # items' kind from their definition's slot (one class for them all)
    import enum  # noqa: PLC0415
    assert profile_bl1.world_paused(ns(Pauser=None, bStatusMenuOnly=True)) and not profile_bl1.world_paused(ns(Pauser=None, bStatusMenuOnly=False))
    assert profile_bl2.world_paused(ns(Pauser=object())) and not profile_bl2.world_paused(ns(Pauser=None, bStatusMenuOnly=True))
    bl1_slot = enum.IntEnum("EEquipmentLoc", ["EQUIPLOC_Shield", "EQUIPLOC_MOD", "EQUIPLOC_Deck"], start=0)
    bl1_shield = ns(DefinitionData=ns(ItemDefinition=ns(EquipmentLocation=bl1_slot.EQUIPLOC_Shield)))
    assert profile_bl1.equip_kind(bl1_shield) == "shield" and profile_bl2.equip_kind(bl1_shield) is None
    # BL1's object behaviours: its behaviour sets' event arrays and reactions (its barrels' Behavior_Explode is there)
    bl1_explode = ns(Class=ns(Name="Behavior_Explode"))
    bl1_barrel = ns(DefaultBehaviorSet=ns(OnSpawn=[], OnBehaviorSetEnabled=[], OnBehaviorSetDisabled=[], OnTouch=[], OnUnTouch=[],
                                         OnUsedBy=[], OnTakeDamage=[None], OnKilled=[], TimerEvents=[], CounterEvents=[],
                                         CustomEvents=[ns(Behaviors=[bl1_explode])]),
                    ExtraBehaviorSets=[])
    assert profile_bl1.object_behaviors(bl1_barrel) == [bl1_explode]
    # BL1's vending machines: their own class (no WillowVendingMachineBase), no shop titles in its menu
    from helios_tracker import shops as profile_shops  # noqa: PLC0415
    bl1_machine = ns(Class=ns(Name="WillowVendingMachine", SuperField=ns(Name="WillowInteractiveObject", SuperField=None)))
    assert not profile_shops.is_machine(bl1_machine), "BL2's profile: not its machine class"
    real_profile = game_profiles.GAME
    game_profiles.GAME = profile_bl1
    try:
        assert profile_shops.is_machine(bl1_machine), "BL1's profile: its machines' own class"
    finally:
        game_profiles.GAME = real_profile
    assert profile_bl1.vending_titles is None and profile_bl2.vending_titles == "VendingMachineExGFxMovie"
    # the updater's one-shot reload: a function each game calls every frame (BL1's viewport client has no Tick)
    assert (profile_bl2.tick_function, profile_bl1.tick_function) == ("WillowGame.WillowGameViewportClient:Tick", "Engine.GameViewportClient:Tick")
    # the price: BL2's call (item, controller, quantity), BL1's (item, quantity) - no controller
    priced = ns(GetSellingPriceForInventory=lambda *a: 1000 + len(a))
    assert (profile_bl2.selling_price(priced, "item", "pc"), profile_bl1.selling_price(priced, "item", "pc")) == (1003, 1002)
    # its prices' currency: BL2's machine says (FormOfCurrency), BL1's has none - dollars
    assert profile_bl1.shop_currency(ns()) == "CURRENCY_Credits"
    assert profile_bl2.ui_stat_kinds == {"shield"} and profile_bl1.ui_stat_kinds == {"shield", "grenade", "classmod"}
    # card stat decimals: BL2's presentation says (FloatPrecision), BL1's has none - one (its SG330's accuracy 6.7)
    assert (profile_bl2.presented_decimals(ns(FloatPrecision=2)), profile_bl1.presented_decimals(ns())) == (2, 1)
    # the shops' timer: BL2's host count (a client: the replicated one), BL1's replicated one (what its menu shows)
    timer_host, timer_gri = ns(SecondsUntilShopsReset=922.85), ns(SecondsUntilShopsReset=925)
    assert profile_bl2.shop_timer_source(ns(Game=timer_host, GRI=timer_gri)) is timer_host
    assert profile_bl2.shop_timer_source(ns(Game=None, GRI=timer_gri)) is timer_gri
    assert profile_bl1.shop_timer_source(ns(Game=timer_host, GRI=timer_gri)) is timer_gri
    # BL1's card lines (tools/probes/probe_bl1_cards.txt, an SG330): the modifier, remapped / its sign flipped / x 100 /
    # rounded as its presentation says - the game's "4.0x", "+43%", "+1"; BL2's: the page's own (None)
    line_rounding = enum.IntEnum("EAttributePresentationRoundingMode", ["ATTRROUNDING_Float", "ATTRROUNDING_IntRound", "ATTRROUNDING_IntCeil",
                                                                         "ATTRROUNDING_IntFloor"], start=0)

    def bl1_pres(**flags: object) -> types.SimpleNamespace:
        return ns(**{"bValueRemappingEnabled": False, "bDisplayAsInverse": False, "bDisplayAsPercentage": False,
                     "RoundingMode": line_rounding.ATTRROUNDING_Float, **flags})
    zoom_pres = bl1_pres(bValueRemappingEnabled=True, bDisplayAsInverse=True, RemappingData=ns(
        InputValueMn=ns(BaseValueConstant=-100.0, BaseValueAttribute=None, InitializationDefinition=None, BaseValueScaleConstant=1.0),
        InputValueMx=ns(BaseValueConstant=0.0, BaseValueAttribute=None, InitializationDefinition=None, BaseValueScaleConstant=1.0),
        OutputValueMn=ns(BaseValueConstant=-10.0, BaseValueAttribute=None, InitializationDefinition=None, BaseValueScaleConstant=1.0),
        OutputValueMx=ns(BaseValueConstant=0.0, BaseValueAttribute=None, InitializationDefinition=None, BaseValueScaleConstant=1.0)))
    card_shown = [profile_bl1.card_line_value(ns(ModifierValue=-40.0), zoom_pres, ns()),
                  profile_bl1.card_line_value(ns(ModifierValue=-0.4318), bl1_pres(bDisplayAsInverse=True, bDisplayAsPercentage=True), ns()),
                  profile_bl1.card_line_value(ns(ModifierValue=1.0), bl1_pres(RoundingMode=line_rounding.ATTRROUNDING_IntFloor), ns()),
                  profile_bl1.card_line_value(ns(ModifierValue=0.0673), bl1_pres(bDisplayAsPercentage=True, RoundingMode=line_rounding.ATTRROUNDING_IntCeil), ns())]
    assert card_shown == [(4.0, 1), (43.0, 0), (1.0, 0), (7.0, 0)], card_shown
    assert profile_bl2.card_line_value(ns(ModifierValue=1.0), bl1_pres(), ns()) is None
    # weapon card damage rounding: BL1's presentation rounds up (85.2 -> 86), BL2's a whole number, rounded
    assert profile_bl1.damage_presentation.endswith("AttrPresent_WeaponDamage") and profile_bl2.damage_presentation is None
    damage_rounding = enum.IntEnum("EAttributePresentationRoundingMode", ["ATTRROUNDING_Float", "ATTRROUNDING_IntCeil"], start=0)
    assert sys.modules["helios_tracker.inspector"]._presented(ns(RoundingMode=damage_rounding.ATTRROUNDING_IntCeil), 85.2) == (86, 0)
    # a game text's HTML entities decoded (BL1's manufacturer "S&amp;S Munitions": the page escaped it again)
    assert sys.modules["helios_tracker.inspector"]._localized(ns(Grades=[ns(DisplayName="S&amp;S Munitions")]), 0) == "S&S Munitions"
    # BL1's rarity table: its RarityLevelColors entries' level ranges (no index function) - 12 rare blue, 18 epic purple
    bl1_rarity = profile_bl1.rarity_table(ns(RarityLevelColors=[
        ns(MinLevel=-1, MaxLevel=1, Color=ns(R=255, G=255, B=255)), ns(MinLevel=2, MaxLevel=4, Color=ns(R=255, G=255, B=255)),
        ns(MinLevel=5, MaxLevel=10, Color=ns(R=61, G=210, B=11)), ns(MinLevel=11, MaxLevel=15, Color=ns(R=47, G=120, B=255)),
        ns(MinLevel=16, MaxLevel=49, Color=ns(R=145, G=50, B=200))]))
    assert bl1_rarity["12"] == [3, "#2f78ff"] and bl1_rarity["18"] == [4, "#9132c8"] and bl1_rarity["0"][0] == 0 and "-1" not in bl1_rarity, bl1_rarity
    assert profile_bl2.shop_currency(ns(FormOfCurrency=enum.IntEnum("ECurrencyType", ["CURRENCY_Credits", "CURRENCY_Eridium"], start=0).CURRENCY_Eridium)) == "CURRENCY_Eridium"
    # BL1's skills (tools/probes/probe_bl1_skills.txt): its action skill locked at Grade 0 (PlayerSkills[ActionSkillPlayerSkillIndex]);
    # its tree from SkillTreeBranches' tiers - indices into PlayerSkills (-1: an empty cell), the points a tier asks from
    # the class's PlayerSkillSet, the First branch (the action skill alone) the root
    branch_enum = enum.IntEnum("ESkillBranch", ["SKILLBRANCH_None", "SKILLBRANCH_First", "SKILLBRANCH_Left"], start=0)
    bloodwing = ns(_get_address=lambda: 0x5B1, Name="A_LaunchBloodwing", SkillName="Bloodwing", MaxGrade=1, SkillDescription="")
    focus = ns(_get_address=lambda: 0x5B2, Name="Focus", SkillName="Focus", MaxGrade=5, SkillDescription="Increases accuracy")
    bl1_skills = [ns(Definition=ns(_get_address=lambda: 0x5B0, Name="Fire", SkillName="Fire", MaxGrade=12, SkillDescription=""), Grade=0),
                  ns(Definition=bloodwing, Grade=0), ns(Definition=focus, Grade=2)]
    bl1_ctrl = ns(_get_address=lambda: 0x5C0, PlayerSkills=bl1_skills, ActionSkillPlayerSkillIndex=1, SkillTreeBranches=[
        ns(BranchIndex=branch_enum.SKILLBRANCH_First, PointsSpentInBranch=0, Tiers=[ns(TierIndex=0, PlayerSkillIndexList=[-1, 1])]),
        ns(BranchIndex=branch_enum.SKILLBRANCH_Left, PointsSpentInBranch=2, Tiers=[ns(TierIndex=0, PlayerSkillIndexList=[2, -1])])],
        PlayerClass=ns(PlayerSkillSet=ns(FirstBranch=ns(Tiers=[ns(PointsToUnlockNextTier=1)]),
                                         LeftBranch=ns(Tiers=[ns(PointsToUnlockNextTier=5)]))))
    assert profile_bl1.action_skill_locked(bl1_ctrl), "Bloodwing at Grade 0: locked"
    # BL1's item cards show the level the item needs (probe_bl1_levels: ExpLevel 6, its card 4), BL2's its level
    bl1_gun = ns(GetControllerPlayerExpLevelRequiredToUse=lambda c: 4)
    assert profile_bl1.zippy_frame(ns(ZippyFrame="shield")) == "shield", "BL1's card type frame: a property"
    # BL1's mission items: usable items whose definition says bMissionItem (no WillowMissionItem class) - "Power Coupling"
    from helios_tracker.util import pickup_kind as bl1_pickup_kind  # noqa: PLC0415
    bl1_coupling = ns(Class=ns(Name="WillowUsableItem"), DefinitionData=ns(ItemDefinition=ns(
        _get_address=lambda: 0x7C1, bMissionItem=True, Presentation=ns(Name="MissionObject"))))
    assert bl1_pickup_kind(bl1_coupling) == "mission", bl1_pickup_kind(bl1_coupling)
    # its card element: an item's frame number (FlashTechFrame - probe_bl1_elements: an Explosive MIRV's 1.0), 0 none
    assert profile_bl1.element_frame(ns(GetTechIconFrame=lambda: 1.0), "grenade") == "1"
    assert profile_bl1.element_frame(ns(GetTechIconFrame=lambda: 0.0), "shield") == ""
    # a weapon's: its damage type's element and its tech level (probe_bl1_elements: The Clipper, "fire1" - its card's x1)
    bl1_dmg_enum = enum.IntEnum("EDamageType", ["DAMAGE_TYPE_Unknown", "DAMAGE_TYPE_Incindiary", "DAMAGE_TYPE_Shock"], start=0)
    bl1_clipper = ns(DefinitionData="data", StaticCalculateWeaponTechLevelForUI=lambda d: (1, d),
                     StaticGetWeaponDamageType=lambda d: (ns(DamageType=bl1_dmg_enum.DAMAGE_TYPE_Incindiary), d))
    assert profile_bl1.element_frame(bl1_clipper, "weapon") == "fire1"
    bl1_plain_gun = ns(**{**vars(bl1_clipper), "StaticGetWeaponDamageType": lambda d: (ns(DamageType=bl1_dmg_enum.DAMAGE_TYPE_Unknown), d)})
    assert profile_bl1.element_frame(bl1_plain_gun, "weapon") == ""
    # its level: a stat of its own (the icon: the mark alone) - none without an element, BL2's never
    assert profile_bl1.element_level(bl1_clipper, "weapon") == 1 and profile_bl1.element_level(bl1_plain_gun, "weapon") == 0
    assert profile_bl1.element_level(ns(GetTechIconFrame=lambda: 3.0, CalculateItemTechLevel=lambda: 2), "grenade") == 2
    assert profile_bl1.element_level(ns(GetTechIconFrame=lambda: 0.0, CalculateItemTechLevel=lambda: 2), "shield") == 0
    assert profile_bl2.element_level(bl1_clipper, "weapon") == 0
    # a barrel's element (its explosion's damage type): its element's mark ("exp0") - not learned from the weapons
    assert profile_bl1.damage_type_frame("DAMAGE_TYPE_Explosive") == "exp0" and profile_bl1.damage_type_frame("DAMAGE_TYPE_Unknown") == ""
    assert game_profiles.LEARNED_ELEMENTS in profile_bl2.features and game_profiles.LEARNED_ELEMENTS not in profile_bl1.features
    assert game_profiles.FONT_LIBRARY in profile_bl1.features and game_profiles.FONT_LIBRARY not in profile_bl2.features
    # its containers looted: no longer usable (probe_bl1_looted: bCanBeUsed a flag, no animation state)
    assert profile_bl1.is_looted(ns(bCanBeUsed=False), False) and not profile_bl1.is_looted(ns(bCanBeUsed=True), False)
    # its quest givers: their missions on the object; one offered = eligible (the game's word) and not picked up yet
    # its local player in a vehicle: no MyWillowPawn - the driver of the pawn it controls (the vehicle, or its seat)
    bl1_me = ns(Name="WillowPlayerPawn_0")
    assert profile_bl1.local_pawn(ns(MyWillowPawn=None, Pawn=ns(Driver=bl1_me))) is bl1_me
    assert profile_bl1.local_pawn(ns(MyWillowPawn=bl1_me, Pawn=ns(Driver=None))) is bl1_me
    assert profile_bl2.local_pawn(ns(MyWillowPawn=bl1_me)) is bl1_me
    # its map exits: a map changer's destination from the level's script - its event's output links to the map change
    # action's DefaultMap (W_Arid_P: Default_MapChanger -> ... -> WillowSeqAct_PrepareMapChangeFromDefinition)
    bl1_changer = ns(_get_address=lambda: 0xC1)
    bl1_change = ns(_get_address=lambda: 0xC4, Class=ns(Name="WillowSeqAct_PrepareMapChangeFromDefinition"), DefaultMap="Dry_P", OutputLinks=[])
    bl1_gate = ns(_get_address=lambda: 0xC3, Class=ns(Name="SeqAct_Gate"), OutputLinks=[ns(Links=[ns(LinkedOp=bl1_change)])])
    bl1_used = ns(_get_address=lambda: 0xC2, Name="SeqEvent_Used_0", Originator=bl1_changer, Class=ns(Name="SeqEvent_Used"),
                  OutputLinks=[ns(Links=[ns(LinkedOp=bl1_gate)])])
    bl1_sdk = sys.modules["unrealsdk"]
    bl1_real_find_all, bl1_real_map_name = getattr(bl1_sdk, "find_all", None), profile_bl1.map_name
    bl1_sdk.find_all = lambda cls, exact=True: [bl1_used, ns(Name="Default__SequenceEvent", Originator=None)]
    profile_bl1.map_name = lambda wi_obj: "Arid_P"
    try:
        assert profile_bl1.object_destination(bl1_changer) == "Dry_P"
        assert profile_bl1.object_destination(ns(_get_address=lambda: 0xC9)) == "", "not a changer: none"
    finally:
        bl1_sdk.find_all, profile_bl1.map_name = bl1_real_find_all, bl1_real_map_name
    assert profile_bl2.object_destination(bl1_changer) == ""
    # its vehicles' names: their own fields (no VehicleDef, no GetCustomizableName - the record had failed)
    assert profile_bl1.vehicle_name(ns(DisplayName="", VehicleNameString="Runner")) == "Runner"
    assert profile_bl2.vehicle_name(ns(VehicleDef=ns(DisplayName="Runner"))) == "Runner"
    assert profile_bl1.object_directives(ns(MissionDirectives=["d"])) == ["d"] and profile_bl2.object_directives(ns(Directives=ns(MissionDirectives=["d"]))) == ["d"]
    bl1_eligibility = enum.IntEnum("EMissionEligibility", ["ME_Eligible", "ME_Ineligible_Level", "ME_Ineligible_Dependencies", "ME_Ineligible_Other"], start=0)
    bl1_board_pc = ns(GetMissionEligibility=lambda m: bl1_eligibility.ME_Eligible if m == "tk" else bl1_eligibility.ME_Ineligible_Other)
    assert profile_bl1.mission_offered(bl1_board_pc, "tk", "", False), "eligible, not taken: its !"
    assert not profile_bl1.mission_offered(bl1_board_pc, "tk", "", True), "eligible but picked up already"
    assert not profile_bl1.mission_offered(bl1_board_pc, "other", "", False)
    assert profile_bl2.mission_offered(None, "m", "begin", False) and not profile_bl2.mission_offered(None, "m", "", False)
    # its missions not picked up: the log's entries, then every other mission loaded, not started - offered: eligible
    # a mission's area: its turn-in waypoint's level (else its target's), named as the map's title is
    real_level_name = sys.modules["helios_tracker.collector"].level_name
    sys.modules["helios_tracker.collector"].level_name = lambda m: {"Arid_P": "Arid Badlands"}.get(m, "")
    try:
        assert profile_bl1.mission_home(ns(TurnInWaypointDefinition=ns(PersistentLevelName="Arid_P"), TargetWaypointDefinition=None)) == {
            "a": "Arid Badlands", "map": "Arid_P"}
        assert profile_bl1.mission_home(ns(TurnInWaypointDefinition=ns(PersistentLevelName="None"),
                                           TargetWaypointDefinition=ns(PersistentLevelName="Arid_P")))["a"] == "Arid Badlands"
        assert profile_bl1.mission_home(ns(TurnInWaypointDefinition=None, TargetWaypointDefinition=ns(PersistentLevelName="Nowhere_P"))) is None
    finally:
        sys.modules["helios_tracker.collector"].level_name = real_level_name
    bl1_offered = game_profiles._NotPickedUp("tk", bl1_board_pc)
    assert profile_bl1.mission_status(bl1_offered) == "NotStarted" and profile_bl1.mission_progress(bl1_offered) == ()
    assert bl1_offered.bHeardKickoff and not game_profiles._NotPickedUp("other", bl1_board_pc).bHeardKickoff
    assert profile_bl2.element_frame(ns(ElementalFrame="shock"), "weapon") == "shock" and profile_bl2.element_frame(ns(ElementalFrame="None"), "weapon") == ""
    assert profile_bl2.zippy_frame(ns(GetZippyFrame=lambda: "comm")) == "comm"
    assert profile_bl1.item_card_level(bl1_gun, 6) == 4 and profile_bl2.item_card_level(bl1_gun, 6) == 6
    bl1_player = {"local": True}
    sys.modules["helios_tracker.inspector"]._skills_from_player_skills(bl1_ctrl, bl1_player, {})
    bl1_root, bl1_left = bl1_player["skills"]
    assert bl1_player["skillPoints"] == 2 and bl1_root.get("root") and [c and c["n"] for c in bl1_root["tiers"][0]["cells"]] == [None, "Bloodwing"], bl1_player
    assert bl1_left["pts"] == 2 and bl1_left["tiers"] == [{"need": 5, "cells": [bl1_left["skills"][0], None]}] and bl1_left["skills"][0]["g"] == 2, bl1_left
    assert bl1_left["raw"] == 1, "no game name for its branches: its own, marked"
    bl1_named = {"local": True}
    sys.modules["helios_tracker.inspector"]._skills_from_player_skills(bl1_ctrl, bl1_named, {}, {"SKILLBRANCH_Left": "SNIPER"})
    assert bl1_named["skills"][1]["n"] == "SNIPER" and "raw" not in bl1_named["skills"][1], bl1_named["skills"][1]
    bl1_iconed = {"local": True}
    sys.modules["helios_tracker.inspector"]._skills_from_player_skills(
        bl1_ctrl, bl1_iconed, {}, {}, {("SKILLBRANCH_Left", 0, 0): "menu.skills.mordecai.icon4.on"})
    assert bl1_iconed["skills"][1]["tiers"][0]["cells"][0]["ic"] == "menu.skills.mordecai.icon4.on", bl1_iconed["skills"][1]
    assert "ic" not in bl1_iconed["skills"][0]["tiers"][0]["cells"][1], "no icon for that cell: none"
    # BL1's pawn names: its balance's grade's (GradeIndex), none without a balance - then its own AIPawnName as the guess
    bl1_skag = ns(BalanceDefinitionState=ns(GradeIndex=1, BalanceDefinition=ns(Grades=[
        ns(GradeModifiers=ns(DisplayName="Skag Pup")), ns(GradeModifiers=ns(DisplayName="Adult Skag"))])), AIPawnName="None")
    bl1_claptrap = ns(BalanceDefinitionState=ns(GradeIndex=0, BalanceDefinition=None), AIPawnName="ClapTrap")
    assert (profile_bl1.pawn_name(bl1_skag), profile_bl1.pawn_raw_name(bl1_skag)) == ("Adult Skag", "")
    assert (profile_bl1.pawn_name(bl1_claptrap), profile_bl1.pawn_raw_name(bl1_claptrap)) == ("", "ClapTrap")
    # BL1's level names: its level list's entries, as properties (gd_globals.General.LevelList, offline)
    profile_levels = ns(LevelList=[ns(PersistentMap="arid_p", LevelName="Arid Badlands"), ns(PersistentMap="Arid_SkagGully_P", LevelName="Skag Gully")])
    assert profile_bl1.level_name_in(profile_levels, "Arid_P") == "Arid Badlands" and profile_bl1.level_name_in(profile_levels, "Nope_P") == ""
    assert profile_bl2.level_name_in(ns(GetFriendlyLevelNameFromMapName=lambda m: {"Ice_P": "Three Horns - Divide"}.get(m, "")), "Ice_P") == "Three Horns - Divide"
    # BL1's map placement (bl1map.placement: from its anchor and its shape's size alone) against the game's own: Arid's
    # map objects, world -> TransformedLocation (0-1) x ClipSize (tools/probes/probe_bl1_map.txt) - within 1.5 movie px
    from helios_tracker import bl1map as placement_map  # noqa: PLC0415
    arid_anchor = placement_map.Anchor("Arid", -28388.717, -10011.951, 32, 58.2, 233.131, 1024, 512)
    arid_center, arid_upp = placement_map.placement(arid_anchor, (779.5, 352.2))
    for (wx, wy), (mu, mv) in (((-11696.0, 32992.0), (0.860, 0.241)), ((-45536.0, -2512.0), (0.563, 0.871)),
                               ((-4980.142, -68936.484), (0.006, 0.122)), ((-12118.424, 32065.379), (0.852, 0.249)),
                               ((-46811.902, -29426.098), (0.338, 0.896))):
        arid_mx, arid_my = (wy - arid_center[1]) / arid_upp, -(wx - arid_center[0]) / arid_upp
        assert abs(arid_mx - mu * 779.5) < 1.5 and abs(arid_my - mv * 352.2) < 1.5, ((wx, wy), (arid_mx, arid_my), (mu * 779.5, mv * 352.2))
    assert profile_bl2.movie_no_skip(ns(bForceNoSkip=1)) is True and profile_bl1.movie_no_skip(ns()) is False
    try:
        game_profiles.make_profile("BL3")
        raise AssertionError("an unknown game: no profile")
    except RuntimeError:
        pass
    assert (level["zmin"], level["zmax"]) == (-4096, 12288), level
    fog = level.get("fog")
    assert fog and fog["url"] == f"/image/{level['id']}/1" and fog["pieces"][0][0] == "sanctuary_pwda_1", fog  # (the fake level: Sanctuary)
    state = json.loads(hub.latest("state"))
    # the pawns: their descriptions apart ("pawninfo", on change), the state what moves - merged as the page does
    pawn_infos = {p["i"]: p for p in json.loads(hub.latest("pawninfo"))["pawns"]}  # (records: a list, by "i")
    # rows, compact: [id, x, y, z, health if not full, {the rest} if any] (data.js movingOf), the max in the description
    def state_row(row: list, info: dict) -> dict:
        row_id, row_x, row_y, row_z, *row_more = row
        row_h = row_more.pop(0) if row_more and isinstance(row_more[0], (int, float)) else None
        row_extra = row_more[0] if row_more else {}
        assert len(row_more) <= 1 and isinstance(row_extra, dict), ("a state row", row)
        assert set(row_extra) <= {"r", "s", "ox", "vac", "rs", "dn", "dd", "mn", "ct", "bo", "dv", "ak", "ps", "mk"}, ("only what moves", row)
        assert row_h != info.get("m") and row_extra.get("s", -1) != info.get("sm"), ("full: left out", row, info)
        return {**info, **row_extra, "i": row_id, "x": row_x, "y": row_y, "z": row_z,
                **({"h": info["m"] if row_h is None else row_h} if info.get("m") else {}),
                **({"s": row_extra.get("s", info["sm"])} if info.get("sm") else {})}

    state_pawns = [state_row(row, pawn_infos[row[0]]) for row in state["pawns"]]
    assert state["pawns"][0][:4] == ["100", 10635, 5702, 3690], ("[id, x, y, z]", state["pawns"][0])
    assert json.dumps(state["pawns"]).count("100.0") == 0, ("health: no .0", state["pawns"])
    kinds = {p["n"]: p["k"] for p in state_pawns}
    assert "Claptrap" not in kinds, ("a hidden pawn: not shown", kinds)
    assert all(("r" in p) == (p["k"] in ("me", "player")) for p in state_pawns), ("a heading: the players' only", state_pawns)
    assert not any(p.get("raw") for p in state_pawns), state_pawns  # both have game names
    assert all(p.get("l") == 12 for p in state_pawns), state_pawns
    assert state["hz"] == 10.0 and "t" in state, state
    assert "pickups" not in state and "pickups" in json.loads(hub.latest("pickups")), "the pickups: a channel of their own"
    shields = {p["n"]: (p.get("s"), p.get("sm")) for p in state_pawns}
    assert shields == {"Zer0": (60.0, 120.0), "Bullymong": (25.0, 50.0)}, shields  # properties / functions
    assert kinds == {"Zer0": "me", "Bullymong": "enemy"}, kinds
    print(f"  collector: level {level['name']!r} {level['status']}, pawns {kinds}")
    (player,) = json.loads(hub.latest("players"))["players"]
    (gun,) = player["equipped"]
    assert (player["n"], player["local"], player["cls"], player["inventory"]) == ("Zer0", True, "Assassin", "full"), player
    assert "clsRaw" not in player and player["char"] == "Zer0", player  # localized, via CharacterClassId
    assert player["xp"] == [7851, 8861], player["xp"]  # in this level / the level's size
    # (stats: [key, the card's value, the current one, extra] - the fake has no BaseValue twins: the current for both)
    assert gun["k"] == "weapon" and gun["stats"][0] == ["damage", 512, 512, 3] and gun["slot"] == 1, gun
    # the owner's bonuses: each stat's card value (its *BaseValue twin) and the current one (skills, class mod,
    # relic) - a faster reload (2.25 s -> 1.8 s), more damage (126.4 -> 354.3), the rest without a twin: the same
    boosted = ns(InstantHitDamage=354.3, InstantHitDamageBaseValue=126.4, ProjectilesPerShot=1.0, FireInterval=0.2,
                 FireIntervalBaseValue=0.25, ClipSize=16.0, ReloadTime=1.8, ReloadTimeBaseValue=2.25,
                 InstantHitDamageTypeDefinitions=[])
    from helios_tracker import inspector as stats_insp  # noqa: PLC0415 - (insp: imported further down)
    boosted_stats = {s[0]: s[1:3] for s in stats_insp._stats(boosted, "weapon")}
    assert boosted_stats == {"damage": [126, 354], "fireRate": [4.0, 5.0], "magazine": [16, 16], "reload": [2.25, 1.8]}, \
        ("the card's value, then with the owner's bonuses", boosted_stats)
    assert (gun["type"], gun["maker"]) == ("Sub-Machine Gun", "Hyperion+"), gun
    parts = {slot: (name, group, text) for slot, name, group, text in gun["parts"]}
    assert parts["Barrel"] == ("SMG_Barrel_Hyperion", "Barrel", "") and parts["Title"][2] == "Bitch", parts
    # its Gibbed code: the game's serial, unique id cleared, check written, trailing 0xFF dropped (decoded by Gibbed's
    # format: the Law, all its parts - tools/probes/probe_serial2.txt); the Pre-Sequel's prefix; none in Assault on Dragon
    # Keep (no Gibbed editor), nor for a serial not full, nor without one (the fake shield)
    law_code = "BL2(hwAAAADNoQCHRwJABoFAQsOIhRENIwHG/////9Iw/v9Pw4hAgg3j)"
    assert gun["gib"] == law_code, gun.get("gib")
    from helios_tracker import games  # noqa: PLC0415
    games.GAME = games.make_profile("TPS")
    assert stats_insp.gibbed_code(weapon) == "BLOZ" + law_code.removeprefix("BL2"), stats_insp.gibbed_code(weapon)
    games.GAME = games.make_profile("AoDK")
    assert stats_insp.gibbed_code(weapon) == "", "no Gibbed editor for Assault on Dragon Keep"
    games.GAME = games.make_profile("BL2")
    skin_serial = ns(State=serial_state.SNS_Full, Buffer=tuple(bytes.fromhex(  # a BanditTech skin's: 16 bytes left
        "07a3123038ffff0021014208e0ff04c2" + "ff" * 24)))
    assert stats_insp.gibbed_code(ns(CreateSerialNumber=lambda: skin_serial)) == "BL2(BwAAAADUWgAhAUII4P8Ewg==)"
    assert stats_insp.gibbed_code(ns(CreateSerialNumber=lambda: ns(State=serial_state.SNS_Empty, Buffer=(255,) * 40))) == ""
    assert stats_insp.gibbed_code(shield) == "", "no serial: no code"
    (obj,) = json.loads(hub.latest("objects"))["objects"]
    assert obj["n"] == "Incendiary Barrel" and "raw" not in obj and obj["d"] == "IO_FireBarrel", obj
    # no balance name, no target name: its definition's map hover header (the Pre-Sequel's oxygen source - it came out
    # "Oxygen Cracks ?", its definition's name)
    oxygen_io = ns(**{**vars(barrel), "_get_address": lambda: 0x5F0, "BalanceDefinitionState": None,
                      "InteractiveObjectDefinition": ns(Name="IO_OxygenCracks", StatusMenuMapInfoBoxHeader="Oxygen Source",
                                                        _path_name=lambda: "GD_Co_AirDome.InteractiveObjects.IO_OxygenCracks")})
    oxygen_rec = col.Collector._object_record(oxygen_io)
    assert oxygen_rec["n"] == "Oxygen Source" and "raw" not in oxygen_rec, oxygen_rec
    # a map exit (a LevelTravelStation): where it leads, the game's words - its header only says "Map Exit" (the user)
    exit_io = ns(**{**vars(oxygen_io), "_get_address": lambda: 0x5F1, "LevelTravelMapDisplayName": "Exit to %s",
                    "TravelDefinition": ns(DestinationStationDefinition=ns(DisplayName="Frostburn Canyon")),
                    "InteractiveObjectDefinition": ns(Name="LevelTravelMachine", StatusMenuMapInfoBoxHeader="Map Exit",
                                                      _path_name=lambda: "GD_GameSystemMachines.InteractiveObjects.LevelTravelMachine")})
    # out of sight: hidden, or every mesh of it hidden in game (BL1's T.K.'s Food once picked up - its actor not hidden)
    seen_mesh = lambda hidden: ns(Class=ns(Name="StaticMeshComponent"), HiddenGame=hidden)  # noqa: E731
    seen_cyl = ns(Class=ns(Name="CylinderComponent"), HiddenGame=True)
    assert col.Collector._out_of_sight(ns(bHidden=False, Components=[seen_cyl, seen_mesh(True)])), "its mesh hidden"
    assert not col.Collector._out_of_sight(ns(bHidden=False, Components=[seen_cyl, seen_mesh(False)])), "its mesh shown"
    assert not col.Collector._out_of_sight(ns(bHidden=False, Components=[seen_cyl])), "no mesh: as its actor"
    assert col.Collector._out_of_sight(ns(bHidden=True, Components=[]))
    exit_rec = col.Collector._object_record(exit_io)
    assert exit_rec["n"] == "Exit to Frostburn Canyon" and "raw" not in exit_rec, exit_rec
    # a boss: the boss bar's pawn (GRI.BossPawn while bHasBossBar - Deadlift: its AI class has no bBoss), kept for the level
    boss_gri = ns(bHasBossBar=False, BossPawn=ns(_get_address=lambda: 0xB055))
    c._note_boss(ns(GRI=boss_gri))
    assert (c.level_id, 0xB055) not in c._boss_pawns, "no boss bar: no boss"
    boss_gri.bHasBossBar = True
    c._info[0xB055] = {"i": "b055", "k": "enemy", "n": "Deadlift"}
    c._note_boss(ns(GRI=boss_gri))
    assert (c.level_id, 0xB055) in c._boss_pawns and c._info[0xB055].get("boss") == 1, ("the boss bar's pawn", c._info[0xB055])
    c._info.pop(0xB055)
    # the areas: the game's names (none for a fog of war only one), the ones uncovered (pc.DiscoveredWorldAreas)
    areas = json.loads(hub.latest("areas"))["areas"]
    assert areas == [{"k": "southernshelf_pwda_4", "x": 100, "y": -200, "z": 30, "r": 4644, "n": "Wreck Of The Ice Sickle"},
                     {"k": "southernshelf_pwda_3", "x": 100, "y": -200, "z": 30, "r": 5908}], areas
    real_get_pc = col.get_pc
    # listed = discovered (tools/probes/probe_fog.txt: HasBeenUncovered False on every entry, visited ones too)
    col.get_pc = lambda **k: ns(DiscoveredWorldAreas=[ns(DiscoveryName="SouthernShelf_PWDA_3", HasBeenUncovered=False),
                                                      ns(DiscoveryName="GLACIAL_PWDA_4", HasBeenUncovered=False)],
                                FullyExploredAreas=["Glacial_P"])
    c._publish_areas()
    msg = json.loads(hub.latest("areas"))
    assert [a.get("u") for a in msg["areas"]] == [None, 1] and "full" not in msg, ("discovered: listed, by short name", msg)
    assert msg["seen"] == [], ("the fog pieces discovered: none of Sanctuary's", msg["seen"])
    col.get_pc = lambda **k: ns(DiscoveredWorldAreas=[ns(DiscoveryName="SANCTUARY_PWDA_0")], FullyExploredAreas=[])
    c._publish_areas()
    msg = json.loads(hub.latest("areas"))
    assert msg["seen"] == ["sanctuary_pwda_0"], ("a fog piece discovered, its actor loaded or not", msg["seen"])
    col.get_pc = lambda **k: ns(DiscoveredWorldAreas=[], FullyExploredAreas=[level["map"].upper()])
    c._publish_areas()
    msg = json.loads(hub.latest("areas"))
    assert msg.get("full") == 1 and all(a.get("u") for a in msg["areas"]), ("a fully explored map: every area", msg)
    col.get_pc = real_get_pc
    # A skill's stats (tools/probes/probe_skill_stats2.txt): GetSkillEffectPresentations(grade, ctrl, out lines) -> the
    # game's text, value, display flags; cached per (skill, grade, player level)
    from helios_tracker import inspector as insp  # noqa: PLC0415

    # Pickup amounts (amounts.py: the tooltip's "$ 22", "18 rounds"), worked out from the definitions as the game has
    # them (tools/probes/probe_pickup_amounts2.txt): cash - its external BaseCredits slot, 10 x 1.25 x 1.12^ExpLevel (its own
    # effect: scale 0); ammo - AmmoAmount (36 in playthrough 2, else 18) x the co-op sharing share (0.5 if cloned for it)
    import enum  # noqa: PLC0415

    from helios_tracker.amounts import pickup_amount  # noqa: PLC0415

    class AmtMod(enum.IntEnum):
        MT_Scale = 0
        MT_PreAdd = 1
        MT_PostAdd = 2

    class AmtOp(enum.IntEnum):
        OPERATOR_EqualTo = 0

    def amt_data(const=0.0, scale=1.0, attr=None, init=None):  # noqa: ANN001, ANN202
        return ns(BaseValueConstant=const, BaseValueScaleConstant=scale, BaseValueAttribute=attr, InitializationDefinition=init)

    def amt_attr(resolver_class, **fields):  # noqa: ANN001, ANN003, ANN202
        return ns(Class=ns(Name="AttributeDefinition"), ValueResolverChain=[ns(Class=ns(Name=resolver_class), **fields)])

    def amt_formula(mult, level, power, offset):  # noqa: ANN001, ANN202
        return ns(RandomVariance=ns(bEnabled=False), ConditionalInitialization=ns(bEnabled=False),
                  ValueFormula=ns(bEnabled=True, Multiplier=mult, Level=level, Power=power, Offset=offset))

    def amt_if(attr, const, then, default):  # noqa: ANN001, ANN202
        return ns(bEnabled=True, DefaultBaseValue=default, ConditionalExpressionList=[ns(BaseValueIfTrue=then, Expressions=[
            ns(AttributeOperand1=attr, ComparisonOperator=AmtOp.OPERATOR_EqualTo, AttributeOperand2=None, ConstantOperand2=const)])])

    cash_calc = amt_formula(amt_data(1.0, attr=amt_attr("ConstantAttributeValueResolver", ConstantValue=1.25)),
                            amt_data(attr=amt_attr("ConstantAttributeValueResolver", ConstantValue=1.12)),
                            amt_data(1.0, attr=amt_attr("ObjectPropertyAttributeValueResolver", PropertyName="ExpLevel")), amt_data())
    cash_slot_attr = amt_attr("AttributeSlotEffectAttributeValueResolver", SlotName="BaseCredits")
    cash_def = ns(ExternalAttributeEffects=[ns(ModifierType=AmtMod.MT_PreAdd, BaseModifierValue=amt_data(0.0, 0.0, attr=cash_slot_attr))],
                  AttributeSlotEffects=[ns(SlotName="BaseCredits", bExternalSlot=True, ModifierType=AmtMod.MT_PostAdd,
                                           BaseModifierValue=amt_data(0.0, 10.0, init=cash_calc), PerGradeUpgrade=amt_data(0.0, 0.1, init=cash_calc))],
                  AttributeSlotBaseGrade=amt_data(1.0), AttributeSlotUpgrades=[ns(SlotName="BaseCredits", GradeIncrease=0)])
    cash_inv = ns(ExpLevel=5, DefinitionData=ns(ItemDefinition=cash_def))
    assert pickup_amount(cash_inv, 1) == 23, ("cash: 22.03, rounded up as the game credits it", pickup_amount(cash_inv, 1))
    playthrough_attr = amt_attr("PlayThroughCountAttributeValueResolver", IncludePlaythroughThree=0)
    ammo_amount = amt_attr("ConditionalAttributeValueResolver", ValueExpressions=amt_if(playthrough_attr, 2.0, amt_data(36.0), amt_data(18.0)))
    shared_attr = amt_attr("ObjectPropertyAttributeValueResolver", PropertyName="ClonedForSharing")
    ammo_share = ns(RandomVariance=ns(bEnabled=False), ValueFormula=ns(bEnabled=False), ConditionalInitialization=amt_if(
        shared_attr, 1.0, amt_data(1.0, attr=amt_attr("ConstantAttributeValueResolver", ConstantValue=0.5)), amt_data(1.0)))
    ammo_def = ns(ExternalAttributeEffects=[ns(ModifierType=AmtMod.MT_PostAdd, BaseModifierValue=amt_data(init=amt_formula(
        amt_data(attr=ammo_amount), amt_data(init=ammo_share), amt_data(1.0), amt_data())))], AttributeSlotEffects=[])
    ammo_inv = ns(ExpLevel=6, ClonedForSharing=0.0, DefinitionData=ns(ItemDefinition=ammo_def))
    ammo_amounts = [pickup_amount(ammo_inv, 1), pickup_amount(ammo_inv, 2), pickup_amount(ammo_inv, 3)]
    assert ammo_amounts == [18, 36, 36], ("ammo by playthrough (the third counts as 2)", ammo_amounts)
    ammo_inv.ClonedForSharing = 1.0
    assert pickup_amount(ammo_inv, 1) == 9, ("co-op: a share", pickup_amount(ammo_inv, 1))
    assert pickup_amount(ammo_inv, 0) is None, "no playthrough known: no amount"

    # Item records by the item object (inspector._ItemCache: the backpack's, gear on the ground's - dropped / picked up,
    # the same object, the same record): kept while it lives, not its record any more once destroyed (its WeakPointer
    # dead - even with another object at its address since), swept then
    cache_inv = ns(_get_address=lambda: 0x7700, Class=ns(Name="WillowWeapon"))
    item_cache = insp._ItemCache()
    cache_rec = item_cache.put(cache_inv, {"i": "7700", "n": "Gun"})
    assert item_cache.get(cache_inv) is cache_rec, "kept while it lives"
    next(iter(item_cache._entries.values()))[0].o = None  # (destroyed: its WeakPointer dead)
    assert item_cache.get(cache_inv) is None, "destroyed: not its record any more"
    item_cache.sweep()
    assert not item_cache._entries, "destroyed: swept"
    assert insp.is_gear(ns(Class=ns(Name="WillowShield", SuperField=None))), "a shield: gear (its card on the ground)"
    assert not insp.is_gear(ns(Class=ns(Name="WillowUsableItem", SuperField=None))), "ammo, cash: not gear"

    calls = []

    def presentations(grade, ctrl, out):  # noqa: ANN001, ANN202
        calls.append(grade)
        import enum  # noqa: PLC0415

        class Rounding(enum.IntEnum):  # (int-based like the game's)
            ATTRROUNDING_IntRound = 0
            ATTRROUNDING_Float = 1

        class Sign(enum.IntEnum):
            SIGNSTYLE_AsIs = 0
            SIGNSTYLE_Positive = 1
        pres = ns(Description="Gun Damage: $NUMBER$", bDisplayAsPercentage=True, bDisplayPercentAsFloat=False,
                  bDisplayAsInverse=False, bDontDisplayNumber=False, bDontDisplayPlusSign=False, SignStyle=Sign.SIGNSTYLE_AsIs,
                  RoundingMode=Rounding.ATTRROUNDING_Float, FloatPrecision=1, Prefix="", Suffix="")
        return (Ellipsis, [ns(AttributePresentation=pres, ModifierValue=0.06 * grade, bShouldDisplay=True),
                           ns(AttributePresentation=pres, ModifierValue=1.0, bShouldDisplay=False)])
    onslaught = ns(_get_address=lambda: 0x5A11, GetSkillEffectPresentations=presentations)
    stat_ctrl = ns(PlayerReplicationInfo=ns(ExpLevel=30))
    fx = insp._skill_stats(onslaught, stat_ctrl, 2)
    assert fx == [{"d": "Gun Damage: $NUMBER$", "v": 0.12, "pct": 1, "fl": 1, "fp": 1}], fx
    assert insp._skill_stats(onslaught, stat_ctrl, 2) == fx and calls == [2], ("cached", calls)
    # An item card's lines (tools/probes/probe_weapon_card.txt): WeaponCardModifierStats, the same entries; a name part's red
    # (tools/probes/probe_weapon_card2.txt: the text from the Description, NoConstraintText or Prefix / Suffix; the colour
    # from TextColor; a line tied to an attribute: its current value on the weapon, by its resolver's property)
    def pres(text, colour=(255, 255, 255), no_number=True, **more):  # noqa: ANN001, ANN202
        return ns(Description=text, NoConstraintText=more.get("nc", ""), bDisplayAsPercentage=False, bDisplayPercentAsFloat=False,
                  bDisplayAsInverse=False, bDontDisplayNumber=no_number, bDontDisplayPlusSign=True, SignStyle="SIGNSTYLE_AsIs",
                  RoundingMode="ATTRROUNDING_IntRound", FloatPrecision=1, Prefix=more.get("pre", ""), Suffix=more.get("suf", ""),
                  bEnableTextColor=True, TextColor=ns(R=colour[0], G=colour[1], B=colour[2]), Attribute=more.get("attr"))
    shot_cost = ns(ValueResolverChain=[ns(PropertyName="ShotCost")])
    # (its element's line: its damage type's own WeaponCardPresentations - marked "el")
    vs_shields = pres("Highly effective vs Shields.", colour=(0, 100, 255))
    vs_shields._get_address = lambda: 0xE1E
    card_gun = ns(ShotCost=2.0, InstantHitDamageTypeDefinitions=[ns(WeaponCardPresentations=[vs_shields])], WeaponCardModifierStats=[
        ns(AttributePresentation=pres("High elemental effect chance."), ModifierValue=0.0, bShouldDisplay=True),
        ns(AttributePresentation=pres("", no_number=False, pre="Consumes [skill]", suf="ammo[-skill] per shot.", attr=shot_cost),
           ModifierValue=1.0, bShouldDisplay=True),
        ns(AttributePresentation=pres("", nc="Deals [skill]bonus elemental damage[-skill]."), ModifierValue=0.0, bShouldDisplay=True),
        ns(AttributePresentation=vs_shields, ModifierValue=0.0, bShouldDisplay=True)])
    card_lines = insp._card_lines(card_gun, "weapon")
    # its elemental chance (tools/probes/probe_element_chance.txt): 20 (shock's base) x 0.6 x 1.4 = 16.8 %; with skills (1.496): 17.95 %
    import enum  # noqa: PLC0415

    class Surface(enum.IntEnum):  # (like the game's: int-based - str() gives the number on Python 3.11+)
        DMGSURFACE_Generic = 0
        DMGSURFACE_Flesh = 1
    shock = ns(_get_address=lambda: 0x5E0C, DamageSurfaceChanceModifiers=[
        ns(SurfaceType=Surface.DMGSURFACE_Flesh, BaseChance=ns(BaseValueConstant=99.0, BaseValueAttribute=None, BaseValueScaleConstant=1.0)),
        ns(SurfaceType=Surface.DMGSURFACE_Generic, BaseChance=ns(BaseValueConstant=20.0, BaseValueAttribute=None, BaseValueScaleConstant=1.0))])
    aegis = ns(Class=ns(Name="WillowWeapon"), InstantHitDamageTypeDefinitions=[ns(StatusEffect=shock)],
               BaseStatusEffectChanceModifier=0.6, BaseStatusEffectChanceModifierBaseValue=0.6,
               StatusEffectChanceModifier=1.496, StatusEffectChanceModifierBaseValue=1.4)
    assert insp._element_chance(aegis) == [16.8, 17.95], insp._element_chance(aegis)
    # its element's name: the game's localization (WillowMenu.int [DamageTypes]), keyed by the DamageType enum's name
    class DamageKind(enum.IntEnum):  # (int-based like the game's)
        DAMAGE_TYPE_Normal = 0
        DAMAGE_TYPE_Shock = 1
    localized = []
    loc_ctrl = ns(Localize=lambda section, key, package: localized.append((section, key, package)) or "shock")
    assert insp._element_name(ns(DamageType=DamageKind.DAMAGE_TYPE_Shock), loc_ctrl) == "shock"
    assert insp._element_name(ns(DamageType=DamageKind.DAMAGE_TYPE_Shock), loc_ctrl) == "shock" and localized == [
        ("DamageTypes", "Shock", "WillowMenu")], ("looked up once", localized)
    missing = ns(Localize=lambda *a: "?INT?WillowMenu.DamageTypes.Normal?")
    assert insp._element_name(ns(DamageType=DamageKind.DAMAGE_TYPE_Normal), missing) == "", "a missing entry: no name"
    # A card line's localization reference ("$WillowGame.ItemCardPresentationDescriptions.CharacterHead": a head's
    # card, seen raw in game): the game's text, looked up once; a missing one: no text, never the reference
    insp_get_pc, loc_calls = insp.get_pc, []
    insp.get_pc = lambda: ns(Localize=lambda section, key, package: loc_calls.append((package, section, key))
                             or ("Unlocks this head." if key == "CharacterHead" else f"?INT?{package}.{section}.{key}?"))
    head_ref = "$WillowGame.ItemCardPresentationDescriptions.CharacterHead"
    assert insp._game_text(head_ref) == "Unlocks this head." == insp._game_text(head_ref) and loc_calls == [
        ("WillowGame", "ItemCardPresentationDescriptions", "CharacterHead")], loc_calls
    assert insp._game_text("$WillowGame.Nope.Missing") == "" and insp._game_text("Deals $5 damage") == "Deals $5 damage"
    insp.get_pc = insp_get_pc
    assert [(ln["d"], ln.get("cur"), ln.get("col"), ln.get("el")) for ln in card_lines] == [
        ("High elemental effect chance.", None, None, None), ("", 2.0, None, None),
        ("Deals [skill]bonus elemental damage[-skill].", None, None, None),
        ("Highly effective vs Shields.", None, "#0064ff", 1)], card_lines
    # A class mod's bonus ranks (tools/probes/probe_skill_bonus.txt): its card's lines whose presentation is a skill's
    def card(path, value):  # noqa: ANN001, ANN202
        return ns(AttributePresentation=ns(_path_name=lambda: path, Name=path.rpartition(".")[2]), ModifierValue=value)
    cmod = ns(ItemCardModifierStats=[card("GD_AttributePresentation.Skills_Soldier.AttrPresent_Steady", 2.02),
                                     card("GD_AttributePresentation.Skills_Soldier.AttrPresent_Pressure", 3.04),
                                     card("GD_AttributePresentation.Weapons.AttrPresent_WeaponReloadSpeed", -0.235)],
              Inventory=None)
    relic = ns(ItemCardModifierStats=[card("GD_AttributePresentation.Skills_Soldier.AttrPresent_Steady", 1.0)], Inventory=cmod)
    real_item_name = insp.item_name
    insp.item_name = lambda i: "Resolute Rifleman" if i is cmod else "Relic"
    assert insp._skill_bonuses(ns(InvManager=ns(ItemChain=relic))) == {
        "steady": [[1, "Relic"], [2, "Resolute Rifleman"]], "pressure": [[3, "Resolute Rifleman"]]}, "bonus ranks, per item"
    insp.item_name = real_item_name
    # A cutscene video (tools/probes/probe_cutscene_watch.txt): told at once with its length; the first frame
    # over a second later clears it; another player's controller's: ignored
    me_pc = ns(_get_address=lambda: 0xC0)
    col.get_pc = lambda **k: me_pc
    real_length = col.movie_length
    col.movie_length = lambda name: 65.0 if name == "Orchid_Intro" else None
    vhub = Hub()
    vc = col.Collector(vhub)
    vc._next_level_check = float("inf")  # (only the video part of its tick)
    vc.movie_started(ns(_get_address=lambda: 0xC1), "Orchid_Intro", False)
    assert "cutscene" not in vhub._channels, "another player's video"
    vc.movie_started(me_pc, "Orchid_Intro", False)
    video = json.loads(vhub.latest("cutscene"))
    assert video["video"] == video["name"] == "Orchid_Intro" and video["len"] == 65.0 and video["at"] > 0, video
    t_now = time.monotonic()
    vc.tick(t_now)
    vc.tick(t_now + 1.5)  # frames still going on after its start (a fade): still playing
    assert json.loads(vhub.latest("cutscene")).get("video"), "cleared by the frames around its start"
    vc.tick(t_now + 60.0)  # frames again after a gap: it's over (or skipped)
    assert json.loads(vhub.latest("cutscene")) == {}, "over: cleared"
    vc.movie_started(me_pc, "Orchid_Intro", False)
    t_now = time.monotonic()
    for k in range(80):  # the frames never stopped: over at its length + 5 s
        vc.tick(t_now + k)
    assert json.loads(vhub.latest("cutscene")) == {}, "over past its length"
    col.movie_length = real_length
    col.get_pc = real_get_pc
    # An in-engine cutscene: the script's cinematic mode; elapsed counted from its start (not a Matinee's
    # Position: some started before it), its length = elapsed + the most its Matinees still play; the day /
    # night cycle's (looping) left out
    interp = ns(Name="SeqAct_Interp_3", Class=ns(Name="SeqAct_Interp"), bIsPlaying=True, bLooping=False, PlayRate=1.0,
                Position=14.0, VariableLinks=[ns(LinkedVariables=[ns(InterpLength=30.0)])])  # 14 s in already: 16 s left
    daynight = ns(Name="WillowSeqAct_DayNightCycle_0", Class=ns(Name="WillowSeqAct_DayNightCycle"), bIsPlaying=True,
                  bLooping=True, PlayRate=0.1, Position=0.5, VariableLinks=[ns(LinkedVariables=[ns(InterpLength=600.0)])])
    real_find_all = col.unrealsdk.find_all
    col.unrealsdk.find_all = lambda cls, exact=True: [daynight, interp] if cls == "SeqAct_Interp" else []
    real_weak = col.WeakPointer
    col.WeakPointer = lambda o: (lambda: o)
    shub = Hub()
    sc = col.Collector(shub)
    scene_pc = ns(bCinematicMode=True, bKismetEnabledCinematicMode=False, MyWillowPawn=ns(bViewingStatusMenu=False))
    scene_wi = ns(Pauser=None)
    sc._check_scene(scene_pc, scene_wi, 10.0)
    assert "cutscene" not in shub._channels, "a cinematic mode not from the script (after a video, a respawn)"
    scene_pc.bKismetEnabledCinematicMode = True
    sc._check_scene(scene_pc, scene_wi, 10.0)
    scene = json.loads(shub.latest("cutscene"))
    assert scene["scene"] == 1 and scene["len"] == 16.0 and abs(time.time() - scene["at"]) < 1, ("from 0, 16 s long (its Matinee's rest)", scene)
    interp.Position = 15.0
    sc._check_scene(scene_pc, scene_wi, 11.0)  # 1 s in, the Matinee moving
    # the game paused: sent as paused where it is (the page's count stopped); resumed: from there
    scene_wi.Pauser = ns(PlayerName="me")
    sc._check_scene(scene_pc, scene_wi, 11.1)
    scene = json.loads(shub.latest("cutscene"))
    assert scene.get("paused") == 1 and abs(scene["pos"] - 1.0) < 0.01 and scene["len"] == 16.0, ("paused: held at 1 s", scene)
    assert scene["name"] == "SeqAct_Interp_3", ("its Matinee's name (no comment, no sequence)", scene)
    sc._check_scene(scene_pc, scene_wi, 20.0)  # 9 s paused: not counted
    scene_wi.Pauser = None
    interp.Position = 15.2
    sc._check_scene(scene_pc, scene_wi, 20.2)
    scene = json.loads(shub.latest("cutscene"))
    assert "paused" not in scene and abs(time.time() - scene["at"] - 1.2) < 0.5, ("resumed from 1.2 s, the pause not counted", scene)
    # its Matinee stuck (not moving, the game not paused): paused too
    sc._check_scene(scene_pc, scene_wi, 21.0)
    assert json.loads(shub.latest("cutscene")).get("paused") == 1, "a Matinee not moving: paused"
    # a later, longer shot: the length grows, elapsed goes on (no jump)
    interp.Position = 16.0
    later_shot = ns(Name="SeqAct_Interp_4", Class=ns(Name="SeqAct_Interp"), bIsPlaying=True, bLooping=False, PlayRate=1.0,
               Position=0.0, VariableLinks=[ns(LinkedVariables=[ns(InterpLength=40.0)])])
    sc._interps = (sc.level_id, [lambda: interp, lambda: later_shot])
    sc._check_scene(scene_pc, scene_wi, 22.5)
    scene = json.loads(shub.latest("cutscene"))
    assert scene["len"] > 40 and "paused" not in scene, ("a longer shot: its length grown", scene)
    scene_pc.bCinematicMode = False
    sc._check_scene(scene_pc, scene_wi, 23.0)
    assert json.loads(shub.latest("cutscene")) == {}, "over: cleared"
    # the main menu: its background runs in the script's cinematic mode too - never a cutscene
    sc._level = {"map": "MenuMap"}
    scene_pc.bCinematicMode = True
    sc._check_scene(scene_pc, scene_wi, 24.0)
    assert json.loads(shub.latest("cutscene")) == {}, "the main menu's background shown as a cutscene"
    # the character creation's idle: in a level, no character in the world yet
    sc._level = {"map": "Stockade_P"}
    scene_pc.MyWillowPawn = None
    sc._check_scene(scene_pc, scene_wi, 25.0)
    assert json.loads(shub.latest("cutscene")) == {}, "the character creation's idle shown as a cutscene"
    col.unrealsdk.find_all = real_find_all
    col.WeakPointer = real_weak
    col.unrealsdk.find_all = real_find_all
    tank = ns(**{**vars(barrel), "Name": "WillowInteractiveObject_9", "_get_address": lambda: 0x501,
                 "BalanceDefinitionState": ns(BalanceDefinition=ns(DefaultDisplayName="Explosive Gas Tank"))})
    c.object_spawned(tank)  # an area activated: the hook, no scan
    chest = ns(**{**vars(barrel), "Name": "WillowInteractiveObject_10", "_get_address": lambda: 0x502,
                  "Loot": [ns(ItemAttachments=[ns(ItemPool=ns(Name="Pool_Money_1"))])],
                  "SimpleAnimState": 4, "bCanBeUsed": (1, 0),
                  "BalanceDefinitionState": ns(BalanceDefinition=ns(
                      _get_address=lambda: 0x503, DefaultDisplayName="Treasure Chest", DefaultLoot=[],
                      DefaultIncludedLootLists=[ns(Name="EpicChestRedLoot", LootData=[
                          ns(ItemAttachments=[ns(ItemPool=ns(Name="Pool_GunsAndGear"))] * 4)])]))})
    c.object_spawned(chest)
    c.tick(1001.3)
    names = [o["n"] for o in json.loads(hub.latest("objects"))["objects"]]
    assert names == ["Incendiary Barrel", "Explosive Gas Tank", "Treasure Chest"], names
    chest.bCanBeUsed = (0, 0)  # opened: use off at once (the anim state only follows)
    c.object_usability_changed(chest)  # the SetUsability hook
    c.tick(1001.35)
    looted = {o["n"]: (o.get("lootable"), o.get("looted")) for o in json.loads(hub.latest("objects"))["objects"]}
    assert looted["Treasure Chest"] == (1, 1) and looted["Incendiary Barrel"] == (None, None), looted
    contents = {o["n"]: o.get("loot") for o in json.loads(hub.latest("objects"))["objects"]}
    objs = {o["n"]: o for o in json.loads(hub.latest("objects"))["objects"]}
    chest_rec = objs["Treasure Chest"]
    assert (chest_rec["loot"], chest_rec["slots"], chest_rec["lists"]) == (["Pool_GunsAndGear"], 4, ["EpicChestRedLoot"]), chest_rec
    assert "loot" not in objs["Incendiary Barrel"], objs["Incendiary Barrel"]
    c.object_destroyed(barrel)  # it exploded
    c.tick(1001.4)
    names = [o["n"] for o in json.loads(hub.latest("objects"))["objects"]]
    assert names == ["Explosive Gas Tank", "Treasure Chest"], names
    # Vending machines (tools/probes/probe_vending.txt): a machine's 30-slot stock (the items, then None), its item of the
    # day, the price the machine asks; the restock timer from WorldInfo.Game (the host) - sent when it drifts
    from helios_tracker import shops as vend_mod  # noqa: PLC0415
    vend_shop_type = enum.IntEnum("EShopType", ["SType_Weapons", "SType_Items", "SType_Health", "SType_BlackMarket"], start=0)
    vend_currency = enum.IntEnum("ECurrencyType", ["CURRENCY_Credits", "CURRENCY_Eridium"], start=0)
    vend_gun = ns(**{**vars(weapon), "Name": "WillowWeapon_27", "_get_address": lambda: 0x520})
    vend_feat = ns(**{**vars(shield), "Name": "WillowShield_14", "_get_address": lambda: 0x521})
    vend_prices = {0x520: 669, 0x521: 766, 0x522: 120, 0x523: 10}
    # shop ammo (always sold: a price list - "basics" - not an item card), by the pickups' rule (util.pickup_kind)
    vend_ammo = ns(Name="WillowUsableItem_23", _get_address=lambda: 0x523, Class=ns(Name="WillowUsableItem", SuperField=None),
                   GetShortHumanReadableName=lambda: "SMG Ammo", DefinitionData=ns(ItemDefinition=ns(
                       _get_address=lambda: 0x524, ItemName="SMG Ammo", Presentation=ns(Name="WeaponAmmo_SMG"))))
    vend_machine = ns(**{**vars(barrel), "Name": "WillowVendingMachine_3", "_get_address": lambda: 0x510,
                         "Class": ns(Name="WillowVendingMachine", SuperField=ns(Name="WillowVendingMachineBase", SuperField=None)),
                         "ShopType": vend_shop_type.SType_Weapons, "FormOfCurrency": vend_currency.CURRENCY_Credits,
                         "ShopInventory": [vend_gun, vend_ammo, None], "FeaturedItem": vend_feat,
                         "GetSellingPriceForInventory": lambda inv, pc, n: vend_prices[inv._get_address()]})
    vend_game = ns(SecondsUntilShopsReset=1169.0, ShopTimerRate=1.0)
    vend_world = ns(Game=vend_game)
    vend_saved = (col.ENGINE, getattr(vend_mod.unrealsdk, "find_class", None))
    col.ENGINE = ns(GetCurrentWorldInfo=lambda: vend_world)
    vend_mod.unrealsdk.find_class = lambda name: ns(ClassDefaultObject=ns(WeaponsShopTitle="Marcus Munitions"))
    vend_earl = ns(**{**vars(vend_machine), "Name": "WillowVendingMachineBlackMarket_0", "_get_address": lambda: 0x511,
                      "ShopType": vend_shop_type.SType_BlackMarket, "ShopInventory": [], "FeaturedItem": None})
    c.object_spawned(vend_machine)  # (the hook: noted as a machine; the scan does the same)
    c.object_spawned(vend_earl)  # Crazy Earl: left out of the list
    assert json.loads(hub.latest("shops"))["machines"] == [], "a stock before any machine"  # (the ticks: none yet)
    vend_empty = hub._channels["shops"][0]
    vend_mod.BUILD_SECONDS, vend_budget = -1.0, vend_mod.BUILD_SECONDS  # no time for item records this pass
    c._publish_shops(2000.0)
    assert c._shops.pending and hub._channels["shops"][0] == vend_empty and c._next_shops == 2000.0 + col.SHOPS_RETRY, (
        "a half-built stock sent")
    vend_mod.BUILD_SECONDS = vend_budget
    c._publish_shops(2000.1)
    (vend_rec,) = json.loads(hub.latest("shops"))["machines"]
    assert (vend_rec["n"], vend_rec["k"], "raw" in vend_rec, "cur" in vend_rec) == ("Marcus Munitions", "weapons", False, False), vend_rec
    # a machine's name: its map hover's first - its definition's StatusMenuMapInfoBoxHeader (the Pre-Sequel's ammo machine:
    # "Bullets Etc.", its menu title still BL2's "The Ammo Dump"); none: the menu's title (above)
    vend_hover = ns(InteractiveObjectDefinition=ns(StatusMenuMapInfoBoxHeader="Bullets Etc."))
    assert c._shops._name(vend_hover, "items") == "Bullets Etc.", "the map hover's name"
    assert c._shops._name(ns(InteractiveObjectDefinition=ns(StatusMenuMapInfoBoxHeader="")), "weapons") == "Marcus Munitions"
    # no name of the game's (BL1's machines: no map header, no shop titles): its definition's, as the map object's
    vend_mod.unrealsdk.find_class = lambda name: ns(ClassDefaultObject=ns(ItemsShopTitle=""))
    vend_nameless = ns(Class=ns(Name="WillowVendingMachine"), InteractiveObjectDefinition=ns(
        Name="InteractiveObj_VendingMachine_GrenadesAndAmmo", StatusMenuMapInfoBoxHeader=""))
    assert c._shops._named(vend_nameless, "other") == {"n": "VendingMachine GrenadesAndAmmo", "raw": 1}, c._shops._named(vend_nameless, "other")
    vend_mod.unrealsdk.find_class = lambda name: ns(ClassDefaultObject=ns(WeaponsShopTitle="Marcus Munitions"))
    assert [(it["n"], it["v"]) for it in vend_rec["items"]] == [("Unkempt Harold", 669)], vend_rec["items"]  # (the machine's price)
    assert vend_rec["basics"] == [{"n": "SMG Ammo", "k": "ammo", "v": 10}], vend_rec.get("basics")
    assert (vend_rec["feat"]["n"], vend_rec["feat"]["v"], vend_rec["feat"]["k"]) == ("Adaptive Shield", 766, "shield"), vend_rec["feat"]
    assert json.loads(hub.latest("shoptimer")) == {"level": c.level_id, "left": 1169.0, "rate": 1.0}
    vend_versions = (hub._channels["shops"][0], hub._channels["shoptimer"][0])
    vend_game.SecondsUntilShopsReset = 1159.0  # 10 s later, as counted: nothing to send
    c._publish_shops(2010.1)
    assert (hub._channels["shops"][0], hub._channels["shoptimer"][0]) == vend_versions, "sent again unchanged"
    vend_game.SecondsUntilShopsReset = 1100.0  # the page's count would be off: the timer again, not the stock
    c._publish_shops(2011.1)
    assert (hub._channels["shops"][0], hub.latest("shoptimer")) == (vend_versions[0], json.dumps(
        {"level": c.level_id, "left": 1100.0, "rate": 1.0}, separators=(",", ":"))), "a drifted timer not sent"
    # the game paused (WorldInfo.Pauser): its timer stands still - sent once, flagged; no resend while it holds
    vend_world.Pauser = ns(Name="PlayerReplicationInfo_0")
    c._publish_shops(2011.5)
    assert json.loads(hub.latest("shoptimer")) == {"level": c.level_id, "left": 1100.0, "rate": 1.0, "paused": 1}
    vend_paused_version = hub._channels["shoptimer"][0]
    c._publish_shops(2030.0)  # 18.5 s later, the game's count unchanged: the page's held too - nothing to send
    assert hub._channels["shoptimer"][0] == vend_paused_version, "a paused timer resent (the page's count went on)"
    vend_world.Pauser = None
    c._publish_shops(2031.0)  # unpaused: sent again, counting
    assert "paused" not in json.loads(hub.latest("shoptimer")) and hub._channels["shoptimer"][0] == vend_paused_version + 1
    vend_new = ns(**{**vars(vend_gun), "Name": "WillowWeapon_31", "_get_address": lambda: 0x522})
    vend_machine.ShopInventory = [vend_new, None]  # restocked: a new item, the timer back up
    vend_game.SecondsUntilShopsReset = 1200.0
    c._publish_shops(2012.1)
    (vend_rec,) = json.loads(hub.latest("shops"))["machines"]
    assert [it["v"] for it in vend_rec["items"]] == [120] and json.loads(hub.latest("shoptimer"))["left"] == 1200.0, vend_rec
    assert "basics" not in vend_rec, vend_rec  # (none left in that stock)
    assert (0x520, "WillowWeapon_27") not in c._shops._items, "a sold item's record kept"
    c.object_destroyed(vend_machine)
    c._publish_shops(2013.1)
    assert json.loads(hub.latest("shops"))["machines"] == [], "a destroyed machine still listed"
    col.ENGINE, vend_find_class = vend_saved
    if vend_find_class is None:
        del vend_mod.unrealsdk.find_class
    else:
        vend_mod.unrealsdk.find_class = vend_find_class
    print(f"  shops: {vend_rec['n']!r}, stock + item of the day with the machine's prices, the timer sent on drift / restock")
    # Loot odds (tools/probes/probe_loot_odds*.txt): the golden chest's configurations (Weight_* x a scale: 300 / 150 / 90 / 80 x 3
    # / 50), a pool's rarity sub-pools (common = the designer modifier x Weight_1_Common; a legendary one from stage 7),
    # a box's health weight (an AmmoDropWeight resolver x 500: its "if low on health" range)
    from helios_tracker import lootodds  # noqa: PLC0415
    def odds_data(const=0.0, scale=1.0, init=None, attr=None):  # an AttributeInitializationData
        return ns(BaseValueConstant=const, BaseValueScaleConstant=scale, InitializationDefinition=init, BaseValueAttribute=attr)
    odds_addr = iter(range(0x9000, 0x9999))
    def odds_weight(mult):  # a GD_Balance.Weighting.Weight_* (its formula: mult x 1^1 + 0)
        return ns(_get_address=lambda a=next(odds_addr): a, ValueFormula=ns(bEnabled=True, Multiplier=odds_data(mult),
                  Level=odds_data(1), Power=odds_data(1), Offset=odds_data(0)), ConditionalInitialization=ns(bEnabled=False),
                  RandomVariance=ns(bEnabled=False))
    odds_w = {n: odds_weight(m) for n, m in (("VeryCommon", 200), ("Common", 100), ("Uncommon", 10), ("Rare", 1), ("Legendary", 0.01))}
    odds_modifier = ns(_get_address=lambda: 0x9a00, Class=ns(Name="DesignerAttributeDefinition"), BaseValue=odds_data(1),
                       _path_name=lambda: "GD_Balance.Weighting.GearDrops_CommonWeightModifier")
    odds_rare_mod = ns(_get_address=lambda: 0x9a01, ValueFormula=ns(bEnabled=True, Multiplier=odds_data(0, attr=odds_modifier),
                       Level=odds_data(0, init=odds_w["Common"]), Power=odds_data(1), Offset=odds_data(0)),
                       ConditionalInitialization=ns(bEnabled=False), RandomVariance=ns(bEnabled=False))
    odds_stage7 = ns(_get_address=lambda: 0x9a02, Class=ns(Name="AttributeDefinition"),
                     ValueResolverChain=[ns(Class=ns(Name="ConstantAttributeValueResolver"), ConstantValue=7.0)])
    def odds_pool(name, entries, min_stage=None):
        return ns(Name=name, _path_name=lambda n=name: "GD_Itempools.WeaponPools." + n, BalancedItems=entries, MinGameStageRequirement=min_stage)
    odds_legendary = odds_pool("Pool_Weapons_Pistols_06_Legendary", [], odds_stage7)
    odds_pistols = odds_pool("Pool_Weapons_Pistols", [
        ns(ItmPoolDefinition=odds_pool("Pool_Weapons_Pistols_01_Common", []), InvBalanceDefinition=None, Probability=odds_data(1, init=odds_rare_mod)),
        ns(ItmPoolDefinition=odds_pool("Pool_Weapons_Pistols_02_Uncommon", []), InvBalanceDefinition=None, Probability=odds_data(1, init=odds_w["Uncommon"])),
        ns(ItmPoolDefinition=odds_legendary, InvBalanceDefinition=None, Probability=odds_data(1, init=odds_w["Legendary"]))])
    def odds_cfg(weight, pool, n=1):
        return ns(Weight=weight, ItemAttachments=[ns(ItemPool=pool)] * n)
    odds_long = odds_pool("Pool_EpicChestGolden_Weapons_LongGuns", [])
    odds_chest = lootodds.configs_odds([odds_cfg(odds_data(0, 1.5, odds_w["VeryCommon"]), odds_long, 2),
                                        odds_cfg(odds_data(0, 1.5, odds_w["Common"]), odds_pistols, 2),
                                        odds_cfg(odds_data(0, 0.9, odds_w["Common"]), odds_long),
                                        *[odds_cfg(odds_data(0, 0.8, odds_w["Common"]), odds_long)] * 3,
                                        odds_cfg(odds_data(0, 0.5, odds_w["Common"]), odds_long)], lootodds.POOLS)
    assert [round(o["p"], 1) for o in odds_chest] == [36.1, 18.1, 10.8, 9.6, 9.6, 9.6, 6.0], odds_chest
    assert odds_chest[0]["a"] == [["GD_Itempools.WeaponPools.Pool_EpicChestGolden_Weapons_LongGuns", 2]], odds_chest[0]
    odds_rows = {r["n"]: r for r in lootodds.POOLS["GD_Itempools.WeaponPools.Pool_Weapons_Pistols"]["e"]}
    assert round(odds_rows["Pool_Weapons_Pistols_01_Common"]["p"], 2) == round(100 / 110.01 * 100, 2), odds_rows  # (modifier 1 x 100)
    assert odds_rows["Pool_Weapons_Pistols_06_Legendary"]["min"] == 7 and "min" not in odds_rows["Pool_Weapons_Pistols_02_Uncommon"], odds_rows
    odds_health = ns(_get_address=lambda: 0x9a03, Class=ns(Name="AttributeDefinition"), ValueResolverChain=[ns(
        Class=ns(Name="AmmoDropWeightAttributeValueResolver"), Resource=ns(Name="Health"), AboveThresholdWeight=odds_data(0.03),
        MinBelowThresholdWeight=odds_data(0.1), MaxBelowThresholdWeight=odds_data(0.25))])
    odds_box = lootodds.configs_odds([odds_cfg(odds_data(0, 1, odds_w["VeryCommon"]), odds_long),
                                      odds_cfg(odds_data(1, 500, attr=odds_health), odds_long),
                                      odds_cfg(ns(BaseValueConstant=0, BaseValueScaleConstant=1, BaseValueAttribute=None,
                                                  InitializationDefinition=ns(_get_address=lambda: 0x9a04, ValueFormula=ns(bEnabled=False))), odds_long)],
                                     lootodds.POOLS)
    assert round(odds_box[1]["p"], 1) == round(15 / 215 * 100, 1) and odds_box[1]["c"] == "health", odds_box[1]  # usual: 0.03 x 500
    assert [round(x, 1) for x in odds_box[1]["lo"]] == [round(50 / 250 * 100, 1), round(125 / 325 * 100, 1)], odds_box[1]  # low: 0.1-0.25
    assert "p" not in odds_box[2], ("an unknown weight given a chance", odds_box[2])
    # the host's live designer attribute (tools/probes/probe_loot_odds3.txt: the common modifier 0.625, its base 1): every odds
    # worked out again with it - common gear 62.5, not 100
    odds_version = lootodds.version
    odds_world = ns(Game=ns(DesignerAttributes=[ns(DesignerAttributeDefinitionPathName="GD_Balance.Weighting.GearDrops_CommonWeightModifier",
                                                   Value=0.625)]))
    assert lootodds.refresh(odds_world) and lootodds.version == odds_version + 1 and not lootodds.POOLS, "a live value change kept stale odds"
    assert not lootodds.refresh(odds_world), "unchanged live values: odds forgotten anyway"
    lootodds.configs_odds([odds_cfg(odds_data(0, 1.5, odds_w["Common"]), odds_pistols)], lootodds.POOLS)
    odds_live = {r["n"]: r for r in lootodds.POOLS["GD_Itempools.WeaponPools.Pool_Weapons_Pistols"]["e"]}
    assert abs(odds_live["Pool_Weapons_Pistols_01_Common"]["p"] - 62.5 / 72.51 * 100) < 0.01, odds_live
    assert lootodds.refresh(ns(Game=None)), "a client (no game info): back to the base values"
    # a weight's condition, from the resource (D_Resources.*): health / oxygen by name, ammo by its group, another its name
    # (the Pre-Sequel's oxygen canisters read "if low on ammo" when "ammo" was the default)
    odds_conditions = [lootodds.condition_of(ns(Name=n, Outer=ns(Name=g))) for n, g in
                       (("Health", "D_Resources"), ("Oxygen", "D_Resources"), ("Ammo_Sniper_Rifle", "AmmoResources"), ("Shield", "D_Resources"))]
    assert odds_conditions == ["health", "oxygen", "ammo", "Shield"], odds_conditions
    # an item entry: the game's name for it (a usable item's ItemName, a balance's InventoryDefinition's); none: ""
    assert lootodds._item_text(ns(ItemName="Oxygen Canister")) == "Oxygen Canister"
    assert lootodds._item_text(ns(ItemName="", InventoryDefinition=ns(ItemName="Health Now!"))) == "Health Now!"
    assert lootodds._item_text(ns(InventoryDefinition=None)) == "", "a weapon's balance: no item name"
    print(f"  loot odds: the golden chest {[round(o['p']) for o in odds_chest]} %, health in a box ~{odds_box[1]['p']:.0f} % "
          f"(low on health ~{odds_box[1]['lo'][0]:.0f}-{odds_box[1]['lo'][1]:.0f} %), a legendary pool from Lv 7, the host's live common modifier")
    missions = json.loads(hub.latest("missions"))
    assert missions["tracked"] == {"n": "Ménage à Liar's Berg"}, missions
    obj_mk, giver = missions["markers"]  # the inactive objective is left out
    assert (obj_mk["k"], obj_mk["rad"], obj_mk["tracked"], obj_mk["objective"]) == (
        "objective", 2125, True, {"n": "Sécuriser la ville"}), obj_mk
    assert (giver["k"], giver["rad"], "objective" in giver, giver["by"]) == ("directive", 0, False, "703"), giver  # by: its NPC
    # The mission log: full pass (every entry, definitions cached), then the fast pass (the tracked /
    # active missions, every second) picks up progress
    def merged_log() -> dict:  # what the page builds: the definitions + the live part, by id
        defs = {m["i"]: m for m in json.loads(hub.latest("missiondefs"))["missions"]}
        live = json.loads(hub.latest("missionlog"))
        return {**live, "missions": [{**defs[m["i"]], **m} for m in live["missions"]]}
    log = merged_log()
    by_id = {m["i"]: m for m in log["missions"]}
    tracked = by_id["GD_Episode02.M_Ep2a_MoreGuns"]
    assert log["tracked"] == tracked["i"] and tracked["st"] == "Active" and tracked["plot"] == 1, log["tracked"]
    assert (tracked["p"], tracked["cur"], tracked["deps"]) == ([1, 3, 0], [1, 2], ["GD_Episode02.M_Ep2_Henchman"]), tracked
    assert [(o["n"], o["c"], o.get("opt")) for o in tracked["obj"]] == [
        ("Sécuriser la ville", 1, None), ("Tuer des bandits", 5, None), ("Bonus", 1, 1)], tracked["obj"]
    assert [by_id[k]["st"] for k in ("GD_Episode02.M_Ep2_Henchman", "GD_Z1_Side.M_Side")] == ["Complete", "NotStarted"], by_id
    assert tracked["area"] == "Southern Shelf" and "area" not in by_id["GD_Z1_Side.M_Side"], "mission area (TravelStation)"
    # where it is: its station's map, where to turn it in, and where its current step is done
    assert (tracked["map"], tracked["tin"]) == ("SouthernShelf_P", {"a": "Sanctuary", "map": "Sanctuary_P"}), tracked
    assert tracked["go"] == {"a": "Southern Shelf - Bay", "map": "SouthernShelf_P"}, ("current step's station", tracked.get("go"))
    assert "go" not in by_id["GD_Z1_Side.M_Side"] and "tin" not in by_id["GD_Z1_Side.M_Side"], "not picked up / no turn-in station"
    from helios_tracker import missions as mlog  # noqa: PLC0415

    # waiting on another mission's objective (MissionDefinition.ObjectiveDependency, EODS_Complete)
    dep_status = enum.Enum("EObjectiveDependencyStatus", ["EODS_Complete"], start=0)
    # (the objective: the tracked mission's "kill" - 5 to do, its progress from the last pass: 3, then 5)
    waiter = ns(ObjectiveDependency=ns(Objective=kill, Status=dep_status.EODS_Complete))
    kill.Outer = mission
    assert mlog._waiting_on(waiter, {}, {0x600: (1, 3, 0)}) == ("Tuer des bandits", "GD_Episode02.M_Ep2a_MoreGuns")
    assert mlog._waiting_on(waiter, {}, {0x600: (1, 5, 0)}) is None, "objective done (its count reached)"
    assert mlog._waiting_on(waiter, {"GD_Episode02.M_Ep2a_MoreGuns": "Complete"}, {}) is None, "its mission done"
    assert mlog._waiting_on(ns(ObjectiveDependency=ns(Objective=None, Status=dep_status.EODS_Complete)), {}, {}) is None
    # The area's level (tools/probes/probe_region.txt): the game stage of the regions this map's missions use
    tundra, train, elsewhere = (ns(_get_address=lambda a=a: a) for a in (0x6a0, 0x6a1, 0x6a2))
    here_station = ns(_get_address=lambda: 0x683, StationDisplayName="Tundra Express", StationLevelName="TundraExpress_P")
    area_log = mlog.MissionLog()
    area_log._mdefs = [ns(TravelStation=here_station, GameStageRegion=tundra), ns(TravelStation=here_station, GameStageRegion=tundra),
                       ns(TravelStation=here_station, GameStageRegion=train), ns(TravelStation=shelf, GameStageRegion=elsewhere)]
    assert area_log.map_regions("tundraexpress_p") == [tundra, train], "this map's missions' regions, once each"
    saved_log, saved_level, saved_get_pc = c._log, c._level, col.get_pc
    c._log, c._level = area_log, {"id": c.level_id, "map": "tundraexpress_p", "name": "Tundra Express"}
    stages = {0x6a0: 13, 0x6a1: -1}  # the train's region: not visited yet (-1)
    col.get_pc = lambda **k: ns(GetGameStageFromRegion=lambda r: stages[r._get_address()])
    c._update_area_level()
    one = c._level.get("lv")
    stages[0x6a1] = 15
    c._update_area_level()
    both = c._level.get("lv")
    c._log, c._level, col.get_pc = saved_log, saved_level, saved_get_pc
    assert (one, both) == ([13, 13], [13, 15]), ("the area's level: its regions' stages, unvisited ones left out", one, both)
    # A co-op client's markers (tools/probes/probe_client_waypoints.txt): no waypoint components - the level's
    # WillowWaypoint actors, each with WaypointInfo {LinkedObjective, ObjectiveSetRestrictions}
    step_set, other_set = ns(_get_address=lambda: 0x6b0), ns(_get_address=lambda: 0x6b1)
    saved_step = log_entries[1].ActiveObjectiveSet
    step_set.ObjectiveDefinitions = saved_step.ObjectiveDefinitions  # the tracked mission's current step: kill, extra
    log_entries[1].ActiveObjectiveSet = step_set
    for o in (secure, kill, extra):
        o.Outer = mission

    def waypoint_actor(a: int, objective: object, restrictions: list, radius: int = 0) -> object:
        w = ns(_get_address=lambda: a, WaypointInfo=ns(LinkedObjective=objective, ObjectiveSetRestrictions=restrictions),
               Location=ns(X=float(a), Y=2.0, Z=3.0), AreaRadius=radius)
        return lambda: w

    c._waypoints = [waypoint_actor(0x6c0, kill, [step_set], 500),  # its step: shown (3 / 5)
                    waypoint_actor(0x6c1, secure, []),  # done (1 / 1), not in the step anyway
                    waypoint_actor(0x6c2, kill, [other_set]),  # another step's
                    waypoint_actor(0x6c3, extra, [])]  # no restrictions, in the current step: shown
    client_marks = c._client_markers(tracker, mission._get_address())
    log_entries[1].ActiveObjectiveSet = saved_step
    c._waypoints = []
    assert [(m["i"], m["rad"], m["tracked"], m["objective"]["n"]) for m in client_marks] == [
        ("6c0", 500, True, "Tuer des bandits"), ("6c3", 0, True, "Bonus")], client_marks
    # Quest givers from the NPCs (tools/probes/probe_directors.txt; a client has no directive waypoints, the host's
    # miss some): an NPC's MissionDirectives against the log - "Side job" can be picked up (its dependency
    # done), "Later job" can't (needs the active mission); an NPC with the game's own marker: skipped
    states = c._log.giver_states()
    assert states.get("GD_Z1_Side.M_Side") == "begin" and "GD_Z1_Later.M_Later" not in states, states
    giver = ns(Location=ns(X=500.0, Y=600.0, Z=700.0))
    c._givers = {0x6d0: (lambda: giver, [(later, True, True), (side, True, True)])}
    givers = c._npc_givers(mission._get_address(), set())
    has_marker = c._npc_givers(mission._get_address(), {0x6d0})
    c._givers = {}
    assert [(m["i"], m["k"], m["mission"]["n"], m["x"]) for m in givers] == [("g6d0", "directive", "Side job", 500)], givers
    assert has_marker == [], has_marker
    assert (givers[0]["mi"], givers[0]["by"]) == ("GD_Z1_Side.M_Side", "6d0"), givers  # the page links the mission / the NPC
    # several at once (an NPC / the bounty board): one marker, every mission listed - one to hand in marked
    # (the log's states stubbed: "Later job" ready to hand in; "Side job" listed once)
    c._givers = {0x6d1: (lambda: giver, [(side, True, False), (later, False, True), (side, True, True), (mission, True, True)])}
    c._log.giver_states = lambda: {"GD_Z1_Side.M_Side": "begin", "GD_Z1_Later.M_Later": "end"}
    several = c._npc_givers(None, set())
    del c._log.giver_states
    c._givers = {}
    assert [[(e["i"], e["n"], e.get("end")) for e in m["list"]] for m in several] == [
        [("GD_Z1_Side.M_Side", "Side job", None), ("GD_Z1_Later.M_Later", "Later job", 1)]], several
    assert (several[0]["mi"], several[0]["mission"]) == ("GD_Z1_Side.M_Side", {"n": "Side job"}), several
    # an object's list (the bounty board: WillowInteractiveObject.Directives, tools/probes/probe_bounty.txt) - the same
    board = ns(Location=ns(X=900.0, Y=0.0, Z=0.0))
    board_directive = ns(MissionDefinition=side, bBeginsMission=True, bEndsMission=False)
    c._note_giver(0x6e0, board, [board_directive])
    c._givers[0x6e0] = (lambda: board, c._givers[0x6e0][1])  # (the fake isn't weak-referenceable: its pointer by hand)
    board_marks = c._npc_givers(None, set())
    c._note_giver(0x6e0, board, [])  # no list (any other object): not a giver
    assert [(m["i"], m["mission"]["n"], m["x"]) for m in board_marks] == [("g6e0", "Side job", 900)] and not c._givers, board_marks
    assert (tracked["ml"], tracked.get("mlk")) == (3, 1), "picked up: its level, locked"
    assert (by_id["GD_Z1_Side.M_Side"]["ml"], by_id["GD_Z1_Side.M_Side"].get("mlk")) == (3, None), "not picked up: the level it would lock at"
    assert "ml" not in by_id["GD_Episode02.M_Ep2_Henchman"], "done: no level read"
    assert by_id["GD_Z1_Later.M_Later"].get("ml") == 3, "locked: its level too (the one it would lock at: a guide)"
    assert by_id["GD_Z1_Side.M_Side"].get("kick") == 1 and "kick" not in by_id["GD_Z1_Later.M_Later"], "offered flag (bHeardKickoff)"
    # the full pass in slices (a few entries per tick): nothing applied until the cycle completes
    from helios_tracker import missions as sliced  # noqa: PLC0415

    chunked = sliced.MissionLog()
    steps = 0
    while not chunked.step(tracker, lambda: [], budget=1):
        steps += 1
        assert chunked.in_cycle and not chunked.payload(1)["missions"], "applied before the cycle completed"
    assert steps == len(log_entries) - 1 and [m["st"] for m in chunked.payload(1)["missions"]] == [m["st"] for m in log["missions"]], steps
    # rewards per player level (tools/probes/probe_rewards.txt: MissionDefinition.GetExperienceReward(pc, bAlt))
    from helios_tracker import missions as mission_log  # noqa: PLC0415

    def controller(addr: int, level: int):  # noqa: ANN202
        return ns(_get_address=lambda: addr, PlayerReplicationInfo=ns(ExpLevel=level))
    for d in (henchman, mission, side, later):
        d.GetExperienceReward = lambda pc, alt: pc.PlayerReplicationInfo.ExpLevel * 100
    log_obj = mission_log.MissionLog()
    log_obj.full(tracker, [controller(1, 30), controller(2, 12), controller(3, 30)])
    rewarded = {m["i"]: m.get("rw") for m in log_obj.payload(1)["missions"]}
    assert rewarded["GD_Episode02.M_Ep2a_MoreGuns"] == {"30": {"xp": 3000}, "12": {"xp": 1200}}, rewarded
    assert rewarded["GD_Z1_Later.M_Later"] == {"30": {"xp": 3000}, "12": {"xp": 1200}}, "one step away: rewarded"
    assert rewarded["GD_Episode02.M_Ep2_Henchman"] is None, "done: no reward"
    henchman.DlcExpansion = ns(_path_name=lambda: "GD_Orchid.DLC")  # the definitions are cached: a fresh one
    mission_log._defs.clear()
    log_obj.full(tracker, [controller(1, 30)])
    dlcs = {m["i"]: m.get("dlc") for m in log_obj.defs_payload()["missions"]}
    assert dlcs["GD_Episode02.M_Ep2_Henchman"] == "GD_Orchid.DLC" and dlcs["GD_Z1_Side.M_Side"] is None, dlcs
    # BL1's mission log (tools/probes/probe_bl1_missions.txt): the player's own list (MissionPlaythroughData), objectives as
    # structs {ProgressMessage, ObjectiveCount}, progress Objectives[].CurrentAmount, MS_Redeemed = done, no steps (all
    # its objectives current), its story number PlotMissionNumber - MissionLog unchanged, the profile's reads
    from helios_tracker import games as mission_games  # noqa: PLC0415
    bl1_status = enum.IntEnum("EMissionStatus", ["MS_NotStarted", "MS_Active", "MS_ReadyToTurnIn", "MS_Complete", "MS_Redeemed"], start=0)

    def bl1_mission(addr: int, name: str, number: int, objectives: list) -> types.SimpleNamespace:
        return ns(_get_address=lambda: addr, _path_name=lambda: f"Z0_Missions.Missions.{name}", Name=name, MissionName=name.removeprefix("M_"),
                  PlotMissionNumber=number, bPlotCritical=True, Dependencies=[], MissionDescription="", MissionSummary="", MissionGiver="T.K. Baha",
                  GameStage=3, Objectives=[ns(ProgressMessage=text, ObjectiveCount=count, StatId="None") for text, count in objectives])
    bl1_meet = bl1_mission(0xB100, "M_MeetAl", 6, [])
    bl1_food = bl1_mission(0xB101, "M_ExterminateSkag", 7, [("Stolen Food:", 4)])
    bl1_two = bl1_mission(0xB102, "M_TwoThings", 8, [("Kill Nine-Toes", 1), ("Bandits killed:", 10)])
    bl1_entries = [ns(MissionDef=bl1_meet, Status=bl1_status.MS_Redeemed, Objectives=[]),
                   ns(MissionDef=bl1_food, Status=bl1_status.MS_ReadyToTurnIn, Objectives=[ns(StatId="None", CurrentAmount=4)]),
                   ns(MissionDef=bl1_two, Status=bl1_status.MS_Active, Objectives=[ns(StatId="None", CurrentAmount=0), ns(StatId="None", CurrentAmount=3)])]
    real_game = mission_games.GAME
    mission_games.GAME = mission_games.make_profile("BL1")
    mission_games.GAME.mission_entries = lambda tracker_obj: bl1_entries  # (the player's list: mods_base's controller, not faked here)
    try:
        bl1_log = mission_log.MissionLog()
        bl1_log.full(ns(ActiveMission=bl1_food), [])
        bl1_defs = {m["i"].rpartition(".")[2]: m for m in bl1_log.defs_payload()["missions"]}
        bl1_live = {m["i"].rpartition(".")[2]: m for m in bl1_log.payload(1)["missions"]}
    finally:
        mission_games.GAME = real_game
    assert [bl1_live[k]["st"] for k in ("M_MeetAl", "M_ExterminateSkag", "M_TwoThings")] == ["Complete", "ReadyToTurnIn", "Active"], bl1_live
    assert bl1_live["M_ExterminateSkag"]["p"] == [4] and bl1_defs["M_ExterminateSkag"]["obj"][0]["c"] == 4, (bl1_live, bl1_defs)
    assert bl1_live["M_TwoThings"]["cur"] == [0, 1] and bl1_live["M_TwoThings"]["p"] == [0, 3], ("no steps: every objective current", bl1_live)
    assert bl1_defs["M_TwoThings"]["num"] == 8 and bl1_defs["M_TwoThings"]["obj"][1]["n"] == "Bandits killed:", bl1_defs
    # BL1's objective markers (collector._waypoint_markers): the level's waypoint actors of an active mission's target
    # definition (its first objective not done), of a ready one's turn-in definition ("end"); the others not
    def bl1_waypoint(addr: int, definition: object, x: float) -> types.SimpleNamespace:
        return ns(_get_address=lambda: addr, WaypointDefinition=definition, Location=ns(X=x, Y=0.0, Z=0.0), bHidden=True)
    wp_pearls, wp_al, wp_vendor = (ns(_get_address=lambda a=a: a) for a in (0xD1, 0xD2, 0xD3))
    bl1_food.TargetWaypointDefinition, bl1_food.TurnInWaypointDefinition = wp_pearls, wp_al
    bl1_two.TargetWaypointDefinition, bl1_two.TurnInWaypointDefinition = wp_vendor, wp_al
    bl1_meet.TargetWaypointDefinition = bl1_meet.TurnInWaypointDefinition = None
    bl1_waypoints = [bl1_waypoint(0xE1, wp_pearls, 1.0), bl1_waypoint(0xE2, wp_al, 2.0), bl1_waypoint(0xE3, wp_vendor, 3.0),
                     bl1_waypoint(0xE4, ns(_get_address=lambda: 0xD9), 4.0)]
    mission_games.GAME = mission_games.make_profile("BL1")
    mission_games.GAME.mission_entries = lambda tracker_obj: bl1_entries
    mission_games.GAME.map_name = lambda wi_obj: "arid_p"
    try:
        bl1_markers = col.Collector._waypoint_markers(ns(_waypoints=[lambda w=w: w for w in bl1_waypoints], _exits=[]), ns(), 0xB102)
        # a mission whose target is in another area: marked on the exit leading there (its transition landmark's
        # ToMapName - Nine-Toes: Take Him Down, WP_NineToes in Arid_SkagGully_P)
        bl1_two.TargetWaypointDefinition = ns(_get_address=lambda: 0xD4, PersistentLevelName="Arid_SkagGully_P")
        bl1_gully = ns(_get_address=lambda: 0xF1, ToMapName="Arid_SkagGully_P", Location=ns(X=-22012.0, Y=44803.0, Z=1370.0))
        bl1_cave = ns(_get_address=lambda: 0xF2, ToMapName="Arid_Cave_P", Location=ns(X=-26730.0, Y=-11709.0, Z=-1122.0))
        bl1_exit_markers = col.Collector._waypoint_markers(ns(_waypoints=[lambda w=w: w for w in bl1_waypoints],
                                                               _exits=[lambda: bl1_gully, lambda: bl1_cave]), ns(), 0xB102)
        # a definition's waypoints: a numbered path - the next one only, its lowest number not completed (Bone Head's
        # Theft's checkpoints: #1 done, #2 shown - the page had both); the same number twice: both (alternatives)
        bl1_two.TargetWaypointDefinition = wp_vendor
        bl1_path = [ns(**{**vars(bl1_waypoint(0xE5 + n, wp_vendor, x)), "WaypointNumber": number, "bCompleted": done})
                    for n, (x, number, done) in enumerate([(5.0, 1, True), (6.0, 2, False), (7.0, 2, False), (8.0, 3, False)])]
        bl1_path_markers = col.Collector._waypoint_markers(ns(_waypoints=[lambda w=w: w for w in bl1_path], _exits=[]), ns(), 0xB102)
    finally:
        mission_games.GAME = real_game
    assert [(m["x"], m["k"]) for m in bl1_exit_markers if m["k"] == "objective"] == [(-22012, "objective")], bl1_exit_markers
    assert [(m["x"], m["k"], m.get("end"), m["tracked"]) for m in bl1_markers] == [(2, "directive", 1, False), (3, "objective", None, True)], \
        ("the ready one's turn-in, the active one's target - not the pearls' (done), not another definition's", bl1_markers)
    assert bl1_markers[1]["objective"]["n"] == "Kill Nine-Toes" and bl1_markers[1]["mi"].endswith("M_TwoThings"), bl1_markers
    assert sorted(m["x"] for m in bl1_path_markers) == [6, 7], ("the next waypoint (#2, both) - not #1 (done), not #3", bl1_path_markers)
    version = hub._channels["missionlog"][0]
    c.tick(1001.5)  # nothing changed: not published again
    assert hub._channels["missionlog"][0] == version, "mission log republished with no change"
    log_entries[1].ObjectivesProgress = [1, 4, 0]  # a kill
    c.tick(1002.6)  # the next marker read (1 s): the fast pass
    tracked = next(m for m in merged_log()["missions"] if m["i"] == tracked["i"])
    assert tracked["p"] == [1, 4, 0], tracked
    assert [b["k"] for b in player["backpack"]] == ["shield"], player["backpack"]
    assert player["backpack"][0].get("wt") == "shield" and "el" not in player["backpack"][0], \
        ("a non-weapon's type icon: its card's GetZippyFrame(), lower case; no element ('None')", player["backpack"][0])
    assert player["host"] is True, "solo / listen server: the mod's player hosts"
    assert player["skills"][0]["n"] == "Sniping" and player["skills"][0]["skills"][0]["g"] == 4, player["skills"]
    assert player["skills"][0]["pts"] == 4 and not player["skills"][0].get("root"), player["skills"]
    (tier,) = player["skills"][0]["tiers"]
    assert tier["need"] == 5 and tier["cells"][0]["g"] == 4 and tier["cells"][1:] == [None, None], tier
    # a co-op client, another player: no inventory manager, their equipped gear on the pawn (tools/probes/probe_coop.txt)
    inspector = sys.modules["helios_tracker.inspector"]
    remote = {"local": False}
    inspector._inventory(ns(InvManager=None, Weapon=weapon, HolsteredWeaponSlots=[weapon, None],
                            EquippedItems=[shield, None, None, None]), remote)
    assert remote["inventory"] == "partial" and [i["k"] for i in remote["equipped"]] == ["weapon", "shield"], remote
    assert remote["inventoryWhy"] == "coopClient" and "backpack" not in remote, remote
    # A shield's card stats (tools/probes/probe_shield.txt, the Pre-Sequel's Dinky Shield - the card: 53, 16, 2.36): its
    # UIStatModifiers, labelled by their presentation's Description, rounded by its RoundingMode / FloatPrecision
    attr_rounding = enum.IntEnum("EAttributePresentationRoundingMode", ["ATTRROUNDING_None", "ATTRROUNDING_IntRound"], start=0)
    def ui_stat(label: str, total: float, rounding: int, precision: int) -> types.SimpleNamespace:
        return ns(ModifierTotal=total, AttributePresentation=ns(Description=label, RoundingMode=attr_rounding(rounding),
                                                                FloatPrecision=precision, _path_name=lambda: label))
    card_shield = ns(UIStatModifiers=[ui_stat("Capacity", 53.0588264465332, 1, 1), ui_stat("Recharge Rate", 15.70201587677002, 1, 1),
                                      ui_stat("Recharge Delay", 2.3648648262023926, 0, 2), ui_stat("Half", 16.5, 1, 1)])
    assert inspector._ui_stats(card_shield) == [["Capacity", 53, 0], ["Recharge Rate", 16, 0], ["Recharge Delay", 2.36, 2],
                                                ["Half", 17, 0]], ("the card's numbers, IntRound half up", inspector._ui_stats(card_shield))
    assert inspector._ui_stats(ns(UIStatModifiers=None)) == [], "no stats: none"
    # A weapon's card Accuracy (tools/probes/probe_accuracy.txt: the Pre-Sequel's shotgun, Spread 4.186 -> the card's 72.1; a
    # sniper, 0.667 -> 95.6): its spread through AttrPresent_WeaponSpread's remapping (both games' Startup.upk: 0..15
    # onto 100..0, ATTRROUNDING_Float, the class default FloatPrecision 1)
    accuracy_rounding = enum.IntEnum("EAccuracyRounding", ["ATTRROUNDING_None", "ATTRROUNDING_IntRound", "ATTRROUNDING_Float"], start=0)
    def remap_bound(value: float) -> types.SimpleNamespace:
        return ns(BaseValueConstant=value, BaseValueScaleConstant=1.0)
    accuracy_pres = ns(bValueRemappingEnabled=True, RoundingMode=accuracy_rounding.ATTRROUNDING_Float, FloatPrecision=1,
                       RemappingData=ns(InputValueMn=remap_bound(0.0), InputValueMx=remap_bound(15.0),
                                        OutputValueMn=remap_bound(100.0), OutputValueMx=remap_bound(0.0)))
    inspector._accuracy_pres[:] = [accuracy_pres]
    assert inspector._accuracy(None, 4.186046600341797, 4.186046600341797) == [72.1, 72.1, 1], "the shotgun's card: 72.1"
    assert inspector._accuracy(None, 0.6666666865348816, 0.6666666865348816) == [95.6, 95.6, 1], "the sniper's card: 95.6"
    assert inspector._accuracy(None, 4.186046600341797, 3.0) == [72.1, 80.0, 1], "with bonuses: from Spread"
    accuracy_pres.bValueRemappingEnabled = False
    assert inspector._accuracy(None, 4.0, 4.0) is None, "no remapping: no accuracy"
    inspector._accuracy_pres.clear()
    # an unset name reads "None" - not a name (the Pre-Sequel's WT_Tediore_Laser has no Typename; the others "Laser")
    assert inspector._localized(ns(PartName="", Typename="None", ItemName="", Grades=[]), 0) == "", "an unset Typename"
    assert inspector._localized(ns(PartName="", Typename="Laser"), 0) == "Laser"
    # ...its name then the game's other weapon types' of the same WeaponType (not the full-named vehicle guns)
    weapon_types = enum.IntEnum("EWeaponType", ["WT_Pistol", "WT_Laser"], start=0)
    real_find_all_types = inspector.unrealsdk.find_all
    inspector.unrealsdk.find_all = lambda name, exact=True: [
        ns(WeaponType=weapon_types.WT_Laser, Typename="Laser", bTypeNameIsFullName=False),
        ns(WeaponType=weapon_types.WT_Laser, Typename="Laser", bTypeNameIsFullName=False),
        ns(WeaponType=weapon_types.WT_Laser, Typename="Moon Buggy Light Laser", bTypeNameIsFullName=True),
        ns(WeaponType=weapon_types.WT_Laser, Typename="None", bTypeNameIsFullName=False)] if name == "WeaponTypeDefinition" else []
    inspector._type_names = None
    tediore_type = inspector._type_name(ns(WeaponType=weapon_types.WT_Laser, Typename="None"))
    assert tediore_type == "Laser", ("its WeaponType's name, from the game's others", tediore_type)
    inspector.unrealsdk.find_all, inspector._type_names = real_find_all_types, None
    # What explodes (a barrel): its definition's behaviours hold a Behavior_Explode, its element its explosion's damage type
    # (element_of); the frame: learned from a weapon's ElementalFrame ("fire" for Incendiary), else the enum's name
    saved_frames = dict(inspector._element_frames)  # (the real .cache's, loaded at import: not in these checks)
    inspector._element_frames.clear()
    barrel_damage = enum.IntEnum("EDamageType", ["DAMAGE_TYPE_Normal", "DAMAGE_TYPE_Incindiary", "DAMAGE_TYPE_Ice"], start=0)  # (the game's spelling)
    barrel_ctrl = ns(Localize=lambda section, key, package: {"Ice": "cryo", "Incendiary": "incendiary"}.get(key, "?INT?"))
    def barrel_def(addr: int, damage) -> types.SimpleNamespace:  # noqa: ANN001
        explode = ns(Class=ns(Name="Behavior_Explode"), Definition=ns(DamageTypeDef=ns(DamageType=damage,
                     HUDDamageColor=ns(R=90, G=200, B=255))))
        return ns(_get_address=lambda: addr, BehaviorProviderDefinition=ns(BehaviorSequences=[
            ns(BehaviorData2=[ns(Behavior=ns(Class=ns(Name="Behavior_Destroy"))), ns(Behavior=explode)])]))
    cryo_barrel = inspector.explosion_info(barrel_def(0xB01, barrel_damage.DAMAGE_TYPE_Ice), barrel_ctrl)
    assert cryo_barrel == {"xp": 1, "el": "ice", "et": "DAMAGE_TYPE_Ice", "eln": "cryo", "ecol": "#5ac8ff"}, cryo_barrel
    # A buff you use (a Moxxtail): activates a skill, hands none of its own loot out; Isaiah's strongbox does: a container
    def behaviours_def(addr: int, *classes: str) -> types.SimpleNamespace:
        return ns(_get_address=lambda: addr, BehaviorProviderDefinition=ns(BehaviorSequences=[
            ns(BehaviorData2=[ns(Behavior=ns(Class=ns(Name=c))) for c in classes])]))
    buff_kinds = [inspector.buff_info(behaviours_def(0xB11, "Behavior_ActivateSkill", "Behavior_SpawnItems")),
                  inspector.buff_info(behaviours_def(0xB12, "Behavior_ActivateSkill", "Behavior_AttachItems"), True),
                  inspector.buff_info(behaviours_def(0xB13, "Behavior_AttachItems"), True),
                  inspector.buff_info(behaviours_def(0xB14, "Behavior_ActivateSkill"), True),
                  inspector.buff_info(behaviours_def(0xB15, "Behavior_ActivateSkill"))]
    assert buff_kinds == [True, False, False, True, False], \
        ("a Moxxtail (no loot list: the Ammo one), Isaiah's strongbox, a chest, a shrine, a switch console", buff_kinds)
    # An elemental plant (its Allegiance the game's Allegiance_ElementalPlant): the explosives' layer, its element from a
    # beam (the Shock Cactus), else its damage areas (the Cryo Vine: WillowDamageArea objects inside its definition)
    plant_beam = ns(Class=ns(Name="Behavior_FireBeam"), DamageTypeDefinition=ns(DamageType=barrel_damage.DAMAGE_TYPE_Ice,
                    HUDDamageColor=ns(R=90, G=200, B=255)))
    cactus_def = ns(_get_address=lambda: 0xB21, Allegiance=ns(Name="Allegiance_ElementalPlant"),
                    BehaviorProviderDefinition=ns(BehaviorSequences=[ns(BehaviorData2=[ns(Behavior=plant_beam)])]))
    vine_def = ns(_get_address=lambda: 0xB22, Allegiance=ns(Name="Allegiance_ElementalPlant"), BehaviorProviderDefinition=None)
    vine_area = ns(Outer=vine_def, DamageTypeDefinition=ns(DamageType=barrel_damage.DAMAGE_TYPE_Ice, HUDDamageColor=ns(R=90, G=200, B=255)))
    real_find_all_plants = inspector.unrealsdk.find_all
    inspector.unrealsdk.find_all = lambda cls, exact=True: [vine_area] if cls == "WillowDamageArea" else []
    plant_kinds = [inspector.plant_info(cactus_def, barrel_ctrl).get("el"), inspector.plant_info(vine_def, barrel_ctrl).get("el"),
                   inspector.plant_info(ns(_get_address=lambda: 0xB23, Allegiance=ns(Name="Allegiance_ExplosiveBarrel")), barrel_ctrl)]
    inspector.unrealsdk.find_all = real_find_all_plants
    assert plant_kinds == ["ice", "ice", {}], ("a beam's element, a damage area's, a barrel isn't a plant", plant_kinds)
    assert inspector.explosion_info(ns(_get_address=lambda: 0xB02, BehaviorProviderDefinition=None), barrel_ctrl) == {}, \
        "no behaviours (the air dome generator): doesn't explode"
    fire_element = inspector.element_of(ns(DamageType=barrel_damage.DAMAGE_TYPE_Incindiary), barrel_ctrl)
    assert fire_element.get("eln") == "incendiary", ("the game's typo corrected: Incindiary -> its text's Incendiary", fire_element)
    fire_before = fire_element.get("el")
    frames_file = inspector.FRAMES_FILE
    frames_tmp = tempfile.TemporaryDirectory()
    inspector.FRAMES_FILE = Path(frames_tmp.name) / "element_frames.json"  # (not the repo's .cache)
    inspector.learn_frame("DAMAGE_TYPE_Incindiary", "fire")  # (as _item learns it from a fire weapon)
    assert json.loads(inspector.FRAMES_FILE.read_text(encoding="utf-8")) == {"DAMAGE_TYPE_Incindiary": "fire"}, "remembered"
    inspector.FRAMES_FILE = frames_file
    frames_tmp.cleanup()
    fire_after = inspector.element_of(ns(DamageType=barrel_damage.DAMAGE_TYPE_Incindiary), barrel_ctrl).get("el")
    assert (fire_before, fire_after) == ("fire", "fire"), ("the game's typo's frame, then the one learned from its items", fire_before, fire_after)
    inspector._element_frames.clear()  # (the real .cache's frames back, once these checks are done)
    inspector._element_frames.update(saved_frames)
    # an object's health: when its definition can take damage and its max is above 0
    hurt_barrel = ns(InteractiveObjectDefinition=ns(bCanTakeDirectDamage=True, bCanTakeRadiusDamage=True), MaxHealth=80.0, Health=35.5)
    assert col.Collector._health(hurt_barrel) == (35.5, 80), col.Collector._health(hurt_barrel)
    assert col.Collector._health(ns(InteractiveObjectDefinition=ns(bCanTakeDirectDamage=False, bCanTakeRadiusDamage=False),
                                    MaxHealth=80.0, Health=80.0)) is None, "can't take damage: no health"
    # killed (an exploded barrel stays, its wreck at 0 health): bHasBeenKilled, or the health down to 0
    assert col.Collector._killed(ns(bHasBeenKilled=True), {"h": 40, "m": 80})
    assert col.Collector._killed(ns(bHasBeenKilled=False), {"h": 0, "m": 80}), "0 health: killed"
    assert not col.Collector._killed(ns(bHasBeenKilled=False), {"h": 35.5, "m": 80})
    assert not col.Collector._killed(ns(bHasBeenKilled=False), {}), "no health: never killed"
    # a container's opened state: a bitmask over its animations, the "Opened" one's bit (tools/probes/probe_prelooted.txt)
    locker_anims = [ns(AnimName=n) for n in ("Open", "Open_Vacuum", "Opened", "Closed")]
    locker_looted = {state: col.Collector._is_looted(ns(SimpleAnimState=state, SimpleAnimInfo=locker_anims, bCanBeUsed=[0, 0]))
                     for state in (8, 14, 12, 4)}
    assert locker_looted == {8: False, 14: True, 12: True, 4: True}, ("closed / just opened / reloaded / spawned looted", locker_looted)
    assert not col.Collector._is_looted(ns(SimpleAnimState=14, SimpleAnimInfo=locker_anims, bCanBeUsed=[1, 0])), "still usable"
    print(f"  inspector: {player['n']} Lv{player['lvl']} {player['cls']}, {len(player['equipped'])} equipped,"
          f" {len(player['backpack'])} in backpack, skills {[b['n'] for b in player['skills']]};"
          f" gun '{gun['type']}' by '{gun['maker']}'; object '{obj['n']}'")
    print(f"  missions: tracked {missions['tracked']['n']!r}, markers"
          f" {[(m['k'], m['rad'], m.get('objective', {}).get('n')) for m in missions['markers']]};"
          f" log {len(log['missions'])} missions, tracked progress {tracked['p']}")
    hub.clients = 0

    # The server: page, SSE stream, image
    server = TrackerServer("127.0.0.1", 0, hub)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.request("GET", "/")
        res = conn.getresponse()
        page = res.read()
        assert res.status == 200 and b"Helios Tracker" in page, res.status
        conn.request("GET", level["images"][0]["url"])
        res = conn.getresponse()
        image = res.read()
        assert res.status == 200 and len(image) == 468 * 512, (res.status, len(image))
        web = ROOT / "helios_tracker" / "web"
        web_files = sorted(p for p in web.rglob("*") if p.suffix in (".js", ".css", ".png", ".svg", ".woff2"))
        assert web / "img" / "favicon.png" in web_files, "the logo (the tab's icon)"
        assert {web / "fonts" / f"helios-h-{k}{b}.woff2" for k in ("gradient", "mono") for b in ("", "-gecko")} <= set(web_files), \
            "the title's H (base.css: the logo as a font, its COLR v1 / one-colour builds, Firefox's)"
        assert {web / "img" / "patterns" / f"{n}.svg" for n in ("shield", "health", "vehicle", "scanlines")} <= set(web_files), "the bars' pattern tiles"
        for file in web_files:  # every module / stylesheet / image, at its path under web/
            conn.request("GET", "/" + file.relative_to(web).as_posix())
            res = conn.getresponse()
            body = res.read()
            want_type = {".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml",
                         ".woff2": "font/woff2"}.get(file.suffix, "text/javascript")
            assert res.status == 200 and res.headers["Content-Type"].startswith(want_type), (file, res.status)
            assert body == file.read_bytes(), file
        for bad in ("/../server.py", "/js/../../server.py", "/web/js/main.js", "/JS/MAIN.JS", "/js/main.py"):
            conn.request("GET", bad)
            res = conn.getresponse()
            res.read()
            assert res.status == 404, (bad, res.status)
        hub.fonts = {slug: data for slug, (_n, data) in game_fonts.items()}  # the game's fonts, once extracted
        for font_path, want in (("/font/willowbody.ttf", 200), ("/font/nope.ttf", 404), ("/font/../server.py", 404)):
            conn.request("GET", font_path)
            res = conn.getresponse()
            body = res.read()
            assert res.status == want and (want != 200 or (res.headers["Content-Type"] == "font/ttf" and body == game_fonts["willowbody"][1])), (font_path, res.status)
        conn.request("GET", "/image/999/0")
        res = conn.getresponse()
        res.read()
        assert res.status == 404, res.status
        sse = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        sse.request("GET", "/events")
        res = sse.getresponse()
        assert res.headers["Content-Type"] == "text/event-stream", res.headers
        events = set()
        while len(events) < 14:
            line = res.fp.readline().decode()
            if line.startswith("event: "):
                events.add(line[7:].strip())
        assert events == {"level", "state", "objects", "players", "missions", "missiondefs", "missionlog", "areas", "shops",
                          "shoptimer", "lootpools", "pickups", "pawninfo", "items"}, events
        # CORS: the project's site (its /live/ page) and local pages may read, any other site not - files and the stream
        for cors_origin, cors_ok in (("https://helios-tracker.zoolsmith.com", True), ("https://zoolsmith.github.io", True), ("http://127.0.0.1:8931", True),
                                     ("http://localhost", True), ("https://evil.example", False), ("", False)):
            cors_conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            for cors_path in ("/", "/js/main.js", "/events"):
                cors_conn.request("GET", cors_path, headers={"Origin": cors_origin} if cors_origin else {})
                cors_res = cors_conn.getresponse()
                cors_allow = cors_res.headers.get("Access-Control-Allow-Origin")
                assert cors_allow == (cors_origin if cors_ok else None), (cors_origin, cors_path, cors_allow)
                if cors_path == "/events":
                    break  # (a stream: never ends)
                cors_res.read()
            cors_conn.close()
        print(f"  server: page {len(page)} bytes + {len(web_files)} js / css / png / svg / woff2 files, image {len(image)} bytes,"
              f" SSE events {sorted(events)}, CORS for the site / local pages only")
    finally:
        server.stop()
    assert not server._thread.is_alive(), "server thread still running"

    # Translations
    import re  # noqa: PLC0415

    i18n_dir = web / "i18n"
    langs = {}
    for file in sorted(i18n_dir.glob("*.js")):
        if file.name != "index.js":
            langs[file.stem] = set(re.findall(r'^\s+"([\w.]+)":', file.read_text(encoding="utf-8"), re.M))
    assert "en" in langs and len(langs) >= 2, langs.keys()
    for code, keys in langs.items():
        assert keys == langs["en"], (code, sorted(keys ^ langs["en"]))
    listed = re.findall(r'^import (\w+) from "\./(\w+)\.js";', (i18n_dir / "index.js").read_text(encoding="utf-8"), re.M)
    assert all(a == b for a, b in listed) and {a for a, _ in listed} == set(langs), ("i18n/index.js", listed, sorted(langs))
    page_src = "\n".join(p.read_text(encoding="utf-8") for p in [web / "index.html", *(web / "js").rglob("*.js")])
    used = set(re.findall(r'data-i18n(?:-title)?="([\w.]+)"', page_src))
    used |= set(re.findall(r'\bt\("([\w.]+)"', page_src))
    used |= set(re.findall(r'(?:setStatus\("\w*", |setMessage\()"([\w.]+)"', page_src))
    used.discard("key")  # the t("key", {vars}) comment
    # t("kind." + k): a dynamic key - its prefix must at least exist
    missing = sorted(k for k in used if k not in langs["en"] and not (
        k.endswith(".") and any(e.startswith(k) for e in langs["en"])))
    assert not missing, missing
    print(f"  i18n: {sorted(langs)} with {len(langs['en'])} keys each, {len(used)} literal keys used by the page")

    # Page refreshes follow the Refresh rate setting (AGENTS.md): what changes by itself is updated from the frames
    # (a refresh...(now) at the end of draw.js' frame), never by a timer of its own - every timer in the page's code
    # is one of these, each with its reason; a new one fails here
    timer_allowed = {
        ("scheduler.js", "setTimeout"): 1,  # the frame scheduler itself: the capped rate's wait between frames
        ("settings.js", "setTimeout"): 1,  # saving the settings, debounced (no drawing)
        ("data.js", "setTimeout"): 1,  # the game gone: checking whether it's back, to reload (no drawing)
        ("data.js", "setInterval"): 1,  # the cutscene clock: no game updates reach the page while a video plays
    }
    timer_found: dict[tuple[str, str], int] = {}
    for timer_file in (web / "js").rglob("*.js"):
        for timer_call in re.findall(r"\b(setInterval|setTimeout)\s*\(", timer_file.read_text(encoding="utf-8")):
            timer_key = (timer_file.name, timer_call)
            timer_found[timer_key] = timer_found.get(timer_key, 0) + 1
    assert timer_found == timer_allowed, ("a page timer outside the Refresh rate setting - refresh it from the frames "
                                          "(AGENTS.md: Page refreshes follow the Refresh rate setting)", timer_found)
    print(f"  page timers: only the {sum(timer_allowed.values())} allowed (everything else refreshes with the frames)")

    # The page's JS: DXT decoding (against the reference decoder above) and world -> map
    node = shutil.which("node")
    if node is None:
        print("  node not found: skipping the page's JS checks")
        return
    want = hashlib.sha256(_dxt5_rgba(468, 512, image)).hexdigest()
    # Record channels (server.py Hub.publish_records): only what changed goes out - fields changed / lost, records gone,
    # the order, the channel's own fields; a page behind gets what it missed at once, a new one (or one too far behind)
    # everything. The page's merge (data.js keyed) runs on these very messages below, against the Hub's snapshot.
    from helios_tracker import server as delta_server  # noqa: PLC0415
    delta_hub = delta_server.Hub()
    delta_a, delta_b, delta_c = {"i": "a", "n": 1, "raw": 1}, {"i": "b", "n": 2, "gear": [1, 2]}, {"i": "c", "n": 3}
    delta_steps = [([delta_a, delta_b], {"level": 1}), ([{"i": "a", "n": 5}, delta_b], {"level": 1}), ([delta_b], {"level": 1}),
                   ([delta_b, delta_c], {"level": 1}), ([delta_c, delta_b], {"level": 1}), ([delta_c, {"i": "b", "n": 2}], {"level": 2})]
    delta_live, delta_msgs = [], []  # a page that follows each version / everything each one sent
    for delta_n, (delta_recs, delta_meta) in enumerate(delta_steps):
        assert delta_hub.publish_records("objs", "objects", delta_recs, delta_meta), ("a change: a new version", delta_n)
        delta_msgs.append(json.loads(delta_hub._channels["objs"][1]))
        delta_live.append(delta_hub._records["objs"].since(None if delta_n == 0 else delta_n))
    assert not delta_hub.publish_records("objs", "objects", delta_steps[-1][0], {"level": 2}), "nothing changed: nothing sent"
    assert delta_msgs[1]["set"] == [{"i": "a", "n": 5, "-": ["raw"]}], ("changed fields, lost ones", delta_msgs[1])
    assert delta_msgs[2]["del"] == ["a"] and delta_msgs[2]["set"] == [] and "o" not in delta_msgs[2], ("gone", delta_msgs[2])
    assert delta_msgs[3]["set"] == [delta_c] and "o" not in delta_msgs[3], ("added at the end: no order", delta_msgs[3])
    assert delta_msgs[4]["o"] == ["c", "b"] and delta_msgs[4]["set"] == [], ("the order changed", delta_msgs[4])
    assert delta_msgs[5]["m"] == {"level": 2} and delta_msgs[5]["set"] == [{"i": "b", "-": ["gear"]}], delta_msgs[5]  # (a flag gone: gone on the page)
    delta_behind = json.loads(delta_hub._records["objs"].since(2))  # (missed versions 3 to 6: a gone "a" too, from 2)
    assert delta_behind["rep"] == 1 and delta_behind["b"] == 2 and delta_behind["o"] == ["c", "b"], delta_behind
    assert json.loads(delta_hub._records["objs"].since(None)).get("full") == 1, "a new page: everything"
    # rows ([id, ...]: the state's pawns) and a stamp: the time goes out with a change, never makes one
    assert delta_hub.publish_records("rows", "pawns", [["p1", 1, 2, 3], ["p2", 4, 5, 6]], {"level": 1}, {"t": 1.0})
    assert not delta_hub.publish_records("rows", "pawns", [["p1", 1, 2, 3], ["p2", 4, 5, 6]], {"level": 1}, {"t": 1.1}), "the stamp alone"
    assert delta_hub.publish_records("rows", "pawns", [["p1", 1, 2, 4], ["p2", 4, 5, 6]], {"level": 1}, {"t": 1.2})
    delta_row = json.loads(delta_hub._channels["rows"][1])
    assert delta_row["set"] == [["p1", 1, 2, 4]] and delta_row["m"] == {"level": 1, "t": 1.2}, ("only the pawn that moved", delta_row)
    # a record changed in place (the collector's container "looted": the same dict published again) - still a change
    delta_inplace = {"i": "box", "lootable": 1}
    delta_hub.publish_records("inplace", "objects", [delta_inplace])
    delta_inplace["looted"] = 1
    assert delta_hub.publish_records("inplace", "objects", [delta_inplace]), "changed in place: missed"
    assert json.loads(delta_hub._channels["inplace"][1])["set"] == [{"i": "box", "looted": 1}], delta_hub._channels["inplace"][1]
    # too far behind (past the history): everything
    delta_server.HISTORY, delta_history = 2, delta_server.HISTORY
    for delta_n in range(4):
        delta_hub.publish_records("short", "objects", [{"i": "x", "n": delta_n}])
    delta_server.HISTORY = delta_history
    assert json.loads(delta_hub._records["short"].since(1)).get("full") == 1, "too far behind: everything"
    # deleted with nothing reordered after (an "o" rebuilds the list: it would hide a missed deletion)
    delta_hub.publish_records("gone", "objects", [{"i": "x"}, {"i": "y"}, {"i": "z"}])
    delta_gone_first = delta_hub._records["gone"].since(None)
    delta_hub.publish_records("gone", "objects", [{"i": "x"}, {"i": "z"}])
    delta_gone_step = delta_hub._records["gone"].since(1)
    delta_hub.publish_records("gone", "objects", [{"i": "x"}])
    delta_gone_last = delta_hub._records["gone"].since(2)
    delta_scenarios = [
        {"list": "objects", "messages": [json.loads(m) for m in delta_live]},  # following every version
        {"list": "objects", "messages": [json.loads(delta_live[0]), json.loads(delta_hub._records["objs"].since(1))]},  # behind
        {"list": "objects", "messages": [delta_msgs[-1]]},  # joined late with no full one: out of step
        {"list": "pawns", "messages": [json.loads(delta_hub._records["rows"].since(None))]},
        {"list": "objects", "messages": [json.loads(m) for m in (delta_gone_first, delta_gone_step, delta_gone_last)]},
        {"list": "objects", "messages": [json.loads(delta_gone_first), json.loads(delta_hub._records["gone"].since(1))]},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "img.bin").write_bytes(image)
        (Path(tmp) / "records.json").write_text(json.dumps(delta_scenarios), encoding="utf-8")
        (Path(tmp) / "test.mjs").write_text(PAGE_TEST_JS, encoding="utf-8")
        out = subprocess.run([node, str(Path(tmp) / "test.mjs"), str(web), str(Path(tmp) / "img.bin"), str(Path(tmp) / "records.json")],
                             capture_output=True, text=True, encoding="utf-8", check=False)
    assert out.returncode == 0, out.stderr
    js = json.loads(out.stdout)
    assert len(js["modules"]) == len([p for p in web_files if p.suffix == ".js"]), js["modules"]
    assert js["sha"] == want, "the page's DXT5 decode differs from the reference decoder"
    assert js["err"] < 0.1, js
    assert js["back"] < 1e-6, js
    assert abs(js["right"] - 3.141592653589793 / 2) < 1e-9, js
    nbsp = "\u00a0"
    assert js["raw"] == [f"Bullymong Pile{nbsp}?", f"AI Pawn{nbsp}?", f"Fire Barrel02{nbsp}?",
                         f"Interactive Object{nbsp}?", f"Willowtree{nbsp}?", "Zer0"], js["raw"]
    mig = js["migrated"]
    assert mig["layers"]["enemy"] == {"on": False, "names": True, "nameSize": 100, "floors": "show", "size": 100, "range": 0}, mig["layers"]
    assert not mig["layers"]["loot.rare"]["on"] and not mig["layers"]["pickup.ammo"]["on"], "old Loot toggle not carried over"
    assert not {"gear", "pickups", "containers"} & set(mig["layers"]), "a folder has no settings"
    assert js["lootLayers"] == ["loot.common", "loot.legendary", "loot.pearl", "loot.pearl", "loot.misc", "loot.misc",
                                "pickup.other", "pickup.cash", "pickup.ammo", "pickup.health", "pickup.other",
                                "loot.uncommon", "pickup.eridium"], js["lootLayers"]
    assert js["freeRects"] == [
        {"x": 0, "y": 0, "w": 1600, "h": 900},  # nothing open: the whole window
        {"x": 268, "y": 0, "w": 1332, "h": 900},  # the panel: right of it
        {"x": 268, "y": 0, "w": 940, "h": 900},  # both: between them
        {"x": 0, "y": 60, "w": 1208, "h": 840},  # a collapsed panel: below it, left of the inspector
    ], js["freeRects"]
    assert js["gameRarity"] == [["legendary", "#ffb400"], ["legendary", "#ffb400"], ["seraph", "#ff9ab8"],
                                ["unknown", "#9132c8"], "loot.legendary"], js["gameRarity"]
    game_out = js["gameOut"]
    assert game_out["gameNone"] == ["enemy", "pickup.eridium", "vaultsymbol", "buff", "slots", "pickup.mission"], game_out["gameNone"]
    assert game_out["gameSwitch"] == [True, False], ("the same features in another order: no change", game_out["gameSwitch"])
    assert game_out["gameTps"] == {"shown": ["loot.glitch", "oxygen", "pickup.oxygen", "jumppad", "area", "fog", "enemy",
                                             "pickup.eridium", "vaultsymbol", "buff", "slots", "pickup.mission"],
                                   "glitch": "glitch", "etech": "loot.legendary"}, game_out["gameTps"]
    # (BL1: no eridium, vault symbols, buffs, slot machines - game.js noLayers; its mission items: bMissionItem)
    assert game_out["gameBl1"] == ["loot.pearl", "enemy", "pickup.mission", 2, 0, "common", "common", True, False,
                                   ["jakobs", "", "", "", ""]], \
        ("BL1: no discovery areas, its pearlescent (500) but no other BL2 / TPS tiers; its treasure chest big; rarity 0 common",
         game_out["gameBl1"])
    assert game_out["gameBl2"] == {"shown": ["loot.pearl", "loot.etech", "area", "fog", "enemy", "pickup.eridium", "vaultsymbol", "buff", "slots", "pickup.mission"], "seraph": "seraph",
                                   "etech": "loot.etech"}, game_out["gameBl2"]
    assert mig["layers"]["player"] == {"names": True, "nameSize": 100, "floors": "show", "size": 100}, mig["layers"]["player"]
    assert mig["view"]["zoom"] == 2.5 and mig["view"]["motion"] == 0, mig["view"]
    assert mig["ui"]["lang"] == "fr" and mig["ui"]["inspectorTab"] == "skills", mig["ui"]
    chk = js["checked"]
    assert chk["enemy"] == {"on": True, "names": False, "nameSize": 100, "floors": "dim", "size": 200, "range": 0}, chk
    assert chk["view"]["follow"] is False and chk["view"]["motion"] == 15 and chk["openLayers"] == ["loot"], chk
    assert chk["drawer"] == {"k": "mission", "id": "M_Plan"} and chk["badDrawer"] == {}, chk  # restored on a refresh
    assert not js["unknownSettings"], js["unknownSettings"]
    missing = sorted(k for k in js["i18nKeys"] if k not in langs["en"])
    assert not missing, ("layer panel keys missing from the catalogs", missing)
    mis = js["missions"]
    assert mis["story"] == ["a:done", "-s1:available", "--s2:locked", "-s3:unknown", "-w:locked", "b:active", "c:locked"], mis["story"]
    assert mis["other"] == ["o:done", "x:ready", "r:ready", "f:other"], mis["other"]
    assert mis["counts"] == {"done": 2, "active": 1, "ready": 2, "available": 1, "unknown": 1, "locked": 3, "other": 1}, mis["counts"]
    assert mis["objectives"] == ["done", "current", "current"], mis["objectives"]
    assert mis["areas"] == ["Shelf:b", "Sanctuary:da", ":c"], mis["areas"]
    assert mis["search"] == ["a:done", "b:locked,a:done", "b:locked", "", ""], mis["search"]
    assert mis["difficulty"] == ["impossible", "tough", "normal", "normal", "trivial", None, None], mis["difficulty"]
    assert mis["finish"] == "f4:7,f1:5,f2:1", mis["finish"]
    # its objective current (to do) / later step / done / mission not started; gives: not started / done; unknown mission
    assert mis["items"] == [True, False, False, False, True, False, True], mis["items"]
    assert mis["statsOut"] == ["Gun Damage: +6\u202f%", "Reload Speed: +8\u202f%", "Shield Recharge Delay: -12\u202f%",
                               "Regenerates 0.4\u202f% of your Max Health / sec.", "Turret Duration: +2 seconds",
                               "Cooldown: 42 seconds"], ("a skill's stats, the game's way", mis["statsOut"])
    assert mis["shotCostOut"] == "Consumes 2 ammo per shot.", ("the shot cost line, its weapon's value", mis["shotCostOut"])
    assert mis["bonusOut"] == ["Gun Damage: +19\u202f%", "Melee Damage: +6\u202f%"], ("the bonuses, added up", mis["bonusOut"])
    lk = mis["lookOut"]  # the see-through settings: 100 % by default, clamped to 0-100, the colour with its alpha
    assert (lk["lookDefault"], lk["lookClamped"], lk["rgba"]) == ({"bg": 100, "map": 100, "panel": 90, "ui": 100, "marker": 100},
                                                                   {"bg": 100, "map": 0, "panel": 20, "ui": 200, "marker": 50}, "rgba(11, 17, 22, 0.4)"), lk
    assert mis["variantWords"] == ["OZ KITS", "3 moonstones", "WEAPONS", "RELICS"], ("the Pre-Sequel's words", mis["variantWords"])
    assert mis["stepOrder"] == ("Throw breaker:current,Power up jump pad:current,Use jump pad:done,Kill Deadlift:current,"
                                "Pick up digistruct key:current"), ("the step's own order, in its slots", mis["stepOrder"])
    assert mis["healthShown"] == "107,107,100,100", ("health rounded down, as the game's HUD; the max the same", mis["healthShown"])
    assert mis["vaultCat"] == "vaultsymbol,station,container,oxygen,oxygen,oxygen,jumppad,npc,chest,buff,slots,chest", \
        ("a vault symbol: its own layer; Catch-A-Ride: a station; anything with loot a container (the Pre-Sequel's"
         " Hyperion ammo crate: no container word in its name)", mis["vaultCat"])
    delta_want = json.loads(delta_hub.latest("objs"))
    delta_gone_want = {"objects": [{"i": "x"}]}
    assert mis["deltaOut"] == [delta_want, delta_want, None, json.loads(delta_hub.latest("rows")), delta_gone_want,
                               delta_gone_want], \
        ("the page's merge of the Hub's messages: the Hub's records", mis["deltaOut"], delta_want)
    assert mis["rowsOut"] == [{"i": "a", "x": 1, "y": 2, "z": 3, "h": 100, "hf": 1, "s": 50, "sf": 1},
                              {"i": "b", "x": 1, "y": 2, "z": 3, "h": 40.5, "s": 10, "r": 5},
                              {"i": "c", "x": 1, "y": 2, "z": 3, "rs": 2}], ("the state's compact rows", mis["rowsOut"])
    assert mis["lootDetailRenders"] == 2, ("an open loot panel: drawn, not again unchanged, again with its card", mis["lootDetailRenders"])
    assert mis["hitPicks"] == ["chest", "onChest", "loot"], ("the click picks what's under the pointer first", mis["hitPicks"])
    fb = mis["fallback"]  # a reward not known for the player's level: the local player's level's, else any
    assert fb["own"] == {"xp": 900} and fb["toLocal"] == {"xp": 1100, "from": 15} and fb["toAny"] == {"xp": 900, "from": 12} and fb["none"] is None, fb
    w = mis["where"]  # where to go: the step's station (active), the turn-in one (ready), else its own
    assert (w["active"]["why"], w["active"]["a"], w["ready"]["a"], w["available"]["why"]) == ("step", "Bay", "Southern Shelf", "home"), w
    assert (w["readyNoTin"]["why"], w["readyNoTin"]["a"], w["activeNoGo"], w["none"]) == ("turnin", "Sanctuary", None, None), w
    assert w["here"] is True and w["notHere"] is False, ("here: the map names compared, any case", w)
    assert mis["tooHigh"] == {"rows": ["ok", "t2", "okKid"], "n": 3, "lv": 11, "total": 160}, mis["tooHigh"]  # dlcKid: its parent's Lv 30
    best = mis["best"]  # u counts its alternative reward (2000 XP); l2 (two steps away) and d (done) are out; e: no reward known
    assert (best["xp"], best["cash"], best["effort"]) == ("ual3vl1ery", "vual1l3ery", "vual3l1ery"), best
    assert best["after"] == ["a"] and best["total"] == 12600 and best["otherLevel"] == 0, best
    me_info, down_info, gone_info = mis["infoHtml"]
    # (a number and its unit: a no-break space between them - never on two lines)
    for want in ("Alive", "Shield", "60 / 100", "Level 30", "500 / 1,000", "Gunzerking", "Active · 12\u202fs", "Locked and Loaded - active", "4\u202fs", "Melee skill", "8\u202fs"):
        assert want in me_info, (want, me_info)
    assert "Crippled" in down_info and "Not known here" in down_info, down_info
    assert "Not in this area" in gone_info, gone_info
    assert mis["gameText"] == ["Go to Sanctuary.<br>Find Roland &amp; win<br>x", "Line one. Line two here"], mis["gameText"]
    print(f"  page JS: {len(js['modules'])} modules import under Node, DXT5 decode matches,"
          f" world->map within {js['err']:.3f} px of the probe samples")


def check_script() -> None:
    """The user script's lookup: autoexec.ps1 in the data folder (paths.DATA - sdk_mods/.helios_tracker/ beside a
    .sdkmod, the mod's folder in a folder install), its log beside it; the old place beside the .sdkmod: not looked at."""
    import tempfile  # noqa: PLC0415

    from helios_tracker import paths  # noqa: PLC0415
    from helios_tracker.script import find_script  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        script_data = Path(tmp) / "sdk_mods" / ".helios_tracker"
        script_data.mkdir(parents=True)
        (script_data.parent / "helios_tracker.autoexec.ps1").write_text("")  # (the old place)
        assert find_script(script_data) is None, "only the data folder's"
        (script_data / "autoexec.ps1").write_text("")
        assert find_script(script_data) == (script_data / "autoexec.ps1", script_data / "autoexec.log")
    assert find_script.__defaults__ == (paths.DATA,), "the data folder by default"
    print("  user script: autoexec.ps1 in the data folder (sdk_mods/.helios_tracker/, or the mod's folder), its log beside it")


def check_sdkmod() -> None:
    """paths.py run from inside a .sdkmod (a zip, imported in a child Python): it finds the zip, reads the page's
    files out of it, and writes to sdk_mods/.helios_tracker/ - created, not a folder the loader would import."""
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as tmp:
        sdk_mods = Path(tmp) / "sdk_mods"
        sdk_mods.mkdir()
        sdkmod = sdk_mods / "helios_tracker.sdkmod"
        with zipfile.ZipFile(sdkmod, "w") as z:
            z.write(ROOT / "helios_tracker" / "paths.py", "helios_tracker/paths.py")
            z.writestr("helios_tracker/__init__.py", "")
            z.write(ROOT / "helios_tracker" / "web" / "index.html", "helios_tracker/web/index.html")
        child = (
            "import sys; sys.path.insert(0, sys.argv[1])\n"
            "from helios_tracker import paths\n"
            "print(paths.SDKMOD); print(paths.DATA); print(len(paths.read('web/index.html') or b''));"
            " print(paths.read('web/nothing.js'))\n"
        )
        out = subprocess.run([sys.executable, "-c", child, str(sdkmod)], capture_output=True, text=True, check=True)
        found, data, size, missing = out.stdout.split("\n")[:4]
        assert Path(found) == sdkmod, out.stdout
        assert Path(data) == sdk_mods / ".helios_tracker" and Path(data).is_dir(), data
        assert int(size) == len((ROOT / "helios_tracker" / "web" / "index.html").read_bytes()), size
        assert missing == "None", missing
    print("  .sdkmod: page files read out of the zip, logs / caches in sdk_mods/.helios_tracker/")


def check_updater() -> None:
    """updater.py against a local stand-in for GitHub's releases API (tools/fake_release.py's format): a newer release
    found, downloaded, verified and swapped in for the .sdkmod; an older one ignored; a release whose zip says another
    version refused (ours untouched); a folder install never replaced."""
    import json  # noqa: PLC0415
    import re  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    import threading  # noqa: PLC0415
    import zipfile  # noqa: PLC0415
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: PLC0415

    import build_sdkmod  # noqa: PLC0415
    from helios_tracker import paths, updater  # noqa: PLC0415

    served: dict[str, bytes] = {}

    class ReleaseHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = served.get(self.path)
            self.send_response(200 if body is not None else 404)
            self.end_headers()
            self.wfile.write(body or b"")

        def log_message(self, *a: object) -> None:
            pass

    release_server = ThreadingHTTPServer(("127.0.0.1", 0), ReleaseHandler)
    threading.Thread(target=release_server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{release_server.server_address[1]}"

    def publish(tag: str, zip_version: str) -> None:
        served["/latest"] = json.dumps({"tag_name": tag, "html_url": f"{base}/page", "assets": [
            {"name": "helios_tracker.sdkmod", "browser_download_url": f"{base}/dl/{tag}"}]}).encode()
        served[f"/dl/{tag}"] = build_sdkmod.build(Path(upd_tmp) / f"{tag}.sdkmod", zip_version, quiet=True).read_bytes()

    def installed_version() -> str:
        with zipfile.ZipFile(upd_sdkmod) as z:
            return re.search(r'version = "(.*)"', z.read("helios_tracker/pyproject.toml").decode())[1]

    saved = paths.SDKMOD, paths.DATA, updater.SOURCE_OVERRIDE, updater.current_version
    with tempfile.TemporaryDirectory() as upd_tmp:
        upd_sdk_mods = Path(upd_tmp) / "sdk_mods"
        upd_sdkmod = build_sdkmod.build(upd_sdk_mods / "helios_tracker.sdkmod", "0.1.0", quiet=True)
        paths.SDKMOD, paths.DATA = upd_sdkmod, upd_sdk_mods / ".helios_tracker"
        updater.SOURCE_OVERRIDE = paths.DATA / "update_source.txt"
        updater.current_version = lambda: (0, 1, 0)
        try:
            assert updater.source() == updater.RELEASES_API, "GitHub without the dev override"
            paths.DATA.mkdir(parents=True)
            updater.SOURCE_OVERRIDE.write_text(f"{base}/latest\n", encoding="utf-8")
            publish("v0.0.9", "0.0.9")
            assert updater.check() is None, "older: nothing to do"
            publish("v0.1.1", "0.1.2")  # its zip says another version: refused
            upd_bad = updater.check()
            assert upd_bad is not None and upd_bad.version == (0, 1, 1), upd_bad
            try:
                updater.install(upd_bad)
                raise AssertionError("a zip of another version installed")
            except ValueError:
                pass
            assert installed_version() == "0.1.0" and not list(paths.DATA.glob("*.download")), "ours untouched"
            publish("v0.2.0", "0.2.0")
            upd_new = updater.check()
            assert upd_new is not None and upd_new.tag == "v0.2.0" and upd_new.page == f"{base}/page", upd_new
            assert updater.install(upd_new) == upd_sdkmod and installed_version() == "0.2.0", "swapped in"
            assert not (paths.DATA / updater.STAGED).exists(), "the download moved in, not left behind"
            upd_running = updater.RUNNING
            updater.RUNNING, updater.current_version = (0, 1, 0), lambda: (0, 2, 0)
            assert updater.pending() == (0, 2, 0), "installed for the next start: a reload runs it"
            updater.RUNNING = (0, 2, 0)
            assert updater.pending() is None, "running it already"
            updater.RUNNING = upd_running
            paths.SDKMOD = None
            assert not updater.can_install(), "a folder install: never replaced"
        finally:
            paths.SDKMOD, paths.DATA, updater.SOURCE_OVERRIDE, updater.current_version = saved
            release_server.shutdown()
    assert updater.parse_version("v1.2.3") == (1, 2, 3) and updater.parse_version("1.2") is None
    import helios_tracker as upd_mod  # noqa: PLC0415 - imported from the repo: a folder install
    assert upd_mod.update_button.is_hidden and upd_mod.auto_update.is_hidden, "folder install: no update options"
    upd_mod._start_check(auto=False)
    assert not upd_mod._update_busy[0], "folder install: never checks"
    assert updater.current_version() is not None, "ours read from the package's pyproject"
    # Reload Now is pressed in the mod's options menu, still open after it: switched to the new mod's options
    # (willow2_mod_menu's provider stack, faked; else its buttons call into the old module - nothing happened)
    class MenuOption:
        def __init__(self, identifier: str, children: tuple = ()) -> None:
            self.identifier, self.children = identifier, children

    class MenuMod:
        def __init__(self) -> None:
            self.opts = (MenuOption("port"), MenuOption("Check for Updates"))
            self.group = MenuOption("Options", self.opts)

        def iter_display_options(self) -> object:
            yield MenuOption("Options", self.opts)

    menu_old, menu_new, menu_extra = MenuMod(), MenuMod(), MenuOption("Enabled")  # (Enabled: the menu's own, kept)
    menu_provider = types.SimpleNamespace(mod=menu_old, options=(menu_extra, menu_old.group),
                                          drawn_options=[menu_extra, menu_old.group, *menu_old.opts])
    menu_other = types.SimpleNamespace(mod=object(), options=(), drawn_options=[MenuOption("port")])
    menu_fake = types.ModuleType("willow2_mod_menu")
    menu_fake.options_menu = types.SimpleNamespace(data_provider_stack=[menu_other, menu_provider])
    sys.modules["willow2_mod_menu"] = menu_fake
    try:
        updater.follow_menu(menu_old, menu_new)
    finally:
        del sys.modules["willow2_mod_menu"]
    assert menu_provider.mod is menu_new and menu_provider.drawn_options[2:] == list(menu_new.opts), menu_provider
    assert menu_provider.drawn_options[0] is menu_extra and menu_provider.drawn_options[1] is not menu_old.group
    assert menu_provider.options[1].identifier == "Options" and menu_provider.options[1] is not menu_old.group
    assert menu_other.drawn_options[0] not in menu_new.opts, "another mod's menu: untouched"
    updater.follow_menu(menu_old, menu_new)  # (no willow2_mod_menu: nothing done, nothing raised)
    # The Port slider: applied on leaving the options, not per step, and in a thread (a restart on the game thread froze
    # it); Open Map in Browser with it not applied yet: restarted first, then the page; after a disable: nothing started
    port_calls: list[str] = []
    port_saved = upd_mod._start, getattr(upd_mod.os, "startfile", None)
    upd_mod._start = lambda **_kw: port_calls.append("start")
    upd_mod.os.startfile = lambda url: port_calls.append("open " + url)

    def port_wait() -> None:
        for port_thread in [t for t in threading.enumerate() if t.name == "helios_tracker restart"]:
            port_thread.join(5)

    try:
        upd_mod._serving[0] = True
        upd_mod._on_port(None, 9000.0)
        assert port_calls == [] and upd_mod._port_changed[0], ("a slider step: nothing restarted", port_calls)
        upd_mod._open_page(None)
        port_wait()
        assert port_calls == ["start", "open " + upd_mod._url()] and not upd_mod._port_changed[0], port_calls
        port_calls.clear()
        upd_mod._open_page(None)
        assert port_calls == ["open " + upd_mod._url()], ("applied: just opened", port_calls)
        port_calls.clear()
        upd_mod._serving[0] = False
        upd_mod._restart_soon()
        port_wait()
        assert port_calls == [], ("disabled meanwhile: no server started", port_calls)
    finally:
        upd_mod._start = port_saved[0]
        if port_saved[1] is None:
            del upd_mod.os.startfile
        else:
            upd_mod.os.startfile = port_saved[1]
        upd_mod._serving[0] = upd_mod._port_changed[0] = False
    print("  updater: a newer release downloaded, verified and swapped in; older / mismatched / folder install left alone; an open options menu follows a reload")


def check_ingame_text() -> None:
    """i18n.py, the in-game text (options, the updater's boxes): the page's nine languages, every key in each, the same
    {placeholders} as English; the game's language picks the catalog (unknown: English)."""
    import string  # noqa: PLC0415

    from helios_tracker import i18n  # noqa: PLC0415

    page_langs = sorted(f.stem for f in (ROOT / "helios_tracker" / "web" / "i18n").glob("*.js") if f.stem != "index")
    assert sorted(i18n.TEXT) == page_langs, ("the page's languages", sorted(i18n.TEXT), page_langs)
    assert sorted(i18n.GAME_LANGS.values()) == page_langs, "every language reachable from a game language"

    def holes(text: str) -> set[str]:
        return {name for _, name, _, _ in string.Formatter().parse(text) if name}

    english = i18n.TEXT["en"]
    for lang, catalog in i18n.TEXT.items():
        assert catalog.keys() == english.keys(), (lang, sorted(catalog.keys() ^ english.keys()))
        for key, text in catalog.items():
            assert text.strip(), (lang, key, "empty")
            assert holes(text) == holes(english[key]), (lang, key, holes(text), holes(english[key]))
    try:
        i18n.set_game_language("FRA")
        assert i18n.language() == "fr" and i18n.t("update.ok") == "OK"
        assert i18n.t("update.latest", ours="v1.2.3") == "Vous avez la dernière version (v1.2.3)."
        i18n.set_game_language("TWN")
        assert i18n.t("update.cancel") == "取消"
        i18n.set_game_language("XYZ")
        assert i18n.language() == "en", "unknown: English"
        i18n.set_game_language("")
        assert i18n.t("check.name") == "Check for Updates"
    finally:
        i18n.set_game_language("")
    print(f"  in-game text: {len(i18n.TEXT)} languages x {len(english)} keys, placeholders matching English")


def main() -> None:
    _install_fakes()
    check_helios_tracker()
    check_script()
    check_sdkmod()
    check_updater()
    check_ingame_text()
    print("OK")


if __name__ == "__main__":
    main()
