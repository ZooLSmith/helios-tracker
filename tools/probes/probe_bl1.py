# Dev probe (in game), instant, read-only: how far Borderlands 1 (Enhanced, the same Python SDK) is from what the
# mod reads in BL2 - before any change for it. Run it in a level, as the player (not the main menu).
# 1. env: Python, unrealsdk, the game mods_base sees, whether helios_tracker imported (the mod doesn't declare BL1:
#    enabling it is locked, importing isn't).
# 2. hooks: each function the mod hooks (__init__.py's @hook), found or not.
# 3. classes: each class the mod looks up (find_class / find_all), found or not, its live instances.
# 4. level: the world info, its map name, its MapInfo's fields - the map's TacticalMapVolume / TacticalMapMovie
#    (collector._check_level) - and the volume's fields.
# 5. player: the controller, its pawn, their replication info - the fields the collector reads, each failing read
#    shown with its exception (the mod's try_ hides them); the skill tree, discoveries, the mission tracker.
# 6. the fields of the main classes (names and types), to compare with BL2's (WillowPlayerController, WillowPawn,
#    WillowPickup, WillowInteractiveObject, MapInfo...).
# 7. samples: a few pickups / interactive objects / waypoints, their fields.
# Properties only; the calls are the ones the mod already makes every frame (GetCurrentWorldInfo,
# GetStreamingPersistentMapName, GetMapInfo). Writes tools/probes/probe_bl1.txt after each section (appends).
#   py exec(open(r"<repo>\tools\probes\probe_bl1.py").read())
from enum import Enum
import sys
from pathlib import Path

import unrealsdk


def _out() -> Path:  # the repo, through the mod's junction (sys.modules if the mod imported, else sdk_mods)
    if (mod := sys.modules.get("helios_tracker")) is not None and getattr(mod, "__file__", None):
        return Path(mod.__file__).resolve().parents[1] / "tools" / "probes" / "probe_bl1.txt"
    for entry in sys.path:
        if (link := Path(entry) / "helios_tracker").is_dir():
            return link.resolve().parent / "tools" / "probes" / "probe_bl1.txt"
    raise RuntimeError("helios_tracker isn't linked in sdk_mods (python tools/link_mod.py bl1)")


OUT = _out()
lines: list[str] = ["#" * 70]


def _flush() -> None:
    with OUT.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    lines.clear()


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>"[:200] if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, Enum):
        return str(value.name)
    if isinstance(value, (str, int, float, bool)):
        return f"{value:.2f}" if isinstance(value, float) else repr(value) if isinstance(value, str) else str(value)
    if depth > 2:
        return "..."
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{_try(lambda: value.Class.Name)}'{_try(lambda: value._path_name())}'"
    if hasattr(value, "_type"):  # struct
        parts = [f"{f.Name}={_brief(_try(lambda f=f: value._get_field(f)), depth + 1)}"
                 for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")]
        return "{" + ", ".join(parts) + "}"
    if hasattr(value, "__len__"):
        items = list(value)
        return f"[{len(items)}: " + ", ".join(_brief(v, depth + 1) for v in items[:6]) + "]"
    return str(value)


SKIP = {"Outer", "Class", "Name", "ObjectArchetype", "ObjectFlags", "HashNext", "HashOuterNext", "StateFrame",
        "LinkerIndex", "ObjectInternalInteger", "NetIndex", "VfTableObject", "Linker"}


def _fields(obj, limit: int = 3000) -> str:  # noqa: ANN001
    out = []
    for f in _try(lambda: list(obj.Class._fields()), []) or []:
        if f.Class.Name.endswith("Property") and str(f.Name) not in SKIP:
            out.append(f"{f.Name}={_brief(_try(lambda f=f: obj._get_field(f)))[:200]}")
    return ", ".join(out)[:limit]


def _read(obj, *names: str) -> None:  # noqa: ANN001
    for name in names:
        lines.append(f"   .{name} = {_brief(_try(lambda n=name: getattr(obj, n)))[:400]}")


def _live(name: str) -> list:
    return [o for o in _try(lambda: list(unrealsdk.find_all(name, exact=False)), []) or []
            if not str(o.Name).startswith("Default__")]


# 1. env
lines.append("== env")
lines.append(f"python {sys.version}")
lines.append(f"unrealsdk {_try(lambda: unrealsdk.__version__)}, pyunrealsdk {_try(lambda: sys.modules['pyunrealsdk'].__version__ if 'pyunrealsdk' in sys.modules else '-')}")
lines.append(f"mods_base game: {_try(lambda: __import__('mods_base').Game.get_current().name)}, "
             f"tree {_try(lambda: __import__('mods_base').Game.get_tree().name)}")
lines.append(f"helios_tracker imported: {'helios_tracker' in sys.modules}, output: {OUT}")
_flush()

# 2. hooks (__init__.py)
lines.append("== hooks")
for path in ("WillowGame.WillowGameViewportClient:PostRender", "WillowGame.WillowScrollingList:HandlePopList",
             "WillowGame.WillowPlayerController:ClientPlayBinkMovie", "WillowGame.WillowPickup:PostBeginPlay",
             "WillowGame.WillowInteractiveObject:PostBeginPlay",
             "WillowGame.WillowInteractiveObject:InitializeBalanceDefinitionState",
             "WillowGame.WillowInteractiveObject:SetUsability",
             "WillowGame.WillowInteractiveObject:Behavior_ChangeUsability",
             "WillowGame.WillowInteractiveObject:Destroyed"):
    func = _try(lambda p=path: unrealsdk.find_object("Function", p), None)
    lines.append(f"{'ok  ' if func is not None else 'MISS'} {path}")
_flush()

# 3. classes
lines.append("== classes (found, live instances)")
for name in ("WillowGameEngine", "WillowGameViewportClient", "WillowPlayerController", "WillowPlayerPawn", "WillowPawn",
             "WillowAIPawn", "WillowPlayerReplicationInfo", "WillowPickup", "WillowInteractiveObject",
             "WillowTacticalMapVolume", "WillowGFxMovie", "MapInfo", "WillowMapInfo", "LevelDependencyList",
             "SeqAct_Interp", "MissionTracker", "WillowWaypoint", "WorldDiscoveryArea", "WeaponTypeDefinition",
             "WillowDamageArea", "WillowDamageTypeDefinition", "VendingMachineExGFxMovie", "WillowVendingMachine",
             "GlobalsDefinition", "PlayerSkillTree", "SkillTreeBranchDefinition", "WillowVehicle", "WillowWeapon",
             "WillowItem", "WillowInventory", "ItemPoolDefinition", "MissionDefinition", "WillowScrollingList",
             "WillowInventoryManager"):
    cls = _try(lambda n=name: unrealsdk.find_class(n), None)
    lines.append(f"{'ok  ' if cls is not None else 'MISS'} {name}"
                 + (f" (super {_try(lambda c=cls: c.SuperField.Name)}), {len(_live(name))} live" if cls is not None else ""))
lines.append(f"GD_Globals.General.Globals: {_brief(_try(lambda: unrealsdk.find_object('GlobalsDefinition', 'GD_Globals.General.Globals'), None))}")
for lst in _live("LevelDependencyList")[:4]:
    lines.append(f"LevelDependencyList {lst._path_name()}: {_fields(lst, 1500)}")
_flush()

# 4. level
lines.append("== level")
engine = _try(lambda: __import__("mods_base").ENGINE, None)
wi = _try(lambda: engine.GetCurrentWorldInfo(), None) if engine is not None else None
lines.append(f"engine {_brief(engine)}, world info {_brief(wi)}")
info = None
if wi is not None and not isinstance(wi, str):
    lines.append(f"GetStreamingPersistentMapName: {_brief(_try(lambda: wi.GetStreamingPersistentMapName()))}")
    _read(wi, "KillZ", "TimeSeconds", "NetMode", "GRI")
    # BL1's persistent map is "Loader" in every area (the map probe): which area is loaded - its streaming levels
    levels = _try(lambda: list(wi.StreamingLevels), [])
    lines.append(f"StreamingLevels: {len(levels) if isinstance(levels, list) else levels}")
    for lv in levels if isinstance(levels, list) else []:
        lines.append(f"   {_brief(lv)}: PackageName {_brief(_try(lambda l=lv: l.PackageName))}, LoadedLevel "
                     f"{_brief(_try(lambda l=lv: l.LoadedLevel))}, visible {_brief(_try(lambda l=lv: l.bIsVisible))}, "
                     f"should load {_brief(_try(lambda l=lv: l.bShouldBeLoaded))}, should show "
                     f"{_brief(_try(lambda l=lv: l.bShouldBeVisible))}")
    for lv in _live("Level")[:12]:
        lines.append(f"   live Level {lv._path_name()}")
    for anchor in _live("LevelLandmarkAnchor"):
        lines.append(f"   anchor {anchor._path_name()}: MapFrame {_brief(_try(lambda a=anchor: a.MapFrame))}")
    # functions that may name the current map (signatures only, not called - "Probes: no blind calls")
    for path in ("WillowGame.WillowGameInfo:GetCurrentMapName", "WillowGame.WillowPlayerController:GetCurrentMapName",
                 "Engine.WorldInfo:GetMapName", "Engine.WorldInfo:GetPersistentMapName", "WillowGame.WillowGameInfo:GetPersistentMapName"):
        func = _try(lambda p=path: unrealsdk.find_object("Function", p), None)
        if func is not None and not isinstance(func, str):
            params = [f"{f.Name}:{f.Class.Name}" for f in _try(lambda f=func: list(f._fields()), []) or []]
            lines.append(f"   function {path}({', '.join(params)})")
        else:
            lines.append(f"   no function {path}")
    info = _try(lambda: wi.GetMapInfo(), None)
    lines.append(f"GetMapInfo: {_brief(info)}")
    if info is not None and not isinstance(info, str):
        lines.append(f"   map info fields: {_fields(info, 4000)}")
        vol = _try(lambda: info.TacticalMapVolume, None)
        if vol is not None and not isinstance(vol, str):
            lines.append(f"   volume fields: {_fields(vol, 3000)}")
            lines.append(f"   volume bounds: {_brief(_try(lambda: vol.BrushComponent.Bounds))}")
for vol in _live("WillowTacticalMapVolume")[:4]:
    lines.append(f"live volume {vol._path_name()}: {_fields(vol, 1500)}")
_flush()

# 5. player
lines.append("== player")
pc = _try(lambda: __import__("mods_base").get_pc(), None)
lines.append(f"get_pc: {_brief(pc)}")
if pc is not None and not isinstance(pc, str):
    _read(pc, "Pawn", "Location", "Rotation", "PlayerReplicationInfo", "PlayerSkillTree", "PlayerClass",
          "DiscoveredWorldAreas", "MyWillowPawn", "WorldInfo")
    pawn = _try(lambda: pc.Pawn, None)
    if pawn is not None and not isinstance(pawn, str):
        lines.append(f"-- pawn {pawn.Class.Name}")
        _read(pawn, "Location", "Rotation", "Health", "HealthMax", "PlayerReplicationInfo", "OxygenPool",
              "bAwaitingInjuredRespawn", "AwaitingRespawnResurrectLocation", "InvManager", "Weapon")
    pri = _try(lambda: pc.PlayerReplicationInfo, None)
    if pri is not None and not isinstance(pri, str):
        lines.append(f"-- replication info {pri.Class.Name}: {_fields(pri, 3000)}")
    tree = _try(lambda: pc.PlayerSkillTree, None)
    if tree is not None and not isinstance(tree, str):
        lines.append(f"-- skill tree {tree.Class.Name}: {_fields(tree, 2000)}")
for tracker in _live("MissionTracker")[:2]:
    lines.append(f"-- mission tracker {tracker._path_name()}: {_fields(tracker, 2500)}")
_flush()

# 6. class fields (names and types: the base to compare with BL2)
lines.append("== class fields")
for name in ("WillowPlayerController", "WillowPlayerPawn", "WillowPawn", "WillowPlayerReplicationInfo", "WillowPickup",
             "WillowInteractiveObject", "MapInfo", "WillowTacticalMapVolume", "MissionTracker", "WillowWaypoint",
             "WorldDiscoveryArea", "WeaponTypeDefinition", "WillowWeapon", "WillowItem"):
    cls = _try(lambda n=name: unrealsdk.find_class(n), None)
    if cls is None or isinstance(cls, str):
        continue
    own = [f"{f.Name}:{f.Class.Name.removesuffix('Property')}" for f in _try(lambda c=cls: list(c._fields()), []) or []
           if f.Class.Name.endswith("Property") and _try(lambda f=f: f.Outer == cls, False)]
    lines.append(f"-- {name} ({len(own)} own): {', '.join(own)}"[:6000])
    _flush()

# 7. samples
lines.append("== samples")
for name in ("WillowPickup", "WillowInteractiveObject", "WillowWaypoint", "WorldDiscoveryArea"):
    for obj in _live(name)[:3]:
        lines.append(f"-- {name} {obj._path_name()}: {_fields(obj, 2500)}")
    _flush()

lines.append("== done")
_flush()
print(f"probe_bl1: written to {OUT}")
