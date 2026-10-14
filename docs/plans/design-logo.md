# design/logo — Abstractly logomark concepts

Approved by the user's task prompt (2026-10-05): design exploration only,
**the live site is not changed**.

## Goal
Three original logomark concepts built on a capital A, each with mark,
mark + wordmark lockup, dark and light versions, and a 16px favicon,
plus a preview page `design/logo/index.html`.

1. **Split crossbar** — sharp A, crossbar broken and stepped (two records that don't match).
2. **Fluted A** — A cut into five vertical ribs (the hero's fluted-glass bands); one rib gold.
3. **Ledger A** — two slanted strokes, crossbar is one gold highlighted row.

## Approach
- `design/logo/build.py` is the single source of the geometry; it writes every SVG
  and the preview page. Wordmark = Inter SemiBold from `frontend/fonts/`, outlined
  with fontTools + uharfbuzz (dev-only, not app dependencies).
- Palette only: `--lux-black`, `--lux-charcoal`, `--lux-ivory`, `--lux-accent`,
  `--primary-dark` (gold on light backgrounds).
- Favicons are separate pixel-hinted drawings on a 16px grid on a charcoal tile.

## Out of scope
- Swapping the chosen mark into `frontend/` (favicon.svg, favicon.ico,
  apple-touch-icon, og-image, header/footer SVGs) — a follow-up task once a concept is picked.
- Trademark search (not done; originality is a design judgement only).

## Round 2 (2026-10-05) — user rejected all three round-1 concepts
New direction from the user: a capital A built only from stacked horizontal
bars (rent-roll rows), lengthening top to bottom, gap for the counter, one
bar shifted sideways as the caught mismatch. White on black, optional gold
shifted bar; Inter Medium wordmark, slightly tight tracking. Three
variations: 5 / 7 / 9 bars, differing in bar thickness and offset
strength. No circles or spheres; must not resemble Ornn's or any other
company's mark. Round-1 files were replaced (still in git history, `60b1131`).

## Round 3 (2026-10-05) — ship Seven rows to the live site
User's pick: **Seven rows, all white, no gold**. Swap it in:
- Header + footer mark on `index.html` and `pricing.html` (pixel-hinted 24x19
  SVG, `currentColor`); brand wordmark to Inter Medium, -0.025em, per the lockup.
- `favicon.svg`, `favicon.ico` (16/32/48), `apple-touch-icon.png` (180).
- New `og-image.png` 1200x630: near-black, gold fluted bands right, logo top
  left, headline "Catch rent roll errors before you close", gold mono figure
  "$42,780 annual income overstated" labelled *Sample report* (the same
  fictional Maple Ridge figure the homepage hero shows).
- og + twitter tags on every page (14 HTML files); `?v=2` on icon and OG URLs
  so browsers and link-preview caches pick up the new files.
- Favicon thickness: checked at real 16px — 1px bars land on whole pixels and
  stay crisp, so no thickening was needed.

Sources: `design/logo/build.py` (SVGs) → `design/logo/render_assets.mjs` (PNGs/ICO,
`og/og-image.html`).

### Out of scope (follow-up)
- The app/admin/owner/404 screens still use the generic building icon next to
  "Abstractly" (`.brand-icon`, `.owner-brand-icon`); they have their own light
  styling, so swapping them is a separate UI task.
- No route, auth, or backend change: rule 4 (roles/team scoping) is n/a.
