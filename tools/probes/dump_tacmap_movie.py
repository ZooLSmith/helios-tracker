# Dev tool (offline): every tag of a level's tactical map movie - imports (names from other movies:
# the fog of war pieces?), shapes, sprites, placements with their names / matrices, labels - and the
# package's exports under the movie's package. Looking for how the game draws its fog of war.
#   python tools/probes/dump_tacmap_movie.py [Map_P]   (default SouthernShelf_P)
# Writes tools/probes/dump_tacmap_movie.txt (overwrites)
# The game: project.json's game.path
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tools/: project.py
import project  # noqa: E402

import importlib.util  # noqa: E402

# upk.py / swf.py alone (the package's __init__ needs the SDK)
def _alone(name):  # noqa: ANN001, ANN202
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "helios_tracker" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_upk, _swf = _alone("upk"), _alone("swf")
Package, _Bits, _matrix, _rect, _tags = _upk.Package, _swf._Bits, _swf._matrix, _swf._rect, _swf._tags

COOKED = project.require(project.cooked_dir(), "The game's CookedPCConsole")
OUT = Path(__file__).with_suffix(".txt")
NAMES = {0: "End", 1: "ShowFrame", 2: "DefineShape", 4: "PlaceObject", 5: "RemoveObject", 9: "SetBackgroundColor",
         12: "DoAction", 22: "DefineShape2", 26: "PlaceObject2", 28: "RemoveObject2", 32: "DefineShape3",
         39: "DefineSprite", 43: "FrameLabel", 56: "ExportAssets", 57: "ImportAssets", 59: "DoInitAction",
         69: "FileAttributes", 70: "PlaceObject3", 71: "ImportAssets2", 76: "SymbolClass", 77: "Metadata",
         82: "DoABC", 83: "DefineShape4", 86: "DefineSceneAndFrameLabelData", 1000: "GFx ExporterInfo",
         1001: "GFx DefineExternalImage", 1009: "GFx DefineExternalImage2"}
lines: list[str] = []


def cstr(b: bytes, o: int) -> tuple[str, int]:
    e = b.index(0, o)
    return b[o:e].decode("latin1"), e + 1


def full_matrix(b) -> tuple[float, ...]:  # noqa: ANN001
    sx = sy = 1.0
    r0 = r1 = 0.0
    if b.u(1):
        n = b.u(5)
        sx, sy = b.s(n) / 65536, b.s(n) / 65536
    if b.u(1):
        n = b.u(5)
        r0, r1 = b.s(n) / 65536, b.s(n) / 65536
    n = b.u(5)
    return sx, sy, r0, r1, b.s(n) / 20, b.s(n) / 20


def fills(code: int, body: bytes) -> str:
    """A shape's fill styles: solid colours, bitmaps (id + matrix), gradients (kind)."""
    b = _Bits(body, 2)
    _rect(b)
    o = b.align()
    if code == 83:
        b = _Bits(body, o)
        _rect(b)
        o = b.align() + 1
    count = body[o]
    o += 1
    out = []
    for _ in range(count):
        kind = body[o]
        o += 1
        if kind == 0x00:
            n = 3 if code in (2, 22) else 4
            out.append("solid #" + body[o : o + n].hex())
            o += n
        elif 0x40 <= kind <= 0x43:
            bmp = struct.unpack_from("<H", body, o)[0]
            b = _Bits(body, o + 2)
            m = full_matrix(b)
            o = b.align()
            out.append(f"bitmap {kind:#x} id={bmp} m=" + ",".join(f"{v:.3f}" for v in m))
        else:
            out.append(f"gradient {kind:#x}")
            break
    return "; ".join(out)


def place2(body: bytes, depth_label: str) -> str:
    flags = body[0]
    depth = struct.unpack_from("<H", body, 1)[0]
    o, parts = 3, [f"flags={flags:#04x} depth={depth}"]
    if flags & 0x02:
        parts.append(f"char={struct.unpack_from('<H', body, o)[0]}")
        o += 2
    if flags & 0x04:
        b = _Bits(body, o)
        parts.append("matrix(sx,sy,r0,r1,tx,ty)=" + ",".join(f"{v:.3f}" for v in full_matrix(b)))
        o = b.align()
    if flags & 0x08:  # colour transform (with alpha): skip it
        b = _Bits(body, o)
        add, mul, n = b.u(1), b.u(1), b.u(4)
        vals = [b.s(n) for _ in range(4 * (add + mul))]
        parts.append(f"cxform={vals}")
        o = b.align()
    if flags & 0x10:
        parts.append(f"ratio={struct.unpack_from('<H', body, o)[0]}")
        o += 2
    if flags & 0x20:
        name, o = cstr(body, o)
        parts.append(f"name={name!r}")
    if flags & 0x40:
        parts.append(f"clipdepth={struct.unpack_from('<H', body, o)[0]}")
    return depth_label + " ".join(parts)


def dump_tags(d: bytes, o: int, indent: str) -> None:
    for code, body in _tags(d, o):
        name = NAMES.get(code, f"tag{code}")
        extra = ""
        if code in (2, 22, 32, 83):
            b = _Bits(body, 2)
            extra = f"id={struct.unpack_from('<H', body)[0]} bounds=" + ",".join(f"{v:.1f}" for v in _rect(b)) + " fills: " + fills(code, body)
        elif code == 26:
            extra = place2(body, "")
        elif code == 39:
            sid, frames = struct.unpack_from("<HH", body)
            lines.append(f"{indent}{name} id={sid} frames={frames} ({len(body)} bytes)")
            dump_tags(body, 4, indent + "    ")
            continue
        elif code in (57, 71):
            url, p = cstr(body, 0)
            if code == 71:
                p += 2
            count = struct.unpack_from("<H", body, p)[0]
            p += 2
            items = []
            for _ in range(count):
                cid = struct.unpack_from("<H", body, p)[0]
                nm, p = cstr(body, p + 2)
                items.append(f"{cid}:{nm}")
            extra = f"from {url!r}: {items}"
        elif code == 56 or code == 76:
            count = struct.unpack_from("<H", body)[0]
            p, items = 2, []
            for _ in range(count):
                cid = struct.unpack_from("<H", body, p)[0]
                nm, p = cstr(body, p + 2)
                items.append(f"{cid}:{nm}")
            extra = str(items)
        elif code == 43:
            extra = repr(cstr(body, 0)[0])
        elif code in (1001, 1009):
            extra = repr(body[:80])
        elif code in (12, 59, 82):
            extra = f"({len(body)} bytes) " + repr(bytes(c if 32 <= c < 127 else 46 for c in body[:400]).decode())
        else:
            extra = f"({len(body)} bytes)"
        lines.append(f"{indent}{name} {extra}")


def main() -> None:
    map_name = sys.argv[1] if len(sys.argv) > 1 else "SouthernShelf_P"
    pkg = Package(COOKED / f"{map_name}.upk")
    try:
        lines.append(f"== {map_name}.upk: exports with TacticalMap / Fog / TacMap in their path")
        movie_idx = None
        for i, e in enumerate(pkg.exports):
            path = pkg.path(i)
            if any(s in path.lower() for s in ("tacticalmap", "fog", "tacmap")):
                cls = pkg.class_name(i)
                lines.append(f"   {cls} {path}")
                if cls == "SwfMovie":
                    movie_idx = i
        lines.append("== imports with TacMap / Fog in their name")
        for imp in pkg.imports:
            if any(s in imp["name"].lower() for s in ("tacmap", "fog")):
                lines.append(f"   {imp}")
        for i, e in enumerate(pkg.exports):
            if pkg.class_name(i) == "Texture2D" and "tacmap" in pkg.path(i).lower():
                tp, _ = pkg.properties(pkg.export_data(i))
                size = [struct.unpack("<i", tp[k][1])[0] for k in ("SizeX", "SizeY") if k in tp]
                fmt = pkg.name_value(tp["Format"][1]) if "Format" in tp else "?"
                lines.append(f"== texture {pkg.path(i)}: {size} {fmt}")
        for i, e in enumerate(pkg.exports):
            if pkg.class_name(i) == "SwfMovie":
                dump_movie(pkg, i)
    finally:
        pkg.close()


def dump_movie(pkg, movie_idx: int) -> None:  # noqa: ANN001
    if True:
        lines.append(f"== SwfMovie {pkg.path(movie_idx)}")
        props, _ = pkg.properties(pkg.export_data(movie_idx))
        lines.append(f"== the movie's properties: {sorted(props)}")
        for k, (t, v) in props.items():
            if k != "RawData":
                lines.append(f"   {k} ({t}): {v[:64]!r}")
        raw = props["RawData"][1]
        raw = raw[4 : 4 + struct.unpack_from("<i", raw)[0]]
        d = raw[:8] + zlib.decompress(raw[8:]) if raw[:3] == b"CFX" else raw
        b = _Bits(d, 8)
        lines.append(f"== movie {d[:3]!r} v{d[3]} stage=" + ",".join(f"{v:.1f}" for v in _rect(b)))
        o = b.align() + 4
        dump_tags(d, o, "   ")


main()
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{len(lines)} lines -> {OUT}")
