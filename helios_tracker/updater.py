"""Updates: the latest GitHub release of the public repo, its helios_tracker.sdkmod swapped in for ours.

- check(): the release API's latest (tag "v1.2.3", the asset by name) against our pyproject version. Blocking (HTTP):
  call it from a thread.
- download(release): into paths.DATA, checked (a zip holding helios_tracker/ only, its __init__.py, its pyproject
  version the tag's), kept there (STAGED); apply(staged): os.replace over our .sdkmod; install = both. Only when
  running from a .sdkmod (a folder install, the dev junction: never checked, never touched - can_install). The file isn't locked while the game runs (seen); the new code runs after a
  reload (reload_mod) or the next start.
- reload_mod(): the mod dropped and imported again (reload.py's steps, + the zip importer's index read again: a
  replaced .sdkmod has new offsets). Game thread only (an option's button, not one of our hooks).
- The source: RELEASES_API, or a dev override - DATA/update_source.txt holding another URL (tools/fake_release.py
  serves one locally).
No SDK imports (offline_check runs it against a local server).
"""

import importlib
import json
import os
import re
import sys
import time
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

from . import paths
from .util import log

RELEASES_API = "https://api.github.com/repos/ZooLSmith/helios-tracker/releases/latest"
ASSET = "helios_tracker.sdkmod"
STAGED = f"{ASSET}.new"  # in DATA: downloaded and verified, waiting for apply()
SOURCE_OVERRIDE = paths.DATA / "update_source.txt"
CHECK_TIMEOUT = 15  # s
DOWNLOAD_TIMEOUT = 120  # s
REPLACE_TRIES, REPLACE_WAIT = 20, 0.25  # (a thread of ours: up to 5 s)
MAX_SIZE = 64 * 1024 * 1024  # bytes: the release is ~0.3 MB - anything this big isn't ours
_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class Release:
    tag: str  # "v0.2.0"
    version: tuple[int, ...]
    download: str  # the asset's URL
    page: str  # the release's page (for people)


def parse_version(text: str) -> tuple[int, ...] | None:
    m = _VERSION.fullmatch(text.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def current_version() -> tuple[int, ...] | None:
    """The installed one, from the package's pyproject.toml (read through paths: the folder or the .sdkmod - the file
    on disk now, so after an install the new version; RUNNING is this session's)."""
    data = paths.read("pyproject.toml")
    try:
        return parse_version(tomllib.loads(data.decode("utf-8"))["project"]["version"]) if data else None
    except (KeyError, ValueError):
        return None


RUNNING = current_version()  # this session's code (the file can be newer: installed for the next start)


def pending() -> tuple[int, ...] | None:
    """The installed .sdkmod's version when it's newer than the code running (Install at Next Start, the automatic
    path): reloading runs it. None otherwise."""
    installed = current_version()
    return installed if installed and RUNNING and installed > RUNNING else None


def source() -> str:
    try:
        if SOURCE_OVERRIDE.is_file() and (url := SOURCE_OVERRIDE.read_text(encoding="utf-8").strip()):
            return url
    except OSError:
        pass
    return RELEASES_API


def _get(url: str, timeout: float, accept: str) -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": "helios-tracker"})  # (GitHub refuses no agent)
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - https (or the dev override)
        data = response.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError(f"{url}: over {MAX_SIZE // 1024 // 1024} MB")
    return data


def latest() -> Release:
    """The latest release (raises when it can't be read, or has no .sdkmod / no version tag)."""
    data = json.loads(_get(source(), CHECK_TIMEOUT, "application/vnd.github+json"))
    tag = str(data["tag_name"])
    version = parse_version(tag)
    if version is None:
        raise ValueError(f"latest release {tag!r}: not a version tag")
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET), None)
    if asset is None:
        raise ValueError(f"latest release {tag}: no {ASSET}")
    return Release(tag, version, str(asset["browser_download_url"]), str(data.get("html_url") or ""))


def check() -> Release | None:
    """The latest release if it's newer than ours, else None (raises like latest())."""
    release, ours = latest(), current_version()
    return release if ours is None or release.version > ours else None


def can_install() -> bool:
    """Only a .sdkmod is replaced (a folder install - the dev junction - never)."""
    return paths.SDKMOD is not None


def verify(path: Path, version: tuple[int, ...]) -> None:
    """A .sdkmod the loader takes (one root folder, named like the file), our package, the release's version."""
    package = paths.PACKAGE.name
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if not names or any(n.split("/", 1)[0] != package for n in names):
            raise ValueError(f"not a {package} .sdkmod: other root folders")
        if f"{package}/__init__.py" not in names:
            raise ValueError(f"not a {package} .sdkmod: no __init__.py")
        if (bad := z.testzip()) is not None:
            raise ValueError(f"damaged: {bad}")
        found = parse_version(tomllib.loads(z.read(f"{package}/pyproject.toml").decode("utf-8"))["project"]["version"])
    if found != version:
        raise ValueError(f"its pyproject says {found}, the release {version}")


def _replace(new: Path, target: Path) -> None:
    """os.replace (same drive: sdk_mods/.helios_tracker beside it), retried: Windows refuses it while another handle
    has the file open - the page's files being read out of it (paths.read) as a browser reconnects (seen: WinError 5
    right after a reload)."""
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(new, target)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(REPLACE_WAIT)


def _require_sdkmod() -> Path:
    if paths.SDKMOD is None:
        raise RuntimeError("not running from a .sdkmod: nothing to replace")
    return paths.SDKMOD


def download(release: Release) -> Path:
    """The release's .sdkmod downloaded and verified, waiting in DATA (STAGED) for apply(). Raises on any failure
    (nothing left behind; ours untouched)."""
    _require_sdkmod()
    part, staged = paths.DATA / f"{ASSET}.download", paths.DATA / STAGED
    paths.DATA.mkdir(parents=True, exist_ok=True)
    try:
        part.write_bytes(_get(release.download, DOWNLOAD_TIMEOUT, "application/octet-stream"))
        verify(part, release.version)
        os.replace(part, staged)  # (ours alone: nothing else opens it)
    finally:
        part.unlink(missing_ok=True)
    return staged


def apply(staged: Path) -> Path:
    """The downloaded .sdkmod swapped in for ours; returns ours. Its code runs after reload_mod() or the next start."""
    target = _require_sdkmod()
    _replace(staged, target)
    return target


def discard() -> None:
    """A downloaded update not wanted (the dialog's Not Now)."""
    (paths.DATA / STAGED).unlink(missing_ok=True)


def install(release: Release) -> Path:
    """download() + apply(): the automatic path."""
    return apply(download(release))


def reload_mod() -> None:
    """Runs the installed code now: disable, drop the modules, import again, enable as before (reload.py's steps).
    Game thread, outside our hooks (the options menu's button)."""
    pkg = sys.modules.get(paths.PACKAGE.name)
    old = getattr(pkg, "mod", None)
    was_enabled = old is not None and old.is_enabled
    if old is not None:
        old.save_settings()  # (a change made in the open menu: saved only when leaving it - the new mod reads the file)
        old.disable(dont_update_setting=True)
    for name in [n for n in sys.modules if n == paths.PACKAGE.name or n.startswith(paths.PACKAGE.name + ".")]:
        del sys.modules[name]
    importlib.invalidate_caches()
    pkg = importlib.import_module(paths.PACKAGE.name)
    if was_enabled:
        pkg.mod.enable()
    if old is not None:
        follow_menu(old, pkg.mod)


def follow_menu(old: object, new: object) -> None:
    """The options menu still open on the old mod (Reload Now is pressed there) switched to the new one: its drawn
    options were the old module's objects - Check for Updates queued its box where no hook drained it any more (nothing
    happened until the menu was reopened), a change went to the old mod, leaving the menu saved the old one's values.
    willow2_mod_menu's internals (options_menu.data_provider_stack: a provider's mod, options, drawn_options); anything
    else (another menu, its internals changed): left as is - backing out and in again does the same."""
    try:
        from willow2_mod_menu import options_menu  # noqa: PLC0415 - (game only; offline_check has no SDK)
    except ImportError:  # (another mod menu)
        return
    try:
        fresh: dict[tuple[type, str], object] = {}

        def walk(options: object) -> None:
            for option in options:  # type: ignore[attr-defined]
                fresh[(type(option), option.identifier)] = option
                walk(getattr(option, "children", ()))

        walk(new.iter_display_options())  # type: ignore[attr-defined]
        same = lambda option: fresh.get((type(option), getattr(option, "identifier", None)), option)  # noqa: E731
        for provider in options_menu.data_provider_stack:
            if getattr(provider, "mod", None) is not old:
                continue
            provider.mod = new
            provider.options = tuple(same(option) for option in provider.options)
            provider.drawn_options[:] = [same(option) for option in provider.drawn_options]
    except Exception as ex:  # noqa: BLE001
        log(f"the open options menu not switched to the reloaded mod ({ex!r}): reopen it")
