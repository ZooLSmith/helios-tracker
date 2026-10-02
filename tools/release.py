# Release tool: publishes helios_tracker.sdkmod as a GitHub release of the public repo - what the mod's updater
# reads (updater.RELEASES_API: the latest release, its tag vX.Y.Z = the pyproject's version, the asset by name).
#   python tools/release.py                      checks + builds + verifies, then says what it would publish
#   python tools/release.py --publish [--notes "What's new"]   ... and publishes it (gh release create)
# Checks: on master, nothing uncommitted (the build packs the working tree), master pushed to the public repo (the
# release's tag goes on that very commit there), the version newer than the latest release, its tag not taken.
# Needs gh, logged in (gh auth login).
# Bump helios_tracker/pyproject.toml's version (and commit) before each release.
import json
import subprocess
import sys
import tomllib
import types

import build_sdkmod
import project

PUBLIC_REPO = "ZooLSmith/helios-tracker"
ASSET = "helios_tracker.sdkmod"

# The updater's own verify / version parsing: its module alone (paths + updater, no SDK) under another package name -
# the package's __init__ needs the SDK (gamework's worker does the same)
_pkg = types.ModuleType("helios_release")
_pkg.__path__ = [str(project.ROOT / "helios_tracker")]
sys.modules["helios_release"] = _pkg
from helios_release import updater  # noqa: E402


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=project.ROOT, capture_output=True, text=True, check=check)


def fail(message: str) -> None:
    sys.exit(f"release: {message}")


def latest_release() -> tuple[int, ...] | None:
    """The public repo's latest release's version (None: no release yet)."""
    answer = run("gh", "api", f"repos/{PUBLIC_REPO}/releases/latest", check=False)
    if answer.returncode != 0:
        if "Not Found" in answer.stdout + answer.stderr:
            return None
        fail(f"couldn't read the latest release: {answer.stderr.strip() or answer.stdout.strip()}")
    return updater.parse_version(json.loads(answer.stdout)["tag_name"])


def main() -> None:
    args = sys.argv[1:]
    publish = "--publish" in args
    notes = args[args.index("--notes") + 1] if "--notes" in args else ""

    pyproject = tomllib.loads((project.ROOT / "helios_tracker" / "pyproject.toml").read_text(encoding="utf-8"))
    version_text = pyproject["project"]["version"]
    version = updater.parse_version(version_text)
    if version is None:
        fail(f"pyproject's version {version_text!r} isn't X.Y.Z")
    tag = f"v{version_text}"

    if (branch := run("git", "branch", "--show-current").stdout.strip()) != "master":
        fail(f"on {branch!r}: releases come from master")
    if dirty := run("git", "status", "--porcelain").stdout.strip():
        fail(f"uncommitted changes (the build packs the working tree): commit or set them aside first\n{dirty}")
    if run("gh", "--version", check=False).returncode != 0:
        fail("gh (GitHub's CLI) not found: https://cli.github.com, then gh auth login")
    head = run("git", "rev-parse", "HEAD").stdout.strip()
    remote = run("git", "ls-remote", f"https://github.com/{PUBLIC_REPO}.git", "refs/heads/master").stdout.split()
    if not remote or remote[0] != head:
        fail(f"the public repo's master isn't this commit ({head[:7]}): push master there first")
    latest = latest_release()
    if latest is not None and version <= latest:
        fail(f"{tag} isn't newer than the latest release (v{'.'.join(map(str, latest))}): bump pyproject's version")
    if run("gh", "release", "view", tag, "--repo", PUBLIC_REPO, check=False).returncode == 0:
        fail(f"{tag} already exists on {PUBLIC_REPO}")

    out = build_sdkmod.build(project.ROOT / "_work" / "release" / tag / ASSET)
    updater.verify(out, version)  # (what every player's updater checks before installing it)
    commit = run("git", "rev-parse", "--short", "HEAD").stdout.strip()
    print(f"{tag}: {out.name} built from {commit}, verified")

    command = ["gh", "release", "create", tag, str(out), "--repo", PUBLIC_REPO, "--target", head,
               "--title", f"Helios Tracker {tag}", "--notes", notes or f"Helios Tracker {tag}."]
    if not publish:
        print(f"would publish (add --publish):\n  {subprocess.list2cmdline(command)}")
        return
    result = run(*command, check=False)
    if result.returncode != 0:
        fail(f"gh release create failed: {result.stderr.strip()}")
    print(f"published: {result.stdout.strip()}")
    run("git", "tag", tag)  # (the private repo's marker: the commit released - pushed by you, like everything)
    print(f"tagged {commit} {tag} here (local)")


if __name__ == "__main__":
    main()
