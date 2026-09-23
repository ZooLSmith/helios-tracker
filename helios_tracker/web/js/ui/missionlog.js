// The mission log, in the right drawer: the tree (story missions in order, the side missions each
// one unlocks under it; available / active / done, locked ones on request) and a mission's
// details (description, giver, objectives with their progress, what it needs / unlocks).
import { $, esc, gameTextHtml, nameHtml } from "../dom.js";
import { num, t } from "../i18n.js";
import { icon } from "../icons.js";
import { GOALS, missionAreas, missionCounts, missionDifficulty, missionState, missionTree, nodeVisible, objectiveStates,
  rankMissions, rewardFor, searchMissions } from "../missions.js";
import { cleanGameText } from "../model.js";
import { saveSettings, settings } from "../settings.js";
import { S, isTrackedPlayer } from "../state.js";
import { renderPlayers } from "./players.js";

const STATE_ICON = { done: "check", active: "diamond", available: "circle", unknown: "circleDashed", locked: "lock", other: "question" };

/** Opens the log: a mission's details (id), or the tree (no id). Back from a mission opened
 *  directly: the tree. */
export function openMissionLog(id = null) {
  S.missionView = { id, history: [] };
  S.inspect = null;
  S.detail = null;
  $("inspector").classList.add("open");
  renderPlayers();
  renderMissionLog(true);
}

/** The main-mission flag (story missions only: side missions are just grey). */
const storyFlag = (m) => (m.plot ? `<span class="mflag">${esc(t("mdetail.storyFlag"))}</span>` : "");

const stateText = (node) => (node.state === "other" ? cleanGameText(node.m.st) : t("mstate." + node.state));

/** Names the game gives to several missions (the 5 "Message in a Bottle"...): those rows show their
 *  area too, so they don't read as repeats. */
let sharedNames = new Set(), sharedFor = null;
function nameShared(m) {
  if (sharedFor !== S.log) {
    const counts = new Map();
    for (const x of S.log.missions) counts.set(x.n, (counts.get(x.n) || 0) + 1);
    sharedNames = new Set([...counts].filter(([, n]) => n > 1).map(([name]) => name));
    sharedFor = S.log;
  }
  return sharedNames.has(m.n);
}

function rowHtml(node, depth, showLocked, withArea = false) {
  if (!nodeVisible(node, showLocked)) return "";
  const m = node.m, tracked = S.log && S.log.tracked === m.i;
  withArea = withArea || nameShared(m);
  const children = node.children.map((c) => rowHtml(c, depth + 1, showLocked)).join("");
  return `<div class="mrow ${node.state}${m.plot ? " story" : ""}${tracked ? " tracked" : ""}" data-mission="${esc(m.i)}"` +
    ` style="--depth:${Math.min(depth, 6)}" title="${esc(stateText(node))}"><span class="mico">${icon(STATE_ICON[node.state])}</span>` +
    `<span class="mn">${nameHtml(m)}</span>${withArea && m.area ? `<span class="marea">${esc(m.area)}</span>` : ""}${storyFlag(m)}` +
    `${tracked ? `<span class="mtag">${esc(t("mdetail.tracked"))}</span>` : ""}</div>` + children;
}

// The log's views: "chain" (story missions in order, what each unlocks under it), "area", and "best"
// (what to do now, ranked: min-maxing XP / cash)
const GROUPINGS = ["chain", "area", "best"];
const BEST_TOP = 10;

/** The selected player (Who): rewards and XP shares are theirs. */
function selectedPlayer() {
  return S.players.find((p) => isTrackedPlayer(p)) || S.players.find((p) => p.local) || null;
}

/** "+1,128 XP · 34 %": the XP, then its share of the player's current level (a guide for now: it
 *  means less once they level up - the number stays). */
function xpText(xp, player) {
  const size = player && player.xp ? player.xp[1] : 0;
  return t("mdetail.xp", { n: xp }) + (size ? " · " + t("best.pct", { n: Math.round((xp / size) * 100) }) : "");
}

/** "Lv 3", coloured by the game's difficulty for the selected player (trivial: far below - only a category: no XP penalty);
 *  a mission not picked up yet has no level (set then). */
function levelBadge(m, player) {
  if (!m.ml) return "";
  const diff = missionDifficulty(m, player && player.lvl, S.log.thresholds);
  // picked up: its level (locked); else the level it would lock at if picked up now (dashed, "→")
  const text = m.mlk ? t("best.lv", { n: m.ml }) : t("best.lvWould", { n: m.ml });
  const tip = [diff ? t("mdiff." + diff) : "", t(m.mlk ? "mdetail.locked" : "mdetail.wouldLock", { n: m.ml })].filter(Boolean).join(" · ");
  return `<span class="mlv ${diff || ""}${m.mlk ? "" : " would"}" title="${esc(tip)}">${esc(text)}</span>`;
}

function bestHtml(query = "") {
  const player = selectedPlayer();
  const level = player ? player.lvl : 0;
  const goal = GOALS.includes(settings.ui.missionGoal) ? settings.ui.missionGoal : "xp";
  const ranked = rankMissions(S.log.missions, goal, level, S.log.thresholds), totalXp = ranked.totalXp;
  // a search narrows the ranking (its goal and order kept)
  const matching = query.trim() ? new Set(searchMissions(S.log.missions, query).map((n) => n.m.i)) : null;
  const rows = matching ? ranked.rows.filter((r) => matching.has(r.m.i)) : ranked.rows;
  let html = `<div class="mtools"><span class="seg">` + GOALS.map((g) =>
    `<button data-mgoal="${g}" class="${g === goal ? "on" : ""}" title="${esc(t("mgoal." + g + "Tip"))}">${esc(t("mgoal." + g))}</button>`).join("") +
    `</span></div>`;
  if (player) {
    const size = player.xp ? player.xp[1] : 0;
    html += `<div class="muted mbestsum">${esc(t("best.for", { name: player.n, n: level }))}` +
      (totalXp ? ` · ${esc(t("best.total", { xp: totalXp }))}` + (size ? ` ${esc(t("best.levels", { n: (totalXp / size).toFixed(1) }))}` : "") : "") + `</div>`;
  }
  if (!rows.length) return html + `<div class="muted">${esc(t(matching ? "mlog.noMatch" : "best.none"))}</div>`;
  html += `<div class="mbestlist">` + rows.slice(0, BEST_TOP).map((r, n) => { // the top 10 only
    const m = r.m, after = (r.after || []).map((d) => S.log.missions.find((x) => x.i === d)).filter(Boolean);
    const sub = [m.area, after.length ? t("best.after", { name: after.map((x) => x.n).join(", ") }) : "",
      goal === "effort" ? t("best.left", { n: r.effort }) : ""].filter(Boolean).join(" · "); // quick wins: why it ranks there
    const values = !r.known ? `<span class="muted">${esc(t("best.noReward"))}</span>`
      : [r.xp ? `<span class="mxp">${esc(xpText(r.xp, player))}</span>` : "", r.cash ? `<span class="mcash">$${esc(num(r.cash))}</span>` : ""].join("");
    return `<div class="mbest mrow ${r.state}${m.plot ? " story" : ""}" data-mission="${esc(m.i)}" title="${esc(stateText(r))}">` +
      `<span class="mrank">${n + 1}</span><span class="mico">${icon(STATE_ICON[r.state])}</span>` +
      `<span class="mbody"><span class="mn">${nameHtml(m)} ${levelBadge(m, player)}</span>${sub ? `<span class="msub">${esc(sub)}</span>` : ""}</span>` +
      `<span class="mval">${values}</span></div>`;
  }).join("") + `</div>`;
  if (ranked.tooHigh) html += `<div class="muted mhidden">${esc(t("best.tooHigh", { n: ranked.tooHigh, lv: ranked.minTooHigh }))}</div>`;
  return html;
}

function treeHtml() {
  const missions = S.log.missions, showLocked = !!settings.ui.showLockedMissions;
  const grouping = GROUPINGS.includes(settings.ui.missionGroup) ? settings.ui.missionGroup : "chain";
  const c = missionCounts(missions);
  return `<input type="search" id="mSearch" class="msearch" placeholder="${esc(t("mlog.search"))}" value="${esc(S.missionView.query || "")}">` +
    `<div class="mtools"><span class="seg">` + GROUPINGS.map((g) =>
    `<button data-mgroup="${g}" class="${g === grouping ? "on" : ""}">${esc(t("mlog.by." + g))}</button>`).join("") + `</span>` +
    (grouping === "best" ? "" : `<label class="row mlocked"><input type="checkbox" id="mShowLocked"${showLocked ? " checked" : ""}>` +
    `<span>${esc(t("mlog.showLocked", { n: c.locked }))}</span></label>`) + `</div>` +
    `<div id="mList">${listHtml()}</div>`;
}

/** Under the tools: the current view - a search narrows it (the view's filters kept): the ranking
 *  filtered (Best now), or the matches as a flat list with their area (the tree / areas; locked ones
 *  only with "Show locked"). */
function listHtml() {
  const missions = S.log.missions, showLocked = !!settings.ui.showLockedMissions;
  const query = S.missionView.query || "";
  const grouping = GROUPINGS.includes(settings.ui.missionGroup) ? settings.ui.missionGroup : "chain";
  if (grouping === "best") return bestHtml(query);
  if (query.trim()) {
    const found = searchMissions(missions, query).filter((n) => showLocked || n.state !== "locked");
    return found.length ? `<div class="mtree">${found.map((n) => rowHtml(n, 0, true, true)).join("")}</div>`
      : `<div class="muted">${esc(t("mlog.noMatch"))}</div>`;
  }
  let html = "";
  const sections = grouping === "area"
    ? missionAreas(missions).map((a) => [a.area || t("mlog.noArea"), a.nodes])
    : (() => { const tree = missionTree(missions); return [[t("mlog.story"), tree.story], [t("mlog.other"), tree.other]]; })();
  for (const [title, list] of sections) {
    const rows = list.map((n) => rowHtml(n, 0, showLocked)).join("");
    if (rows) html += `<div class="group">${esc(title)}</div><div class="mtree">${rows}</div>`;
  }
  return html;
}

/** The reward, as the game computes it for this player (XP, currency, items); an alternative one
 *  (some missions let you choose) after an "or". */
function rewardHtml(rw, player) {
  const side = (r) => {
    const rows = [];
    if (r.xp) rows.push(esc(xpText(r.xp, player)));
    if (r.cash) rows.push(esc(r.cur === "Credits" || !r.cur ? "$" + num(r.cash) : `${num(r.cash)} ${cleanGameText(r.cur)}`));
    const items = [...(r.items || []), ...(r.pools || [])].map(nameHtml);
    return [...rows.map((x) => `<div class="mrw">${x}</div>`), ...items.map((x) => `<div class="mrw mrwitem">${x}</div>`)].join("");
  };
  let html = `<div class="group">${esc(t("mdetail.rewards"))}</div>` + side(rw);
  if (rw.alt) html += `<div class="mrw or">${esc(t("mdetail.altReward"))}</div>` + side(rw.alt);
  return html;
}

function detailHtml(m, tree) {
  const rows = [];
  if (m.area) rows.push([t("mdetail.area"), m.area]);
  if (m.giver) rows.push([t("mdetail.giver"), m.giver]);
  if (m.turnin) rows.push([t("mdetail.turnin"), m.turnin]);
  const player = selectedPlayer();
  if (m.ml) {
    const diff = missionDifficulty(m, player && player.lvl, S.log.thresholds), gap = player ? m.ml - player.lvl : 0;
    rows.push([t("mdetail.level"), num(m.ml) + (diff ? ` · ${t("mdiff." + diff)}` : "") +
      (player && gap ? ` · ${t(gap < 0 ? "mdetail.below" : "mdetail.above", { n: Math.abs(gap) })}` : "") +
      ` · ${t(m.mlk ? "mdetail.lockedShort" : "mdetail.wouldLockShort")}`]);
  }
  const flags = [m.repeat && t("mdetail.repeatable"), m.fail && t("mdetail.canFail")].filter(Boolean);
  if (flags.length) rows.push([t("mdetail.flags"), flags.join(" · ")]);
  let html = "";
  const desc = gameTextHtml(m.desc); // descriptions can hold line breaks (<br>)
  if (desc) html += `<div class="mdesc">${desc}</div>`;
  if (rows.length) html += `<div class="kv">` + rows.map(([k, v]) => `<span>${esc(k)}</span><span>${esc(v)}</span>`).join("") + `</div>`;
  // Objectives: the ones done and the current step (later steps / other branches aren't shown)
  const objectives = objectiveStates(m).filter((s) => s.state !== "pending");
  if (objectives.length) {
    html += `<div class="group">${esc(t("mdetail.objectives"))}</div>` + objectives.map((s) =>
      `<div class="mobj ${s.state}"><span class="mico">${icon(s.state === "done" ? "check" : "circle")}</span>` +
      `<span class="mn">${nameHtml(s.o)}${s.o.opt ? ` <span class="mopt">${esc(t("mdetail.optional"))}</span>` : ""}</span>` +
      (s.o.c > 1 ? `<span class="mcount">${num(Math.min(s.p, s.o.c))}/${num(s.o.c)}</span>` : "") + `</div>`).join("");
  }
  const reward = player ? rewardFor(m, player.lvl) : null;
  if (reward) html += rewardHtml(reward, player);
  else if (m.rw) html += `<div class="group">${esc(t("mdetail.rewards"))}</div><div class="muted">${esc(t("best.noReward"))}</div>`;
  // Requires / unlocks: neutral rows (the story flag and colours are for the mission shown, not the
  // ones it links to), with the linked mission's state
  const link = (id) => {
    const other = tree.byId.get(id);
    if (!other) return "";
    const state = missionState(other, tree.byId);
    return `<div class="mrow link ${state}" data-mission="${esc(id)}" title="${esc(stateText({ m: other, state }))}">` +
      `<span class="mico">${icon(STATE_ICON[state])}</span><span class="mn">${nameHtml(other)}</span></div>`;
  };
  const needs = (m.deps || []).map(link).join("");
  if (needs) html += `<div class="group">${esc(t("mdetail.requires"))}</div>${needs}`;
  const unlocks = S.log.missions.filter((o) => (o.deps || []).includes(m.i)).sort((a, b) => a.num - b.num).map((o) => link(o.i)).join("");
  if (unlocks) html += `<div class="group">${esc(t("mdetail.unlocks"))}</div>${unlocks}`;
  return html;
}

export function renderMissionLog(resetScroll) {
  const body = $("ibody"), scroll = body.scrollTop;
  // the search box is rebuilt with the rest: keep its focus / caret across a refresh from the game
  const search = document.activeElement && document.activeElement.id === "mSearch" ? document.activeElement : null;
  const caret = search ? [search.selectionStart, search.selectionEnd] : null;
  $("itabs").style.display = "none";
  if (!S.log || !S.log.missions.length) {
    $("iwho").textContent = t("mlog.title");
    $("isub").textContent = "";
    body.innerHTML = `<div class="note">${esc(t("mlog.none"))}</div>`;
    return;
  }
  const tree = missionTree(S.log.missions);
  const m = S.missionView.id ? tree.byId.get(S.missionView.id) : null;
  if (m) {
    const state = stateText({ m, state: missionState(m, tree.byId) });
    $("iwho").innerHTML = `<button class="mback" id="mBack" title="${esc(t("mlog.back"))}">${icon("back")}</button>` +
      `<span class="mtitle ${m.plot ? "story" : "side"}">${nameHtml(m)}</span>${storyFlag(m)}`;
    $("isub").textContent = [state, t(m.plot ? "mdetail.story" : "mdetail.side"), S.log.tracked === m.i ? t("mdetail.tracked") : ""]
      .filter(Boolean).join(" · ");
    body.innerHTML = detailHtml(m, tree);
  } else {
    const c = missionCounts(S.log.missions);
    $("iwho").textContent = t("mlog.title");
    $("isub").textContent = t("mlog.summary", { done: c.done, active: c.active, available: c.available, unknown: c.unknown });
    body.innerHTML = treeHtml();
    if (caret) { const input = $("mSearch"); input.focus(); input.setSelectionRange(...caret); }
  }
  body.scrollTop = resetScroll ? 0 : scroll;
}

/** To a mission (from the tree or a requires / unlocks link): where we were goes on the history. */
function goTo(id) {
  const view = S.missionView;
  view.history.push({ id: view.id, scroll: $("ibody").scrollTop });
  view.id = id;
  renderMissionLog(true);
}

/** Back one step: the previous mission (its scroll kept), and at the bottom of the history the tree. */
function goBack() {
  const view = S.missionView, prev = view.history.pop() || { id: null, scroll: 0 };
  view.id = prev.id;
  renderMissionLog(true);
  $("ibody").scrollTop = prev.scroll;
}

export function initMissionLog() {
  // One set of delegated handlers on the drawer (its content is rebuilt on every change)
  $("inspector").addEventListener("click", (e) => {
    if (!S.missionView) return;
    if (e.target.closest("#mBack")) { goBack(); return; }
    const goal = e.target.closest("[data-mgoal]");
    if (goal) { settings.ui.missionGoal = goal.dataset.mgoal; saveSettings(); $("mList").innerHTML = listHtml(); return; }
    const grouping = e.target.closest("[data-mgroup]");
    if (grouping) { settings.ui.missionGroup = grouping.dataset.mgroup; saveSettings(); renderMissionLog(true); return; }
    const row = e.target.closest("[data-mission]");
    if (row) goTo(row.dataset.mission);
  });
  // Typing a search: only the list under the box is redrawn (the box keeps its focus)
  $("inspector").addEventListener("input", (e) => {
    if (e.target.id !== "mSearch" || !S.missionView) return;
    S.missionView.query = e.target.value;
    $("mList").innerHTML = listHtml();
  });
  $("inspector").addEventListener("change", (e) => {
    if (e.target.id !== "mShowLocked") return;
    settings.ui.showLockedMissions = e.target.checked;
    saveSettings();
    renderMissionLog();
  });
}
