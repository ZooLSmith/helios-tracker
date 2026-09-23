"""
Offline sanity check (plain Python, no game): imports z_hud_overlay and the mods with fake SDK
modules, runs their per-frame draw path against a fake overlay, and validates the Scaleform movies
they generate.

    python tools/offline_check.py

Catches import errors, typos in the draw path, and malformed SWF output - not in-game behaviour.
"""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ammo_counter"))  # for swf_inspect


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


class FakeOverlay:
    """Stands in for z_hud_overlay.Overlay: records what the mod asks it to show."""

    generation = 1
    ready = True

    def __init__(self) -> None:
        self.texts: dict[str, list] = {}
        self.updates = 0

    visible = True

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False

    def close(self) -> None: ...

    def set_priority(self, priority: int) -> None:
        self.priority = priority

    def measure(self, text: str) -> tuple[float, float]:
        return (len(text) * 14.0, 30.0)

    def set_texts(self, group: str, draws: list) -> None:
        self.texts[group] = draws
        self.updates += 1

    def set_backdrops(self, draws: list) -> None:
        self.backdrops = draws


# endregion


def check_swf(data: bytes, label: str) -> None:
    import swf_inspect as S  # noqa: PLC0415

    tmp = ROOT / "tools" / "_check.gfx"
    tmp.write_bytes(data)
    try:
        _, _, body = S.load(str(tmp))
        counts: dict[str, int] = {}
        for code, _ in S.tags(body):
            counts[S.TAGNAMES.get(code, str(code))] = counts.get(S.TAGNAMES.get(code, str(code)), 0) + 1
    finally:
        tmp.unlink()
    print(f"  {label}: {len(data)} bytes, tags {counts}")


def check_ammo_counter() -> None:
    import ammo_counter as m  # noqa: PLC0415

    print("ammo_counter:")
    check_swf(m._overlay.build_swf("check"), "movie")
    fake = _use_fake_overlay(m)
    m._icons = types.SimpleNamespace(set=lambda icons: setattr(fake, "icons", icons))
    m._reader = types.SimpleNamespace(values=lambda pc, e: tuple((100 + i, 200) for i in range(len(e))))
    canvas = types.SimpleNamespace(SizeX=1920, SizeY=1080)
    args = types.SimpleNamespace(Canvas=canvas)

    m.on_post_render(None, args, None, None)
    m.on_post_render(None, args, None, None)  # unchanged: must not update again
    assert fake.updates == 2, fake.updates  # txt + max, once
    m.number_format.value = m.NUMBER_CURRENT_MAX
    m.on_post_render(None, args, None, None)
    assert m.widget.frame._logged == set(), m.widget.frame._logged
    assert fake.backdrops == [], "backdrop drawn while off"
    m.backdrop.enabled.value = True
    m.on_post_render(None, args, None, None)
    b0, c0 = fake.backdrops[0], fake.icons[0]
    assert len(fake.backdrops) == 6 and b0.x < c0.x and b0.w > c0.size, (b0, c0)
    print(f"  backdrops: {len(fake.backdrops)}, first {b0}")
    m.backdrop.whole.value = True
    m.on_post_render(None, args, None, None)
    (whole,) = fake.backdrops
    assert abs(whole.x - b0.x) < 1e-6 and whole.h > 5 * b0.h, (whole, b0)
    print(f"  whole bounding box: {whole}")
    m.backdrop.whole.value = False
    m.backdrop.pad_x.value, m.backdrop.pad_y.value = -500, -500  # negative past the content: nothing
    m.on_post_render(None, args, None, None)
    assert all(b.w == 0 and b.h == 0 for b in fake.backdrops), fake.backdrops
    m.backdrop.pad_x.value, m.backdrop.pad_y.value = 10, 3
    m.backdrop.enabled.value = False
    print(f"  icons: {len(fake.icons)}, first {fake.icons[0]}")
    print(f"  txt[0]: {fake.texts['txt'][0]}")
    print(f"  max[0]: {fake.texts['max'][0]}")
    print(f"  options: {[getattr(o, 'identifier', o) for o in m.mod.options]}")


def _use_fake_overlay(m) -> FakeOverlay:  # noqa: ANN001
    fake = FakeOverlay()
    m.widget.overlay = m._overlay = fake
    m.widget._visible = lambda pc, positioning: True
    return fake


def _run_frames(m, n: int = 2) -> FakeOverlay:  # noqa: ANN001
    fake = _use_fake_overlay(m)
    args = types.SimpleNamespace(Canvas=types.SimpleNamespace(SizeX=1920, SizeY=1080))
    for _ in range(n):
        m.on_post_render(None, args, None, None)
    assert m.widget.frame._logged == set(), m.widget.frame._logged
    return fake


def check_nudge() -> None:
    """Arrow keys in Placement Mode: tap = 1 step, hold = accelerating movement, wheel = scale."""
    from z_hud_overlay import Placement, nudge  # noqa: PLC0415

    clock = [1000.0]
    nudge.time.monotonic = lambda: clock[0]  # drive time by hand

    def key(name: str, event: int) -> object:
        return nudge.on_input_key(None, types.SimpleNamespace(Key=name, Event=event), None, None)

    pl = Placement(x=500, y=500, scale=100)
    assert key("Right", 0) is None  # nobody in Placement Mode: input untouched
    pl.placement_mode.value = True
    assert not pl.apply_nudge()  # first call only syncs
    assert key("Right", 0) is nudge.Block  # tap: captured
    assert pl.apply_nudge() and pl.x.value == 501, pl.x.value
    clock[0] += 0.2  # still within the hold delay: no extra movement
    pl.apply_nudge()
    assert pl.x.value == 501, pl.x.value
    for _ in range(100):  # hold 1 more second, 10 ms frames
        clock[0] += 0.01
        pl.apply_nudge()
    held_1s = pl.x.value
    for _ in range(100):  # and another second: faster
        clock[0] += 0.01
        pl.apply_nudge()
    assert pl.x.value - held_1s > held_1s - 501 > 10, (held_1s, pl.x.value)
    key("Right", 1)
    stop = pl.x.value
    clock[0] += 0.5
    pl.apply_nudge()
    assert pl.x.value == stop, "moved after release"
    key("MouseScrollUp", 0)
    pl.apply_nudge()
    assert pl.scale.value == 105, pl.scale.value
    pl.placement_mode.value = False
    pl.apply_nudge()
    clock[0] += 1.0  # past the capture timeout
    assert key("Right", 0) is None  # Placement Mode off: input back to the game
    from z_hud_overlay.options import DEFAULT_LAYER, layer_to_priority  # noqa: PLC0415

    assert (layer_to_priority(0), layer_to_priority(DEFAULT_LAYER), layer_to_priority(20)) == (0, 204, 255)
    assert layer_to_priority(99) == 255  # clamped
    print(f"nudge: OK (tap 500->501, held 1 s -> {held_1s}, 2 s -> {stop}, wheel scale 100->105)")


def check_cooldown_math() -> None:
    from skill_timer.cooldown import drain_time  # noqa: PLC0415

    # No modifiers: value / rate (rate > 1 = a permanent cooldown bonus)
    assert drain_time(12.0, 1.0, []) == 12.0
    assert abs(drain_time(12.0, 1.5, []) - 8.0) < 1e-9
    # Probe run 1 (Tactical Withdrawal refund): pool 40.978, rate 12.112, boost 2.47 s left.
    # Observed: the boost ended at pool ~11.7, then 1/s -> real time left ~ 2.45 + 11.7
    t = drain_time(40.978, 12.112, [(11.112, 2.47)])
    assert 13.0 < t < 14.5, t
    # Refund bigger than what's left: it just drains during the boost
    assert abs(drain_time(10.0, 12.0, [(11.0, 2.5)]) - 10.0 / 12.0) < 1e-9
    print(f"cooldown math: OK (probe run 1 -> {t:.2f} s real time left)")


def check_skill_timer() -> None:
    import skill_timer as m  # noqa: PLC0415

    print("skill_timer:")
    check_swf(m._overlay.build_swf("check"), "movie")
    fake = _run_frames(m)
    assert fake.updates == 2, fake.updates  # seconds + (empty) fraction, once
    assert fake.texts["ms"] == [], fake.texts["ms"]
    print(f"  whole seconds: {fake.texts['t'][0]}")
    m.decimals.value = 2
    fake = _run_frames(m, 1)
    sec, frac = fake.texts["t"][0], fake.texts["ms"][0]
    assert (sec.text, frac.text) == ("12", ".34"), (sec.text, frac.text)
    print(f"  with ms: '{sec.text}' + '{frac.text}' (fraction at x={frac.x:.1f}, scale {frac.scale})")
    # Cooldown finished: vanishes - except in Placement Mode, which shows the preview
    pool = sys.modules["mods_base"].get_pc().SkillCooldownPool.Data
    pool.CurrentValue = 0.0
    m._last["key"] = None
    fake = _run_frames(m, 1)
    assert fake.visible is False, "timer still visible when ready"
    m.placement.placement_mode.value = True
    fake = _run_frames(m, 1)
    assert fake.visible is True and fake.texts["t"][0].text == "12", fake.texts
    m.placement.placement_mode.value = False
    pool.CurrentValue = 12.3456
    print("  ready: hidden; ready in Placement Mode: preview 12.34")
    # Running, 25% through a 24 s skill: 18 s of active time, in the active colour
    pc_cls = type(sys.modules["mods_base"].get_pc())
    pc_cls.ActionSkillTime = 0.25
    pool.CurrentValue, pool.ConsumptionRate = 42.0, 0.0  # frozen at max while running
    m.decimals.value = 0
    m._last["key"] = None
    fake = _run_frames(m, 1)
    t = fake.texts["t"][0]
    assert fake.visible and t.text == "18" and t.rgb == m.active_style.rgb, (t, fake.visible)
    m.decimals.value, m._last["key"] = 1, None
    fake = _run_frames(m, 1)
    d = fake.texts["ms"][0]
    assert d.text == ".0" and d.rgb == m.active_ms_style.rgb and d.alpha == m.active_ms_style.alpha, d
    m.show_active.value = False
    m._last["key"] = None
    fake = _run_frames(m, 1)
    assert fake.visible is False, "cooldown shown while running"
    m.show_active.value = True
    m.decimals.value = 2
    pc_cls.ActionSkillTime = -1.0
    pool.CurrentValue, pool.ConsumptionRate = 12.3456, 1.0
    print(f"  running: active time '{t.text}' in the active colour; Show Active Time off: hidden")
    expect = {1: ("12", ".9"), 2: ("12", ".99"), 3: ("12", ".999")}
    for places, want in expect.items():
        m.decimals.value = places
        assert m._format(12.9995) == want, (places, m._format(12.9995))
    m.decimals.value = 0
    assert m._format(12.001) == ("13", ""), m._format(12.001)  # whole seconds round up
    m.decimals.value = 2
    print(f"  options: {[getattr(o, 'identifier', o) for o in m.mod.options]}")


def check_xp_counter() -> None:
    import xp_counter as m  # noqa: PLC0415

    print("xp_counter:")
    check_swf(m._overlay.build_swf("check"), "movie")
    fake = _run_frames(m)
    assert fake.updates == 2, fake.updates  # xp + max, once
    print(f"  total: {fake.texts['xp'][0].text} {fake.texts['max'][0].text}")
    m.mode.value, m.grouping.value = m.MODE_LEVEL, "Space"
    m._reader._t = -1e9  # force a re-read
    fake = _run_frames(m, 1)
    print(f"  level: {fake.texts['xp'][0].text} {fake.texts['max'][0].text}")
    print(f"  options: {[getattr(o, 'identifier', o) for o in m.mod.options]}")


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
const { worldToMap, mapToWorld, yawToAngle } = await load("js/geo.js");
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
console.log(JSON.stringify({ sha: crypto.createHash("sha256").update(rgba).digest("hex"), err, back, right, raw, modules }));
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

    # A level load through the collector (fake world); the map is extracted on its thread
    ns = types.SimpleNamespace
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
    me.HealthVar, me.HealthMaxVar, me.ShieldVar, me.ShieldMaxVar = 141.0, 141.0, 60, 120
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
        Tiers=[ns(Skills=[skill_def], PointsToUnlockNextTier=5)],
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
    mission = ns(_get_address=lambda: 0x600, Name="M_Ep2a_MoreGuns", MissionName="Ménage à Liar's Berg")
    area = ns(Location=ns(X=28354.0, Y=-12060.0, Z=3310.0), AreaRadius=2125)
    secure = ns(Name="Securethetown", ProgressMessage="Sécuriser la ville")

    def waypoint(addr: int, owner: object, active: bool, objective: object = None, cls: str = "MissionObjectiveWaypointComponent") -> object:
        return ns(_get_address=lambda: addr, Class=ns(Name=cls), bActive=active, Owner=owner,
                  WaypointInfo=ns(LinkedObjective=objective))

    tracker = ns(Name="MissionTracker_0", ActiveMission=mission, MissionWaypoints=[ns(Mission=mission, Waypoints=[
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
    assert [b["k"] for b in player["backpack"]] == ["shield"], player["backpack"]
    assert player["skills"][0]["n"] == "Sniping" and player["skills"][0]["skills"][0]["g"] == 4, player["skills"]
    assert player["skills"][0]["pts"] == 4 and not player["skills"][0].get("root"), player["skills"]
    (tier,) = player["skills"][0]["tiers"]
    assert tier["need"] == 5 and tier["cells"][0]["g"] == 4 and tier["cells"][1:] == [None, None], tier
    print(f"  inspector: {player['n']} Lv{player['lvl']} {player['cls']}, {len(player['equipped'])} equipped,"
          f" {len(player['backpack'])} in backpack, skills {[b['n'] for b in player['skills']]};"
          f" gun '{gun['type']}' by '{gun['maker']}'; object '{obj['n']}'")
    print(f"  missions: tracked {missions['tracked']['n']!r}, markers"
          f" {[(m['k'], m['rad'], m.get('objective', {}).get('n')) for m in missions['markers']]}")
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
        while len(events) < 5:
            line = res.fp.readline().decode()
            if line.startswith("event: "):
                events.add(line[7:].strip())
        assert events == {"level", "state", "objects", "players", "missions"}, events
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
    print(f"  page JS: {len(js['modules'])} modules import under Node, DXT5 decode matches,"
          f" world->map within {js['err']:.3f} px of the probe samples")


def main() -> None:
    _install_fakes()
    import z_hud_overlay  # noqa: F401, PLC0415

    print("z_hud_overlay: imported")
    check_nudge()
    check_ammo_counter()
    check_cooldown_math()
    check_skill_timer()
    check_xp_counter()
    check_helios_tracker()
    print("OK")


if __name__ == "__main__":
    main()
