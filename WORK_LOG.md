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

## Phase 5 — Accessibility

Two gaps, both fixed and committed together (`260ecd1`):

**Every placeholder-only input had no accessible name.** A screen
reader on the login form, the dashboard filter row, the tag/QA inputs,
the team-add form, messaging, the owner console filters/entry forms,
and the admin login all announced "edit text, blank" -- the visible
label was a `placeholder`, which assistive tech does not treat as a
name. Added `aria-label` to all of them (13 files). No visual change.

**The accent brass failed WCAG AA as text.** `--lux-accent` (#b68a4e)
is 3.1:1 on white -- fine for a button fill or an icon (non-text UI
only needs 3:1), but below the 4.5:1 bar for actual text: "Go to
Alerts ->", "See what's driving this score ->", the `.btn-text` links,
accent-colored table/version/tag labels, `.source-page`, etc. Added
`--lux-accent-text` (= `--primary-dark`, #8f6c3a, the same brass one
step darker -- already in the palette) and swapped it in for the ~40
places the accent renders AS text. Button fills, borders, and
`accent-color` on native controls deliberately keep the lighter
`--lux-accent`. Verified live: login/forgot/reset pages, dashboard,
owner console -- accent text renders as legible brass, no regression.

**Also fixed here:** `owner.css`'s `.text-input:focus` had only a
border-color change, no focus ring -- every other `.text-input` in the
product pairs it with a 3px brass ring. Added it for parity.

Status: **Phase 5 done, committed (`260ecd1`).**

---

## Phase 6 — Final consistency sweep

Re-walked the full page inventory (see checklist at the bottom of this
file) against the now-touched codebase. Most screens are consistent --
the palette, card treatment, type scale, stat tiles, sidebar, and
health/confidence components all read as one system across the app,
admin, and owner surfaces. One real fix, three flags.

**Fixed (`de40025`): stacked-form layout on the forgot/reset-password
pages.** `styles.css` has a flex-column rule that forces the
access-gate forms into a stable vertical stack
(`#accessGateForm, #accessGateRequestForm, #loginForm`). `#forgotForm`
and `#resetForm` -- same shape, same card, added later on their own
pages -- were never added to it, so their input + submit button fell
back to inline flow: the button rendered narrower-than-full-width and
flush against the input with no gap, unlike every other login card.
The rule's own comment already describes this exact bug for the old
login page. Added both ids. Verified live (forgot + reset pages now
match login's stacked layout).

**Flagged, not changed -- judgment calls that affect how the product
looks:**

1. **Three login screens, three brand treatments.** App login
   (`app/login.html`) and forgot/reset use a brass building-glyph icon
   + centered wordmark on the ivory background. Admin login
   (`admin/index.html`) uses a document-glyph icon (different icon,
   same everything else). Owner login (`owner/login.html`) has no icon
   at all, left-aligned text, on a near-black background. The dark
   owner background reads as deliberate (WORK_LOG Phase 2 covers it --
   "not a team login" signalling) and the copy reinforces it. The
   **icon mismatch** (building vs. document vs. none) does not read as
   deliberate -- it looks like three people built three login pages.
   First flagged in Phase 2; still open. Unifying on the building glyph
   is the obvious call but it changes the admin + owner login visuals,
   so leaving it for a human decision.

2. **Mobile sidebar has no scroll affordance.** Below 768px the
   sidebar is a horizontally-scrollable tab strip with 11+ items and
   no fade edge / chevron hinting there's more to the right. Carried
   over from Phase 4. Reasonable pattern, discoverability is the only
   question -- a ~24px fade on the right edge would resolve it.

3. **Three separate modal implementations** in the app
   (`discrepancy-modal.js`, `task-detail-modal.js`, `export-modal.js`)
   each with their own `-backdrop`/`-overlay`/`-close` classes and
   their own focus handling, plus a fourth in the owner console
   (`.owner-modal-overlay`). They look close enough that this isn't
   visible to a user today, but there's no shared modal primitive, so
   they can drift. Not a redesign-pass fix -- noting it as tech debt
   the next structural pass should consolidate.

**Not re-audited (out of scope for this session -- "gaps only"):** the
deep responsive re-check of the authenticated SPA at every breakpoint
(Phase 4 did this with working CDP tooling and documented it); the
states audit (Phase 3). This session's headless screenshot harness hit
the same emulation-vs-`captureBeyondViewport` gotcha Phase 4 recorded
-- worked around it (tall fixed viewport, no beyond-viewport capture)
but only after it produced several misleading "squished" SPA captures.
If re-runing visual checks, set the device-metrics height large and
screenshot normally rather than relying on `captureBeyondViewport`.

Status: **Phase 6 done, committed (`de40025`).**

---

## Page & component inventory (Phase 1 checklist)

The checklist the session was run against. "Prior" = done by the
earlier design pass (commits `c63f138`..`03662cd`); "P5"/"P6" = this
session.

### Standalone pages

| Page | File | Status this session |
|---|---|---|
| Landing / marketing | `index.html` + `landing.css` | Prior (Phase 1-2). P5: eyebrows/links/accents -> `--lux-accent-text`. Verified clean. |
| Pricing | `pricing.html` | Prior (Phase 2: brass checkmarks, scroll-reveal false-alarm documented). P5: `.pricing-tier-price-custom` -> accent-text. Verified clean. |
| App login | `app/login.html` | Prior. P5: aria-labels. Verified clean. **Flag: brand icon differs from admin/owner.** |
| Forgot password | `app/forgot-password.html` | P5: aria-label. **P6: fixed form not stacking (`de40025`).** Verified. |
| Reset password | `app/reset-password.html` | P5: aria-labels. **P6: fixed form not stacking.** Error state (dead/absent token) verified clean. |
| Admin login gate | `admin/index.html` | P5: aria-labels. Verified clean. **Flag: document-glyph brand icon vs app's building glyph.** |
| Owner login | `owner/login.html` | Prior (Phase 2: h1 sizing, grid). P5: aria-labels, focus ring. Verified clean. **Flag: no brand icon, dark bg (bg is deliberate).** |

### App SPA (`app/index.html`) — views via `registerView()`

| View | Module | Status |
|---|---|---|
| Dashboard (+ zero-lease onboarding state) | `dashboard-view.js` | Prior (Phase 2-3). P5: ~15 accent-text swaps, filter aria-labels. Verified clean at desktop. |
| Alerts | `alerts-view.js` | Prior. P5: severity/type filter aria-labels. Backend alert-copy path-leak fixed in Phase 2. |
| Discrepancies | `discrepancies-view.js` | Prior. P5: filter aria-labels. **Note: concurrent session has uncommitted edits here — not touched.** |
| Portfolio Trends | `trends-view.js` | Prior (Phase 1: px->rem on chart labels). Not re-audited. |
| Tasks | `tasks-view.js` | Prior. Not re-audited. |
| Upload Leases | `upload-view.js` | Prior (Phase 2: "already clean"). Verified clean at desktop. |
| Expirations / Timeline | `timeline-view.js` | Prior. Not re-audited. |
| Rent Roll | `rentroll-view.js` | Prior (Phase 2 + Phase 4 `.main-content` width fix). Not re-verified (harness limit). |
| Compare | `comparison-view.js` | Prior. Not re-audited. |
| Ask a Question (portfolio) | `qa-view.js` | Prior. P5: `#qaInput` aria-label, `.qa-example-chip` accent-text. |
| Portfolio Report | `report-view.js` | Prior. Not re-audited. |
| Team Notes | `team-notes-view.js` | Prior. Not re-audited. |
| Team | `team-view.js` | Prior. P5: team-add-form aria-labels (name/email/role/password). |
| Lease Detail ("abstraction results") | `detail-view.js` | Prior (Phase 2: flagged 6 equal-weight toolbar buttons — still open, needs a real Export dropdown). P5: tag/QA input aria-labels, `.source-page`/`.version-chip` accent-text. |
| Comments / verify popover / discrepancy modal / export modal / task modal | `comments.js`, `verify-popover.js`, `discrepancy-modal.js`, `export-modal.js`, `task-detail-modal.js` | Prior. **P6 flag: 3+ separate modal implementations, no shared primitive.** |

### Admin SPA (`admin/dashboard.html`)

| View | Module | Status |
|---|---|---|
| Overview / "Today's Priorities" | `admin-dashboard-view.js` (`overview`) | Prior (Phase 2: fixed raw route paths + punctuation in digest copy). Verified clean. |
| Leases & Rent Rolls | `admin-dashboard-view.js` (`dashboard`) | Prior. Not re-audited. |
| Upload | `admin-upload-view.js` | Prior. Not re-audited. |
| Access Requests | `admin-bootstrap.js` (`access`) | Prior. Not re-audited. |
| Alerts / Discrepancies / Trends / Reports / Team / Activity | shared with app modules | Prior. Not re-audited. |
| Settings | `admin-bootstrap.js` (`settings`) | Prior. Not re-audited. |
| Lease Detail (admin) | `admin-detail-view.js` | Prior. Not re-audited. |
| Assistant | `assistant.js` | Prior (Phase 1: dead error-color fallback removed). P5: `.today-quick-action svg` accent-text. |

### Owner console (`owner/index.html`)

| Tab | Module | Status |
|---|---|---|
| Accounts | `owner-app.js` | Prior (Phase 2: grid values, h1 sizing; is_owner login bug). P5: filter aria-labels, `.owner-row-link` accent-text, focus ring. Verified clean. |
| Revenue & Expenses | `owner-app.js` | Prior (Phase 3: empty-state copy verified). P5: revenue/expense form aria-labels. |

### Shared design system

| Artifact | File | Status |
|---|---|---|
| Tokens (color, type scale, spacing scale, shadow, radius) | `design-system.css` | Prior (Phase 1 formalized type/spacing scales, semantic palette). P5: added `--lux-accent-text`. This file **is** the enforceable design system — no separate DESIGN_SYSTEM.md needed. |
| Shared buttons (`.btn-primary/secondary/danger/block`) | `design-system.css` | Prior. Consistent across all surfaces. |
| Shared loading affordances (`.spinner-small`, `.loading-inline`) | `design-system.css` | Prior (Phase 3). |
| `overflow-x: hidden` safety net | `design-system.css` | Prior (Phase 4). |
| `.text-input` / `.btn-text` / `.view-header` / `.panel` / `.empty-state` / `.skeleton` / `.nav-item` / `.toast` | `app/styles.css` | Prior. P5: `.btn-text`, `.empty-state-icon svg` -> accent-text; `.text-input:focus` ring propagated to owner.css. |

---
---

# ═══ SESSION 2 — QA / Hardening Pass ═══

Started 2026-09-03. Separate 6-phase brief from the design pass above:
(1) cross-browser + real-device, (2) performance, (3) branding/identity
details, (4) data-heavy screens, (5) interaction depth, (6) a11y
(dynamic content + keyboard). Same rules: commit per phase, running log.

## S2 Phase 1 — Cross-browser & real-device

**Live testing on Safari, Firefox, and a real device is BLOCKED in this
environment — flagged, not silently skipped:**
- Firefox is not installed (no `brew` install done — heavy, and the
  user is away).
- Safari automation needs `Allow Remote Automation` + a screen-
  recording permission grant, both of which require the user present.
  `safaridriver` session creation and `screencapture` both fail.
- No real device access.
- What I *could* run live: Chrome (Chromium engine) via CDP, which the
  design pass already used. So "tested in Chrome + static analysis for
  the other two engines" is the honest summary.

**Static cross-engine audit (CSS + JS) — result: clean.** This
codebase is unusually conservative and already well-prefixed:
- No `backdrop-filter`, `:has()`, `@container`, CSS nesting,
  `aspect-ratio`, `-webkit-line-clamp`, scrollbar styling, `<dialog>`/
  `showModal`, `inert`, `text-wrap`, `navigator.share/clipboard`,
  `showPicker`, `structuredClone`, `randomUUID`. Nothing that splits
  across Chromium/WebKit/Gecko.
- `-webkit-mask-image` (landing hero grid fade) already has the
  unprefixed `mask-image` right beside it.
- `<summary>` marker: `.faq-item summary` already sets `list-style:
  none` (the Firefox-correct way) *and* `::-webkit-details-marker`.
- Date parsing: `owner-app.js` constructs dates with numeric args and
  carries a comment about the `new Date("YYYY-MM-DD")` UTC-midnight
  footgun — already handled.
- `100vh` on `.sidebar` (`height: 100vh; position: sticky`) is
  desktop/tablet only — the sidebar goes `position: static` below
  768px, so the mobile-Safari "100vh includes the URL bar" bug doesn't
  bite here.
- `input[type=date]` is styled only with `padding` + `width` (no
  attempt to override the native control internals), so Safari's
  differently-shaped date field degrades cleanly rather than breaking.

**THE cross-browser bug — architectural, production-only, flagged for a
human decision (see DEPLOYMENT.md, new section added this pass):**
Session auth is a cookie (`SameSite=None; Secure; HttpOnly`). In prod
the frontend (`abstractly-n0id.onrender.com`) and backend
(`abstractly-api.onrender.com`) are **cross-site** — `onrender.com` is
on the Public Suffix List, so those two subdomains are separate sites,
not just separate origins. Consequences:
- **Safari: login is broken.** ITP blocks `SameSite=None` third-party
  cookies outright since 2020. `POST /auth/login` returns 200 + the
  cookie, Safari drops it, the next `/auth/session` is
  unauthenticated → the app bounces straight back to the login page.
  Classic "login loops in Safari."
- **Chrome: works today, fragile.** Third-party-cookie deprecation is
  paused, not cancelled; enterprise policy or the user toggling the
  setting breaks it.
- **Firefox: works.** Total Cookie Protection *partitions* rather than
  blocks, so the cookie persists keyed to the top-level site.
- **Dev is unaffected** — `localhost:8000` ↔ `localhost:5000` is
  same-site (ports don't factor into "site"), so the cookie is
  first-party locally. This is exactly why it hasn't been caught.
- **Not fixed here** — every fix is a deployment/architecture change
  that can't be verified while the user is away: (a) a custom domain
  with `app.` + `api.` subdomains of one registrable domain makes them
  same-site and `SameSite=Lax` starts working; (b) reverse-proxy the
  API under the frontend's own origin (`/api/*`) so the cookie is
  first-party; (c) switch to `Authorization: Bearer` tokens in
  `localStorage`. (a) is the cleanest and the custom-domain step is
  already half-documented. Wrote all of this into DEPLOYMENT.md under
  a new "Known issue: sign-in on Safari" section so it can't get lost.

**Fixes committed this phase:** none to code — the static audit found
nothing engine-specific to fix, and the one real bug is architectural.
DEPLOYMENT.md gains the Safari section.

Status: **S2 Phase 1 done (audit + DEPLOYMENT.md warning), committing.**

---

## S2 Phase 2 — Performance

**Baseline (Lighthouse 13.4, simulated mobile throttling, local
server) → after:**

| Page | Perf | FCP | LCP |
|---|---|---|---|
| Landing | 94 → **100** | 1.75s → **1.26s** | 2.89s → **1.65s** |
| Pricing | 97 → **100** | 1.41s → **1.20s** | 2.51s → **1.50s** |
| App login | 98 → **99** | 1.98s → **1.5s** | 1.98s → **1.8s** |

TBT was already 0 ms everywhere; CLS 0 (0.017 on pricing) — unchanged,
still well under budget. Numbers are local-server + simulated
throttling, so treat them as relative (the deltas are real, the
absolute values will differ on Render).

**What changed:**

1. **Self-hosted Inter** (the big one — most of that LCP drop). Was
   `<link>`d from `fonts.googleapis.com`, which is two render-blocking
   cross-origin round trips: the CSS from `googleapis.com`, then the
   woff2 from `gstatic.com`. Replaced with one 48 KB same-origin file
   (`frontend/fonts/inter-latin-var.woff2` — Inter's Latin subset,
   which is a single variable file covering weights 100–900), declared
   via `@font-face` in `design-system.css`, `font-display: swap`. OFL
   license bundled alongside (`frontend/fonts/OFL.txt`). Removed the
   two `fonts.*` preconnects from all 10 HTML entry points.
2. **Font preload** on every entry point (`<link rel="preload"
   as="font" crossorigin>`) so the woff2 starts downloading with the
   first bytes of HTML rather than after the CSS parses — kills the
   fallback→Inter flash on the landing hero h1.
3. **Killed the `@import`** at the top of `app/styles.css`
   (`@import '../design-system.css'`). That forced the browser to
   download + parse styles.css before it could even discover
   design-system.css (and the font it declares) — a serial chain.
   design-system.css is now a direct second `<link>` before styles.css
   in the 5 HTML files that reach it that way (the 4 app/* pages +
   admin/dashboard.html). Parallel download now.
4. **App-script preload** in `app/index.html`: `api.js`, `app.js`,
   `dashboard-view.js` are warmed via `<link rel="preload"
   as="script">`. `access-gate.js` only injects the ~20 view scripts
   *after* the `/auth/session` round trip; preloading the 3 on the
   first-paint path means they're cached the instant the gate passes
   instead of starting a fresh waterfall.
5. **Cache-Control headers** for the static site — *recommended, NOT
   committed*. `render.yaml`'s frontend `headers:` block was being
   actively edited by a concurrent session (adding a security-header /
   CSP block) and YAML rejects a duplicate `headers:` key, so I left a
   `NOTE` comment in that block instead of a conflicting second list.
   The entries to merge in: `/*` CSS/JS `public, max-age=600,
   must-revalidate` (not content-hashed — no build step — so a short
   TTL keeps deploys from being stuck behind stale caches), `/*.html`
   `no-cache` (deploys visible immediately), `/fonts/*`
   `max-age=2592000`. **Whoever lands that security block: add these.**
   (Also — that session's CSP is `font-src 'self'`, which would have
   blocked the *old* Google Fonts `<link>`. This pass's self-hosting
   change is what makes their CSP correct; the two changes depend on
   each other.)

**Images: none exist.** The entire frontend has zero raster images —
every icon is inline SVG, no `<img>` tags, no `url()` bitmaps, no
background images. "Optimize images / add lazy-loading" has nothing to
act on. Total frontend payload is 944 KB uncommitted, ~1 MB, and
gzips to a fraction of that.

**Not done, deliberately:**
- **CSS/JS minification** (Lighthouse flags ~16 KB of unminified CSS).
  This needs a build step, which the project has explicitly chosen not
  to have (`render.yaml`: "static site, no build step"). Render gzips
  on the wire so the real cost is ~3 KB. Flagging as a future call: if
  a build step is ever added for another reason, minify then.
- **Combining design-system.css + the per-surface CSS** into one file
  per page — would save one request but duplicates the token file 4×
  and breaks the single-source-of-truth. Not worth it over HTTP/2.

**Data-heavy screens** (lease detail / rent roll) are addressed in S2
Phase 4 — DOM weight + render cost measured there.

Status: **S2 Phase 2 done, committing.**

---

## S2 Phase 3 — Branding & identity details

**Favicon — there was none.** No `<link rel="icon">`, no `.ico`, no
manifest, on any page — every tab showed the browser's blank-doc
default, and the browser's automatic `/favicon.ico` request was 404ing
(showed up as a console error in the Lighthouse best-practices audit).
Added:
- `favicon.svg` — the brass building glyph on a rounded charcoal
  square, reads on both light and dark browser chrome. Primary icon
  for every modern browser.
- `favicon.ico` — 16+32 px, rasterized from the SVG (via headless
  Chrome, since there's no build step / SVG rasterizer). Fallback for
  older browsers and the automatic root request.
- `apple-touch-icon.png` — 180 px, full-bleed charcoal (iOS applies
  its own rounded mask), for "Add to Home Screen".
- Linked on all 10 HTML entry points with root-absolute paths.

**Logo consistency — the brand mark was three different icons.** The
app + its sign-in pages used a *building* glyph; the landing page
(nav + footer), pricing, and both admin pages used a *document*
glyph; the owner console was wordmark-only with no icon. The design
pass had flagged this and left it for a decision — S2 Phase 3's brief
("consistent logo usage across every page") is that decision.
Standardized on the **building** glyph (real estate, and it's what the
actual product already used): swapped it into the landing nav +
footer, pricing, and both admin brand marks; added it to the owner
console brand mark (login card + in-console header) with a small
`.owner-brand` flex rule + `.owner-brand-icon` in `owner.css`. The
*document* glyph still appears as a nav-item icon for "Reports &
Exports" / "Portfolio Report" — that's semantically correct there and
was left.

**Social / SEO meta — none existed.** No `<meta name="description">`,
no Open Graph, no Twitter Card, anywhere (Lighthouse SEO was 90 on
every page for the missing description alone). Added to the two public
marketing pages (`index.html`, `pricing.html`):
- `meta name="description"` (real copy pulled from the hero / pricing
  intro).
- Full OG set (`og:type/site_name/title/description/url/image` +
  `image:width/height`) and Twitter `summary_large_image`.
- `og-image.png` — a 1200×630 card generated to match the landing
  hero (charcoal, brass "Underwriting-Ready." accent, building glyph,
  real tagline). `og:image`/`og:url` are absolute per spec and point
  at the current `abstractly-n0id.onrender.com` host — commented as
  another place to update on a custom-domain move (alongside
  `config.js` and `render.yaml`).
- The 8 app/admin/owner pages got `<meta name="robots" content="noindex">`
  instead — they're behind auth, shouldn't be indexed, and don't need
  social cards.

**Custom 404 — `frontend/404.html`.** Render static sites serve
`/404.html` from the publish root for any unmatched path. Built one on
the same `.access-gate-card` treatment as the sign-in screens: brass
building glyph, "404 / Page not found", "Go to homepage" +
"Sign in to the app". Was a bare Render default 404 before.

**Console 404 fixed as a side effect** — the missing `/favicon.ico`
was the "browser errors were logged to the console" ding on the
landing page's best-practices score.

Status: **S2 Phase 3 done, committing.**

---

## S2 Phase 4 — Data-heavy screens

Targets: the abstraction-results screen (lease detail, `detail-view.js`
— a card grid, not a table) and the rent-roll table (`rentroll-view.js`
`#rentRollTable`), plus the dashboard lease library and comparison
table, which share `.data-table` / `.table-scroll`.

**Sticky table headers — there were none** (`position: sticky`
appeared exactly once in the whole app: the sidebar). `.table-scroll`
was `overflow-x: auto` with no height cap, so a 60-row rent roll just
grew the page and the header scrolled away.
- `.table-scroll` now `overflow: auto; max-height: calc(100vh - 12rem)`
  — a scroll frame tall tables need and short ones never reach.
- `.data-table th` → `position: sticky; top: 0` + opaque background +
  a `box-shadow` restating the bottom border (a sticky cell's own
  border detaches mid-scroll in some engines).
- `.rent-roll-totals-row td` → `position: sticky; bottom: 0` so the
  portfolio TOTAL stays visible while rows scroll.
- Verified with a scrolled+cloned rent roll under CDP: header pins,
  body scrolls under it. **Needs a real 50+ lease portfolio to
  confirm at production scale** — the test DB only has 5.

**Confidence: low-confidence fields now actually stand out.** The
result card's left border was green for *anything* found, regardless
of tier — a low-confidence value looked as trustworthy as a verified
one. Now:
- `.result-card.found.conf-high` → green border (unchanged look)
- `.result-card.found.conf-medium` → amber border **+ amber-tinted
  card header**
- `.result-card.found.conf-low` → red border **+ red-tinted header**
- `.found` with no tier keeps green (confidence unknown).
`detail-view.js` emits `conf-<tier>` from `fieldData.confidence`.
Confirmed live: on a 13-high / 1-medium lease, the single "Lease End
Date" card reads as the obvious thing to check in a grid of 15.

**Not color alone — confidence badges get a glyph.** `confidenceBadgeHtml`
now prefixes a small `aria-hidden` SVG: ✓ high, ⚠ medium, ! low, –
not-found. Green-high vs red-low is the exact pair deuteranopia
collapses; the badge already had the words ("High Confidence"), the
icon + the lightness-based header tint add two more non-hue channels.
`.confidence-badge` became `inline-flex` with a gap to seat the icon.

**Column widths:** left as auto-layout. The verbose extracted date
strings ("1st day of January, 2026") wrap a little, but that's the
*value* being verbose, not a width bug — forcing `nowrap` would push
the table into horizontal scroll on desktop where it currently fits.
`.table-scroll` already handles the narrow-container case.

Status: **S2 Phase 4 done, committing.**

---

## S2 Phase 5 — Interaction depth

**Toast feedback: already thorough.** ~130 `showToast` call sites
covering saved / deleted / renamed / uploaded / reassigned / resolved /
password-reset across app, admin, and owner. Toasts already animate in
and out (`.show` via rAF, 4s, fade out). No gaps worth filling — this
was built well in earlier work.

**Confirmation dialogs: existed, but were `window.confirm()`.** Every
destructive action already gated on a confirm (delete lease(s), delete/
dismiss task, deactivate member, deny access, suspend account, reset
password, delete finance entry) — but via the browser's native OS
dialog, which is jarring, unstyleable, and reads as unfinished in an
otherwise-polished product.

Replaced all 11 call sites with **`confirmDialog()`** — a real in-app
dialog returning `Promise<boolean>`:
- Shared `.confirm-backdrop` / `.confirm-dialog` CSS in
  `design-system.css` (backdrop fades, card scales in;
  `prefers-reduced-motion` respected).
- JS helper in `app.js` (covers app + admin — admin/dashboard.html
  loads app.js) and a synced copy in `owner-app.js` (separate bundle).
- `role="alertdialog"`, `aria-modal`, `aria-labelledby` the title.
- **Focus: starts on Cancel** (safe default for a destructive prompt),
  Tab is trapped between the two buttons, Escape and backdrop-click
  cancel, focus is **restored to the trigger** on close.
- Destructive confirms use `btn-danger` for the confirm button,
  non-destructive (dismiss tasks, reset password) use `btn-primary`.
- Copy rewritten per dialog (title + explanatory line) instead of the
  single cramped `confirm()` string.
Verified live: open → focus on Cancel → Esc → backdrop removed → focus
restored → promise resolves false.

**State transitions: already smooth.** `.view.active` has a
`viewFadeIn` (opacity + 4px slide, 0.2s, reduced-motion-aware); the
verify popover and the three existing modals animate in via
`verifyPopoverIn`. No jarring hard-swaps found on navigation.

**Flagged, not changed:** the three existing modals
(`discrepancy-modal`, `task-detail-modal`, `export-modal`) animate the
card in but not the backdrop, and don't animate out at all. The design
pass already flagged "3 separate modal implementations, no shared
primitive" as tech debt; `confirmDialog` is the reference for how a
shared one should behave (fade backdrop + scale card, both directions).
Consolidating the existing three is a refactor for another pass, not
this QA sweep.

Status: **S2 Phase 5 done, committing.**

---

## S2 Phase 6 — Accessibility, properly

**Keyboard: the "upload and review a lease" path now works end to end
without a mouse.** The two things that broke it:

1. **Every extracted field was a `<div>` with only a click handler** —
   `role="button"` + `tabindex="0"` + Enter/Space now open the inline
   editor, and after a save the rebuilt card **returns focus to the
   value element** instead of dropping it on `<body>` (tabbing through
   the review grid was otherwise broken by every edit).
2. **The upload dropzones were `<div>`s with only a click handler** —
   a keyboard user literally could not start an upload. `uploadBox`,
   `rentRollUploadBox`, `t12UploadBox`, and the lease-detail
   `resubmitDropzone` are now `role="button"` + tab stop + Enter/Space,
   with `:focus-visible` rings.

Verified live under CDP: Tab from `<body>` → skip link → Enter →
focus on `<main>`; Tab to a field → Enter → editor opens, focus in
input → Escape → focus back on the field. Upload boxes take focus and
fire on Enter.

**Screen-reader announcements for dynamic content:**
- `#toastContainer` is `aria-live="polite"` (app + admin); each toast
  carries `role="status"`, or `role="alert"` for errors so they
  interrupt. Owner console toasts got the same `role`.
- `#appBootLoading` is `role="status"` with an `.sr-only` "Loading the
  app…" (a bare spinner announces nothing).
- All 24 `<p class="loading-inline">` view-loaders across app / admin /
  owner got `role="status"`.
- The `confirmDialog` from Phase 5 is `role="alertdialog"` +
  `aria-modal` + labelled by its title, focus-trapped, focus-restoring.

**Landmarks & skip link:**
- `.skip-link` ("Skip to content") + `.sr-only` utility added to
  `design-system.css`. Skip link on app, admin, landing, pricing;
  target `<main id="mainContent" tabindex="-1">`.
- `landmark-one-main` was failing on every non-app page. The sign-in /
  404 / owner-login gate wrappers are now `<main>`; landing & pricing
  wrap their content between `<nav>` and `<footer>` in `<main>`.
- pricing `heading-order`: the tier cards jumped h1→h3. Tier names are
  now `<h2>` (`.pricing-tier-name` unchanged visually).

**Contrast (WCAG AA, the "go beyond contrast" ask still starts with
getting contrast right):** several failures the design pass's
`--lux-accent-text` didn't reach —
- **`.btn-primary`** was white on `--lux-accent` = **3.1:1**. The
  design pass deferred this citing "non-text UI needs only 3:1" — but a
  button *label* is text and needs 4.5. Now `--lux-accent-text`
  (#8f6c3a) = 4.8:1. Same fix on **`.nav-item.active`** (identical
  white-on-brass). The accent stays #b68a4e for fills/borders/icons.
- `.footer-copy` #8b8779 → `--text-medium`.
- `.pricing-placeholder-note` amber-on-tint 3.3:1 → darker amber.
- `.eyebrow` at 12px was 4.33:1 on ivory → one step darker (#82612e).

**Lighthouse, before → after (public pages):**

| Page | Perf | A11y | Best-pr | SEO |
|---|---|---|---|---|
| Landing | 94→**99** | 94→**100** | 96→**100** | 90→**100** |
| Pricing | 97→**100** | 84→**100** | 100→**100** | 90→**100** |
| App login | 98→**99** | 92→**100** | 100→**100** | 90→**50*** |

\* login SEO drops because Phase 3 correctly added `noindex` to the
auth pages — Lighthouse counts `noindex` + no-meta-description against
the SEO score, but for a sign-in page both are the right call.

**Flagged, not done:** full keyboard navigation of the **rent-roll and
dashboard tables** — the rows are click-to-open `<tr>`s (open the lease
detail) with no keyboard equivalent, and the rent-roll cells are the
same click-to-edit `<span>` pattern the detail fields had. Making the
whole table grid keyboard-navigable (roving tabindex, or turning the
first cell into a link) is a bigger structural change than this pass;
the *review* path (detail view) is fully covered, the *rent-roll edit*
path is not. Also not done: focus-trapping the three pre-existing
modals (`discrepancy` / `task` / `export`) — same "no shared modal
primitive" tech debt noted in Phase 5.

Status: **S2 Phase 6 done, committing.**
