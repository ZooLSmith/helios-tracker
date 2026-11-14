// The damage log's store (no DOM): what the mod's log sends (helios_tracker/damage.py - its batches, the definitions
// they bring), kept for the page's views. Two levels (design.md "The page"):
// - the hits, kept for a time (Keep hits for: settings.view.keepHits, minutes): typed arrays, a column per field, in
//   blocks of a minute - expiring drops whole blocks; a safety cap (MAX_HITS: a pathological rate), the oldest first;
// - per-second totals for the whole session, never dropped: per player, dealt / taken.
// Times are the log's: ms since its start (t0, epoch ms). Rows come nearly sorted (a batch per tick, a hit's time
// taken in its hook): each is put in its place.

/** A hit's flags (damage.py's bits). */
export const FLAG = { CRIT: 1, TICK: 2, KILL: 4, EFFECT: 8, DOWNED: 16, WIND: 32, FOLDED: 64 };

export const KEEP_CHOICES = [1, 5, 10, 30, 60]; // Keep hits for, minutes (settings.view.keepHits)
const BLOCK_MS = 60000;
const MAX_HITS = 1000000;
const PLAYER_KINDS = new Set(["me", "player"]);

/** A minute of hits: a column per field, grown as needed. */
class Block {
  constructor(key) {
    this.key = key; // its minute (t / BLOCK_MS)
    this.n = 0;
    this.alloc(64);
  }

  alloc(cap) {
    const old = this.cols;
    this.cols = {
      t: new Uint32Array(cap), serial: new Uint32Array(cap), a: new Uint32Array(cap), v: new Uint32Array(cap),
      h: new Float32Array(cap), s: new Float32Array(cap), f: new Uint8Array(cap), w: new Uint32Array(cap),
      e: new Uint16Array(cap), c: new Uint16Array(cap),
    };
    if (old) for (const k in old) this.cols[k].set(old[k].subarray(0, this.n));
  }

  /** A hit put in its place (by time: from the end - nearly always the end itself). */
  insert(t, serial, row) {
    if (this.n === this.cols.t.length) this.alloc(this.n * 2);
    const c = this.cols;
    let i = this.n;
    while (i > 0 && c.t[i - 1] > t) i--;
    if (i < this.n) for (const k in c) c[k].copyWithin(i + 1, i, this.n);
    c.t[i] = t; c.serial[i] = serial; c.a[i] = row[1]; c.v[i] = row[2]; c.h[i] = row[3]; c.s[i] = row[4];
    c.f[i] = row[5]; c.w[i] = row[6]; c.e[i] = row[7]; c.c[i] = row[8] || 1;
    this.n++;
  }

  hit(i) {
    const c = this.cols;
    return { t: c.t[i], serial: c.serial[i], a: c.a[i], v: c.v[i], h: c.h[i], s: c.s[i], f: c.f[i], w: c.w[i], e: c.e[i], c: c.c[i] };
  }
}

export class DamageStore {
  constructor() { this.reset("", 0); }

  /** A new session (the server's "sid": the mod reloaded, the log switched off and on): everything dropped. */
  reset(sid, t0) {
    this.sid = sid;
    this.t0 = t0 || 0; // the log's start, epoch ms
    this.actors = new Map(); this.whats = new Map(); this.elements = new Map(); // id -> definition (damage.py)
    this.blocks = []; // in time order
    this.count = 0; // hits kept
    this.serial = 0; // hits ever added (a hit's serial: what an event's link names)
    this.events = []; // {t, kind, actor, other, hit (a serial, -1: none), rest}, in time order
    this.seconds = new Map(); // second -> Map(player id -> [dealt, taken]): the session's, never dropped
    this.keepMs = 10 * BLOCK_MS;
    this.version = 0; // bumped on any change (the views redraw on a new one)
  }

  /** The definitions a batch or a catch-up brings ({a, w, e}: id -> definition; a newer one replaces). */
  define(defs) {
    if (!defs) return;
    for (const [kind, map] of [["a", this.actors], ["w", this.whats], ["e", this.elements]]) {
      for (const [id, def] of Object.entries(defs[kind] || {})) map.set(Number(id), def);
    }
    this.version++;
  }

  /** A batch (damage.py: {q, h: hits, v: events, a / w / e: definitions}). */
  add(batch) {
    this.define(batch);
    const first = this.serial;
    for (const row of batch.h || []) this.addHit(row);
    for (const ev of batch.v || []) {
      const [t, kind, actor, other, hit, ...rest] = ev;
      const e = { t, kind, actor, other, hit: hit >= 0 ? first + hit : -1, rest };
      let i = this.events.length;
      while (i > 0 && this.events[i - 1].t > t) i--;
      this.events.splice(i, 0, e);
    }
    this.version++;
  }

  addHit(row) {
    const t = row[0], key = Math.floor(t / BLOCK_MS);
    let i = this.blocks.length;
    while (i > 0 && this.blocks[i - 1].key > key) i--;
    let block = i > 0 && this.blocks[i - 1].key === key ? this.blocks[i - 1] : null;
    if (!block) { block = new Block(key); this.blocks.splice(i, 0, block); }
    block.insert(t, this.serial++, row);
    this.count++;
    const amount = row[3] + row[4];
    const sec = Math.floor(t / 1000);
    for (const [id, side] of [[row[1], 0], [row[2], 1]]) {
      if (!PLAYER_KINDS.has(this.actors.get(id)?.k)) continue;
      let s = this.seconds.get(sec);
      if (!s) this.seconds.set(sec, s = new Map());
      let v = s.get(id);
      if (!v) s.set(id, v = [0, 0]);
      v[side] += amount;
    }
    while (this.count > MAX_HITS && this.blocks.length > 1) this.count -= this.blocks.shift().n;
  }

  /** The log's time now (ms since its start). */
  now() { return this.t0 ? Date.now() - this.t0 : 0; }

  /** Keep hits for `minutes` (settings.view.keepHits). */
  setKeep(minutes) {
    this.keepMs = (KEEP_CHOICES.includes(minutes) ? minutes : 10) * BLOCK_MS;
  }

  /** Drops the hits and events older than the time kept (whole blocks: a minute's grace at most). */
  expire(now = this.now()) {
    const cutoff = now - this.keepMs;
    let dropped = 0;
    while (this.blocks.length && (this.blocks[0].key + 1) * BLOCK_MS <= cutoff) {
      dropped += 1;
      this.count -= this.blocks.shift().n;
    }
    let e = 0;
    while (e < this.events.length && this.events[e].t < cutoff) e++;
    if (e) this.events.splice(0, e);
    if (dropped || e) this.version++;
  }

  /** The kept hits' time span ([first, last] ms; null: none). */
  span() {
    if (!this.count) return null;
    const first = this.blocks.find((b) => b.n), last = this.blocks.findLast((b) => b.n);
    return [first.cols.t[0], last.cols.t[last.n - 1]];
  }

  /** Every kept hit from t1 to t2 (ms, both in), in time order: fn(hit) - a new object each. */
  forEachHit(t1, t2, fn) {
    for (const b of this.blocks) {
      if ((b.key + 1) * BLOCK_MS <= t1 || b.key * BLOCK_MS > t2) continue;
      for (let i = 0; i < b.n; i++) {
        const t = b.cols.t[i];
        if (t >= t1 && t <= t2) fn(b.hit(i));
      }
    }
  }

  /** Every kept hit from t2 back to t1 (ms, both in), newest first, until fn(hit) returns false. */
  eachHitBack(t1, t2, fn) {
    for (let k = this.blocks.length - 1; k >= 0; k--) {
      const b = this.blocks[k];
      if (b.key * BLOCK_MS > t2) continue;
      if ((b.key + 1) * BLOCK_MS <= t1) return;
      for (let i = b.n - 1; i >= 0; i--) {
        const t = b.cols.t[i];
        if (t > t2) continue;
        if (t < t1) return;
        if (fn(b.hit(i)) === false) return;
      }
    }
  }

  /** The last `n` hits kept, newest first. */
  latest(n) {
    const out = [];
    for (let k = this.blocks.length - 1; k >= 0 && out.length < n; k--) {
      const b = this.blocks[k];
      for (let i = b.n - 1; i >= 0 && out.length < n; i--) out.push(b.hit(i));
    }
    return out;
  }

  /** A player's totals from t1 to t2 (ms) off the per-second ones (whole seconds: the edges' partial ones in full):
   *  [dealt, taken]. */
  totals(id, t1, t2) {
    const out = [0, 0];
    for (let sec = Math.floor(t1 / 1000), end = Math.floor(t2 / 1000); sec <= end; sec++) {
      const v = this.seconds.get(sec)?.get(id);
      if (v) { out[0] += v[0]; out[1] += v[1]; }
    }
    return out;
  }
}

/** The page's one store (feed.js fills it, the views read it). */
export const damageStore = new DamageStore();
