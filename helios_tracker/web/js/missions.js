// The mission log (the collector's "missionlog"): each mission's state, the tree, objective states.
// Pure (no DOM): tested offline under Node.

/** Picked up and not handed in yet: the game's statuses between Active and Complete (every
 *  required objective done - tools/probe_turnin.txt). */
export const READY = ["ReadyToTurnIn", "RequiredObjectivesComplete"];
const pickedUp = (m) => m.st === "Active" || READY.includes(m.st);

/** "done" / "active" / "ready" (to turn in) / "available" (not started, every mission it needs done,
 *  its giver offered it: "kick") / "unknown" (the same, but not offered yet: still to be found) /
 *  "locked" (a mission it needs isn't done, or it waits on another mission's objective: "wait" - the
 *  game won't offer it before), or "other" for a status the page doesn't know (shown by its game name). */
export function missionState(m, byId) {
  if (m.st === "Complete") return "done";
  if (m.st === "Active") return "active";
  if (READY.includes(m.st)) return "ready";
  if (m.st !== "NotStarted") return "other";
  if (!(m.deps || []).every((d) => byId.get(d)?.st === "Complete")) return "locked";
  if (m.wait && !m.kick) return "locked";
  return m.kick ? "available" : "unknown";
}

/** Where to go for a mission now (tools/probe_area.txt): in progress, where it's done ("go": its
 *  step's station override, else the level the game says - GetLevelForMission; none: null, its origin
 *  isn't where to go); ready, its turn-in station ("tin", else back at its own); not picked up, its own
 *  station - where to grab it (its giver's). { a: the name (the game's), map: its level's map,
 *  why: "step" | "turnin" | "home" } or null. */
export function whereTo(m, state) {
  const home = m.area || m.map ? { a: m.area || "", map: m.map || "", why: "home" } : null;
  if (state === "ready") return m.tin ? { ...m.tin, why: "turnin" } : home && { ...home, why: "turnin" };
  if (state === "active") return m.go ? { ...m.go, why: "step" } : null;
  return home;
}

/** Whether a place (whereTo / a station) is the level the player is in (map names compared). */
export function isHere(place, level) {
  return !!(place && place.map && level && level.map && place.map.toLowerCase() === String(level.map).toLowerCase());
}

/** The mission a side mission hangs under in the tree: the first mission it needs that's in the
 *  log (story missions are a flat list: they chain one after the other). */
function parentOf(m, byId) {
  if (m.plot) return null;
  return (m.deps || []).find((d) => byId.has(d) && d !== m.i) || null;
}

/** { story: [node], other: [node] }, node = { m, state, children: [node] }: story missions in
 *  order, each with the side missions it unlocks under it (recursively); side missions needing
 *  nothing (or nothing in the log) under "other". Sorted by mission number. */
export function missionTree(missions) {
  const byId = new Map(missions.map((m) => [m.i, m]));
  const nodes = new Map(missions.map((m) => [m.i, { m, state: missionState(m, byId), children: [] }]));
  const story = [], other = [];
  for (const node of nodes.values()) {
    const parent = parentOf(node.m, byId);
    if (parent) nodes.get(parent).children.push(node);
    else (node.m.plot ? story : other).push(node);
  }
  const sort = (list) => { list.sort((a, b) => a.m.num - b.m.num); for (const n of list) sort(n.children); return list; };
  return { story: sort(story), other: sort(other), byId };
}

/** The missions by area (the travel station's name the game gives), each area's missions in
 *  mission order, areas in the order of their first mission (roughly the story's); missions with no
 *  area last (area ""). [{ area, nodes: [{ m, state }] }] */
export function missionAreas(missions) {
  const byId = new Map(missions.map((m) => [m.i, m]));
  const areas = new Map();
  for (const m of [...missions].sort((a, b) => a.num - b.num)) {
    const key = m.area || "";
    if (!areas.has(key)) areas.set(key, []);
    areas.get(key).push({ m, state: missionState(m, byId), children: [] });
  }
  return [...areas].map(([area, nodes]) => ({ area, nodes }))
    .sort((a, b) => (a.area === "") - (b.area === "") || a.nodes[0].m.num - b.nodes[0].m.num);
}

/** Text folded for searching: lower case, accents dropped ("Ménage" -> "menage"). */
export function foldText(s) {
  return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

/** The missions matching a search (every word in the name, area, giver or turn-in), in mission
 *  order, as nodes { m, state } - locked ones too. */
export function searchMissions(missions, query) {
  const words = foldText(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const byId = new Map(missions.map((m) => [m.i, m]));
  return missions
    .filter((m) => { const text = foldText([m.n, m.area, m.giver, m.turnin].join(" ")); return words.every((w) => text.includes(w)); })
    .sort((a, b) => a.num - b.num)
    .map((m) => ({ m, state: missionState(m, byId), children: [] }));
}

/** Whether a node or anything under it is visible (locked ones hidden unless showLocked). */
export function nodeVisible(node, showLocked) {
  return showLocked || node.state !== "locked" || node.children.some((c) => nodeVisible(c, showLocked));
}

/** Per objective: { o, i, p, state: "done" | "current" | "pending" } - done: its count reached;
 *  current: in the step the game shows now; pending: later or never (branches). */
export function objectiveStates(m) {
  const cur = new Set(m.cur || []);
  return (m.obj || []).map((o, i) => {
    const p = (m.p || [])[i] || 0;
    const state = p >= o.c ? "done" : cur.has(i) ? "current" : "pending";
    return { o, i, p, state };
  });
}

/** The required objectives not done yet (at least 1: turning it in is a step too) - the "N to do"
 *  of Quick wins and Finish first. */
function objectivesLeft(m) {
  return Math.max(1, objectiveStates(m).filter((o) => o.state !== "done" && !o.o.opt).length);
}

/** Counts per state, for the log's summary line. */
export function missionCounts(missions) {
  const byId = new Map(missions.map((m) => [m.i, m]));
  const counts = { done: 0, active: 0, ready: 0, available: 0, unknown: 0, locked: 0, other: 0 };
  for (const m of missions) counts[missionState(m, byId)]++;
  return counts;
}

/** A mission's reward for a player level (the game scales rewards to the player: the collector sends
 *  one per level of the players whose controller it has - on a co-op client only its own). Not known
 *  for that level: the fallback level's (the local player's), else any level's - a mission's XP goes
 *  by its own level (notes: the XP curve), so it's most likely the same; "from": that level (the page
 *  marks it). null if none. */
export function rewardFor(m, level, fallbackLevel = null) {
  if (!m.rw) return null;
  const own = m.rw[String(level)];
  if (own || fallbackLevel == null) return own || null; // (no fallback asked: that level's only)
  const key = m.rw[String(fallbackLevel)] ? String(fallbackLevel) : Object.keys(m.rw)[0];
  return key ? { ...m.rw[key], from: Number(key) } : null;
}

/** A mission's difficulty for a player, as the game's mission log colours it: its level minus
 *  theirs against the game's thresholds (sent with the log: impossible / hard / tough / normal, else
 *  trivial: far below them - only a category, missions have no outlevel XP penalty). null if the mission has no level yet (set when picked up). */
export function missionDifficulty(m, playerLevel, thresholds) {
  if (!m.ml || !playerLevel || !thresholds) return null;
  const d = m.ml - playerLevel;
  for (const k of ["impossible", "hard", "tough", "normal"]) if (thresholds[k] != null && d >= thresholds[k]) return k;
  return "trivial";
}

export const GOALS = ["xp", "cash", "balanced", "effort", "finish"];

/** The "Best now" ranking for a player level: the missions doable now (active / ready / available / unknown)
 *  and the locked ones a single step away (every mission they need is done, active or offered -
 *  not merely "unknown": a DLC's first mission, never offered, would pull in its whole DLC; "after"
 *  lists what's left), ranked by goal - xp, cash (credits), balanced (both, scaled to the best
 *  mission), effort (balanced per objective left). A mission's better reward counts (the normal or
 *  the alternative one). { rows: [{ m, state, after, xp, cash, effort, known, score }], totalXp } */
export function rankMissions(missions, goal, level, thresholds = null, fallbackLevel = null) {
  const ranked = rankAll(missions, goal, level, fallbackLevel);
  // too high a level to do now (the game's "hard" or "impossible": 3+ above the player; "tough",
  // 1-2 above, stays): left out, counted
  const tooHigh = ranked.rows.filter((r) => ["hard", "impossible"].includes(missionDifficulty(r.m, level, thresholds)));
  if (!tooHigh.length) return { ...ranked, tooHigh: 0, minTooHigh: 0 };
  const rows = ranked.rows.filter((r) => !tooHigh.includes(r));
  return { rows, totalXp: rows.reduce((sum, r) => sum + r.xp, 0), tooHigh: tooHigh.length,
    minTooHigh: Math.min(...tooHigh.map((r) => r.m.ml)) };
}

function rankAll(missions, goal, level, fallbackLevel) {
  // "finish": the missions picked up (their level is locked: their XP is fixed while the player
  // levels up), the furthest below the player first
  if (goal === "finish") {
    const byId = new Map(missions.map((m) => [m.i, m]));
    const rows = missions.filter((m) => pickedUp(m) && m.mlk).map((m) => {
      const rw = rewardFor(m, level, fallbackLevel), sides = rw ? [rw, rw.alt].filter(Boolean) : [];
      return { m, state: missionState(m, byId), after: null, known: !!rw, from: rw ? rw.from : undefined, effort: objectivesLeft(m),
        xp: Math.max(0, ...sides.map((r) => r.xp || 0)), cash: Math.max(0, ...sides.map((r) => (!r.cur || r.cur === "Credits" ? r.cash || 0 : 0))),
        score: level - m.ml };
    }).sort((a, b) => b.score - a.score || a.m.num - b.m.num);
    return { rows, totalXp: rows.reduce((sum, r) => sum + r.xp, 0) };
  }
  const byId = new Map(missions.map((m) => [m.i, m]));
  const states = new Map(missions.map((m) => [m.i, missionState(m, byId)]));
  const doable = (id) => ["active", "ready", "available", "unknown"].includes(states.get(id));
  const underway = (id) => ["active", "ready", "available"].includes(states.get(id)); // started or offered
  // DLCs started (one of their missions active or done): a DLC's missions nobody offered yet only
  // count then - its first missions need nothing, so they'd always look doable
  const started = new Set(missions.filter((m) => m.dlc && (pickedUp(m) || m.st === "Complete")).map((m) => m.dlc));
  const rows = [];
  for (const m of missions) {
    const state = states.get(m.i);
    if (state === "unknown" && m.dlc && !started.has(m.dlc)) continue;
    let after = null;
    if (!doable(m.i)) {
      if (state !== "locked" || !(m.deps || []).every((d) => byId.get(d)?.st === "Complete" || underway(d))) continue;
      // waiting on another mission's objective: one step away only while that mission is under way
      if (m.wait && !(m.wait.m && underway(m.wait.m))) continue;
      after = m.deps.filter((d) => byId.get(d)?.st !== "Complete");
      if (m.wait && !after.includes(m.wait.m)) after.push(m.wait.m);
    }
    const rw = rewardFor(m, level, fallbackLevel), sides = rw ? [rw, rw.alt].filter(Boolean) : [];
    const xp = Math.max(0, ...sides.map((r) => r.xp || 0));
    const cash = Math.max(0, ...sides.map((r) => (!r.cur || r.cur === "Credits" ? r.cash || 0 : 0)));
    const effort = objectivesLeft(m);
    rows.push({ m, state, after, xp, cash, effort, known: !!rw, from: rw ? rw.from : undefined, score: 0 });
  }
  // A locked one's effort includes what's left of the missions it waits on (done first)
  const byRow = new Map(rows.map((r) => [r.m.i, r]));
  for (const r of rows) if (r.after) r.effort += r.after.reduce((sum, d) => sum + (byRow.get(d)?.effort || 0), 0);
  const maxXp = Math.max(1, ...rows.map((r) => r.xp)), maxCash = Math.max(1, ...rows.map((r) => r.cash));
  for (const r of rows) {
    const both = r.xp / maxXp + r.cash / maxCash;
    r.score = goal === "cash" ? r.cash : goal === "balanced" ? both : goal === "effort" ? both / r.effort : r.xp;
  }
  rows.sort((a, b) => b.known - a.known || b.score - a.score || a.m.num - b.m.num);
  return { rows: afterTheirs(rows), totalXp: rows.reduce((sum, r) => sum + r.xp, 0) };
}

/** The ranked rows with every locked one moved just below the last mission it waits on, when it
 *  would rank above it (you can't do it first); the rest keeps its order. */
function afterTheirs(rows) {
  const listed = new Set(rows.map((r) => r.m.i)), placed = new Set(), out = [], waiting = [];
  const ready = (r) => (r.after || []).every((d) => placed.has(d) || !listed.has(d));
  const place = (r) => {
    out.push(r);
    placed.add(r.m.i);
    for (let k = 0; k < waiting.length;) { // whoever was waiting on it, in their ranked order
      if (ready(waiting[k])) place(waiting.splice(k, 1)[0]);
      else k++;
    }
  };
  for (const r of rows) (ready(r) ? place : (x) => waiting.push(x))(r);
  return out.concat(waiting);
}
