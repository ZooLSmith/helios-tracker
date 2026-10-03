"""
Helios Tracker: a live map of the current level in your web browser.

The mod runs a small local web server; the page shows the game's own map image (the map screen's)
with players, enemies, NPCs, vehicles, loot and interactive objects on it, live, with zoom/pan.

- collector.py: game thread, reads the level and what's in it, publishes JSON to the Hub
- tacmap.py:    reads the map images from the game's packages on disk (background thread)
- server.py:    HTTP + Server-Sent Events, stdlib only, never touches UObjects
- script.py:    runs the user's optional autoexec.ps1 alongside the server (a tunnel...)
- updater.py:   the latest GitHub release's .sdkmod: checked, swapped in, reloaded
- web/:          the page: index.html + ES modules (js/), stylesheets (css/), translations (i18n/)
"""

import os
import socket
import sys
import threading
import time
from typing import Any

from mods_base import BoolOption, ButtonOption, HiddenOption, SliderOption, build_mod, hook
from ui_utils import OptionBox, OptionBoxButton
from unrealsdk.hooks import Type, add_hook, remove_hook
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from .collector import Collector, game_language
from .gamedir import cooked_dir
from . import gamecards, gamefonts, gameicons, games, gamescan, gamework, i18n, updater
from .script import start_script
from .server import Hub, TrackerServer
from .i18n import t
from .util import log, log_error, start_log

start_log()
i18n.set_game_language(game_language())  # (the in-game text: options, the updater's boxes)

_STALE = "_helios_tracker_server"  # sys attribute: the running server, across module reloads
_STALE_SCRIPT = "_helios_tracker_script"  # same for the running autoexec.ps1

# region Options


_port_changed = [False]  # the Port slider moved: the server restarted on leaving the options (on_menu_back)


def _on_port(_opt: Any, _value: float) -> None:
    _port_changed[0] = True  # (not a restart per slider step: every step was one, the old port gone meanwhile)


def _on_lan(_opt: Any, value: bool) -> None:
    _restart_soon(new_lan=value)


port = SliderOption(
    "port",
    value=8777,
    min_value=1024,
    max_value=65535,
    display_name=t("port.name"),
    description=t("port.desc"),
    on_change_while_enabled=_on_port,
)
lan = BoolOption(
    "lan",
    value=False,
    display_name=t("lan.name"),
    description=t("lan.desc"),
    on_change_while_enabled=_on_lan,
)
rate = SliderOption(
    "rate",
    value=10,
    min_value=1,
    max_value=30,
    display_name=t("rate.name"),  # (was "Updates Per Second": read as the mod's own updates, next to Check for Updates)
    description=t("rate.desc"),
)


def _url() -> str:
    return f"http://127.0.0.1:{int(port.value)}/"  # not localhost: the server is IPv4 only


def _open_page(_opt: Any) -> None:
    def open_it() -> None:
        os.startfile(_url())  # type: ignore  # noqa: S606

    if _port_changed[0]:  # (the Port slider moved, not applied yet - still in the menu: now, then the page on it)
        _port_changed[0] = False
        _restart_soon(then=open_it)
    else:
        open_it()


open_page = ButtonOption(
    "Open Map in Browser",  # (the identifier: English in every language - follow_menu matches on it)
    display_name=t("open.name"),
    on_press=_open_page,
    description=t("open.desc"),
)

# endregion
# region Updates
# Only from a .sdkmod (updater.can_install): a folder install - the dev junction - never checks, its options hidden.
# The menu draws an option's name once (no live relabelling): the button only ever checks, the game's own dialog box
# (ui_utils.OptionBox) shows it - "Checking for updates..." (Cancel), then the answer; a newer one: asked first
# (Download and Install / Not Now: nothing downloaded before), "Downloading vX...", then Reload Now / Later - each box
# replacing the last (an open box's text can't be changed through ui_utils) - and the bottom-left message
# (games.GAME.show_message) says what the automatic path did.
# The checks run in a thread; what they show goes through _ui_queue, drained on the game thread by on_post_render.

UPDATE_EVERY = 24 * 3600  # s between automatic checks
TOAST_FOR = 8.0  # s the bottom-left message stays
_update_busy = [False]  # a check / download running
_busy_text = [""]  # what it's doing, for the waiting box ("Checking for updates...", "Downloading vX...")
_answer_wanted = [False]  # the button pressed while it runs: it answers with the dialogs (an automatic one too)
_ui_queue: list[Any] = []  # callables for the game thread
_toast_until = [0.0]
_progress_box: list[Any] = [None]  # the open "Checking..." / "Downloading..." box
_check_cancelled = [False]  # its Cancel: the check's answer dropped (a download deleted)


def _on_game_thread(fn: Any) -> None:
    _ui_queue.append(fn)


def _toast(text: str) -> None:
    def show() -> None:
        games.GAME.show_message(text, TOAST_FOR)
        _toast_until[0] = time.monotonic() + TOAST_FOR

    _on_game_thread(show)


def _drain_ui(now: float) -> None:
    """Game thread, every frame (on_post_render): the queued dialogs / messages, the message's timeout."""
    while _ui_queue:
        try:
            _ui_queue.pop(0)()
        except Exception as ex:  # noqa: BLE001
            log_error("update dialog", ex)
    if _toast_until[0] and now > _toast_until[0]:
        _toast_until[0] = 0.0
        try:
            games.GAME.hide_message()
        except Exception as ex:  # noqa: BLE001
            log_error("update message", ex)


def _close_progress() -> None:
    box, _progress_box[0] = _progress_box[0], None
    if box is not None and box.is_showing():
        box.hide()


def _progress(text: str) -> None:
    """The manual check's waiting box (its only button: Cancel)."""

    def show() -> None:
        if _check_cancelled[0] or _ui_queue:  # (its answer already queued behind it: no box opened and shut at once)
            return
        _close_progress()

        def cancel(*_: Any) -> None:
            _check_cancelled[0] = True
            _progress_box[0] = None

        box = OptionBox(title=t("box.title"), message=text, buttons=[OptionBoxButton(t("update.cancel"))],
                        on_select=cancel, on_cancel=cancel)
        box.show()
        _progress_box[0] = box

    _on_game_thread(show)


def _dialog(title: str, message: str, buttons: list[str], on_pick: Any = None, check_answer: bool = False) -> None:
    """A box replacing the waiting one; `check_answer`: dropped if that one was cancelled (on_pick(None) then)."""

    def show() -> None:
        if check_answer and _check_cancelled[0]:
            if on_pick is not None:
                on_pick(None)
            return
        _close_progress()
        choices = [OptionBoxButton(name) for name in buttons]

        def picked(_box: Any, button: Any) -> None:
            if on_pick is not None:
                on_pick(button.name)

        OptionBox(title=title, message=message, buttons=choices, on_select=picked,
                  on_cancel=lambda _box: on_pick and on_pick(None)).show()

    _on_game_thread(show)


DOWNLOAD, NOT_NOW = t("update.download"), t("update.notNow")


def _offer(release: updater.Release) -> None:
    """A newer release found: asked first - nothing downloaded before Download and Install."""

    def pick(choice: str | None) -> None:
        if choice != DOWNLOAD:
            return
        _check_cancelled[0] = False
        text = t("update.downloading", tag=release.tag)
        _progress(text)
        _start_thread(_download_update, text, release)

    _dialog(t("box.updateTitle"), t("update.available", tag=release.tag, ours=_ours()), [DOWNLOAD, NOT_NOW], pick,
            check_answer=True)


def _download_update(release: updater.Release) -> None:
    """A thread: downloaded, verified, swapped in (unless cancelled meanwhile), then the reload offered."""
    try:
        staged = updater.download(release)
        if _check_cancelled[0]:
            updater.discard()
            return
        updater.apply(staged)
        log(f"Helios Tracker {release.tag} installed")
        _on_game_thread(lambda: _offer_reload(release.version, check_answer=True))
    except Exception as ex:  # noqa: BLE001
        log(f"update {release.tag} not installed: {ex}")
        _dialog(t("box.title"), t("update.installFailed", tag=release.tag, error=ex), [t("update.ok")],
                check_answer=True)
    finally:
        _update_busy[0], _answer_wanted[0] = False, False


def _start_thread(target: Any, text: str, *args: Any) -> None:
    _update_busy[0], _busy_text[0] = True, text
    threading.Thread(target=target, args=args, name="helios_tracker update", daemon=True).start()


def _tag(version: tuple[int, ...] | None) -> str:
    return "v" + ".".join(map(str, version)) if version else t("update.unknownVersion")


def _ours() -> str:
    return _tag(updater.RUNNING)


RELOAD_NOW, LATER = t("update.reloadNow"), t("update.later")


def _offer_reload(installed: tuple[int, ...], check_answer: bool = False) -> None:
    """Installed, not running yet: the reload (its button: ui_utils' hook, outside ours - the reload's place)."""

    def pick(choice: str | None) -> None:
        if choice == RELOAD_NOW:
            updater.reload_mod()

    _dialog(t("box.updateTitle"), t("update.installed", tag=_tag(installed), ours=_ours()), [RELOAD_NOW, LATER], pick,
            check_answer=check_answer)


def _check_update(auto: bool) -> None:
    """A thread: the latest release; newer -> offered (the button) or downloaded and installed (automatic - unless the
    button was pressed meanwhile: then answered like the button's)."""
    try:
        release = updater.check()
        auto = auto and not _answer_wanted[0]
        if release is None:
            log("Helios Tracker is up to date")
            if not auto:
                _dialog(t("box.title"), t("update.latest", ours=_ours()), [t("update.ok")], check_answer=True)
            return
        log(f"Helios Tracker {release.tag} is available: {release.page}")
        if not auto:
            _on_game_thread(lambda: _offer(release))
            return
        _busy_text[0] = t("update.downloading", tag=release.tag)
        updater.apply(updater.download(release))
        log(f"Helios Tracker {release.tag} installed")
        if _answer_wanted[0]:  # (pressed during the download)
            _on_game_thread(lambda: _offer_reload(release.version, check_answer=True))
        else:
            _on_game_thread(lambda: _reload_soon(release.tag))
    except Exception as ex:  # noqa: BLE001 - offline, GitHub down, a bad release: next time
        log(f"update check failed: {ex}")
        if not auto or _answer_wanted[0]:
            _dialog(t("box.title"), t("update.checkFailed", error=ex), [t("update.ok")], check_answer=True)
    finally:
        _update_busy[0], _answer_wanted[0] = False, False


def _start_check(auto: bool) -> None:
    if not updater.can_install():
        return
    if not auto:
        if (installed := updater.pending()) is not None:
            _offer_reload(installed)
            return
        _check_cancelled[0] = False  # (pressed again after a Cancel: the running check's answer wanted again)
        _progress(_busy_text[0] if _update_busy[0] else t("update.checking"))
        _answer_wanted[0] = True
    if _update_busy[0]:
        return
    _start_thread(_check_update, t("update.checking"), auto)


# The automatic path reloads by itself: from a one-shot hook on another function (the queue drains in our PostRender
# hook, which the reload removes - not done from inside it), the next frame; the new module says it (the old one's
# message would never be hidden: its hook is gone) - the tag handed over on sys.
RELOAD_HOOK = ("WillowGame.WillowGameViewportClient:Tick", "helios_tracker.auto_reload")
_UPDATED = "_helios_tracker_updated"  # sys attribute: the tag just installed by the automatic path, for the new module


def _reload_soon(tag: str) -> None:
    def once(*_: Any) -> None:
        remove_hook(RELOAD_HOOK[0], Type.PRE, RELOAD_HOOK[1])
        setattr(sys, _UPDATED, tag)
        try:
            updater.reload_mod()
        except Exception as ex:  # noqa: BLE001
            log_error("automatic update reload", ex)

    add_hook(RELOAD_HOOK[0], Type.PRE, RELOAD_HOOK[1], once)


def _announce_update() -> None:
    """At enable: the automatic path's reload just ran this module - said in the bottom-left message."""
    if (tag := getattr(sys, _UPDATED, None)) is not None:
        delattr(sys, _UPDATED)
        _toast(t("update.updated", tag=tag))


def _auto_update() -> None:
    """At enable: a check once a day, when the option's on (a dev source - update_source.txt: at every enable)."""
    dev_source = updater.source() != updater.RELEASES_API
    if not updater.can_install() or not auto_update.value:
        return
    if time.time() < float(next_update_check.value or 0) and not dev_source:
        return
    next_update_check.value = time.time() + UPDATE_EVERY
    if (built := globals().get("mod")) is not None and hasattr(built, "save_settings"):  # (enable can come first)
        built.save_settings()
    _start_check(auto=True)


auto_update = BoolOption(
    "auto_update",
    value=False,  # (off by default: the player turns it on)
    display_name=t("auto.name"),
    description=t("auto.desc"),
    is_hidden=not updater.can_install(),
)
update_button = ButtonOption(
    "Check for Updates",
    display_name=t("check.name"),
    on_press=lambda _: _start_check(auto=False),
    description=t("check.desc"),
    is_hidden=not updater.can_install(),
)
next_update_check = HiddenOption("next_update_check", 0.0)  # time.time() of the next automatic check

# endregion
# region Server lifecycle

_hub = Hub()
_collector = Collector(_hub)  # not `collector`: that would shadow the submodule


def _publish_assets() -> None:
    """The game assets the server can serve now ("assets": the page asks for item card icons only once they're there -
    before, a 404). Any thread (gamecards.listener: the files' scan, the first players' read)."""
    payload = '{"cards":%d,"textures":%d}' % (games.GAME.card_icons_ready(), gameicons.textures_ready())
    if payload != _assets_sent[0]:  # (only when it changed: the three kinds' keys come one by one)
        _assets_sent[0] = payload
        _hub.publish("assets", payload)


_assets_sent = [""]


gamecards.listener = _publish_assets
_publish_assets()


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet sent: just picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return None


# _start / _stop: from the game thread (enable / disable) and from a restart thread (_restart_soon), one at a time
_server_lock = threading.RLock()
_serving = [False]  # between _on_enable and _on_disable: a restart thread late after a disable starts nothing


def _restart_soon(new_lan: bool | None = None, then: Any = None) -> None:
    """The server restarted in a thread: stopping waits for its loop (<= its poll interval) and the user script's
    end - on the game thread, a freeze (every Port slider step was one: the user caught it). `then`: called after."""

    def run() -> None:
        with _server_lock:
            if _serving[0]:
                _start(new_lan=new_lan)
        if then is not None:
            then()

    threading.Thread(target=run, name="helios_tracker restart", daemon=True).start()


def _stop() -> None:
    with _server_lock:
        _stop_locked()


def _stop_locked() -> None:
    script = getattr(sys, _STALE_SCRIPT, None)
    setattr(sys, _STALE_SCRIPT, None)
    if script is not None:
        try:
            script.stop()
        except Exception as ex:  # noqa: BLE001
            log_error("script stop", ex)
    server = getattr(sys, _STALE, None)
    setattr(sys, _STALE, None)
    if server is not None:
        try:
            server.stop()
        except Exception as ex:  # noqa: BLE001
            log_error("server stop", ex)


def _start(new_port: int | None = None, new_lan: bool | None = None) -> None:
    """(Re)starts the server; the option callbacks pass their new value (set after they return)."""
    with _server_lock:
        _start_locked(new_port, new_lan)


def _start_locked(new_port: int | None, new_lan: bool | None) -> None:
    _stop_locked()  # also a server left running by a reload that didn't disable the mod
    _port_changed[0] = False  # (started on port.value: a moved slider's too)
    port_value = int(port.value if new_port is None else new_port)
    lan_value = bool(lan.value if new_lan is None else new_lan)
    try:
        server = TrackerServer("0.0.0.0" if lan_value else "127.0.0.1", port_value, _hub)
    except OSError as ex:
        log(f"couldn't start the web server on port {port_value}: {ex}")
        return
    setattr(sys, _STALE, server)
    where = f"http://localhost:{port_value}/"
    if lan_value and (ip := _lan_ip()):
        where += f" (LAN: http://{ip}:{port_value}/)"
    log(f"live map at {where}")
    setattr(sys, _STALE_SCRIPT, start_script(port_value))
    _hub.fonts = gamefonts.FONTS  # (its catalogue from the game files' scan: when a page connects)


_scan_started = [False]


def _scan_game_files() -> None:
    """The game files' index (fonts, item card / skill icons: gamescan.py - one pass, cached on disk), once per
    session, when a page first connects (not at every game start); a thread waiting on gamework's subinterpreter
    (the scan itself runs there, beside the game - or here, politely, without one)."""
    if _scan_started[0] or games.SCAN not in games.GAME.features:
        return
    _scan_started[0] = True
    # the game's language (Core.Object's static GetLanguage: "INT", "RUS"... - read here, on the game thread): its font
    # library (gamefonts.font_library)
    language = game_language()

    def scan() -> None:
        try:
            t = time.monotonic()
            gamescan.run(cooked_dir(), language)
            log(f"game files indexed in {time.monotonic() - t:.1f} s ({gamework.mode()}): language {language or '?'}"
                f" ({gamefonts.font_library(language)}), fonts {', '.join(gamefonts.FONTS.names())}")
        except Exception as ex:  # noqa: BLE001
            log_error("game files scan", ex)

    threading.Thread(target=scan, name="helios_tracker game files", daemon=True).start()


_collector.on_page = lambda: _scan_game_files()


def _on_enable() -> None:
    _collector.reset()
    _serving[0] = True
    _start()
    _announce_update()
    _auto_update()


def _on_disable() -> None:
    with _server_lock:
        _serving[0] = False
        _stop_locked()
    _stop_worker()
    _collector.reset()


def _stop_worker() -> None:
    """The game files' worker (gamework's subinterpreter) - this module's, or a previous one's (a reload)."""
    for worker in {id(w): w for w in (getattr(sys, "_helios_tracker_worker", None), gamework) if w is not None}.values():
        try:
            worker.stop()
        except Exception as ex:  # noqa: BLE001
            log_error("game files worker stop", ex)


_stop_worker()  # (a reload: the previous module's worker)


# endregion
# region Game hook

_next = [0.0]


@hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST)
def on_post_render(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    now = time.monotonic()
    if _ui_queue or _toast_until[0]:
        _drain_ui(now)
    if now < _next[0]:
        return
    _collector.rate = max(1.0, float(rate.value))
    _next[0] = now + 1.0 / _collector.rate
    try:
        _collector.tick(now)
    except Exception as ex:  # noqa: BLE001
        log_error("tick", ex)


@hook("WillowGame.WillowScrollingList:HandlePopList", Type.POST)
def on_menu_back(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    """Leaving an options screen (the mod menu saves there too): the Port slider moved - the server restarted once."""
    if _port_changed[0]:
        _port_changed[0] = False
        _restart_soon()


@hook("WillowGame.WillowPlayerController:ClientPlayBinkMovie", Type.PRE)
def on_bink_movie(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    """A cutscene video starting: the game renders nothing until it's over (tools/probes/probe_cutscene_watch.txt)."""
    try:
        _collector.movie_started(obj, str(args.MovieName), games.GAME.movie_no_skip(args))
    except Exception as ex:  # noqa: BLE001
        log_error("movie hook", ex)


@hook("WillowGame.WillowPickup:PostBeginPlay", Type.POST)
def on_pickup_spawn(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    """New pickups (loot drops...) as they appear: replaces frequent find_all scans (hitches)."""
    try:
        _collector.pickup_spawned(obj)
    except Exception as ex:  # noqa: BLE001
        log_error("pickup hook", ex)


@hook("WillowGame.WillowInteractiveObject:PostBeginPlay", Type.POST)
def on_object_spawn(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    try:
        _collector.object_spawned(obj)
    except Exception as ex:  # noqa: BLE001
        log_error("object spawn hook", ex)


@hook("WillowGame.WillowInteractiveObject:InitializeBalanceDefinitionState", Type.POST)
def on_object_balance(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    """The balance (behind the display name) can be set after the spawn: refresh the record."""
    try:
        _collector.object_spawned(obj)
    except Exception as ex:  # noqa: BLE001
        log_error("object balance hook", ex)


def _on_usability(obj: UObject) -> None:
    try:
        _collector.object_usability_changed(obj)
    except Exception as ex:  # noqa: BLE001
        log_error("object usability hook", ex)


@hook("WillowGame.WillowInteractiveObject:SetUsability", Type.POST)
def on_set_usability(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    """A container being opened turns its use off: it's looted now (no waiting for a check)."""
    _on_usability(obj)


@hook("WillowGame.WillowInteractiveObject:Behavior_ChangeUsability", Type.POST)
def on_change_usability(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    _on_usability(obj)


@hook("WillowGame.WillowInteractiveObject:Destroyed", Type.PRE)
def on_object_destroyed(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    try:
        _collector.object_destroyed(obj)
    except Exception as ex:  # noqa: BLE001
        log_error("object destroyed hook", ex)


# endregion

mod = build_mod(
    description=t("mod.desc"),
    on_enable=_on_enable,
    on_disable=_on_disable,
    hooks=[on_post_render, on_bink_movie, on_pickup_spawn, on_object_spawn, on_object_balance, on_object_destroyed,
           on_set_usability, on_change_usability, on_menu_back],
    options=[open_page, port, lan, rate, auto_update, update_button, next_update_check],
)
