# Helios Tracker - design wishes (not built yet)

Things the user wants the page to look like, decided but deliberately not done - with why, and what would
have to be true to do them. Part of the retheme toward Borderlands 2's art style (gradients, the game's own
fonts: done - `gamefonts.py`).

## Chamfered corners (45° cuts)

**The wish** (the user, 2026-09-24): Borderlands' UI often cuts panel corners at a sharp 45° instead of
rounding them - most often the top left and the bottom right ("/ ... /"), sometimes other pairs, sometimes the
bottom right alone. The page's panels, cards, tabs, buttons and skill tiles could do the same.

**Not done: no technique is safe enough yet.**

- `clip-path: polygon(...)` (works everywhere): clips everything outside the shape - and the page draws
  outside its boxes on purpose in places: the boosted skill's blue outer ring (`.scell.boosted`, a 2 px
  box-shadow outside the tile), the tiles' drop shadows (`--tile-depth`), glows (the cutscene bar's lit end,
  the bars' outlines), focus outlines. The diagonal also gets no border line (a two-layer workaround exists, a
  clipped border-coloured layer under an inset clipped background one, but it multiplies elements and breaks
  every `border` / inset ring we already use). Too risky to roll out: the user's call.
- `corner-shape: bevel` with `border-radius` (CSS Borders 4): the right tool - borders, shadows and outlines
  follow the cut, nothing is clipped. But Chromium only (shipped 2025): no Firefox support yet, and OBS's
  embedded browser (CEF, an older Chromium) doesn't have it either - the page is shown in OBS.
- Gradient-cut backgrounds (`linear-gradient(135deg, transparent 8px, ...)`): the fill only - borders and
  shadows stay square. Not the look.

**When to revisit:** `corner-shape` supported in Firefox and in the CEF of the OBS versions people use (then
as a progressive enhancement: `@supports (corner-shape: bevel)`, square corners elsewhere - no clip-path
fallback). Build it then as a few shared utilities in `base.css` (`chamfer-tl-br`, `chamfer-br`,
`chamfer-tr-bl`, a `--chamfer` size), piloted on the panel header, the drawer, the tabs and the skill tiles
before anything else.
