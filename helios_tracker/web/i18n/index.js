// The page's translations: one catalog per language, looked up with t("key", {vars}) (js/i18n.js).
// A key missing in a language falls back to English. To add a language: copy en.js to
// "<code>.js" ("de", "es", ...), translate the values and add it below; the page picks it
// automatically from the browser's languages (or the Language menu).
import en from "./en.js";
import fr from "./fr.js";

export default { en, fr };
