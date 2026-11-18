// The damage log's cost on the page (the user: check the impacts): each piece of its work timed - a batch into the
// store, each tab's drawing, Realtime's glide, the Info tab's summary, the range's refresh - calls, mean, max, total,
// and how many ms each second of page time it took. Read in the browser's console: heliosDamagePerf() (a table),
// heliosDamagePerf.reset() (measure one fight alone). The mod's side: tools/probes/damage_log_stats.py.
// Its own cost: two performance.now() a measured call, nothing drawn.

const marks = new Map(); // name -> {n, total, max} (ms)
let since = performance.now();

/** fn() timed under `name`; its result returned. */
export function timed(name, fn) {
  const start = performance.now();
  try {
    return fn();
  } finally {
    const ms = performance.now() - start;
    let m = marks.get(name);
    if (!m) marks.set(name, m = { n: 0, total: 0, max: 0 });
    m.n++;
    m.total += ms;
    if (ms > m.max) m.max = ms;
  }
}

/** The measures as rows (the costliest first) - the console's table. */
export function perfRows() {
  const span = Math.max(1, performance.now() - since) / 1000;
  return [...marks].sort((a, b) => b[1].total - a[1].total).map(([name, m]) => ({
    what: name, calls: m.n, "mean ms": +(m.total / m.n).toFixed(3), "max ms": +m.max.toFixed(2),
    "total ms": +m.total.toFixed(1), "ms / s": +(m.total / span).toFixed(2),
  }));
}

function show() {
  console.log(`damage log, the page: over ${((performance.now() - since) / 1000).toFixed(0)} s`);
  console.table(perfRows());
}
show.reset = () => { marks.clear(); since = performance.now(); console.log("damage log, the page: measures reset"); };
globalThis.heliosDamagePerf = show; // (the console's way in: a dev tool, nothing else reads it)
