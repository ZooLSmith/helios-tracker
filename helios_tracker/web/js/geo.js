// World <-> tactical map transform. Pure (no DOM): tested offline under Node.

export const UU_PER_METER = 100; // 1 uu = 1 cm - measured (tools/probes/probe_scale.py): Salvador (1.62 m) is 152-160 uu tall

/** The largest rectangle of the w x h screen that none of the rects ({left, top, right, bottom}, e.g.
 *  the open panels) covers -> {x, y, w, h}; the whole screen if nothing covers it. Brute force over
 *  the rects' edges: a handful of rects, so a few hundred candidates. */
export function largestFreeRect(w, h, rects) {
  const boxes = rects.map((r) => ({ l: Math.max(0, r.left), t: Math.max(0, r.top), r: Math.min(w, r.right), b: Math.min(h, r.bottom) }))
    .filter((r) => r.r > r.l && r.b > r.t);
  const xs = [...new Set([0, w, ...boxes.flatMap((r) => [r.l, r.r])])].sort((a, b) => a - b);
  const ys = [...new Set([0, h, ...boxes.flatMap((r) => [r.t, r.b])])].sort((a, b) => a - b);
  let best = { x: 0, y: 0, w: 0, h: 0 };
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) {
    const x0 = xs[i], x1 = xs[j];
    for (let k = 0; k < ys.length; k++) for (let m = k + 1; m < ys.length; m++) {
      const y0 = ys[k], y1 = ys[m];
      if ((x1 - x0) * (y1 - y0) <= best.w * best.h) continue;
      if (boxes.some((r) => r.l < x1 && r.r > x0 && r.t < y1 && r.b > y0)) continue; // covered
      best = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }
  }
  return best.w ? best : { x: 0, y: 0, w, h };
}

// The volume's NorthOffsetInDegreesClockwise (level.north) isn't in the map's coordinates: the image fits the world
// unrotated on the levels that set one (Thousand Cuts 180, Opportunity 325...; notes.md) - rotating positions by it put
// the markers wrong (The Dust, 90). The game's map screen turns its whole view by it (MapYawOffset): mapTurn, the
// view's turn (view.js), does the same.

/** World (X, Y) -> tactical map movie px. World +X is up (north), +Y is right. */
export function worldToMap(level, x, y) {
  return [(y - level.center[1]) / level.upp, -(x - level.center[0]) / level.upp];
}

/** Map movie px -> world (X, Y): the inverse of worldToMap. */
export function mapToWorld(level, mx, my) {
  return [level.center[0] - my * level.upp, level.center[1] + mx * level.upp];
}

/** UE yaw (65536 = full turn, 0 = +X) -> clockwise screen angle in radians (0 = up). */
export function yawToAngle(level, yaw) {
  return ((yaw % 65536) / 65536) * 2 * Math.PI;
}

/** The view's turn (S.view.rot) that shows the map like the game's map screen (the sign checked in The Dust). */
export function mapTurn(level) {
  return (level.north || 0) * Math.PI / 180;
}
