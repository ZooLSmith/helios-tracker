// Frames are requested, not looped: "smooth" = every animation frame; an fps cap = a timer at that
// interval (animation frames only come when the browser renders, which it may stop doing when
// nothing changes); "updates only" = one frame per change (data, view, input). Changes never draw
// faster than the cap - except what the user does to the view (dragging, zooming: invalidateNow).
// Why cap at all: every frame the page draws, Windows' compositor (DWM) composes the screen again - next to the
// game, a page redrawing at the monitor's rate costs DWM and the GPU real time (stutter in game); a low rate or
// "updates only" keeps them quiet.
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

/** The user moving the view (dragging, zooming): a frame on the next animation frame, whatever the Refresh
 *  rate - someone's using the page. (The capped / "updates only" frames go on as they were.) */
export function invalidateNow() {
  const motion = settings.view.motion;
  if (motion && typeof motion !== "number") { invalidate(); return; } // smooth: every animation frame already
  if (S.pendingNow) return;
  S.pendingNow = true;
  requestAnimationFrame(() => {
    S.pendingNow = false;
    S.lastDraw = performance.now();
    draw();
  });
}
