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

    mb.BoolOption = mb.SliderOption = mb.SpinnerOption = mb.DropdownOption = mb.ButtonOption = Opt
    mb.NestedOption = mb.GroupedOption = Nested
    mb.hook = lambda *a, **k: (lambda f: f)
    mb.build_mod = lambda **k: types.SimpleNamespace(**k)
    mb.Library = type("Library", (), {})
    mb.Mod = object
    mb.EInputEvent = types.SimpleNamespace(IE_Pressed=0, IE_Released=1, IE_Repeat=2)

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


# endregion


GAME_COOKED = Path(r"E:\SteamLibrary\steamapps\common\Borderlands 2\WillowGame\CookedPCConsole")

# Run as an ES module: node test.mjs <web dir> <image file>
PAGE_TEST_JS = """
import fs from "node:fs";
import crypto from "node:crypto";
import path from "node:path";
import { pathToFileURL } from "node:url";
const [web, imageFile] = process.argv.slice(2);
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
  for (const north of [0, 30]) { // map -> world undoes world -> map, north offset included
    const turned = { ...level, north };
    const [wx, wy] = mapToWorld(turned, ...worldToMap(turned, x, y));
    back = Math.max(back, Math.hypot(wx - x, wy - y));
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
  view: { follow: 1, motion: 15 }, ui: { openLayers: ["loot", 3] } });
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
// The game's rarity table (tools/probe_rarity3.txt): 7-10 share legendary's colour entry; 503 has no name
setRarityTable({ "5": [5, "#ffb400"], "9": [7, "#ffb400"], "501": [13, "#ff9ab8"], "503": [15, "#9132c8"] });
const gameRarity = [5, 9, 501, 503].map((q) => rarity(q)).concat([lootLayer({ q: 9, c: "WillowWeapon" })]);
setRarityTable(null);
const unknownSettings = LAYERS.flatMap((l) => l.settings.filter((k) => !LAYER_SETTINGS[k]).map((k) => l.id + "." + k));
// Missions: state (available = every mission it needs done), the tree, objective states
const { missionTree, objectiveStates, missionCounts, missionAreas } = await load("js/missions.js");
const log = [
  { i: "a", num: 1, plot: 1, st: "Complete", deps: [] }, { i: "b", num: 2, plot: 1, st: "Active", deps: ["a"],
    obj: [{ c: 1 }, { c: 5 }, { c: 1, opt: 1 }], p: [1, 3], cur: [1, 2] },
  { i: "c", num: 3, plot: 1, st: "NotStarted", deps: ["b"] }, { i: "s1", num: 20, plot: 0, st: "NotStarted", deps: ["a"], kick: 1 },
  { i: "s3", num: 22, plot: 0, st: "NotStarted", deps: ["a"] },
  { i: "s2", num: 21, plot: 0, st: "NotStarted", deps: ["s1"] }, { i: "o", num: 30, plot: 0, st: "Complete", deps: [] },
  { i: "x", num: 40, plot: 0, st: "RequiredObjectivesComplete", deps: ["gone"] }];
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
const finishLog = [{ i: "f1", num: 1, st: "Active", deps: [], ml: 3, mlk: 1 }, { i: "f2", num: 2, st: "Active", deps: [], ml: 7, mlk: 1 },
  { i: "f3", num: 3, st: "NotStarted", deps: [], ml: 2 }, { i: "f4", num: 4, st: "Active", deps: [], ml: 1, mlk: 1 }];
const finish = rankMissions(finishLog, "finish", 8).rows.map((r) => `${r.m.i}:${r.score}`).join(",");
// a mission the game rates impossible for the player (5+ levels above): left out, counted
const highLog = [{ i: "ok", num: 1, st: "Active", deps: [], ml: 9, mlk: 1, rw: { "8": { xp: 100 } } },
  { i: "dlc", num: 2, st: "Active", deps: [], ml: 30, mlk: 1, rw: { "8": { xp: 7890 } } }];
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
const missionsOut = { tooHigh, finish, difficulty, best, search, infoHtml, areas, gameText, story: flat(tree.story), other: flat(tree.other), counts: missionCounts(log),
  objectives: objectiveStates(log[1]).map((s) => s.state) };
console.log(JSON.stringify({ sha: crypto.createHash("sha256").update(rgba).digest("hex"), err, back, right, raw, modules, missions: missionsOut,
  migrated, checked: { enemy: checked.layers.enemy, view: checked.view, openLayers: checked.ui.openLayers }, i18nKeys, unknownSettings, lootLayers, gameRarity, freeRects }));
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

    # field(): the property looked up once per class, then read with _get_field (tools/probe_perf.txt)
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
    if not GAME_COOKED.is_dir():
        print("  game files not found: skipping the map / server checks")
        return
    # Map images straight from the game's packages
    for level_name, size in {"Sanctuary_P": (468, 512), "SouthernShelf_P": (876, 1024)}.items():
        t = time.perf_counter()
        (img,) = load_tactical_map(GAME_COOKED / f"{level_name}.upk", f"UI_TacticalMap_{level_name[:-2]}.{level_name}")
        assert (img.format, img.width, img.height) == ("PF_DXT5", *size), img
        print(f"  {level_name}: {img.name} {img.width}x{img.height} {img.format}, bounds {img.bounds}"
              f" ({time.perf_counter() - t:.2f} s)")
    # A DLC map: its package is under DLC/<code name>/{Lic,Compat}/Content (the collector's package_path)
    real_cooked = col.cooked_dir
    col.cooked_dir = lambda: GAME_COOKED
    try:
        dlc = col.package_path("Sage_Underground_P.upk")
        assert dlc is not None and "DLC" in dlc.parts, dlc
        assert col.package_path("Sanctuary_P.upk") == GAME_COOKED / "Sanctuary_P.upk" and col.package_path("Nope_P.upk") is None
        t = time.perf_counter()
        (img,) = load_tactical_map(dlc, "Sage_UI_TacticalMap_Undergrnd.Undergrnd_P")
        assert (img.format, img.width, img.height) == ("PF_DXT5", 1024, 644), img
        print(f"  Sage_Underground_P (DLC): {img.name} {img.width}x{img.height} ({time.perf_counter() - t:.2f} s)")
    finally:
        col.cooked_dir = real_cooked

    # A level load through the collector (fake world); the map is extracted on its thread
    ns = types.SimpleNamespace
    # A respawning player (tools/probe_respawn.txt): hidden + awaiting a respawn -> their New-U spot
    spot = ns(X=19361.0, Y=-27830.0, Z=1581.0)
    # Down states (tools/probe_respawn.txt): crippled / dead / fine
    injured = enum.Enum("EInjuredStage", ["INJURED_Not", "INJURED_Targeted"], start=0)
    dead_state = enum.Enum("EInjuredDeadState", ["INJUREDDEAD_None", "INJUREDDEAD_InitRagdoll"], start=0)
    down_state = col.Collector._down_state
    assert down_state(ns(InjuredState=injured.INJURED_Targeted, InjuredDeadState=dead_state.INJUREDDEAD_None)) == "crippled"
    assert down_state(ns(InjuredState=injured.INJURED_Targeted, InjuredDeadState=dead_state.INJUREDDEAD_InitRagdoll)) == "dead"
    assert down_state(ns(InjuredState=injured.INJURED_Not, InjuredDeadState=dead_state.INJUREDDEAD_None)) == ""
    assert down_state(ns()) == "", "no InjuredState: fine"
    respawn_state = col.Collector._respawn_state
    # Skills (tools/probe_passives.txt): the manager's running timed skills by player; the action skill
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
    # a hidden helper (Krieg's BloodOverdriveChild, dev text for a name, in no tree): shown as the tree
    # skill with its icon (tools/probe_child_skill.txt)
    icon = ns(_path_name=lambda: "UI_Lilac_SharedSkillIcons_Psyc.SkillIcon-Psycho04")
    overdrive = skill_def(0x904, "Surcharge sanglante", skill_type.SKILL_TYPE_Passive, timed=False)
    overdrive.SkillIcon = icon
    child = skill_def(0x905, "Blood Overdrive Child - If you are reading this please bug it!", skill_type.SKILL_TYPE_Passive)
    child.SkillIcon = icon
    krieg_pc = ns(_get_address=lambda: 0x951, PlayerSkillTree=ns(Skills=[ns(Definition=overdrive)]))
    manager.ActiveSkills = [ns(Definition=child, SkillState=skill_state.SKILL_Active, StartTime=1640.0, Duration=8.0,
                               SkillInstigator=krieg_pc)]
    reader.update(player_pc, 1642.0, 12.0)
    assert reader._by_pc[0x951]["timed"] == [("Surcharge sanglante", 6.0, 8.0)], reader._by_pc
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
            _get_address=lambda: addr, Name=name, Class=ns(Name="WillowAIPawn"), bDeleteMe=False, bIsDead=False,
            Location=ns(X=x, Y=y, Z=3690.0), Rotation=ns(Yaw=16384), GetMaxHealth=lambda: 100.0,
            GetHealth=lambda: 40.0, IsEnemy=lambda other: enemy, GetExpLevel=lambda: 12,
            GetShieldStrength=lambda: 25.0, GetMaxShieldStrength=lambda: 50.0 if enemy else 0.0, GetTargetName=lambda *out: (..., name.title()) if out else ...,  # out param only
            NextPawn=nxt, PlayerReplicationInfo=None,
        )

    seat = pawn(0x210, "seat", 10000.0, 3000.0)  # a vehicle's turret seat: not shown
    seat.Class = ns(Name="WillowWeaponPawn", SuperField=None)
    enemy = pawn(0x200, "bullymong", 10000.0, 3000.0, nxt=seat, enemy=True)
    me = pawn(0x100, "me", 10635.4, 5702.0, nxt=enemy)
    me.Class = ns(Name="WillowPlayerPawn", SuperField=None)
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
    weapon = ns(
        _get_address=lambda: 0x300, Class=ns(Name="WillowWeapon", SuperField=None), Inventory=None,
        GetShortHumanReadableName=lambda: "Unkempt Harold", RarityLevel=5, ExpLevel=30, MonetaryValue=4321,
        InstantHitDamage=512.4, ProjectilesPerShot=3.0, FireInterval=0.25, ClipSize=16.0, ReloadTime=2.25,
        QuickSelectSlot=1, DefinitionData=weapon_data,
    )
    shield = ns(
        _get_address=lambda: 0x301, Class=ns(Name="WillowShield", SuperField=None), Inventory=None,
        GetShortHumanReadableName=lambda: "Adaptive Shield", RarityLevel=2, ExpLevel=28, MonetaryValue=900,
        DefinitionData=None,
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
    col.cooked_dir = lambda: GAME_COOKED
    barrel = ns(  # an interactive object whose display name comes from its balance definition
        Name="WillowInteractiveObject_3", Outer=ns(Class=ns(Name="Level")), bDeleteMe=False, bHidden=False,
        Location=ns(X=9000.0, Y=1000.0, Z=3690.0), InteractiveObjectDefinition=ns(Name="IO_FireBarrel"),
        BalanceDefinitionState=ns(BalanceDefinition=ns(DefaultDisplayName="Incendiary Barrel")),
        Class=ns(Name="WillowInteractiveObject"), _get_address=lambda: 0x500,
        GetTargetName=lambda: "", GetHumanReadableName=lambda: "",
    )
    # The mission tracker (as seen in game, tools/probe_missions.txt): one tracked mission with an
    # active area objective and an inactive one, plus an active quest giver on an NPC
    # The mission log (tools/probe_quests.txt): MissionList entries {MissionDef, Status,
    # ObjectivesProgress (per ObjectiveDefs entry), ActiveObjectiveSet}; a done story mission, the
    # tracked one (3 objectives, the current step = the last two), a side mission it unlocked
    # (available) and one needing the tracked mission (locked)
    status = enum.Enum("EMissionStatus", ["MS_NotStarted", "MS_Active", "MS_Complete"], start=0)
    secure = ns(Name="Securethetown", ProgressMessage="Sécuriser la ville", ObjectiveCount=1, _get_address=lambda: 0x650)
    kill = ns(Name="KillBandits", ProgressMessage="Tuer des bandits", ObjectiveCount=5, _get_address=lambda: 0x651)
    extra = ns(Name="Bonus", ProgressMessage="Bonus", ObjectiveCount=1, bObjectiveIsOptional=True, _get_address=lambda: 0x652)

    def mission_def(addr: int, path: str, name: str, number: int, plot: bool, deps: list, objectives: list = ()) -> object:
        return ns(_get_address=lambda: addr, _path_name=lambda: path, Name=path.split(".")[-1], MissionName=name,
                  MissionNumber=number, bPlotCritical=plot, Dependencies=deps, ObjectiveDefs=list(objectives),
                  MissionDescription="[place]Liar's Berg[-place] needs you.", MissionGiver="Claptrap", GameStage=3,
                  TravelStation=ns(StationDisplayName="Southern Shelf") if number < 20 else None)

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
        waypoint(0x702, ns(Location=ns(X=5.0, Y=6.0, Z=7.0)), True, cls="MissionDirectiveWaypointComponent"),
    ])])
    real_find_all = col.unrealsdk.find_all
    col.unrealsdk.find_all = lambda cls, exact=True: {"WillowInteractiveObject": [barrel], "MissionTracker": [tracker]}.get(cls, [])
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
        level = json.loads(hub._channels["level"][1])
        if level["status"] != "loading":
            break
        time.sleep(0.05)
    assert level["status"] == "ready" and level["upp"] == 128.0 and level["center"] == [-3072.0, -10240.0], level
    assert (level["zmin"], level["zmax"]) == (-4096, 12288), level
    state = json.loads(hub._channels["state"][1])
    kinds = {p["n"]: p["k"] for p in state["pawns"]}
    assert not any(p.get("raw") for p in state["pawns"]), state["pawns"]  # both have game names
    assert all(p.get("l") == 12 for p in state["pawns"]), state["pawns"]
    assert state["hz"] == 10.0, state.get("hz")
    shields = {p["n"]: (p.get("s"), p.get("sm")) for p in state["pawns"]}
    assert shields == {"Zer0": (60.0, 120.0), "Bullymong": (25.0, 50.0)}, shields  # properties / functions
    assert kinds == {"Zer0": "me", "Bullymong": "enemy"}, kinds
    print(f"  collector: level {level['name']!r} {level['status']}, pawns {kinds}")
    (player,) = json.loads(hub._channels["players"][1])["players"]
    (gun,) = player["equipped"]
    assert (player["n"], player["local"], player["cls"], player["inventory"]) == ("Zer0", True, "Assassin", "full"), player
    assert "clsRaw" not in player and player["char"] == "Zer0", player  # localized, via CharacterClassId
    assert player["xp"] == [7851, 8861], player["xp"]  # in this level / the level's size
    assert gun["k"] == "weapon" and gun["stats"][0] == ["damage", 512, 3] and gun["slot"] == 1, gun
    assert (gun["type"], gun["maker"]) == ("Sub-Machine Gun", "Hyperion+"), gun
    parts = {slot: (name, group, text) for slot, name, group, text in gun["parts"]}
    assert parts["Barrel"] == ("SMG_Barrel_Hyperion", "Barrel", "") and parts["Title"][2] == "Bitch", parts
    (obj,) = json.loads(hub._channels["objects"][1])["objects"]
    assert obj["n"] == "Incendiary Barrel" and "raw" not in obj and obj["d"] == "IO_FireBarrel", obj
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
    names = [o["n"] for o in json.loads(hub._channels["objects"][1])["objects"]]
    assert names == ["Incendiary Barrel", "Explosive Gas Tank", "Treasure Chest"], names
    chest.bCanBeUsed = (0, 0)  # opened: use off at once (the anim state only follows)
    c.object_usability_changed(chest)  # the SetUsability hook
    c.tick(1001.35)
    looted = {o["n"]: (o.get("lootable"), o.get("looted")) for o in json.loads(hub._channels["objects"][1])["objects"]}
    assert looted["Treasure Chest"] == (1, 1) and looted["Incendiary Barrel"] == (None, None), looted
    contents = {o["n"]: o.get("loot") for o in json.loads(hub._channels["objects"][1])["objects"]}
    objs = {o["n"]: o for o in json.loads(hub._channels["objects"][1])["objects"]}
    chest_rec = objs["Treasure Chest"]
    assert (chest_rec["loot"], chest_rec["slots"], chest_rec["lists"]) == (["Pool_GunsAndGear"], 4, ["EpicChestRedLoot"]), chest_rec
    assert "loot" not in objs["Incendiary Barrel"], objs["Incendiary Barrel"]
    c.object_destroyed(barrel)  # it exploded
    c.tick(1001.4)
    names = [o["n"] for o in json.loads(hub._channels["objects"][1])["objects"]]
    assert names == ["Explosive Gas Tank", "Treasure Chest"], names
    missions = json.loads(hub._channels["missions"][1])
    assert missions["tracked"] == {"n": "Ménage à Liar's Berg"}, missions
    obj_mk, giver = missions["markers"]  # the inactive objective is left out
    assert (obj_mk["k"], obj_mk["rad"], obj_mk["tracked"], obj_mk["objective"]) == (
        "objective", 2125, True, {"n": "Sécuriser la ville"}), obj_mk
    assert (giver["k"], giver["rad"], "objective" in giver) == ("directive", 0, False), giver
    # The mission log: full pass (every entry, definitions cached), then the fast pass (the tracked /
    # active missions, every second) picks up progress
    def merged_log() -> dict:  # what the page builds: the definitions + the live part, by id
        defs = {m["i"]: m for m in json.loads(hub._channels["missiondefs"][1])["missions"]}
        live = json.loads(hub._channels["missionlog"][1])
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
    assert (tracked["ml"], tracked.get("mlk")) == (3, 1), "picked up: its level, locked"
    assert (by_id["GD_Z1_Side.M_Side"]["ml"], by_id["GD_Z1_Side.M_Side"].get("mlk")) == (3, None), "not picked up: the level it would lock at"
    assert "ml" not in by_id["GD_Episode02.M_Ep2_Henchman"], "done: no level read"
    assert by_id["GD_Z1_Side.M_Side"].get("kick") == 1 and "kick" not in by_id["GD_Z1_Later.M_Later"], "offered flag (bHeardKickoff)"
    # the full pass in slices (a few entries per tick): nothing applied until the cycle completes
    from helios_tracker import missions as sliced  # noqa: PLC0415

    chunked = sliced.MissionLog()
    steps = 0
    while not chunked.step(tracker, lambda: [], budget=1):
        steps += 1
        assert chunked.in_cycle and not chunked.payload(1)["missions"], "applied before the cycle completed"
    assert steps == len(log_entries) - 1 and [m["st"] for m in chunked.payload(1)["missions"]] == [m["st"] for m in log["missions"]], steps
    # rewards per player level (tools/probe_rewards.txt: MissionDefinition.GetExperienceReward(pc, bAlt))
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
    version = hub._channels["missionlog"][0]
    c.tick(1001.5)  # nothing changed: not published again
    assert hub._channels["missionlog"][0] == version, "mission log republished with no change"
    log_entries[1].ObjectivesProgress = [1, 4, 0]  # a kill
    c.tick(1002.6)  # the next marker read (1 s): the fast pass
    tracked = next(m for m in merged_log()["missions"] if m["i"] == tracked["i"])
    assert tracked["p"] == [1, 4, 0], tracked
    assert [b["k"] for b in player["backpack"]] == ["shield"], player["backpack"]
    assert player["host"] is True, "solo / listen server: the mod's player hosts"
    assert player["skills"][0]["n"] == "Sniping" and player["skills"][0]["skills"][0]["g"] == 4, player["skills"]
    assert player["skills"][0]["pts"] == 4 and not player["skills"][0].get("root"), player["skills"]
    (tier,) = player["skills"][0]["tiers"]
    assert tier["need"] == 5 and tier["cells"][0]["g"] == 4 and tier["cells"][1:] == [None, None], tier
    # a co-op client, another player: no inventory manager, their equipped gear on the pawn (tools/probe_coop.txt)
    inspector = sys.modules["helios_tracker.inspector"]
    remote = {"local": False}
    inspector._inventory(ns(InvManager=None, Weapon=weapon, HolsteredWeaponSlots=[weapon, None],
                            EquippedItems=[shield, None, None, None]), remote)
    assert remote["inventory"] == "partial" and [i["k"] for i in remote["equipped"]] == ["weapon", "shield"], remote
    assert remote["inventoryWhy"] == "coopClient" and "backpack" not in remote, remote
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
        web_files = sorted(p for p in web.rglob("*") if p.suffix in (".js", ".css"))
        for file in web_files:  # every module / stylesheet, at its path under web/
            conn.request("GET", "/" + file.relative_to(web).as_posix())
            res = conn.getresponse()
            body = res.read()
            want_type = "text/css" if file.suffix == ".css" else "text/javascript"
            assert res.status == 200 and res.headers["Content-Type"].startswith(want_type), (file, res.status)
            assert body == file.read_bytes(), file
        for bad in ("/../server.py", "/js/../../server.py", "/web/js/main.js", "/JS/MAIN.JS", "/js/main.py"):
            conn.request("GET", bad)
            res = conn.getresponse()
            res.read()
            assert res.status == 404, (bad, res.status)
        conn.request("GET", "/image/999/0")
        res = conn.getresponse()
        res.read()
        assert res.status == 404, res.status
        sse = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        sse.request("GET", "/events")
        res = sse.getresponse()
        assert res.headers["Content-Type"] == "text/event-stream", res.headers
        events = set()
        while len(events) < 7:
            line = res.fp.readline().decode()
            if line.startswith("event: "):
                events.add(line[7:].strip())
        assert events == {"level", "state", "objects", "players", "missions", "missiondefs", "missionlog"}, events
        print(f"  server: page {len(page)} bytes + {len(web_files)} js / css files, image {len(image)} bytes,"
              f" SSE events {sorted(events)}")
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

    # The page's JS: DXT decoding (against the reference decoder above) and world -> map
    node = shutil.which("node")
    if node is None:
        print("  node not found: skipping the page's JS checks")
        return
    want = hashlib.sha256(_dxt5_rgba(468, 512, image)).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "img.bin").write_bytes(image)
        (Path(tmp) / "test.mjs").write_text(PAGE_TEST_JS, encoding="utf-8")
        out = subprocess.run([node, str(Path(tmp) / "test.mjs"), str(web), str(Path(tmp) / "img.bin")],
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
    assert mig["layers"]["enemy"] == {"on": False, "names": True, "floors": "show", "size": 100, "range": 0}, mig["layers"]
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
    assert mig["layers"]["player"] == {"names": True, "floors": "show", "size": 100}, mig["layers"]["player"]
    assert mig["view"]["zoom"] == 2.5 and mig["view"]["motion"] == 0, mig["view"]
    assert mig["ui"]["lang"] == "fr" and mig["ui"]["inspectorTab"] == "skills", mig["ui"]
    chk = js["checked"]
    assert chk["enemy"] == {"on": True, "names": False, "floors": "dim", "size": 200, "range": 0}, chk
    assert chk["view"]["follow"] is False and chk["view"]["motion"] == 15 and chk["openLayers"] == ["loot"], chk
    assert not js["unknownSettings"], js["unknownSettings"]
    missing = sorted(k for k in js["i18nKeys"] if k not in langs["en"])
    assert not missing, ("layer panel keys missing from the catalogs", missing)
    mis = js["missions"]
    assert mis["story"] == ["a:done", "-s1:available", "--s2:locked", "-s3:unknown", "b:active", "c:locked"], mis["story"]
    assert mis["other"] == ["o:done", "x:other"], mis["other"]
    assert mis["counts"] == {"done": 2, "active": 1, "available": 1, "unknown": 1, "locked": 2, "other": 1}, mis["counts"]
    assert mis["objectives"] == ["done", "current", "current"], mis["objectives"]
    assert mis["areas"] == ["Shelf:b", "Sanctuary:da", ":c"], mis["areas"]
    assert mis["search"] == ["a:done", "b:locked,a:done", "b:locked", "", ""], mis["search"]
    assert mis["difficulty"] == ["impossible", "tough", "normal", "normal", "trivial", None, None], mis["difficulty"]
    assert mis["finish"] == "f4:7,f1:5,f2:1", mis["finish"]
    assert mis["tooHigh"] == {"rows": ["ok"], "n": 1, "lv": 30, "total": 100}, mis["tooHigh"]  # picked up only, the furthest behind first
    best = mis["best"]  # u counts its alternative reward (2000 XP); l2 (two steps away) and d (done) are out; e: no reward known
    assert (best["xp"], best["cash"], best["effort"]) == ("ual3vl1ery", "vual1l3ery", "vual3l1ery"), best
    assert best["after"] == ["a"] and best["total"] == 12600 and best["otherLevel"] == 0, best
    me_info, down_info, gone_info = mis["infoHtml"]
    for want in ("Fine", "Shield", "60 / 100", "Level 30", "500 / 1,000", "Gunzerking", "Active · 12 s", "Locked and Loaded - active", "4 s", "Melee skill", "8 s"):
        assert want in me_info, (want, me_info)
    assert "Crippled" in down_info and "Not known here" in down_info, down_info
    assert "Not in this area" in gone_info, gone_info
    assert mis["gameText"] == ["Go to Sanctuary.<br>Find Roland &amp; win<br>x", "Line one. Line two here"], mis["gameText"]
    print(f"  page JS: {len(js['modules'])} modules import under Node, DXT5 decode matches,"
          f" world->map within {js['err']:.3f} px of the probe samples")


def main() -> None:
    _install_fakes()
    check_helios_tracker()
    print("OK")


if __name__ == "__main__":
    main()
