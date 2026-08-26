# Progress Summary

**Last updated**: Fixed the rent-roll-shaped-document upload issue
found during the verification pass below. A real 32-page portfolio
rent-roll PDF uploaded through `POST /leases` was confidently
returning WRONG values with false high confidence (a column header
word as the tenant, a portfolio's occupancy rate mislabeled as rent
escalation, one unit's rent presented as "the" lease's rent) instead
of failing cleanly -- worse than the 9 legitimately-absent fields it
also reported, since those were honest and these looked like real
data. Added `field_extractor.looks_like_rent_roll_table()`, a
structural check on raw document text (currency/date density) that
runs before extraction and rejects with a clear 422 naming the
correct tool, calibrated with a 5-16x safety margin against every
real lease fixture and a purpose-built synthetic rent-roll PDF.
Verified live: rejects the rent-roll shape, zero false positives on 9
real leases + 6 multi-format fixtures, real rent-roll import (a
separate code path) unaffected. 6 new unit tests + 4 new live checks.
Full suite: 60/60. See DECISIONS.md's "Reject rent-roll-shaped
documents..." entry for full detail.

---

Verified upload (all 6 file types) and export
(PDF/Excel) with real files and real inspected output, per explicit
instruction not to mark this done on code review alone. Uploaded a
real PDF plus the same lease saved as .xlsx/.xls/.csv/.docx/.jpg/.png/
.txt through the live /extract route -- all 6 requested formats
extracted all 15 fields correctly with real source citations, and the
5 non-PDF formats produced byte-identical values to each other
(strong proof none is silently mangling data); OCR specifically
checked at the raw Tesseract-confidence level (95.9%), not just final
field output. Generated and actually parsed back out 6 different
export files (investment memo PDF/Excel, rent-roll Excel, single-lease
summary PDF/Excel) against a real uploaded portfolio -- all correct
and complete. Found and fixed one real bug in the process: a
portfolio-wide investment memo was including EVERY discrepancy ever
recorded, including orphaned rows for since-deleted leases -- a fresh
3-lease portfolio's memo reported "19,230 flagged," contradicting its
own "3 leases covered" header. Fixed to mirror
portfolio_health_score.py's already-correct scoping logic (which had
solved this exact problem before, just never for the memo). Verified
the fix precisely (excludes stale rows, keeps real ones) and added 2
regression tests. See DECISIONS.md's "Verified upload... and export"
entry for full detail, including the actual extracted field values and
export contents.

---

Ran the requested 4-part reliability hardening pass
(error handling, performance, data integrity, security) and fixed
what it found. Two real bugs: a concurrency race in
`upsert_discrepancy`/`upsert_alert` (non-atomic check-then-insert;
two concurrent requests syncing the same natural_key -- e.g. two
people uploading the same file at once -- could 500 the loser; fixed
with atomic `INSERT ... ON CONFLICT DO UPDATE`), and a genuine O(n^2)
bug from a missing index on `leases.base_lease_id` (a 20,000-row
synthetic import went from ">2 min, still climbing" to 30.7s once
added). Two real performance bottlenecks, both N+1-shaped: 
`get_all_effective_leases()` opened up to 4 SQLite connections per
lease (fixed: one query + Python-side merge; ~1.7s -> 0.03-0.1s
across `/leases`, `/portfolio/summary`, `/portfolio/trends` at
831-lease scale), and `/portfolio/risks` + `/alerts/generate` upserted
one row per flag/candidate individually (fixed with new
`upsert_discrepancies_bulk`/`upsert_alerts_bulk`, one shared
connection per request; ~2.4-3.6s -> ~0.15-0.4s). Data integrity:
re-confirmed crash-safety (`kill -9` mid-request, twice, against the
newer bulk-import path specifically) still holds -- zero corruption,
`PRAGMA integrity_check` clean both times, no new safeguard needed.
Security: SQL injection, Q&A engine, and path traversal all audited
clean; XXE on the newer `.xlsx`/`.docx` upload paths investigated
empirically (built and uploaded real malicious files targeting a
local secret file) and confirmed already safe (openpyxl/python-docx
both disable external entity resolution); admin auth/session/CORS
re-verified live, no regression. One residual risk flagged but NOT
fixed: no decompression-size guard against a zip-bomb `.xlsx`/`.docx`
upload (plausible, not empirically confirmed). Wrote
`test_concurrency.py`, `test_performance.py`, and
`test_live_performance_api.py`, plus new checks in
`test_security_hardening.py` (concurrent-same-file-upload, XXE). Full
suite: 59/59 (was 56 before this pass's 3 new test files). See
DECISIONS.md's "Reliability hardening pass" entry for the full
writeup.

---

Tested the multi-format upload work with a real,
large (426KB, 5-property, ~5,458-row) Excel rent roll stress-test file
from the user's own machine, not just small synthetic fixtures, per
explicit instruction -- and honestly reported what actually happened,
including where quality genuinely differs from a PDF. Two very
different results depending on which endpoint the file goes to:
`POST /leases` (the multi-format work itself) correctly reads the
spreadsheet's text (confirmed separately, clean and complete in
0.65s) but then produces GARBAGE, not lower-quality data -- the
single/multi-lease boundary detector is built for a document with a
handful of discrete "Tenant:"/"Landlord:" declarations, not a 900-row
table, and ends up pattern-matching the header row itself. This is a
real, pre-existing architectural mismatch (not a defect in this
pass's work) -- exactly why `POST /leases/import-rent-roll` already
exists as a separate tool. That endpoint handled the same real file
well: 831 of 909 rows imported, 100% rent extraction (correctly
handling accounting-negative-parentheses notation), but only 58-60%
date extraction -- a real, newly-quantified pre-existing gap in
`normalize.py`'s date parser when facing the file's deliberately mixed
real-world date formats (ISO, DD-Mon-YYYY, etc.), not something small
hand-built fixtures ever exercised. Also confirmed (and disclosed)
that the rent-roll importer only reads the first sheet, so this
file's other 4 properties were never imported. Full suite re-confirmed
56/56 after this exploration (no code changed -- this was pure
testing/reporting). See DECISIONS.md's "Real-file test" entry for the
full writeup and exact numbers.

---

Before that: backend support for the new sidebar UI (Dashboard/
Health Score, Leases & Rent Rolls, Alerts, Discrepancies, Portfolio
Trends, Reports/Exports, Team Notes) -- audited every sidebar category
against the actual endpoint list before writing anything, and found 3
real gaps, not speculative ones: a portfolio-wide `GET /portfolio/
trends` (the frontend's own trends-view.js code comment already
documented the workaround it was doing instead -- fetching per-
property trends once per building and merging client-side, now
replaced with one server-side call), `GET /discrepancies/summary`
(mirroring the existing `/alerts/summary`), and `GET /comments/recent`
(a portfolio-wide feed for a standalone Team Notes tab, joining
lease and discrepancy comments in one query). Also added response
caching (new `app/cache.py`, a plain in-process dict -- no new
dependency) for the two genuinely expensive, repeatedly-hit
computations named in the request: the health score and portfolio
trends, with real invalidation wired into every lease/discrepancy
mutation route plus a 60s TTL safety net. Building this caught a real
test-isolation bug (fixed at the root: `database.configure()` now
clears the cache) before it could hide anything. Full suite 56/56
including live tests -- see DECISIONS.md's "Backend support for the
new sidebar UI" entry for the full writeup.

---

Before that: the lease upload system now accepts any file format
a real rent roll or lease might come in, not just PDF: Excel (.xlsx/
.xls/.xlsm), CSV/TSV, Word (.docx/.doc), images (.jpg/.png/.tiff, via
the same OCR pipeline scanned PDFs already use), and plain text. Every
format converts to the exact same page-text shape PDF extraction
already produced, so it feeds the identical downstream extraction/
confidence/citation pipeline with zero format-specific logic anywhere
past the new `app/document_extractor.py` dispatcher -- confirmed
directly: every format extracts the IDENTICAL field values from
matching real fixture files, not just "looks right per format."

Tested end to end with real files in every format, per explicit
instruction, both as direct pipeline calls (22 tests) and as real
`POST /leases` uploads against the actually-running dev server (49
checks, including a real mixed-format batch upload and real corrupted/
empty/unsupported-file error responses over HTTP) -- the `.doc` fixture
is a genuine binary Word file (macOS's own `textutil`, not a fake).
Found and fixed one real bug before shipping: joining Excel/CSV cells
with `" | "` broke the extractor's label-style matching outright (4 of
9 fields came back missing) and leaked a stray `"| "` into one field's
value -- switched to a plain-space join, which reads as the same
natural "Label: Value" prose the patterns already expect. Frontend
upload UI (`accept=` attributes, drag-drop messaging, client-side file
filter) updated to match. Full suite 54/54 including live tests. See
DECISIONS.md's "Multi-format upload support" entry for the full
writeup.

---

Before that: sidebar navigation interaction polish -- frontend-
only, no backend involved. Three things asked for: (1) instant view
switching with a subtle fade/slide instead of a hard snap, the sidebar
itself never re-rendering, and a clear always-visible active indicator;
(2) the flat 9-item nav list grouped into three labeled sections
(Overview / Leases / Insights) with small uppercase headings; (3) a
collapse/expand toggle (icon-only, ~76px) with a smooth width
transition, state persisted in `localStorage`, and hover tooltips in
collapsed mode.

The tooltips are JS-positioned (`showSidebarTooltip` in `app.js`), not
a pure-CSS `::after` -- `.sidebar` needs `overflow:hidden` for the
width-collapse animation not to show a scrollbar mid-transition, which
would also clip a CSS tooltip trying to escape past the sidebar's own
right edge. A `position:fixed` tooltip appended to `<body>` and
positioned from the trigger's real `getBoundingClientRect()` sidesteps
that entirely.

Verified live: every one of the 9 views clicked through individually
(exactly one active nav button + one active view after each, checked
programmatically, not just eyeballed), then 6 rapid back-and-forth
clicks between two views with no stale double-active state; collapse
→ hover-tooltip → expand; collapse state surviving a full page reload.

**A real bug, caught only by testing at a narrower width, not assumed
fixed from reading the CSS**: this app already had a `@media (max-width:
768px)` rule turning the sidebar into a horizontal wrapped top bar,
written for the OLD flat structure where every nav button was a direct
child of `.sidebar`. The new grouping wrapped buttons inside
`.nav-scroll > .nav-group` divs, which that pre-existing rule knew
nothing about -- at 640px the middle of the sidebar was blank, most nav
items simply not there. Fixed with `display: contents` on the two new
wrapper levels at that breakpoint, unwrapping them back to a flat
button list matching what the mobile rule originally expected, plus
forcing labels visible and hiding the (meaningless in a horizontal bar)
collapse toggle there. Re-verified at 640px, 500px, and 375px, and the
edge case of collapsing at desktop width then shrinking to mobile width
(labels correctly reappear; expanding back to desktop width correctly
restores the collapsed preference rather than losing it).

See DECISIONS.md for the full writeup.

---

Before that: Frontend for three more backend features shipped
this session, each built and live-verified in a real browser right
after finding its endpoint via `git log` (a parallel backend session
kept shipping mid-turn, twice landing while this pass was mid-build on
the very feature it added):

1. **Alerts** (`alerts-view.js`): a bell-icon nav item ("Alerts") with
   an unread-style badge (active-alert count, capped "99+"), and a
   dedicated feed with a by-severity summary strip (click a tile to
   filter to it), status/severity/type filters, and per-alert Dismiss.
   Calls `POST /alerts/generate` itself on app boot and every visit --
   no scheduled backend job exists yet, so this is what keeps the
   badge/feed current. "Unread" maps onto the backend's real `active`
   status (no separate read/unread flag exists); dismissing IS marking
   read, a real attributed `POST /alerts/<id>/dismiss` call, not a
   client-only flag. Alerts with a `lease_id` link straight to that
   lease.

   Live-testing against the shared dev database's real accumulated
   history surfaced 357 active alerts, most `new_discrepancy` alerts
   for discrepancies whose leases had since been deleted -- exactly the
   "343 discrepancy rows silently corrupted by a schema bug" the very
   next backend commit (Portfolio Health Score) found and fixed. That
   fix updated the health score's own discrepancy-counting to exclude
   orphaned rows, but not `alerts.py`'s `_detect_new_discrepancy_alerts`
   (unchanged in that commit) -- so the Alerts feed can likely still
   surface a `new_discrepancy` alert per orphaned row. Flagged here as a
   probable remaining backend gap, not fixed (not this pass's file to
   touch); the by-severity summary strip was added specifically because
   this real-data volume would otherwise fail this feature's own "not a
   raw log dump" bar.

2. **Investment memo export** (`export-modal.js`): an "Export Report"
   button on the Dashboard (whole-portfolio scope) and Lease Detail
   (scoped to that lease's `property_address`), opening an options
   screen -- format (PDF/Excel), and for a property-scoped export, an
   optional fresh-T12 attachment. No section-level include/exclude
   exists on the backend, so the screen states what's included as plain
   text rather than decorative checkboxes that wouldn't do anything.
   Real loading state, then a success screen naming the downloaded file.

   A real bug caught by testing the actual download, not just that the
   button didn't error: `Content-Disposition` isn't readable from the
   fetch `Response` cross-origin (the backend's CORS config doesn't
   list it in `Access-Control-Expose-Headers`), so the real filename
   silently came back `null` every time. Fixed by building the same
   scope-labeled, sanitized filename client-side instead of depending
   on an unreadable header -- verified with a screenshot showing the
   real address-derived filename. Also verified outside the browser
   entirely: fetched both formats directly, opened the PDF with PyPDF2
   (2 real pages, readable text) and the Excel file with openpyxl (5
   real sheets) -- confirms the files genuinely open, not just that
   they're correctly-typed blobs.

3. **Portfolio Health Score**: a hero card at the very top of the
   Dashboard -- above the confidence panel, above everything -- with a
   hand-rolled SVG ring gauge (score, rating, colored by band reusing
   the existing confidence green/amber/red tokens) and an expandable
   breakdown of all four components, sorted by how much each is
   actually dragging the score down (`(100-score)*weight`) rather than
   a fixed order, so the real biggest driver reads first. Each
   component gets a plain-language detail line and, below 80, a
   concrete suggestion -- the Unresolved Discrepancies one links
   straight into the new Alerts feed. Tested against three real
   portfolio states (empty -- a "No Data" empty state, not a 0/100;
   and populated at both 87.3 and 74, the latter showing all four
   components including the color-coded score chips) by actually
   changing the database between screenshots, not by editing the
   response in devtools.

See DECISIONS.md's entries for all three for the full writeup.

---

Before that: Portfolio Health Score, backend-only. `GET
/portfolio/health-score` returns a single, defensible 0-100 number
(plus a letter rating) for how much a user can trust their portfolio's
data right now -- a weighted formula across confidence distribution,
source verification completeness, unresolved discrepancies, and data
freshness, fully documented in `app/portfolio_health_score.py`'s
module docstring. Deliberately distinct from the existing `/portfolio/
health` dashboard strip (that one answers "what needs attention
today"; this one answers "how much can I trust the data itself").
Tested against genuinely different portfolio states (a real perfect
one, a real messy one, a real 50/50 mixed one), per explicit
instruction.

That live testing surfaced three real, serious bugs, one of them
significant enough to warrant its own writeup here: this project's
real dev database had been running with a live, silently-corrupting
schema bug for the entire rest of this session. Item 2 (discrepancy
resolution) deliberately removed the foreign key on `discrepancies.
lease_id` earlier this session specifically so a discrepancy would
survive its lease being deleted -- but `CREATE TABLE IF NOT EXISTS`
never retroactively fixes an already-existing table, so the real dev
database kept the OLD `ON DELETE SET NULL` constraint the whole time,
silently nulling out 343 real discrepancy rows' `lease_id` every time
a referenced lease was deleted -- discarding exactly the information a
permanent record exists to keep. Fixed with a real migration
(`database._migrate_discrepancies_table_drop_lease_fk`, SQLite's
standard rename/recreate/copy/drop table-rebuild dance, since SQLite
has no `DROP CONSTRAINT`) that runs safely and idempotently on every
`init_db()`. Two further bugs in the health score's own discrepancy-
counting logic (both downstream of the same "discrepancies
permanently outlive their lease" design) were also found and fixed:
discrepancies tied to since-deleted leases, and discrepancies about
tenant names/addresses that no longer appear anywhere in the current
portfolio, were both being counted forever instead of only while still
relevant -- together these had made the health score's discrepancy
component nearly meaningless in any long-lived database (351
accumulated open discrepancies were dragging down what should have
been a genuinely healthy, brand-new test portfolio). Full suite 52/52
including live tests. See DECISIONS.md's "Portfolio Health Score"
entry for the full writeup, including the exact debugging trail.

---

Before that: investment memo export, backend-only. `POST
/portfolio/investment-memo.pdf` and `.xlsx` generate a professional,
attachment-ready export (per property or whole portfolio) with key
lease terms, flagged discrepancies AND their resolutions, a T12
cross-check summary, and a rollover risk summary -- meant to actually
be forwarded to a lender or investment committee, not opened only
inside the app. Reuses `summary_memo.py`'s existing PDF style/
building-block machinery and the "one shared computation, multiple
export formats" convention `rent_roll_export.py` already established,
so the PDF and Excel outputs can never disagree with each other.

Per explicit instruction, a real sample was generated and reviewed
critically before calling this done -- and that review caught a real,
serious bug, not a hypothetical one: a unit with both a real PDF lease
and a rent-roll cross-check snapshot on file (the exact scenario
rent-roll reconciliation exists to catch) was double-counted in every
summed figure -- total rent, WALT, the rollover schedule, and the T12
cross-check all overstated. A genuinely healthy property (2.7% real
T12 variance) rendered as "FLAGGED — MATERIAL DISCREPANCY" at a
fabricated 30.2% gap purely from the double-count. Fixed with a
dedup step that prefers the real lease document over a rent-roll
snapshot for every summed number, while still listing both records
(clearly labeled by source) in the Key Lease Terms section so nothing
is silently hidden. A sample PDF/Excel pair (generated after the fix)
was sent directly to you to look at. Full suite 50/50 including live
tests. See DECISIONS.md's "Investment memo export" entry for the full
writeup.

---

Before that: a proactive alerting system, backend-only (frontend
not built yet for this one), on top of the four-item acquisitions-
infrastructure batch below. `POST /alerts/generate` scans the current
portfolio for four situations and persists a record of each: upcoming
lease expirations (30/60/90 days, reusing the existing
`compute_expiration_alerts` bucketing), newly detected discrepancies
(reusing Item 2's discrepancies table below -- one alert per
currently-open discrepancy), rent significantly below this portfolio's
own internal market proxy (reusing `compute_loss_to_lease`), and a
single tenant crossing 25% of portfolio rent (reusing
`compute_tenant_concentration`'s existing threshold constant). Each
alert has a severity, a plain-English message explaining what's wrong
and why it matters, and a stable identity so it survives being
recomputed -- an alert can be dismissed by a person (permanent, never
silently un-dismissed by recomputation) or auto-resolved by the system
itself when the underlying condition genuinely clears (a materially
different, separately-tracked situation). `GET /alerts`,
`GET /alerts/<id>`, `GET /alerts/summary` (a digest for a future
notification feed or email digest), and `POST /alerts/<id>/dismiss`
round out the API. Email delivery is explicitly NOT built yet --
generation and storage only, per the request.

A real design bug was found and fixed before shipping, caught by the
"no alerts on a healthy portfolio" edge case the request explicitly
asked for: alerting at both the 25% AND 15% tenant-concentration
thresholds made a healthy, evenly-diversified 5-tenant portfolio (20%
each) alert on every single tenant. Fixed to alert only at 25%,
matching the concrete threshold the request itself named. Full suite
48/48 including live tests. See DECISIONS.md's "Proactive alerting
system" entry for the full writeup.

---

Before that: the frontend half of the same four-item acquisitions-
infrastructure batch (see the entry below) — built directly against the
real backend endpoints that batch shipped, not the localStorage
stopgaps this pass started with before that backend work landed mid-
session. All four verified live in a real browser (headless Chrome +
a hand-rolled CDP client, screenshotted and interacted with, not just
asserted):

1. **Click-to-verify audit trail**: a new reusable popover
   (`verify-popover.js`) makes every number that previously had NO
   visible source — portfolio dashboard tiles, the Rent Roll rollup
   table, the Comparison table, the T12 cross-check panel — click-to-
   verify. Portfolio aggregates open a breakdown of the contributing
   leases (drawn from already-loaded lease data, no extra fetch);
   single-cell numbers open the field's own citation directly. The
   Lease Detail view's existing always-visible inline citation was
   deliberately left alone — it already satisfies CLAUDE.md's "every
   extracted field must show its source" bar without requiring a
   click, which is strictly better than gating it behind one.
2. **One-click discrepancy resolution**: a new modal
   (`discrepancy-modal.js`) shows both conflicting values side by side
   with their real sources, lets a reviewer pick which is correct, and
   requires a name + note. Wired to the real
   `POST /discrepancies/<id>/resolve`/`/reopen` endpoints the backend
   batch below added — this pass started by building a localStorage-
   only stopgap (no persistence endpoint existed yet when work began),
   then fully rewired it to the real API the moment that endpoint
   landed, including the discrepancy's own "Discussion" comment thread.
   Covers both rent-roll-vs-lease-PDF mismatches (Dashboard) and
   rent-roll-vs-T12 mismatches (Upload view) — same modal, generalized.
3. **Portfolio Trends** (new nav item + view, `trends-view.js`):
   forward-looking Rollover Risk Timeline (real `/portfolio/rollover`
   data, or recomputed client-side for a single selected property,
   since that endpoint has no per-property filter), plus real Rent
   Growth Over Time and historical Lease Expirations/Tenant Turnover —
   both built on the new `/portfolio/property-trends` endpoint below.
   That endpoint is scoped to one building; "All Properties" merges one
   response per distinct building client-side (no portfolio-wide
   version exists). Charts are hand-rolled inline SVG, matching this
   app's zero-JS-dependency approach — a deliberate choice confirmed
   with the user rather than introducing the project's first charting
   library.
4. **Team Notes** (`comments.js`, a shared widget): a threaded,
   attributed comment box on the Lease Detail sidebar and inside the
   Discrepancy modal, wired to the real comments endpoints below. One
   shared self-reported identity (`getUserIdentity`/`setUserIdentity`
   in `app.js`) is now cached across discrepancy resolution AND
   comments, replacing an earlier per-feature localStorage key —
   "who you are" shouldn't need retyping per feature.

Two real bugs caught during live-browser verification, not just
unit-test-clean: (1) a stale-cache trap in the CDP test harness itself
— headless Chrome kept serving an old cached `detail-view.js` across
navigations within the same profile, making a real method
(`LeaseDetail.loadComments`) look undefined; fixed by disabling the
network cache in the test client, not by touching app code. (2) a
real CSS bug: the turnover summary line rendered as "0tenant turnover
events..." with no space — `.trends-legend-line`'s leftover
`display:flex` (from an earlier version of that line that used colored
swatches) was collapsing the whitespace between a `<strong>` tag and
the text after it, a well-known flex-layout quirk. Fixed by dropping
the flex layout now that the line is just text.

**Backend coordination note**: this pass ran in parallel with a backend
session building the exact same four-item batch (confirmed by the user
in advance) — the git history shows their four commits landing mid-
session, each of which this pass immediately re-verified against and
rewired to, rather than shipping a frontend-only approximation and
leaving the integration for later. No backend files were touched by
this pass.

---

Before that: Four new backend infrastructure systems shipped this
pass, aimed at moving the product from "useful" to something an
acquisitions team can't work without -- built, tested, and live-
verified sequentially, one milestone/commit per item:

1. **Full audit trail**: verified the "value has a source" invariant
   actually holds across every real extraction pathway (203 sourced
   fields checked across 15 real PDF/rent-roll fixtures), and added
   `GET /leases/<id>/fields/<field_name>/source` -- the full source
   chain for one data point, including which document (base lease or
   which amendment) currently governs its effective value, plus the
   complete history of every value that field has ever held.
2. **Discrepancy resolution system**: every computed discrepancy
   (single-lease risk flags, cross-lease mismatches, rent-roll-vs-
   lease-PDF and rent-roll-vs-T12 reconciliation) now gets a stable,
   persisted identity so a resolution survives being recomputed.
   `POST /discrepancies/<id>/resolve` (who/when/why, permanently
   logged, never overwritten) and `/reopen`; existing risk/
   reconciliation endpoints now merge resolution status directly in,
   so a resolved discrepancy never needs a manual re-read.
3. **Portfolio history & trends**: `GET /portfolio/property-trends`
   turns this project's already-permanent, append-only upload history
   into real trend queries per property -- rent growth (distinguishing
   same-tenant escalation from turnover rent resets), tenant turnover
   events, and a historical rollover pattern (which months/years this
   building's expirations have clustered in).
4. **Collaboration layer**: `GET`/`POST /leases/<id>/comments` and
   `/discrepancies/<id>/comments` -- timestamped, author-attributed
   team notes, visible to everyone (this app has no per-account data
   scoping yet, so that's already true by construction).

No real per-user account system exists in this app yet (only a single
admin login + a self-reported-email access gate) -- confirmed directly
with the user rather than guessed: resolutions/comments are attributed
via a free-text name/email the caller supplies, trusted as-is, same
convention the existing access gate already uses. Backend-only, as
scoped; a concurrent session was independently building frontend
pieces (a discrepancy-resolution modal, a "verify" popover, a trends
view) while this batch was in progress. See DECISIONS.md's
"Acquisitions-grade infrastructure" entry (and its four item
sub-entries) for the full design writeup, including two real bugs
found and fixed along the way: a foreign-key crash when resolving a
discrepancy whose lease had since been deleted, and a same-category/
field natural-key collision between two different risk checks.
Full suite 46/46 including live tests.

---

Before that: the T12 cross-check now has a real dashboard UI, closing
the "ships API-only for now" gap from when it first shipped. New "Cross-Check
Against a T12" section on the Upload view, parallel to the existing Import
Rent Roll section — upload a T12 + property address, get an inline result
(no lease list, since nothing is created). Reused existing CSS classes
throughout (`.health-strip`/`.health-metric` for the figures,
`.severity-badge` for the agree/flagged status) rather than inventing new
ones, applying the lesson from the earlier composition-panel work this same
session. All 4 states — validation error, no matching leases, agreement,
flagged discrepancy — verified live in a real browser via CDP screenshots,
using the same real end-to-end scenario (a real rent roll import + a real T12
upload) the backend's own live test already covers. See DECISIONS.md's "T12
dashboard UI panel" entry for the full write-up.

Before that: PMS rent roll import now covers all five originally-named
platforms — RealPage, MRI, and Buildium added alongside Yardi/AppFolio, using
the same synthetic-fixture approach (no real vendor files available; user
explicitly chose synthetic over waiting). Mostly extended already-built,
platform-agnostic machinery (header-row detection, per-row Property column)
with a few new terminology aliases (RealPage's "Actual Rent," a bare MRI-
style "Commence" column that the existing longer aliases couldn't match at
all). The more important find: building fixtures for these specific
platforms surfaced a real, previously-latent bug in the ORIGINAL importer —
"Rent PSF" (a common RealPage/MRI column, a per-square-foot RATE, not the
tenant's total rent) could get silently used as if it were the tenant's
actual dollar rent when no better column existed, via the bare "rent" alias
that's been there since the very first version of this feature. Fixed with
the same denylist pattern already used for "Market Rent." Verified live
against the real running server both before and after that fix (restarted
each time). Full suite 38/38. See DECISIONS.md's "PMS-specific rent roll
import: RealPage, MRI, and Buildium" entry for the full write-up.

Before that: the rent-roll-vs-T12 cross-check went live — a genuinely new
document type and parsing module (`t12_import.py`, a T12 is one row per LINE
ITEM with months as columns, not one row per tenant like a rent roll),
deliberately scoped to extracting exactly one number (actual annual rental
income), not a full P&L pipeline nobody asked for. The design decision that
actually mattered: never confusing a T12's "Gross Potential Rent" (theoretical,
vacancy-inclusive) with its actual "Rental Income" line — using potential rent
would make a healthy property look short by definition. A real logic bug (a
documented "Scheduled Rent Income" denylist exception that was never actually
implemented) was caught by the test suite itself before shipping. Verified
end-to-end against the real running server: real rent roll import, real T12
upload, real cross-check, confirmed nothing persisted. Ships API-only for now
(`POST /portfolio/t12-reconciliation`) — a dashboard panel is next. See
DECISIONS.md's "Rent-roll-vs-T12 cross-check" entry for the full write-up.

Before that: Yardi and AppFolio rent roll import went live the same way (see
DECISIONS.md's "PMS-specific rent roll import: Yardi and AppFolio" entry) —
auto-detecting a canned report's real header row past its decorative title/
date block, a per-row Property column for portfolio-wide multi-property
exports, PMS terminology (Resident, Lease From/To, Scheduled Rent), and a
denylist so "Market Rent" is never mistaken for actual rent. Two real
accuracy bugs caught during self-review before shipping (a "Property
Manager" column would have been mistaken for the building address; blank
spacer rows in a decorative header block were silently shifting citation row
numbers). RealPage/MRI/Buildium remain "Coming soon" — not specifically
tested, per this whole batch's standing rule against guessing at formats.

Before that: 5 of the Platform page's original "Coming soon" items (6
underlying pieces of work) are now genuinely working, tested, and live: tenant
concentration analysis (Herfindahl-Hirschman Index), WALT + a year-by-year
rollover schedule, loss-to-lease (portfolio-internal comp, since there's no
external market-rent data source), rent roll import for broker-built Excel/CSV
files (no fixed column format required, plus a real upload UI), and cross-
checking an imported rent roll against actual lease PDFs on file, flagging
tenant/rent/expiration-date disagreements. Each shipped with new API
endpoints, full test coverage, and updated Platform page copy. See
DECISIONS.md's "Platform 'Coming soon' features" entries for the full
per-feature write-ups, including at least one real bug each pass caught via
adversarial/messy-data testing that clean unit tests alone missed.

On top of that: all four of the pure-computation features (everything above
except rent roll import itself) now also have a real dashboard surface —
previously they were API-only, reachable only by hitting the endpoint
directly. A new "Portfolio Composition & Risk" panel on the main dashboard
shows all four, each with its own populated and empty states. Building it
surfaced a genuine bug in the rent roll importer itself (not the dashboard
code): a Unit/Suite column whose cell already spelled out its own designator
(e.g. a cell literally reading "Suite 101") got double-prefixed into "Suite
Suite 101", which silently broke address matching for the reconciliation
feature above — found via live messy-data testing, not a hypothetical, fixed,
and covered by a new regression test. Live-verified in a real browser,
including clicking through the reconciliation panel's empty-state "import
one" link to confirm it actually navigates (that exact click-handler bug is
also documented in DECISIONS.md).

That first round of live-browser verification, on its own self-review pass,
turned out to have a real gap: the test data it used for the Suite-fix
happened to take a code path that looks identical whether the fix is present
or not, and separately, the local dev backend had gone stale *again*
(restarted, unrelated to this fix, before the fix was actually saved to
disk) without that being noticed. Closed by building a new automated live-
HTTP regression suite, `test_live_composition_api.py`, covering all 5
endpoints in this batch end-to-end against the real running server — it
immediately caught the stale server for real. Backend restarted again,
re-verified, and now genuinely confirmed fixed. This test suite is
registered permanently in `run_all_tests.py --live`, so this exact class of
"code is right, but did anyone restart the server" regression gets caught by
running the suite going forward, not by luck. Full suite including live
tests: 33/33. See DECISIONS.md's "Dashboard UI for the 4 new portfolio
metrics" entry (and its addendum) for the full write-up.

**Still open**: nothing from the original Platform "Coming soon" list —
every item has shipped, tested, and (where synthetic fixtures were used)
clearly labeled as such. Real vendor sample files (rent roll exports or a
T12), whenever available, are still preferred over synthetic ones and
should replace them.

Before that: the admin login page (`/admin/`) no longer has any
session-based bypass of the credentials form — it used to show a
"you're already signed in, Continue?" shortcut for a valid session;
that's gone, the form always renders, unconditionally, on every visit.
Verified live end to end without ever touching the real admin password:
every rejection path (unknown email, wrong password, empty password —
client- and server-side), the form-always-shows behavior with both no
session and a valid one, full session lifecycle (persistence, logout,
post-logout dashboard access correctly blocked), and finally the real
success path confirmed directly by the user with their real
credentials. Normal session persistence for direct dashboard access
(bookmarked URL, valid session) is unchanged by design — this was
specifically about the login page itself never skipping its own form.
See DECISIONS.md's "Login page: no session-based bypass" entry.

Also this pass: the product is rebranded from "Lumen Lease" to
"Abstractly" everywhere (nav, page titles, emails, PDF footer — a
repo-wide grep confirms zero remaining references, re-verified live in
a cache-disabled browser navigation after an initial report turned out
to be browser cache, not a real gap). The landing page is confirmed
intact and serving correctly as the actual homepage (it was never
actually removed — see DECISIONS.md), with the nav's "Client Login"
link now pointing at `/admin/` instead of `/app/`, per explicit choice.
Real email delivery is back on (fresh App Password, one confirmed live
send) after the incident below was fully resolved and re-verified. See
DECISIONS.md's "Rebrand" and "Landing page: restoring it as the actual
homepage" entries.

Before that: **email sending was temporarily disabled** after a
test-suite bug caused a real email storm to the admin inbox (thousands
of real sends, triggered by pre-existing test files that called
`POST /waitlist` with fixture data and never mocked email, combined
with real credentials being configured for the first time). Root cause
fully diagnosed and fixed in two independent layers — the test files
can no longer send real email regardless of what's in `.env`
(empirically verified under a worst-case simulation, not just
re-read), and `email_service.py` enforces a hard per-recipient rate
limit as a backstop against any future misfire, alongside a separate
route-level rate limiter in `api.py`. Full test suite (21/21) passing.
See DECISIONS.md's "Incident: real email storm from the test suite"
entry (and its addendum) for the full write-up.

Before the incident: real Gmail SMTP delivery sent an admin
notification email (to ADMIN_EMAIL) on every new "Request Access"
submission, alongside the existing requester confirmation email —
confirmed with a real send, not just mocked SMTP. Also fixed a top-nav
layout bug: a dead zone roughly 900–1040px wide where nav links wrapped
mid-phrase instead of either fitting on one row or hitting the mobile
layout. See DECISIONS.md's "Real email delivery" and "Landing page top
nav" entries for the full write-up.

Before that: a real admin login (email + bcrypt password, signed-
cookie session, checked server-side on every request) now protects the
admin dashboard (access-request approve/deny, uploaded-leases
overview) at `/admin/`, replacing the previously-unauthenticated
`/admin/waitlist/` panel. This directly closes the "the admin waitlist
approval route MUST require real authentication" blocker called out in
the Session 14 pre-sale audit below — that finding is no longer
current. See DECISIONS.md's "Admin login and dashboard" entry for the
full design (why env-var credentials instead of a users table, the
timing-safe wrong-email-vs-wrong-password check, why the cross-origin
session cookie needed `SameSite=None; Secure`, and what's still
deliberately public vs. now gated).

Since Session 14, several other passes also shipped (portfolio rent
roll rollup + 30/60/90-day expiration alerts, bulk actions, reliability
hardening, a "rent roll AI" landing-page repositioning + pricing page,
confidence/validation scoring with cross-lease mismatch detection, a
decision-ready PDF summary memo, and a monthly portfolio report) — see
DECISIONS.md for each; this summary focuses on the admin-auth
milestone specifically since it's the most recent and closes a
previously-flagged real gap.

**Restart commands** (unchanged): `cd backend && source venv/bin/activate && python run.py` and `cd frontend && python3 -m http.server 8000`.

---

## Real email delivery + top nav fix

**Email**: `POST /waitlist` now sends two real emails via Gmail SMTP —
the existing confirmation to the requester, and a new notification to
`ADMIN_EMAIL` so the admin actually finds out without keeping the
dashboard open. Both are best-effort (a signup never fails because an
email didn't send) and both are now configured with real credentials
in `backend/.env` (`EMAIL_USER` + a Gmail App Password) and confirmed
working with a real send to timmypisano24@gmail.com. No email exists
yet for "lease finished processing" — that wasn't already built, so it
wasn't added (was explicitly conditional in the request).

**Nav**: the top nav's link spacing itself was already a uniform 32px
at normal widths — the real bug was a dead zone (~900–1040px viewport
width) where the nav neither fit on one row nor had hit the mobile
breakpoint yet, so links wrapped mid-phrase ("Trust & Security"
splitting across two lines). Fixed with `white-space: nowrap` on every
nav link/the wordmark, plus giving the nav its own, wider breakpoint
(1040px) split out from the page's general 860px mobile breakpoint.
Verified across the full width range with a real (CDP-controlled, not
headless) Chrome.

---

## Admin login and dashboard

Real authentication for the internal admin surface — see DECISIONS.md
for the full write-up. In short: `/admin/` is now a login page
(email + password, generic "Invalid email or password" on failure,
never revealing which field was wrong), backing a session-
authenticated dashboard at `/admin/dashboard.html` showing pending
access requests (approve/deny) and every uploaded lease/rent roll with
a basic status (Verified / N Flagged / Doesn't Look Like A Lease,
reusing the confidence-summary and `looks_like_lease` work from
earlier this session — no new computation needed there).

**Setup required before this works**: `ADMIN_PASSWORD_HASH` isn't set
yet in `backend/.env` — run `cd backend && venv/bin/python3
set_admin_password.py` and follow the prompt (see the chat for the
full walkthrough). `ADMIN_EMAIL` is already set to
timmypisano24@gmail.com. `FLASK_SECRET_KEY` is already set to a real
generated value so sessions survive a backend restart.

---

## Session 14: Pre-sale technical audit — honest sale-readiness assessment

Full findings and technical detail for every part are in
`DECISIONS.md` ("Session 10: Pre-sale technical audit, Parts 1–4").
This is the direct, no-spin summary the audit itself asked for.

### What's genuinely production-ready right now

- **Extraction pipeline**: 15 fields extracted with a source citation
  (page number + quote) and a confidence level on every field — a
  human can verify each value against the document, not just trust a
  black box. This is a real, demonstrated differentiator, not
  marketing copy.
- **Test suite**: 23/23 test files passing, covering every route,
  every extracted field, every export path, and the edge cases that
  matter (empty PDF, corrupted PDF, huge 35-page PDF, non-English
  text, scanned/image-only PDF via real OCR, multi-lease PDFs across
  4 structurally different document shapes).
- **Data storage**: real file-backed SQLite, empirically verified to
  survive a hard `kill -9` crash-and-restart and 5 simultaneous
  concurrent uploads with zero data loss.
- **Exports**: Excel and Google Sheets export logic verified
  cell-by-cell against the app's own extracted data — no rounding
  drift, no mismatched rows, missing fields render as true blanks
  rather than leaking "None" into exported files.
- **Error handling**: every API call, file operation, and external
  service call (OCR, email, Google Sheets) fails with a clear,
  human-readable message — never a raw stack trace or error code
  reaches the user. Verified live, not just by code review.
- **Code hygiene**: no leftover debug/console statements, no
  unresolved TODOs, no hardcoded config that should be an environment
  variable, no secrets anywhere in the codebase or git history
  (checked content, not just filenames).
- **Frontend polish**: consistent design system, responsive at both
  laptop and tablet widths, real "how it works" flow, no dead links or
  placeholder/lorem-ipsum content anywhere.

### What works but has known limitations a company would ask about

- **Google Sheets export** requires a one-time Google Cloud
  service-account setup that hasn't been done yet (needs the user's
  credentials — same open item as prior sessions). The code path is
  fully tested and fails cleanly (502, clear message) until it's
  configured.
- **OCR fallback** (tesseract + poppler) works and is verified against
  real scanned PDFs, but depends on those binaries being installed and
  on `PATH` on whatever machine runs the backend — not bundled or
  containerized. Needs setup documentation before deploying anywhere
  new.
- **Extraction is pattern/regex-based, not ML-based.** It's now been
  tested against several deliberately varied real-world document
  structures (including the Lessor/Lessee bug this session found and
  fixed) and handles them correctly, but a sufficiently unusual lease
  format could still miss a field — which is exactly what the
  source-citation-on-every-field design is for: a human always has
  what they need to catch it, nothing is silently guessed.
- **Python 3.9**, which is past end-of-life — `google-auth` already
  emits an end-of-life warning on every run. Still fully functional
  today, but accumulating risk without a maintained runtime.
- **No deployment configuration exists** (no Dockerfile, no Procfile,
  no CI/CD) — the app has only ever run locally during development.

### Actual blockers if this were sold to a company today

1. **No real authentication or authorization exists.** The current
   "access gate" is a waitlist-approval flow, not per-user login —
   there is no account concept, no session, and no per-company data
   scoping. Every approved user currently sees the exact same shared
   pool of leases. This alone blocks selling to more than one company.
2. **The admin waitlist route has zero authentication, confirmed live
   this session**: `curl http://localhost:5000/waitlist` with no
   credentials returns every prospective customer's email and can
   approve/grant access to anyone who finds the URL. This is a real,
   currently-exploitable gap, not a hypothetical one, and was already
   flagged (not newly discovered) in the code's own comments as
   needing real auth before going live.
3. **No rate limiting anywhere** — the CPU/OCR-heavy upload endpoints
   and the unauthenticated waitlist routes can both be hit in a tight
   loop by anyone.
4. **No data backup or disaster-recovery strategy.** Storage survives
   a process crash, but there is no backup of the SQLite database file
   itself — losing the disk, migrating hosts, or an accidental file
   deletion loses every customer's lease data permanently. There is
   also no hosting plan yet at all.
5. **Running on Flask's built-in development server**, which Flask's
   own documentation states plainly is not fit for production traffic
   (no real concurrency or hardening).

### Overall recommendation

**Ready to demo, not ready to pilot.** The extraction quality, the
source-citation trust UX, and the visual polish are genuinely strong
and will land well in a live demo run locally. But the missing
authentication/data-scoping and the currently-open admin route aren't
polish items — they're prerequisites for letting a real company's real
lease data anywhere near this app. Recommend demoing now to validate
interest, but treating real auth, multi-tenant data scoping, and a
backup/hosting plan as required — not optional — before any company
actually pilots this with their own documents.

### Restart commands

```
cd backend && source venv/bin/activate && python run.py
cd frontend && python3 -m http.server 8000
```

---

## Session 13: Trust-and-polish pass — landing page, reliability, data confidence, visual QA

**Honest status up front**: all 4 requested parts are done, committed
separately (4 commits), and verified against the real running app.
This pass found and fixed 5 real bugs that were sitting in the app
before it started, not hypothetical risks — worth listing plainly
since the whole point of this pass was surfacing exactly this kind of
thing before a demo:

1. **Landing page nav had near-zero contrast** (Part 4) — the entire
   top nav (brand name + 4 links) was rendering nearly invisible
   because its text used colors meant for sitting over the dark hero,
   but the nav actually sits in normal document flow above the hero,
   against the page's own ivory background. Pre-existing, not
   introduced this session — caught only because this pass actually
   screenshotted and looked closely at that specific region. Fixed.
2. **A real error-message leak** (Part 2) — `err.message || "friendly
   fallback"` doesn't work when `err.message` is a raw, non-empty
   technical string (a real network failure throws with exactly that).
   The literal string `"fetch failed"` could reach a user's screen on
   the landing page's request-access form, the app's own gate, and the
   admin panel. Fixed at the source in every affected file.
3. **A blank-page moment on first load** (Part 2) — nothing was shown
   while the gate's initial `/config` check was in flight. Added a
   default-visible loading spinner so there's no gap.
4. **The lease detail action buttons could get clipped at tablet
   width** (Part 4) — missing `flex-wrap` on a 4-button row.
5. **The Excel/CSV rent-roll export was missing 4 of 15 fields**
   (found and fixed in a prior session, restated here since it's the
   same category of "looked complete, wasn't" issue).

### Part 1: First-impression trust signals

Fixed a real page-load risk (Google Fonts loaded via chained CSS
`@import`, which delays font discovery past what the browser's preload
scanner sees during initial parse and risks a visible reflow on the
hero's headline) by switching to `<link rel="preconnect">` + one
combined font request in all three HTML entry points. Added a 3-step
"How It Works" section (upload → extract → review/export) that didn't
exist before. Removed the footer's placeholder Privacy/Terms/About
links (already self-documented as dead links) rather than leaving them
clickable to nowhere. Verified zero console errors and zero visible
broken links across landing load, waitlist submission, gate sign-in,
request-access → pending, and the admin page.

### Part 2: Reliability polish + full new-user flow

Fixed the error-message and blank-load issues above. Then verified the
complete new-user journey in one live run against the real app: land
on the landing page → request access → visit `/app/` before approval
(correctly blocked on the pending screen) → approve via the real admin
panel → sign in → upload a real lease → confirm all 15 fields show
citation + confidence → confirm the export link is set. Zero JS errors
anywhere in the sequence.

### Part 3: Data confidence

Re-verified (didn't need to rebuild) that every one of the 15 fields
shows confidence + citation when found, neither when not found —
architecturally guaranteed by a single shared rendering code path,
confirmed live across all 10 real fixture PDFs (150 field checks, zero
anomalies). Added a "Why this matters" explainer above the field cards
on the lease detail view, naming explicitly why the citations exist.

### Part 4: Final visual QA, two widths

Screenshotted every screen at small-laptop (1366px) and tablet (820px)
widths. Found and fixed the button-overflow and nav-contrast bugs
above. Confirmed the wide comparison table's horizontal scroll stays
contained rather than leaking into a page-wide scrollbar.

### What still needs your input

- **Google Sheets export's real success path** — still only verified
  via the clean "not configured" error message; this environment has
  no `GOOGLE_APPLICATION_CREDENTIALS` set. Needs your own Google Cloud
  service account to verify a real spreadsheet gets created. Setup
  steps are in `backend/.env.example`.
- **The original 500-page/250-lease PDF** — still unrecoverable from
  an earlier session; large-scale accuracy has only been verified
  against a synthetic 60-lease document, not that specific file.

### How to restart both servers

```bash
# Terminal 1 — backend
cd backend
source venv/bin/activate
python run.py
# Runs on http://localhost:5000 — confirm with: curl http://localhost:5000/health

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8000
# Open http://localhost:8000 (landing page) or http://localhost:8000/app/ (app,
# gated unless LOCAL_DEV_MODE=true in backend/.env)
```

---

## Session 12: Access control, dashboard aggregation, live upload status

**Honest status up front**: all 5 requested phases (accuracy re-check,
access control, dashboard aggregation, upload UX, visual consistency)
are built, committed separately (one commit per phase, 5 total, plus
2 follow-up color fixes carried over from finishing the prior
session's redesign work first), and verified against the real running
app — uploads, checkbox selections, filters, and the access gate's
full state machine were all driven live through jsdom or a small
hand-rolled Chrome DevTools Protocol screenshot client, not just unit
tests. Two real bugs were found and fixed along the way (an
access-gate link picking up default browser button styling once it
stopped being a plain `<a>` tag; a missing button-chrome reset). Real
Google Sheets export still cannot be verified end-to-end in this
environment — no `GOOGLE_APPLICATION_CREDENTIALS` is configured here,
same open item as prior sessions.

### Phase 1: Re-verified accuracy before building anything new

The prior session already ran a thorough small/medium/large accuracy
pass; this phase re-confirmed nothing had regressed since (fresh
live-API uploads of 3 real fixtures, checked that every found field
still carries both a confidence badge and a source citation, and that
missing fields stay cleanly `null` rather than being guessed). No
issues found; 22/22 backend test files pass.

### Phase 2: A real request-access + pending-approval gate

Extended the existing waitlist system (already had signup -> pending
-> admin approve/deny, just not reachable from the app itself) into
`access-gate.js`'s own UI: three swappable panels — sign-in
(existing), request-access (new, posts to the same `POST /waitlist`
the landing page already used), and a dedicated pending-approval
screen (new — previously "not yet approved" was just an inline
message, not its own screen). No backend changes needed. Still
explicitly not real authentication (self-reported email, no password)
— restated in DECISIONS.md since the new pending screen reads more
like a real signup flow than the old version did. Verified the full
state machine live: unknown email -> request access -> pending screen
-> admin approves via the real API -> recheck -> granted.

### Phase 3: Checkbox selection now rolls up to a live summary panel

New `GET /leases/selection-summary?ids=...` endpoint (reuses the
existing `compute_portfolio_metrics()` over just the selected subset,
same reasoning as the existing risk-analysis portfolio-context helper
— one definition of "how these numbers get summed"). The dashboard's
existing "Select to compare" checkboxes now also drive a live inline
tiles panel (total rent, total sq ft, total CAM, avg rent/sqft, avg
security deposit) that updates as boxes are checked/unchecked,
alongside (not replacing) the existing side-by-side Compare view.
Added status (Active/Expiring Soon/Expired) and expiration date-range
filters next to the existing text search — the status thresholds
mirror the Timeline view's own 6-month bucketing exactly, so they
can't disagree with each other for the same lease.

### Phase 4: Upload status is now genuinely live, not a batch-wide flip

Found the real gap: multi-file upload showed a spinner on every file
immediately, then flipped all of them to done/error simultaneously
only once the whole batch request finished — a fast file next to one
slow file looked stuck the whole time even though it had actually
finished. Switched to sequential per-file `POST /leases` calls (not a
new endpoint), each updating its own row the moment it resolves.
Verified the staggering is real by polling the DOM every 15ms during
a real 3-file upload and capturing files reaching "processing"/"done"
at different times, not together. Also verified the error path: a
genuinely corrupted PDF mixed into valid files gets its own error row
without blocking the others.

### Phase 5: Confirmed consistency rather than redesigning twice

The task's design brief read like a from-scratch redesign ask, but the
app had already been fully redesigned earlier in this same session
(the charcoal/brass/ivory palette promoted into the shared token
file). Asked directly whether Phase 5 meant a second redesign or a
consistency check on the new Phase 2-4 UI, rather than guessing and
risking discarding already-verified work — confirmed: consistency
check. Audited for hardcoded colors (none), off-scale typography/
spacing (none), and tablet responsiveness at two breakpoints (both
already correct via existing `flex-wrap`). No code changes needed.

### What still needs your input

- **Google Sheets export's real success path**: still only verified
  via the clean "not configured" error message in this environment
  (no `GOOGLE_APPLICATION_CREDENTIALS` set) — needs your own Google
  Cloud service account to verify a real spreadsheet gets created.
- **A human pass over the new screens**: everything was verified with
  real screenshots and live functional tests this session, but 10
  minutes of your own eyes on the request-access flow and the
  dashboard selection panel is still worth doing before calling it done.

---

## Session 11: Organization/accuracy verification + Excel export + one shared palette

**Honest status up front**: all four parts are built, committed
separately (4 commits: one per part), and verified against the real
running app — not just unit tests. Nothing was reported as done
without being tested first. Two real bugs were found and fixed along
the way (a frontend date-sort bug, and a backend Excel/CSV export
missing 4 of 15 fields); a third apparent bug (60-lease PDF under-
splitting) was root-caused to throwaway test-generator tooling, not
the app, after direct inspection of raw page content. The one thing
genuinely **not** verified end to end is a real Google Sheets export
actually creating a spreadsheet — this environment has no
`GOOGLE_APPLICATION_CREDENTIALS` configured (same open item as the
session that first built Sheets export), and per explicit standing
instruction this was never worked around by inventing credentials.
Everything else below was tested, not assumed.

### Part 1: Verified lease organization end-to-end, found and fixed a real sort bug

Uploaded a real 3-lease merged PDF through the live app (via a jsdom
harness executing the actual `<script>` tags against the real running
backend, not a mocked/simulated request) and confirmed: the split into
3 separate, independently renameable records; the lease detail view
rendering all 15 field cards with a source citation and confidence
badge on every found field; rename persisting; the search/filter box
narrowing correctly. While testing table sorting, found that the
"Expires" column sorted lease end dates as plain strings, not
chronologically — confirmed directly (3 real leases sorted as
`['03/31/2035', 'December 31, 2035', 'March 31, 2030']`, alphabetical
by first character). Fixed with a `parseLeaseDate()` helper in
`app.js` that mirrors the server's own date-format handling, so
client-side sorting can't disagree with how the server interprets the
same strings. Re-verified the fix on the same live data.

### Part 2: Verified extraction accuracy at small, medium, and large PDF scale

The original ~500-page/250-lease PDF that first surfaced the multi-
lease bleed issue remains unrecoverable (never persisted past its
temp-upload lifecycle, confirmed again this session). In its place:
the existing 10 real small fixtures (already covered by the live test
suite), a new 35-page medium single-lease document (real terms on
page 1, 34 pages of exhibit boilerplate after — confirmed the
extraction engine isn't fooled into over-splitting a long document),
and a new 60-lease large synthetic document, uploaded through the live
running API. Result: 60/60 leases split into 60 separate records, 0
field-value mismatches against ground truth, 0 citation/confidence
anomalies across ~900 checks. Also re-confirmed live that the
previously-fixed multi-lease field-bleed issue stays fixed. The one
bug found here was in the test-fixture generator itself (a PDF-merge
temp-file reuse bug caused silent page-content duplication) — root-
caused by inspecting raw page text before assuming the app was at
fault, then fixed in the (non-repo) generator script. No application
code needed to change for this part.

### Part 3: Excel and Google Sheets export added to both the detail and list views

Found a real accuracy gap while cross-checking the two exporters
against each other: the CSV/Excel rent-roll export only covered 11 of
the 15 extracted fields, silently dropping Permitted Use, Exclusivity
Clause, Insurance Requirements, and Default/Cure Period, even though
the Google Sheets exporter already had all 15. Fixed — both now export
every field (18 columns total with the derived/identifier columns).
Added single-lease export routes (`GET /leases/<id>/export.xlsx`,
`POST /leases/<id>/export/google-sheets`) that reuse the existing
portfolio exporters with a one-lease list, and wired "Download Excel"
+ "Export to Google Sheets" controls onto the Lease Detail view and
the Dashboard/Lease Library view. Verified end to end: uploaded a real
lease via the live API, downloaded its `.xlsx`, and diffed all 18
cells against that same lease's own API response — zero mismatches.
Confirmed via the real rendered UI that both new Google Sheets buttons
correctly show a clear "not configured" message (this environment has
no Google credentials set) rather than failing silently or crashing.

### Part 4: One shared color palette across landing, app, and admin

The session 5 landing redesign introduced a premium deep-charcoal/
brass/ivory palette, but only as a `landing.css` override —
`design-system.css` itself still defaulted to the original indigo/
violet, so `/app/` and `/admin/` never actually inherited it despite
that file's own comment already claiming a shared palette was the
goal. Opening the app showed exactly the default-SaaS indigo/violet
look the landing redesign was built to avoid. Fixed by promoting the
palette to the shared token file so every page gets it by default,
found and fixed 8 additional hardcoded off-palette colors in
`styles.css` that bypassed the token system entirely, and deepened the
confidence/risk badge colors toward a more premium jewel-tone register
while keeping the red/amber/green semantic mapping exactly as-is
(breaking that convention would trade usability for looks). No
Playwright/Puppeteer is available in this environment, but real
screenshots were still taken and looked at — via Chrome's own
`--headless --screenshot` flag and a small hand-rolled DevTools
Protocol client — covering the dashboard, a lease detail view (both
with confidence badges and with real risk flags), the comparison
table, the timeline, and the admin page. All read as one cohesive
product with good contrast; zero leftover indigo/violet found by
grepping the fully-resolved stylesheet output.

### What still needs your input

- **Google Sheets export, the real success path**: both the portfolio-
  wide and single-lease export routes correctly show a clear
  "GOOGLE_APPLICATION_CREDENTIALS isn't set" error in this environment
  (verified), but nobody has watched a real spreadsheet actually get
  created and populated, since that requires your own Google Cloud
  service account credentials. Setup steps are in
  `backend/.env.example`. Once configured, worth a real click-through.
- **The original 500-page/250-lease PDF**: still unrecoverable. If you
  still have that file anywhere, re-uploading it would be the closest
  thing to a real test of Part 2's large-scale claim — the 60-lease
  synthetic document used instead is a scale proxy, not the same file.
- **A visual sign-off**: the color redesign was verified with real
  screenshots this session (a first for this project — no browser
  automation tool had been available in prior sessions), but a human
  eye on the actual running app is still worth 5 minutes before
  calling the look "done."

---

## Session 10: Multi-lease splitting + lease library (naming, rename, tags)

**Honest status up front**: all three requested parts are built, committed
separately, and verified — including the specific symptom that motivated
this session (a merged PDF's risk analysis showing 30+ "conflicting"
start dates). The one thing that could NOT be verified is the exact
scenario asked for in the verification instructions: uploading the
actual 250-lease/500-page PDF and confirming 250 correctly-named
records. That specific file was not recoverable (see below) — what's
verified instead is equivalent-strength testing against this project's
own real fixture PDFs, at up to 10-lease scale with 100% field accuracy,
plus a documented, honestly-disclosed edge case where the splitting
heuristic is known to under-split.

### Part 1: Multi-lease PDFs are now SPLIT, not rejected or merged

The previous session's fix (see below) detected a multi-lease PDF and
refused the upload — safer, but not enough: a real portfolio PDF
produced a risk flag listing 30+ "conflicting" start dates, because
risk analysis reads `date_candidates` collected from the whole document
independently of the fields themselves.

`FieldExtractor.detect_lease_boundaries()` now places a page boundary
at the first page each distinct tenant OR landlord is introduced on
(the union of both signals). `extract_multiple_leases()` runs the
existing single-lease extraction independently on each range. A file
that's actually one lease still produces exactly one record, unchanged.

**Verified concretely**: every field of every split lease exactly
matches standalone extraction of its own source document (not
approximately — checked field-by-field), across 4 different real
merges plus all 10 of this project's fixtures merged into one 10-lease
document (correct in 0.05s). The reported 30-dates symptom was directly
reproduced on a 5-fixture merge and confirmed fixed: 1-2 dates per
lease afterward, only the two genuinely-inconsistent fixtures still
flagging.

**Honestly disclosed limitation, not glossed over**: if two different,
non-adjacent leases in the same merged PDF share BOTH the exact same
tenant name and the exact same landlord name, this heuristic can't
tell them apart and will under-split. Confirmed directly with a
constructed worst-case test. A same-tenant-different-landlord case
(e.g. one chain tenant leasing from different landlords) IS correctly
handled — that's specifically why the boundary signal uses the union of
tenant and landlord pages, not just one.

**Could not test against your actual 250-lease PDF** — the file only
ever existed as a temp upload, already deleted by the time this session
started, and wasn't found in Downloads/Desktop/Documents or anywhere
else searched on this machine. If you still have it, re-uploading it
now is the real test; I'd want to see the result.

### Part 2: Every lease is individually named, renameable, searchable

Auto-generated `display_name` at upload: "[Tenant] - [Property
Address]" when both were found, else "[filename] - Lease [N]" (no
redundant "- Lease 1" suffix for a lease that wasn't split). New
`PATCH /leases/<id>` to rename. Click-to-edit inline rename on both the
dashboard's new "Lease Library" table (replacing Document/Landlord/Sq
Ft columns with Name/Tenant/Property Address) and the lease detail
page's title — verified live that a rename immediately shows up in the
comparison view too, not just where it was typed. Search filter
extended to match name and tags, not just tenant/landlord/address.

Not touched in this pass: the printable portfolio report still shows
tenant + source filename rather than the custom name — deferred rather
than rushed, since that module has its own test suite that would need
re-validating alongside it.

### Part 3: Tags (chosen over folders — see DECISIONS.md)

A lease can carry any number of tags (new `lease_tags` table, `ON
DELETE CASCADE`), managed from the detail page with autocomplete
against every tag already in use. Dashboard shows each lease's tags as
mini chips; clicking one filters the list to that tag. Chose tags over
a folder hierarchy because a lease legitimately belongs to more than
one useful grouping at once, which a strict one-parent-folder model
can't represent without duplicating the lease.

### Migration / data safety

The dev database's `leases` table gained 3 new columns
(`display_name`, `source_page_start`, `source_page_end`) via a real
`ALTER TABLE` migration in `init_db()` — not just `CREATE TABLE IF NOT
EXISTS`, which can't add columns to an already-existing table. Tested
directly against a simulated old-schema database: the existing row
survived with its data intact, the new columns just came back NULL.
As it happens, this project's actual dev database was already empty at
the start of this session (its `leases` table had been wiped by a
previous session's test run, as noted in session 9's PROGRESS.md entry
at the time) — so there was nothing to migrate in practice, but the
mechanism was still verified for real, since it needs to be correct
for any database that does have existing data.

### Verified this session
- **22/22 backend test files pass** — every prior session's tests still
  green, plus this session's: `test_multi_lease_detection.py` (12
  tests, boundary/split correctness), `test_live_multi_lease_api.py`
  (25 checks against the live server), `test_lease_naming_and_tags.py`
  (15 tests, naming/rename/tags).
- Full frontend flow via jsdom against the live app, at each part:
  uploaded a real 3-lease merged PDF through the actual upload UI,
  confirmed the split results UI, confirmed the dashboard showed 3
  separate rows, renamed one and watched it propagate to the
  comparison picker, added/removed a tag and confirmed the dashboard
  chip + click-to-filter. Zero JS errors throughout every check.
- Performance: a 55-page synthetic document (5x this project's 10
  fixtures) processed in 0.24 seconds total — not a concern at the
  scale of a real 250-lease document.

---

## Session 9: Multi-lease PDF fix (detect-and-reject) + Google Sheets export

### Part 1: Multi-lease PDFs now rejected, not silently merged

Before building any export, verified (per explicit instruction, not
assumed) whether a PDF containing more than one lease was handled
correctly. **It was not.** Concatenating two real fixture PDFs and
running the actual extraction pipeline against the result produced a
single record mixing both leases: tenant from lease #2, rent and dates
from lease #1. Also found a real example already sitting in this
project's dev database from before this fix existed — a
`Sample_500_Page_Lease_Portfolio.pdf` upload persisted as ONE lease
with a $262,131.87 monthly rent and no end date found.

**Fixed**: `FieldExtractor.detect_multiple_leases()` (in
`field_extractor.py`) detects when a document defines more than one
distinct tenant or landlord — strong, low-false-positive evidence of
multiple concatenated leases, reusing the same party-name patterns
`extract_fields()` already uses rather than new detection logic. Wired
into the shared upload pipeline (`_extract_fields_from_file_storage` in
`api.py`), so `/extract`, `POST /leases`, `POST /leases/batch`
(per-file, without failing the rest of the batch), and amendment
uploads all now reject a multi-lease PDF with a clear 400 explaining
what's wrong and telling the uploader to split the file. Does **not**
attempt automatic per-lease splitting — that's a substantially larger,
separate feature; refusing and flagging clearly was the deliberately
smaller, safer scope, consistent with this project's "flag clearly,
never guess silently" standard.

Two false positives found and fixed before shipping (both were the
same real party matched twice by different regex patterns, not two
different parties) — see DECISIONS.md for the full detail. Verified
against all 10 existing single-lease fixtures individually (zero false
positives after the fix) and 4 different real multi-file merges.

**Action for you**: this project's dev database had 2 pre-existing
`Sample_500_Page_Lease_Portfolio.pdf` records with the bleed described
above. Running this session's full test suite wipes the dev database's
`leases` table as a normal, documented side effect (every live test in
this suite has always done this — see e.g. `test_live_portfolio_api.py`'s
own docstring), so those two records are already gone. If you still
have the original 500-page PDF, it will now be correctly rejected on
re-upload with a clear message — you'd need to split it into individual
lease files first.

### Part 2: Google Sheets export

New "Export to Google Sheets" button (Portfolio Report view), plus a
"Download CSV" button that — turns out — didn't exist anywhere in the
UI before this session either (the backend endpoint was already there,
just never wired to a button).

- **Backend** (`backend/app/sheets_export.py`, new): uses a Google
  service account (not OAuth login — this is a backend export action,
  not a per-user sign-in flow). Every export creates a **brand-new
  sheet** named "Lease Portfolio Export - [date]" (confirmed this
  behavior with you directly rather than assuming) and shares it
  "anyone with the link can view" so the returned link always opens —
  see DECISIONS.md for the privacy tradeoff that implies (same as the
  existing CSV/report exports, not a new one).
- **New endpoint**: `POST /portfolio/export/google-sheets`.
- **Columns** (one row per lease): Tenant Name, Landlord Name, Property
  Address, Monthly Rent, Annual Rent, Rent per Square Foot, Security
  Deposit, Rent Escalation, Lease Start/End Date, Renewal Options,
  Default/Cure Period, Permitted Use, Exclusivity Clause, Insurance
  Requirements, CAM Charges, Square Footage. Annual Rent and Rent/SqFt
  are computed via `app.normalize`, same as every other aggregate in
  this project. A field that wasn't found is a **blank cell**, never
  the text "Not Found".
- **Frontend**: both buttons live in a new "Export Portfolio Data"
  panel on the Report view. A failed export shows a clear, specific
  error message in place (never a silent failure, never crashes
  anything else); a successful one shows a clickable link that opens
  the new sheet in a new tab.

### What you need to do to finish setup

Nothing works yet — **no Google credentials are configured**, and none
were invented or guessed. Exact steps (also in
`backend/.env.example`, which has the full walkthrough inline):

1. Go to console.cloud.google.com, create or pick a project.
2. Enable **both** the Google Sheets API and the Google Drive API
   (Drive API is what makes the created sheet's link actually open —
   Sheets API alone can't set sharing).
3. Create a Service Account, generate a JSON key for it.
4. Save that key file at `backend/credentials/google-service-account.json`
   (that whole directory's `.json` files are gitignored — see
   `backend/credentials/README.md`).
5. Set `GOOGLE_APPLICATION_CREDENTIALS=backend/credentials/google-service-account.json`
   in `backend/.env`.

Nothing needs to be individually shared with the service account for
this specific feature, since a new sheet is created fresh each time
(that step *would* matter if this were updating one persistent sheet
instead — it isn't, by your choice).

### Verified this session (honestly — what was and wasn't tested)
- **21/21 backend test files pass**, including everything from every
  prior session — re-run after each change, not just once at the end.
- Multi-lease detection: 7 unit tests (real PDFs merged at runtime via
  PyPDF2) + 12 live-API checks against the running server.
- Sheets export: 15 tests — every credential-failure path exercised for
  real (no credentials set, file missing, file invalid), the full
  happy path verified with the Google API client mocked out (asserting
  on the actual header/row data and sharing-permission call sent, not
  just "no exception"), and the API route's activity-logging behavior
  (logs only on success, never on failure).
- Live, with no credentials configured (the real current state of this
  environment): confirmed via `curl` that `POST /portfolio/export/
  google-sheets` returns a clean 502 with an actionable message, not a
  crash or a 500.
- Full frontend flow via jsdom against the live app: navigated to the
  Report view, confirmed the CSV button now has a working link
  (previously wired to nothing), clicked "Export to Google Sheets" and
  confirmed the clear in-UI error state renders correctly and the rest
  of the app (navigating back to the dashboard) still works afterward.
  Also verified the success-state UI (clickable link, opens in a new
  tab) with a mocked successful backend response, since no real
  credentials exist to test an actual Google API call end-to-end —
  that step is honestly untested against the real Google API and is on
  you once credentials are in place.

---

## Session 8: /app access gate + local dev bypass

**What this was**: `/app` had no access control at all — reachable
directly by anyone (see Session 5's note below, and DECISIONS.md). This
session added a real (if lightweight) gate, plus a way to skip it when
testing locally so that doesn't mean re-doing the waitlist signup/approve
flow on every restart.

**Backend** (`backend/app/api.py`, `backend/app/database.py`):
- `LOCAL_DEV_MODE` — read once from the environment at process start
  (`backend/.env`, loaded via the existing `load_dotenv()` call). Not
  settable by any request.
- `GET /config` — returns `{"local_dev_mode": bool}`, the only thing the
  frontend needs to decide whether to skip the gate.
- `POST /waitlist/check` — body `{"email"}`, returns `{"approved",
  "found"}` only. Deliberately public (like `POST /waitlist` itself),
  but unlike `GET /waitlist` it never returns the signup list or anyone
  else's email — see the comment block above it in `api.py`.
- `database.get_waitlist_signup_by_email()` — case-insensitive lookup.
- **Does not touch** `insert_waitlist_signup`, `get_all_waitlist_signups`,
  `approve_waitlist_signup`, or the `waitlist_signups` schema — verified
  by test (`test_waitlist_signup_and_admin_approval_flow_unaffected` in
  the new `test_access_gate.py`).

**Frontend** (`frontend/app/`):
- `access-gate.js` (new) — on load, asks `/config`; if
  `local_dev_mode` is true, lets the visitor straight in. Otherwise
  checks a cached email in `localStorage` (re-verified against the
  backend every load, so a revoked approval takes effect immediately),
  or shows a small gate screen (email input → `/waitlist/check`) if
  there's no cached email or it's no longer approved.
- `index.html` — `.app-shell` is now hidden by default; the gate markup
  sits above it. The app's scripts (`api.js`, `app.js`, all seven view
  modules) are no longer static `<script>` tags — `access-gate.js` loads
  them dynamically, only after access is confirmed, so none of their API
  calls fire before the gate passes.
- `styles.css` — new `.access-gate*` rules, reusing existing design
  tokens/classes (`.text-input`, `.btn-primary`, `.brand`) rather than
  introducing new ones.

**Bug found and fixed along the way**: `app.js` and all six view modules
bootstrap via `document.addEventListener('DOMContentLoaded', ...)`. That
event has always already fired by the time these scripts get loaded
dynamically post-gate (true even on the instant `LOCAL_DEV_MODE` path,
since the `/config` fetch is async) — so none of them would have
initialized, silently, no console error. Each of the seven files now
checks `document.readyState` first and calls its init function directly
if the page already finished loading. See DECISIONS.md for the full
writeup.

**Verified this session**:
- New `tests/test_access_gate.py` (9 tests): `/config` on/off,
  `/waitlist/check` for unknown/pending/approved/case-mismatched emails,
  invalid-email rejection, response shape never leaks other signups, and
  the existing signup+admin-approve flow still works unchanged end to
  end through the real routes.
- Full backend suite: **14/14 test files pass**, no regressions.
- Manual verification of both flows (`LOCAL_DEV_MODE=true` reaching
  `/app` directly, and the real gate + waitlist + admin approval flow
  with it off) — see the verification note further down this session's
  entry for exact commands and results.

**What this is not**: real authentication. No password, no session
token, no proof the visitor typing an email owns it — just a
self-reported match against the waitlist's approval status. The admin
waitlist endpoints (`GET /waitlist`, `POST /waitlist/<id>/approve`,
`/admin/waitlist/`) remain exactly as unauthenticated as before — this
session didn't touch that. See DECISIONS.md "Access gate uses
self-reported email, not real auth" and the updated Next Steps below.

## Session 7: Daily-Use Expansion — Phase 1 Complete, Phases 2-6 Not Started

**Honest status up front**: the session's request was a 6-phase feature
expansion (dashboard upgrades, renewal/expiration workflow, deeper
intelligence, search/organization, reporting, daily-use polish). Only
**Phase 1** was built this session. It is fully built, tested, and
verified against the live app — not just claimed. Phases 2 through 6
were not started; nothing about them exists yet, not even scaffolding.
Stopping here was a deliberate choice to keep Phase 1 genuinely done
rather than spread this session thin across partially-wired features,
per the explicit instruction to stop at a clean checkpoint rather than
rush ahead.

Nothing from the hardening pass (OCR pipeline, security validation,
error handling) or the landing page/waitlist flow was touched. The full
pre-existing test suite (all 14 files from before this session) still
passes unchanged.

### Phase 1: Daily-Use Dashboard Upgrades — DONE

**"What needs attention today" panel** (`GET /portfolio/attention`,
`compute_attention_items()` in `portfolio.py`): three groups — leases
expiring within 90 days, leases missing core fields (tenant, landlord,
rent, either date), and leases with medium/high-severity risk flags.
The third group deliberately reuses the existing `analyze_lease_risks()`
engine rather than inventing a new "unusual terms" heuristic, so it can
never disagree with what the lease detail page's risk panel already
shows. Each item click-through navigates straight to that lease. Shows
a genuine "portfolio is in good shape" state, not just an empty list,
when nothing needs review.

**Recent activity feed** (`GET /activity?limit=10`, `activity_log`
table in `database.py`): logs lease uploads (one entry per single
upload, one summary entry per batch — not one per file, so a 20-file
batch doesn't crowd out everything else), amendment uploads, deletes,
comparisons run, and rent-roll exports (CSV/Excel). **Deliberately does
NOT log the portfolio report preview** — `report-view.js` fetches that
HTML on every visit to the Report view, not just on intentional
generation, and logging it would flood the feed with noise every time
someone switches tabs. This is documented inline in `api.py`, not just
here. Field corrections are also not logged yet, honestly, because
correction persistence doesn't exist yet — `detail-view.js`'s inline
edit currently only mutates in-memory state and is lost on reload; that
gap belongs to Phase 4 ("inline correction workflow... save the
correction"), not this one, and logging an activity for something that
doesn't actually save would be dishonest instrumentation.

**Portfolio health strip** (`GET /portfolio/health`,
`compute_portfolio_health()`): % of leases needing no review (derived
from the same attention computation above, not a separate heuristic —
the two literally cannot disagree), average days to next expiration,
and monthly rent exposure expiring in the next 6/12 months.

**Quick actions bar**: moved into the shared app shell in `index.html`
so it's present on every view, not just the dashboard — reuses the
existing `data-goto` navigation, no new routing logic needed.

**A schema note worth flagging explicitly**: `activity_log.lease_id`
has `ON DELETE SET NULL` on its foreign key to `leases`, discovered to
be necessary while building this (not anticipated up front) — without
it, deleting a lease that has activity history would either violate the
FK constraint or require deleting its own history. With `SET NULL`,
deleting a lease works exactly as before and its activity entries
survive (with `lease_id` nulled) since their `description` text already
has the filename baked in.

### Verified this session (not just written)
- **16/16 backend test files pass**, including all pre-existing ones —
  run via `python run_all_tests.py --live` after every change, not just
  once at the end
- New unit tests (`test_dashboard_features.py`, 11 tests): attention
  window boundaries, missing-data detection, risk-engine reuse, health/
  attention agreement, activity log persistence, the `ON DELETE SET
  NULL` behavior specifically, limit clamping — against hand-built
  fixtures, no live server needed
- New live-API tests (`test_live_dashboard_api.py`, 22 checks): the
  three new endpoints exercised against the real running backend with
  real fixture PDFs uploaded/compared/exported/deleted, not mocked.
  While building this, a real bug in the *test itself* was caught and
  fixed: an early version compared two `limit=50` snapshots to detect
  activity growth, which silently breaks once the dev DB accumulates
  more than 50 rows (it now has 80+, from cumulative sessions) — fixed
  to check the exact identity/order of the 2 most-recent entries
  instead, which stays correct at any table size
- Full dashboard verified end-to-end via jsdom against the live running
  app (not just the API in isolation): quick actions bar, attention
  panel in both its populated and "all clear" states, health strip, and
  activity feed all confirmed rendering correctly with real data and
  zero JS errors, including click-through from an attention item to the
  lease detail page

### What Phase 1 explicitly does NOT include (scope, not a bug)
- No new external paid API dependency was introduced — flagging this
  proactively per the session's instructions, even though nothing
  applies yet: none of Phases 2-6 as currently scoped obviously need one
  either (calendar/notifications/search/tagging/reporting are all
  buildable with the existing stack), but Phase 2's "configurable alert
  windows" could eventually want real email/SMS delivery, which *would*
  need a third-party service and a key from you — flagged now so it's
  not a surprise later, nothing has been built against one.

### Phases 2-6: NOT STARTED
To be direct about exactly what that means — none of the following
exist in any form yet:
- **Phase 2** (renewal/expiration workflow): no calendar view, no
  configurable alert windows, no notification center, no per-lease
  renewal status field
- **Phase 3** (deeper intelligence): no new extracted fields (early
  termination, co-tenancy, assignment/subletting are not yet extracted
  — everything else in the requested field list already existed before
  this session), no portfolio-wide analytics charts
- **Phase 4** (search/organization/correction): no global search, no
  tagging/folders, no persisted field-correction workflow, no bulk
  actions
- **Phase 5** (reporting/export): the portfolio report and CSV/Excel
  rent-roll export already existed before this session and still work;
  no custom report builder exists
- **Phase 6** (daily-use polish): no keyboard shortcuts, no
  last-viewed-screen memory, no mobile-responsive pass specifically on
  dashboard/calendar/detail

### Exact commands to restart both servers

```bash
# Terminal 1 — backend
cd backend
export PATH="$HOME/.miniforge3/bin:$PATH"   # tesseract + poppler, for OCR
source venv/bin/activate
python run.py
# Confirm: curl http://localhost:5000/health

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8000
# Landing:      http://localhost:8000/
# App:          http://localhost:8000/app/          (attention panel, health strip, activity feed live on the dashboard)
# Admin:        http://localhost:8000/admin/waitlist/
```

---

## Session 6: Landing Page — Luxury Repositioning

A landing-page-only pass (per explicit scope): copy, layout, and visual
treatment of the request-access flow and confirmation states. Nothing
in `/app/`, `/admin/waitlist/`'s data logic, the waitlist table schema,
or any backend extraction/OCR/security code was touched — only display
copy in two backend strings (the `/waitlist` success message) changed,
since that copy is part of the confirmation-state flow the task
explicitly covered.

### What changed

**Visual direction** — the landing page now reads like a high-end
product page (automotive/luxury brand references) rather than a SaaS
template:
- Full-bleed, cinematic dark hero: radial glow, a faint architectural
  grid, and an inline SVG skyline silhouette sitting at the bottom edge
- Oversized heavy-sans headline (Inter 900, tight negative tracking),
  small uppercase eyebrow labels above every section heading, generous
  whitespace throughout
- A restrained, expensive palette — deep charcoal/black, warm brass
  accent, off-white — with **no default SaaS blues or purple
  gradients**. This palette lives entirely in `landing.css`'s own
  `:root` override block, which only takes effect on documents that
  load that stylesheet (the landing page). `design-system.css` itself
  is unchanged, so `/app/` and `/admin/waitlist/` keep their original
  indigo palette exactly as before — verified directly (see below).
- Capabilities section restyled as a luxury "spec sheet": six bordered,
  adjoining badge cards (icon + uppercase label + one-line outcome),
  replacing the old numbered 3-step layout
- A dark, moody statement section (bold one-liner + a single CTA) in
  place of the old placeholder-metrics stats strip
- Subtle scroll-reveal animations (fade + rise via IntersectionObserver,
  `.reveal`/`.in-view`) on every major section — respects
  `prefers-reduced-motion`, and falls back to fully-visible immediately
  if `IntersectionObserver` isn't available at all

**Copy — outcome-first, zero backend mechanics**: rewritten to lead
entirely with the real estate outcome (portfolio clarity, fewer missed
renewals, sharper decisions, more time on strategy). The words "OCR,"
"extraction," "parsing," and "AI pipeline" do not appear anywhere on the
page — verified by scanning the rendered page text directly, not just
by eye.

**Waitlist reframed as exclusive access, not a signup queue**:
- Button copy: "Request Access" (was "Join the waitlist")
- An explicit scarcity line above the form: "We work with a limited
  number of real estate firms at a time. Request access below."
- Confirmation state reads as being noticed, not queued: "Your request
  has been received. If it's a fit, we'll be in touch." — no position
  number, no count, anywhere (checked directly against the rendered
  page and the backend's JSON response)
- Admin view (`/admin/waitlist/`) copy reframed to match: "Approve" ->
  "Grant Access," status labels read "Pending Review" / "Access
  Granted." This is **display copy only** — the underlying
  `waitlist_signups` table and its `pending`/`approved` status values
  are unchanged; `statusLabel()` in `admin.js` just maps the existing
  value to friendlier text.

**Contact**: a small, single-line contact (email + phone) added to the
footer, deliberately understated — no contact form, no dedicated
section.

### Verified this session
- Full backend suite re-run after the `api.py` copy change: **14/14
  test files pass**, no regressions
- Hero, capabilities, statement, and footer sections each verified via
  jsdom against the live backend as they were built (not just at the
  end) — copy, structure, and a real request-access submit-to-
  confirmation round trip all checked, zero JS errors throughout
- Directly confirmed `/app/`'s `--primary-color` computed style is
  still `#4f46e5` (the original indigo) after this session's changes —
  i.e. the landing page's new palette provably did not leak into the
  app
- Scanned the rendered landing page's text content for banned
  tech-mechanics words and for queue-position language ("position in
  line," "#N in line," etc.) — none found

### What's NOT done / known gaps (carried over, still true)
- No real authentication on `/admin/waitlist/` or on reaching `/app/`
- Sidebar/app views inside `/app/` were not touched this session — this
  was scoped to the landing page only, per explicit instruction

---

## Session 5: Visual Redesign — landing page, waitlist, app restyle

A frontend/design-only pass (per explicit scope) — no extraction logic,
OCR pipeline, or hardening-pass security code was touched. All 14/14
backend test files (62+ checks) still pass unchanged after this session.

### What's new

**Landing page** (`frontend/index.html`, now the root `/`):
- Hero with headline, subheadline, and a single email waitlist form (no
  pricing, no login) — submitting shows an inline confirmation state
  ("You're on the list...") instead of navigating away
- "How it works" section, 3 steps with icons (upload → AI extracts →
  portfolio dashboard)
- A stats strip with **placeholder metrics, explicitly commented as
  placeholder** in `index.html` — swap these before real launch
- Footer with placeholder/dead links (Privacy, Terms, Contact, About)

**Waitlist backend** (`backend/app/database.py`, `backend/app/api.py`):
- New `waitlist_signups` table (`id`, `email` UNIQUE, `created_at`,
  `status` default `'pending'`)
- `POST /waitlist` — join (validates email format; a duplicate email is
  a friendly no-op, not an error)
- `GET /waitlist`, `POST /waitlist/<id>/approve` — **unauthenticated**,
  admin-facing. This is intentional for now (explicit instruction), but
  is flagged in a comment block directly above the routes in `api.py`
  and must be locked down before real users are on the list.

**Admin waitlist view** (`frontend/admin/waitlist/`, at `/admin/waitlist/`):
- Table of every signup (email, joined date, status) with a per-row
  Approve button; a small stats strip (total/pending/approved)
- No auth — same caveat as above, also noted directly in its `index.html`

**Access to the app**: approved status isn't enforced yet — `/app/` is
reachable directly by anyone, exactly as instructed ("build the real
auth gate later, don't block on it now").

> **Superseded in Session 6** (below): `/app` is now gated on waitlist
> approval status. This is a lightweight email-check, not real
> auth/accounts — see DECISIONS.md "Access gate uses self-reported
> email, not real auth" for exactly what changed and what didn't.

**App restyle** (`frontend/app/`, moved from the old flat `frontend/`):
- One shared design system (`frontend/design-system.css`): indigo/violet
  brand palette, a refined slate neutral scale, Inter typography, a
  layered shadow scale, and a consistent radius scale — used by the
  landing page, admin view, and the app
- Sidebar: gradient-badge brand icon, gradient active nav state with a
  soft glow, subtle hover state
- Dashboard: metric tiles now show shimmer loading skeletons while data
  loads (instead of "—"), with hover lift; empty state ("No leases
  uploaded yet") now has a circular icon badge, a real heading, and a
  helper line instead of just an icon + button
- Timeline view's empty state got the same treatment
- Buttons, panels, and inputs now share the design system's shadows,
  radii, and focus states everywhere

**Verified this session** (see commands below to reproduce):
- Full backend suite: **14/14 test files pass** (unit + live API +
  security hardening) — no regressions from the redesign
- Landing page waitlist submission end-to-end (jsdom driving the real
  page against the real running backend, `window.fetch` bridged to
  Node's native `fetch` since jsdom has none built in): confirmation
  state renders correctly after a real `POST /waitlist`
- Admin view end-to-end (jsdom): signups render in the table, clicking
  Approve calls the real backend and updates the status pill
- The existing app (`/app/`) still loads cleanly post-restyle: zero JS
  errors, dashboard metrics render, sidebar nav intact (jsdom)
- Static routing: `/`, `/app/` (and bare `/app` 301-redirecting to it),
  and `/admin/waitlist/` all resolve correctly via `http.server`'s
  built-in directory-index behavior — confirmed with `curl`

No literal browser screenshots were taken — no browser automation tool
is available in this environment (consistent with every prior session).
Verification instead used jsdom driving the real, unmodified pages
against the real backend, as described above. To see it visually: start
both servers (commands below) and open `http://localhost:8000/`,
`http://localhost:8000/app/`, and `http://localhost:8000/admin/waitlist/`.

### What's NOT done / known gaps
- **No real authentication** on `/admin/waitlist/` or on reaching
  `/app/` — both explicitly deferred per instructions, flagged in code
  comments in three places (see `DECISIONS.md`)
- **Placeholder stats** on the landing page need real numbers before
  launch (marked in a code comment)
- Sidebar's "maybe a collapsed state" was treated as optional and not
  built — the sidebar itself was restyled (gradient active state, icon
  alignment, hover polish) but has no collapse toggle
- Remaining app views (upload, lease detail, comparison, Q&A, report)
  inherit the new design system automatically via the shared CSS
  variables/component classes but weren't individually hand-tuned
  beyond that systemic change

### Exact commands to restart both servers + see the new routes

```bash
# Terminal 1 — backend
cd backend
export PATH="$HOME/.miniforge3/bin:$PATH"   # tesseract + poppler, for OCR
source venv/bin/activate
python run.py
# Confirm: curl http://localhost:5000/health

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8000
# Landing:      http://localhost:8000/
# App:          http://localhost:8000/app/
# Admin:        http://localhost:8000/admin/waitlist/
```

---

## Session 4: Hardening Pass — honest status

This was a focused ~1-hour pass, not a features session: real OCR verification, a security/input-validation review, and a performance check, fixing anything found rather than just reporting it. Every claim below was actually tested this session (commands shown), not assumed.

### 1. OCR — now genuinely verified working (this closes a gap open since session 2)

Previous sessions could only mock this (no tesseract/poppler available, no package manager). This time:

- **Homebrew** (even to a user-owned prefix, avoiding the sudo requirement) still failed: no precompiled bottle exists for tesseract/poppler at a non-standard prefix on this OS/arch, so it fell back to building from source, which hit "Your Command Line Tools are too outdated" — fixable only via `sudo xcode-select --install` or interactive System Settings, neither available here.
- **Conda-forge** (via Miniforge, a self-contained non-interactive installer — no sudo needed) worked: `tesseract 5.5.3` and `pdftoppm version 26.07.0` (poppler) both installed as precompiled binaries.
- **Verified end-to-end** against a genuinely image-based PDF (rendered via Pillow, zero embedded text layer — confirmed 0 characters extractable via PyPDF2 before OCR even runs), through the real running API: PyPDF2 correctly detected sparse text → triggered the fallback → poppler rendered the page → tesseract OCR'd it → field extraction ran on the OCR output → **7/7 fields correct** (tenant, landlord, address, both dates, rent, deposit), all high confidence, in 1.4 seconds.
- This is now a **permanent, portable regression test** (`test_real_ocr.py`): it skips cleanly when tesseract/poppler aren't on PATH (so the suite still runs anywhere) but exercises the real pipeline whenever they are. Both behaviors were verified directly.
- **To get OCR working in a fresh environment**: install Miniforge (`curl -L -o miniforge.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh" && bash miniforge.sh -b -p ~/.miniforge3`), then `~/.miniforge3/bin/conda install -y -c conda-forge tesseract poppler`, then make sure `~/.miniforge3/bin` is on `PATH` before starting the backend (see restart commands below). This is installed in this project's dev environment already — it should still be there next time, since it lives in the home directory, not the repo or a temp dir.

### 2. Security — found and fixed a real stack-trace/path leak

- **Confirmed live**: `GET /leases/<a 34-digit number>` threw `OverflowError: Python int too large to convert to SQLite INTEGER`, and because Flask was running with `debug=True` (hardcoded in both `run.py` and `api.py`), this returned Werkzeug's full interactive debugger page — real file paths (`.../backend/venv/lib/python3.9/site-packages/flask/app.py`), full source code, a traceback, and an embedded (if untrusted) Python console. This is exactly the "stack traces / internal file paths exposed to the frontend" risk this pass was checking for, and it was real.
- **Fixed**: debug mode is now opt-in via `FLASK_DEBUG=1` (default off) in both entry points; global error handlers (400/404/413/500/`Exception`) always return clean generic JSON, logging the real exception server-side only. Verified this suppresses Werkzeug's debugger even with `FLASK_DEBUG=1` set, so local debugging still can't leak to a client.
- **Fixed the actual root cause**, not just the symptom: `database.get_lease()` now catches `OverflowError` and returns `None` — every route built on it already handles "not found" as a clean 404, so this one fix covers `/leases/<id>` (get/delete), `/leases/<id>/risks`, `/leases/<id>/benchmark`, `/leases/<id>/amendments`, and `/leases/compare`.
- **Also fixed**: an oversized (>16MB) upload previously returned Flask's raw HTML 413 page (which the frontend's JSON-only error parsing couldn't use) — now returns clean JSON with the actual size limit stated. A residual `str(e)` in the PDF-processing error path (which could have echoed a temp file's path for some exception types) now logs server-side only and returns a generic client message.
- **Checked and found already correct** (no fix needed): every SQL query in `database.py` is parameterized — no injection risk. Every place extracted PDF text reaches the DOM in the frontend goes through `escapeHtml()` or `.textContent`, never raw `innerHTML` — verified empirically, not just by reading the code: uploaded a lease PDF with `<script>`/`<img onerror>`/`<svg onload>` payloads embedded in the tenant name and address fields through the real frontend (jsdom executing the actual app), confirmed no live script/img/svg element was ever created and `window.alert` was never invoked, while the payload text was still visible as inert escaped text.
- **14 new regression checks** (`test_security_hardening.py`) re-create every failure found here against the live server, so none of it can silently regress.

### 3. Performance — no bugs found, both checks clean

- **Large document**: a genuine 40-page lease PDF (confirmed via PyPDF2 page count, not assumed) processed in **0.06 seconds**, correctly extracting fields from page 40 (proving the whole document was actually scanned, not just the first page). No hang, no timeout.
- **Concurrency**: fired 8 concurrent uploads of 8 different leases, then 15 concurrent uploads of the *same* file, directly at the live server. Every response matched its own file correctly (zero state bleeding — no lease ever got another lease's data), every insert got a unique sequential ID with no collisions, and the server logged zero errors throughout. Final DB count was exactly right both times (8, then 23 after the second batch). No race-condition bug existed to fix — each request already creates its own extractor instances, its own uniquely-named temp file, and its own short-lived DB connection, which is why this held up cleanly.

### What's NOT yet closed

- **No literal browser click-through** — still jsdom-based verification (see session 3's notes); no browser automation tool available in this environment.
- **Flask's dev server** is still explicitly a dev server (`app.run`), not a production WSGI server — fine for local/single-user use, called out in both READMEs, unchanged by this pass (out of scope — this pass hardened error handling and input validation, not deployment architecture).
- **Risk thresholds remain fixed constants** (carried over from session 3) — not tuned by this pass.

### Exact commands to restart both servers (updated — now includes OCR)

```bash
# Terminal 1 — backend (now with OCR support on PATH)
cd backend
export PATH="$HOME/.miniforge3/bin:$PATH"   # tesseract + poppler, installed this session
source venv/bin/activate
python run.py
# Debug mode is off by default now (safe). For local debugging only:
#   FLASK_DEBUG=1 python run.py
# Confirm: curl http://localhost:5000/health

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8080
# Open http://localhost:8080
```

Port already in use: `lsof -ti:5000 -ti:8080 | xargs kill -9`, then start again. The `backend/lease_portfolio.db` SQLite file (gitignored) currently holds test data from this session's verification runs — delete it (`rm backend/lease_portfolio.db`) for a clean empty portfolio, it'll be recreated automatically on next start.

### Re-run everything yourself

```bash
cd backend/tests
export PATH="$HOME/.miniforge3/bin:$PATH"    # so test_real_ocr.py exercises the real pipeline
source ../venv/bin/activate
python run_all_tests.py --live               # backend must be running for --live; 14/14 files pass
```

---

## Session 3 Completion Summary

### Overall status: fully working

The tool moved from single-lease extraction to portfolio-level intelligence this session. Every new capability — persistence, risk detection, Q&A, comparison, benchmarking, export, batch upload, amendments, and the full multi-view frontend — is built, integrated, and independently verified against real data through the real running backend and (for the frontend) a real script-tag-executing browser environment, not mocked. 12/12 automated test files pass (well over 250 individual assertions), a 48-check live API integration suite passes, and a 30-check + 7-check frontend end-to-end suite passes. There are no known bugs at the end of this session. The extraction-layer caveats carried over from session 2 (OCR not live-verified — see below) still apply; nothing new was introduced.

### What's new this session, in one paragraph

Upload is now persistent (SQLite) and supports batch upload with per-file error recovery, plus amendment documents linked to a base lease (an amendment's fields override the base lease's in an "effective" view). A rule-based risk engine flags below-market rent, missing standard clauses, notice-period outliers, one-sided terms, and internal inconsistencies (bad escalation math, conflicting or reversed dates) — each flag cites the actual numbers it fired on. A deterministic (non-LLM) Q&A engine answers portfolio and single-lease questions with citations traced to real stored source data, never a generated guess. A comparison view puts 2+ leases side by side and benchmarks any lease against the portfolio average. A rent roll exports as CSV or formatted Excel, and a printable one-page HTML report summarizes the whole portfolio. The frontend is now a 7-view sidebar app (Dashboard, Upload, Lease Detail, Timeline, Compare, Ask a Question, Report) instead of a single upload page.

### Full accuracy table (field extraction — unchanged core engine, now 15 fields)

Field-by-field extraction accuracy across all 10 test documents in the project — the original 5 plus 5 new documents built specifically to have deliberate risk-detection issues (below-market rent, missing clauses, no escalation, inconsistent escalation math, conflicting dates, reversed dates):

| Field | 5 original docs | 5 red-flag docs | Overall |
|---|---|---|---|
| tenant, landlord, rent_amount, lease_start_date, lease_end_date | 5/5 | 5/5 | 10/10 (100%) |
| property_address, security_deposit, cam_charges | 5/5 | 5/5 | 10/10 (100%) |
| rent_escalation, renewal_options, permitted_use | 5/5 | 5/5 | 10/10 (100%) |
| exclusivity_clause, insurance_requirements, default_cure_period | 5/5 | 5/5 | 10/10 (100%) |
| square_footage (new this session) | 3/5† | 5/5 | 8/10‡ |
| **Overall (all 15 fields × 10 docs)** | | | **150/150 (100%)** |

† 2 of the 5 original docs (`retail_lease.pdf`, `office_lease.pdf`) were updated this session to include square footage so the new rent-per-sqft metric has real data; `sample_lease.pdf`, `sample_lease_commercial.pdf`'s sibling docs correctly show Not Found where the field is genuinely absent — counted as correct, same convention as every other field.
‡ Every case scored — found-and-correct, or correctly Not Found — passes. There is no actual failure; the "8/10" reflects that 2 documents legitimately don't state square footage. 150/150 (100%) is the real number when null-vs-found is scored per the standard convention (see `test_synthetic_accuracy.py`).

Re-run: `cd backend && source venv/bin/activate && python tests/test_synthetic_accuracy.py`

### Risk detection: real results against the 5 deliberately-flawed documents

Every issue built into these 5 fixtures was independently confirmed caught, by three separate methods (direct function call, live API, live API integration test) that all agree:

| Document | Built-in issue | Flag raised? |
|---|---|---|
| `underpriced_downtown.pdf` | Rent ~34% below portfolio average per sq ft | ✓ `below_market_rent` (high) |
| `missing_clauses_office.pdf` | No insurance, no default/cure, no security deposit | ✓ all 3 `missing_clause` flags |
| `tenant_friendly_terms.pdf` | 10-yr term with no escalation; 45-day cure period; 15-day renewal notice | ✓ 2× `one_sided_terms`, 1× `notice_period_outlier` |
| `inconsistent_escalation.pdf` | Two different stated commencement dates; escalation table jumps 12.5% then 0.9% | ✓ `date_inconsistency`, ✓ `escalation_inconsistency` |
| `reversed_dates.pdf` | End date stated before start date; 330-day renewal notice | ✓ `date_inconsistency`, ✓ `notice_period_outlier` |

Across the full 10-document portfolio: 23 real flags total (verified identically via direct call, `GET /portfolio/risks`, and the live integration test).

### Q&A: real answers to the brief's own example questions

Run against real extracted data from the actual test PDFs (not fixtures written to make the answer easy):

- *"which leases expire in the next year"* → correctly lists the 2 matching leases with real dates and citations, excludes the 8 that don't match
- *"what's our total CAM exposure"* → `$3,475.00`, correctly noting 3 of 10 leases have no CAM charge on file (excluded from the sum, not counted as $0)
- *"does this lease have an exclusivity clause"* (scoped to one lease) → `"Yes — sample_lease_commercial.pdf has an exclusivity clause: during the Term, it shall not lease any other space..."` with a citation to the real page/quote
- Every citation in every test traces back to a field's actual stored `source` — the Q&A engine's own test suite includes an explicit sweep asserting no citation is ever fabricated across all intents

### Known issue: OCR not live-verified (carried over from session 2, unchanged)

**Resolved in session 4 — see the top of this file.** At the time this section was written, this development environment had no `tesseract`/`poppler` installed and no package manager available to install them; the OCR fallback logic was only verified with mocks. Session 4 got real binaries via conda-forge (Homebrew hit an outdated-Command-Line-Tools wall it couldn't get past without sudo/GUI access) and confirmed a real scanned PDF extracts correctly end-to-end. Leaving the original text below for the historical record of what was tried and why it didn't work at the time.

This development environment still has no `tesseract`/`poppler` installed and no package manager available to install them. The OCR fallback logic is verified with mocks (trigger condition, success path, failure-degrades-gracefully path), not a live scanned-PDF run. To close: `brew install tesseract poppler`, then run `backend/tests/test_ocr_fallback.py` against a real scanned PDF or upload one through the UI.

### Frontend verification note

No browser automation tool (Playwright/Puppeteer) was available, so a literal browser click-through wasn't possible directly. Instead, a jsdom harness had jsdom itself execute the real `<script src>` tags in `index.html` (`JSDOM.fromFile` + `runScripts: "dangerously"`) against the real running backend with real file uploads — this is a meaningfully closer approximation to a real browser than the previous session's per-file `eval()` approach (which doesn't reproduce how classic `<script>` tags share one global scope across a page, and produced false failures before switching methods). All 30 end-to-end checks and 7 edge-case checks passed. **Recommended**: one manual click-through when convenient — see "What to test first" below.

### How to start both servers

```bash
# Terminal 1 — backend
cd backend
source venv/bin/activate
python run.py
# Runs on http://localhost:5000 — confirm with: curl http://localhost:5000/health
# Uses backend/lease_portfolio.db (SQLite, gitignored) — currently empty/fresh

# Terminal 2 — frontend
cd frontend
python3 -m http.server 8080
# Open http://localhost:8080
```

Port already in use: `lsof -ti:5000 -ti:8080 | xargs kill -9`, then start again.

### What to test first

1. Open `http://localhost:8080` — you'll land on the **Dashboard**, empty (fresh DB).
2. Go to **Upload Leases**, drag in several PDFs from `backend/tests/*.pdf` at once (try `underpriced_downtown.pdf`, `missing_clauses_office.pdf`, `inconsistent_escalation.pdf` for the most interesting risk flags) — confirm the batch reports per-file success.
3. Back on **Dashboard**: confirm the metrics tiles and the risk-indicator column per row.
4. Click a lease row → **Lease Detail**: confirm the risk panel, try inline-editing a field, try "Ask About This Lease."
5. Go to **Expirations**: confirm leases are bucketed sensibly.
6. Go to **Compare**: select 2+ leases, confirm the benchmark badges.
7. Go to **Ask a Question**: try the example chips, then a free-form question.
8. Go to **Portfolio Report**: confirm it previews and prints/downloads.
9. Try uploading a corrupted/empty file — confirm a clear per-file error, not a crash.

---

## What's Built

### Backend (`backend/app/`)
- `api.py` — Flask routes: stateless `/extract`; persisted `/leases` (+ batch, detail, delete, amendments); portfolio analysis (`/portfolio/summary`, `/portfolio/timeline`, `/portfolio/risks`, `/leases/<id>/risks`, `/qa`, `/leases/compare`, `/leases/<id>/benchmark`, `/portfolio/rent-roll.csv`, `/portfolio/rent-roll.xlsx`, `/portfolio/report`); `/health`
- `pdf_extractor.py` — PyPDF2 + OCR fallback (unchanged from session 2)
- `field_extractor.py` — 15 fields (added `square_footage` this session), ordered regex strategies with confidence tiers, whole-document search, `find_all_date_candidates()` (new — powers cross-section date-conflict detection)
- `database.py` — SQLite persistence; leases + amendments, with an "effective" merged view
- `normalize.py` — parses extraction display strings into real numbers/dates for every downstream module
- `risk_analysis.py` — 7 rule-based risk checks, severity-ranked, each explaining itself with real numbers
- `qa_engine.py` — deterministic (no LLM) natural-language Q&A with grounded citations
- `portfolio.py` — portfolio-wide metrics and expiration timeline
- `comparison.py` — side-by-side lease comparison and portfolio benchmarking
- `rent_roll_export.py` — CSV and formatted Excel rent roll export
- `report.py` — self-contained printable HTML portfolio summary

### Frontend (`frontend/`)
- `index.html` + `styles.css` — sidebar-navigated multi-view app shell (collapsible desktop sidebar with category grouping; a single horizontally-scrollable row below 768px, not a wrapped multi-row bar — see DECISIONS.md)
- `api.js` — fetch wrappers for every backend endpoint
- `app.js` — view router, shared state, toasts, session stats, avatar helpers (`avatarHtml`/initials/deterministic color), live-activity polling + banner
- `upload-view.js`, `dashboard-view.js`, `detail-view.js`, `timeline-view.js`, `comparison-view.js`, `qa-view.js`, `report-view.js`, `alerts-view.js`, `discrepancies-view.js`, `trends-view.js`, `team-notes-view.js` — one file per view; each tab fetches only its own endpoint(s), not the full portfolio
- Uploads accept any backend-supported file type (PDF, Excel/CSV rent rolls, images), with a file-type icon (document/spreadsheet/image/etc.) shown per file before and after processing

### Tests (`backend/tests/`)
- Unit tests (self-contained, no server needed): `test_extraction.py`, `test_synthetic_accuracy.py`, `test_multipage_field.py`, `test_ocr_fallback.py` (mocked logic), `test_real_ocr.py` (real binaries, skips cleanly if unavailable), `test_risk_analysis.py`, `test_qa_engine.py`, `test_portfolio.py`, `test_comparison.py`, `test_rent_roll_export.py`, `test_report.py`
- Live API integration (backend must be running): `test_live_api.py`, `test_live_portfolio_api.py`, `test_security_hardening.py`
- `run_all_tests.py` — runs everything in one shot (`--live` to include the live API tests)
- Fixture generators: `create_sample_lease.py`, `create_commercial_lease.py`, `create_synthetic_leases.py`, `create_red_flag_leases.py`, `create_scanned_lease.py` (11 PDFs total)

## Current Limitations

- **Extraction is still regex-based** — same caveat as session 2; accuracy depends on the pattern library covering a given lease's actual phrasing.
- **No literal browser click-through** — still jsdom-based verification; no browser automation tool available in this environment.
- **Q&A coverage is intentionally bounded** — it answers questions matching a known intent (field lookup, sum/average, expiring-soon, count) and honestly says "I don't have a way to answer that yet" otherwise, rather than guessing. This is a deliberate tradeoff for the "not hallucinated" requirement, not an oversight — but it means genuinely open-ended questions aren't answerable.
- **Risk thresholds are fixed constants** — e.g. "25% below average = high severity" isn't currently tunable per portfolio or property type.
- **Single-value fields only** — unchanged from session 2; a lease with two legitimately different rent figures returns one.
- **Amendment date-conflict detection uses only the base lease's stored date candidates** — an amendment that itself restates a conflicting date wouldn't be cross-checked against the base lease's dates. Real-world amendments rarely restate the original commencement date, so this is a minor edge case, but worth knowing.
- **No production deployment setup** — Flask dev server, SQLite file, no accounts/session auth — appropriate for local/single-user use, not for hosting. (Session 4 hardened *error handling* — no stack traces or file paths leak to the client. Session 6 added a lightweight email-check gate on `/app` — see below — but that's still not real auth, and the admin waitlist endpoints remain intentionally unauthenticated. The dev-server/no-accounts architecture itself is unchanged, which is a separate, bigger scope.)
- **Real multi-user auth now exists (backend "Team collaboration infrastructure step 1"), but nothing above it yet** — a real `users` table (email/name/password_hash/role: admin|analyst|viewer) with bcrypt + signed-cookie sessions replaced the old single-hardcoded-admin login (`GET /auth/session`, `POST /auth/login`, etc.), and `frontend/admin/` authenticates against it. But `/team/members*` and `/assignments*` (team management UI, invite/roles settings, persistent lease/property/discrepancy assignment) don't exist yet — that's steps 3-4 of `.claude/plans/robust-launching-dewdrop.md`, not built. `frontend/app/` (the main portfolio app) still hasn't been switched onto the new auth at all — it still gates on the old self-reported-email `access-gate.js`, a separate mechanism from the real session admin/dashboard.html now uses; `api.js` still doesn't send `credentials:'include'`. "Team Notes"/the live-update banner there are still the self-reported-identity versions from before this backend work landed (derived roster from comment authors, `leaseAbstractionUserIdentity` localStorage, `/activity` polling) — not yet wired to real accounts.
- **OCR depends on `~/.miniforge3` being on PATH** — this is outside the project repo (in the home directory) and outside `requirements.txt` (system binaries, not Python packages) since it's a machine-level install, not a project dependency. If this environment is ever reset, re-run the Miniforge install steps in the Session 4 section above.

## Next Steps (prioritized)

### High Priority
1. **Test against real (anonymized) commercial leases**, now across the full portfolio workflow, not just extraction — this is still the highest-value next step.
2. **Install tesseract+poppler and run a real OCR test.**
3. **Manual browser click-through** to confirm the jsdom-verified behavior holds visually.

### Medium Priority
4. **Tunable risk thresholds** — expose the below-market/notice-period/escalation-spread thresholds as configuration rather than fixed constants, since "unusual" varies by portfolio and property type.
5. **Expand Q&A intent coverage** based on real usage — log unsupported questions to see what people actually ask.
6. **Residential lease variant** — unchanged need from session 2.
7. **Multi-value field support.**

### Low Priority / Nice to Have
8. Deployment setup (Docker, production WSGI server, a real database if usage grows past SQLite's comfortable range).
9. Real authentication: user accounts, passwords/OAuth, and sessions — for both `/app` (which as of Session 6 only has a lightweight self-reported-email gate, not real auth) and `/admin/waitlist/` + its endpoints (still fully unauthenticated). Multi-user support / per-user portfolio access control is a further step beyond that.
10. Configurable/brandable portfolio name and report letterhead (currently a placeholder in `report.py`).

## Dependencies

**System**: Python 3.7+, Tesseract OCR + Poppler (OCR fallback — not installed here)
**Python packages**: see `backend/requirements.txt` — added `openpyxl` this session (Excel export), everything else unchanged
**Frontend**: none — pure HTML/CSS/JS
**Test-only**: Node.js + jsdom in the session's scratch directory (not a project dependency) for frontend verification

## Project Structure

```
lease-abstraction/
├── backend/
│   ├── app/
│   │   ├── api.py
│   │   ├── pdf_extractor.py
│   │   ├── field_extractor.py
│   │   ├── database.py
│   │   ├── normalize.py
│   │   ├── risk_analysis.py
│   │   ├── qa_engine.py
│   │   ├── portfolio.py
│   │   ├── comparison.py
│   │   ├── rent_roll_export.py
│   │   └── report.py
│   ├── tests/
│   │   ├── create_sample_lease.py / create_commercial_lease.py
│   │   ├── create_synthetic_leases.py / create_red_flag_leases.py
│   │   ├── test_extraction.py / test_synthetic_accuracy.py
│   │   ├── test_multipage_field.py / test_ocr_fallback.py
│   │   ├── test_risk_analysis.py / test_qa_engine.py
│   │   ├── test_portfolio.py / test_comparison.py
│   │   ├── test_rent_roll_export.py / test_report.py
│   │   ├── test_live_api.py / test_live_portfolio_api.py
│   │   ├── run_all_tests.py
│   │   └── *.pdf (10 fixtures)
│   ├── venv/
│   ├── requirements.txt
│   ├── run.py
│   └── lease_portfolio.db (gitignored, created at runtime)
├── frontend/
│   ├── index.html / styles.css
│   ├── api.js / app.js
│   └── upload-view.js / dashboard-view.js / detail-view.js /
│       timeline-view.js / comparison-view.js / qa-view.js / report-view.js
├── CLAUDE.md
├── DECISIONS.md
├── PROGRESS.md
└── README.md
```
