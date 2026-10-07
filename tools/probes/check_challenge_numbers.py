# Offline research: the level challenge objects' numbers (NumberInChallengeGroup) in a map's packages - a co-op client's
# objects don't have them (all 1: tools/probes/probe_vault_save.txt, NM_Client) but the same positions as the host's,
# whose numbers are known (probe_vault_discovered.txt, Sanctuary: #3 at (11742, 5866, 3714)...). Are they placed data,
# in the map's packages? Lists every WillowInteractiveObject export with a NumberInChallengeGroup or an IO_VaultRoy
# definition: its package, position, number, definition, challenge.
#   python tools/probes/check_challenge_numbers.py [map name prefix, default Sanctuary]
# Writes tools/probes/check_challenge_numbers.txt (overwrites)
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
    """Its tagged properties: a placed actor's come after a state frame (its size not worked out here) - the first offset
    whose list parses to its end with a Location or a definition."""
    for o in range(4, min(len(data), 96)):
        try:
            props, _end = pkg.properties(data, o)
        except Exception:  # noqa: BLE001, S112
            continue
        if "Location" in props or "InteractiveObjectDefinition" in props:
            return props
    return None


def main() -> None:
    prefix = (sys.argv[1] if len(sys.argv) > 1 else "Sanctuary").lower()
    cooked = project.require(project.cooked_dir(), "game.path")
    lines: list[str] = []
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
            for i, e in enumerate(pkg.exports):
                if pkg.class_name(i) != "WillowInteractiveObject":
                    continue
                props = _actor_properties(pkg, pkg.export_data(i))
                if props is None:
                    lines.append(f"{path.name} {e['name']}: properties unreadable")
                    continue
                definition = pkg.ref_path(struct.unpack_from("<i", props["InteractiveObjectDefinition"][1])[0]) \
                    if "InteractiveObjectDefinition" in props else ""
                if "NumberInChallengeGroup" not in props and not definition.endswith("IO_VaultRoy"):
                    continue
                found += 1
                loc = struct.unpack_from("<fff", props["Location"][1]) if "Location" in props else None
                number = int.from_bytes(props["NumberInChallengeGroup"][1], "little") if "NumberInChallengeGroup" in props else None
                challenge = pkg.ref_path(struct.unpack_from("<i", props["AssociatedChallenge"][1])[0]) \
                    if "AssociatedChallenge" in props else ""
                at = f"({loc[0]:.0f}, {loc[1]:.0f}, {loc[2]:.0f})" if loc else "(no Location)"
                lines.append(f"{path.name} {pkg.path(i)} at {at} number={number} def={definition} challenge={challenge!r}")
            lines.append(f"{path.name}: {found} level challenge objects")
        finally:
            pkg.close()
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


main()
