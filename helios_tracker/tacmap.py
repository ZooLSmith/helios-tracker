"""
Reads a level's tactical map (the in-game map screen's image) straight from the game's cooked
packages on disk. Pure Python, no SDK: runs on a background thread, and offline in tests.

A level's persistent package (e.g. Sanctuary_P.upk) holds:
- SwfMovie UI_TacticalMap_<Level>.<Level>_P: a small Scaleform movie drawing the map image(s) as
  shapes, in movie px;
- Texture2D UI_TacticalMap_<Level>.<Level>_P_I1 (..._I2, ...): the images (DXT5, stored inline).
World -> movie px uses the WillowTacticalMapVolume (see collector.py); this module only returns
the images and where each sits in movie px.

The packages themselves: upk.py; the movies' tags: swf.py.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

from .swf import _affine, _Bits, _cstr, _matrix, _movie_raw, _movie_tags, _place2, _shape_bitmap, _tags
from .upk import Package, _texture

# region Scaleform movie


def parse_map_movie(raw: bytes) -> list[tuple[str, tuple[float, float, float, float], tuple[int, int, int, int] | None]]:
    """[(image file name, (x0, x1, y0, y1) in movie px, the part of the image drawn: (x, y, w, h) px or None - all of
    it)] for each map image placed on the stage."""
    images: dict[int, str] = {}
    subs: dict[int, tuple[int, tuple[int, int, int, int]]] = {}  # sub-image id -> (its image's id, its rect)
    shapes: dict[int, tuple[tuple[float, float, float, float], int]] = {}
    out = []
    for code, body in _movie_tags(raw):
        if code == 1009:  # GFx DefineExternalImage2: id (u16, then 2 bytes: 0, or 9 - the Pre-Sequel's
            # ComFacility_P, its image id 0), format, target w/h, export name, file name
            cid = struct.unpack_from("<H", body)[0]
            p = 10
            p += 1 + body[p]  # export name
            images[cid] = body[p + 1 : p + 1 + body[p]].decode("latin1")
        elif code == 1008:  # GFx DefineSubImage: id, its image's id, x1 y1 x2 y2 (px, u16) - a part of an image
            # (ComFacility_P: 743 x 644 of its 1024 x 1024 texture), what the shape shows
            cid, image, x1, y1, x2, y2 = struct.unpack_from("<6H", body)
            subs[cid] = (image, (x1, y1, x2 - x1, y2 - y1))
        elif code in (2, 22, 32, 83):
            if (s := _shape_bitmap(code, body)) is not None and (s[2] in images or s[2] in subs):
                shapes[s[0]] = (s[1], s[2])
        elif code == 26:  # PlaceObject2
            flags = body[0]
            if not flags & 0x02:
                continue
            cid = struct.unpack_from("<H", body, 3)[0]
            if cid not in shapes:
                continue
            sx = sy = 1.0
            tx = ty = 0.0
            if flags & 0x04:
                sx, sy, tx, ty = _matrix(_Bits(body, 5))
            (x0, x1, y0, y1), bmp = shapes[cid]
            image, crop = subs[bmp] if bmp in subs else (bmp, None)
            if image in images:
                out.append((images[image], (x0 * sx + tx, x1 * sx + tx, y0 * sy + ty, y1 * sy + ty), crop))
    return out


FOG_BLOB = "fog of war blob"  # the fog piece SharedWillowTacMaps exports (tools/probes/dump_tacmap_movie.txt)


def parse_fog_pieces(raw: bytes) -> list[tuple[str, tuple[float, ...]]]:
    """A level movie's fog of war (tools/probes/dump_tacmap_movie.txt): the fog blob it imports from
    SharedWillowTacMaps, placed once per discovery area - named by the area's short name
    ("SOUTHERNSHELF_PWDA_1"), its matrix (as _affine, movie px) stretching the blob over it. The map
    screen hides an area's blob once it's discovered. -> [(name, matrix)]."""
    blobs: set[int] = set()
    out = []
    for code, body in _movie_tags(raw):
        if code == 71:  # ImportAssets2: url, 2 reserved bytes, count, (id, name)...
            _url, p = _cstr(body, 0)
            count = struct.unpack_from("<H", body, p + 2)[0]
            p += 4
            for _ in range(count):
                cid = struct.unpack_from("<H", body, p)[0]
                name, p = _cstr(body, p + 2)
                if name == FOG_BLOB:
                    blobs.add(cid)
        elif code == 26:
            cid, matrix, name = _place2(body)
            if cid in blobs and name and matrix:
                out.append((name, matrix))
    return out


def parse_fog_blob(raw: bytes) -> tuple[str, tuple[float, float, float, float]] | None:
    """SharedWillowTacMaps' fog blob: the image file its tactical map frame shows and that shape's
    bounds (movie px: -128..128 - its 64 x 64 texture declared 256 x 256). The export is a sprite
    ("tacMap" frame: the map screen's blob, "miniMap": the minimap's); its first placement is the
    tacMap one. None if it isn't there."""
    images: dict[int, str] = {}
    shapes: dict[int, tuple[tuple[float, float, float, float], int]] = {}
    sprites: dict[int, int] = {}  # sprite id -> the first character it places
    exports: dict[str, int] = {}
    for code, body in _movie_tags(raw):
        if code == 1009:
            cid = struct.unpack_from("<I", body)[0]
            p = 10
            p += 1 + body[p]
            images[cid] = body[p + 1 : p + 1 + body[p]].decode("latin1")
        elif code in (2, 22, 32, 83):
            if (s := _shape_bitmap(code, body)) is not None and s[2] in images:
                shapes[s[0]] = (s[1], s[2])
        elif code == 39:
            sid = struct.unpack_from("<H", body)[0]
            for sub, sbody in _tags(body, 4):
                if sub == 26 and (cid := _place2(sbody)[0]) is not None:
                    sprites[sid] = cid
                    break
        elif code == 56:  # ExportAssets: count, (id, name)...
            count, p = struct.unpack_from("<H", body)[0], 2
            for _ in range(count):
                cid = struct.unpack_from("<H", body, p)[0]
                name, p = _cstr(body, p + 2)
                exports[name] = cid
    cid = exports.get(FOG_BLOB)
    shape = shapes.get(sprites.get(cid, cid)) if cid is not None else None
    return (images[shape[1]], shape[0]) if shape else None


# endregion
# region Images


@dataclass
class MapImage:
    name: str
    format: str  # EPixelFormat, e.g. "PF_DXT5" - decoded by the web page
    width: int
    height: int
    data: bytes  # top mip, as stored
    bounds: tuple[float, float, float, float]  # x0, x1, y0, y1 in movie px
    crop: tuple[int, int, int, int] | None = None  # the part drawn in bounds (x, y, w, h px: a sub-image), None all


@dataclass
class MapFog:
    blob: MapImage  # the fog piece (bounds: its shape's, around 0)
    pieces: list[tuple[str, tuple[float, ...]]]  # (area short name, matrix placing the blob: _affine)


SHARED_TACMAPS = "SharedWillowTacMaps.SharedWillowTacMaps"


def load_fog(package_file: Path, movie_path: str) -> MapFog | None:
    """The level's fog of war: SharedWillowTacMaps' blob (its texture, cooked into the level's package
    with the movie) and where the level's movie places it. None if either is missing."""
    pkg = Package(package_file)
    try:
        idx, shared = pkg.find(movie_path, "SwfMovie"), pkg.find(SHARED_TACMAPS, "SwfMovie")
        if idx is None or shared is None:
            return None
        pieces = parse_fog_pieces(_movie_raw(pkg, idx))
        blob = parse_fog_blob(_movie_raw(pkg, shared))
        if not pieces or blob is None:
            return None
        file_name, bounds = blob
        stem = file_name.rpartition(".")[0] or file_name
        tex = pkg.find(f"{SHARED_TACMAPS.partition('.')[0]}.{stem}", "Texture2D")
        if tex is None:
            return None
        fmt, w, h, body = _texture(pkg, tex)
        return MapFog(MapImage(stem, fmt, w, h, body, bounds), pieces)
    finally:
        pkg.close()


def load_tactical_map(package_file: Path, movie_path: str) -> list[MapImage]:
    """The images of the tactical map movie `movie_path` (e.g. "UI_TacticalMap_Sanctuary.Sanctuary_P")."""
    pkg = Package(package_file)
    try:
        idx = pkg.find(movie_path, "SwfMovie")
        if idx is None:
            raise FileNotFoundError(f"{movie_path} not in {package_file.name}")
        raw = _movie_raw(pkg, idx)
        movie_pkg = movie_path.rpartition(".")[0]
        out = []
        for file_name, bounds, crop in parse_map_movie(raw):
            stem = file_name.rpartition(".")[0] or file_name
            tex = pkg.find(f"{movie_pkg}.{stem}", "Texture2D")
            if tex is None:
                raise FileNotFoundError(f"texture {movie_pkg}.{stem} not in {package_file.name}")
            fmt, w, h, body = _texture(pkg, tex)
            out.append(MapImage(stem, fmt, w, h, body, bounds, crop))
        return out
    finally:
        pkg.close()


# endregion
