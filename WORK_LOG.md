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

## Phase 2 — Rebuild every core screen for consistency and polish

**Scope mapping, flagged rather than guessed silently:** the brief
names screens that don't map 1:1 onto what exists. Stating the
interpretation used, so it can be corrected:

- "Landing/marketing page" → `frontend/index.html` + `pricing.html`.
- "Login and signup" → `frontend/app/login.html` is the real login.
  There is no traditional self-serve signup — confirmed by a very
  recent commit's own research (`e202334`): "this app has no self-serve
  signup — an admin creates each team member's login directly." The
  closest thing to "signup" is the landing page's waitlist "Request
  Access" form (prospective customers, not existing team members).
  Treating that as "signup" for this audit.
- "Onboarding flow" → the zero-lease dashboard first-run state, which
  was *just* reworked in the commit immediately before this session
  (sample-lease button, simplified empty dashboard). Auditing it, not
  rebuilding it from scratch, given how recent that work is.
- "Main dashboard" / "lease upload flow" / "the abstraction results/
  review screen" / "the rent roll validation screen" → the app's
  Dashboard, Upload, Lease Detail (this IS "abstraction results" — the
  extracted-field review/verify/edit screen), and Rent Roll views,
  respectively, inside `frontend/app/index.html`.
- "Admin and owner logins" → **correction, mid-audit**: this was
  initially read as plain language for "the regular account holder"
  (no `owner` role existed in `ROLE_RANK` when Phase 1 started). A
  concurrent session then built a REAL owner console while this phase
  was in progress (`frontend/owner/login.html` + `index.html`, a
  standalone `is_owner`-gated mini-SPA for the SaaS product owner --
  account management + revenue/expense tracking, distinct from the
  admin role and from every CRE end-user screen). Corrected scope:
  "admin login" = `frontend/admin/index.html`, "owner login" =
  `frontend/owner/login.html`, now audited below.

**Found while mapping the scope, fixed immediately (belongs equally to
Phase 1's "don't leave old and new mixed"):** `frontend/app/index.html`
shipped an entire dead 3-panel access-gate UI (self-reported-email
sign-in / request-access / pending-approval panels) plus ~250 lines of
matching JS in `access-gate.js` — leftover from before real per-user
login existed. The code's own comments confirmed it: *"Gate is now real
per-user login... that machinery is retired (dead code, kept in place
... to minimize churn)."* It never rendered (the real init() always
either grants a session or redirects to `login.html`) but it still
shipped as bytes, CSS, and a maintenance trap. Removed the dead HTML,
trimmed `access-gate.js` from 344 → ~130 lines, and removed one now-
orphaned CSS block (`.access-gate-pending-icon`, confirmed unused
anywhere else first). **Verified live**, not assumed: cleared cookies,
confirmed an unauthenticated visit to `index.html` still redirects to
`login.html`; logged in for real and confirmed the dashboard still
renders with `CURRENT_USER` populated and the boot spinner correctly
hidden.

### Screen-by-screen findings

**Pricing (`pricing.html`).** Two real issues, both fixed:
1. Feature-list bullets were a hollow ring (`border`, no fill) next to
   "what's included in this tier" copy -- ambiguous at a glance (reads
   as easily as "not selected" as "included"). Replaced with a filled
   brass checkmark, reusing the palette rather than inventing a new
   color.
2. The bottom dark CTA section appeared fully invisible in a
   full-page screenshot. Investigated rather than assumed broken: it's
   a real, correctly-built scroll-reveal (`.reveal`/`.in-view`,
   `IntersectionObserver`-driven, with explicit fallbacks for
   `prefers-reduced-motion` and no-IntersectionObserver-support) --
   my screenshot method just doesn't trigger real scroll events.
   Verified with an actual `scrollTo()` that it fires correctly. Not a
   bug; false alarm, documented so it isn't "fixed" again later by
   someone hitting the same false alarm.

**Upload / Rent Roll / Lease Detail (main app).** Already clean,
consistent, well-organized -- no changes needed on Upload or Rent Roll.
Lease Detail (the "abstraction results/review" screen) has a real
"no clear single primary action" issue: six buttons of identical
`.btn-secondary` visual weight in the top toolbar (Export Report,
Export JSON, Download Excel, Export to Google Sheets, Download Summary
Memo, plus Delete as `.btn-danger`) before the actual review content
even starts. **Flagged, not restructured**: the thorough fix is
consolidating the five export paths into one "Export ▾" menu, which
means building a real dropdown component (and its own keyboard/focus
handling, which Phase 5 cares about) -- judged too large a structural
change to make safely mid-audit across five more remaining phases.
Noting it here as the clear next step if there's time, rather than
either leaving it silently or rushing a riskier fix.

**Admin dashboard.** Found and fixed a real bug, not a style issue:
the "Today's Priorities" digest was showing raw internal route paths
directly in user-facing copy -- literally `"...resolve it at
/discrepancies/155492 once you've confirmed which source is
correct."` A real "View →" link already sits right next to every one
of these rows, making the path reference both confusing (a CRE
professional has no reason to know what `/discrepancies/155492`
means) and redundant. Traced to `backend/app/alerts.py`'s
`_detect_new_discrepancy_alerts()` -- the message text predates the
"View →" link's existence and was never revisited. Removed the path
reference; also fixed a punctuation bug on the same line (the
appended sentence ran directly into the discrepancy's own message
with no separator, e.g. "...by 40% This hasn't been reviewed" with no
period). This is shared backend infrastructure -- verified the fix
renders correctly both on the admin dashboard AND the main app's own
Alerts feed (same underlying data), not just the one screen it was
first noticed on.

**Also noticed on the admin dashboard, deliberately NOT fixed:** the
same "Today's Priorities" list appears to show the same underlying
rent-mismatch issue twice -- once as a plain "Discrepancy: ..." row and
again as an "Alert: New discrepancy: ..." row with near-identical
text. This may be two genuinely different tracked records surfacing
by design, or it may be real duplication in how the priorities list
aggregates discrepancies + alerts. **Flagging rather than guessing**:
this needs tracing through the aggregation logic to determine which
it is before touching it, and risks breaking a working dedup
assumption elsewhere if changed without that -- didn't attempt it
during this pass.

**Owner console (`frontend/owner/`).** Brand new -- built by a
concurrent session literally while this phase was in progress, so it
predated Phase 1's token audit entirely. Found the whole stylesheet
(`owner.css`) used ad-hoc round decimals (0.2rem, 0.35rem, 0.4rem,
0.6rem, 0.7rem, 0.8rem, 0.85rem, 0.9rem, 0.95rem, 1.1rem, 1.4rem,
1.6rem -- 12 distinct values, ~30 declarations) instead of the
0.0625rem grid every other stylesheet in this product uses. Every one
mapped to its nearest on-grid value (all deltas ≤0.05rem, i.e.
imperceptible) via a scripted pass, verified after with the same
grid-check used in Phase 1 (zero off-grid values remain). The two
`h1` sizes got a more deliberate fix than "nearest grid step": the
login card's `h1` now matches `.access-gate-card h1` /
`.admin-gate-card h1` exactly (`1.25rem` -- same role, all three
logins), and the in-console page-header `h1` now matches the main
app's `.view-header h1` (`1.75rem` -- same role, a page title).

Also found and fixed a **real functional bug, not styling**: owner
login always failed with "This account does not have owner access,"
for every account including a genuine owner. `login.js` checks
`data.is_owner` on the `/auth/login` response, and the running
backend process was started before that field existed in the route's
response -- a stale-process issue (confirmed by reading the
route: `is_owner` was already correctly in the code and the session).
Restarted the backend; verified a real owner login now redirects
correctly and the console renders. **This is a live-environment
caveat worth knowing about, not a code defect**: any deployed instance
needs a restart after a backend change for it to take effect, same as
every other backend fix this session has needed to verify.

**Flagging, not changing:** the owner login page uses a dark/near-black
full-page background (`var(--lux-charcoal)`), while both other login
pages (app, admin) use the light ivory background + white card
convention. This reads as a deliberate choice (signaling "this is a
different, more restricted surface than a team login," similar to how
this app already uses dark sections purposefully elsewhere -- the
sidebar, the landing hero) rather than an accident, and the copy
reinforces it ("Not a team login. Sign in with the operator
account."). Left as-is rather than forcing visual parity with the
other two logins, but flagging explicitly since it's a real,
noticeable, currently-unexplained inconsistency between three
otherwise near-identical screens.

**Access-gate dead-code removal** (see above, this phase) also
belongs in this section as a Phase 2 deliverable, not just Phase 1's.

Status: **Phase 2 done, committing.**

---

## Phase 3 — States (loading, empty, error, success)

Audited rather than assumed a rebuild was needed, since Phase 1/2 had
already shown this codebase carries real, deliberate prior polish
passes. Findings:

**Error state: already hardened, verified not just read.** Checked
the backend first, since a leaked stack trace is the most damaging
possible "error state" failure for a product handling real financial
data. Found a real, deliberate prior "hardening pass": global
`@app.errorhandler`s for 400/404/413/500/`Exception` that ALL return a
clean, generic JSON message (the real exception is `logger.exception`'d
server-side only), and Flask's debug mode defaults off (opt-in via
`FLASK_DEBUG` env var, not on by default). Grepped the entire frontend
for patterns that would leak a raw error object or `.stack` into the
DOM -- none found. Spot-checked the newest code (owner console, built
literally this session) against the same pattern used everywhere
else (`apiRequest`'s clean network-error wrapper +
`escapeHtml(err.message)`) -- consistent, not a special case. Live-
tested a real error path (wrong-account owner login) and confirmed a
clean, correctly-styled, plain-language message renders (see
`p3_owner_login_error.png`).

**Loading states: present everywhere checked**, mixing spinner
(simpler lists/tables, e.g. Rent Roll's "⟳ Loading…" row that keeps
the table headers visible immediately) and true skeleton (denser
tiles, e.g. the Dashboard's stat cards) depending on content
complexity -- this is a reasonable, deliberate split, not an
inconsistency, and the brief's own wording ("skeleton OR spinner")
allows either. Verified live with network throttled via CDP
(`Network.emulateNetworkConditions`) rather than trusting a fast
localhost response to hide a blank-page flash.

**Empty states: present with real, helpful copy** everywhere audited
-- the zero-lease dashboard (redone the commit immediately before this
session), the owner console's Revenue & Expenses tab ("Manual entries
— no billing integration is connected yet." / "No entries yet -- add a
revenue or expense entry below to see a trend."), Rent Roll's empty
portfolio state. None of these are a bare "No data."

**Success confirmations: verified live**, not assumed from memory of
earlier work. Ran the real one-click "Try a Sample Lease" flow end to
end: lands directly on a fully-processed lease detail page (15/15
fields high-confidence, a "Sample" tag applied automatically) rather
than leaving the user on the upload screen wondering if anything
happened -- arriving somewhere concrete with the real result IS the
confirmation here, which reads as stronger than a toast that fades
while you're still looking at an empty form. (Toast-style confirmations
for other actions -- task creation, field-edit saves, password reset --
were already built and verified live in earlier work this session; not
re-verified here since nothing in Phases 1-2 touched that code.)

**No changes made in this phase** -- audit did not surface a gap
worth fixing that wasn't already caught by Phase 1/2's own findings
(the alert-message path leak, fixed in Phase 2, was itself partly a
"the copy shown after an error/discrepancy is confusing" issue that
belongs conceptually to this phase too).

Status: **Phase 3 done, committing.**

---

## Phase 4 — Responsive pass

Checked every core screen at 375px (mobile) and 768px (tablet) with a
real Chrome instance under CDP device emulation (not just a resize of
a desktop window) -- landing/pricing, the three login screens (app,
admin, owner), the authenticated app's dashboard, upload, lease
detail, and rent roll, the admin dashboard, and the owner console.

**A methodology trap worth recording**: the CDP screenshot helper's
`full_page=True` path re-applies and then clears its own device
emulation override as a side effect. Any plain screenshot taken later
in the same script silently reverted to the desktop window's real
size (1440x1000) even though a `window.innerWidth` check moments
earlier correctly reported 375. Fixed by re-applying the mobile
override immediately before every single screenshot rather than once
at script start -- this is a test-harness gotcha, not a product bug,
but it produced three convincingly "broken" login-page screenshots
before it was traced, so it's noted here in case it resurfaces.

**Real bug found and fixed: mobile viewport could be silently widened
by a single un-wrapped element.** On a real phone (and reproducibly
under CDP mobile emulation), an element that overflows its container
without anything clipping it doesn't just get cut off locally -- the
whole page's effective viewport widens to fit it, shrinking every
line of text and every other element down with it. This hit three
screens:

| Screen | Root cause | Fix |
|---|---|---|
| Dashboard | `.today-briefing-grid`'s `minmax(220px, 1fr)` × 3 columns has a hard 220px floor per track that doesn't relax below 768px | Added `grid-template-columns: 1fr` inside the existing `@media (max-width: 768px)` block |
| Dashboard, Rent Roll | `.main-content`, a flex item in a column-direction flex container, wasn't reliably stretching to the container's cross-axis width once a wide descendant (a button row, a table) was inside it -- `min-width: 0` alone didn't fix this in Chrome's flex layout, `width: 100%` did | Added explicit `width: 100%` to `.main-content` in the mobile media query |
| Owner Console | `.owner-header` (brand + email + Log Out) had no `flex-wrap`, so at 375px the Log Out button was pushed off the edge and clipped | Added `flex-wrap: wrap` to the base rule, plus a mobile override so the email/button pair drops to its own full-width row instead of squeezing next to the brand |

Also added a blanket `overflow-x: hidden` on `html`/`body` in
`design-system.css` (shared by every entry point) as a safety net --
belt-and-suspenders against the same "one overflowing element widens
the whole page" failure mode for anything not explicitly caught
above. The three fixes above address the actual causes; this just
stops a future miss from taking the whole page down with it, at the
cost of clipping (rather than reflowing) anything that still doesn't
fit -- worth remembering if a future screen looks fine on paper but a
control seems to have vanished at a narrow width, since the CSS
container-query-style breakpoints that already existed were doing
their job in every OTHER case checked (the sidebar's intentional
horizontal-scroll nav strip on mobile, the rent roll table's own
`.table-scroll` wrapper, the lease detail toolbar's 6-button wrap, the
`view-header`/`quick-actions-bar`/`table-controls` wrap rules) --
those were flagged as fine, not touched.

**Flagging, not changing**: the sidebar becomes a horizontally-
scrollable single-row tab strip below 768px (a prior session's
deliberate choice, documented in its own CSS comment) rather than a
hamburger menu. It has no visual affordance (fade edge, arrow) hinting
that more nav items are reachable by scrolling right -- a reasonable
mobile pattern, but the lack of a scroll hint is a judgment call on
discoverability, not something that reads as broken. Left alone here;
noted as a possible Phase 6 micro-polish candidate.

**Tablet (768px)**: no overflow found on any of the same screens once
the mobile fixes above landed (the `.main-content: width: 100%` fix in
particular resolved what would otherwise have been the same class of
issue here too). Multi-column layouts (today's briefing, owner
console's accounts table) render with real columns rather than a
cramped single-column squeeze, which is the expected tablet behavior
distinct from the mobile layout, not just a smaller version of
desktop.

Screenshots for this phase (before/after and tablet) live under
`/tmp/p4m_*.png` and `/tmp/p4t_*.png` on this machine -- not committed
to the repo (temp verification artifacts, not project files).

Status: **Phase 4 done, committing.**

---
