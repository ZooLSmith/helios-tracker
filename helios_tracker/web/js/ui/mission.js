// Panel "Mission" section: the tracked mission and its shown objectives.
import { $, esc, nameHtml } from "../dom.js";
import { t } from "../i18n.js";
import { S } from "../state.js";

export function renderMission() {
  const box = $("mission"), m = S.missions;
  if (!m.tracked) { box.innerHTML = `<div class="muted">${esc(t("mission.none"))}</div>`; return; }
  const objectives = [];
  for (const mk of m.markers) {
    if (mk.tracked && mk.objective && !objectives.some((o) => o.n === mk.objective.n)) objectives.push(mk.objective);
  }
  box.innerHTML = `<div class="mname">${nameHtml(m.tracked)}</div>` +
    objectives.map((o) => `<div class="obj">${nameHtml(o)}</div>`).join("");
}
