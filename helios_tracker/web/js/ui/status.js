// The connection status (panel) and the message in the middle of the map. Kept as keys so a
// language change can re-translate them.
import { $ } from "../dom.js";
import { t } from "../i18n.js";

let status = ["", "status.connecting"], message = ["msg.connecting"], paused = false;

/** The box: the connection's state - once live, hidden unless the game is paused (then "Game paused"). */
function renderStatus() {
  const [kind, key] = status, pause = kind === "live" && paused;
  $("status").className = pause ? "paused" : kind;
  $("status").querySelector("span").textContent = t(pause ? "status.paused" : key);
}

export function setStatus(kind, key) {
  status = [kind, key];
  renderStatus();
}

/** The game paused or not (each state from the game says). */
export function setPaused(on) {
  if (paused === !!on) return;
  paused = !!on;
  renderStatus();
}

export function setMessage(key, vars) {
  message = [key, vars];
  $("msg").textContent = key ? t(key, vars) : "";
}

export function isLive() { return status[0] === "live"; }

export function refreshStatus() { setStatus(...status); setMessage(...message); }
