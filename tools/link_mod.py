# Dev tool: links this repo's helios_tracker/ into the game's sdk_mods with a directory junction (no admin
# needed), so edits here are live in game. The game: project.json's game.path.
#   python tools/link_mod.py
# Removing the link (rmdir <game>/sdk_mods/helios_tracker) leaves the repo alone.
import subprocess
import sys

import project

game = project.require(project.game_dir(), "The game")
sdk_mods = project.require(game / "sdk_mods", "sdk_mods (install the Python SDK first)")
link, target = sdk_mods / "helios_tracker", project.ROOT / "helios_tracker"
if link.exists() or link.is_junction():
    if link.resolve() == target.resolve():
        print(f"already linked: {link} -> {target}")
        sys.exit(0)
    sys.exit(f"{link} exists and isn't a link to {target}: move it away first")
subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True)
