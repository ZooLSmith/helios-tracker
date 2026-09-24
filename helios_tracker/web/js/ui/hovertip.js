// The page's own tooltip for HTML elements (the map's look: base.css #tip, #htip), instead of the browser's
// title: any element with data-tip (its lines: "\n" separated) and / or data-tip-title (a bold first line), or
// data-tip-html (sections built by tipSections: already escaped).
// One delegated listener for the whole page; follows the pointer, kept inside the window.
import { esc } from "../dom.js";

let tip = null, target = null;

function show(el, x, y) {
  const title = el.dataset.tipTitle || "", body = el.dataset.tip || "", html = el.dataset.tipHtml || "";
  if (!title && !body && !html) return hide();
  if (target !== el) {
    target = el;
    tip.innerHTML = (title ? `<b>${esc(title)}</b>` : "") + html +
      body.split("\n").filter(Boolean).map((line) => `<span class="tl">${esc(line)}</span>`).join("");
    tip.style.display = "block";
  }
  place(x, y);
}

function place(x, y) {
  const gap = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  const left = x + gap + w > innerWidth ? Math.max(4, x - gap - w) : x + gap; // flipped near the edges
  const top = y + gap + h > innerHeight ? Math.max(4, y - gap - h) : y + gap;
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function hide() {
  target = null;
  if (tip) tip.style.display = "none";
}

export function initHoverTips() {
  tip = document.createElement("div");
  tip.id = "htip";
  document.body.appendChild(tip);
  document.addEventListener("pointerover", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-tip], [data-tip-title], [data-tip-html]") : null;
    if (el) show(el, e.clientX, e.clientY); else hide();
  });
  document.addEventListener("pointermove", (e) => { if (target) place(e.clientX, e.clientY); });
  document.addEventListener("pointerleave", hide);
  document.addEventListener("scroll", hide, true); // (the element moved away from under the pointer)
}

/** A tooltip line: text, or [before, value, after] - the value emphasised (.sval). */
function lineHtml(line) {
  if (!Array.isArray(line)) return esc(line);
  const [before, value, after] = line;
  return esc(before) + (value ? `<b class="sval">${esc(value)}</b>` : "") + esc(after || "");
}

/** A tooltip in sections (a divider between them): [{kind, head?, lines}] - kind: a class for its look
 *  ("meta", "stats", "desc"...), head: a small heading above its lines, lines: text or [before, value, after]
 *  (the value emphasised). Empty sections left out. */
export function tipSections(title, sections) {
  const has = (line) => (Array.isArray(line) ? line.some(Boolean) : !!line);
  const html = sections.filter((s) => s && s.lines && s.lines.some(has)).map((s) =>
    `<div class="tsec ${s.kind || ""}">${s.head ? `<span class="thead">${esc(s.head)}</span>` : ""}` +
    s.lines.filter(has).map((line) => `<span class="tl">${lineHtml(line)}</span>`).join("") + `</div>`).join("");
  return (title ? ` data-tip-title="${esc(title)}"` : "") + (html ? ` data-tip-html="${esc(html)}"` : "");
}

/** An element's tooltip attributes: data-tip-title="…" data-tip="line\nline" (escaped for HTML). */
export function tipAttrs(title, ...lines) {
  const body = lines.filter((l) => l != null && l !== "").join("\n");
  return (title ? ` data-tip-title="${esc(title)}"` : "") + (body ? ` data-tip="${esc(body)}"` : "");
}
