"""
The game's skill icons as PNGs (files only: no SDK, no UObjects - safe on the server's threads).

A skill's SkillDefinition.SkillIcon is a small Scaleform movie ("SharedSkillIcons_Soldier.SkillIcon-Able"); a
Texture2D of the same path sits next to it, in its class's streaming package (tools: GD_Soldier_Streaming_SF.upk,
34 icons - DXT5, 64 x 64; the action skill's 256 x 128): the four classes' in WillowGame/CookedPCConsole, the
DLC classes' in DLC/<code name>/<Compat...>/Content (GD_Lilac_Psycho_..., GD_Tulip_Mechro_...: their icons
named UI_Lilac_SharedSkillIcons_Psyc.* / UI_Tulip_SharedSkillIcons_Mech.*). Indexed once
(which package holds which icon), decoded and encoded as a PNG the first time one is asked for, then kept -
extracted from the player's install at run time, never stored in the repo.
"""

import re
import struct
import threading
import zlib
from pathlib import Path

from .tacmap import Package, _texture

# a skill icon's object path: the four classes' "SharedSkillIcons_Soldier.SkillIcon-Able", the DLC classes'
# "UI_Lilac_SharedSkillIcons_Psyc.SkillIcon-Psycho01" / "UI_Tulip_SharedSkillIcons_Mech..."
ICON_PATH = re.compile(r"(?:UI_[A-Za-z0-9]+_)?SharedSkillIcons_[A-Za-z0-9_]+\.[A-Za-z0-9_-]+", re.I)
MAX_ICONS = 400  # PNGs kept (every class's: ~250)

_lock = threading.Lock()
_game_dir: Path | None = None
_index: dict[str, tuple[Path, int]] | None = None  # icon path (lower case) -> (package, export index)
_pngs: dict[str, bytes | None] = {}


def set_game_dir(cooked: Path | None) -> None:
    """The install's WillowGame/CookedPCConsole (the mod knows it: collector.cooked_dir)."""
    global _game_dir  # noqa: PLW0603
    _game_dir = cooked


def _packages() -> list[Path]:
    if _game_dir is None:
        return []
    game = _game_dir.parent.parent
    # (Startup.upk too: a few icons are only there - Axton's Willing, "Skillicon-willing", Maya's Sphere)
    return (sorted(_game_dir.glob("GD_*_Streaming_SF.upk")) + sorted((game / "DLC").glob("*/*/Content/GD_*_Streaming_SF.upk"))
            + [p for p in (_game_dir / "Startup.upk",) if p.is_file()])


def _build_index() -> dict[str, tuple[Path, int]]:
    index: dict[str, tuple[Path, int]] = {}
    for path in _packages():
        try:
            pkg = Package(path)
        except Exception:  # noqa: BLE001 - a package that won't read: its icons missing, not the others
            continue
        try:
            for i in range(len(pkg.exports)):
                name = pkg.path(i)
                if ICON_PATH.fullmatch(name) and pkg.class_name(i) == "Texture2D":
                    index.setdefault(name.lower(), (path, i))
        finally:
            pkg.close()
    return index


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


def warm() -> None:
    """Builds the index ahead (a thread at the server's start: ~3 s with Startup.upk - not on the first request)."""
    global _index  # noqa: PLW0603
    with _lock:
        if _index is None:
            _index = _build_index()


def icon_png(path: str) -> bytes | None:
    """A skill icon (its object path: "SharedSkillIcons_Soldier.SkillIcon-Able") as a PNG, or None if the game
    doesn't have it (or it won't decode). Thread-safe; the first call builds the index (six packages)."""
    global _index  # noqa: PLW0603
    if not ICON_PATH.fullmatch(path):
        return None
    key = path.lower()
    with _lock:
        if key in _pngs:
            return _pngs[key]
        if _index is None:
            _index = _build_index()
        # the movie's texture: the same path, or its first image's (the Scaleform importer's "<movie>_I1": the
        # DLC classes' and some others - AAIcon-MechroAA_I1, like the map images')
        where = _index.get(key) or _index.get(key + "_i1")
        data = None
        if where is not None:
            try:
                pkg = Package(where[0])
                try:
                    fmt, w, h, body = _texture(pkg, where[1])
                finally:
                    pkg.close()
                data = png(w, h, decode_dxt(fmt, w, h, body))
            except Exception:  # noqa: BLE001 - that icon's missing, the page shows none
                data = None
        if len(_pngs) >= MAX_ICONS:
            _pngs.pop(next(iter(_pngs)))
        _pngs[key] = data
        return data
