// The drawer's lists (the mission log, the damage log): the header's chevron (#ifold, next to the close button), a
// cycle (the user: "plain => filters => collapsed"), one setting per list (settings.ui.missionFold, damageFold):
// - plain: the list, its filters (.mfilters) folded away;
// - filters: the list and its filters;
// - collapsed: the relevant only (the user) - the list alone, the header's line under the title (a count) hidden, the
//   drawer half the page at most (drawer.css #inspector.listcollapsed).
// Folded, an active search stays in sight under the title (its box is folded away: .mquery). A phone ignores the fold
// (drawer.css: its filters always shown).
import { $, esc } from "../dom.js";
import { icon } from "../icons.js";
import { t } from "../i18n.js";
import { saveSettings, settings } from "../settings.js";
import { S } from "../state.js";
import { renderInspector } from "./inspector.js";

const FOLDS = ["plain", "filters", "collapsed"];
// the icon and the tooltip: what a click does next (icons.js fold* - the step now read inverted: the user)
const STEP = { plain: ["foldFilters", "fold.filters"], filters: ["foldCollapse", "fold.collapse"],
  collapsed: ["foldExpand", "fold.expand"] };

/** A list's fold ("missionFold", "damageFold"): one of FOLDS. */
export const foldOf = (key) => (FOLDS.includes(settings.ui[key]) ? settings.ui[key] : "filters");

/** The chevron shown for the list in the drawer, as its fold is; its filters (.mfilters) shown or not. */
export function showFold(key, filters) {
  const mode = foldOf(key), fold = $("ifold");
  fold.hidden = false;
  // (a class on the drawer, not a :has() in the CSS: the lists' DOM changes all the time - the damage log's every frame)
  $("inspector").classList.toggle("listcollapsed", mode === "collapsed");
  // (and the filters drawn inside the list, folded away with the rest: the Recap's tabs - drawer.css .listfolded)
  $("inspector").classList.toggle("listfolded", mode !== "filters");
  fold.innerHTML = icon(STEP[mode][0]);
  fold.title = t(STEP[mode][1]);
  if (filters) filters.classList.toggle("closed", mode !== "filters");
  return mode;
}

/** No list in the drawer: no chevron, the drawer at its full height. */
export function hideFold() {
  $("ifold").hidden = true;
  $("inspector").classList.remove("listcollapsed", "listfolded");
}

/** The search in sight under the title while the filters are folded away ("" without one). */
export const queryHtml = (key, query) => (foldOf(key) !== "filters" && query.trim()
  ? `<span class="mquery">${esc(t("mlog.searching", { q: query.trim() }))}</span>` : "");

// Collapsed, the drawer's height follows its list's (cards coming and going in Realtime, rows in the mission log)
// gradually (the user), from the frames - the Refresh rate's (smooth: eased, N fps: stepped, updates only: at once),
// never a timer or a CSS transition of its own. Its height as the CSS lays it out (auto, half the page at most: the
// cap there) measured every MEASURE_MS only (a forced layout), each frame writing a height only while it moves.
const EASE_MS = 160, MEASURE_MS = 250;
let phone = null, shownHeight = null, wantHeight = 0, measuredAt = -Infinity, easedAt = 0;

/** From draw.js' frame: the collapsed drawer's height towards its list's. */
export function refreshDrawerHeight(now) {
  const box = $("inspector");
  phone ??= matchMedia("(max-width: 520px)"); // (drawer.css: the page whole there, the fold ignored - first used here:
  // the module also loads where there's none, offline_check's Node)
  // (a selected thing's fitted panel - #inspector.fit - not: the CSS's fit only, the user didn't want it animated)
  if (!box.classList.contains("open") || !box.classList.contains("listcollapsed") || phone.matches) {
    if (shownHeight !== null) { box.style.height = ""; shownHeight = null; } // (the CSS's again: full, unfolded)
    return;
  }
  if (shownHeight === null) { shownHeight = box.offsetHeight; easedAt = now; measuredAt = -Infinity; }
  if (now - measuredAt >= MEASURE_MS) {
    measuredAt = now;
    box.style.height = ""; // (laid out as the CSS has it, read, put back - one task: never painted)
    wantHeight = box.offsetHeight;
    box.style.height = `${shownHeight.toFixed(1)}px`;
  }
  const dt = Math.min(200, now - easedAt);
  easedAt = now;
  if (shownHeight === wantHeight) return;
  const k = settings.view.motion ? 1 - Math.exp(-dt / EASE_MS) : 1;
  shownHeight += (wantHeight - shownHeight) * k;
  if (Math.abs(wantHeight - shownHeight) < 0.5) shownHeight = wantHeight;
  box.style.height = `${shownHeight.toFixed(1)}px`;
}

export function initListFold() {
  $("ifold").addEventListener("click", () => {
    const key = S.missionView ? "missionFold" : S.damageView ? "damageFold" : null;
    if (!key) return;
    settings.ui[key] = FOLDS[(FOLDS.indexOf(foldOf(key)) + 1) % FOLDS.length];
    saveSettings();
    renderInspector(); // (the list keeps its scroll)
  });
}
