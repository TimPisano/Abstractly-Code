# Plan: docs/design-tokens

## Goal

A single reference, `DESIGN_TOKENS.md` (repo root), listing every color,
font, spacing value, border radius, shadow, and logo asset the frontend
currently uses — where each is defined and where it's used. Where a color
is hardcoded in more than one place, point those places at a CSS variable
instead, **with zero change to any rendered pixel and zero change to app
behavior**. Proof: before/after headless screenshots of the homepage,
dashboard, and login page, pixel-diffed.

## Prior art

Searches: TASKS.md for `design|token|css var|design system`; `git log --all
--grep` for `design.?token|css variable|design system`; branch names for
`design|token|theme|css`; stash list.

- **`c63f138` "Phase 1: design system audit"** (on `main`): already made
  `frontend/design-system.css` the single source of truth for color,
  shadow, radius, and added `--text-xs..5xl` / `--space-1..16` scales. It
  deliberately did *not* mass-convert existing declarations. This task
  builds on that file — no second token file.
- `design/logo`, `design/og-image-minimal` (merged): the logo assets this
  doc will inventory. `docs/plans/design-logo.md` has their history.
- No open branch does token docs. Overlap risk: `fix/quick-wins` (375px
  CSS fixes, may touch `app/styles.css`) and `pivot/section8` (plan only).
  My CSS edits are a handful of lines, so conflicts should be trivial.

## What the scan found (hardcoded colors outside design-system.css)

42 distinct hex values; only 7 appear in more than one file. Real
duplicates worth centralizing:

| Value | Where | Existing token |
|---|---|---|
| `#2f6b4f`, `#9a3b3b` | `owner/owner.css:537-539` (quality tiers) | `--success-color`, `--error-color` |
| `#e3f1e8`, `#fdf0dc`, `#f7e0e0`, `#8a5a1c` | `owner/owner.css:537-539` | check for matching `-light` tokens; reuse if exact match, else leave |
| `#e5a5a0` | `app/auth.css:26` | `--lux-error-on-dark` |
| `#e0b374` ×4 | `landing.css:775,776,808,828` | none → one local var in landing.css |
| `#fff` ×3 | `app/auth.css:346,381,511` | `--white` (same color, `#fff` == `#ffffff`) |

Rgba values get the same treatment only where an exact token already exists.

**Deliberately left hardcoded (documented, not changed):**
- `<meta name="theme-color" content="#0a0a0b">` in 5 auth pages — HTML
  attributes can't read CSS variables.
- `app/report-view.js` iframe `srcdoc` colors — an iframe document does
  not inherit the parent's variables.
- `owner/owner-app.js` toast inline `color:#fff` and `landing.js` canvas
  RGB floats — JS/WebGL, not CSS.
- `var(--x, #fallback)` fallbacks (`app/index.html:502`,
  `deal-mismatch-view.js:196`, `owner.css:506/517/524`, `styles.css:2181`):
  where `--x` is **undefined**, the fallback is what actually renders, so
  "fixing" it would change pixels. Documented as findings only.

## Approach

1. Run the app locally (backend on a fresh temp DB with a seeded user +
   Maple Ridge demo deal, frontend static server) from the **unchanged**
   branch; capture **before** screenshots: `/` (homepage),
   `/app/login.html`, `/app/` dashboard (logged in), at 1440/768/375, top
   + mid + bottom scroll. Animations/the hero canvas frozen where possible
   (reduced-motion emulation) so the diff is deterministic.
2. Write `DESIGN_TOKENS.md`: colors (token → value → used in), fonts
   (Inter self-hosted, weights, fallback stacks, type scale), spacing
   scale + common off-scale values, radii, shadows, z-index if
   tokenized, logo/icon assets (favicon.svg/.ico, apple-touch-icon,
   og-image, header mark SVGs, `design/logo/` sources), plus the "left
   hardcoded" list above and why.
3. Make the color centralization edits in the table above — only where
   the computed value is byte-identical.
4. Capture **after** screenshots with the same DB and settings; pixel-diff
   every pair (Pillow, already in the venv). Also compare
   `getComputedStyle` color values of every element on those pages
   before/after (catches differences hidden below the fold).
5. Full test suite, commit, push branch, reviewer.

## Files to change

- `DESIGN_TOKENS.md` (new), this plan
- `frontend/owner/owner.css`, `frontend/app/auth.css`, `frontend/landing.css`
  (a few lines each), possibly `frontend/design-system.css` (add a token
  only if a duplicated value has none)

## Files not to touch

All JS, all HTML, all backend. No behavior changes. No "fixing" colors.

## Team isolation & roles

n/a — no routes or queries touched.

## Feature flag

n/a — no behavior change.

## Verification

- Before/after PNGs + per-pair pixel diff (expect 0 differing pixels) +
  computed-style diff; paths recorded in TASKS.md. I'll open and look at
  the screenshots.
- Owner console and auth pages other than login aren't in the requested
  set but are touched by the CSS edits — I'll add `/owner/` (login screen)
  and `/app/signup.html` to the diff run so every edited file is covered.
- `python backend/tests/run_all_tests.py`.

## Out of scope

- Mass-converting every hardcoded `rem`/`px`/rgba to tokens (that's the
  churn `c63f138` explicitly avoided).
- Fixing undefined-variable fallbacks, contrast, or any visual tweak.
- Updating CLAUDE.md's stale tenancy section.

## Open questions

1. `DESIGN_TOKENS.md` at repo root (as you wrote it) vs `docs/` — I'll use
   the **root** unless you say otherwise (`chore/repo-layout` wants a
   tidy root; flagging the tension).
2. Pixel-identical is the bar. If the hero canvas animation makes the
   homepage diff noisy even with reduced motion, I'll mask just that
   canvas region and say so — OK?
