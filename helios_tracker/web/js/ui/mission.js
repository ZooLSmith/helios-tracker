// Panel "Mission" section: the tracked mission, its status and every objective of its current step
// (done / to do, counts) from the mission log; the mission's name opens its details, "All missions"
// the log. Before the log arrives: the objectives shown on the map (the quest markers).
import { $, esc, nameHtml } from "../dom.js";
import { num, t } from "../i18n.js";
import { icon } from "../icons.js";
import { cleanGameText } from "../model.js";
import { objectiveStates } from "../missions.js";
import { S } from "../state.js";
import { openMissionLog } from "./missionlog.js";

function objectiveHtml(s) {
  return `<div class="obj ${s.state}"><span class="oico">${icon(s.state === "done" ? "check" : "diamond")}</span>` +
    `<span class="on">${nameHtml(s.o)}${s.o.opt ? ` <span class="mopt">${esc(t("mdetail.optional"))}</span>` : ""}</span>` +
    (s.o.c > 1 ? `<span class="ocount">${num(Math.min(s.p, s.o.c))}/${num(s.o.c)}</span>` : "") + `</div>`;
}

export function initMission() {
  $("mission").addEventListener("click", (e) => { // the name: its details; "All missions": the tree
    const el = e.target.closest("[data-log]");
    if (el) openMissionLog(el.dataset.log === "1" ? null : el.dataset.log);
  });
}

export function renderMission() {
  const box = $("mission"), log = S.log;
  const m = log && log.tracked ? log.missions.find((x) => x.i === log.tracked) : null;
  const all = log && log.missions.length ? `<button class="act mall" data-log="1">${esc(t("mission.all"))}</button>` : "";
  if (m) {
    const cur = new Set(m.cur || []);
    const step = objectiveStates(m).filter((s) => cur.has(s.i));
    const summary = cleanGameText(m.summary);
    box.innerHTML = `<div class="mname${m.plot ? " story" : ""}" data-log="${esc(m.i)}" title="${esc(t("mission.details"))}">${nameHtml(m)}</div>` +
      (step.length ? step.map(objectiveHtml).join("") : summary ? `<div class="muted">${esc(summary)}</div>` : "") + all;
    return;
  }
  const mk = S.missions; // no log yet: the tracked mission's markers
  if (!mk.tracked) { box.innerHTML = `<div class="muted">${esc(t("mission.none"))}</div>` + all; return; }
  const objectives = [];
  for (const marker of mk.markers) {
    if (marker.tracked && marker.objective && !objectives.some((o) => o.n === marker.objective.n)) objectives.push(marker.objective);
  }
  box.innerHTML = `<div class="mname">${nameHtml(mk.tracked)}</div>` +
    objectives.map((o) => `<div class="obj current"><span class="oico">${icon("diamond")}</span><span class="on">${nameHtml(o)}</span></div>`).join("") + all;
}
