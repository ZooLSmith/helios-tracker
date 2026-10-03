# Release tool: builds helios_tracker.sdkmod (a zip holding helios_tracker/...: git's files - tracked, or new and not
# ignored - as they are in the working tree, without the dev ones) into _work/dist/.
#   python tools/build_sdkmod.py           build it
#   python tools/build_sdkmod.py install   build it, and run it in the game instead of the dev junction: the junction
#                                          parked as sdk_mods/.helios_tracker_dev (the loader skips dot names; a
#                                          folder would win over the .sdkmod), the .sdkmod copied beside it
#   python tools/build_sdkmod.py dev       back to the junction: the .sdkmod removed, the junction renamed back
#                                          (or linked again: link_mod.py)
# Add "tps" for the Pre-Sequel, "bl1" for Borderlands 1 (project.json's keys). Double-clickable: tools/use_sdkmod.bat, tools/use_dev.bat.
import re
import shutil
import subprocess
import sys
import zipfile

import project

PACKAGE = "helios_tracker"
DEV_FILES = {"reload.py"}  # (logs, .cache/, autoexec scripts: gitignored, so never listed)

def build(out: "project.Path | None" = None, version: str | None = None, quiet: bool = False) -> "project.Path":
    """The .sdkmod (default: _work/dist/); `version`: its pyproject's instead (tools/fake_release.py's test releases)."""
    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", PACKAGE], cwd=project.ROOT, capture_output=True, check=True)
    names = sorted(n for n in listed.stdout.decode("utf-8").split("\0") if n)
    out = out or project.ROOT / "_work" / "dist" / f"{PACKAGE}.sdkmod"
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in names:
            rel = name[len(PACKAGE) + 1 :]
            if rel in DEV_FILES or "__pycache__" in name:
                continue
            src = project.ROOT / name
            if not src.is_file():  # (deleted in the working tree, not committed yet)
                continue
            if version and rel == "pyproject.toml":
                text = src.read_text(encoding="utf-8")
                z.writestr(name, re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1))
            else:
                z.write(src, name)
            count += 1
    if not quiet:
        print(f"{out} ({count} files, {out.stat().st_size // 1024} KB)")
    return out


def sdk_mods(key: str) -> "project.Path":
    game = project.require(project.path(key), f"The game ({key})")
    return project.require(game / "sdk_mods", "sdk_mods (install the Python SDK first)")


def main() -> None:
    args = sys.argv[1:]
    key = next((k for k in ("tps", "bl1") if k in args), "game")  # (project.json's keys: the Pre-Sequel, Borderlands 1)
    action = next((a for a in args if a in ("install", "dev")), "build")
    if action == "build":
        build()
    elif action == "install":
        install(sdk_mods(key))
    elif action == "dev":
        dev(sdk_mods(key), key)


def install(mods: "project.Path") -> None:
    folder, parked = mods / PACKAGE, mods / f".{PACKAGE}_dev"
    if folder.exists() or folder.is_junction():
        if not folder.is_junction():
            sys.exit(f"{folder} is a real folder, not the dev junction: move it away first")
        if parked.exists() or parked.is_junction():
            sys.exit(f"both {folder} and {parked} exist: remove one first")
        folder.rename(parked)
        print(f"parked the junction: {parked}")
    shutil.copyfile(build(), mods / f"{PACKAGE}.sdkmod")
    print(f"installed {mods / f'{PACKAGE}.sdkmod'} - restart the game ('python tools/build_sdkmod.py dev' to go back)")


def dev(mods: "project.Path", key: str) -> None:
    folder, parked = mods / PACKAGE, mods / f".{PACKAGE}_dev"
    (mods / f"{PACKAGE}.sdkmod").unlink(missing_ok=True)
    if parked.is_junction() and not (folder.exists() or folder.is_junction()):
        parked.rename(folder)
        print(f"junction back: {folder}")
    elif not folder.is_junction():  # (never parked, or removed): linked again
        subprocess.run([sys.executable, str(project.ROOT / "tools" / "link_mod.py"), key], check=True)
    print("restart the game")


if __name__ == "__main__":
    main()
