// A virtual list (the user: thousands of log lines as as many divs - only the ones in view are): a scrolling element
// holds a spacer as tall as every line, and in it the lines in view (a few more each side) at their place. Every line
// the same height - one line measured once drawn (the interface size changes it). Drawn again on a scroll (the
// browser's event: no timer) or new lines; the DOM written only when what's in view changed.
const OVERSCAN = 10;

/** A list in `scroller` (emptied): returns { set(count, render, resetScroll), redraw() } - render(i) a line's HTML. */
export function virtualList(scroller) {
  scroller.innerHTML = `<div class="vspace"><div class="vrows"></div></div>`;
  const space = scroller.firstElementChild, rows = space.firstElementChild;
  let count = 0, render = () => "", rowPx = 0, shown = "";
  function redraw() {
    const px = rowPx || 20, top = scroller.scrollTop, height = scroller.clientHeight || 600;
    const first = Math.max(0, Math.floor(top / px) - OVERSCAN), last = Math.min(count, Math.ceil((top + height) / px) + OVERSCAN);
    space.style.height = `${count * px}px`;
    let html = "";
    for (let i = first; i < last; i++) html += render(i);
    const key = `${first}|${html}`;
    if (key !== shown) {
      shown = key;
      rows.style.transform = `translateY(${first * px}px)`;
      rows.innerHTML = html;
    }
    // (the height a line takes, measured: then drawn again on it)
    const measured = rows.firstElementChild?.offsetHeight || 0;
    if (measured && measured !== rowPx) { rowPx = measured; shown = ""; redraw(); }
  }
  scroller.addEventListener("scroll", redraw, { passive: true });
  return {
    set(n, fn, resetScroll = false) {
      count = n;
      render = fn;
      if (resetScroll) scroller.scrollTop = 0;
      redraw();
    },
    redraw,
  };
}
