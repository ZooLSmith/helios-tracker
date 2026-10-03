"""
The game's skill icons as PNGs (files only: no SDK, no UObjects - safe on the server's threads).

A skill's SkillDefinition.SkillIcon is a small Scaleform movie ("SharedSkillIcons_Soldier.SkillIcon-Able"); a
Texture2D of the same path sits next to it, in its class's streaming package (tools: GD_Soldier_Streaming_SF.upk,
34 icons - DXT5, 64 x 64; the action skill's 256 x 128): the four classes' in WillowGame/CookedPCConsole, the
DLC classes' in DLC/<code name>/<Compat...>/Content (GD_Lilac_Psycho_..., GD_Tulip_Mechro_...: their icons
named UI_Lilac_SharedSkillIcons_Psyc.* / UI_Tulip_SharedSkillIcons_Mech.*; the Pre-Sequel's without "GD_":
Crocus_Baroness_..., Quince_Doppel_..., icons SharedSkillIcons_Cro_Aurelia.*). Indexed once
(which package holds which icon), decoded and encoded as a PNG the first time one is asked for, then kept -
extracted from the player's install at run time, never stored in the repo.
"""

import re
import struct
import threading
import zlib
from pathlib import Path
from typing import Any

from . import gamework
from .upk import _texture, opened

# a skill icon's object path: the four classes' "SharedSkillIcons_Soldier.SkillIcon-Able", the DLC classes'
# "UI_Lilac_SharedSkillIcons_Psyc.SkillIcon-Psycho01" / "UI_Tulip_SharedSkillIcons_Mech..."
ICON_PATH = re.compile(r"(?:UI_[A-Za-z0-9]+_)?SharedSkillIcons_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+", re.I)
MAX_ICONS = 400  # PNGs kept (every class's: ~250)

_lock = threading.Lock()
_index: dict[str, tuple[Path, int]] | None = None  # icon path (lower case) -> (package, export index)
_pngs: dict[str, bytes | None] = {}


def icon_packages(cooked: Path | None) -> list[Path]:
    """Where the skill icons are: the classes' streaming packages (BL2's naming - the engine config doesn't list
    them), the DLC classes' too (any "*_Streaming_SF" in a DLC's Content: only theirs, in both games), and Startup (a few icons only there: Axton's Willing, "Skillicon-willing")."""
    if cooked is None:
        return []
    game = cooked.parent.parent
    return (sorted(cooked.glob("GD_*_Streaming_SF.upk")) + sorted((game / "DLC").glob("*/*/Content/*_Streaming_SF.upk"))
            + [p for p in (cooked / "Startup.upk",) if p.is_file()])


_textures: dict[str, tuple[Path, int]] | None = None  # every always-loaded package's texture: path -> (package, export)
_texture_pngs: dict[str, bytes | None] = {}
TEXTURE_PATH = re.compile(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_-]+)+")


def set_textures(index: dict[str, tuple[Path, int]]) -> None:
    """The always-loaded packages' textures by path, from gamescan's pass (a pickup's own icon: its PickupFlagIcon)."""
    global _textures  # noqa: PLW0603
    with _lock:
        _textures = index
        _texture_pngs.clear()


def textures_ready() -> bool:
    with _lock:
        return _textures is not None


def texture_by_path(path: str) -> bytes | None:
    """An always-loaded texture by its object path ("fx_shared_items.Textures.ItemCards.Credits": a pickup's icon) as
    a PNG, or None (not one of them, won't decode, not indexed yet: not kept). Decoded by gamework (cached on disk);
    its pixels in a texture file cache (.tfc) too (upk._texture). Thread-safe."""
    if not TEXTURE_PATH.fullmatch(path or ""):
        return None
    key = path.lower()
    with _lock:
        if key in _texture_pngs:
            return _texture_pngs[key]
        if _textures is None:
            return None
        where = _textures.get(key)
    data = gamework.asset({"do": "icon", "package": str(where[0]), "export": where[1]}, [where[0]]) if where else None
    with _lock:
        if len(_texture_pngs) >= MAX_ICONS:
            _texture_pngs.pop(next(iter(_texture_pngs)))
        _texture_pngs[key] = data
    return data


def movie_texture(pkg: Any, idx: int) -> str | None:
    """The texture a skill icon's movie (SwfMovie export `idx`) draws, as the game links it: the movie's References
    (its first - the icon's one image), an export of the same package or an import of another's (the Soldier's
    streaming package imports Willing's from Startup.upk). Its path, lower case; None if it has none. Usually the
    movie's own path (SkillIcon-Able), not always (SkillIcon-DoubleYourFun uses SkillIcon-DoubleFun)."""
    props, _ = pkg.properties(pkg.export_data(idx))
    if "References" not in props:
        return None
    value = props["References"][1]
    count = struct.unpack_from("<i", value)[0]
    for n in range(count):
        if ref := struct.unpack_from("<i", value, 4 + 4 * n)[0]:
            return pkg.ref_path(ref).lower()
    return None


def set_index(index: dict[str, tuple[Path, int]]) -> None:
    """The icons by path, from gamescan's one pass (cached)."""
    global _index  # noqa: PLW0603
    with _lock:
        _index = index
        _pngs.clear()


# region DXT -> RGBA -> PNG


def _rgb565(c: int) -> tuple[int, int, int]:
    return (c >> 11 & 31) * 255 // 31, (c >> 5 & 63) * 255 // 63, (c & 31) * 255 // 31


def _colour_block(blk: bytes, o: int, dxt1: bool) -> list[tuple[int, int, int, int]]:
    c0, c1, bits = struct.unpack_from("<HHI", blk, o)
    a, b = _rgb565(c0), _rgb565(c1)
    if dxt1 and c0 <= c1:
        cols = [(*a, 255), (*b, 255), (*((x + y) // 2 for x, y in zip(a, b)), 255), (0, 0, 0, 0)]
    else:
        cols = [(*a, 255), (*b, 255), (*((2 * x + y) // 3 for x, y in zip(a, b)), 255),
                (*((x + 2 * y) // 3 for x, y in zip(a, b)), 255)]
    return [cols[bits >> (2 * i) & 3] for i in range(16)]


def decode_dxt(fmt: str, w: int, h: int, data: bytes) -> bytes:
    """DXT1 / DXT5 (the icons') -> RGBA bytes, row by row."""
    dxt1 = fmt == "PF_DXT1"
    if fmt not in ("PF_DXT1", "PF_DXT5"):
        raise ValueError(f"unsupported icon format {fmt}")
    size = 8 if dxt1 else 16
    out = bytearray(w * h * 4)
    bw = (w + 3) // 4
    for n in range(len(data) // size):
        bx, by = n % bw, n // bw
        if by * 4 >= h:
            break
        o = n * size
        alpha = None
        if not dxt1:
            a0, a1 = data[o], data[o + 1]
            abits = int.from_bytes(data[o + 2 : o + 8], "little")
            table = [a0, a1] + ([((6 - i) * a0 + (i + 1) * a1) // 7 for i in range(6)] if a0 > a1
                                else [((4 - i) * a0 + (i + 1) * a1) // 5 for i in range(4)] + [0, 255])
            alpha = [table[abits >> (3 * i) & 7] for i in range(16)]
            o += 8
        texels = _colour_block(data, o, dxt1)
        for i, (r, g, b, a) in enumerate(texels):
            x, y = bx * 4 + i % 4, by * 4 + i // 4
            if x < w and y < h:
                p = (y * w + x) * 4
                out[p : p + 4] = bytes((r, g, b, alpha[i] if alpha is not None else a))
    return bytes(out)


def png(w: int, h: int, rgba: bytes) -> bytes:
    """RGBA bytes -> a PNG (8-bit RGBA, no filter)."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    rows = b"".join(b"\0" + rgba[y * w * 4 : (y + 1) * w * 4] for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


# endregion


def texture_png(path: Path, idx: int) -> bytes:
    """A package's texture as a PNG (gamework's job)."""
    with opened(path) as pkg:  # (the worker: kept open for the next job)
        fmt, w, h, body = _texture(pkg, idx)
    return png(w, h, decode_dxt(fmt, w, h, body))


def icon_png(path: str) -> bytes | None:
    """A skill icon (its object path: "SharedSkillIcons_Soldier.SkillIcon-Able") as a PNG, or None if the game
    doesn't have it (or it won't decode; or gamescan hasn't given the index yet: not kept, asked again).
    Decoded by gamework (its subinterpreter; cached on disk). Thread-safe."""
    if not ICON_PATH.fullmatch(path):
        return None
    key = path.lower()
    with _lock:
        if key in _pngs:
            return _pngs[key]
        if _index is None:
            return None
        # the movie's texture: the same path, or its first image's (the Scaleform importer's "<movie>_I1": the
        # DLC classes' and some others - AAIcon-MechroAA_I1, like the map images')
        where = _index.get(key) or _index.get(key + "_i1")
    data = gamework.asset({"do": "icon", "package": str(where[0]), "export": where[1]}, [where[0]]) if where else None
    with _lock:
        if len(_pngs) >= MAX_ICONS:
            _pngs.pop(next(iter(_pngs)))
        _pngs[key] = data
    return data
