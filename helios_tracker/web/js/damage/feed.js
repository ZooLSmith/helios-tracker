// The damage log's feed: the stream's "damage" messages (server.py _Events) into the store, and the catch-up.
// - {"sid", "t0", "seq", "catchup": 1}: the page is new or too far behind - the history fetched (GET /damage?since=
//   the last batch it has), then the stream followed from there;
// - {"sid", "b": [batches]}: the batches it lacks, each numbered ("q") - one missing (a gap): the history asked again.
// A new "sid" (the mod reloaded, the log switched off): the store dropped, everything fetched again. While a catch-up
// is on its way, the stream's batches wait; those it already brought are skipped.

/** The feed of `store`: a function taking the stream's messages. `fetchJson(url)`: the request (a promise of JSON). */
import { timed } from "./perf.js";

export function createFeed(store, fetchJson, changed = () => {}) {
  let seq = 0; // the last batch the store has
  let fetching = false, again = false;
  let waiting = []; // the stream's batches while a catch-up is on its way

  function newSession(sid, t0) {
    store.reset(sid, t0);
    seq = 0;
    waiting = [];
  }

  function apply(batches) {
    for (const b of batches) {
      if (b.q <= seq) continue; // (brought by a catch-up already)
      if (b.q > seq + 1) { catchUp(); return; } // a gap: the history has it (and what follows)
      timed("store: a batch", () => store.add(b));
      seq = b.q;
    }
    changed();
  }

  async function catchUp() {
    if (fetching) { again = true; return; }
    fetching = true;
    try {
      do {
        again = false;
        const r = await fetchJson(`/damage?since=${seq}`);
        if (!r.sid) break; // (no log in this session yet)
        if (r.sid !== store.sid) newSession(r.sid, r.t0);
        store.t0 = r.t0;
        store.define(r.defs);
        for (const b of r.b || []) {
          if (b.q <= seq) continue;
          timed("store: a catch-up batch", () => store.add(b)); // (one before missing: past the server's history - gone)
          seq = b.q;
        }
      } while (again);
    } catch (err) {
      console.warn("damage log: catch-up failed", err); // (the next gap asks again; the game gone: the page reloads)
    }
    fetching = false;
    const queued = waiting;
    waiting = [];
    apply(queued);
  }

  return function onMessage(msg) {
    if (msg.sid !== store.sid) newSession(msg.sid, msg.t0);
    if (msg.catchup) { catchUp(); return; }
    if (fetching) { waiting.push(...(msg.b || [])); return; }
    apply(msg.b || []);
  };
}
