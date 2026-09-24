// The Info tab's Cutscene block, above the mission: a video playing on the game's PC (data.js onCutscene)
// shown like a video player's bar - elapsed / total, from its start and its length (the collector
// reads it from the video file). The game renders nothing meanwhile, so it's counted here.
import { $ } from "../dom.js";
import { t } from "../i18n.js";
import { icon } from "../icons.js";
import { S } from "../state.js";

const clock = (s) => {
  const n = Math.max(0, Math.floor(s));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
};

export function renderCutscene() {
  const box = $("cutscene");
  if (!box) return;
  const v = S.video;
  if (box.hidden !== !v) box.hidden = !v;
  if (!v) return;
  if (!box.firstChild) {
    // a video player: the Players list's bar (its played part, its name inside: the video's file / the
    // Matinee's), under it elapsed (with the play icon) / total
    box.innerHTML = `<h3></h3><div class="cplayer"><div class="vital on cs"><span class="vbar"><i></i>` +
      `<span class="vnum"><b class="cname"></b></span></span></div>` +
      `<div class="ctimes"><span class="cnow"><span class="cplay">${icon("play")}</span><span class="cel"></span></span>` +
      `<span class="clen"></span></div></div>`;
  }
  const nameEl = box.querySelector(".cname");
  if (nameEl.textContent !== v.name) { nameEl.textContent = v.name; nameEl.title = v.name; }
  const head = box.querySelector("h3"), title = t("h.cutscene");
  if (head.textContent !== title) head.textContent = title; // (the language can change meanwhile)
  const elapsed = v.paused ? v.pos : Math.max(0, Date.now() / 1000 - v.at), len = v.len; // (paused: where it stopped)
  const track = box.querySelector(".vbar");
  // The bar moves by itself (a CSS animation over the video's length), set once per video - from where it
  // is now (a page opened meanwhile: a negative delay). No length known: a full, faint bar.
  const key = `${v.at}:${len}:${v.paused}`;
  if (track.dataset.video !== key) {
    track.dataset.video = key;
    track.classList.toggle("unknown", !len);
    track.style.setProperty("--len", len ? `${len}s` : "1s");
    track.style.setProperty("--delay", len ? `${-Math.min(elapsed, len)}s` : "0s");
    track.classList.toggle("paused", v.paused); // (the bar held where it is)
    box.querySelector(".cplay").innerHTML = icon(v.paused ? "pause" : "play");
    const bar = track.querySelector("i"); // restarted
    bar.style.animation = "none"; void bar.offsetWidth; bar.style.animation = "";
  }
  const now = clock(len ? Math.min(elapsed, len) : elapsed), total = len ? clock(len) : "";
  const nowEl = box.querySelector(".cel"), lenEl = box.querySelector(".clen");
  if (nowEl.textContent !== now) nowEl.textContent = now;
  if (lenEl.textContent !== total) lenEl.textContent = total;
}
