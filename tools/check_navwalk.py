# Dev tool (offline): scores tools/probe_navwalk.txt (the player's positions, recorded in game) against the game
# files, for the 3D map study (.agent/notes.md "Level geometry for a 3D map"). Per level:
#  - nav coverage: the share of the player's positions (on foot, walking) with a nav mesh triangle under the feet
#    (within Z_TOL), the uncovered ones grouped into spots (where the 3D map would have holes);
#  - the 2D map's rotation: the share of positions landing on the map image's drawn pixels with the runtime
#    centre, unrotated vs rotated by NorthOffsetInDegreesClockwise (geo.js rotates by it) - on levels with one.
# Needs numpy + Pillow and project.json's game.
#   python tools/check_navwalk.py [probe_navwalk.txt]
import io
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

import project

sys.path.insert(0, str(project.ROOT / "helios_tracker"))
from tacmap import Package, load_tactical_map  # noqa: E402  (no relative imports: loads without the SDK)

Z_TOL = 120.0  # uu between the feet and the nav surface
CELL = 512.0  # the triangle grid's cell, uu
SPOT = 800.0  # uncovered positions closer than this form one spot


def package_index() -> dict[str, Path]:
    game = project.require(project.game_dir(), "the game")
    files: dict[str, Path] = {}
    for f in [*(game / "WillowGame" / "CookedPCConsole").glob("*.upk"), *(game / "DLC").rglob("*.upk")]:
        files.setdefault(f.stem.lower(), f)
    return files


def level_packages(files: dict[str, Path], level: str) -> list[Path]:
    """The persistent package and its streaming levels (the game's own list, not a name prefix)."""
    pf = files[level.lower()]
    names = [level]
    p = Package(pf)
    try:
        for i in range(len(p.exports)):
            if p.class_name(i).startswith("LevelStreaming"):
                props, _ = p.properties(p.export_data(i), 4)
                if "PackageName" in props:
                    names.append(p.name_value(props["PackageName"][1]))
    finally:
        p.close()
    return [files[n.lower()] for n in names if n.lower() in files]


def nav_mesh(packages: list[Path]) -> tuple[np.ndarray, np.ndarray]:
    """Every GBXNavMesh of those packages merged: vertices (n, 3), triangles (m, 3)."""
    verts, tris, base = [], [], 0
    for f in packages:
        p = Package(f)
        try:
            for i in range(len(p.exports)):
                if p.class_name(i) != "GBXNavMesh":
                    continue
                data = p.export_data(i)
                _, o = p.properties(data, 26)
                n = struct.unpack_from("<i", data, o)[0]
                o += 4
                v = np.frombuffer(data, "<f4", 3 * n, o).reshape(n, 3)
                o += 12 * n
                m = struct.unpack_from("<i", data, o)[0]
                o += 4
                t = np.frombuffer(data, "<u2", 7 * m, o).reshape(m, 7)[:, :3].astype(np.int64)
                verts.append(v)
                tris.append(t + base)
                base += n
        finally:
            p.close()
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    return np.concatenate(verts).astype(np.float64), np.concatenate(tris)


class NavIndex:
    def __init__(self, v: np.ndarray, t: np.ndarray) -> None:
        self.v, self.t = v, t
        self.grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        lo = np.floor(v[t][:, :, :2].min(1) / CELL).astype(int)
        hi = np.floor(v[t][:, :, :2].max(1) / CELL).astype(int)
        for k in range(len(t)):
            for gx in range(lo[k, 0], hi[k, 0] + 1):
                for gy in range(lo[k, 1], hi[k, 1] + 1):
                    self.grid[(gx, gy)].append(k)

    def gap(self, x: float, y: float, z: float) -> float | None:
        """The smallest |surface Z - z| over the triangles under (x, y), None when none is."""
        best = None
        for k in self.grid.get((int(np.floor(x / CELL)), int(np.floor(y / CELL))), ()):
            a, b, c = self.v[self.t[k]]
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-9:
                continue
            l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
            l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-4:
                continue
            g = abs(l1 * a[2] + l2 * b[2] + l3 * c[2] - z)
            best = g if best is None else min(best, g)
        return best


def map_alpha(files: dict[str, Path], level: str, movie: str) -> list[tuple[np.ndarray, tuple[float, ...]]]:
    """The tactical map's images: (alpha > 40 mask, bounds in movie px)."""
    pkg = files.get(movie.partition(".")[0].lower()) or files[level.lower()]
    try:
        images = load_tactical_map(pkg, movie)
    except FileNotFoundError:
        images = load_tactical_map(files[level.lower()], movie)
    out = []
    for mi in images:
        fourcc = {"PF_DXT1": b"DXT1", "PF_DXT3": b"DXT3", "PF_DXT5": b"DXT5"}[mi.format]
        w4, h4 = (mi.width + 3) // 4 * 4, (mi.height + 3) // 4 * 4
        dds = (b"DDS " + struct.pack("<7I", 124, 0x81007, h4, w4, len(mi.data), 0, 1) + b"\0" * 44
               + struct.pack("<2I4s5I", 32, 4, fourcc, 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0))
        alpha = np.array(Image.open(io.BytesIO(dds + mi.data)).convert("RGBA"))[:, :, 3] > 40
        out.append((alpha, mi.bounds))
    return out


def on_map(images, pts: np.ndarray, cx: float, cy: float, upp: float, north: float) -> float:  # noqa: ANN001
    """Share of pts landing on drawn map pixels - geo.js's worldToMovie with that north."""
    mx, my = (pts[:, 1] - cy) / upp, -(pts[:, 0] - cx) / upp
    if north:
        a = np.radians(north)
        mx, my = mx * np.cos(a) - my * np.sin(a), mx * np.sin(a) + my * np.cos(a)
    hit = np.zeros(len(pts), bool)
    for alpha, (x0, x1, y0, y1) in images:
        h = alpha.shape[0]
        w = round((x1 - x0) / (y1 - y0) * h) if y1 > y0 else alpha.shape[1]  # stored width is padded to 4
        ix = ((mx - x0) / (x1 - x0) * w).astype(int)
        iy = ((my - y0) / (y1 - y0) * h).astype(int)
        ok = (ix >= 0) & (iy >= 0) & (ix < min(w, alpha.shape[1])) & (iy < h)
        hit[ok] |= alpha[iy[ok], ix[ok]]
    return float(hit.mean()) if len(pts) else 0.0


def spots(points: list[tuple[float, float, float]]) -> list[tuple[int, float, float, float]]:
    """Greedy grouping: (count, x, y, z) of each spot."""
    groups: list[list[tuple[float, float, float]]] = []
    for p in points:
        for g in groups:
            if (g[0][0] - p[0]) ** 2 + (g[0][1] - p[1]) ** 2 < SPOT**2:
                g.append(p)
                break
        else:
            groups.append([p])
    return sorted(((len(g), *np.mean(g, axis=0)) for g in groups), reverse=True)


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else project.ROOT / "tools" / "probe_navwalk.txt"
    levels: dict[str, tuple[str, float, float, float, float] | None] = {}
    samples: dict[str, list[tuple[float, float, float, str, str]]] = defaultdict(list)
    for line in src.read_text(encoding="utf-8").splitlines():
        f = line.split("\t")
        if f[0] == "L":
            levels[f[1]] = (f[2], float(f[3]), float(f[4]), float(f[5]) * 4, float(f[6])) if f[3] else None
        elif f[0] == "P":
            samples[f[2]].append((float(f[3]), float(f[4]), float(f[5]), f[6], f[7]))
    files = package_index()
    for level, pts in samples.items():
        print(f"== {level}: {len(pts)} positions")
        if level.lower() not in files:
            print("   no package found")
            continue
        index = NavIndex(*nav_mesh(level_packages(files, level)))
        walking = [p for p in pts if p[3] == "PHYS_Walking" and not p[4].endswith("Vehicle")]
        covered, missed = 0, []
        for x, y, z, *_ in walking:
            g = index.gap(x, y, z)
            if g is not None and g <= Z_TOL:
                covered += 1
            else:
                missed.append((x, y, z))
        if walking:
            print(f"   on foot, walking: {len(walking)}, nav under the feet: {covered / len(walking):.1%}")
        for n, x, y, z in spots(missed)[:12]:
            print(f"     hole: {n:4d} positions around X {x:8.0f} Y {y:8.0f} Z {z:6.0f}")
        others = defaultdict(int)
        for p in pts:
            if p not in walking:
                others[f"{p[3]} {p[4]}"] += 1
        if others:
            print("   not scored:", dict(others))
        info = levels.get(level)
        if info and info[0]:
            movie, cx, cy, upp, north = info
            try:
                images = map_alpha(files, level, movie)
            except Exception as e:  # noqa: BLE001
                print(f"   map: {e!r}")
                continue
            arr = np.array([p[:2] for p in walking] or [p[:2] for p in pts])
            line = f"   on the 2D map's drawn pixels: unrotated {on_map(images, arr, cx, cy, upp, 0):.1%}"
            if north:
                line += (f", rotated by north {north:g}: {on_map(images, arr, cx, cy, upp, north):.1%}"
                         f", by -north: {on_map(images, arr, cx, cy, upp, -north):.1%}")
            print(line)


if __name__ == "__main__":
    main()
