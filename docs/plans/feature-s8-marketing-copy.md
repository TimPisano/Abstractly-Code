# feature/s8-marketing-copy (T11, homepage only)

**Approved scope:** the user's 2026-10-13 launch brief, Part 3 — rewrite the
landing page copy for Section 8 landlords and property managers.

## In scope
- `frontend/index.html` text only: headings, body copy, card text, FAQ,
  nav link text, form label text, `<title>`, meta description, OG and
  Twitter title/description.

## Unchanged (verified)
- Every tag, id, class, href, anchor (`#why-multifamily` stays as the id),
  script and form field name/payload — HTML tag skeleton compared before
  and after: identical (580 tags).
- Hero sample card numbers and the problem-section sample report (real
  engine output / labelled fictional data) — no new figures invented.
- Pricing (numbers and pricing copy), `pricing.html`, terms/privacy,
  brand files, `landing.js`, CSS.

## Out of scope
- `pricing.html` and the other pages' meta tags (PIVOT_PLAN T11 covers
  them later); demo/waitlist email copy; replacing the Maple Ridge hero
  card with Section 8 sample figures (needs T13's answer key on main).

## Known gap (claims discipline, PIVOT_PLAN Step 3)
Several lines describe Section 8 features that are not live on prod yet
(tenant share / HAP split = `fix/section8-tenant-share`; PHA, inspection
and recert tracking = T1/T9 behind `SECTION8_MODE`, off). The user asked
for this copy explicitly; merging it is the user's call.
