// The mission log (the collector's "missionlog"): each mission's state, the tree, objective states.
// Pure (no DOM): tested offline under Node.

/** "done" / "active" / "available" (not started, every mission it needs done, its giver offered
 *  it: "kick") / "unknown" (the same, but not offered yet: still to be found) / "locked", or "other"
 *  for a status the page doesn't know (shown by its game name). */
export function missionState(m, byId) {
  if (m.st === "Complete") return "done";
  if (m.st === "Active") return "active";
  if (m.st !== "NotStarted") return "other";
  if (!(m.deps || []).every((d) => byId.get(d)?.st === "Complete")) return "locked";
  return m.kick ? "available" : "unknown";
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

/** Counts per state, for the log's summary line. */
export function missionCounts(missions) {
  const byId = new Map(missions.map((m) => [m.i, m]));
  const counts = { done: 0, active: 0, available: 0, unknown: 0, locked: 0, other: 0 };
  for (const m of missions) counts[missionState(m, byId)]++;
  return counts;
}
