// The page's icons: small inline SVGs (12 x 12, drawn with currentColor: the CSS colours them, 1em
// sized). No emoji / text glyphs as icons. One place to swap them for the game's own icons (or
// authored versions of them) later.

const ICONS = {
  check: `<path d="M2.4 6.4 4.9 8.9 9.7 3.4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  diamond: `<path d="M6 1.6 10.4 6 6 10.4 1.6 6Z" fill="currentColor"/>`,
  checkCircle: `<circle cx="6" cy="6" r="4.8" fill="currentColor"/>` + // ready to turn in: a check in a disc
    `<path d="M3.7 6.2 5.3 7.8 8.4 4.4" fill="none" stroke="#0b1116" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`,
  circle: `<circle cx="6" cy="6" r="3.5" fill="none" stroke="currentColor" stroke-width="1.5"/>`,
  circleDashed: `<circle cx="6" cy="6" r="3.5" fill="none" stroke="currentColor" stroke-width="1.3" stroke-dasharray="1.8 1.6"/>`,
  lock: `<rect x="2.8" y="5.4" width="6.4" height="4.8" rx="0.9" fill="currentColor"/>` +
    `<path d="M4.2 5.4V4a1.8 1.8 0 0 1 3.6 0v1.4" fill="none" stroke="currentColor" stroke-width="1.3"/>`,
  question: `<circle cx="6" cy="6" r="4.6" fill="none" stroke="currentColor" stroke-width="1.2"/>` +
    `<path d="M4.6 4.7a1.5 1.5 0 1 1 2.1 1.4c-.5.3-.7.6-.7 1.1" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>` +
    `<circle cx="6" cy="8.7" r=".75" fill="currentColor"/>`,
  close: `<path d="M3 3 9 9M9 3 3 9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>`,
  back: `<path d="M7.6 2.4 4 6l3.6 3.6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
  chevronDown: `<path d="M3.2 4.6 6 7.4l2.8-2.8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  chevronUp: `<path d="M3.2 7.4 6 4.6l2.8 2.8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  chevronRight: `<path d="M4.6 3.2 7.4 6 4.6 8.8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>`,
  tune: `<path d="M1.8 3.6h8.4M1.8 8.4h8.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>` + // settings: two sliders
    `<circle cx="4.4" cy="3.6" r="1.5" fill="currentColor"/><circle cx="7.6" cy="8.4" r="1.5" fill="currentColor"/>`,
};

export const ICON_NAMES = Object.keys(ICONS);

/** An icon's SVG markup (an unknown name: the question mark). */
export function icon(name, cls = "") {
  return `<svg class="icon${cls ? " " + cls : ""}" viewBox="0 0 12 12" width="1em" height="1em" aria-hidden="true">${ICONS[name] || ICONS.question}</svg>`;
}

/** Fills the static HTML's [data-icon] elements. */
export function applyIcons(root = document) {
  for (const el of root.querySelectorAll("[data-icon]")) el.innerHTML = icon(el.dataset.icon);
}
