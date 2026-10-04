# Dev tool: links this repo's helios_tracker/ into the game's sdk_mods with a directory junction (no admin
# needed), so edits here are live in game. The game: project.json's game.path, or another key's (tps: the Pre-Sequel, bl1: Borderlands 1).
#   python tools/link_mod.py [tps | bl1]
# Removing the link (rmdir <game>/sdk_mods/helios_tracker) leaves the repo alone.
import subprocess
import sys

import project

key = sys.argv[1] if len(sys.argv) > 1 else "game"
game = project.require(project.path(key), f"The game ({key})")
sdk_mods = project.require(game / "sdk_mods", "sdk_mods (install the Python SDK first)")
link, target = sdk_mods / "helios_tracker", project.ROOT / "helios_tracker"
if link.exists() or link.is_junction():
    if link.resolve() == target.resolve():
        print(f"already linked: {link} -> {target}")
        sys.exit(0)
    sys.exit(f"{link} exists and isn't a link to {target}: move it away first")
subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True)
