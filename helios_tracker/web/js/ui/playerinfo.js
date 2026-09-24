// The player drawer's Info tab: their state (fine / in a menu / crippled / dead / respawning), health and shield,
// action skill (ready / running / cooldown), timed skill effects and melee skill cooldown - live from
// their pawn in the state payload (refreshed a few times a second while the tab is open).
import { esc } from "../dom.js";
import { num, t } from "../i18n.js";
import { nameText } from "../model.js";
import { settings } from "../settings.js";
import { S, pawnPos } from "../state.js";
import { tipAttrs } from "./hovertip.js";

/** A player's "Who" value (Settings): the mod's own player "me", the others by name (ids change per level). */
export const whoValue = (p) => (p.local ? "me" : p.n);

/** A labelled bar: text on the left, value on the right, the fill = fraction (0..1). */
function barRow(label, value, fraction, cls) {
  return `<div class="ibar ${cls}"><i style="width:${(Math.max(0, Math.min(1, fraction)) * 100).toFixed(1)}%"></i>` +
    `<span class="ibl">${esc(label)}</span><span class="ibv">${esc(value)}</span></div>`;
}

const seconds = (s) => t("unit.seconds", { n: Math.ceil(s) });

function stateKey(pawn) {
  if (pawn.rs) return "respawning";
  if (pawn.dd) return "dead";
  if (pawn.dn || (pawn.m > 0 && pawn.h <= 0 && !(pawn.sm > 0 && pawn.s > 0))) return "ffyl";
  if (pawn.ct) return "cutscene";
  if (pawn.mn) return "menu";
  return "fine";
}

export function playerInfoHtml(p) {
  const pawn = S.pawns.get(p.i);
  if (!pawn) return `<div class="note">${esc(t("pinfo.away"))}</div>`;
  const live = { ...pawn, ...pawnPos(pawn, performance.now()) };
  const state = stateKey(live);
  // their state, and on its right a shortcut: make them "Who" (the tracked player: the map measures from them);
  // once they are, Follow (the map centred on them, like F) - "Following" while it does, a click stops it (the
  // clicks: inspector.js, delegated)
  const tracked = settings.view.target === whoValue(p);
  const following = tracked && settings.view.follow;
  const track = !tracked
    ? `<button class="ptrack" data-track="${esc(whoValue(p))}"${tipAttrs("", t("pinfo.trackTip"))}>${esc(t("pinfo.track"))}</button>`
    : `<button class="ptrack${following ? " on" : ""}" data-follow${tipAttrs("", t(following ? "pinfo.followingTip" : "pinfo.followTip"))}>` +
      `${esc(t(following ? "pinfo.following" : "pinfo.follow"))}</button>`;
  let html = `<div class="pstaterow"><div class="kv"><span>${esc(t("pinfo.state"))}</span>` +
    `<span class="pstate ${state}">${esc(t(state === "fine" ? "pinfo.fine" : "vital." + state))}</span></div>${track}</div>`;
  html += `<div class="group">${esc(t("pinfo.vitals"))}</div>`;
  if (live.sm > 0) html += barRow(t("detail.shield"), `${num(Math.round(live.s))} / ${num(Math.round(live.sm))}`, live.s / live.sm, "sh");
  if (live.m > 0) html += barRow(t("detail.health"), `${num(Math.round(live.h))} / ${num(Math.round(live.m))}`, live.h / live.m, "hp");
  const veh = pawn.dv ? S.pawns.get(pawn.dv) : null; // driving: the vehicle's health
  if (veh && veh.m > 0) {
    const v = { ...veh, ...pawnPos(veh, performance.now()) };
    html += barRow(nameText(veh), `${num(Math.round(v.h))} / ${num(Math.round(v.m))}`, v.h / v.m, "vh");
    if (veh.bo && veh.bo[1] > 0) { // its boost (nitro), the action skill's look
      const pct = Math.max(0, Math.min(1, veh.bo[0] / veh.bo[1]));
      // refilling: its seconds (the bar shows how full it is)
      html += barRow(t("pinfo.boost"), veh.bo[2] != null ? seconds(veh.bo[2]) : "", pct, "bo");
    }
  }
  // Experience: from the players payload (it changes with kills, not per update)
  if (p.xp) {
    const [cur, size] = p.xp;
    html += barRow(t("insp.level", { n: p.lvl }), size ? `${num(cur)} / ${num(size)}` : num(cur), size ? cur / size : 1, "xp");
  } else if (p.lvl) { // the XP isn't known (a co-op client, another player): the level, an empty bar
    html += barRow(t("insp.level", { n: p.lvl }), "", 0, "xp");
  }
  // The action skill
  const ak = pawn.ak;
  html += `<div class="group">${esc(t("pinfo.action"))}</div>`;
  if (!ak) html += `<div class="muted">${esc(t(p.local || S.meId === p.i ? "pinfo.noAction" : "pinfo.unknown"))}</div>`;
  else if (ak[0] === "u") { // another player, on a co-op client: only when they last used it
    html += `<div class="muted">${esc(t("pinfo.lastUsed", { n: num(ak[1]) }))}</div>` +
      `<div class="muted">${esc(t("pinfo.unknown"))}</div>`;
  } else {
    const name = ak[0] === "r" ? ak[1] : ak[3];
    const label = name || t("skill.tip");
    if (ak[0] === "r") html += barRow(label, t("skill.ready"), 1, "ready");
    else if (ak[0] === "a") html += barRow(label, `${t("skill.active")} · ${seconds(ak[2])}`, ak[1], "active");
    else html += barRow(label, seconds(ak[2]), ak[1], "cooldown");
  }
  if (pawn.mk) html += barRow(t("pinfo.melee"), seconds(pawn.mk[1]), pawn.mk[0], "cooldown");
  // Timed skill effects (a passive's triggered buff...)
  if (pawn.ps && pawn.ps.length) {
    html += `<div class="group">${esc(t("pinfo.effects"))}</div>` +
      pawn.ps.map(([name, left, duration]) => barRow(name || "?", seconds(left), duration > 0 ? left / duration : 0, "effect")).join("");
  }
  return html;
}
