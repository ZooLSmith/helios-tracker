"""
Helios Tracker: a live map of the current level in your web browser.

The mod runs a small local web server; the page shows the game's own map image (the map screen's)
with players, enemies, NPCs, vehicles, loot and interactive objects on it, live, with zoom/pan.

- collector.py: game thread, reads the level and what's in it, publishes JSON to the Hub
- tacmap.py:    reads the map images from the game's packages on disk (background thread)
- server.py:    HTTP + Server-Sent Events, stdlib only, never touches UObjects
- script.py:    runs the user's optional autoexec.ps1 alongside the server (a tunnel...)
- web/:          the page: index.html + ES modules (js/), stylesheets (css/), translations (i18n/)
"""

import os
import socket
import sys
import threading
import time
from typing import Any

from mods_base import BoolOption, ButtonOption, SliderOption, build_mod, hook
from unrealsdk.hooks import Type
from unrealsdk.unreal import BoundFunction, UObject, WrappedStruct

from .collector import Collector, cooked_dir, package_path
from .gamefonts import load_game_fonts
from .gameicons import set_game_dir, warm as warm_icons
from .script import start_script
from .server import Hub, TrackerServer
from .util import log, log_error, start_log

start_log()

_STALE = "_helios_tracker_server"  # sys attribute: the running server, across module reloads
_STALE_SCRIPT = "_helios_tracker_script"  # same for the running autoexec.ps1

# region Options


def _on_port(_opt: Any, value: float) -> None:
    _start(new_port=int(value))


def _on_lan(_opt: Any, value: bool) -> None:
    _start(new_lan=value)


port = SliderOption(
    "port",
    value=8777,
    min_value=1024,
    max_value=65535,
    display_name="Port",
    description="Port of the local web server: the page is at http://localhost:<port>/.",
    on_change_while_enabled=_on_port,
)
lan = BoolOption(
    "lan",
    value=False,
    display_name="Allow LAN Access",
    description=(
        "Also serve the map to other devices on your network (a phone, a tablet, another PC)."
        " Windows may ask to let the game through its firewall."
        " Off: only this PC can open it."
    ),
    on_change_while_enabled=_on_lan,
)
rate = SliderOption(
    "rate",
    value=10,
    min_value=1,
    max_value=30,
    display_name="Updates Per Second",
    description="How often positions are sent to the page (it smooths movement in between).",
)


def _url() -> str:
    return f"http://127.0.0.1:{int(port.value)}/"  # not localhost: the server is IPv4 only


open_page = ButtonOption(
    "Open Map in Browser",
    on_press=lambda _: os.startfile(_url()),  # type: ignore  # noqa: S606
    description="Opens the live map in your default browser (the mod must be enabled).",
)

# endregion
# region Server lifecycle

_hub = Hub()
_collector = Collector(_hub)  # not `collector`: that would shadow the submodule


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet sent: just picks the outgoing interface
            return s.getsockname()[0]
    except OSError:
        return None


def _stop() -> None:
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
    _stop()  # also a server left running by a reload that didn't disable the mod
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
    _load_fonts()
    set_game_dir(cooked_dir())  # (the skill icons: read from its packages when asked for)
    threading.Thread(target=warm_icons, name="helios_tracker icons", daemon=True).start()  # their index, ahead


def _load_fonts() -> None:
    """The game's UI fonts (WillowBody...), once per session, on a thread of their own (files only:
    gamefonts.py) - the page's @font-face rules fall back to its system fonts until they're there."""
    if _hub.fonts is not None:
        return
    _hub.fonts = {}

    def extract() -> None:
        try:
            startup = package_path("Startup.upk")
            if startup is None:
                raise FileNotFoundError("Startup.upk not found")
            fonts = load_game_fonts(startup)
            _hub.fonts = {slug: data for slug, (_name, data) in fonts.items()}
            log(f"game fonts: {', '.join(name for name, _ in fonts.values())}")
        except Exception as ex:  # noqa: BLE001
            log_error("game fonts", ex)

    threading.Thread(target=extract, name="helios_tracker fonts", daemon=True).start()


def _on_enable() -> None:
    _collector.reset()
    _start()


def _on_disable() -> None:
    _stop()
    _collector.reset()


# endregion
# region Game hook

_next = [0.0]


@hook("WillowGame.WillowGameViewportClient:PostRender", Type.POST)
def on_post_render(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    now = time.monotonic()
    if now < _next[0]:
        return
    _collector.rate = max(1.0, float(rate.value))
    _next[0] = now + 1.0 / _collector.rate
    try:
        _collector.tick(now)
    except Exception as ex:  # noqa: BLE001
        log_error("tick", ex)


@hook("WillowGame.WillowPlayerController:ClientPlayBinkMovie", Type.PRE)
def on_bink_movie(obj: UObject, args: WrappedStruct, ret: Any, func: BoundFunction) -> None:  # noqa: ARG001
    """A cutscene video starting: the game renders nothing until it's over (tools/probe_cutscene_watch.txt)."""
    try:
        _collector.movie_started(obj, str(args.MovieName), bool(args.bForceNoSkip))
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
    on_enable=_on_enable,
    on_disable=_on_disable,
    hooks=[on_post_render, on_bink_movie, on_pickup_spawn, on_object_spawn, on_object_balance, on_object_destroyed,
           on_set_usability, on_change_usability],
    options=[open_page, port, lan, rate],
)
