// Panel "Players" list: name, level · class, shield / health / XP bars; a click opens the inspector.
import { esc, nameHtml } from "../dom.js";
import { num, t } from "../i18n.js";
import { prettyRaw } from "../model.js";
import { S, findPlayer, isTrackedPlayer, pawnPos } from "../state.js";
import { openInspector } from "./inspector.js";
import { renderTargets } from "./panel.js";

export function playerSub(p) {
  let cls = p.cls ? (p.clsRaw ? prettyRaw(p.cls) : p.cls) : "";
  if (p.char && p.char !== p.n) cls = cls ? `${cls} (${p.char})` : p.char; // "Gunzerker (Salvador)"
  // The level is in the XP bar when there is one
  return [p.lvl && !p.xp ? t("insp.level", { n: p.lvl }) : "", cls].filter(Boolean).join(" · ");
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
    // shield + health together, under the "Fight For Your Life" overlay (shown when both are empty)
    `<div class="vitals">${vital("sh")}${vital("hp")}<div class="ffyl">${esc(t("vital.ffyl"))}</div></div>` +
    vital("xp") + `</div>`).join("");
  for (const row of box.querySelectorAll(".pentry")) row.onclick = () => openInspector(row.dataset.id);
  for (const p of S.players) { // XP: from the players payload (it changes with kills, not per frame)
    const el = box.querySelector(`.pentry[data-id="${CSS.escape(p.i)}"] .vital.xp`);
    if (!el || !p.xp) continue;
    const [cur, size] = p.xp;
    el.classList.add("on");
    el.querySelector("i").style.width = (size ? Math.max(0, Math.min(1, cur / size)) * 100 : 100).toFixed(1) + "%";
    // XP on the left (like the other bars' numbers), the level on the right
    el.querySelector(".vnum b").textContent = size ? num(cur) : "";
    el.querySelector(".vnum .vmax").textContent = size ? ` / ${num(size)}` : "";
    el.querySelector(".vright").textContent = t("insp.level", { n: p.lvl });
  }
  updatePlayerVitals();
  renderTargets();
}

// Shield, then health, under each player: from the live state (their marker), not the slower
// players payload - only widths / numbers change, the list isn't rebuilt
export function updatePlayerVitals(now = performance.now()) {
  for (const row of document.querySelectorAll("#players .pentry")) {
    const pawn = S.pawns.get(row.dataset.id);
    const p = pawn && { ...pawn, ...pawnPos(pawn, now) };
    const set = (cls, cur, max) => {
      const el = row.querySelector(".vital." + cls);
      const on = !!p && max > 0;
      if (el.classList.contains("on") !== on) el.classList.toggle("on", on);
      if (!on) return;
      const frac = Math.max(0, Math.min(1, cur / max));
      const bar = el.querySelector("i"), width = (frac * 100).toFixed(1) + "%";
      if (bar.style.width !== width) bar.style.width = width; // only on a change (called with the frames)
      const curText = num(Math.round(cur)), maxText = ` / ${num(Math.round(max))}`; // "/ max" at 70%
      const curEl = el.querySelector(".vnum b"), maxEl = el.querySelector(".vnum .vmax");
      if (curEl.textContent !== curText) curEl.textContent = curText;
      if (maxEl.textContent !== maxText) maxEl.textContent = maxText;
    };
    set("sh", p && p.s, p && p.sm);
    set("hp", p && p.h, p && p.m);
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
    // Respawning (at a New-U), dead (before the respawn), or crippled (down / no health, no shield left)
    const respawning = !!p && !!p.rs, dead = !!p && !!p.dd && !respawning;
    const down = respawning || dead || (!!p && (!!p.dn || (p.m > 0 && p.h <= 0 && !(p.sm > 0 && p.s > 0))));
    const box = row.querySelector(".vitals");
    if (box.classList.contains("down") !== down) box.classList.toggle("down", down);
    if (box.classList.contains("dead") !== dead) box.classList.toggle("dead", dead);
    const text = t(respawning ? "vital.respawning" : dead ? "vital.dead" : "vital.ffyl"), label = box.querySelector(".ffyl");
    if (label.textContent !== text) label.textContent = text;
  }
}
