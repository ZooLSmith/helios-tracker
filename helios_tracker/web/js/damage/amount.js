// Damage amounts, the log's way: in full up to 99,999, short from 100,000 on ("130K", "1.2M": the language's compact
// form - the user: damage easily reaches 130,000), under 10 with a decimal (a burn's tick). Their column as wide as the
// biggest seen: store.maxHit, which only grows in a session (the user: no column resizing as hits get bigger).
import { num, numUpTo } from "../i18n.js";

const SHORT_FROM = 100000;
let compact = null, compactLang = "";

export function amountText(n) {
  if (n < 10) return numUpTo(n, 1);
  if (n < SHORT_FROM) return num(Math.round(n));
  const lang = globalThis.document?.documentElement.lang || "en";
  if (!compact || compactLang !== lang) {
    compactLang = lang;
    compact = new Intl.NumberFormat(lang, { notation: "compact", maximumFractionDigits: 1 });
  }
  return compact.format(n);
}

/** Whether amountText(n) isn't the exact number (its tooltip then gives it). */
export const isShortened = (n) => n >= SHORT_FROM;

let widest = 3; // the widest amount's text seen (characters): only grows - 99,999 is wider than 130K

/** The amount column's width (CSS: ch, the digits tabular) for amounts up to `n` - never narrower than before. */
export function amountWidth(n) {
  widest = Math.max(widest, amountText(n).length);
  return `${widest}ch`;
}
