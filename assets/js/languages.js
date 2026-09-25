// The site's languages: one folder each (<code>/, same file names), in this order in the menus. A new language:
// its folder of pages + an entry here (its name in its own language, and the site's few UI words - missing ones
// fall back to English).
export const LANGUAGES = [
  {
    code: "en", name: "English",
    ui: {
      language: "Language", pages: "Pages", search: "Search", placeholder: "Search the docs  ( / )", none: "Nothing found for",
      loading: "Reading the pages…",
      offline: "Search reads the other pages: open the site from a web server (GitHub Pages, or python -m http.server).",
      copy: "Copy", copied: "Copied", theme: "Theme", link: "Link to this section",
      missing: "This page isn't translated yet: its language's home page instead.",
      linkBad: "That isn't a web address: paste what the tunnel printed, like https://something.trycloudflare.com",
      linkLocal: "That's an address on your own PC or home network: it only works there. Paste the tunnel's address instead.",
    },
  },
  {
    code: "fr", name: "Français",
    ui: {
      language: "Langue", pages: "Pages", search: "Rechercher", placeholder: "Rechercher  ( / )", none: "Aucun résultat pour",
      loading: "Lecture des pages…",
      offline: "La recherche lit les autres pages : ouvrez le site depuis un serveur web (GitHub Pages, ou python -m http.server).",
      copy: "Copier", copied: "Copié", theme: "Thème", link: "Lien vers cette section",
      missing: "Cette page n'est pas encore traduite : la page d'accueil de cette langue à la place.",
      linkBad: "Ce n'est pas une adresse web : collez ce que le tunnel a affiché, comme https://quelquechose.trycloudflare.com",
      linkLocal: "C'est une adresse de votre PC ou de votre réseau : elle ne marche que là. Collez plutôt l'adresse du tunnel.",
    },
  },
];

export const DEFAULT = "en";

// The site's UI words in a language (English for what it lacks)
export function ui(code) {
  const en = LANGUAGES.find((l) => l.code === DEFAULT).ui;
  return { ...en, ...(LANGUAGES.find((l) => l.code === code)?.ui || {}) };
}

// The visitor's language: their pick on the site before, else the first of the browser's that the site has
export function preferred() {
  let picked = null;
  try { picked = localStorage.getItem("helios.site.lang"); } catch { /* private mode */ }
  if (LANGUAGES.some((l) => l.code === picked)) return picked;
  const prefs = navigator.languages?.length ? navigator.languages : [navigator.language || DEFAULT];
  for (const p of prefs) {
    const base = p.toLowerCase().split("-")[0];
    if (LANGUAGES.some((l) => l.code === base)) return base;
  }
  return DEFAULT;
}

export function remember(code) {
  try { localStorage.setItem("helios.site.lang", code); } catch { /* this visit only */ }
}
