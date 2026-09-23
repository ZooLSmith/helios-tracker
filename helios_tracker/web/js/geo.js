// World <-> tactical map transform. Pure (no DOM): tested offline under Node.

export const UU_PER_METER = 100; // 1 uu = 1 cm - measured (tools/probe_scale.py): Salvador (1.62 m) is 152-160 uu tall

/** World (X, Y) -> tactical map movie px. World +X is up (north), +Y is right. */
export function worldToMap(level, x, y) {
  let mx = (y - level.center[1]) / level.upp;
  let my = -(x - level.center[0]) / level.upp;
  if (level.north) { // volume's NorthOffsetInDegreesClockwise (0 on every level checked so far)
    const a = level.north * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    [mx, my] = [mx * c - my * s, mx * s + my * c];
  }
  return [mx, my];
}

/** Map movie px -> world (X, Y): the inverse of worldToMap. */
export function mapToWorld(level, mx, my) {
  if (level.north) {
    const a = -level.north * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
    [mx, my] = [mx * c - my * s, mx * s + my * c];
  }
  return [level.center[0] - my * level.upp, level.center[1] + mx * level.upp];
}

/** UE yaw (65536 = full turn, 0 = +X) -> clockwise screen angle in radians (0 = up). */
export function yawToAngle(level, yaw) {
  return ((yaw % 65536) / 65536) * 2 * Math.PI + (level.north || 0) * Math.PI / 180;
}
