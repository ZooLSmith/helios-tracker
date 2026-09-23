// Frames are requested, not looped: "smooth" = every animation frame; an fps cap = a timer at that
// interval (animation frames only come when the browser renders, which it may stop doing when
// nothing changes); "updates only" = one frame per change (data, view, input). Changes never draw
// faster than the cap.
import { draw } from "./draw.js";
import { settings } from "./settings.js";
import { S } from "./state.js";

export function invalidate() {
  if (S.pending) return;
  S.pending = true;
  const motion = settings.view.motion;
  const capped = typeof motion === "number" && motion > 0;
  const wait = capped ? Math.max(0, 1000 / motion - (performance.now() - S.lastDraw)) : 0;
  const tick = () => {
    S.pending = false;
    S.lastDraw = performance.now();
    draw();
    if (settings.view.motion) invalidate(); // interpolating: keep going; "updates only": wait for a change
  };
  if (capped) setTimeout(tick, wait);
  else requestAnimationFrame(tick);
}
