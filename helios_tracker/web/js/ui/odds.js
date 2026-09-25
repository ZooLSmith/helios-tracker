// A container's loot odds in its panel's "Can contain" (lootodds.py: the object's `odds`, the pools in S.lootPools):
// each loot configuration it may pick, its chance, its pools - a pool opens on its own entries and their chances, a
// sub-pool opens further. Worked out from the game's loot data by rules inferred from it (not checked against the
// game's own rolls): every chance marked "~". A weight depending on the player ("if low on health / ammo"): its
// chance then, beside. A chance the data doesn't give: "?".
import { esc, nameHtml } from "../dom.js";
import { numUpTo, t } from "../i18n.js";
import { S } from "../state.js";

const MAX_DEPTH = 5; // sub-pools opened in place

const figure = (p) => numUpTo(p, p < 0.1 ? 3 : p < 1 ? 2 : 1); // (small chances: their digits kept)

function pct(p) {
  return p == null ? "?" : "~" + t("unit.percent", { n: figure(p) });
}

/** "~6-12 % if low on health" (a weight the player's state changes), or "". */
function lowHtml(row) {
  if (!row.lo) return "";
  const [a, b] = row.lo;
  const range = Math.abs(a - b) < 0.05 ? pct(a) : "~" + t("unit.percent", { n: `${figure(Math.min(a, b))}–${figure(Math.max(a, b))}` });
  return ` <span class="odlow">${esc(t("odds.ifLow", { p: range, what: t("odds.low." + (row.c || "ammo")) }))}</span>`;
}

const poolName = (key) => {
  const pool = S.lootPools && S.lootPools[key];
  return nameHtml({ n: String(pool ? pool.n : key.split(".").pop()).replace(/^Pool_/, ""), raw: 1 });
};

/** A pool, openable: its entries (items, sub-pools) with their chances. */
function poolHtml(key, depth, count = 1) {
  const pool = S.lootPools && S.lootPools[key];
  const head = `${count > 1 ? `<span class="odn">${esc(t("odds.times", { n: count }))}</span>` : ""}${poolName(key)}`;
  if (!pool || !pool.e || !pool.e.length || depth > MAX_DEPTH) return `<div class="odpool">${head}</div>`;
  const rows = [...pool.e].sort((a, b) => (b.p ?? -1) - (a.p ?? -1)).map((e) =>
    `<div class="odrow"><span class="odp">${esc(pct(e.p))}</span><span class="odwhat">` +
    (e.pool ? poolHtml(e.pool, depth + 1) : nameHtml({ n: e.n, raw: 1 })) +
    (e.min ? ` <span class="odmin">${esc(t("odds.fromLevel", { n: e.min }))}</span>` : "") + lowHtml(e) + `</span></div>`).join("");
  return `<details class="odpool"><summary>${head}</summary><div class="odrows">${rows}</div></details>`;
}

/** The object's configurations, the likeliest first: "~36 %  2 × Epic Chest Golden Weapons Long Guns ?". */
export function oddsHtml(it) {
  const configs = [...(it.odds || [])].sort((a, b) => (b.p ?? -1) - (a.p ?? -1));
  if (!configs.length) return "";
  return `<div class="odds" title="${esc(t("odds.tip"))}">` + configs.map((cfg) =>
    `<div class="odrow"><span class="odp">${esc(pct(cfg.p))}</span><span class="odwhat">` +
    (cfg.a.length ? cfg.a.map(([key, n]) => poolHtml(key, 1, n)).join("") : `<span class="muted">${esc(t("odds.nothing"))}</span>`) +
    lowHtml(cfg) + `</span></div>`).join("") + `</div>`;
}
