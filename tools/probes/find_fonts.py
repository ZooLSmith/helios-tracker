# Dev tool (offline): where BL2 keeps its fonts - UE3 Font objects (bitmap pages) and Scaleform font
# libraries (SwfMovie with DefineFont2/3 tags: vector glyphs) - in the game's startup / UI packages.
#   python tools/probes/find_fonts.py [package ...]   (default: the startup packages + GFxUI)
# Writes tools/probes/find_fonts.txt (overwrites)
# The game: project.json's game.path
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tools/: project.py
import project  # noqa: E402

# upk.py / swf.py alone (the package's __init__ needs the SDK)
def _alone(name):  # noqa: ANN001, ANN202
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "helios_tracker" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_upk, _swf = _alone("upk"), _alone("swf")
Package, _Bits, _rect, _tags = _upk.Package, _swf._Bits, _swf._rect, _swf._tags

COOKED = project.require(project.cooked_dir(), "The game's CookedPCConsole")
OUT = Path(__file__).with_suffix(".txt")
lines: list[str] = []
state_movies = [0]


def fonts_in_movie(raw: bytes) -> list[str]:
    """The fonts a Scaleform movie defines: DefineFont2 (48) / DefineFont3 (75) - name, glyph count, flags."""
    if raw[:3] == b"CFX":
        d = raw[:8] + zlib.decompress(raw[8:])
    elif raw[:3] == b"GFX":
        d = raw
    else:
        return [f"(not a movie: {raw[:3]!r})"]
    b = _Bits(d, 8)
    _rect(b)
    out = []
    for code, body in _tags(d, b.align() + 4):
        if code in (48, 75):
            fid, flags = struct.unpack_from("<HB", body)
            name_len = body[4]
            name = body[5 : 5 + name_len].decode("latin1", "replace").rstrip("\0")
            glyphs = struct.unpack_from("<H", body, 5 + name_len)[0]
            out.append(f"DefineFont{2 if code == 48 else 3} id={fid} {name!r} glyphs={glyphs} flags={flags:#04x}"
                       f"{' bold' if flags & 1 else ''}{' italic' if flags & 2 else ''}")
        elif code in (91, 1005):  # DefineFont4 / GFx DefineCompactedFont (Scaleform's own)
            fid = struct.unpack_from("<H", body)[0]
            out.append(f"{'DefineFont4' if code == 91 else 'GFx DefineCompactedFont'} id={fid} ({len(body)} bytes) {bytes(c if 32 <= c < 127 else 46 for c in body[2:60]).decode()!r}")
        elif code == 88:  # DefineFontName: the font's name / copyright
            out.append(f"DefineFontName {bytes(c if 32 <= c < 127 else 46 for c in body[:80]).decode()!r}")
    return out


def scan(path: Path) -> None:
    try:
        pkg = Package(path)
    except Exception as ex:  # noqa: BLE001
        lines.append(f"== {path.name}: can't read ({type(ex).__name__}: {ex})")
        return
    try:
        hits = []
        for i, _e in enumerate(pkg.exports):
            cls = pkg.class_name(i)
            p = pkg.path(i)
            if cls in ("Font", "MultiFont"):
                hits.append(f"   {cls} {p}")
            elif cls == "SwfMovie":
                raw = b""
                try:
                    props, _ = pkg.properties(pkg.export_data(i))
                    raw = props["RawData"][1]
                    raw = raw[4 : 4 + struct.unpack_from("<i", raw)[0]]
                    fonts = fonts_in_movie(raw)
                except Exception as ex:  # noqa: BLE001
                    fonts = [f"(error {type(ex).__name__}: {ex})"]
                movies = hits.count  # (counted below)
                state_movies[0] += 1
                if fonts:
                    hits.append(f"   SwfMovie {p} ({len(raw)} bytes):")
                    hits += [f"      {f}" for f in fonts]
        lines.append(f"== {path.name}: {len(hits)} lines, {state_movies[0]} movies scanned so far")
        lines.extend(hits)
    finally:
        pkg.close()


names = sys.argv[1:] or [p.name for p in sorted(COOKED.glob("Startup*.upk"))] + ["GFxUI.upk", "Engine.upk", "WillowGame.upk"]
for n in names:
    if (COOKED / n).is_file():
        scan(COOKED / n)
    else:
        lines.append(f"== {n}: not found")
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{len(lines)} lines -> {OUT}")
