# Design & Polish Pass — Running Log

Started 2026-09-02. Working through 6 phases (design system, screen
rebuilds, states, responsive, accessibility, micro-polish), committing
after each. This file is the running log requested — updated as I go,
most recent entry at the bottom of each phase's section.

---

## Phase 1 — Design system audit

**Starting position, found by audit (not assumed):** this codebase
already went through a real design-system consolidation in an earlier
pass. `frontend/design-system.css` is a genuine single source of truth
— color palette (deep charcoal/ivory/brass, deliberately not a
templated indigo-gradient SaaS look), semantic colors, a neutral scale,
confidence/severity colors, an elevation (shadow) scale, a radius
scale, and shared button/loading primitives — and all three consumers
(`landing.css`, `frontend/app/styles.css`, `frontend/admin/admin.css`)
already `@import` it rather than redeclaring tokens. This is NOT a
hackathon-mixed-styles situation at the token level. Confirmed by
grepping for hardcoded hex colors outside design-system.css itself:
essentially none — 4 stray instances total across ~5,900 lines of CSS
(details below), not the widespread duplication I'd expect if this
needed a from-scratch rebuild.

**What WAS missing:** an explicit, named type scale and spacing scale.
Neither existed as tokens. Auditing actual usage (`grep -oE
'font-size:...'` etc. across all 3 stylesheets) showed a real de facto
scale already in disciplined use — spacing and type both sit on a
0.0625rem (1px @ 16px root) grid, e.g. font sizes 0.625 / 0.6875 /
0.75 / 0.8125 / 0.875 / 0.9375 / 1 / 1.0625 / 1.125 / 1.25rem etc., each
used dozens of times. So the scale already existed in practice; it just
wasn't named. Formalized it as CSS custom properties
(`--text-xs` … `--text-3xl`, `--space-1` … `--space-12`) so new work
has a documented scale to reach for, WITHOUT mass-converting ~600
already-correct existing declarations from raw rem to var() — that
conversion would be pure churn (no visual change, since the values
already match the scale) with real regression risk across a
4,400-line stylesheet this project has no automated visual-diff way to
verify. **Flagging this as a judgment call**, not a silent guess: if
you want every declaration converted to reference the new tokens
explicitly (rather than just having the tokens available for new/
touched code), say so and I'll do the mechanical pass.

**Concrete outliers found and fixed** (real inconsistencies, not
just missing formalization):

| File | Selector | Was | Now | Why |
|---|---|---|---|---|
| app/styles.css | `.access-gate-subtitle` | `0.9rem` | `0.9375rem` | matches the app-wide `.view-subtitle` convention used on every other screen |
| app/styles.css | `.access-gate-message` | `0.85rem` | `0.875rem` | matches `.btn-text`/body-text convention |
| app/styles.css | `.access-gate-link` | `0.85rem` | `0.875rem` | matches `.btn-text` exactly (it IS a text link) |
| app/styles.css | `.trend-chart-value-label` | `13px` | `0.8125rem` | exact conversion (13/16), off-grid px in an otherwise all-rem file |
| app/styles.css | `.trend-chart-axis-label` | `12px` | `0.75rem` | exact conversion (12/16) |
| app/styles.css | `.trend-chart-sublabel` | `10px` | `0.625rem` | exact conversion (10/16) |
| app/styles.css | `.qa-example-chip:hover` | `#e8dcc3` | `var(--lux-accent-tint-hover)` | new token added rather than a magic hex |
| app/styles.css | `.dashboard-date-filter-label` | `gap: 0.4rem` | `0.375rem` | off-grid, nearest real scale step |
| app/styles.css | `.team-members-table td/th` | `padding: 0.6rem ...` | `0.625rem ...` | off-grid, nearest real scale step |
| admin/admin.css | `.admin-gate-subtitle` | `0.9rem` | `0.9375rem` | same bug, duplicated from the app's login page CSS |
| admin/admin.css | `.admin-gate-message` | `0.85rem` | `0.875rem` | same bug, duplicated |
| admin/admin.css | `.assistant-message-bot.is-error` | `var(--error-color, #c0392b)` | `var(--error-color)` | dead fallback that didn't even match the real token's color |
| admin/admin.css | `.btn-deny:hover` | `var(--error-light, #fbeceb)` | `var(--error-light)` | same |
| landing.css | `.waitlist-error` | `color: #e5a5a0` | `var(--lux-error-on-dark)` | new token: the dark hero has no light-background error-red equivalent, so one was added rather than forcing the light-mode `--error-color` (would fail contrast on the dark hero) |

**Left alone, deliberately:** `.hero-subhead { font-size: 1.1875rem }`
in landing.css — only used once, but it IS on the 0.0625rem grid
(19 × 0.0625) and a marketing hero legitimately wants its own step
between the dense-UI scale and the huge display sizes. Not a bug.

**Verification:** re-ran the same audit greps after the fixes — zero
remaining stray hex colors outside design-system.css, zero remaining
off-grid font-size values. Live-checked (real browser, real
screenshots) the app login page, the admin login page, the landing
page, and the landing page's error state (triggered manually to
confirm `--lux-error-on-dark` renders legibly on the dark hero) — no
visual regressions from the token/value swaps.

**Noted for Phase 2, not fixed here** (a screen-consistency issue, not
a token issue — in scope for the screen-rebuild phase): the admin
login page's brand mark is a different icon (a plain document/file
glyph) than the app login page's brand mark (a building glyph). Same
wordmark, same card treatment, different icon — worth unifying when
Phase 2 touches both login screens.

Status: **done, committing.**

---
