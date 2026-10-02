# Dev probe (in game - as a co-op CLIENT, host works too), instant: what tells an NPC offers a mission
# (the yellow "!" above its head) - a client has no mission waypoint components, so the map shows no
# quest givers there. Stand near an NPC with a "!" (and one without), then run it.
# Logs: the net mode; every pawn (NPCs) and interactive object (bounty boards, doors...) within 40 m, the
# pawns not players: its class, name, distance, and every
# property / component whose name looks mission / director / particle / icon related (the "!" is a
# particle: MissionTracker.StaticSetMissionDirectorParticle), with the particle components' template and
# active flag; the MissionTracker's IconHelper_Directors and DynamicMissionDirectives.
# Writes tools/probes/probe_directors.txt (overwrites)
#   py exec(open(r"<repo>\tools\probes\probe_directors.py").read())
import enum
import math
import re
import sys
from pathlib import Path

import unrealsdk
from mods_base import ENGINE, get_pc

OUT = Path(sys.modules["helios_tracker"].__file__).resolve().parents[1] / "tools" / "probes" / "probe_directors.txt"  # the repo, through the mod's junction
RANGE = 4000.0  # uu (40 m)
PATTERN = re.compile(r"mission|director|particle|icon|psc|eligible|redeem|exclaim|quest", re.I)
SKIP = {"Object", "Actor"}
lines: list[str] = []


def _try(fn, default="<err>"):  # noqa: ANN001, ANN202
    try:
        return fn()
    except Exception as ex:  # noqa: BLE001
        return f"<{type(ex).__name__}: {ex}>" if default == "<err>" else default


def _brief(value, depth: int = 0) -> str:  # noqa: ANN001
    if value is None:
        return "None"
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, float):
        return f"{value:.1f}"
    if hasattr(value, "_path_name") and hasattr(value, "Class"):
        return f"{value.Class.Name}'{value.Name}'"
    if depth > 2:
        return "..."
    if hasattr(value, "_type") and hasattr(value._type, "_fields"):
        return "{" + ", ".join(f"{f.Name}={_try(lambda f=f: _brief(value._get_field(f), depth + 1))}"
                               for f in _try(lambda: list(value._type._fields()), []) if f.Class.Name.endswith("Property")) + "}"
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        return "[" + ", ".join(_brief(v, depth + 1) for v in list(value)[:6]) + (f", ... ({len(value)})" if len(value) > 6 else "") + "]"
    return repr(value)


def _particle(comp) -> str:  # noqa: ANN001
    return (f"{comp.Class.Name}'{comp.Name}' template={_try(lambda: _brief(comp.Template))} active={_try(lambda: comp.bIsActive)}"
            f" hidden={_try(lambda: comp.HiddenGame)}")


def main() -> None:
    wi = ENGINE.GetCurrentWorldInfo()
    pc = get_pc()
    here = pc.Pawn.Location
    lines.append(f"map {_try(lambda: str(wi.GetStreamingPersistentMapName()))} netmode={_try(lambda: _brief(wi.NetMode))}")
    pawn, near = wi.PawnList, []
    for _ in range(2000):
        if pawn is None:
            break
        if "Player" not in str(pawn.Class.Name):
            loc = _try(lambda p=pawn: p.Location, None)
            if loc is not None and not isinstance(loc, str):
                d = math.dist((loc.X, loc.Y, loc.Z), (here.X, here.Y, here.Z))
                if d <= RANGE:
                    near.append((d, pawn))
        pawn = _try(lambda p=pawn: p.NextPawn, None)
    near.sort(key=lambda x: x[0])
    lines.append(f"{len(near)} non-player pawns within {RANGE / 100:.0f} m")
    for d, p in near:
        name = _try(lambda p=p: str(p.BalanceDefinitionState.BalanceDefinition.PlayThroughs[0].DisplayName), "?")
        lines.append(f"== {p.Class.Name} {p.Name} '{name}' {d / 100:.1f} m")
        c = p.Class
        while c is not None and c.Name not in SKIP:
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)):
                    lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f, p=p: _brief(p._get_field(f)))}")
            c = c.SuperField
        # the missions it gives / takes back: its MissionDirectivesDefinition, every property
        directives = _try(lambda p=p: p.MissionDirectives, None)
        if directives is not None and not isinstance(directives, str):
            c2 = directives.Class
            while c2 is not None and c2.Name not in SKIP | {"GBXDefinition"}:
                for f in _try(lambda c=c2: list(c._fields()), []):
                    if f.Class.Name.endswith("Property"):
                        lines.append(f"   directives {c2.Name}.{f.Name} = {_try(lambda f=f, o=directives: _brief(o._get_field(f)))}")
                c2 = c2.SuperField
        for comp in _try(lambda p=p: list(p.Components), []) or []:  # its particle components: the "!"?
            if comp is not None and "Particle" in str(comp.Class.Name):
                lines.append(f"   component {_particle(comp)}")
        for comp in _try(lambda p=p: list(p.AllComponents), []) or []:
            if comp is not None and "Particle" in str(comp.Class.Name):
                lines.append(f"   (all) component {_particle(comp)}")
    # mission givers that aren't NPCs: bounty boards, doors, signs... (interactive objects)
    objs = []
    for io in unrealsdk.find_all("WillowInteractiveObject", exact=False):
        loc = _try(lambda io=io: io.Location, None)
        if io.Name.startswith("Default__") or loc is None or isinstance(loc, str):
            continue
        d = math.dist((loc.X, loc.Y, loc.Z), (here.X, here.Y, here.Z))
        if d <= RANGE:
            objs.append((d, io))
    objs.sort(key=lambda x: x[0])
    lines.append(f"{len(objs)} interactive objects within {RANGE / 100:.0f} m")
    for d, io in objs:
        lines.append(f"== IO {io.Name} def={_try(lambda io=io: io.InteractiveObjectDefinition.Name)} {d / 100:.1f} m")
        c = io.Class
        while c is not None and c.Name not in SKIP:
            for f in _try(lambda c=c: list(c._fields()), []):
                if f.Class.Name.endswith("Property") and PATTERN.search(str(f.Name)):
                    lines.append(f"   {c.Name}.{f.Name} = {_try(lambda f=f, io=io: _brief(io._get_field(f)))}")
            c = c.SuperField
        for comp in _try(lambda io=io: list(io.AllComponents), []) or []:
            if comp is not None and "Particle" in str(comp.Class.Name):
                lines.append(f"   component {_particle(comp)}")
        # a bounty board (several missions in a submenu) or a vault symbol (the Cult of the Vault
        # challenge: clicked to be discovered) - everything, the object and its definition
        what = (str(_try(lambda io=io: io.InteractiveObjectDefinition.Name, "")) + " " + io.Name).lower()
        if "bounty" in what or "vault" in what:
            for label, obj in (("board", io), ("board definition", _try(lambda io=io: io.InteractiveObjectDefinition, None))):
                if obj is None or isinstance(obj, str):
                    continue
                lines.append(f"   --- {label}: every property")
                c = obj.Class
                while c is not None and c.Name not in SKIP | {"GBXDefinition"}:
                    for f in _try(lambda c=c: list(c._fields()), []):
                        if f.Class.Name.endswith("Property"):
                            lines.append(f"      {c.Name}.{f.Name} = {_try(lambda f=f, o=obj: _brief(o._get_field(f)))}")
                        elif f.Class.Name == "Function" and PATTERN.search(str(f.Name)):
                            params = [f"{p.Name}:{p.Class.Name}" for p in _try(lambda f=f: list(f._fields()), [])]
                            lines.append(f"      {c.Name}.{f.Name}({', '.join(params)})")
                    c = c.SuperField
    # vault symbols may not be interactive objects: any actor nearby named / classed like one
    lines.append("== actors within 40 m whose class or name mentions vault / symbol")
    for a in unrealsdk.find_all("Actor", exact=False):
        text = (str(a.Class.Name) + " " + str(a.Name)).lower()
        if a.Name.startswith("Default__") or not ("vault" in text or "symbol" in text):
            continue
        loc = _try(lambda a=a: a.Location, None)
        if loc is None or isinstance(loc, str):
            continue
        d = math.dist((loc.X, loc.Y, loc.Z), (here.X, here.Y, here.Z))
        if d <= RANGE:
            lines.append(f"   {a.Class.Name} {_try(a._path_name)} {d / 100:.1f} m hidden={_try(lambda a=a: a.bHidden)}")
    trackers = [t for t in unrealsdk.find_all("MissionTracker", exact=False) if not t.Name.startswith("Default__")]
    for t in trackers[:1]:
        lines.append(f"== tracker IconHelper_Directors = {_try(lambda t=t: _brief(t.IconHelper_Directors))}")
        lines.append(f"== tracker DynamicMissionDirectives = {_try(lambda t=t: _brief(t.DynamicMissionDirectives))}")
        lines.append(f"== tracker MissionWaypoints = {_try(lambda t=t: len(t.MissionWaypoints))}")


try:
    main()
except Exception as ex:  # noqa: BLE001
    lines.append(f"probe failed: {type(ex).__name__}: {ex}")
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"probe_directors: {len(lines)} lines -> {OUT}")
