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
