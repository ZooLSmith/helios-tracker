// The damage log's store (no DOM): what the mod's log sends (helios_tracker/damage.py - its batches, the definitions
// they bring), kept for the page's views. Two levels (design.md "The page"):
// - the hits, kept for a time (Keep hits for: settings.view.keepHits, minutes): typed arrays, a column per field, in
//   blocks of a minute - expiring drops whole blocks; a safety cap (MAX_HITS: a pathological rate), the oldest first;
// - per-second totals for the whole session, never dropped: per player, dealt / taken;
// - each victim's life (lives): who took how much of it - its contributions (contribution()), a fading score - for the
//   session (the Realtime tab: a card's bar is the enemy's whole life, the slider only picks who's shown).
// A hit's extras (damage.py _extra): its overkill ("o": its health past what was left - out of a contribution, in the
// damage dealt), slag's share of it ("g") and who slagged the target ("by": the share theirs, split equally - design.md).
// Times are the log's: ms since its start (t0, epoch ms). Rows come nearly sorted (a batch per tick, a hit's time
// taken in its hook): each is put in its place.

/** A hit's flags (damage.py's bits). */
export const FLAG = { CRIT: 1, TICK: 2, KILL: 4, EFFECT: 8, DOWNED: 16, WIND: 32, FOLDED: 64, HEAL: 128 };

/** A heal (an ally's hit converted to healing - notes.md "Healing"): its amounts given back, in no damage total. */
export const isHeal = (h) => !!(h.f & FLAG.HEAL);

export const KEEP = { min: 1, max: 120, def: 30 }; // Keep hits for, minutes (settings.view.keepHits - a slider; default 30: the user)

/** A keep time as kept: whole minutes, in the slider's range (an unknown value: the default). */
export const keepMinutes = (n) => (Number.isFinite(+n) && +n > 0 ? Math.min(KEEP.max, Math.max(KEEP.min, Math.round(+n))) : KEEP.def);
const BLOCK_MS = 60000;
const MAX_HITS = 1000000;
const PLAYER_KINDS = new Set(["me", "player"]);
const SCORE_HALF_MS = 10000; // a victim's score halved every this long (design.md: ~10 s)

/** Who a hit's damage counts for (design.md, the user): the shooter - "hits" (0) or "ticks" (1) -, but slag's share
 *  of it to whoever slagged the target ("slag", 2: split equally - the shooter among them keeps theirs); its overkill
 *  out (a contribution stops at the kill; the damage dealt doesn't). fn(source, kind, amount) for each part. One's own
 *  damage on oneself: none (the user). */
export function contribution(store, h, fn) {
  if (!h.a || h.a === h.v || isHeal(h)) return;
  const amount = Math.max(0, h.h - h.o) + h.s;
  if (amount <= 0) return;
  const by = h.by ? store.groups[h.by] : null;
  const slag = by?.length ? amount * h.g : 0;
  fn(h.a, h.f & FLAG.TICK ? 1 : 0, amount - slag);
  if (slag) for (const id of by) fn(id, 2, slag / by.length);
}

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
      e: new Uint16Array(cap), c: new Uint16Array(cap), o: new Float32Array(cap), g: new Float32Array(cap),
      by: new Uint16Array(cap), // (an index in the store's groups: who slagged it - 0 none)
    };
    if (old) for (const k in old) this.cols[k].set(old[k].subarray(0, this.n));
  }

  /** A hit put in its place (by time: from the end - nearly always the end itself). */
  insert(t, serial, row, by) {
    if (this.n === this.cols.t.length) this.alloc(this.n * 2);
    const c = this.cols;
    let i = this.n;
    while (i > 0 && c.t[i - 1] > t) i--;
    if (i < this.n) for (const k in c) c[k].copyWithin(i + 1, i, this.n);
    c.t[i] = t; c.serial[i] = serial; c.a[i] = row[1]; c.v[i] = row[2]; c.h[i] = row[3]; c.s[i] = row[4];
    c.f[i] = row[5]; c.w[i] = row[6]; c.e[i] = row[7]; c.c[i] = row[8] || 1;
    const x = row[9] || {};
    c.o[i] = x.o || 0; c.g[i] = x.g || 0; c.by[i] = by;
    this.n++;
  }

  hit(i) {
    const c = this.cols;
    return { t: c.t[i], serial: c.serial[i], a: c.a[i], v: c.v[i], h: c.h[i], s: c.s[i], f: c.f[i], w: c.w[i], e: c.e[i], c: c.c[i],
      o: c.o[i], g: c.g[i], by: c.by[i] };
  }
}

export class DamageStore {
  constructor() { this.reset("", 0); }

  /** A new session (the server's "sid": the mod reloaded, the log switched off and on): everything dropped. */
  reset(sid, t0) {
    this.sid = sid;
    this.t0 = t0 || 0; // the log's start, epoch ms
    this.actors = new Map(); this.whats = new Map(); this.elements = new Map(); // id -> definition (damage.py)
    // a player back under a new id (reconnected: a new controller - damage.py keys a player by theirs) is the one of
    // that name already in the log (the user): alias (new id -> the first one's), every hit and event put under it
    this.alias = new Map(); this.playerByName = new Map(); // (name -> its first player id)
    this.blocks = []; // in time order
    this.count = 0; // hits kept
    this.serial = 0; // hits ever added (a hit's serial: what an event's link names)
    this.events = []; // {t, kind, actor, other, hit (a serial, -1: none), rest}, in time order
    this.seconds = new Map(); // second -> Map(player id -> [dealt, taken]): the session's, never dropped
    this.maxHit = 0; // the biggest hit seen in the session (health + shield): the amount column's width (amount.js)
    this.heat = new Map(); // second -> all the damage dealt in it (not on oneself), as long as the hits are kept: the
    // time window's heatmap (window.js)
    this.groups = [[]]; this.groupIndex = new Map(); // who slagged a hit: [ids] by index (a hit's "by"; 0: none)
    this.lives = new Map(); // victim -> {parts: Map(source -> [hits, ticks, slag]), total, score, at, last, death}
    this.keepMs = KEEP.def * BLOCK_MS;
    this.version = 0; // bumped on any change (the views redraw on a new one)
  }

  /** The definitions a batch or a catch-up brings ({a, w, e}: id -> definition; a newer one replaces). */
  define(defs) {
    if (!defs) return;
    for (const [kind, map] of [["w", this.whats], ["e", this.elements]]) {
      for (const [id, def] of Object.entries(defs[kind] || {})) map.set(Number(id), def);
    }
    for (const [key, def] of Object.entries(defs.a || {})) this.defineActor(Number(key), def);
    this.version++;
  }

  /** An actor's definition: a player's first one named like a player already in the log (reconnected) - the id an
   *  alias of theirs, the definition theirs (its map link the new pawn's; their number - their colour - kept). */
  defineActor(id, def) {
    const name = PLAYER_KINDS.has(def.k) && !def.raw ? def.n || "" : "";
    const first = this.alias.get(id) ?? (name && !this.actors.has(id) ? this.playerByName.get(name) : undefined);
    if (first !== undefined && first !== id) {
      const old = this.actors.get(first);
      this.alias.set(id, first);
      this.actors.set(first, { ...def, k: old?.k ?? def.k, o: old?.o ?? def.o });
      return;
    }
    this.actors.set(id, def);
    if (name && !this.playerByName.has(name)) this.playerByName.set(name, id);
  }

  /** The id a hit or an event is put under (a reconnected player's: their first one). */
  actorId(id) { return this.alias.size ? this.alias.get(id) ?? id : id; }

  /** A batch (damage.py: {q, h: hits, v: events, a / w / e: definitions}). */
  add(batch) {
    this.define(batch);
    const first = this.serial;
    for (const row of batch.h || []) this.addHit(row);
    for (const ev of batch.v || []) {
      const [t, kind, actor, other, hit, ...rest] = ev;
      const e = { t, kind, actor: this.actorId(actor), other: this.actorId(other), hit: hit >= 0 ? first + hit : -1, rest };
      let i = this.events.length;
      while (i > 0 && this.events[i - 1].t > t) i--;
      this.events.splice(i, 0, e);
    }
    this.version++;
  }

  addHit(row) {
    if (this.alias.size) { // (a reconnected player's ids: their first one - a slagger's too, once each)
      row[1] = this.actorId(row[1]); row[2] = this.actorId(row[2]);
      if (row[9]?.by) row[9] = { ...row[9], by: [...new Set(row[9].by.map((x) => this.actorId(x)))] };
    }
    const t = row[0], key = Math.floor(t / BLOCK_MS);
    let i = this.blocks.length;
    while (i > 0 && this.blocks[i - 1].key > key) i--;
    let block = i > 0 && this.blocks[i - 1].key === key ? this.blocks[i - 1] : null;
    if (!block) { block = new Block(key); this.blocks.splice(i, 0, block); }
    const by = this.group(row[9]?.by);
    block.insert(t, this.serial++, row, by);
    this.count++;
    const amount = row[3] + row[4];
    const sec = Math.floor(t / 1000);
    if (row[5] & FLAG.HEAL) { // (a heal: in no damage total - the log's lines and the Recap's healing only)
      while (this.count > MAX_HITS && this.blocks.length > 1) this.count -= this.blocks.shift().n;
      return;
    }
    if (amount > this.maxHit) this.maxHit = amount;
    if (row[1] !== row[2]) this.heat.set(sec, (this.heat.get(sec) || 0) + amount);
    for (const [id, side] of [[row[1], 0], [row[2], 1]]) {
      if (!PLAYER_KINDS.has(this.actors.get(id)?.k)) continue;
      let s = this.seconds.get(sec);
      if (!s) this.seconds.set(sec, s = new Map());
      let v = s.get(id);
      if (!v) s.set(id, v = [0, 0]);
      v[side] += amount;
    }
    if (row[1] !== row[2] && row[2]) this.live(row, by);
    while (this.count > MAX_HITS && this.blocks.length > 1) this.count -= this.blocks.shift().n;
  }

  /** The index of a group of slaggers ([ids]; none: 0). */
  group(ids) {
    if (!ids?.length) return 0;
    const key = ids.join(",");
    let i = this.groupIndex.get(key);
    if (i === undefined) { i = this.groups.length; this.groups.push(ids.slice()); this.groupIndex.set(key, i); }
    return i;
  }

  /** A hit into its victim's life: its contributions, its score (fading: halved every SCORE_HALF_MS - a fight going on
   *  rises, an old one sinks: the Realtime tab's order), its killing blow. */
  live(row, by) {
    const v = row[2];
    let life = this.lives.get(v);
    if (!life) this.lives.set(v, life = { parts: new Map(), total: 0, score: 0, at: row[0], last: -Infinity, death: -Infinity });
    const h = { a: row[1], h: row[3], s: row[4], f: row[5], o: row[9]?.o || 0, g: row[9]?.g || 0, by };
    let total = 0;
    contribution(this, h, (source, kind, amount) => {
      let p = life.parts.get(source);
      if (!p) life.parts.set(source, p = [0, 0, 0]);
      p[kind] += amount;
      total += amount;
    });
    life.total += total;
    const t = row[0];
    life.score = life.score * 0.5 ** (Math.max(0, t - life.at) / SCORE_HALF_MS) + total;
    life.at = Math.max(life.at, t);
    life.last = Math.max(life.last, t);
    if (row[5] & FLAG.KILL) life.death = Math.max(life.death, t);
  }

  /** A victim's score at `now` (its fading damage taken). */
  score(life, now = this.now()) { return life.score * 0.5 ** (Math.max(0, now - life.at) / SCORE_HALF_MS); }

  /** The log's time now (ms since its start). */
  now() { return this.t0 ? Date.now() - this.t0 : 0; }

  /** Keep hits for `minutes` (settings.view.keepHits). */
  setKeep(minutes) {
    this.keepMs = keepMinutes(minutes) * BLOCK_MS;
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
    for (const sec of this.heat.keys()) { // (in time order, give or take a late batch: up to the first one kept)
      if (sec * 1000 >= cutoff) break;
      this.heat.delete(sec);
    }
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
