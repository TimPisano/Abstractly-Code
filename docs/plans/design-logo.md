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
