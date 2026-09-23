// The connection status (panel) and the message in the middle of the map. Kept as keys so a
// language change can re-translate them.
import { $ } from "../dom.js";
import { t } from "../i18n.js";

let status = ["", "status.connecting"], message = ["msg.connecting"];

export function setStatus(kind, key) {
  status = [kind, key];
  $("status").className = kind;
  $("status").querySelector("span").textContent = t(key);
}

export function setMessage(key, vars) {
  message = [key, vars];
  $("msg").textContent = key ? t(key, vars) : "";
}

export function isLive() { return status[0] === "live"; }

export function refreshStatus() { setStatus(...status); setMessage(...message); }
