// The damage log's Recap tab (view.js - design.md "The rework", the user's ideas): who did what over a stretch of time
// (the range shared with the Log tab). Its own tabs: Enemies, then one per player.
// - Enemies: a card per enemy / object damaged in the range (each its own - six Psychos, six cards), the biggest pool
//   first (max health + shield: parts.js maxPool), then the latest hit. Its bar (bars.js): as wide as its pool against
//   the biggest listed (the user: a boss the whole width, a quarter of it a quarter), filled by what each source took
//   off it in the range - a contribution (store.js): a killing blow's overkill out, slag's share of a hit its slagger's.
//   Under it what it took (the Overview's, which this replaces): a row per who / what with / element / hit or tick, the
//   latest first, no weapon names (icons; the tooltip has it); the ticks of an attacker with an effect still going on
//   it pinned on top; rows under 2 % folded in "+ N more"; the killing blow marked. The search filters the hits.
// - A player: what they did - damage dealt (every hit's full amount, overkill in: the weapons' numbers), their
//   contribution, the slag they brought to others' hits, kills, healing given, damage taken -, and a row per weapon /
//   element / hits or ticks: the amount, its share, hits, crits, kills.
// One's own damage on oneself left out everywhere (the user); a heal in no damage total.
import { esc } from "../dom.js";
import { num, t } from "../i18n.js";
import { tipSections } from "../ui/hovertip.js";
import { amountText, isShortened } from "./amount.js";
import { barHtml, legendHtml, partLabel, percentText } from "./bars.js";
import { actorHtml, actorName, defName, elementIcon, isPlayer, maxPool, playerOrder, whatIcons } from "./parts.js";
import { hitMatches } from "./search.js";
import { FLAG, contribution, isHeal } from "./store.js";

const ACTORS = 100; // cards at most
const FOLD_SHARE = 0.02; // a row under this share of what its actor took: folded (design.md: ~2 %, to tune)
const MIN_WIDTH = 0.04; // a bar's track never narrower than this share (a Psycho beside a boss: still a bar)

/** The effects still going on (applied, not ended - the events: exact), as of the kept events: victim -> Set(who
 *  applied them). */
function runningEffects(store) {
  const count = new Map();
  for (const e of store.events) {
    if (e.kind !== "fx+" && e.kind !== "fx-") continue;
    const key = `${e.actor}|${e.other}|${e.rest[1]}`;
    const n = (count.get(key) || 0) + (e.kind === "fx+" ? 1 : -1);
    if (n > 0) count.set(key, n); else count.delete(key);
  }
  const out = new Map();
  for (const key of count.keys()) {
    const [victim, by] = key.split("|").map(Number);
    if (!out.has(victim)) out.set(victim, new Set());
    out.get(victim).add(by);
  }
  return out;
}

const addRow = (rows, key, init, h, amount) => {
  let r = rows.get(key);
  if (!r) rows.set(key, r = { ...init, amount: 0, n: 0, crits: 0, kills: 0, last: -Infinity });
  r.amount += amount;
  r.n += h.f & FLAG.FOLDED ? h.c : 1;
  if (h.f & FLAG.CRIT) r.crits++;
  if (h.f & FLAG.KILL) r.kills++;
  r.last = Math.max(r.last, h.t);
};

/** What happened in [t1, t2]: the victims (not players) and the players, each with their numbers and rows. */
export function gatherRecap(store, t1, t2, words = []) {
  const victims = new Map(), players = new Map();
  const victim = (id) => {
    let x = victims.get(id);
    if (!x) victims.set(id, x = { id, taken: 0, parts: new Map(), rows: new Map(), last: -Infinity, death: -Infinity });
    return x;
  };
  const player = (id) => {
    let x = players.get(id);
    if (!x) players.set(id, x = { id, dealt: 0, contrib: 0, slag: 0, kills: 0, healed: 0, taken: 0, rows: new Map() });
    return x;
  };
  for (const id of playerOrder(store)) player(id); // (every player a tab, whatever they did)
  store.forEachHit(t1, t2, (h) => {
    if (h.a === h.v || !hitMatches(words, store, h)) return; // (on oneself: not counted - the user)
    const amount = h.h + h.s, tick = h.f & FLAG.TICK ? 1 : 0;
    if (isHeal(h)) { if (h.a && isPlayer(store, h.a)) player(h.a).healed += amount; return; }
    if (h.a && isPlayer(store, h.a)) {
      const p = player(h.a);
      p.dealt += amount;
      if (h.f & FLAG.KILL) p.kills++;
      addRow(p.rows, `${h.w}|${h.e}|${tick}`, { w: h.w, e: h.e, tick }, h, amount);
    }
    if (!h.v) return;
    if (isPlayer(store, h.v)) player(h.v).taken += amount;
    contribution(store, h, (source, kind, part) => {
      if (isPlayer(store, source)) { const p = player(source); p.contrib += part; if (kind === 2) p.slag += part; }
      if (isPlayer(store, h.v)) return;
      const v = victim(h.v);
      let p = v.parts.get(source);
      if (!p) v.parts.set(source, p = [0, 0, 0]);
      p[kind] += part;
    });
    if (isPlayer(store, h.v)) return;
    const v = victim(h.v);
    v.taken += amount;
    v.last = Math.max(v.last, h.t);
    if (h.f & FLAG.KILL) v.death = Math.max(v.death, h.t);
    addRow(v.rows, `${h.a}|${h.w}|${h.e}|${tick}`, { a: h.a, w: h.w, e: h.e, tick }, h, amount);
  });
  for (const e of store.events) { // (dead outside a hit too: a fall)
    if (e.t > t2) break;
    if (e.kind === "died" && victims.has(e.actor)) victims.get(e.actor).death = Math.max(victims.get(e.actor).death, e.t);
  }
  return { victims, players };
}

const countText = (r) => (r.tick ? (r.n === 1 ? t("dmg.oneTick") : t("dmg.nTicks", { n: r.n }))
  : r.n === 1 ? t("dmg.oneHit") : t("dmg.nHits", { n: r.n }));

/** A row of what an enemy took: who > what with (icons - the user: no weapon names, its tooltip has it), how many, the
 *  amount. */
function takenRowHtml(store, victimId, r) {
  const what = defName(store.whats.get(r.w)), el = store.elements.get(r.e);
  const tip = tipSections(what || actorName(store, r.a), [
    { kind: "meta", lines: [`${actorName(store, r.a)} → ${actorName(store, victimId)}`] },
    { kind: "stats", lines: [isShortened(r.amount) ? num(Math.round(r.amount)) : "", el?.eln || "",
      r.crits ? t("dmg.critsN", { n: r.crits }) : ""] },
  ]);
  const kill = r.kills > 0;
  return `<div class="dmsrow${kill ? " kill" : ""}"${tip}><span class="dmwho">${actorHtml(store, r.a)}` +
    // (its "›" only before something: a melee, no element - nothing to point at)
    `${(icons => (icons ? `<span class="dmarrow">›</span>${icons}` : ""))(whatIcons(store, r.w, r.e))}</span>` +
    `<span class="dmtags">${kill ? `<span class="dmtag kill">${esc(t("dmg.dead"))}</span>` : ""}</span>` +
    `<span class="dmcount">${esc(countText(r))}</span><span class="dmamt">${esc(amountText(r.amount))}</span></div>`;
}

const byLast = (a, b) => b.last - a.last;

/** An enemy's rows: the effects still going on (pinned), the others, the small ones folded. */
function takenRowsHtml(store, x, running, more) {
  const from = running.get(x.id) || new Set(), rows = [...x.rows.values()];
  const pinned = rows.filter((r) => r.tick && from.has(r.a)).sort(byLast);
  const rest = rows.filter((r) => !pinned.includes(r)).sort(byLast);
  let small = rest.filter((r) => !r.kills && r.amount < FOLD_SHARE * x.taken);
  if (small.length < 2) small = []; // (one row folded in a "+ 1 more": no shorter)
  const shown = rest.filter((r) => !small.includes(r)), open = more.has(x.id);
  let html = "";
  if (pinned.length) {
    html += `<div class="dmpinned"><div class="dmsubhead">${esc(t("dmg.running"))}</div>` +
      pinned.map((r) => takenRowHtml(store, x.id, r)).join("") + `</div>`;
  }
  html += shown.map((r) => takenRowHtml(store, x.id, r)).join("");
  if (small.length) {
    if (open) html += small.map((r) => takenRowHtml(store, x.id, r)).join("");
    const sum = small.reduce((s, r) => s + r.amount, 0);
    html += `<button class="islink dmmore" data-dmmore="${x.id}">` +
      `${esc(open ? t("dmg.less") : t("dmg.more", { n: small.length, amount: amountText(sum) }))}</button>`;
  }
  return `<div class="dmrows">${html}</div>`;
}

/** The Enemies tab's HTML. */
function enemiesHtml(store, data, words, more) {
  const running = runningEffects(store);
  const list = [...data.victims.values()].map((x) => ({ ...x, pool: maxPool(store, x.id), total: [...x.parts.values()]
    .reduce((s, p) => s + p[0] + p[1] + p[2], 0) }));
  list.sort((a, b) => b.pool - a.pool || b.last - a.last);
  const shown = list.slice(0, ACTORS);
  if (!shown.length) return `<div class="note">${esc(t(words.length ? "dmg.noMatch" : "dmg.quietWindow"))}</div>`;
  // (an unknown pool - never seen on the map, an object: what it took stands for it)
  const sizeOf = (x) => x.pool || x.total;
  const biggest = Math.max(...shown.map(sizeOf), 1);
  const seen = new Set();
  for (const x of shown) for (const id of x.parts.keys()) seen.add(id);
  return legendHtml(store, seen) + shown.map((x) => {
    const dead = x.death > -Infinity, size = sizeOf(x);
    const from = running.get(x.id), fx = from ? [...new Set([...x.rows.values()]
      .filter((r) => r.tick && from.has(r.a)).map((r) => r.e))].map((e) => elementIcon(store, e)).join("") : "";
    const filled = dead ? 1 : size > 0 ? Math.min(1, x.total / size) : 0;
    return `<div class="dmcard${dead ? " dead" : ""}"><div class="dmentry open"><span class="dmwho">${actorHtml(store, x.id)}</span>` +
      `<span class="dmstate">${fx}${dead && ![...x.rows.values()].some((r) => r.kills) ? `<span class="dmtag kill">${esc(t("dmg.dead"))}</span>` : ""}</span>` +
      `<span class="dmstats"><span class="dmstat taken"><span class="dmstatl">${esc(t("dmg.taken"))}</span>${esc(amountText(x.taken))}</span></span></div>` +
      barHtml(store, x.parts, filled, Math.max(MIN_WIDTH, size / biggest)) + takenRowsHtml(store, x, running, more) + `</div>`;
  }).join("");
}

/** A player's tab's HTML. */
function playerHtml(store, data, id) {
  const p = data.players.get(id);
  if (!p) return `<div class="note">${esc(t("dmg.quietWindow"))}</div>`;
  const stat = (key, amount, cls = "") => (amount
    ? `<span class="dmstat ${cls}"><span class="dmstatl">${esc(key)}</span>${esc(amountText(amount))}</span>` : "");
  const head = `<div class="dmcard"><div class="dmentry open"><span class="dmwho">${actorHtml(store, id)}</span><span class="dmstate"></span>` +
    `<span class="dmstats">${stat(t("dmg.dealt"), p.dealt, "dealt")}${stat(t("dmg.contribution"), p.contrib)}` +
    `${stat(partLabel(store, 2), p.slag)}${p.kills ? `<span class="dmstat"><span class="dmstatl">${esc(t("dmg.kills"))}</span>${num(p.kills)}</span>` : ""}` +
    `${stat(t("dmg.healed"), p.healed, "heal")}${stat(t("dmg.taken"), p.taken, "taken")}</span></div>`;
  const rows = [...p.rows.values()].sort((a, b) => b.amount - a.amount);
  if (!rows.length) return head + `<div class="note">${esc(t("dmg.quietWindow"))}</div></div>`;
  return head + `<div class="dmrows">` + rows.map((r) => {
    const what = defName(store.whats.get(r.w)), el = store.elements.get(r.e);
    const tip = tipSections(what || "?", [{ kind: "stats", lines: [isShortened(r.amount) ? num(Math.round(r.amount)) : "",
      el?.eln || "", r.crits ? t("dmg.critsN", { n: r.crits }) : "", r.kills ? `${t("dmg.kills")}: ${num(r.kills)}` : ""] }]);
    return `<div class="dmsrow${r.kills ? " kill" : ""}"${tip}><span class="dmwho">${whatIcons(store, r.w, r.e) || `<span class="dmwhat"></span>`}` +
      `<span class="nm">${esc(what || "?")}</span></span><span class="dmtags"><span class="dmtag">${esc(percentText(r.amount, p.dealt))}</span></span>` +
      `<span class="dmcount">${esc(countText(r))}</span><span class="dmamt">${esc(amountText(r.amount))}</span></div>`;
  }).join("") + `</div></div>`;
}

/** The Recap's HTML. `state`: {tab: "enemies" or a player's id, more: Set(ids whose small rows are shown)}. */
export function recapHtml(store, t1, t2, words = [], state = { tab: "enemies", more: new Set() }) {
  const data = gatherRecap(store, t1, t2, words);
  const ids = playerOrder(store);
  const tab = ids.includes(state.tab) ? state.tab : "enemies";
  const tabs = `<div class="mtools dmrecaptabs"><span class="seg">` +
    `<button data-dmrecap="enemies" class="${tab === "enemies" ? "on" : ""}">${esc(t("dmg.enemies"))}</button>` +
    ids.map((id) => `<button data-dmrecap="${id}" class="${tab === id ? "on" : ""}">${esc(actorName(store, id))}</button>`).join("") +
    `</span></div>`;
  return tabs + (tab === "enemies" ? enemiesHtml(store, data, words, state.more) : playerHtml(store, data, tab));
}

/** The Recap's clicks (on its list, delegated): its tabs, "+ N more" shows / hides an enemy's small rows. */
export function bindRecap(list, state, changed) {
  list.onclick = (e) => {
    const more = e.target.closest("[data-dmmore]"), tab = e.target.closest("[data-dmrecap]");
    if (more) {
      const id = Number(more.dataset.dmmore);
      if (state.more.has(id)) state.more.delete(id); else state.more.add(id);
    } else if (tab) state.tab = tab.dataset.dmrecap === "enemies" ? "enemies" : Number(tab.dataset.dmrecap);
    else return;
    changed();
  };
}
