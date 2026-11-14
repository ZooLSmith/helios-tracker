# Offline research: the population points placed in a map's packages - the containers that aren't objects yet (chests,
# coolers, cash boxes... spawned within the point's SpawnAndCullRadius: notes.md "Containers spawned by distance").
# Live, Three Horns had 137 PopulationOpportunityPoints (probe_chest_spawn.txt): are they all in the map's packages,
# with their position and PopulationDef, readable without the game (a co-op client, sublevels not streamed in)?
# Lists every Population* export: its package, class, position, definition, radius; then counts per definition.
#   python tools/probes/check_population_points.py [map name prefix, default Ice_]
# Writes tools/probes/check_population_points.txt (overwrites)
import collections
import struct
import sys
from pathlib import Path

import importlib.util

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import project  # noqa: E402

# upk.py alone (the package's __init__ needs the SDK)
_spec = importlib.util.spec_from_file_location("upk", ROOT / "helios_tracker" / "formats" / "upk.py")
_upk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_upk)
Package = _upk.Package

OUT = Path(__file__).with_suffix(".txt")


def _actor_properties(pkg, data: bytes):  # noqa: ANN001, ANN202
    """Its tagged properties: after a state frame - the first offset whose list parses to its end with a Location."""
    for o in range(4, min(len(data), 96)):
        try:
            props, _end = pkg.properties(data, o)
        except Exception:  # noqa: BLE001, S112
            continue
        if "Location" in props or "PopulationDef" in props:
            return props
    return None


def _ref(pkg, props, name):  # noqa: ANN001, ANN202
    return pkg.ref_path(struct.unpack_from("<i", props[name][1])[0]) if name in props else ""


def main() -> None:
    prefix = (sys.argv[1] if len(sys.argv) > 1 else "Ice_").lower()
    cooked = project.require(project.cooked_dir(), "game.path")
    lines: list[str] = []
    per_def: collections.Counter = collections.Counter()
    classes: collections.Counter = collections.Counter()
    for path in sorted(cooked.glob("*.upk")):
        if not path.name.lower().startswith(prefix):
            continue
        try:
            pkg = Package(path)
        except Exception as ex:  # noqa: BLE001
            lines.append(f"{path.name}: unreadable ({type(ex).__name__}: {ex})")
            continue
        try:
            found = 0
            for i, _e in enumerate(pkg.exports):
                cls = pkg.class_name(i)
                if not cls.startswith(("Population", "WillowPopulation")):
                    continue
                classes[(path.name, cls)] += 1
                if cls not in ("PopulationOpportunityPoint", "WillowPopulationOpportunityPoint"):
                    continue
                props = _actor_properties(pkg, pkg.export_data(i))
                if props is None:
                    lines.append(f"{path.name} {pkg.path(i)}: properties unreadable")
                    continue
                found += 1
                loc = struct.unpack_from("<fff", props["Location"][1]) if "Location" in props else None
                at = f"({loc[0]:.0f}, {loc[1]:.0f}, {loc[2]:.0f})" if loc else "(no Location)"
                definition = _ref(pkg, props, "PopulationDef")
                per_def[definition] += 1
                others = sorted(k for k in props if k not in ("Location", "PopulationDef"))
                lines.append(f"{path.name} {cls} {pkg.path(i)} at {at} def={definition} props={others}")
            lines.append(f"{path.name}: {found} PopulationOpportunityPoints")
        finally:
            pkg.close()
    lines.append("")
    lines.append("== classes per package")
    lines += [f"   {n:4} {p} {c}" for (p, c), n in sorted(classes.items())]
    lines.append("== points per definition")
    lines += [f"   {n:4} {d or '(none)'}" for d, n in per_def.most_common()]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[-40:]))


main()
