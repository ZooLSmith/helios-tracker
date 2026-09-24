// Panel "Players" list: name, level · class, shield / health / XP bars; a click opens the inspector.
import { esc, nameHtml } from "../dom.js";
import { num, numShort, t } from "../i18n.js";
import { prettyRaw } from "../model.js";
import { S, findPlayer, isTrackedPlayer, pawnPos } from "../state.js";
import { openInspector } from "./inspector.js";
import { renderTargets } from "./panel.js";

export function playerSub(p) {
  let cls = p.cls ? (p.clsRaw ? prettyRaw(p.cls) : p.cls) : "";
  if (p.char && p.char !== p.n) cls = cls ? `${cls} (${p.char})` : p.char; // "Gunzerker (Salvador)"
  // The level is in the XP bar (an empty one when the XP isn't known: co-op client, another player)
  return cls;
}

export function renderPlayers() {
  const box = document.getElementById("players");
  if (!S.players.length) { box.innerHTML = '<div class="muted">—</div>'; return; }
  const sel = findPlayer();
  const vital = (cls) => `<div class="vital ${cls}"><span class="vbar"><i></i><span class="vnum"><b></b><span class="vmax"></span></span>` +
    `<span class="vnum vright"></span></span></div>`;
  box.innerHTML = S.players.map((p) =>
    `<div class="pentry${sel && sel.i === p.i ? " sel" : ""}" data-id="${esc(p.i)}">` +
    `<div class="phead"><div class="pname${isTrackedPlayer(p) ? " me" : ""}">${nameHtml(p)}</div>` +
    `<span class="askill"><i></i><span></span></span></div>` +
    `<div class="pinfo">${esc(playerSub(p))}</div>` +
    // shield, health and XP (the level) together, under the state overlay (crippled / dead /
    // respawning / in a menu: the word over all of them); driving: shield + health on one row, the
    // vehicle's health under them
    `<div class="vitals"><div class="shhp">${vital("sh")}${vital("hp")}</div><div class="vhbo">${vital("vh")}${vital("bo")}</div>${vital("xp")}` +
    `<div class="ffyl">${esc(t("vital.ffyl"))}</div></div>` +
    `</div>`).join("");
  for (const row of box.querySelectorAll(".pentry")) row.onclick = () => openInspector(row.dataset.id);
  for (const p of S.players) { // XP: from the players payload (it changes with kills, not per frame)
    const el = box.querySelector(`.pentry[data-id="${CSS.escape(p.i)}"] .vital.xp`);
    if (!el || (!p.xp && !p.lvl)) continue;
    // no XP known (a co-op client doesn't get the others'): an empty bar, the level on the right
    const [cur, size] = p.xp || [0, 0];
    el.classList.add("on");
    el.title = p.xp ? "" : t("pinfo.unknown");
    el.querySelector("i").style.width = (!p.xp ? 0 : size ? Math.max(0, Math.min(1, cur / size)) * 100 : 100).toFixed(1) + "%";
    // XP on the left (like the other bars' numbers), the level on the right
    el.querySelector(".vnum b").textContent = size ? num(cur) : "";
    el.querySelector(".vnum .vmax").textContent = size ? ` / ${num(size)}` : "";
    el.querySelector(".vright").textContent = t("insp.level", { n: p.lvl });
  }
  updatePlayerVitals();
  alignPatterns(box); // (the rebuilt bars: their patterns carry on)
  renderTargets();
}

// The bars' patterns (shield hexagons, health columns, vehicle stripes: base.css) slide left: CSS
// animations (panel.css / drawer.css), one tile per cycle. Their timing follows the Refresh rate: smooth
// = linear, a cap (or the game's updates) = steps(), as many jumps per cycle as frames at that rate -
// set once per setting change, nothing per frame.
// each: [its repeat width (px), its speed (px per second): health faster than shields]
// [tile px, px/s]: shield, health, vehicle; sc: the skill tiles' scanlines going up (the game's)
// rb: the effervescent rarity's colour cycling (drawer.css .item.rainbow: one cycle = 3 s, model.js RAINBOW_CYCLE)
const PATTERNS = { sh: [18, 8], hp: [12, 11], vh: [10, 8], sc: [5, 8], rb: [30, 10] }; // (the tiles: web/img/patterns/*.svg; sc: drawer.css)
/** The patterns' animations in `root` on the page's clock: a rebuilt bar (the list re-rendered on a
 *  click, the Info tab refreshed) would start its pattern over - with the same start time (the page's
 *  time zero) every bar's position depends on the time only, so a new one carries on where the old one
 *  was. Once per rebuild, not per frame. */
export function alignPatterns(root) {
  if (!root || !root.getAnimations) return;
  for (const a of root.getAnimations({ subtree: true })) if (/^pat-/.test(a.animationName || "")) a.startTime = 0;
}

export function patternTiming(motion, hz) {
  const fps = motion === "smooth" ? 0 : motion > 0 ? motion : hz || 10; // 0: every frame
  const root = document.documentElement.style;
  for (const [key, [tile, speed]] of Object.entries(PATTERNS)) {
    const period = tile / speed; // s per tile
    root.setProperty(`--pat-dur-${key}`, `${period.toFixed(3)}s`);
    root.setProperty(`--pat-timing-${key}`, fps ? `steps(${Math.max(1, Math.round(period * fps))})` : "linear");
  }
}

// Shield, then health, under each player: from the live state (their marker), not the slower
// players payload - only widths / numbers change, the list isn't rebuilt
export function updatePlayerVitals(now = performance.now()) {
  for (const row of document.querySelectorAll("#players .pentry")) {
    const pawn = S.pawns.get(row.dataset.id);
    const p = pawn && { ...pawn, ...pawnPos(pawn, now) };
    // short: the numbers compacted ("1.7M / 1.7M": half-width bars while driving), the full ones on hover
    const set = (cls, cur, max, short = false) => {
      const el = row.querySelector(".vital." + cls);
      const on = !!p && max > 0;
      if (el.classList.contains("on") !== on) {
        el.classList.toggle("on", on);
        if (on) alignPatterns(el); // shown now (e.g. the vehicle's bar): its pattern on the page's clock too
      }
      if (!on) return;
      const frac = Math.max(0, Math.min(1, cur / max));
      const bar = el.querySelector("i"), width = (frac * 100).toFixed(1) + "%";
      if (bar.style.width !== width) bar.style.width = width; // only on a change (called with the frames)
      const fmt = short ? numShort : num;
      const curText = fmt(Math.round(cur)), maxText = ` / ${fmt(Math.round(max))}`; // "/ max": smaller, at 70%
      const curEl = el.querySelector(".vnum b"), maxEl = el.querySelector(".vnum .vmax");
      if (curEl.textContent !== curText) curEl.textContent = curText;
      if (maxEl.textContent !== maxText) maxEl.textContent = maxText;
      const title = short ? `${num(Math.round(cur))} / ${num(Math.round(max))}` : "";
      if (el.title !== title) el.title = title;
    };
    // Driving: the vehicle's health (its own marker's), shield and health side by side above it
    const veh = p && p.dv ? S.pawns.get(p.dv) : null, vp = veh ? { ...veh, ...pawnPos(veh, now) } : null;
    const driving = !!(vp && vp.m > 0);
    set("sh", p && p.s, p && p.sm, driving);
    set("hp", p && p.h, p && p.m, driving);
    set("vh", vp && vp.h, vp && vp.m);
    // its boost (nitro): a quarter of the row, the action skill's look, no numbers (the % on hover)
    const bo = vp && vp.bo, boEl = row.querySelector(".vital.bo");
    const boOn = !!(bo && bo[1] > 0);
    if (boEl.classList.contains("on") !== boOn) { boEl.classList.toggle("on", boOn); if (boOn) alignPatterns(boEl); }
    if (boOn) {
      const pct = Math.max(0, Math.min(1, bo[0] / bo[1])), width = (pct * 100).toFixed(1) + "%", bar = boEl.querySelector("i");
      if (bar.style.width !== width) bar.style.width = width;
      const title = t("vital.boost", { n: Math.round(pct * 100) });
      if (boEl.title !== title) boEl.title = title;
      // refilling: the seconds until full (the collector's: delay + rate), bare like the action skill's cooldown
      const text = bo[2] != null ? String(Math.ceil(bo[2])) : "";
      const numEl = boEl.querySelector(".vnum b");
      if (numEl.textContent !== text) numEl.textContent = text;
    }
    const vitalsBox = row.querySelector(".vitals");
    if (vitalsBox.classList.contains("driving") !== driving) vitalsBox.classList.toggle("driving", driving);
    // The action skill: ready / running (a draining bar) / cooling down (seconds left)
    const chip = row.querySelector(".askill"), ak = p && p.ak && p.ak[0] !== "u" ? p.ak : null; // ("u": last use only - the Info tab)
    const kind = ak ? ak[0] : "";
    if (chip.dataset.k !== kind) { chip.dataset.k = kind; chip.className = "askill" + (kind ? " " + kind : ""); }
    if (ak) { // ["r", name] / ["a" | "c", fraction left, seconds left, name]
      // Running / cooling down: the seconds left, a bare number (the chip's look tells which)
      const text = kind === "r" ? t("skill.ready") : String(Math.ceil(ak[2]));
      const label = chip.querySelector("span"), width = kind === "r" ? "100%" : (ak[1] * 100).toFixed(1) + "%";
      if (label.textContent !== text) label.textContent = text;
      const name = (kind === "r" ? ak[1] : ak[3]) || t("skill.tip");
      const bar = chip.querySelector("i"), title = kind === "r" ? name : `${name} · ${t(kind === "a" ? "skill.active" : "skill.cooldown")}`;
      if (bar.style.width !== width) bar.style.width = width; // only on a change (called with the frames)
      if (chip.title !== title) chip.title = title;
    }
    // Respawning (at a New-U), dead (before the respawn), or crippled (down / no health, no shield left);
    // else in a menu (the same word over the bars, not red)
    const respawning = !!p && !!p.rs, dead = !!p && !!p.dd && !respawning;
    const down = respawning || dead || (!!p && (!!p.dn || (p.m > 0 && p.h <= 0 && !(p.sm > 0 && p.s > 0))));
    const menu = !down && !!p && (!!p.mn || !!p.ct); // (a cutscene: the same neutral look)
    const box = row.querySelector(".vitals");
    if (box.classList.contains("down") !== down) box.classList.toggle("down", down);
    if (box.classList.contains("dead") !== dead) box.classList.toggle("dead", dead);
    if (box.classList.contains("menu") !== menu) box.classList.toggle("menu", menu);
    const text = t(respawning ? "vital.respawning" : dead ? "vital.dead" : menu ? (p.ct ? "vital.cutscene" : "vital.menu") : "vital.ffyl"), label = box.querySelector(".ffyl");
    if (label.textContent !== text) label.textContent = text;
  }
}
