# Implementation Decisions

## Sidebar navigation: grouping, collapse/expand, and transition polish

Pure interaction/organization polish on the existing sidebar, no
backend involved and no visual redesign -- same palette, same
typography, same `.nav-item`/`.brand` component shapes, just restructured
and given real transitions.

### Why the tooltip is JS, not CSS
`.sidebar` needed `overflow: hidden` added so the width-collapse
animation doesn't show a scrollbar flash mid-transition. That same
`overflow:hidden` would clip a pure-CSS `::after` tooltip trying to
render past the sidebar's own right edge in collapsed (76px) mode --
confirmed by reasoning through the CSS before writing any tooltip code,
not discovered as a bug afterward. `showSidebarTooltip()`/
`hideSidebarTooltip()` in `app.js` instead create one shared
`position:fixed` element appended to `<body>`, positioned via the
trigger's `getBoundingClientRect()` on `mouseenter` -- unaffected by
any ancestor's overflow/clipping, and only one DOM node is ever
created/reused rather than one tooltip per nav item.

### Why label collapse uses `max-width` + `opacity`, not `display:none`
Every piece of text that needs to disappear when the sidebar collapses
(brand wordmark, group headings, nav item labels, the alert count)
shares one `.nav-label` class, animated via `opacity` + `max-width`
rather than toggling `display`. `display:none` can't be transitioned at
all (an element with it either has a box or doesn't, nothing in
between) -- the max-width approach lets the label visibly shrink away
as part of the same motion as the sidebar's own width change, instead
of text vanishing instantly partway through the container's animation.

### Left accent bar: present but transparent by default
`.nav-item::before` (the left highlight bar) always exists in the DOM/
layout as a 3px-wide, zero-opacity-equivalent (transparent
background-color) element, not conditionally rendered only when
active/hovered. Reserving the space up front means the bar fading in on
hover/active never shifts any other content by appearing -- only its
own `background-color` transitions, nothing about layout does.

### The pre-existing 768px mobile breakpoint, and the bug found testing under it
This app already collapses the sidebar into a horizontal wrapped top
bar below 768px (`@media (max-width: 768px)`), written before this
pass for a flat list of `.nav-item` buttons as direct children of
`.sidebar`. The new grouping/scrolling wrappers (`.nav-scroll`,
`.nav-group`) broke that rule silently -- at 640px width the sidebar's
own middle was blank, most nav buttons not rendering at all, discovered
only by actually resizing the viewport and screenshotting, not by
reading the new CSS and assuming it composed cleanly with the old rule.
Root cause: the mobile rule's `.nav-item { flex: 1 1 auto }` expected
`.nav-item` to be a direct flex child of `.sidebar` (now
`flex-direction: row` at that width); with two intervening wrapper divs
neither participating in that row-flex layout as expected, the buttons
inside them weren't laid out as intended.

Fixed with `display: contents` on `.nav-scroll` and `.nav-group` at
that same breakpoint -- removes those two wrapper elements' own boxes
from layout entirely while keeping their children in the DOM, so the
buttons become direct flex children of `.sidebar` again, exactly
matching what the original mobile rule assumed. Also: forced
`.nav-label` back to fully visible at this breakpoint (a desktop
"collapsed" preference carried into a resize otherwise left icon-only
buttons in a context with no room for a separate mobile collapse
concept) and hid the collapse toggle entirely (meaningless once the
sidebar's shape itself already changes for mobile). Verified at 640px/
500px/375px and the specific edge case of collapsing at desktop width
then shrinking the window -- labels correctly reappear, and widening
back out correctly restores the desktop collapsed preference rather
than silently losing it.

## Alerts UI, investment memo export UI, and portfolio health score UI

Three separate frontend asks, arriving mid-session while the backend
for each landed in parallel (`578ecd8`, `9b887fa`, `6b5f800`) -- each
built by reading the actual committed endpoint first via `git log`/
`git show`, never guessed at.

### Alerts: "unread" = the backend's real `active` status, not a new flag
No read/unread concept exists in the `alerts` table -- only `active`/
`dismissed`/`auto_resolved`. Rather than inventing a client-only "read"
flag (which would either drift from what the team actually did, or
need its own fake persistence), the badge counts `active` alerts and
Dismiss is the one real action, doing double duty as both "acted on"
and "read." Same identity convention as discrepancy resolutions/
comments (self-reported name, `getUserIdentity()`/`setUserIdentity()`
in `app.js`) -- Dismiss reuses it rather than asking for a name again.

Generation (`POST /alerts/generate`) has no scheduled backend trigger
yet, so the frontend calls it itself -- once at app boot (for the nav
badge, so it's never far from fresh even without a visit to the Alerts
view) and again on every Alerts-view load/refresh. Documented safe by
the backend to call this often (idempotent against unchanged data).

**Real-data finding, not fixed here**: live-testing surfaced 357 active
alerts against the shared dev database, the bulk of them
`new_discrepancy` alerts for discrepancies whose lease had since been
deleted. The very next backend commit (Portfolio Health Score)
independently found and partially fixed the same root cause (a schema
bug that had silently corrupted 343 discrepancy rows) -- but only in
the health score's own counting logic, not in `alerts.py`'s
`_detect_new_discrepancy_alerts`, which still calls
`database.list_discrepancies(status="open")` unfiltered. The Alerts
feed likely still surfaces one alert per orphaned row. Flagged in
PROGRESS.md as a probable remaining backend gap rather than patched
here (backend logic, not this pass's file). The by-severity summary
strip at the top of the Alerts view exists specifically because this
real volume, not a contrived one, would otherwise read as exactly the
"raw log dump" the feature was asked not to be.

### Investment memo export: no section toggles, because none exist server-side
The options screen offers format (PDF/Excel) and, for a property-scoped
export, an optional T12 attachment -- not per-section include/exclude
checkboxes, because `build_investment_memo_data` always returns every
section (key terms, discrepancies, T12, rollover). Showing toggles that
don't actually change the request would be a UI that lies about what
it does; the screen states what's included as plain text instead.

**Real bug, caught by testing the actual download**: `Content-
Disposition` isn't readable via `response.headers.get()` on this
cross-origin request -- the backend's `CORS(...)` call has no
`expose_headers`, and that header isn't on the small always-exposed
CORS allowlist by default. `filenameFromResponse()`'s header read
silently returned `null` every time (confirmed by logging it live, not
assumed from reading the CORS config alone). Fixed client-side: the
same scope label already known to the modal (`this.scopeLabel`) is
sanitized the identical way the backend's own `safe_name` does
(`api.py`), producing the real descriptive filename without needing
the header at all. Not filed as a "please expose the header" backend
ask, since the client-side fix is strictly sufficient and doesn't
depend on a CORS config change landing first.

### Portfolio health score: breakdown ordered by actual drag, not fixed order
The four components render in the fixed order the backend returns them
in its JSON, but the UI re-sorts them by `(100 - score) * weight`
(descending) before display -- the component actually costing the most
points reads first, not whichever the backend happened to compute
first. A suggestion line only appears below a component scoring under
80, so a portfolio that's fine on 3 of 4 axes doesn't get three
unnecessary "here's how to improve" nags under things that aren't
actually a problem -- matches the "actionable, not alarming" brief:
only the real drag gets a call to action, and the Unresolved
Discrepancies one links directly into the new Alerts view rather than
just naming the problem.

Verified against three genuinely different states by changing the
actual database between screenshots (empty portfolio -- confirmed
`score: null`/`rating: "No Data"` renders as a real empty state, not a
0/100; then two different populated states, 87.3 and 74, the second
specifically chosen live because the alert-seeding data from the same
session had 10 open discrepancies on 4 leases, driving that component
down and reordering the breakdown to put it first) -- not screenshotted
once and assumed to generalize.

## Acquisitions-grade UI: click-to-verify, discrepancy resolution modal, portfolio trends, team notes

The frontend half of the same four-item batch as the "Acquisitions-
grade infrastructure" entry below — that entry's backend work landed
mid-session, in parallel, as expected (the user confirmed a backend
session was building it concurrently). Rather than building a
frontend-only approximation and leaving integration as follow-up work,
each of the four pieces below was rewired to the real endpoint the
moment it landed, verified against it live, and only left as a
client-side stopgap where no backend endpoint exists at all (there
isn't one, anywhere in this batch, by the time this entry was
written).

### Feature 1 scope call: don't touch the Lease Detail view's citations

CLAUDE.md's quality bar states every extracted field must show its
source — the Lease Detail view already does this, always-visible,
inline (`detail-view.js`'s `.field-source` block). The ask was to make
every number in the app "clickable, opening a clear view" of its
source. Read literally, that could mean collapsing the Detail view's
inline citation behind a click too, matching the rest of the app. Not
done — an always-visible citation is strictly more trustworthy than
one requiring a click, and hiding it to be consistent with newly-added
click affordances elsewhere would be a regression dressed up as
consistency. The new `verify-popover.js` component was instead applied
only to the places that had NO source display at all before this pass:
portfolio dashboard tiles, the Rent Roll rollup table, the Comparison
table, and the T12 cross-check panel.

Two popover modes: `showSource()` for one field's own citation (used
on Rent Roll/Comparison table cells, via `AppState.leases` — already
loaded with full `extracted_fields` including `source`, confirmed by
reading `_lease_summary()` in `api.py`, so no extra fetch is needed),
and `showAggregate()` for a portfolio-level number, which lists the
contributing leases (same already-loaded data) rather than fabricating
a single citation for a sum/average that was never extracted from one
document. Clicking a lease in that list navigates to it, where its own
real citation is already visible.

### Feature 2: built as a localStorage stopgap first, then fully rewired

At the point this pass started building the discrepancy-resolution
modal, `backend/app/discrepancies.py` did not exist yet — no stable
discrepancy ID, no resolve/reopen endpoint, nothing to persist a
resolution against. Rather than waiting, the modal was built complete
and testable against a localStorage-only resolution store (keyed by
the mismatch's natural key: `rent_roll_lease_id:lease_document_id:field`),
clearly labeled in the UI as "saved to this browser only, not yet
synced to your team." Partway through this same session, the backend
batch's discrepancy-persistence commit landed
(`5e75b26 Add discrepancy resolution system`). The modal was then
rewritten to call the real `POST /discrepancies/<id>/resolve`/`/reopen`
endpoints directly — every mismatch object returned by
`/portfolio/rent-roll-reconciliation` and `/portfolio/t12-reconciliation`
already carries `discrepancy_id`/`resolution_status`/`resolution`
inline (see `sync_rent_roll_reconciliation`/`sync_t12_reconciliation`),
so the modal just acts on that id — no separate lookup needed. The
localStorage code was deleted entirely, not left behind as a fallback;
a resolution that isn't actually shared with the team is a worse user
experience than a clear error, not a safer one.

Generalized to cover the T12 cross-check panel (Upload view) too, once
that endpoint started returning `discrepancy_id`/`t12_source` (the
latter had been silently dropped by `compute_t12_reconciliation`
before the backend's audit-trail-adjacent fix) — same modal, a second
call site, `sourceNote` added as an alternative to `source` on a
"side" for the rent-roll figure, which is an aggregate across however
many leases matched that property, not a single citation.

### Feature 3: no portfolio-wide trends endpoint exists — merged client-side

`GET /portfolio/property-trends` (the backend batch's item 3) is
scoped to one building at a time (`?property_address=X`); there is no
portfolio-wide equivalent. For the Trends view's "All Properties"
selection, this pass fetches that endpoint once per distinct building
address found across the loaded leases and merges the results
client-side (`_mergePropertyTrends` in `trends-view.js`) — string-
concatenating unit lists and turnover events, summing the by-month/
by-year rollover-pattern histograms. Straightforward because each
building's trends are already independent of every other's; flagged
here rather than left silent since a portfolio-wide backend endpoint
would be a more efficient way to get the same answer if this feature
sees real usage at portfolio sizes where N sequential-ish fetches
matters.

Rollover Risk Timeline (forward-looking, unrelated to the
property-trends endpoint) still uses the real portfolio-wide
`/portfolio/rollover` response for "All Properties," and only falls
back to a client-side recomputation (`computeRolloverBuckets`,
deliberately mirroring `portfolio.py`'s `compute_rollover_schedule`
bucket-by-bucket, including its exact risk thresholds) when one
specific property is selected, since that endpoint also has no
per-property filter.

Chart rendering is hand-rolled inline SVG (`renderBarChart`), not a
charting library — this app has had zero JS dependencies until now,
and introducing one would be the project's first; confirmed with the
user as a deliberate choice before building rather than defaulted to.

### Feature 4: one shared identity, not one localStorage key per feature

Team Notes (`comments.js`) is a single widget shared by the Lease
Detail sidebar and the Discrepancy modal's "Discussion" section,
rather than two separate implementations. It reads/writes the same
`getUserIdentity()`/`setUserIdentity()` pair now in `app.js`, which
also replaced the Feature 2 modal's own separate
`leaseAbstractionResolverName` localStorage key from its earlier
build. One name, cached once, reused everywhere a self-reported
identity is needed in this app — matching the backend's own choice to
use one `resolved_by`/`author_name` convention across resolutions and
comments rather than two.

### Two bugs found via live-browser verification (not caught by static review)

1. **Test-harness stale cache, not an app bug.** The hand-rolled CDP
   test client reused one Chrome profile directory across repeated
   navigations within the same session; Chrome's disk cache kept
   serving an old `detail-view.js` even after it was edited on disk,
   making `LeaseDetail.loadComments` look undefined mid-debugging
   before the actual cause (stale cache, not stale code) was found.
   Fixed with `Network.setCacheDisabled(true)` in the CDP client, not
   by touching any app file. Documented here because it cost real
   debugging time and would trip up the same way again otherwise.
2. **Real CSS bug**: `.trends-legend-line` still carried
   `display:flex; align-items:center` from an earlier version of the
   Tenant Turnover summary line that rendered colored swatches next to
   short labels. Once that line became a single sentence
   (`<strong>0</strong> tenant turnover events...`), the flex layout's
   whitespace handling collapsed the space between the `<strong>` tag
   and the word after it, rendering as "0tenant" in a real screenshot
   — not something a static read of the template string would have
   caught, since the space is right there in the source. Fixed by
   dropping the now-unnecessary flex layout; `.trend-legend-swatch`
   (now unused) was deleted rather than left as dead CSS.

## Acquisitions-grade infrastructure: audit trail, discrepancy resolution, portfolio history, collaboration

Four backend systems, requested together as the next step from "useful"
to something an acquisitions team can't work without: (1) a full,
queryable source-chain audit trail on every extracted field, (2) a real
discrepancy-resolution workflow instead of re-reading the same flag
every time, (3) permanent historical records with trend queries per
property, (4) team comments/notes on leases and discrepancies. Built
sequentially, each with its own data model, tests, and live
verification, per explicit instruction. Sub-entries below cover each.

### Identity model for resolutions/comments: self-reported name, not real accounts
**Status: decision confirmed with the user before building anything.**
This app has no real multi-user account system anywhere -- only a
single hardcoded admin login (`auth.py`) and a client-side "self-
reported email" access gate that isn't even sent to the backend on API
calls (confirmed by reading `access-gate.js`/`api.js` directly). Asked
directly rather than guessed: comments and discrepancy resolutions are
attributed via a free-text `resolved_by`/`author_name` string the
caller supplies with each request -- no password, no accounts table,
backend trusts it as-is. This matches the existing product philosophy
exactly (the waitlist access gate is already self-reported, unverified
email) and needs zero new auth infrastructure. If/when real per-user
login exists, these fields become natural candidates to populate from
the authenticated session instead of a request body, without a schema
change.

### Item 1: Full audit trail

**What already existed vs. what was missing.** Every extracted field
already carried a `source` citation when it had a value -- PDF-derived
fields as `{"page": N, "quote": "..."}` (`field_extractor.py`),
rent-roll-imported fields as `{"row": N, "file": "...", "quote": "..."}`
(`rent_roll_import.py`) -- so the underlying data was already there.
What was missing: (a) no verification this invariant actually holds
across every real extraction pathway rather than just being true by
convention, (b) no way to query it -- a human had to open the lease
detail JSON and find the field themselves, (c) no lineage across
amendments -- `get_effective_fields()` already correctly picks the
latest amendment's non-null value, but silently discarded which
document (base lease vs. which amendment) that value came from and
what the base lease originally said before being overridden.

**Verification, not just trust.** `test_audit_trail.py` runs the real
extraction pipeline (`FieldExtractor`, not a mock) against all 9 real
PDF fixtures this project has, and the real rent-roll importer against
all 6 PMS-format fixtures (Yardi CSV+XLSX, AppFolio, RealPage, MRI,
Buildium), asserting for every field that has a value: a source exists,
has a real quote, and has either a page or a row. Deliberately guards
against a vacuous pass (extraction silently returning nothing would
make every per-field check a no-op) by asserting a minimum count of
sourced fields found overall (203 across both pathways) -- a test that
can't fail because there was nothing to check isn't a real check.

**New: `database.get_field_source_chain(lease_id, field_name)`.**
Returns the effective value/source/confidence/origin document for one
field, PLUS the full history across the base lease and every
amendment -- not just the winner. Deliberately built as a fresh,
read-only derivation (re-walking `get_lease` + `get_amendments`
directly) rather than by modifying `get_effective_fields()`'s existing
merge output, so every existing consumer of that function (portfolio
metrics, risk analysis, exports, the Q&A engine, comparison) keeps
its exact current dict shape -- no risk of a new key silently breaking
an existing exact-shape assertion (e.g. `test_rent_roll_export.py`'s
cell-by-cell diff).

**New endpoint: `GET /leases/<id>/fields/<field_name>/source`.** 400
for an unrecognized field name (lists the valid 15), 404 for a
nonexistent lease, otherwise the full chain above. Live-verified
end-to-end (`test_live_audit_trail_api.py`, 20/20 checks against the
real running server, not `test_client()`): a real PDF upload's
page+quote citation, a real amendment overriding `tenant` and the
chain correctly showing both the base lease's original value (marked
non-effective) and the amendment's (marked effective), the 400/404
paths, and a real rent-roll-imported lease citing row+file instead of
page. Full suite 40/40 including live tests.

### Item 2: Discrepancy resolution system

**The core problem: none of this project's discrepancies have ever had
a stable identity.** Single-lease risk flags (`risk_analysis.
analyze_lease_risks`), cross-lease mismatches
(`compute_cross_lease_mismatches`), rent-roll-vs-lease-PDF
reconciliation (`compute_rent_roll_reconciliation`), and rent-roll-vs-
T12 reconciliation (`compute_t12_reconciliation`) are all computed
fresh, in memory, on every request -- no database row, no id, nothing
a "resolved" flag could attach to. Building resolution required first
inventing a way to recognize "the same real-world discrepancy" across
repeated computations, since the numbers involved (a rent gap
percentage, a dollar difference) shift slightly every time underlying
data changes even when the disagreement itself is the same one a human
already looked at.

**Data model** (`database.py`): two new tables. `discrepancies` --
one row per distinct discrepancy, identified by a deterministic
`natural_key` string (never derived from the rendered message or
dollar amounts, only from identifying fields: lease id(s), category,
field) with a `status` ('open'/'resolved') and the latest computed
snapshot (`details`, a JSON blob of the full flag/mismatch payload).
`discrepancy_resolutions` -- an append-only permanent log, one row per
resolve/reopen action (`action`, `correct_source`, `note`,
`resolved_by`, `resolved_by_email`, `created_at`) -- nothing is ever
overwritten or deleted, satisfying "permanently logged... never lost"
literally: a discrepancy resolved, reopened, and resolved again keeps
all three entries.

**Natural keys, per discrepancy type** (`app/discrepancies.py`):
- `lease_risk_flag`: `{lease_id}:{category}:{field}:{occurrence_index}`
  -- the occurrence index (not just category+field) exists because a
  single lease can legitimately raise more than one flag with the same
  category AND field (`_check_date_range` and `_check_date_candidate_
  conflicts` can both fire on `category="date_inconsistency",
  field="lease_end_date"` for the same messy document) -- confirmed
  this collision is real, not hypothetical, and covered by
  `test_sync_lease_risk_flags_same_category_field_gets_distinct_
  natural_keys`. The index is computed over `analyze_lease_risks`'
  own output order, which is deterministic for the same input (a fixed
  sequence of checks, then a stable sort).
- `cross_lease_mismatch`: the SORTED `(lease_id, other_lease_id)` pair
  plus field -- deliberately NOT keyed by whichever lease's flag list
  happens to be rendered first, since the same mismatch appears twice
  (once phrased from each lease's own perspective, see `_cross_lease_
  flag_pair`). This makes viewing it from either lease resolve to the
  SAME discrepancy row, verified directly
  (`test_sync_cross_lease_mismatch_dedupes_across_both_leases_
  perspectives`: resolving from lease A's list is immediately visible
  as resolved from lease B's list too).
- `rent_roll_reconciliation`: `{rent_roll_lease_id}:{lease_document_
  id}:{field}` -- both ids are real, permanent lease rows, so this is
  the cleanest of the four.
- `t12_reconciliation`: address-only (`_normalize_building_address`),
  since a T12 upload is never persisted anywhere (by original design --
  see the "Rent-roll-vs-T12 cross-check" entry). **Honestly documented
  limitation, not silently assumed away**: a DIFFERENT T12 file
  uploaded later for the same building collides onto the same
  discrepancy row, since there's no persisted T12 upload to key against
  instead -- the coarsest identity of the four, a direct consequence of
  T12s being intentionally stateless. Only synced when a real
  discrepancy is flagged, or one already exists for that address
  (an unflagged check with no prior history creates nothing --
  verified: `test_sync_t12_reconciliation_only_persists_when_flagged_
  or_already_tracked`).

**Resolution never overwrites the underlying computation.**
`upsert_discrepancy` refreshes the latest-seen snapshot every time a
flag recomputes, but deliberately leaves `status` untouched --
recomputing must never silently un-resolve or re-resolve something a
human already decided. The read-side wiring (`_lease_risks`,
`/portfolio/risks`, `/portfolio/rent-roll-reconciliation`,
`/portfolio/t12-reconciliation`) all call the matching `sync_*`
function before returning, which merges `discrepancy_id`/
`resolution_status`/`resolution` directly into each flag/mismatch dict
-- this is what actually delivers "resolving it once means no more
manual re-reads": the existing risk/reconciliation views show resolved
status automatically, with zero new endpoint the caller has to know to
hit.

**New endpoints**: `GET /discrepancies` (filterable by `status`,
`lease_id`, `type`), `GET /discrepancies/<id>` (detail + full
resolution history), `POST /discrepancies/<id>/resolve` (body:
`correct_source`, `note`, `resolved_by`, optional `resolved_by_email`
-- all three required fields validated non-empty, 400 otherwise;
always allowed regardless of current status, so a second reviewer
confirming or updating the note isn't rejected), `POST /discrepancies/
<id>/reopen` (body: `note`, `resolved_by`; 400 if the discrepancy isn't
currently resolved -- reopening something already open is a no-op that
would just clutter the log for no reason).

**A real bug found while writing the live test, not a hypothetical
one**: `activity_log.lease_id` has a genuine foreign key to `leases`.
A discrepancy's own `lease_id` can now outlive the lease it once
pointed at -- deleting a lease does NOT delete or renumber the
discrepancies that reference it (a deliberate design choice: a
discrepancy is a permanent record, and `discrepancies.lease_id`/
`related_lease_id` were built WITHOUT a foreign key for exactly this
reason, unlike every other FK'd column in this schema). Calling
`resolve`/`reopen` on a discrepancy whose lease had since been deleted
crashed `insert_activity` with a raw `IntegrityError` the first time
this was actually exercised end-to-end. Fixed with `_activity_lease_id`
in `api.py`, which only passes `lease_id` through to the activity log
if that lease still exists, logging the activity with no lease link
otherwise rather than either crashing or blocking the resolution
itself from succeeding.

**Verified**: `test_discrepancies.py` (17 tests: upsert/list/resolve/
reopen CRUD, natural-key collision and cross-lease dedup, all 4 API
routes) and `test_live_discrepancies_api.py` (23 checks against the
real running server: a real PDF upload's real missing-clause flags,
resolve, confirm the resolution persists across a completely fresh
`GET /leases/<id>/risks` call, reopen, the 400/404 paths). Full suite
42/42 including live tests.

### Item 3: Portfolio history & trends

**The underlying data was already permanent -- the gap was that it
wasn't queryable as a timeline.** `leases` has always been append-only:
a lease PDF upload and a rent-roll import both always INSERT a new
row; the only UPDATE path in the entire schema is a display_name
rename via PATCH. So every rent-roll re-import a firm has ever done
has always been silently accumulating a real historical record --
nothing new had to be persisted for this item. What was actually
missing was the ability to query that accumulated history as a trend,
which is what `app/portfolio_history.py` (pure read/aggregation, zero
new tables) and the new `GET /portfolio/property-trends` endpoint
provide.

**Two different address-matching granularities, reused deliberately
from existing code rather than invented fresh**: building-level
matching (`_normalize_building_address`, suite-insensitive -- same
convention `compute_loss_to_lease`/`compute_t12_reconciliation` already
use) decides which historical records belong to "this property" at
all. Unit-level matching (`_normalize_address`, suite-INCLUSIVE -- same
convention `compute_rent_roll_reconciliation`/`compute_cross_lease_
mismatches` already use) decides which records are the SAME unit's
history over time, for rent growth and tenant turnover specifically.
Using the building-level match for the unit-level trends would blend
different units' independent rent/tenant histories into one nonsense
timeline -- confirmed this distinction actually matters with
`test_rent_growth_different_units_tracked_independently` (two
different suites at the same building, opposite rent trends, tracked
as two separate unit timelines, not averaged together into a
meaningless number).

**Rent growth and tenant turnover are reported separately, on purpose,
even though they're related.** A rent change at the exact same
transition as a tenant change is a market reset at turnover; a rent
change with the SAME tenant is a scheduled escalation or renewal.
Collapsing both into one undifferentiated "rent grew X%" number would
hide which story actually happened. Every rent-growth transition
carries its own `tenant_changed` flag so a caller never has to guess
which kind of change they're looking at -- verified directly
(`test_rent_growth_flags_tenant_change_at_transition`: a real tenant
swap alongside a rent DECREASE, the honest opposite of the "growth"
name, deliberately chosen as a test case so the function is proven to
report what actually happened rather than what the feature's name
might imply).

**Rollover pattern is historical, not forward-looking -- deliberately
distinct from the existing `compute_rollover_schedule`.** That
existing feature (portfolio.py) already reports the CURRENT,
forward-looking expiration schedule from today. This is the opposite
direction: a building-level bucket of every lease_end_date this
building's full historical record has ever shown, by month and by
year, surfacing a pattern (e.g. a disproportionate cluster of
expirations in one calendar month across multiple years) that's only
visible at all because every past upload was retained -- exactly the
"something firms can't get anywhere else without redoing the work
manually" the request asked for.

**Honestly documented limitation, not silently avoided**: `DELETE
/leases/<id>` (`database.delete_lease`) is still a real hard delete --
deleting a lease also deletes its history from this feature, confirmed
directly (`test_deletion_removes_history_documented_limitation`).
Deliberately NOT changed to a soft-delete for this pass: doing so would
mean touching `get_all_leases`/`get_all_effective_leases`'s filtering
semantics, which every existing "current portfolio state" computation
in `portfolio.py` (metrics, risk analysis, WALT, tenant concentration,
loss-to-lease, every reconciliation) depends on -- a materially larger
and riskier change than this feature asked for, and one that would
touch dozens of already-tested, already-shipped code paths for a
concern (permanence through deletion specifically) that wasn't the
literal ask. Flagged here as a legitimate follow-up if permanence
through deletion turns out to matter in practice.

**New endpoint**: `GET /portfolio/property-trends?property_address=X`
-- 400 if the address is missing/blank, otherwise 200 always,
including zero matching records (an honest "no history yet," not an
error -- a real address with no data and a garbled/invalid address are
different situations, and only the second is a 400). Returns the raw
history timeline plus all three trend sections (`rent_growth`,
`tenant_turnover`, `rollover_pattern`) in one response, rather than
three separate endpoints -- kept the surface small since a UI
reasonably wants all three together for one property.

**Verified**: `test_portfolio_history.py` (18 tests covering all three
trend computations plus the combined endpoint) and
`test_live_portfolio_history_api.py` (15 checks against the real
running server, simulating the actual real-world workflow this feature
exists for: the SAME rent roll re-imported for the same property at
two different points in time, with a real +10% rent increase on the
same tenant correctly read as a renewal/escalation story, not a
turnover). Full suite 44/44 including live tests.

### Item 4: Collaboration layer

**Data model** (`database.py`): one new table, `comments` --
`lease_id`/`discrepancy_id` (exactly one set per comment, enforced at
the API layer rather than a SQL CHECK constraint, consistent with how
every other validation in this codebase is layered), `author_name`
(required), `author_email` (optional), `body` (required), `created_at`.
`lease_id`/`discrepancy_id` both carry real foreign keys with `ON
DELETE CASCADE` -- unlike `discrepancies.lease_id` (deliberately
un-FK'd in Item 2, since a discrepancy is meant to survive its lease
being deleted), a comment is a note ABOUT a specific lease or
discrepancy with no independent meaning once that thing is gone, so
cascading its deletion is the correct behavior here, not an oversight
of the Item 2 precedent. Verified directly
(`test_lease_comments_deleted_with_lease`).

**"Visible to the whole team" needed literally nothing extra to
build.** This app has no per-account data scoping anywhere (every
approved user already sees the same shared pool of leases -- see the
Session 14 pre-sale audit's blocker #1 in PROGRESS.md, still true
today), so a plain `GET` with no session-based filtering already IS
"visible to everyone on the account" by construction. Verified this
is genuinely true rather than assumed:
`test_comments_are_visible_regardless_of_which_client_posted_them`
(unit) and the live suite (two independent HTTP clients, no shared
cookie/session state, posting to the same lease -- a third, completely
fresh read sees both).

**Author identity**: exactly the self-reported-name/email convention
confirmed with the user at the start of this whole batch (see this
file's "Identity model for resolutions/comments" entry above) --
`author_name`/`author_email` are whatever the caller supplies in the
request body, trusted as-is, no accounts table.

**New endpoints**: `GET`/`POST /leases/<id>/comments`,
`GET`/`POST /discrepancies/<id>/comments` -- 404 for a nonexistent
lease/discrepancy on either verb, 400 if `author_name` or `body` is
missing/blank on POST. Comments are intentionally separate from
`discrepancy_resolutions` (Item 2's permanent resolve/reopen log,
which is a formal decision record with a required `correct_source`) --
a comment is a running discussion thread with no such structure, e.g.
"confirmed with the broker this is fine" without that being a formal
resolution action.

**Verified**: `test_comments.py` (8 tests: CRUD, cascade-delete, both
route pairs, cross-client visibility) and `test_live_comments_api.py`
(15 checks against the real running server: a real lease upload, real
missing-clause risk flags to comment on, two independent team members'
notes both visible to a third fresh reader, the 400/404 paths). Full
suite 46/46 including live tests.

## Proactive alerting system

A new, fifth backend system on top of the four above, requested as a
follow-up in the same session: instead of a human having to open the
app and go looking, scan the current portfolio for four specific
situations and persist a record of each one -- upcoming lease
expirations (30/60/90 days), newly detected discrepancies, rent
significantly below this portfolio's own internal market proxy, and
tenant concentration crossing a risk threshold.

### Reused, not re-derived

Every one of the four detectors calls an EXISTING computation rather
than re-deriving its own version of the same logic, which would risk
silently disagreeing with what the dashboard already shows for the
same thing: `compute_expiration_alerts` (already built, already
30/60/90-bucketed) for expirations; `database.list_discrepancies(status
="open")` (Item 2, this same session) for discrepancies;
`compute_loss_to_lease` (already built, explicitly the portfolio's own
internal best-achieved-rent proxy since there's no external market-
rate data source -- see that function's own docstring) for below-
market rent; `compute_tenant_concentration`'s already-defined
`TOP_TENANT_HIGH_RISK_PCT` constant (25%, borrowed from DOJ/FTC merger
guideline thresholds, not invented fresh) for concentration. An alert
is a NOTIFICATION about a condition computed elsewhere, not a second
parallel computation of the same fact.

### Data model: `alerts`, extending the natural-key upsert pattern from Item 2

Same `natural_key`-based identity/upsert approach as `discrepancies`
(see that section above), with one real addition: alert `status` is
`'active'` / `'dismissed'` / `'auto_resolved'`, not just active/
dismissed. A discrepancy always needs an explicit human resolve
action; an alert's underlying condition can genuinely clear on its own
(a lease gets renewed further out, a re-imported rent roll shows the
rent caught up, a tenant's share drops back under 25%) -- that's a
materially different situation from a human saying "I've seen this,
stop showing it to me," so it gets its own status rather than being
conflated with a manual dismiss.

`upsert_alert`'s status-transition rules, the actual core logic of this
feature: an `'active'` alert recomputing stays `'active'` (snapshot
refreshes); an `'auto_resolved'` alert whose condition recurs flips
back to `'active'` (it wasn't a human decision, so there's nothing to
silently overturn -- it's just true again); a `'dismissed'` alert NEVER
flips back automatically, no matter how many times the condition
recurs -- a human decision is never silently overturned by
recomputation, the same non-negotiable rule Item 2's discrepancy
resolutions already established. `generate_alerts()` auto-resolves any
previously-`'active'` alert whose natural key doesn't appear in the
current run's candidates -- scoped to only the 4 alert types this pass
manages (`_MANAGED_ALERT_TYPES`), specifically so a future 5th alert
type added by different code can't get every one of its own alerts
incorrectly auto-resolved just because this generation pass never
asked about it.

### A real bug found and fixed before shipping: the tenant-concentration threshold

The first version alerted at BOTH `TOP_TENANT_HIGH_RISK_PCT` (25%,
severity high) AND `TOP_TENANT_MODERATE_RISK_PCT` (15%, severity
medium) -- reusing both of `compute_tenant_concentration`'s existing
thresholds seemed consistent at first. Writing the "healthy portfolio
produces zero alerts" edge case the request explicitly asked for
caught the real problem immediately: a healthy, evenly-diversified
5-tenant portfolio (20% each, a genuinely LOW-risk shape by any
reasonable read) alerted on all 5 tenants, since 20% clears the 15%
"moderate" bar. That's exactly the wrong behavior for a proactive
alerting system -- noisy on a healthy portfolio undermines trust in
every other alert it raises. Fixed by alerting only at the 25% bar
(severity always `high`), matching the concrete threshold the request
itself named as its example ("e.g. one tenant now >25%") rather than
inventing a second, noisier tier. Covered by
`test_tenant_concentration_evenly_split_stays_quiet` (must stay silent)
and `test_tenant_concentration_exactly_at_threshold_still_alerts`
(>=, not >, still fires exactly at 25%).

### `below_market_rent`'s severity thresholds are this module's own judgment call

`compute_loss_to_lease` deliberately reports raw loss-percentage
numbers with NO severity label of its own -- its docstring explains why
directly: an internal-proxy "market rate" (best-achieved rent at the
same building, not a real external comp) doesn't have a defensible
enough reference point to responsibly attach a risk level to. An alert
is a stronger claim than a raw metric, so this module defines its own
thresholds (`BELOW_MARKET_ALERT_HIGH_PCT` = 20%, `_MEDIUM_PCT` = 10%)
rather than retrofitting a label onto a function that intentionally
doesn't have one -- keeping that boundary intact means
`compute_loss_to_lease` still means exactly what its docstring says
everywhere else it's used (the dashboard panel, the property-trends
work), and only the alerting layer's own added interpretation lives
here.

### Idempotent by design, verified directly

`generate_alerts()` is meant to be called on a schedule (a cron job,
eventually) or manually -- re-running against unchanged data must
create zero new rows. Verified both in isolation
(`test_generate_alerts_is_idempotent`) and live against the real
running server (`test_live_alerts_api.py`: a second `/alerts/generate`
call creates 0, refreshes what's still true).

### Observed during live verification, not a bug: discrepancies/alerts accumulate across every past test run in this dev DB

Running the live alert test against the real dev server surfaced 281
already-`open` `new_discrepancy`-eligible discrepancies sitting in the
database, accumulated from every prior live-test session this whole
project has ever run (discrepancies are permanent records by Item 2's
own design -- test cleanup only ever deletes the LEASES it created,
never the discrepancies those leases generated, which is the entire
point of "permanently logged, never lost"). This is working exactly as
designed, not a bug -- caught a real bug in the LIVE TEST ITSELF, not
the app: an early version of `test_live_alerts_api.py` compared the
`/alerts/summary` digest's `active_count` against the length of an
UNFILTERED `GET /alerts` call, which naturally exceeds the active
count once any alert has been dismissed or auto-resolved, including
ones from unrelated prior runs. Fixed by comparing against
`GET /alerts?status=active` instead. Worth knowing for whoever
maintains this dev environment long-term: this database's discrepancy/
alert history will keep growing indefinitely unless a real cleanup/
archival policy is deliberately added later -- not needed yet at this
project's current scale, but flagged here rather than silently
building up unnoticed.

### New endpoints

`POST /alerts/generate` (no body -- runs all 4 detectors, upserts,
auto-resolves, returns a summary), `GET /alerts` (filterable by
`status`, `type`, `severity`, `lease_id`, sorted severity-first then
most-recently-seen -- a notification feed's natural reading order),
`GET /alerts/<id>`, `GET /alerts/summary` (a digest of active-alert
counts by severity/type, explicitly designed for a future notification-
feed header or email digest -- email delivery itself is explicitly out
of scope for this pass, per the request), `POST /alerts/<id>/dismiss`
(body: `dismissed_by`, optional `note` -- same self-reported-identity
convention as discrepancy resolutions and comments).

### Verified

`test_alerts.py` (23 tests: CRUD status-transition rules, each
detector individually, the explicit "no alerts"/"many alerts at once"/
"resolved (auto)"/"dismissed (manual)" edge cases the request named,
all 5 routes) and `test_live_alerts_api.py` (26 checks against the
real running server: a real portfolio genuinely tripping all 4 alert
types via real rent-roll imports and a real messy PDF, the full
generate → dismiss → regenerate-stays-dismissed lifecycle, and
resolving the underlying discrepancy causing its alert to genuinely
auto-resolve). Full suite 48/48 including live tests.

## Investment memo export (PDF / Excel, per property or per portfolio)

A backend-generated, professional export meant to be attached to a
real investment committee memo or forwarded to a lender/partner who
will never open this app -- key lease terms, flagged discrepancies AND
their resolutions, a T12 cross-check summary, and a rollover risk
summary. Requested with explicit instructions to design the data
structure first, then generate a sample and review it critically
before calling it done -- that review caught a real, serious bug (see
below), not a hypothetical one.

### Built on existing infrastructure, not from scratch

Two existing modules already did adjacent work, and this reuses their
established machinery rather than inventing new patterns:
`summary_memo.py` (a one-lease or whole-portfolio "everything,
briefly" PDF memo, built for the same "forward this to someone outside
the app" purpose) supplies the low-level reportlab building blocks --
`_header_flowables`, `_key_terms_table`, `_confidence_summary_
flowables`, `_build_pdf`, the shared `_styles`/color constants -- all
imported directly rather than duplicated, so this new document renders
in the exact same visual language as every other PDF this app
produces. `rent_roll_export.py`/`sheets_export.py` establish the "one
shared computation, multiple export formats" convention this module
follows too: `build_investment_memo_data()` is the single canonical
data structure BOTH `generate_investment_memo_pdf` and `generate_
investment_memo_excel` render from, so the two formats can never
disagree about what they're reporting for the same request (verified
directly: `test_excel_has_all_five_sheets_with_correct_dedup` and the
live suite both check the Excel and PDF outputs agree on the same
numbers for the same scenario).

### What's genuinely new: property-level scope, and discrepancy RESOLUTIONS not just flags

Neither `summary_memo.py` nor `report.py` can produce "just this one
building" -- both are per-lease or whole-portfolio only. This adds a
`property_address` scope (building-level matched via `_normalize_
building_address`, same convention `compute_loss_to_lease`/`compute_
t12_reconciliation` already use) alongside the existing whole-
portfolio option. And where `summary_memo.py`'s "Top Risk Flags"
section shows `risk_analysis`'s live-computed flags with no resolution
status, this document reads from Item 2's discrepancies table instead
-- an outside reader sees not just "here's a red flag" but "here's
what we found, here's who resolved it, when, and why," which is the
actual point of bringing something to an IC: demonstrating the
diligence was done, not just that a question exists.

### A real, serious bug found during the critical-review pass, not a hypothetical one

Generating the first sample export against a realistic scenario (a
real PDF lease AND a real rent-roll snapshot on file for the exact
same unit -- precisely the situation rent-roll reconciliation exists
to catch) surfaced a genuine data-accuracy problem: `compute_
portfolio_metrics`, `compute_walt`, and `compute_rollover_schedule` all
just sum over whatever's in the scoped lease list, with zero
deduplication logic anywhere for "the same unit represented twice."
Total monthly rent for a 2-unit property showed $21,250 instead of the
real $15,250 -- Suite 110's $6,250 lease PLUS its own $6,000 rent-roll
cross-check snapshot, double-counted as if they were two different
units. The T12 cross-check section had the identical bug (passed the
undeduped lease list into `compute_t12_reconciliation`), which made a
genuinely healthy property (2.7% real variance) render as "FLAGGED —
MATERIAL DISCREPANCY" at a fabricated 30.2% gap. Both would have been
materially wrong numbers in a document specifically meant for a real
lender or investment committee -- exactly the kind of error this
project's "never guess, never silently produce a misleading number"
quality bar exists to catch, and it was only caught because the
request explicitly asked for a self-generated sample to be reviewed
critically before shipping, not assumed correct from the design alone.

**Fix**: `_dedupe_for_financial_computation()` -- prefers the real PDF
lease over a rent-roll snapshot when both exist for the exact same
unit (`_normalize_address`, suite-inclusive); among multiple records
of the SAME source type for one unit, keeps whichever was uploaded
most recently. Applied to every SUMMED figure (portfolio metrics,
confidence tally, WALT, rollover schedule, T12 cross-check) -- but
deliberately NOT to the "Key Lease Terms" section, which still lists
every record on file, each labeled with its source ("Lease Document"
vs "Rent Roll Import — cross-check record, not counted in totals
above") so a reader understands why two entries for one unit might
appear rather than the duplicate being silently hidden. The Overview
section explicitly states how many records were excluded and why.
Covered by 4 dedicated tests (`test_dedupes_rent_roll_duplicate_of_a_
pdf_lease_for_financial_totals`, `test_dedupe_prefers_pdf_lease_
regardless_of_upload_order`, `test_dedupe_keeps_most_recent_when_
both_are_the_same_source_type`) plus the live suite's full end-to-end
version of the exact scenario that first caught it.

### T12: fresh upload preferred, falls back to the last persisted cross-check

The export routes accept an OPTIONAL `t12_file` alongside
`property_address` (multipart POST, not GET, since a file may be
attached) -- if given, computes a live `compute_t12_reconciliation`
right there (and this fresh result is what appears in the memo, though
deliberately NOT also synced into the discrepancies table from this
export path, to keep "generating a memo" and "running a reconciliation
check" as separate actions with separate intent). Without a fresh
upload, falls back to the most recently-seen PERSISTED
`t12_reconciliation` discrepancy for that property (Item 2 and the
alerting system both already populate this when a real mismatch was
found) -- so a memo generated without a file in hand still shows the
last known cross-check rather than nothing. Honestly reports
unavailable when neither exists, and portfolio-wide memos never offer
T12 at all (a T12 covers exactly one building by definition) --
verified directly rather than assumed
(`test_t12_unavailable_for_portfolio_scope`).

### New endpoints

`POST /portfolio/investment-memo.pdf` and `POST /portfolio/investment-
memo.xlsx` -- both accept the same optional multipart fields
(`property_address`, `t12_file`), return the file as a real
`attachment` download with a real filename. 400 if `t12_file` is
supplied without `property_address`, or if it's not a `.csv`/`.xlsx`.

### Verified

`test_investment_memo.py` (17 tests: the data structure's scoping/
dedup/T12-fallback logic, PDF and Excel rendering for both empty and
populated scopes, both routes, both error paths) and
`test_live_investment_memo_api.py` (22 checks against the real running
server: the exact real double-count scenario end to end -- a real PDF
upload, a real rent-roll import of the same unit, a real reconciliation
mismatch, a real resolution, a real T12 file attached to the export
request -- confirming the PDF and Excel outputs agree with each other
and correctly show the deduped, non-inflated numbers). Full suite
50/50 including live tests.

## Portfolio Health Score

A single, defensible 0-100 number (plus a letter rating) summarizing
how much a user can trust their portfolio's data RIGHT NOW -- meant to
be the number that makes someone check the app regularly, the way a
credit score or an uptime SLA number works. The full formula is
documented in `app/portfolio_health_score.py`'s module docstring (per
explicit instruction to document it clearly, not just implement it) --
summarized here.

**Explicitly NOT the same thing as the existing `compute_portfolio_
health`** (the dashboard's "morning glance" strip: verified-vs-needs-
review counts, renewal urgency, rent on the clock over the next two
windows). That function answers "what needs attention today." This one
answers a narrower, different question: "how much can I trust the DATA
itself, right now." Deliberately kept as two separate functions with
two separate names rather than merged or renamed to avoid confusion --
they measure genuinely different things and a caller wanting one
should never accidentally get the other.

**The formula**: a weighted sum of four 0-100 sub-scores --
Confidence Distribution (30%, reuses `compute_portfolio_confidence_
summary`'s existing high/medium/low/not_found tally with weighted
partial credit: high=1.0, medium=0.6, low=0.3), Source Verification
(25%, % of leases with every `CORE_FIELDS_FOR_COMPLETENESS` field
present AND zero fields flagged during extraction validation),
Unresolved Discrepancies (25%, a smooth diminishing-returns curve --
`100 / (1 + open_discrepancies_per_lease)` -- rather than a hard
cutoff, so it degrades gracefully instead of cliff-dropping at an
arbitrary count), and Data Freshness (20%, % of leases refreshed --
uploaded or amended -- within a configurable staleness window,
default 6 months). The weights are explicitly documented as this
module's own judgment call, not a market-tested standard -- same
honesty standard `compute_loss_to_lease`/`compute_tenant_concentration`
already hold their own thresholds to. An empty portfolio returns
`score: None, rating: "No Data"` -- an unscored portfolio is not a
known-zero one, the same convention every aggregate in `portfolio.py`
already follows.

**Tested against genuinely different portfolio states, per explicit
instruction** -- not just unit-level component checks:
`test_perfect_portfolio_scores_near_100_excellent` (every field found,
high confidence, zero discrepancies, uploaded today -- scores 95+,
"Excellent"), `test_messy_portfolio_scores_low_critical` (sparse
fields, low confidence, 6 real open discrepancies, uploads 400 days
stale -- scores under 40, "Critical"), `test_mixed_portfolio_scores_
in_the_middle` (half genuinely good, half genuinely bad -- lands
strictly between the two extremes, with the 50/50 split's arithmetic
directly verified, not just "somewhere in the middle").

### Two real, serious bugs found live -- neither reproducible by a fresh-temp-DB unit test

Both concern the Unresolved Discrepancies component specifically, and
both share the same root cause: `database.list_discrepancies(status=
"open")` is deliberately unscoped (Item 2's discrepancies are
permanent records, by design, that outlive the lease they were about).
A health score computed over an unscoped count of "every open
discrepancy this database has EVER accumulated" is not the same thing
as "how much can I trust the CURRENT portfolio" -- and this project's
own real dev database, after months of accumulated test runs, made
that gap concrete rather than theoretical.

1. **Lease-scoped discrepancies whose lease no longer exists.**
   `lease_risk_flag`/`cross_lease_mismatch`/`rent_roll_reconciliation`
   discrepancies from leases deleted in prior sessions kept counting
   against the CURRENT portfolio's score forever. Fixed by only
   counting a lease-scoped discrepancy if its `lease_id`/`related_
   lease_id` still appears in the current lease set
   (`test_discrepancies_from_deleted_leases_do_not_count_against_a_
   healthy_current_portfolio`).

2. **Portfolio-wide discrepancies (no lease_id at all) whose subject no
   longer exists.** `tenant_concentration`/`t12_reconciliation`
   discrepancies are facts about a TENANT NAME or an ADDRESS, not a
   lease row -- fix #1 didn't touch these at all, since they were
   never lease-scoped to begin with. 351 of them had accumulated live,
   from tenant names and properties used across this whole project's
   entire test history, none of which exist in the current portfolio.
   Fixed by requiring the tenant_concentration's tenant (normalized)
   or the t12_reconciliation's address (normalized, building-level) to
   still appear somewhere in the current portfolio
   (`test_portfolio_wide_discrepancy_counts_only_if_its_subject_is_
   still_current`). Together, fix #1 and #2 dropped the live test's
   open-discrepancy count from 351 (an empty CURRENT portfolio showing
   351 "open" discrepancies!) to the real, current number.

### A THIRD bug, upstream of both: `discrepancies.lease_id` had a live `ON DELETE SET NULL` foreign key nobody meant to still be there

Debugging bug #1 above (resolving real discrepancies wasn't moving the
score at all) traced back further than expected: the real dev database
still had the ORIGINAL `discrepancies` table schema -- including
`FOREIGN KEY (lease_id) REFERENCES leases(id) ON DELETE SET NULL` --
from before that constraint was deliberately removed earlier this same
session (see Item 2's entry above: "a discrepancy is a permanent
record, and `discrepancies.lease_id`/`related_lease_id` were built
WITHOUT a foreign key for exactly this reason"). `CREATE TABLE IF NOT
EXISTS` never retroactively fixes an ALREADY-EXISTING table's
constraints, so that removal only ever took effect for brand-new
databases (every unit test's fresh temp DB) -- the real, long-lived
dev database kept the old FK the whole time, and kept silently
NULLING OUT `lease_id` on 343 real discrepancy rows every time a lease
they referenced was deleted, discarding exactly the information a
permanent record exists to keep. This was a real, live, silently-
corrupting bug that had been happening for the entire rest of this
session without being noticed, until the health score's own scoping
logic made its effect visible.

**Fixed with a real migration**, `database._migrate_discrepancies_
table_drop_lease_fk`: detects an already-existing `discrepancies` table
still carrying the old FK (`PRAGMA foreign_key_list`) and rebuilds it
via SQLite's standard rename/recreate/copy/drop dance (SQLite has no
`ALTER TABLE ... DROP CONSTRAINT`), with `PRAGMA foreign_keys OFF` for
the duration so SQLite doesn't try to "helpfully" rewrite `comments`'s
own FK text mid-rebuild (verified directly that `comments.discrepancy_
id`'s FK still enforces correctly against the rebuilt table afterward,
not just assumed). Idempotent and safe to run on every `init_db()` --
a no-op once already migrated, verified by running it twice against
the same copied database file. Confirmed live: 390 discrepancy rows,
zero data loss, `PRAGMA integrity_check` clean. The 343 already-lost
`lease_id` values from before this fix are genuinely gone (there's no
way to recover which lease a NULL used to point to), which is exactly
why bug #1's fix treats a lease-scoped discrepancy with a null
lease_id as "can't verify relevance, exclude" rather than "count it
anyway" -- the honest response to unrecoverable data, not a guess.

### New endpoint

`GET /portfolio/health-score?staleness_threshold_months=6` (optional,
defaults to 6) -- 400 for a non-numeric or non-positive threshold.

### Verified

`test_portfolio_health_score.py` (14 tests: all four components
individually, the three portfolio-state scenarios, both migration-
adjacent scoping bugs, the route) and `test_live_health_score_api.py`
(18 checks against the real running server: an empty portfolio, a real
clean lease, a real messy fixture with real open discrepancies,
confirming the score measurably drops when they're added and
measurably recovers when they're resolved -- the exact check that
originally caught bugs #1/#2/#3 above). Full suite 52/52 including
live tests.

### Summary: all four items shipped this pass

Full audit trail (item 1), discrepancy resolution (item 2), portfolio
history & trends (item 3), and the collaboration layer (item 4) are
all built, tested (unit + live against the real running server), and
committed as four separate milestones. Backend-only, as scoped --
frontend surfaces for all four are a natural next step (a concurrent
session was already building a discrepancy-resolution modal and a
"verify" popover while this batch was in progress, per this session's
own note when that was first noticed).

## Production-Readiness Hardening (session 4)

A focused ~1-hour pass: real OCR verification, security/input-validation
review, performance testing. Full results in PROGRESS.md; this section
covers the decisions, not the test output.

### Debug mode: opt-in via FLASK_DEBUG, not hardcoded on
**Status: done.** Both `run.py` and `api.py`'s `__main__` block
previously hardcoded `app.run(debug=True, ...)`. Changed to read
`FLASK_DEBUG` from the environment, defaulting to off.
- **Reason**: confirmed live that Flask's interactive debugger (which
  `debug=True` enables) shows a full traceback, real filesystem paths,
  and an embedded Python console for any unhandled exception —
  triggered by nothing more exotic than an oversized integer in a URL
  path. That's fine for a developer debugging locally with the
  terminal in front of them; it's a serious information-disclosure
  risk for anything else. Making it opt-in (rather than removing it
  entirely) keeps the debugger available for local development without
  it being the default.

### Global error handlers return clean JSON regardless of debug mode
**Status: done.** Registered `@app.errorhandler` for 400/404/413/500
and a catch-all `Exception` handler in `api.py`, all returning a
generic `{"error": "..."}` body; the real exception is logged
server-side via `logger.exception(...)` in every case.
- **Reason**: Two problems needed one fix. First, several failure
  modes returned Flask/Werkzeug's *default* HTML error pages (a raw
  413 page for oversized uploads, a raw 404 page for unknown routes)
  instead of JSON, which the frontend's JSON-only error parsing
  couldn't use cleanly. Second, and more important: registering
  `@app.errorhandler(Exception)` turns out to intercept an exception
  *before* it reaches Werkzeug's interactive-debugger path, even with
  `debug=True` — verified this directly, not assumed from
  documentation. That means local `FLASK_DEBUG=1` debugging and
  "never leak a traceback to a client" aren't actually in tension:
  the handler catches it first either way, and only the terminal
  running the server sees the real exception.

### Oversized/out-of-range lease IDs are "not found," not a crash
**Status: done.** `database.get_lease()` catches `OverflowError` and
returns `None`.
- **Reason**: this is the actual root cause of the debugger-leak
  finding above (an id like `9` × 34 digits overflows SQLite's signed
  64-bit `INTEGER` column). Fixing it at the single lowest layer
  (`get_lease`, which `get_effective_lease` and therefore every route
  built on it calls first) means every route that checks "does this
  lease exist" before doing anything else — detail, delete, risks,
  benchmark, amendments, compare — automatically returns a proper 404
  instead of relying on the generic exception handler as a safety net.
  Fixing the specific cause is more correct than only fixing the
  generic symptom, even though the generic handler would have masked
  it either way.

### OCR binaries via conda-forge, not Homebrew
**Status: done.** Got real `tesseract`/`poppler` working via a
Miniforge (conda-forge) install to `~/.miniforge3`, after Homebrew —
even installed to a user-owned prefix specifically to avoid needing
sudo — failed.
- **Reason**: Homebrew bottles (precompiled binaries) are built for
  the *standard* prefix (`/opt/homebrew` on Apple Silicon); installing
  to a non-standard user-owned prefix to dodge the sudo requirement for
  creating `/opt/homebrew` meant Homebrew couldn't use those bottles
  for at least poppler/tesseract's build chain, and fell back to
  compiling from source — which then failed because this machine's
  Xcode Command Line Tools are older than the build requires, and
  updating them needs either sudo (`xcode-select --install`) or
  interactive System Settings, neither available in this session.
  Conda-forge packages are precompiled for a relocatable install
  location by design (conda environments are *meant* to live anywhere,
  unlike Homebrew's bottle system), so the same "can't use sudo, can't
  use the GUI" constraint didn't block it. This is genuinely a
  workaround for this specific machine's state (an outdated CLT
  version), not a general statement that Homebrew is the wrong choice
  — a machine with current Command Line Tools, or with sudo access,
  would likely succeed with plain Homebrew.
- **Consequence**: OCR now depends on `~/.miniforge3/bin` being on
  `PATH` when the backend starts. This lives outside the repo (home
  directory) and outside `requirements.txt` (it's system binaries, not
  Python packages) since it's a machine-level install. See PROGRESS.md
  for the exact restart commands and for how to reproduce this install
  from scratch if the environment is ever reset.

## Portfolio Intelligence Expansion (2026-08-12, session 3)

This section was updated live as work happened, not just at the end,
per explicit instruction — the per-decision "Status" lines below were
the running record during the session and are now all "done."

### Scope
Moving from single-lease extraction to portfolio-level intelligence:
multi-lease upload/storage, a portfolio dashboard, expiration timeline,
risk/anomaly detection, a grounded natural-language Q&A interface,
lease-vs-lease comparison and benchmarking, batch upload with per-file
error recovery, amendment linking, rent roll export, and a printable
portfolio summary report.

### Persistence: SQLite via Python's stdlib `sqlite3`, not a new dependency
**Status: done.**
Portfolio features (sort/filter across leases, aggregate averages, link
amendments to a base lease) genuinely require queryable persistence —
the previous session's browser-localStorage-only state can't support
this. Chose `sqlite3` (stdlib, zero new dependency) over a JSON-file
store or a heavier ORM/database.
- **Reason**: Keeps the "minimal dependencies" philosophy from session 1
  while giving real query capability (filtering, sorting, joins for
  amendments) that a flat JSON file would make painful to maintain
  correctly as the number of leases grows. A learning-project scale
  (dozens to low hundreds of leases) is exactly SQLite's sweet spot.
- **Schema**: single `leases` table — `id`, `filename`, `uploaded_at`,
  `extracted_fields` (JSON blob of the existing 14/15-field extraction
  result, unchanged shape), `document_type` ('lease' or 'amendment'),
  `base_lease_id` (NULL for base leases, FK to the base lease for an
  amendment). An "effective" lease view merges a base lease's fields
  with its most recent amendment's non-null fields (amendment overrides
  base per-field) — see `database.py: get_effective_lease()`.

### New field: square_footage (15th extracted field)
**Status: done.**
Added to support "average rent per square foot" portfolio metric, which
the brief explicitly conditions on square footage being extracted.
- **Reason**: Needed as an input to a specific requested metric; follows
  the same label-style/prose-style pattern-matching approach as every
  other field in `field_extractor.py`.

### Normalization layer for portfolio math
**Status: done.**
`app/normalize.py` — parses the extractor's *display strings* ("$6,250.00",
"April 1, 2025", "3% annually", "10 days after written notice") into
actual numbers/dates for aggregation, comparison, and risk-threshold
checks. Shared by every downstream module (risk analysis, portfolio
metrics, comparison, Q&A, rent roll export).
- **Reason**: The extraction engine's job is to produce human-readable,
  source-verifiable strings, not machine-typed values — that's the right
  design for the extraction layer, but portfolio math needs real numbers.
  Building this parsing once as a shared utility avoids every downstream
  module re-implementing (and subtly disagreeing on) currency/date
  parsing.

### Q&A engine: deterministic intent-matching, NOT an LLM call
**Status: done, independently verified.** `app/qa_engine.py`, built by a
parallel subagent. Re-ran its tests myself, confirmed no network/LLM
imports, then ran the brief's own example questions against real
extracted data from actual test PDFs — each answered correctly with
citations traced back to real stored source data.
The brief asks for "an accurate answer grounded in the actual extracted/
source data — not a hallucinated answer," with citations. Built as a
rule-based natural-language query engine: pattern-match the question
against a set of known intents (list-expiring, aggregate-field,
field-lookup-on-lease, has-clause, etc.), execute a real query against
the SQLite-stored extracted data, and construct the answer directly from
stored values with a citation (lease name + page + quote) pulled from
the actual stored source. Unsupported questions get an honest "I can't
answer that yet" rather than a guess.
- **Reason**: An LLM-generated answer — even a good one — can hallucinate
  a number or misattribute a citation, which is exactly what the brief
  says to avoid. A deterministic query engine cannot fabricate a value:
  it either finds a real stored fact and returns it with its real
  source, or it says it doesn't know. The tradeoff is coverage (only
  questions matching a known intent pattern are answerable) rather than
  open-ended chat — a deliberate choice given the "not hallucinated"
  requirement is explicit and non-negotiable in the brief. No API keys,
  no external LLM dependency, no per-query cost.

### Risk detection: rule-based thresholds + cross-field consistency checks
**Status: done.** `app/risk_analysis.py`. Flags below-market rent (vs.
portfolio average, preferring a per-sqft comparison when available),
notice-period outliers (absolute bounds + portfolio-relative
deviation), missing standard clauses (insurance, default/cure,
security deposit), one-sided terms (no escalation on a long-term
lease, unusually long cure period), and internal inconsistencies
within a single lease (escalation-schedule rate spread, invalid/
reversed date range, conflicting dates across sections). Each flag
carries a severity and a plain-English explanation citing the actual
numbers it fired on. Built by a parallel subagent per the shared
contract, independently re-verified afterward (re-ran its 26 tests,
then ran it against all 5 real red-flag fixture PDFs with a portfolio
context computed from actual data) — every deliberately-built issue
was caught correctly.
- **Reason**: This is explicitly "the differentiator" per the brief — go
  beyond extraction into analysis. Rule-based (not ML-based) for the
  same reason as the Q&A engine: explainability. Every flag needs to say
  *why* it fired, which a rule threshold can state directly ("rent is
  22% below the portfolio average of $X") in a way an opaque model
  score couldn't.

### Portfolio metrics, timeline, comparison, and benchmarking
**Status: done.** `app/portfolio.py` (totals/averages computed only
over leases whose value actually parsed — a missing field is skipped,
never counted as zero, so an average can't be silently diluted;
expiration timeline bucketed 0-6/6-12/12-24/24+ months plus already-
expired/unknown) and `app/comparison.py` (side-by-side N-lease compare
keeping the extractor's original display strings verbatim — a compare
view is exactly where a human checks the tool's work against the
source, so normalizing the numbers there would work against the
point; single-lease-vs-portfolio benchmarking with a signed % diff and
above/below/in-line assessment). Built by a parallel subagent,
independently re-verified: re-ran its 24 tests, then ran both modules
against all 10 real test PDFs — the benchmark for the deliberately
underpriced lease (64.8% below average rent) is consistent with the
below_market_rent flag risk_analysis raised for the same lease
independently.

### Rent roll export and printable portfolio report
**Status: done.** `app/rent_roll_export.py` (CSV via stdlib, Excel via
the one new dependency this session — `openpyxl==3.1.5` — with real
numeric typing applied conservatively so a qualified value like "$4.50
per sq ft annually" never gets misrepresented as a bare number) and
`app/report.py` (self-contained, print-oriented HTML one-pager: no
external assets, so it renders identically saved or emailed). Built by
a parallel subagent, independently re-verified: re-ran its 22 tests,
then generated real CSV/Excel/HTML from all 10 actual test PDFs and
read the Excel file back with openpyxl and the HTML report by eye —
professional-looking output, correctly surfacing all 23 real risk
flags from this session's portfolio.

### Frontend: stays vanilla JS, no build step, restructured as a multi-view app
**Status: done.** The single-lease-upload page is now a sidebar-
navigated multi-view app: Dashboard, Upload, Lease Detail (inline
editing, risk panel, amendments, per-lease Q&A), Expiration Timeline,
Compare, Ask a Question, and Portfolio Report — plain `<script>`
includes, no framework/bundler.
- **Reason**: Session 1 explicitly chose vanilla JS for zero build
  tooling and stayed consistent through session 2's larger single-page
  rebuild; introducing a framework now would be a bigger, tangential
  architectural change the brief didn't ask for. Vanilla JS can still
  organize multiple views cleanly with careful state management — it
  just takes more discipline than a framework would.
- **Verification note**: found and fixed two test-harness-only issues
  while verifying this (neither was a real app bug): a jsdom
  `window.eval()`-per-file harness doesn't reproduce how real
  `<script>` tags share one global scope for top-level `let`/`const`
  across a page, and jsdom's `FormData`/`File` aren't recognized by
  Node's native `fetch` (a cross-realm mismatch that doesn't exist in
  an actual browser). Fixed by having jsdom execute the real
  `<script src>` tags (`JSDOM.fromFile` + `runScripts: "dangerously"`)
  and bridging FormData across realms in the harness — see the
  frontend rebuild commit for detail. All 30 end-to-end checks passed
  against the real backend with real file uploads afterward.

### Backend module ownership during parallel work
Foundation (`database.py`, `normalize.py`, the `square_footage` field,
and the new lease/batch/amendment API routes) was built first and
sequentially, since every other module depends on its contract. The
independent analysis modules (`risk_analysis.py`, `qa_engine.py`,
`portfolio.py`/`comparison.py`, `rent_roll_export.py`/`report.py`) were
then built in parallel by separate agents, each producing a new
self-contained file plus its own tests and NOT touching `api.py` or each
other's files — wiring those modules into Flask routes was done
afterward by the orchestrating session alone, specifically to avoid
multiple agents editing the same shared file concurrently.

## Backend Structure (2026-08-12)

Built Python backend for lease PDF extraction with the following design choices:

### Architecture
- **Modular design**: Separated PDF extraction (`pdf_extractor.py`) from field extraction (`field_extractor.py`) for better maintainability
- **API layer**: Flask API (`api.py`) handles HTTP concerns separately from business logic
- **Reason**: This separation makes it easier to swap out components (e.g., add ML-based extraction later) without touching API code

### PDF Text Extraction Strategy
- **Primary method**: PyPDF2 for digital PDFs (fast, no external dependencies)
- **Fallback**: OCR using pytesseract + pdf2image when text extraction yields < 100 chars
- **Reason**: Most modern leases are digital PDFs, so PyPDF2 handles 90% of cases efficiently. OCR is slower but handles scanned documents when needed

### Field Extraction Approach
- **Method**: Regex patterns with keyword matching
- **Not using**: Machine learning or NLP models
- **Reason**:
  - Simpler to debug and maintain for a solo learning project
  - Sufficient for standardized lease formats
  - Can add ML layer later if needed without changing API contract
  - Lower deployment complexity (no model files to manage)

### JSON Response Format
Each field returns:
```json
{
  "value": "extracted value or null",
  "source": {
    "page": page_number,
    "quote": "context snippet"
  } or null
}
```
- **Reason**: Source information helps users verify extractions and debug issues. Null values are explicit about what wasn't found.

### File Organization
- `backend/app/`: Core application modules
- `backend/tests/`: Test utilities and sample data
- **Reason**: Standard Python project layout, familiar to most developers

### Dependencies
- Flask + flask-cors: Lightweight web framework
- PyPDF2: Pure Python PDF reader
- pdf2image + pytesseract: OCR fallback
- reportlab: Test PDF generation
- **Reason**: Minimal dependencies, all well-maintained libraries

### Testing Approach
- Created sample PDF generator to ensure reproducible tests
- Included validation script that checks extraction against known values
- **Reason**: Real lease PDFs contain sensitive data; generated test data is safer to commit

### Pre-existing Files
Found `app/extract.py` and `app/main.py` already in the codebase. These appear to be an earlier implementation attempt. Left them in place but built a new, more complete system with better separation of concerns.

### Future Improvements (not implemented)
- Machine learning models for more flexible extraction
- Support for more date formats
- Additional fields (property address, landlord, etc.)
- Confidence scores
- Batch processing

## Frontend Structure (2026-08-12)

Built minimal web UI for uploading PDFs and viewing extraction results.

### Technology Choice
- **Method**: Vanilla JavaScript, HTML5, and CSS3
- **Not using**: React, Vue, or other frameworks
- **Reason**:
  - Zero build tools or compilation steps required
  - Just serve static files - extremely simple deployment
  - Easy to understand and modify for a solo learning project
  - No framework overhead or dependency management
  - Perfect for learning fundamentals

### File Structure
- `frontend/index.html`: Single-page app structure
- `frontend/app.js`: Upload handling, API integration, result rendering
- `frontend/styles.css`: Modern CSS with Grid and Flexbox
- **Reason**: Simple three-file structure - easy to navigate and understand

### Key Features Implemented
1. **Drag-and-drop upload**: Visual feedback and click fallback
2. **File validation**: Type and size checks before upload
3. **Loading states**: Spinner and status messages
4. **Result display**: Card-based layout showing value, status, page, and quote
5. **Error handling**: Clear user-friendly error messages
6. **JSON export**: Download full extraction results
- **Reason**: These features meet the MVP requirement of "simple web UI to upload and view results"

### Design Choices
- **CSS variables**: Easy theming and color management
- **Status badges**: Green for "Found", gray for "Not Found" - clear visual distinction
- **Quote display**: Shows context snippet so users can verify extraction accuracy
- **Responsive layout**: Works on desktop and mobile using CSS Grid
- **Reason**: Aligns with quality bar of "show source so humans can verify"

### Integration Approach
- Backend API: `http://localhost:5000/extract`
- CORS already enabled in Flask backend
- Field mapping: Backend keys → user-friendly labels
- **Reason**: Clean separation - frontend and backend can be developed/deployed independently

### Server Options
Documented three ways to serve static files:
1. Python's http.server
2. Node's http-server
3. VS Code Live Server
- **Reason**: Solo developer might not have Node installed; Python is guaranteed since backend uses it

## Extraction Engine Rework (2026-08-12, session 2)

The original 4-field extractor only matched rigid "Label: Value" phrasing
(e.g. "Monthly Rent: $2,500.00"). It silently returned "Not Found" for the
narrative sentence structure real commercial leases actually use ("...the
sum of $6,250.00 per month...", "Blue Sky Coffee Roasters, Inc. (\"Tenant\")").
This session reworked the extraction engine and expanded it from 4 to 14
fields, added confidence scoring, and hardened it against messier input.

### Pattern strategy: ordered fallback, most-reliable-first
Every field tries several regex strategies in priority order (label style →
prose style → loose fallback), stopping at the first match. Each strategy is
tagged with a confidence tier (high/medium/low) reported alongside the
value, so a human reviewer knows how much to trust a given extraction
without having to inspect the source quote themselves.
- **Reason**: A single rigid pattern per field can't cover both "Field:
  Value" documents and narrative legal prose. Trying multiple strategies
  and keeping the most specific one lets the tool handle both without
  guessing silently — a field found via a loose fallback is visibly lower
  confidence than one found via an explicit label.

### Bounded "gap" instead of requiring keyword/value adjacency
A keyword and its value are matched with a bounded, period-excluding gap
between them (`[^.$]{0,100}?`) rather than requiring immediate adjacency.
This lets patterns match "shall commence on April 1, 2025" or "base rent
... the sum of $6,250.00 per month" without also running past the end of
the sentence into unrelated text.
- **Reason**: This is the core fix for the Part 1 bug. Requiring immediate
  adjacency is what caused rent/date extraction to fail on prose lease
  text in the first place.

### Whole-document search, not page-by-page
All extractors search the full document text (pages joined, with an
offset-to-page-number map for source attribution) rather than looping
page by page.
- **Reason**: Two problems with page-by-page search: (1) a keyword and its
  value can legitimately be split across a page break in a real multi-page
  lease, and neither page's text alone contains the full clause; (2) it
  made pattern priority page-dependent — a low-confidence match on page 1
  would win over a high-confidence match on page 2 just because it was
  checked first. Searching the whole document fixes both.

### Case-sensitivity is scoped per-pattern, not global
`_search_ordered` defaults to `re.IGNORECASE`, but party-name extraction
(tenant/landlord) explicitly passes `flags=0` and scopes case-insensitive
keywords locally with `(?i:...)`.
- **Reason**: Found during Part 4 robustness testing — a blanket
  `re.IGNORECASE` flag makes `[A-Z]`/`[a-z]` character classes stop
  meaning "a capitalized word," since both classes then match either
  case. That silently defeats the capitalization heuristic used to bound
  where a proper name ends, causing catastrophic over-capture on casual
  phrasing (captured "Jordan Blake and the tenant is Alex Chen" instead of
  "Jordan Blake"). Any future pattern whose capture group relies on
  `[A-Z]`/`[a-z]` to detect real capitalization must follow the same
  scoping approach.

### Confidence tiers reflect match directness, not just field type
Confidence is assigned per matching *strategy*, not per field: an explicit
label always scores high regardless of which field it's on; a reversed-
order match (value before its keyword, e.g. "...the sum of $12,500.00 as a
security deposit") scores medium; a generic fallback with little
disambiguating context scores low. Composite fields (renewal options)
grade confidence by how many of their expected sub-parts (notice period,
renewal basis) were actually corroborated in the text.
- **Reason**: This is what the Part 3 requirement ("confidence based on how
  directly the source text matches expected patterns") actually calls for
  — a fixed per-field confidence wouldn't distinguish an unambiguous label
  match from a loose proximity-based guess on the same field.

### Ambiguous keyword matches are disambiguated by proximity, not document order
Default/cure period extraction scans every "(N) days ... written notice"
candidate in the document and prefers the one with "default"/"cure" nearby,
rather than taking the first match found.
- **Reason**: Found during Part 4 testing — a lease can have several
  unrelated "(N) days ... written notice" clauses (renewal notice, cure
  notice), and blindly taking the first one in document order picked up
  the wrong clause when the renewal section happened to come first.

### Synthetic test documents as the primary robustness signal
Rather than relying only on real leases (sensitive, hard to source safely)
or a single stylized sample, this session built 3 additional synthetic
lease PDFs (`retail_lease.pdf`, `office_lease.pdf`, `casual_sublease.pdf`)
each with deliberately different section structure, sentence phrasing,
currency/date formatting, and drafting formality, plus a field-by-field
accuracy report (`test_synthetic_accuracy.py`) across all 5 fixtures.
- **Reason**: A single "does it pass" test document can't reveal phrasing-
  specific gaps. Testing against meaningfully different documents is what
  actually surfaced the case-sensitivity bug, the heading-period bug, and
  the ambiguous-keyword bug above — all three were invisible against the
  original two fixtures.

### OCR fallback verified with mocks, not a live run
This dev environment has no tesseract/poppler installed and no package
manager available to install them. The OCR trigger condition, success
path, and failure-degrades-gracefully path are verified with
`unittest.mock` against the real `pdf_extractor.py` code (not rewritten
test doubles), rather than skipped entirely.
- **Reason**: Verifying the logic is still valuable even without live OCR
  — it confirms the fallback actually triggers on sparse text, that OCR
  output flows into field extraction normally, and that an OCR failure
  degrades to an empty page list instead of raising and crashing the
  request. A live end-to-end run against a real scanned PDF should still
  happen in an environment with those binaries before relying on this path
  in production — see `PROGRESS.md` known limitations.

### Frontend: grouped display + inline editing + confidence badges
Results are grouped into Parties / Financial Terms / Dates & Term /
Special Clauses (`FIELD_GROUPS` in `app.js`) instead of one flat grid.
Confidence renders as a color-coded badge per field. Clicking a value
turns it into an inline text input; committing a correction sets an
`edited: true` flag on that field, which is included in the JSON export.
- **Reason**: Matches the Part 6 requirements directly. The `edited` flag
  (rather than silently overwriting) preserves the distinction between
  "the tool found this" and "a human corrected this" through to export,
  which matters for an abstraction tool whose whole premise is
  human-verifiable extraction.

### Frontend verified via jsdom against real backend output, not just read
No browser automation tool was available in this environment. Instead of
relying on static code review alone, a scratch jsdom harness loads the
actual unmodified `index.html`/`app.js`, mocks `fetch` to return real
`/extract` responses (captured from the live backend against real test
PDFs), and drives the exact `processFile()` entry point the browser uses
on upload — then asserts on the resulting DOM and on the actual JSON blob
captured from `exportJSON()`.
- **Reason**: This is a meaningfully stronger check than reading the
  source, since it executes the real code through the real entry point
  and catches issues static review would miss (e.g. an early version of
  this harness itself revealed a scoping mistake in test setup, not the
  app — but the point of running it was to catch exactly that class of
  false confidence). It is still not a substitute for a literal browser
  click-through; that should be done manually — see `PROGRESS.md` for
  what to check.

## Session 5: Visual redesign — landing page, waitlist, and app restyle

### Routes via real directory structure, not client-side routing
The frontend is still served by plain `python3 -m http.server`, with no
server-side routing logic and no build step. To get real, bookmarkable
URLs for `/`, `/app/`, and `/admin/waitlist/`, each is its own directory
with its own `index.html` — `http.server`'s built-in behavior (serve a
directory's `index.html`, 301-redirect a bare path to its trailing-slash
form) does the rest. The old flat `frontend/*.js`/`styles.css` files
moved into `frontend/app/` unchanged (only their CSS's token block was
replaced with an `@import`), so nothing about how the app itself loads
or runs changed — only where it lives.
- **Reason**: Keeps the "no build step, no framework" decision from
  session 1 intact rather than reaching for a JS router or a second dev
  server just to get distinct URLs.

### One shared token file, not three separate palettes
`frontend/design-system.css` holds every color/typography/shadow/radius
CSS custom property, plus a few truly shared components (buttons,
loading spinner). The landing page and admin view link it directly;
`frontend/app/styles.css` `@import`s it instead of redeclaring its own
`:root` block. All existing component class names and CSS variable
*names* in the app were preserved exactly — only their values changed —
so `app.js` and every view module needed zero changes to pick up the
new look.
- **Reason**: A single source of truth was the only way to guarantee the
  landing page and the app actually look like the same product, per the
  explicit "one cohesive palette, used everywhere" requirement. Keeping
  variable/class names stable avoided touching any JS (the task was
  scoped to a visual pass, not a behavior change) and made every existing
  jsdom-based test/verification pattern keep working unmodified.

### Waitlist has no real auth yet — deliberate, and flagged loudly
`GET /waitlist` and `POST /waitlist/<id>/approve` are open endpoints, and
`/admin/waitlist/` has no login. This was an explicit instruction
("no auth needed yet ... build the real auth gate later, don't block on
it now"), not an oversight. It's called out in three places so it can't
be missed later: a comment block directly above the routes in `api.py`,
a comment block in the admin `index.html`, and here.
- **Reason**: Matches the requested scope exactly — the task was to get
  a working waitlist gate and admin approval flow shipped now, with real
  authentication as explicitly deferred follow-up work, not something to
  half-build or skip documenting.

### Inter font via Google Fonts CDN, despite the "minimal dependencies" precedent
`design-system.css` pulls Inter from `fonts.googleapis.com`. Earlier
sessions' dependency choices (stdlib `sqlite3` over an ORM, no JS
framework) favored minimal/offline-friendly dependencies. This is a
narrow, deliberate exception: a system-font stack reads as a prototype,
and "premium SaaS typography" was an explicit requirement Inter serves
directly. If offline use becomes a requirement later, this is a single
`@import` line to swap for a self-hosted font file — noted here so that
tradeoff is visible, not buried.
  what to check.

## Session 6: /app access gate + local dev bypass (2026-08-15)

### Access gate uses self-reported email, not real auth
`/app` previously had zero enforcement — anyone with the URL landed
straight in the dashboard (see Session 5's "no auth yet" note above,
which was specifically about the admin waitlist endpoints but was true
of `/app` too). It's now gated: a visitor must enter an email with
`status = 'approved'` in `waitlist_signups`, checked via the new
`POST /waitlist/check` endpoint (`frontend/app/access-gate.js`).

This is explicitly **not** real authentication. There's no password, no
session token tied to a verified identity, and nothing stopping someone
from typing in an email they don't own if they can guess or find an
approved one. What it does do: stops a stranger who just has the URL
(the actual problem this session was scoped to solve) from reaching the
dashboard, while staying consistent with the project's "no accounts /
no login system" architecture so far — adding real password/session
auth would be a materially bigger scope (user table, password hashing,
session or token management, login UI) than what was asked for here.
- **Reason**: Matches the requested scope — "build the real auth gate"
  in context meant "stop unapproved visitors from reaching /app," not
  "build a full accounts system." The gap between this and real auth is
  called out here and in `api.py` directly above the route so it isn't
  mistaken for more than it is. Real auth (accounts, passwords/OAuth,
  sessions) remains a Next Steps item, now split out from the admin-panel
  auth gap tracked in the Session 5 entry above — the two are separate
  problems (who can reach `/app` vs. who can approve signups /
  see everyone's email) and don't need to ship together.

### LOCAL_DEV_MODE: a server-side, env-only bypass — not a client-side one
The gate can be skipped locally via `LOCAL_DEV_MODE=true` in
`backend/.env`. The frontend never decides this for itself — it asks the
backend via `GET /config`, and the backend only reports what's already
in its own environment at process start (`os.environ`, loaded once
before any request is handled). A client can't set or influence this
value through any request path.
- **Reason**: The alternative — a client-side flag (URL param, hardcoded
  `true` in JS, a build-time toggle) — would ship the same bypass to
  production by accident the moment that code path is reachable there,
  since there's no build step to strip it out (Session 1's "no build
  tooling" decision, still in effect). Routing it through an
  environment variable the *server* controls means the real/default
  gate is what ships everywhere by default, and the bypass only exists
  on whichever machine's `.env` explicitly turns it on — which is also
  why `backend/.env` (gitignored, per Session 1) is the only place this
  is ever set to `true`; `.env.example` documents the variable but
  defaults it to `false`.

### App scripts now load dynamically, after the gate — not statically in the HTML
`frontend/app/index.html` no longer lists `api.js`/`app.js`/the view
modules as static `<script>` tags. `access-gate.js` is the only
statically-loaded script; it injects the rest only after access is
confirmed (`script.async = false` on each, to preserve load order
without blocking).
- **Reason**: Without this, every view module's API calls (dashboard
  metrics, lease list, etc.) would fire immediately on page load
  regardless of whether the visitor is allowed in — the gate would only
  be hiding the DOM, not actually stopping the underlying requests. This
  also surfaced a latent bug worth noting: `app.js` and all six view
  modules bootstrap via `document.addEventListener('DOMContentLoaded',
  ...)`, which never fires for a script injected after that event
  already happened (true even on the `LOCAL_DEV_MODE` bypass path, since
  the `/config` fetch that decides that is itself async). Each of those
  seven files now checks `document.readyState` first and calls its init
  function directly if the page has already finished loading — a small,
  general fix that also makes each file correct if loaded late for any
  other reason in the future, not just this one.

### Multi-lease PDFs are rejected at upload, not silently merged into one record

A merged/bundled PDF — several distinct leases scanned or concatenated
into a single file — was silently persisted as ONE lease record.
`extract_fields()` treats the whole document as one continuous text
block and returns each field's single best match anywhere in it, so
across a genuinely multi-lease PDF, different fields independently
"win" from different constituent leases: the tenant name from lease #2
paired with the rent amount from lease #1, with nothing to indicate the
record is a mix.

**This was verified empirically, not assumed**: concatenating two real
fixture PDFs (`retail_lease.pdf` + `office_lease.pdf`) via PyPDF2 and
running the real extraction pipeline against the result produced tenant
`"Vertex Analytics LLC"` (from page 2 / office_lease) paired with rent
`"$6,000.00"` and dates from page 1 / retail_lease — a real Frankenstein
record. The same investigation also found a live example already in
this project's dev database: a pre-existing `Sample_500_Page_Lease_
Portfolio.pdf` upload (from before this fix existed) had been persisted
as a single lease with an implausible `$262,131.87` monthly rent and no
end date found — consistent with the same bleed, at much larger scale.

**Fix**: `FieldExtractor.detect_multiple_leases()` scans the whole
document for every match of the tenant/landlord party-name patterns
(reusing the same patterns `extract_fields()` itself uses, via a new
`_find_all_party_values()`, rather than inventing separate detection
logic) and checks whether more than one *distinct* tenant or landlord
is defined. A genuine single lease defines exactly one of each, even
when that name is repeated verbatim many times through the document —
2+ different names is a strong, low-false-positive signal that more
than one lease is present. `_extract_fields_from_file_storage()` in
`api.py` calls this before trusting `extract_fields()`'s result and
returns a 400 (not a 500 — this is a client-actionable "wrong kind of
file" situation, not a server error) with a message naming the
conflicting parties found, telling the uploader to split the PDF and
upload each lease separately. Applies uniformly to `/extract`,
`POST /leases`, `POST /leases/batch` (per-file, without failing the
rest of the batch), and amendment uploads, since they all share this
one pipeline function.

This does NOT attempt to automatically split a multi-lease PDF into its
constituent leases — that would need real per-lease boundary detection
(which page ranges belong to which lease) and is a substantially larger
feature with its own accuracy risks. Refusing and telling the human
what's wrong was the deliberately smaller, safer scope, consistent with
this project's existing "flag clearly, never guess silently" standard
(see the original quality-bar requirement in the root CLAUDE.md).

**False positives found and fixed before shipping this**: an early
version flagged 2 of the 10 existing single-lease fixtures incorrectly.
Both were the same root cause — the same real party mentioned twice
surfaces as two slightly different strings (once via the tight
word-boundary label pattern, once via the looser to-end-of-line one, or
once with a corporate suffix like ", Inc." and once without it in a
later reference) — not two different parties. Fixed with
`_dedupe_party_values()`, which merges values where one is a
case-insensitive prefix of the other before counting distinct parties.
Verified against all 10 real single-lease fixtures individually (zero
false positives) and 4 different real multi-file merges, including one
combining the two fixtures that had triggered the false positives (to
confirm the fix didn't just suppress detection entirely) — see
`test_multi_lease_detection.py`.

### Google Sheets export: service account, not OAuth; new sheet every time

`sheets_export.py` uses a Google **service account** key
(`GOOGLE_APPLICATION_CREDENTIALS`, a JSON file path — the standard env
var name Google's own libraries look for) rather than per-user OAuth.
- **Reason**: this is a backend-triggered export action (click a
  button, get a sheet), not a "sign in with Google" login flow — there
  is no per-user Google identity anywhere else in this app to hang
  OAuth off of, and a service account is the credential type meant for
  exactly this shape of server-to-server access.

Every export **creates a brand-new Sheet** (never updates one persistent
sheet), named `"Lease Portfolio Export - <date>"`.
- **Reason**: asked directly rather than assumed — see the
  AskUserQuestion exchange in this session. A fresh sheet per export
  also has no "which format does the existing sheet expect" compatibility
  concern to maintain over time, unlike updating a fixed sheet would.

The created sheet is shared **"anyone with the link can view"** (via
the Drive API, since Sheets API alone can't set sharing) rather than
shared with a specific person's email.
- **Reason**: a service-account-created file isn't visible to anyone
  else by default, and there's no single "current user" account
  anywhere in this app (no real per-user auth exists yet — see the
  access-gate entry above) to share it with individually instead.
  Link-shareable is the only option that guarantees the URL handed back
  actually opens for whoever clicked the button. This does mean anyone
  who obtains that exact (unguessable, but not access-controlled) link
  could view that export's data — documented explicitly in
  `backend/.env.example` as the same tradeoff the existing CSV/report
  exports already have, not a new regression introduced by this
  feature.

Column formatting (which fields become real numbers vs. stay as
extracted display strings, blank-not-"Not Found" for missing fields)
deliberately mirrors `rent_roll_export.py`'s existing philosophy rather
than inventing a third convention for a third export format — see that
module's docstring and `sheets_export.py`'s docstring for the shared
reasoning. Annual Rent and Rent per Square Foot are computed via
`app.normalize`, the same module every other aggregate in this project
uses, so a number in the exported sheet can't quietly disagree with the
same figure shown on the dashboard.

Verified as far as possible without real Google credentials (none are
configured in this environment, by design — nothing was invented or
guessed): every failure path (unset env var, missing file, invalid key
file, a mocked Google API 403/401/other error) raises a clean,
actionable `SheetsExportError`, confirmed live against the running
server with `curl`. The full happy path — creating a sheet, writing the
correct rows, setting sharing — is verified with `googleapiclient.
discovery.build` and `service_account.Credentials.from_service_account_
file` mocked out (`test_sheets_export.py`), asserting on the actual
data passed to the mocked Sheets API calls (header row, per-lease rows
in order, the sharing permission body), not just that no exception was
raised. What is NOT verified: an actual real Google Sheet being
created via a real API call, since no real credentials exist to test
with — that step is on whoever sets up
`GOOGLE_APPLICATION_CREDENTIALS`.

### Multi-lease PDFs are now SPLIT, not rejected — supersedes the earlier "reject" decision

The previous session's fix for multi-lease PDF field-bleed (see the
"Multi-lease PDFs are rejected instead of silently merged" entry above)
deliberately chose the smaller, safer scope: detect the situation and
refuse the upload, rather than attempt real per-lease boundary
detection, which that entry called "a substantially larger and riskier
feature on its own." This session built that larger feature, on
explicit request, after the smaller fix turned out not to be enough in
practice — a real merged portfolio PDF a user actually tried to upload
produced a risk-analysis flag listing 30+ "conflicting" start dates,
because `date_candidates` were being collected from the whole 500-page
document instead of kept separate per lease (the same underlying
bleed the reject-based fix prevented at the *field* level, but not at
the *risk-analysis* level, since risk analysis reads `date_candidates`
independently of `extract_fields()`'s own single-best-match fields).

**How boundary detection works**: `FieldExtractor.detect_lease_
boundaries()` places a page boundary at the first page each distinct
tenant OR distinct landlord is introduced on — the UNION of both
signals (not just one, and not just whichever found more distinct
parties, which was this feature's first, more conservative
implementation before it was strengthened — see below). Verified safe
against all 10 real single-lease fixtures before switching to the union
approach: in every one, the lease's tenant and landlord are introduced
on the *same* page (a lease's "parties" section names both together),
so the union never adds a spurious mid-lease boundary. `extract_
multiple_leases()` then runs the existing single-lease `extract_
fields()` + `find_all_date_candidates()` independently on each
boundary's own page range — never on the whole document — which is
what actually fixes the 30-dates symptom: each split lease's
`date_candidates` now only ever contains dates from its own 1-2 pages.

**Verified, concretely, not just reasoned about**: every field of every
split-out lease exactly matches what extracting that same source
fixture completely standalone produces (not "close" — byte-for-byte
equal), across 4 different real multi-file merges including a 4-way
merge, plus a 10-fixture merge (all 10 real fixtures concatenated into
one document) that correctly produced exactly 10 leases in 0.05
seconds. The reported symptom itself was directly reproduced and
confirmed fixed: a 5-fixture merge that showed 6 smeared "conflicting"
start dates under the old whole-document approach now shows 1-2 dates
per lease, with only the two fixtures that are genuinely internally
inconsistent (by design, as test fixtures) still flagging.

**Known, real, honestly-documented limitation**: if two genuinely
different, non-adjacent leases in the same merged PDF happen to share
BOTH the exact same tenant name AND the exact same landlord name, this
heuristic (or any purely name-based one) cannot tell them apart, and
they will incorrectly merge into one record — confirmed directly: a
test merging `retail_lease.pdf` + `office_lease.pdf` + `retail_lease.
pdf` again (so the same tenant AND landlord reappear on the third page)
produces 2 detected leases, not the true 3, with the second result's
fields bleeding between the office lease and the second copy of the
retail lease. This is not fixed and was not silently assumed away. It
was NOT possible to test against the user's actual real-world 500-page/
250-lease PDF that originally surfaced this bug — the file itself
wasn't recoverable (upload-time processing only ever kept a temporary
copy, already deleted; it wasn't found in common locations on this
machine either) — so this feature's accuracy against that *specific*
document is unverified; everything above is verified against this
project's own real fixture PDFs and real merges of them instead. This
should be spot-checked against the real file when available.

Not implemented, and deliberately out of scope: page-break heuristics
and repeated "COMMERCIAL LEASE AGREEMENT"/"ARTICLE 1: PARTIES"-style
structural title detection (both suggested as alternative signals).
The tenant/landlord-identity signal was preferred because it was
already built, already validated with zero false positives across
every real fixture in this project, and is what the fields themselves
are extracted from — a structural-title signal would need its own
separate validation pass against real documents to avoid new false
positives (e.g. a document that mentions "lease agreement" in a table
of contents or definitions section without that being a real
boundary), which there wasn't a real corpus available to validate
against here.

### Organization: tags, not folders

Chose a simple flat tag system (a lease can carry any number of tags;
a new `lease_tags` table, `id, lease_id, tag`, `UNIQUE(lease_id, tag)`,
`ON DELETE CASCADE` so deleting a lease can't leave orphaned tag rows)
over a folder hierarchy.
- **Reason**: a folder model forces a choice this project's own users
  explicitly don't have to make up front — "by property, portfolio, or
  however I want to organize them" was the actual request, and a real
  lease often belongs to more than one useful grouping at once (e.g.
  both "Downtown Portfolio" and "Expiring 2026" simultaneously) — a
  strict one-parent-folder model can't represent that without either
  duplicating the lease or picking one grouping arbitrarily over the
  other. Tags don't have that limitation, and they're a smaller,
  simpler addition to the existing relational schema (one small table,
  no tree/parent-child logic, no move/reparent operations to build).
- **Trade-off, stated plainly**: a folder view gives a stronger sense
  of "this lease lives in exactly one place," which some users may
  prefer conceptually. If that turns out to matter later, it's still
  buildable on top of this — a "primary folder" could just be
  "the first tag," or a genuine parent-child folder table added
  alongside tags without displacing them. Not built now because
  nothing in the request required it and it would have been guessing
  at a UI model rather than building the one actually asked for.

## Session 7 (continued): Part 2 — accuracy verified at scale (2026-08-15)

### Tested small/medium/large sizes; found zero app bugs, one test-tooling bug

Requirement: confirm extraction accuracy holds at small (1-5pg),
medium (30-50pg), and large (500pg, multi-lease) PDF sizes, not just
small ones — and fix any accuracy issues found, not just report them.

The real user-uploaded ~500-page/250-lease PDF that originally
surfaced the multi-lease bleed issue could not be recovered (it was
never persisted past the delete-after-processing temp file; Downloads/
Desktop/Documents were searched again this session, still not found —
this is unchanged from the prior session's finding, restated here for
honesty rather than silently re-asserted). In its place:
- **Small**: the existing 10 real fixture PDFs (1-2 pages each,
  `backend/tests/*.pdf`) — already covered by `test_live_api.py` and
  `test_multi_lease_detection.py`, both passing (22/22 test files,
  including live-API tests against a running server).
- **Medium**: a new 35-page synthetic single lease (real terms on
  page 1, 34 pages of realistic exhibit/boilerplate after, generated
  with explicit `showPage()` calls). Verified 100% field accuracy and
  confirmed `detect_lease_boundaries()` correctly returns one
  unsplit range for the whole document — a long document full of
  boilerplate doesn't fool the boundary detector into over-splitting.
- **Large**: a new 60-page synthetic multi-lease document, 60
  genuinely distinct tenants/landlords/terms (no real 500-page file
  was available, so this is explicitly a scale proxy, not the same
  as the original file). Uploaded through the live running API (not
  just the extraction pipeline directly), confirmed: 60/60 leases
  split into 60 separate DB records (no stacking/merging), 0/60
  field-value mismatches against ground truth, 0 anomalies in
  source-page citation or confidence across all ~900 found-field
  checks (15 fields × 60 leases).

**A real bug was found and fixed, but it was in the throwaway test
generator script, not the application**: the first attempt at the
60-lease fixture wrote each single-lease PDF to a reused temp filename
(`_tmp_lease_{i}.pdf`), read it with `PyPDF2.PdfReader`, then deleted
the file immediately before the next loop iteration. `PdfReader` reads
page content lazily rather than eagerly, so by the time
`PdfWriter.write()` actually serialized the merged document (once, at
the very end, after all 60 "adds"), several of the per-lease source
files had already been deleted and their filename reused by a later
iteration — silently corrupting the merged PDF (page 5 ended up a
byte-for-byte duplicate of page 2's content) with no error raised
anywhere. `detect_lease_boundaries()` was directly verified to behave
correctly given that corrupted input (deduping the duplicated page 5
into page 2's boundary was the right call given what was actually on
the page) — confirming the fault was upstream, in the generator, not
in `field_extractor.py`. Fixed by giving every temp file a unique name
and keeping every `PdfReader` reference alive until after the final
`write()`. This fixture-generation script is scratch tooling only,
not part of the repo, so there's no application diff for this fix —
it's recorded here because the debugging process (and the discipline
of checking raw page text before assuming the app was at fault) is
exactly the kind of thing this file exists to capture.

**Also directly re-confirmed** (not just assumed from the prior
session): merging two real fixture PDFs and uploading via the live
API still produces zero field bleed between the resulting leases —
the specific regression this project has previously flagged as
"a known issue" remains fixed.

No application code changes were needed for Part 2 — extraction
accuracy, boundary detection, confidence levels, and source citations
all held correctly at every size tested, including under live-API
upload (not just direct pipeline calls). All 22 test files (17
non-live + 5 live-API) pass with the backend/frontend dev servers
running.

## Session 7 (continued): Part 3 — Excel/Google Sheets export, wired to both views

### Found and fixed a real accuracy gap: the Excel/CSV export was missing 4 of 15 fields

`rent_roll_export.py`'s `COLUMNS` (used by both the CSV and Excel
exporters) only ever covered 11 of the 15 extracted fields — Permitted
Use, Exclusivity Clause, Insurance Requirements, and Default/Cure
Period were silently absent from every rent-roll export, even though
`sheets_export.py`'s Google Sheets export already included all 15.
This was caught by directly comparing the two exporters' `COLUMNS`
lists against each other and against `field_extractor.py`'s actual
15-field output, not by assuming either exporter was complete because
it had tests. Fixed by adding all 4 to `COLUMNS`/`_FIELD_FOR_COLUMN`/
`_COLUMN_WIDTHS`; `_cell_value`'s existing pass-through logic needed no
changes since it was already generic over the field-key mapping. CSV
and Excel now carry all 15 extracted fields (18 columns total, with
the 3 derived: Rent/SqFt, Months Until Expiration, and the Filename
identifier). `test_rent_roll_export.py` updated to assert 18 columns
and to give one fixture lease real values for all 4 previously-missing
fields, so blank-cell-vs-value behavior is actually exercised for them
too, not just implied by symmetry with the other 11.

### Single-lease export: new routes, not a special-cased exporter

Added `GET /leases/<id>/export.xlsx` and
`POST /leases/<id>/export/google-sheets` rather than writing a
separate single-lease rendering path. Both just call the existing
`generate_rent_roll_excel([lease])` / `export_to_google_sheets([lease])`
with a one-item list — the portfolio exporters were already written to
take a list of leases with no assumption about its length, so scoping
to one lease needed zero changes to either exporter module, only two
thin routes in `api.py`. The Excel route names the downloaded file
after the lease's own display name (sanitized to safe filename
characters) rather than the generic `rent_roll.xlsx`, since a
single-lease download landing in a Downloads folder named
`rent_roll.xlsx` next to five other identically-named files would be
useless.

### Export controls added to the Dashboard (list view) and Lease Detail view specifically

The Report view already had portfolio-wide CSV + Google Sheets export
(built in an earlier session) — that was left as-is. This part's ask
was specifically an Export option on the Lease Library (Dashboard) and
the individual Lease Detail view, so two new UI locations were wired,
matching the "choice between Google Sheets or .xlsx" framing exactly
(a Download Excel link plus an Export to Google Sheets button, not a
CSV option, in both new locations) rather than duplicating the Report
view's CSV-inclusive pattern.

### Verified end-to-end, including the exact standard requested: exported data matches the app

For the single-lease Excel route: uploaded a real fixture via the live
API, downloaded the resulting `.xlsx` via the live route, then
compared every one of its 18 cells against that same lease's
`extracted_fields` as returned by `GET /leases/<id>` — zero
mismatches. For the portfolio-wide route: same check at the header
level, confirming all 18 columns are present in a real download, not
just in a unit test with hand-built fixtures. For both Google Sheets
routes (portfolio and single-lease): confirmed the failure path is
clean and actionable — `GOOGLE_APPLICATION_CREDENTIALS` is not
configured in this environment's `backend/.env` (consistent with the
prior session's explicit instruction not to invent or guess
credentials), and both routes correctly return the same
already-existing, safe-to-display "Google Sheets export isn't set up
yet... see backend/.env.example" message rather than a stack trace or
a silent failure — verified both via direct `curl` against the live
API and via the actual rendered UI (jsdom against the real running
app: clicking each Export to Google Sheets button surfaces that exact
message in the page, with zero JS errors). The success path for
Google Sheets itself (a real spreadsheet actually getting created) is
still only verified via `test_sheets_export.py`'s mocks, same as the
prior session — this remains the one piece of Part 3 that needs the
user's own Google Cloud service account credentials to verify for
real; instructions are already in `backend/.env.example`.

22/22 backend test files pass. All test leases created during this
verification were deleted afterward; the dev DB is empty again.

## Session 7 (continued): Part 4 — one shared palette, actually shared this time

### The app screens were never actually on the landing page's palette — fixed at the token level

Session 5 introduced the deep-charcoal/brass/ivory palette but only as
a `landing.css` override — `design-system.css`'s own `:root` still
defaulted to indigo/violet (`#4f46e5`/`#7c3aed`), and that file's
comment already claimed "one cohesive palette, used everywhere" as the
goal without actually achieving it, since `/app/` never loads
`landing.css`. This session's request ("redesign the app screens to
match the landing page's premium feel, not just the landing page")
made that gap concrete: opening `/app/` showed the exact default-SaaS
indigo/violet gradient the landing redesign was built to avoid.

Fixed by promoting the palette values themselves — `--primary-color`,
`--text-dark`, `--background`, the whole neutral scale, `--sidebar-bg`
— into `design-system.css`'s shared `:root`, so `/app/`, `/admin/`,
and the landing page all render one palette by default with zero
per-page override needed. `landing.css`'s own `:root` block was
trimmed to only what's genuinely still landing-specific: a hairline
border color no other page uses, and a deliberately more dramatic
shadow/sharper-radius treatment suited to an editorial marketing page
rather than the app's data-dense screens. Confirmed via computed
`getComputedStyle` values (not just reading the CSS) that `/app/` and
`/` now resolve every checked token — primary, text, background,
sidebar, success/error/warning, confidence, severity — to identical
values.

### Radius left unchanged — this was scoped as a color pass, not a shape pass

Every app component's padding was tuned against the existing 6/10/14/
20px radius scale. Changing radius alongside color would risk visual
regressions with no screenshot-based way to catch them ahead of time
in a pass this size. Kept the radius scale exactly as it was and
scoped this session's changes to color only, per the literal ask
("redesign the color palette").

### Semantic colors deepened toward a jewel-tone register, not hue-shifted

Confidence (high/medium/low) and risk severity (high/medium/low) keep
their red/amber/green mapping exactly — that convention is load-
bearing for scanning a portfolio at a glance, and breaking it would
trade usability for looks, which the request explicitly ruled out.
What changed is saturation and warmth: the old colors were flat,
bright Tailwind-default green/amber/red (`#059669`/`#d97706`/`#dc2626`)
on cool blue-gray tints; the new ones are deeper, more muted jewel
tones (`#2f6b4f`/`#a6741f`/`#9a3b3b`) on warm ivory-tinted backgrounds,
so a risk flag or confidence badge reads as part of the same premium
product instead of a bolted-on default component-library color.

### Six hardcoded off-palette colors found and fixed outside the token file

Auditing `styles.css` directly (not just trusting that token changes
would cascade everywhere) turned up 8 colors that bypassed the design
tokens entirely and would have stayed indigo/violet/default-blue no
matter what the tokens said: the sidebar's radial-gradient glow and
three box-shadow glows (`rgba(124, 58, 237, ...)` / `rgba(79, 70, 229,
...)`, replaced with the brass accent's rgb equivalent), a violet
gradient stop on the empty-state icon (`#f3eeff`, simplified to a flat
`var(--primary-light)` fill — also removes a diagonal-gradient look
the request specifically flagged as templated), a default-blue chip
hover (`#dbeafe`, replaced with a deepened brass tint), and two
hardcoded dark green/red export-status text colors that were
redundant with the (now-deepened) `--success-color`/`--error-color`
tokens and simplified to reference them directly.

### Verified with real screenshots, not just computed-style checks

No Playwright/Puppeteer is available in this environment (a limitation
disclosed in prior sessions too), but this machine does have Google
Chrome installed, and its `--headless --screenshot` CLI flag needs
neither — used directly for the landing page, and a small ~40-line
Chrome DevTools Protocol client (Node's native `WebSocket` and
`fetch`, no npm packages) to drive an already-launched headless Chrome
instance for the app screens that need in-page interaction first
(opening a lease detail view, running a multi-lease comparison) before
the screenshot. Actually looked at, not just asserted: the dashboard
(empty and with real uploaded leases, including risk-flag badges), a
lease detail view with all confidence badges, a lease detail view with
real MEDIUM-severity risk flags, the expiration timeline, the
multi-lease comparison table (explicitly called out as a data-heavy
screen needing careful contrast — confirmed the above-average/below-
average benchmark badges are clearly legible), and the admin waitlist
page. All read as one cohesive, premium product with good contrast
throughout; no leftover indigo/violet found anywhere (confirmed by
grepping the fully-resolved stylesheet text for the old hex/rgba
values, in addition to eyeballing every screenshot). All test leases
created for these screenshots were deleted afterward.

### Follow-up: the printable portfolio report had its own, separate palette — missed on the first pass

Screenshotting every remaining screen (Upload, Ask a Question, and the
in-app Report view) turned up one the design-token audit couldn't have
caught: `report.py`'s printable summary report builds a fully
self-contained HTML document with one inline `<style>` block, by
deliberate design (it's the only output meant to be saved/printed/
emailed with no network dependency — see that module's own docstring).
Being self-contained means it was never wired to `design-system.css`
at all, on the old palette or the new one — its severity badges used
their own independent red/amber (`#b3261e`/`#8a5a00`) that happened to
be close to, but not the same as, the app's old tokens. Viewed inside
the in-app Report screen (in an iframe, right next to the new
palette's buttons and cards), the mismatch was obvious.

Fixed by hand-aligning the report's badge/border/text colors to the
same values now used everywhere else (`#9a3b3b`/`#a6741f`/`#2f6b4f`
for high/medium/low, the same warm neutral grays), without touching
its structure, layout, or print rules — it's still a light-background,
ink-restrained, `@media print`-tuned document, just one that now uses
the same specific colors as the rest of the product instead of a
similar-looking but independently-chosen set. `test_report.py` doesn't
assert exact hex values (it asserts structure/content), so no test
changes were needed; all 11 report tests still pass.

## Session 8: Client-facing product pass, Phase 2 — a real request-access + pending-approval gate

### Extended the existing waitlist system rather than building a second one

The new request asked for "new users sign up but land in a pending
state" and "until approved, show a pending approval screen instead of
the dashboard." Both already existed in substance — the landing page's
waitlist form + `/waitlist` (status `pending`) + `/admin/waitlist/`
approve/deny — just not reachable from the app itself, and not
rendered as a dedicated screen. Rather than building a parallel
"users" concept, extended `access-gate.js` (`frontend/app/`) into
three swappable panels inside the same card: sign-in (existing),
request-access (new — a plain email form posting to the same
`POST /waitlist` the landing page already uses), and pending-approval
(new — a dedicated screen, not an inline message next to a form).
- **Reason**: the schema this needs already exists
  (`waitlist_signups: email, created_at, status`) and is already
  covered by a real admin approval flow — inventing a second,
  parallel "user account" concept would duplicate that state and
  create two sources of truth for "is this person allowed in" with no
  new requirement actually asking for anything the waitlist model
  can't represent. No backend changes were needed for this phase at
  all; everything is new frontend state built on existing endpoints.

### Still explicitly not real authentication

Same caveat as before, restated because this phase makes the flow
*feel* more like a real signup than it did previously (a dedicated
pending screen reads as "your account is being set up," not just "an
email on a list"): there is still no password, and "access" is still
a self-reported email checked against a status column, not a verified
identity. `access-gate.js`'s own header comment and DECISIONS.md's
earlier "Access gate uses self-reported email, not real auth" entry
still apply unchanged. If this product moves toward real customers
with real login credentials, that's a genuinely separate build (a
`users` table with password hashes or an OAuth provider, sessions,
etc.), not an extension of the waitlist gate.

### Verified the full state machine live, not just each panel in isolation

Wrote a jsdom harness that drives the real gate against the real
backend through every transition in one run: unknown email -> error
message (still on sign-in) -> click "Request access" -> prefilled
request panel -> submit -> pending panel with the right email shown ->
"Check again" while still pending (correctly stays put) -> approve the
signup via the actual admin API (not a mock) -> "Check again" ->
gate hides, app shell (with a working dashboard nav) shows. All 9
checks passed on the first fully-wired run. Required briefly disabling
`LOCAL_DEV_MODE` (it bypasses the gate entirely, by design) and
restoring it after — done via a real `.env` edit + server restart
each way, backed up first, confirmed restored via `/config` afterward.

Also screenshotted all three panels with the same headless-Chrome/CDP
approach from the Part 4 redesign work, which caught one real bug the
functional test couldn't: the "Request access" and "Use a different
email" links are `<button type="button">` now (they weren't before —
they used to be a plain `<a>`), and picked up the browser's default
button chrome (a visible border box) since `.access-gate-link` had
never needed to reset that. Fixed by resetting `background`/`border`/
`padding`/`font` on that class. A pure functional/DOM test would never
have caught this — only actually rendering it would.

## Session 8 (continued), Phase 3 — checkbox selection rolls up to a live summary panel

### New endpoint reuses compute_portfolio_metrics rather than a second summing routine

`GET /leases/selection-summary?ids=1,2,3` (new, in `api.py`) calls the
exact same `compute_portfolio_metrics()` that already powers the
portfolio-wide dashboard tiles, just over the caller's subset of
leases instead of every lease. No new aggregation logic was written.
- **Reason**: this project already has one documented instance of
  exactly this reasoning (`portfolio_context_for_risk_analysis`, "so a
  risk flag citing a number the dashboard disagrees with would
  undermine the whole point") — a selection-summary total is the same
  category of risk. Computing sums a second way client-side (parsing
  "$6,250.00" strings in JS) would create two independent places a
  currency-parsing edge case could be fixed in only one of them and
  silently diverge from the other. Mirrors `/leases/compare` and
  `/leases/<id>/benchmark`'s existing `?ids=` pattern rather than
  inventing a new request shape.
- Unlike `/leases/compare` (requires 2+ ids), a single selected lease
  is allowed here — its "total" is just its own numbers, which is
  still a meaningful thing to show. Doesn't log an activity-feed
  entry, unlike a run comparison: checking a box to glance at a
  running total is routine browsing, not a distinct action worth an
  audit trail entry.

### Selection summary is additive to Compare, not a replacement for it

The existing "Select to compare" checkbox mode now drives two
independent pieces of UI: the existing compare-bar (2+ selected ->
"Compare Selected" navigates to the side-by-side Compare view,
unchanged) and a new inline summary panel (1+ selected -> live rollup
tiles, reusing the exact `.metric-tile` markup/CSS the portfolio-wide
tiles already use, so it reads as the same kind of number in the same
place rather than a bolted-on second summary style). A "latest
request wins" token guards `updateSelectionSummary()` against a rapid
run of checkbox clicks resolving out of order and overwriting a newer
total with a stale one.

### Status filter mirrors the Timeline view's own 6-month bucketing exactly

The new "Expiring soon" status option reuses `portfolio.py`'s
`DAYS_PER_MONTH = 30.4375` constant and its `< 0` / `< 6` month
thresholds verbatim in a client-side `leaseStatus()` helper, so a
lease the dashboard filter calls "expiring soon" can't disagree with
the Timeline view's "Expiring within 6 months" bucket for the same
lease — same reasoning, and the same established pattern, as Part 1's
`parseLeaseDate()` mirroring `normalize.py`'s date parsing. A lease
with no parseable end date matches neither the status filter nor the
date-range filter (excluded, not guessed into a bucket) — consistent
with how the rest of the app treats missing dates.

### Verified live: checkbox selection, deselection, and both new filters

jsdom driving the real running app against 3 real uploaded fixtures:
selecting all 3 shows the correct 3-lease totals (cross-checked
against a direct `curl` of the same endpoint — identical numbers);
deselecting one live-recomputes to the correct 2-lease totals; the
panel correctly hides again at zero selected. Status and date-range
filters both correctly narrow the visible rows. Also screenshotted the
populated dashboard to confirm the new filter row and the selection
summary panel render correctly, consistent with the existing tile
style. 22/22 backend test files pass; all test leases created for
verification were deleted afterward.

## Session 8 (continued), Phase 4 — genuinely per-file upload status

### Found the real gap: every progress row updated together, at the end, not live

Before this phase, a multi-file upload showed a spinner next to every
selected file immediately, then flipped ALL of them to done/error
simultaneously — only once the entire batch finished, because the
frontend sent one `POST /leases/batch` request and waited for the
single combined response. A 3-file batch with one large, slow file and
two small, fast ones would leave the two fast files' rows sitting on a
spinner for as long as the slow one took, giving no true indication
that they'd actually already finished. This matched the letter of
"show extraction status per file" (each file did have its own row) but
not the substance of it (the status shown wasn't actually live).

### Switched to sequential per-file requests, not a new backend endpoint

Rather than building server-sent events or WebSockets for real push
updates — a large jump in complexity for what's fundamentally "update
a DOM element as each of N sequential awaits resolves" — `upload-
view.js` now calls `POST /leases` once per file in a `for` loop with
`await`, updating that file's own row immediately when its request
resolves, before moving to the next file. This is still sequential
over the network (file 2 doesn't start until file 1's response comes
back), but it does not block the browser's UI thread — `await` yields
control back to the event loop between requests — and critically, each
row's displayed status now reflects reality the moment it's true,
instead of waiting for the slowest file in the set.
- **Reason for sequential over parallel**: predictable load on the
  extraction pipeline (each upload can trigger real OCR work) and
  simpler, easier-to-reason-about error isolation, matching what
  `/leases/batch`'s server-side `for` loop already did — this is the
  same processing order, just with the status now surfaced after each
  step instead of all at once at the end. The existing `/leases/batch`
  endpoint and its tests are untouched and still valid; the frontend
  just no longer calls it for the drag-and-drop flow, since real
  per-file live status isn't achievable through one combined response
  no matter how the request is shaped.

### Verified the staggering is real, not just structurally plausible

Uploaded 3 real fixtures (one of them the 35-page medium document from
the earlier accuracy-verification phase, deliberately included because
it takes measurably longer than the small ones) and polled the DOM
every 15ms during the upload. The captured transitions show file 1
reaching "processing" at t=15ms while files 2 and 3 are still
"pending," file 1 finishing and file 2 starting at t=45ms while file 3
is still waiting, and file 3 finally starting only once file 2 is
done — direct proof the rows update independently and in true upload
order, not cosmetically. Separately verified the error path with a
genuinely corrupted PDF mixed into a batch of valid ones: the bad file
gets its own clear error row and detail message, the two valid files
still complete and get created normally, and the summary count
correctly reads 2 succeeded / 1 failed. Screenshotted all four visual
states (pending / processing / done / error) together. 22/22 backend
test files pass (backend was unmodified — this phase was frontend-
only); all leases created during verification were deleted afterward.

## Session 8 (continued), Phase 5 — consistency audit, not a second redesign

### Asked before assuming: "new palette/typography/spacing" vs. a consistency pass

The task's DESIGN section read as a from-scratch redesign brief ("new
color palette, typography, spacing... should look like a professional
B2B SaaS product"), phrased the same way it would be if this were the
first design pass on the app. It isn't — the app was already fully
redesigned earlier in this same session (the deep-charcoal/brass/ivory
palette promoted from the landing page into the shared token file,
verified screen-by-screen with real screenshots), and every piece of
UI built in Phases 2-4 (gate panels, filter row, selection summary
tiles, upload status rows) was already built using those same existing
tokens and component classes, not new ones. Redoing the palette from
scratch here would have discarded already-verified work for no stated
reason, so this was raised directly rather than guessed at either way
— asked whether Phase 5 meant "consistency pass" or "genuinely
propose something different," confirmed: consistency pass.

### What the audit actually checked

Grepped every CSS/JS file touched in Phases 2-4 for hardcoded hex
colors bypassing the token system (none found — the one apparent match
was `#accessGateForm`, a CSS ID selector, not a color) and diffed the
font-size/spacing values added since the Part 4 redesign against the
existing scale (all reused already-established values — `0.75rem`,
`0.8125rem`, `0.9375rem` for type; `0.4rem`/`0.5rem`/`0.75rem` for
spacing — nothing new introduced). Also screenshotted the dashboard
and the access gate at two tablet breakpoints (820px, matching the
existing `>768px` layout, and 700px, matching the existing `<=768px`
horizontal-sidebar layout) specifically because "responsive for
desktop and tablet" was an explicit requirement and none of this
session's earlier screenshots had been taken below desktop width —
both breakpoints already handled the new filter row and selection
panel correctly via the existing `flex-wrap` on `.table-controls`,
with no CSS changes needed.

No code changes were required for Phase 5 — the audit confirmed the
Phase 2-4 work was already consistent with the established design
system rather than finding drift to fix.

## Session 9: Trust-and-polish pass, Part 1 — first-impression trust signals

### Google Fonts moved from CSS @import to a real <link>, with preconnect

Found a genuine "could cause a visible reflow on the hero" issue while
auditing for load-time layout shift: Inter was loaded via `@import
url(...)` split across two files (`design-system.css` for weights
400-800, `landing.css` for weight 900 alone), and for `/app/` and
`/admin/`, that import was itself one more hop deep (`styles.css`
`@import`s `design-system.css`, which `@import`s the font). `@import`
inside a stylesheet is only discovered once that stylesheet has
already been fetched and parsed — the browser's HTML preload scanner
can't see it during initial page parse the way it can see a `<link>`
tag — so the font request starts later than it needs to, and two
separate font requests (one per weight range) doubled that delay
further. A large `h1` rendering first in a fallback system font and
then re-flowing once Inter 900 finally arrives is exactly the kind of
shift the request called out.

Fixed by removing both `@import`s and adding `<link rel="preconnect">`
(googleapis.com + gstatic.com) plus a single combined `<link
rel="stylesheet">` requesting all six weights (400-900) in one request,
directly in the `<head>` of all three HTML entry points (landing,
`/app/`, `/admin/waitlist/`) — discovered immediately by the preload
scanner, in parallel with everything else, and shared across pages via
one cache entry instead of three separate ones.

### Added a 3-step "How It Works" section (didn't exist before)

Nothing on the landing page walked a first-time visitor through
upload → extract → review/export before this — the page went straight
from the hero to a 6-item capabilities grid, which explains *what* the
product does but not *how a session actually goes*. Added a 3-card
"From PDF To Portfolio Clarity In Three Steps" section between the
hero and capabilities (Upload → We extract every term, with confidence
+ citations named explicitly → Review, compare, export), reusing the
same `.section-heading` pattern as capabilities so it doesn't read as
a bolted-on afterthought, but visually distinct (filled numbered
circles vs. capabilities' outlined icon circles) so it doesn't get
confused with the feature list right below it.

### Removed the footer's placeholder links instead of leaving them dead

The footer had `<a href="#">Privacy</a>`, `Terms`, `About` — already
self-documented in a comment as "placeholders (dead links) until those
pages exist." Per this pass's explicit instruction to remove sections
with nothing honest to put there rather than leave a placeholder: since
no real Privacy/Terms/About pages exist yet, removed the links
entirely rather than inventing fake destinations or leaving `#`
anchors a visitor could click and get nowhere. The real contact line
(email + phone, already genuine) and copyright stay. Worth revisiting
once real policy pages exist.

### No fake stats or testimonials found — nothing to remove there

Read the full landing page looking specifically for fabricated social
proof (customer counts, logos, quotes) since that was named explicitly
in the request. Found none — the existing copy already only describes
real product capabilities, not invented traction numbers. Confirmed
via a full-page grep for "lorem", "TODO", "TBD", "coming soon", and
similar markers too — none found anywhere in the landing page, gate,
or admin view's HTML/JS.

### Verified zero console errors and zero visible broken links, live

Wrote a jsdom harness with a custom `VirtualConsole` capturing
`jsdomError`/`console.error`/`window error`/`unhandledrejection`
across five real scenarios: landing page load, landing waitlist
submission, gate sign-in with an unknown email, the new request-access
-> pending flow, and the admin waitlist page. Zero errors in all five.
A literal-DOM-query pass also flagged 3 `href="#"` anchors on the gate
page — traced each one to its ancestor chain and confirmed all three
sit inside `display:none` containers (the hidden `.app-shell` and its
not-yet-loaded dashboard/detail/report views) at every level, so
they're not actually visible or clickable while a visitor is on the
gate; this is the existing, deliberate "real href gets set by that
view's own `load()`, once it loads" pattern from the export-button
work, not a bug. All test waitlist signups created during this
verification were deleted from the dev DB afterward.

22/22 backend test files pass (this part touched only frontend
HTML/CSS, no backend changes).

## Session 9 (continued), Part 2 — reliability polish + full new-user flow

### Found and fixed a real error-message bug: `err.message || "fallback"` doesn't work

Auditing every error path for "no raw error codes or stack traces ever
visible to a user" turned up a genuine bug, not just a hypothetical
risk: `access-gate.js`'s three catch blocks used
`err.message || "Couldn't reach the server..."` to fall back to a
friendly message when something goes wrong. That pattern only works if
`err.message` can be falsy — but a raw `fetch()` network failure
(backend unreachable, DNS down) throws with a non-empty technical
`message` ("Failed to fetch" in a browser, "fetch failed" in this
project's own Node-based test harness), so the `||` never falls
through and the raw string reaches the screen verbatim. Reproduced
directly: killed the simulated network path and watched the literal
string `"fetch failed"` appear in the gate's error text.

Fixed at the source rather than patching each `||` site (which is what
produced the bug in the first place — easy to get subtly wrong per
call site): `api.js`'s shared `apiRequest()` now wraps its own
`fetch()` call in a try/catch and re-throws one consistent friendly
message on any network failure, before the raw error ever reaches a
caller's `catch`. `access-gate.js` can't use `apiRequest()` (it runs
before `api.js` is even loaded — it's the thing that decides whether
to load it), so it got its own copy of the same fix via a small
`fetchJson()` helper. Grepping for every other raw `fetch(` call in
the frontend turned up two more unprotected sites that needed the same
fix independently: `landing.js`'s waitlist form (the single most
visible form on the whole site) and `admin/waitlist/admin.js`'s two
calls — both fixed the same way, each inline since these are
standalone scripts with no shared module to fix once for both.

### Closed a blank-page gap at initial load

`#accessGate` and `#appShell` both start `display:none` in the raw
HTML; nothing decides which one to show until `access-gate.js`'s
`GET /config` round trip resolves. On a slow connection that's a
window where the page is blank — not broken, but exactly the kind of
moment the request called out as looking "frozen." Added
`#appBootLoading`, a small centered spinner with no inline
`display:none` (so it's the thing painted first, before any JS runs),
hidden by every one of access-gate.js's decision points (`showSignIn`,
`showRequestAccess`, `showPending`, `grant`) the instant they run.
Verified with an artificially delayed `/config` response: at t=50ms
(mid-fetch) the spinner is showing and neither the gate nor the app
shell is visible yet; once the fetch resolves, the spinner is gone and
the correct one of the other two is showing — no blank frame either
side of the transition.

### Verified the complete new-user journey end to end, live, all in one run

Not a series of isolated checks — one script that plays out the actual
sequence a first-time visitor would go through against the real
running app: land on the landing page, submit "Request Access" with a
brand-new email, visit `/app/` before being approved (confirmed it
correctly lands on the pending screen, not the dashboard), approve the
request through the real admin panel (clicking the real button, not
calling the API directly), sign back in now that it's approved, upload
a real lease PDF, open its detail view and confirm all 15 field cards
show both a citation and a confidence badge, and confirm the Excel
export link is correctly set. Zero JS errors at any point in the whole
sequence. All test data (the lease, the waitlist signup) deleted
afterward; `LOCAL_DEV_MODE` was toggled off to exercise the real gate
for this test and restored afterward, confirmed via `/config`.

22/22 backend test files pass throughout (all fixes this part were
frontend-only).

## Session 9 (continued), Part 3 — data confidence

### Coverage was already architecturally guaranteed — re-verified, didn't rebuild

`detail-view.js`'s `createResultCard()` is the single code path every
one of the 15 extracted fields renders through — there's no per-field
branching that could let one field type quietly skip its confidence
badge or citation. Re-verified this holds in practice, not just in
theory: uploaded all 10 of this project's real fixture PDFs (each with
a different field-presence pattern — some missing clauses, some with
every field found) through the live API and checked every field on
every one for exactly two failure modes: a found field missing its
confidence or citation, or a not-found field carrying stray citation
data it shouldn't have. Zero anomalies across all 10 fixtures × 15
fields. Nothing needed fixing here; the ask to "add it if any field
type is missing this" turned out to already be satisfied.

### Added the accuracy explainer, not present before

Nothing on the lease detail view told a buyer *why* the citations and
confidence badges are there — they were just present, which a careful
reader would notice but a first-time skimmer might not register as a
deliberate differentiator. Added a short "Why this matters" callout
directly above the field cards (replacing the old terse one-line
`.edit-hint`, whose "click to correct" guidance is folded into the new
note's closing sentence rather than dropped): names explicitly that
every value traces to a source page/quote, that confidence is
attached, and that a citation can be clicked to verify against the
original document. Styled with the same jade/`--confidence-high`
tokens used for high-confidence badges elsewhere, so it reads as
reinforcing that system rather than introducing a new visual language.
The now-unused `.edit-hint` CSS rule was removed rather than left as
dead code.

Screenshotted the result on a real uploaded lease to confirm placement
and legibility. 22/22 backend test files pass (frontend-only change).
Test lease deleted afterward.

## Session 9 (continued), Part 4 — final visual QA, two widths

### Found and fixed a real overflow bug: the lease detail action buttons

`.detail-actions` (Export JSON / Download Excel / Export to Google
Sheets / Delete) was a plain `display: flex` row with no wrap. It had
room to spare at desktop width, but Part 3's Google Sheets button
addition (an earlier session) pushed the row's natural width past what
a tablet viewport (820px) has available, and with no `flex-wrap`, the
last button was clipped at the viewport edge rather than dropping to a
second line. Fixed with `flex-wrap: wrap` — same one-line fix already
correctly in place on the sibling `.export-actions` block, just missed
on this one when the button was added. Verified the wide comparison
table's own horizontal scroll doesn't leak into a page-wide scrollbar
either (`body.scrollWidth === document.documentElement.clientWidth` at
tablet width) — that one was already correctly contained.

### Found and fixed a real, pre-existing contrast bug: the landing page nav was nearly invisible

While screenshotting the landing page at both widths for this pass,
noticed the top nav (brand name, "How It Works," "Capabilities,"
"Request Access," "Client Login") wasn't rendering at all — not a
sizing/wrapping issue this time, a color one. Diagnosed methodically
rather than guessing: confirmed via `getComputedStyle` that color,
opacity, and visibility were all "correct" and the elements were
correctly hit-testable and on top (`elementFromPoint` returned the
right `<a>` tag) — ruling out a covering-element or stacking-context
theory. Forcing an obviously-wrong bright red/yellow override made the
text immediately visible, which combined with `getBoundingClientRect()`
on `.landing-nav` vs `.hero` (nav: y 0-140; hero starts at y 140) and
`getComputedStyle(document.body).backgroundColor` (`rgb(246,243,236)`,
the ivory token) pinned the actual cause: `.landing-nav` sits in normal
document flow *before* `.hero`, so it paints against the page's own
ivory background — but `.landing-brand` and `.landing-nav-links` were
both styled with light/`--lux-ivory` text colors clearly meant for
sitting *over* the dark hero. Ivory text at up to 65% opacity on an
ivory background is a near-zero-contrast bug, not a deliberate
transparent-nav-over-hero look — the markup never actually positions
the nav over the hero, so that light-on-dark styling never had a
backdrop that would make it visible. This is not something this
session introduced; it's been present since the nav was first built,
just never caught because no prior screenshot happened to scrutinize
that specific region closely enough to notice genuinely-missing text
rather than assume it simply hadn't been looked at yet.

Fixed by switching `.landing-brand`, `.landing-nav-links`, and
`.nav-client-login`'s border to the same dark-ivory-appropriate tokens
the rest of the page's light-background sections already use
(`--text-dark`, `--text-medium`, `--border-color`), and the hover
color to the brass accent instead of ivory (which would have the same
invisibility problem). Verified fixed with a fresh screenshot: brand
name and all four nav links now clearly legible against the ivory
background.

This is exactly the class of bug a "make sure nothing looks broken"
pass exists to catch, and exactly why the instruction to actually
screenshot and look — not just trust that a component was styled
correctly when it was written — mattered here: every computed-style
diagnostic said the text was "there," and it still wasn't visible to
an actual visitor.

Re-ran the full backend suite after both fixes: 22/22 pass (both were
frontend CSS-only changes). All QA test leases deleted afterward.

## Session 10: Pre-sale technical audit, Part 1 — test coverage

**Exact numbers, as requested**: 22/22 test files passing, 555/555
individual checks/assertions passing (the finer-grained count — most
files are one `assert` per named `test_...()` function, a handful use
an explicit checks-list with their own "N/N" reporting, both counted
at that finest granularity and summed). Includes real OCR, not mocked
— see below.

### Inventoried every route, field, export path, and named edge case against actual test coverage — didn't assume

Went through all 35 backend routes and cross-referenced each against
every test file's content (not just filenames), all 15 extracted
fields, and the 7 edge cases named in the request (empty/corrupted/
huge/tiny/non-English/scanned/multi-lease PDF). Found 4 real gaps and
fixed all 4, plus one more found by accident while fixing them:

1. **`GET /leases/selection-summary` had zero test coverage.** Added
   route-level checks (2+ ids, exactly 1 id — allowed here unlike
   `/leases/compare`, 0 ids returns 400, nonexistent id returns 404)
   to `test_live_portfolio_api.py`.
2. **The single-lease export routes (`GET /leases/<id>/export.xlsx`,
   `POST /leases/<id>/export/google-sheets`) had zero test coverage**
   — only their portfolio-wide siblings were tested, even though
   they're separate route handlers with their own not-found/success
   paths. Added real xlsx-content and mocked-Sheets-response tests for
   both.
3. **A dead test, hiding as a live one**: `test_sheets_export.py` had
   two fully-written test functions
   (`test_route_returns_200_with_url_on_success_and_logs_activity`,
   `test_route_does_not_log_activity_on_failure`) that were never
   actually invoked — `run_all_tests.py` runs each file as a
   subprocess, which only executes what's inside `if __name__ ==
   "__main__":`, and these two calls were missing from that block.
   They'd been silently not-running, passing by never being asked to.
   Found this by writing a quick AST script to check every test file
   for exactly this pattern (defined-but-never-called) — which itself
   had a bug (a broken `ast.Compare` check produced a false positive
   here, which I almost "fixed" by adding duplicate calls before
   re-reading the file and catching my own mistake). Correctly fixed
   by reading the actual `__main__` block directly rather than trusting
   the script's output blindly — the same "verify, don't just script
   something once and trust it" discipline this project applies to
   everything else.
4. **The XSS/injection round-trip test was silently skipping.**
   `test_security_hardening.py`'s XSS check read a fixture PDF from a
   hardcoded `/tmp/xss_test_lease.pdf` path that nothing in the repo
   ever generated — it happened to still exist on this machine from
   an earlier session's manual scratch work, so the check always
   looked green, but would silently no-op (not fail, just never run)
   on a fresh clone or CI runner with no memory of that file. Rebuilt
   as an in-memory reportlab PDF generated fresh every run. While
   rewriting it, found the test's own assumption was wrong too: it
   targeted the *tenant* field, but the tenant/landlord name pattern's
   character class (`[A-Za-z0-9&,.'\-\s]`) can't match `<`/`>`/`/` at
   all, so a script tag there correctly extracts as not-found — never
   actually reaching the "does captured script-like text round-trip
   safely" question the test existed to answer. Retargeted to
   `permitted_use`, whose pattern (`[^.]{5,150}`) has no such
   restriction and genuinely captures the payload — confirming it
   round-trips as inert JSON string data (the API never renders HTML;
   the frontend's `escapeHtml()`, already covered elsewhere, is what
   makes this safe on screen).
5. **"Large PDF" and "non-English text" had never been tested at
   all** (empty PDF was already covered incidentally by the corrupted-
   PDF test's random-bytes case reading 0 usable pages the same way,
   confirmed by inspection, not assumed). Added three new permanent
   tests: a genuinely empty (0-page, structurally valid, not
   corrupted-bytes) PDF fails the same clean way a corrupted one does;
   a Spanish-language lease with accented characters extracts without
   crashing and every field honestly comes back not-found rather than
   fabricating a match (the extraction patterns are English-only by
   design); and a permanent 35-page single-lease document (real terms
   on page 1, 34 pages of exhibit boilerplate) that's now a real
   regression test instead of the ad-hoc scratch-script verification
   an earlier session did by hand and never locked in — confirms both
   that extraction doesn't degrade on a realistically long document
   and that `detect_lease_boundaries()` doesn't mistake "long" for
   "multi-lease" and over-split it.

### Real OCR, not mocked — but flagging what that actually took

`test_real_ocr.py` requires real `tesseract`/`poppler` binaries and
was **silently SKIPPING** at the start of this audit — this shell
session's `PATH` didn't include them, even though a prior session
installed them via Miniforge conda-forge into `~/.miniforge3/bin`
(documented in PROGRESS.md). Confirmed the binaries were still
genuinely present on disk (not reinstalled — verified with `ls`
directly) and re-ran with `PATH` corrected: real OCR pipeline
re-verified end to end, 7/7 fields correct. This is a real
environment-fragility point worth naming plainly for the sale-
readiness report: OCR support depends on a `PATH` export that isn't
persistent across shells/sessions/deploys unless something (a
`.bashrc`, a Docker image, a systemd unit) sets it — worth fixing
properly (baking the binaries or the `PATH` export into whatever
actually runs this in production) before relying on OCR working
by default in a new environment.

22/22 test files, 555/555 checks. Dev DB confirmed empty throughout
(all route tests clean up after themselves or use isolated temp DBs).

## Session 10 (continued), Part 2 — code quality pass

### What was already solid — said so, didn't redo it

Swept for TODO/FIXME/XXX markers, `console.log`/`console.debug` in the
frontend, and dead code across the whole repo: **found none**. The
lease-splitting/extraction logic (`detect_lease_boundaries`,
`extract_multiple_leases` in `field_extractor.py`) already has
extensive inline reasoning — why the union-of-tenant-and-landlord
signal was chosen over either alone, the exact known limitation where
it can't tell apart two leases sharing both party names, and pointers
to the tests and DECISIONS.md entries that verify each claim. Backend
normalization logic (`parse_currency`, `parse_date`,
`parse_square_footage`, `rent_per_sqft`) exists in exactly one place
(`normalize.py`), reused everywhere rather than reimplemented.
Error handling for all three external service integrations (OCR,
email, Google Sheets) is already consistent and genuinely
defensive — email in particular has two deliberate, documented layers
(`email_service.py` catches internally and returns `False`;
`api.py`'s `_send_email_best_effort` catches again at the call site,
explicitly "belt and suspenders" so a future bug in the email path can
never turn a successful signup into a 500). Nothing needed fixing in
any of this.

### Fixed: raw `print()` instead of the established `logging` convention

`pdf_extractor.py` was the one file still using bare `print()` for
diagnostics and error reporting, while `api.py`, `email_service.py`,
and `sheets_export.py` all consistently use Python's `logging` module
(`logger.exception(...)` for real errors, so a full traceback lands in
server logs without ever reaching a client response). Switched all 4
call sites to `logger.info`/`logger.warning`/`logger.exception` to
match. Re-ran the OCR test suite (including real, non-mocked OCR) to
confirm the behavior itself didn't change, only where the diagnostic
output goes.

### Fixed: a genuinely significant hardcoded value — `API_BASE_URL` in four separate files

`landing.js`, `app/access-gate.js`, `app/api.js`, and
`admin/waitlist/admin.js` each independently declared their own
`const API_BASE_URL = 'http://localhost:5000'` — four copies of the
same value, with no way to point this frontend at a real deployed
backend without editing all four and risking missing one (a real
pre-launch deployment blocker, not just tidiness). Extracted to one
new file, `frontend/config.js`, loaded as the first `<script>` in all
three HTML entry points (landing, `/app/`, `/admin/waitlist/`) —
classic `<script>` tags in one document share a single top-level
lexical scope, so every later script (including `access-gate.js`'s own
IIFE, via closure) sees the same `API_BASE_URL` by name, no import or
`window.` prefix needed. To point this frontend at a real backend now,
one line in one file changes; nothing else does.

This was a genuinely high-risk change to make blind (it touches how
literally every page reaches the backend), so it was verified live,
not just visually inspected: a jsdom check confirmed `API_BASE_URL` is
defined with the right value and zero JS errors on all three entry
points, that the dashboard still actually loads leases through a real
fetch call, and a direct functional round-trip (upload via the real
API, then confirm the dashboard's own fetch — through the new
config.js-sourced URL — renders that same lease) before considering it
safe.

Also fixed the same category of issue in `run.py`: the Flask dev
server's port was hardcoded to 5000. Now reads `PORT` from the
environment (falling back to 5000), matching how the file already
handled `FLASK_DEBUG` — many hosting platforms assign a port via
exactly this env var and expect the app to read it rather than
guessing a fixed one.

### Noted, deliberately not fixed: duplicated test-helper functions

`_request()`/`_multipart_body()` (the raw-HTTP test helpers) are
copy-pasted with minor signature drift across `test_live_portfolio_
api.py`, `test_live_multi_lease_api.py`, `test_live_dashboard_api.py`,
and `test_security_hardening.py`. Real duplication, but low severity —
it's test-only code with no effect on the shipped product, the
signatures have already drifted slightly (some take `json_body`, some
don't; `_multipart_body` takes different argument shapes), and
properly unifying it means touching four already-comprehensive,
currently-passing test files' worth of call sites for a maintainability
win with no product-facing benefit. Given the actual blockers still
ahead for this pass (real auth, multi-tenancy, backups), this was
deliberately left as a documented, known item rather than spending the
time now — flagged here explicitly rather than silently skipped.

Also noted: one frontend helper, `lease_filename()`, is snake_case
against the rest of the frontend's consistent camelCase — a single
trivial cosmetic inconsistency, not fixed for the same reason (touches
many call sites for zero functional benefit).

### Also surfaced (not this section's job to fix, flagged for the sale-readiness report)

Restarting the backend during this pass surfaced two things worth
carrying into the honest report rather than losing track of: Flask's
own startup output warns "This is a development server. Do not use it
in a production deployment" (this project has no production WSGI
server — gunicorn, uwsgi — configured at all), and this environment's
Python (3.9.6) is past its official end of life per warnings from the
`google-auth` library. Neither is a "code quality" fix in the sense
of this section; both are real pre-launch items.

22/22 test files, 555/555 checks, unchanged from Part 1 (no test
counts should change from a pure code-quality pass — confirmed they
didn't). Dev DB confirmed empty after the live verification above.

## Session 10 (continued), Part 3 — security re-verification

This part is mostly re-verification, not new code — recorded here for
the trail, with the actual recommendation in the final sale-readiness
report.

### Input validation: re-verified, solid, no new gaps

Covered by Part 1's expanded `test_security_hardening.py` (19/19):
oversized files (413), corrupted PDFs (500, clean message), a genuine
empty 0-page PDF (500, clean message), malformed lease IDs (404, not a
500/traceback), unknown routes (JSON 404), and script-tag content in
extracted fields (round-trips as inert JSON, confirmed via the
`permitted_use` field specifically, since the party-name fields'
character class can't even match it).

### No secrets anywhere — checked content, not just filenames

`backend/.gitignore` (found on the second look — the *repository
root* `.gitignore` only covers `.claude/`, but `backend/.gitignore` is
thorough: `.env`, `*.db`, `credentials/*.json`, `venv/`, all present
with clear comments naming exactly what each protects, e.g. "Real
secrets (Gmail App Password, etc)"). Confirmed `.env` has never been
tracked. Went further than a filename check: grepped the full `git log
--all -p` history for common API-key shapes (`AIza...`, `sk-...`),
PEM private-key headers, and credential-looking assignments. One hit,
inspected in context: a private key string in a test fixture — literal
text `"-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n"`,
explicitly documented in its own docstring as "a syntactically-
plausible (but fake) service account key... never sent anywhere real
since google.auth itself is mocked." Not a leak.

### The admin waitlist route has no real authorization — confirmed live, not assumed

This is not a new finding — `api.py` already carries an explicit
comment block above these routes stating plainly that `/waitlist`
(GET, lists every signup's email) and `/waitlist/<id>/approve` (POST)
are unauthenticated by deliberate current-stage product decision, and
"MUST be locked down behind real auth before this goes live to real
users." Re-verified it's actually true right now, not just documented
as a past decision: `curl -s http://localhost:5000/waitlist` with zero
headers, zero credentials, returns `200` and the full signup list.
**Per the explicit instruction not to downplay this: this is a real
blocker for selling to companies**, not a nice-to-have. Anyone who
discovers the admin URL can read every prospective client's email and
grant themselves (or anyone) access to the product. Full assessment
and recommendation in the final report — this section's job was to
confirm the gap is real and current, which it is.

### No rate limiting anywhere — confirmed absent, flagged as a gap (not built here)

No rate-limiting library (Flask-Limiter or equivalent) is in
`requirements.txt` or referenced anywhere in `app/`. Every route,
including the PDF-processing upload endpoints (CPU/memory-intensive,
especially the OCR fallback path) and the unauthenticated waitlist
routes, has no request-volume protection at all — a single caller
could hit `/leases` or `/extract` in a tight loop, or hammer
`/waitlist` to enumerate/spam-approve. Per the request's own framing
("if none exists, flag it as a gap") this section's job was
confirmation, not implementation — recorded as a real gap for the
sale-readiness report, not silently built without being asked.

## Session 10 (continued), Part 4 — data handling and reliability

### Storage survives a hard crash and concurrent uploads — verified empirically, not assumed

Storage is real file-backed SQLite (`backend/lease_portfolio.db`, not
`:memory:`), with every route opening its own connection, always
closed in a `finally`, and every write explicitly `commit()`-ed before
the connection closes — so there's no long-lived in-memory state a
crash could lose and no batched-write window where a crash could catch
a commit half-done. Verified directly rather than trusting that
description: uploaded a lease, hard-killed the server process with
`kill -9` (not a graceful shutdown), restarted it, and confirmed the
lease was still present with all fields intact. Separately, fired 5
simultaneous uploads at the running server and confirmed all 5
persisted (`lease_count` correctly read back as 5) with no lost or
corrupted rows — SQLite's own file-level locking serializes the
concurrent writes safely without any additional code needed here.

### Multi-lease splitting: real bug found and fixed while testing against structural variation

The request specifically asked not to trust the splitting logic
against just the one sample PDF already in the repo. Built
`test_multi_lease_structural_variation.py` with three genuinely
different document shapes (not just re-shuffled sample text): each
lease spanning 2 pages instead of 1, financial/term clauses stated
*before* the parties are named instead of after, and "Lessor"/"Lessee"
terminology with numbered "ARTICLE" headers instead of "Landlord"/
"Tenant" prose.

The third case failed on first run — and not narrowly. Tracing it
down found that `field_extractor.py`'s `_defined_term_pattern`, the
regex used to pull a party's name out of prose like
`Some Company, LLC ("Lessor")`, only ever matched the literal words
"Tenant"/"Landlord" there. A separate, unrelated pattern (for
label-style text like `Tenant: John Smith`) already recognized
"Lessee"/"Lessor"/"Renter" as synonyms — but that recognition never
extended to the defined-term pattern, which both single-lease
extraction and multi-lease boundary detection both depend on. The
practical effect: **any lease using "Lessor"/"Lessee" phrasing —
extremely common real-world terminology, not a rare edge case — would
silently extract neither tenant nor landlord at all**, in ordinary
single-lease use, not just in multi-lease documents. This was not
caught by the existing test suite because none of its fixtures used
that terminology in the defined-term style.

Fixed by changing `_defined_term_pattern` to accept a tuple of role
keywords and build an alternation (`Tenant|Lessee|Renter`,
`Landlord|Lessor`), and updating its three callers
(`_extract_defined_party`, `_find_all_party_occurrences`,
`_find_all_party_values`) and their six call sites across
`extract_fields()`, `detect_lease_boundaries()`, and
`detect_multiple_leases()` accordingly. Verified three ways before
considering it fixed: the new structural-variation tests directly
(3/3 pass), the full suite after registering the new file (23/23
files), and a live end-to-end upload through the running API — which
initially still showed `tenant: None, landlord: None` after the code
fix, until realizing the Flask dev server doesn't hot-reload and was
still running the pre-fix code in memory; restarting it produced the
correct `tenant: Cascade Outdoor Supply Co.`, `landlord: Highland
Estates Group`.

### Export accuracy: Excel and Google Sheets checked cell-by-cell, not spot-checked

Uploaded three leases with deliberately varied field coverage (one
fully-populated commercial lease, one minimal Lessor/Lessee lease with
many fields absent, one office lease with a different subset missing)
and compared every cell of `/portfolio/rent-roll.xlsx` and every value
`sheets_export._lease_row()` would write against each lease's own
`extracted_fields` response, field by field:

- Currency and count strings (`"$6,250.00"`, `"2,400 sq ft"`) retype
  correctly to plain numbers (`6250`, `2400`) in both exports, with no
  rounding drift — `Rent/SqFt` matches the exact division
  (`6250/2400 = 2.604166...`, `11250/4500 = 2.5`) in the Excel export,
  and the Sheets row-builder's independently-derived `Annual Rent`
  (`monthly * 12`) and `Rent per Square Foot` came out identical to
  hand-computed values for all three leases.
- Every field the extractor reported as not-found rendered as a true
  blank cell (`None` in the xlsx, `""` in the Sheets row) in both
  exports — never the literal text "None" or "Not Found" leaking into
  exported data.
- Row count and row order matched the upload order exactly in both
  exports (3 leases in, 3 rows out, correctly attributed).

No mismatches found. Google Sheets export itself still can't be
tested end-to-end without live Google credentials (unchanged from
Part 1/Part 2 — the route correctly returns a clean 502 with a setup
message when unconfigured, confirmed by existing tests), but the row
data it *would* send is proven identical to what the Excel export and
the app itself show, which was the actual accuracy question being
asked here.

## Admin login and dashboard — real authentication for the admin surface

Replaces the previously-unauthenticated `/admin/waitlist/` panel
(flagged repeatedly across earlier sessions as a real pre-sale
blocker: `GET /waitlist` and `POST /waitlist/<id>/approve` had zero
auth, confirmed live) with a real login page and session-authenticated
dashboard. Deliberately separate from the client-facing access gate
(`/waitlist/check`, self-reported email, no password — see "Access
gate uses self-reported email, not real auth" below) and from the
deferred multi-tenant client auth work; this is specifically the one
admin's login.

### Single admin account via env vars, not a users table

`ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` in `backend/.env`, checked
directly in `app/auth.py` — no new database table. There is exactly
one admin account for now; a table (with the migration, uniqueness
constraints, and query layer that implies) would be solving a problem
that doesn't exist yet. `ADMIN_PASSWORD_HASH` is a bcrypt hash, never
the real password — generated by a new one-off script
(`backend/set_admin_password.py`) that prompts with `getpass` (never
echoed, never in shell history) and prints the line to paste into
`.env`. The app never writes to `.env` itself.

### Timing-safe wrong-email vs. wrong-password check

The explicit requirement was that a failed login must not reveal
*which* credential was wrong. The response message already doesn't
(`"Invalid email or password"` either way), but `verify_admin_
credentials()` also always runs the bcrypt comparison — using the real
configured hash — even when the email is already known not to match,
so a wrong-email attempt takes essentially the same time as a
wrong-password one. Without this, an attacker could distinguish the
two cases by response latency alone (bcrypt is deliberately slow;
skipping it on email mismatch would make that path measurably faster).

### Flask's signed-cookie session, not a custom session store

`session['admin_authenticated']` via Flask's built-in session
(itsdangerous-signed cookie, `SESSION_COOKIE_HTTPONLY=True`, 12-hour
`permanent_session_lifetime`) rather than a server-side sessions table.
This is real, server-verified auth state — the cookie is
cryptographically signed and tamper-evident, checked server-side on
every request via `require_admin` — not a "the client says it's logged
in" pattern. `FLASK_SECRET_KEY` signs it; if unset, a random one is
generated per-process (logged as a warning) rather than falling back to
any hardcoded value — sessions just don't survive a restart until a
real, stable key is set.

### CORS with credentials: the real cross-origin cookie problem, solved the way production will need anyway

The frontend (its own port via `python3 -m http.server`) and the
backend API are different origins even in local dev — a plain
`CORS(app)` with no credentials support, and a `fetch()` without
`credentials: 'include'`, would both silently make cookie-based auth
impossible; the browser drops the `Set-Cookie` on the way in and
never sends it back out. Fixed with three matched pieces:
`CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS)`
(flask-cors requires an explicit origin list, not `*`, once credentials
are involved), `SESSION_COOKIE_SAMESITE='None'` +
`SESSION_COOKIE_SECURE=True` (a cross-site `fetch()` won't carry a
`Lax`/`Strict` cookie at all, credentials flag or not), and
`credentials: 'include'` on every admin-facing fetch call in
`login.js`/`dashboard.js`. `Secure` normally means HTTPS-only, but
Chrome/Firefox/Safari all treat `http://localhost` (and
`http://127.0.0.1`) as a secure context specifically for local
development, which is what makes this work over plain HTTP here — a
real deployment will need real HTTPS on both sides for the same
cookie to keep working, which is exactly the shape production needs
anyway, not a dev-only shortcut being deferred.

### What's now gated vs. still deliberately public

`GET /waitlist`, `POST /waitlist/<id>/approve`, and the new
`POST /waitlist/<id>/deny` all require `@require_admin`. `POST
/waitlist` (signup) and `POST /waitlist/check` (the client access
gate's approval lookup) remain public by design — signup has to be
reachable by anyone, and `/waitlist/check`'s narrow response shape
(`{approved, found}` for one email the caller already supplies) was
already a deliberate, separate decision, not an oversight, documented
in the comment block above these routes.

### Existing tests updated, not just left broken

Several pre-existing tests (`test_access_gate.py`,
`test_waitlist_email.py`) called the now-gated routes directly via
Flask's `test_client()` with no session — caught by simply running the
suite after adding `require_admin`, not assumed safe. Fixed by adding
a small `_login_as_admin(client)` helper that sets the session directly
via `session_transaction()` (the standard way to test a session-gated
Flask route without driving bcrypt through an actual login POST for
every test that needs one).

Verified live: full login → dashboard → approve/deny → logout → 401
lifecycle through headless Chrome (not just curl), confirming the
`SameSite=None; Secure` cookie actually round-trips in a real browser
against `http://localhost`, plus regression-checked that the client
app (`/app/`) and landing page waitlist form are both unaffected by
the CORS/session config change.

## Real email delivery: admin notification on new access requests

`email_service.py` already sent a confirmation email to whoever
submitted the "Request Access" form; nothing told the admin a request
had come in short of manually reopening the dashboard. Added
`send_admin_new_request_notification(requester_email)`, sent to
`ADMIN_EMAIL` (the same single admin account `auth.py` already reads
from env), wired into `POST /waitlist` right next to the existing
confirmation send.

Same best-effort posture as every other send in this module: wrapped
in `_send_email_best_effort` at the call site, and `_send()` itself
never raises — a signup must never fail because an email didn't go
out. Verified with a mocked-SMTP test that a signup fires exactly two
sends (confirmation + notification) to the two different recipients,
plus a test that the route still returns 201 even if the notification
call itself raises.

One thing the existing confirmation-email code didn't have to worry
about: the notification embeds the *requester's own* email address in
an HTML email body, and `/waitlist`'s validation
(`_EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"`) only checks it's
email-shaped — it doesn't forbid `<`/`>`/other HTML metacharacters in
the local part. Escaped the requester's address with `html.escape()`
before embedding it (the plain-text MIME part still uses it raw, which
is fine — there's no markup to inject there), with a test asserting a
`<img onerror=...>`-shaped "address" renders escaped in the parsed
HTML MIME part specifically, not just absent from the raw multipart
string (the raw string legitimately contains it once, unescaped, in
the plain-text part).

Confirmed live: real Gmail SMTP send to timmypisano24@gmail.com,
via a real (Google-generated) App Password, not mocked — both the
confirmation-email template and the new admin notification landed in
the inbox.

## Landing page top nav: closing a dead zone between breakpoints

Reported as "still not fixed" after an earlier pass. Measuring gaps via
`getBoundingClientRect()` on the live page showed the flex gap itself
was already a perfectly uniform 32px at every width tested ≥ 1024px —
the complaint wasn't the spacing value, it was a range of viewport
widths (roughly 900–1040px, confirmed by bisecting screenshot
renders at a real CDP-controlled browser width) where the nav neither
fit on one row next to the brand nor had yet hit the page's mobile
breakpoint. In that dead zone, flex items shrank and link text wrapped
*mid-phrase* — "Trust & Security" splitting across two lines — because
nothing prevented an individual `<a>` from breaking.

The nav outgrew its own breakpoint: the existing `@media (max-width:
860px)` comment said "5 links + Client Login" when fixing this; it's
actually 6 links + Client Login now, and that breakpoint was never
revisited as sections were added to the page over time.

Fix has two independent parts, deliberately not just one:
1. `white-space: nowrap` on `.landing-brand` and every
   `.landing-nav-links a` — no individual link (or the wordmark) can
   ever break mid-word, regardless of width.
2. Split `.landing-nav`/`.landing-nav-links`'s stacking rules out of
   the shared 860px media query into their own `@media (max-width:
   1040px)` block — 1040px gives margin above the ~935px measured
   minimum for a one-row fit, for different fonts/zoom levels, without
   moving unrelated sections (`.platform-groups`, `.pricing-grid`,
   `.steps-grid`) that still fit fine down to 860px and have no reason
   to stack earlier.

(1) alone would have just pushed the overflow into a horizontal
scrollbar or clipped content instead of a mid-word wrap; (2) alone
would still have let a sufficiently long link wrap mid-word in some
future dead zone. Together, every width either renders one clean row
or the existing centered/wrapped mobile stack — nothing in between.

Verified via a CDP-controlled real Chrome (not headless) across the
full range (880/900/940/1000/1039/1040/1041/1100/1280px): confirmed
with a hard reload (`Page.reload({ignoreCache: true})` + cache
disabled) after discovering a plain reload was serving a browser-cached
`landing.css` and silently masking the fix during the first pass of
verification.

## Incident: real email storm from the test suite, and the send-side rate limit

**What happened.** Real `EMAIL_USER`/`EMAIL_APP_PASSWORD` were configured
in `backend/.env` for the first time (to verify the new admin
notification email actually delivers). Shortly after, the full test
suite (`run_all_tests.py`) was run twice. Two pre-existing test files —
`test_access_gate.py` and `test_admin_auth.py` — call `POST /waitlist`
repeatedly with fixture emails (`secret1@example.com`,
`secret2@example.com`, `MixedCase@Example.com`, `notafit@example.com`,
`client@example.com`, etc.) through Flask's in-process `test_client()`,
and neither ever mocked `app.email_service`. That was always true and
always harmless, because this dev environment had never had real
credentials before — `email_service._send()`'s existing
"not configured" check made every call a silent no-op. The moment real
credentials existed, that same code path became a real Gmail send on
every one of those calls: the requester-confirmation email (to the
fake fixture address, which just bounces) and — the actually damaging
one — the admin notification added earlier this session, which always
targets the real `ADMIN_EMAIL`, regardless of which fixture triggered
it. Across two full suite runs plus prior individual runs of those two
files during earlier iteration, that's what put "thousands" of real
emails, with recognizably test-shaped subject lines/addresses, in the
real inbox.

**What it was not**: not a retry loop (`_send()` has no retry logic at
all — one failed attempt logs and returns `False`, once) and not a
duplicate-trigger bug (`join_waitlist` intentionally calls two
*different* send functions once each — confirmation to the requester,
notification to the admin — and `approve_waitlist` calls its one send
function exactly once). Confirmed by reading every call site, not
inferred. Also confirmed clean: none of the `LIVE_API_TESTS` (which hit
a real running backend over actual HTTP, where `run_all_tests.py`'s own
env-sanitizing can't help) reference `/waitlist` at all.

**The fix has two independent layers, deliberately:**

1. *Test-side (can't happen from this direction again)*: both
   `test_access_gate.py` and `test_admin_auth.py` now pop
   `EMAIL_USER`/`EMAIL_APP_PASSWORD` from `os.environ` immediately
   after importing `app.api` — after `load_dotenv()` has already run,
   so they can't be silently repopulated from `.env` — guaranteeing
   `_send()`'s existing fail-safe applies no matter what's configured
   locally. `run_all_tests.py` also strips both vars from the
   environment it passes to *every* subprocess, so a future test file
   that touches `/waitlist` without remembering to mock email fails
   safe by default rather than depending on that file's author getting
   it right. Three overlapping guarantees (two files defend themselves
   even run standalone; the runner defends every file including ones
   that don't yet exist) rather than one.

2. *Send-side (can't happen from any direction, including ones nobody
   thought of yet)*: `email_service._send()` now enforces a rate limit
   — no single recipient can receive more than
   `_RATE_LIMIT_MAX_PER_WINDOW` (10) emails from this module within
   `_RATE_LIMIT_WINDOW_SECONDS` (60), in-memory, per-recipient,
   independent of anything upstream. This is explicitly a backstop, not
   a prevention mechanism — the test-side fix above is what actually
   stops *this* incident from recurring; the rate limit exists so that
   a different future misfire (a new test file, a route bug, anything
   calling a `send_*` function repeatedly) hits a hard, small cap
   instead of an unbounded real-world blast radius. Logged at `error`
   level when tripped, since it should never happen in normal
   operation and is worth investigating if it does.

**Immediate incident response**, before any of the above was written:
`EMAIL_USER`/`EMAIL_APP_PASSWORD` were commented out in `backend/.env`
(blocks any new process from loading real credentials) and the exposed
Gmail App Password was revoked directly at Google's end by the human
operator (the only action that's instant regardless of what any
already-running process had cached in memory — editing the local `.env`
file can't touch a process that already loaded the old value at
startup). Email sending stayed intentionally disabled until this fix
was verified.

**Verified**: full suite 21/21 after the fix, including two new tests
(`test_send_side_rate_limit_caps_repeated_sends_to_same_recipient`,
`test_send_side_rate_limit_is_per_recipient`) proving the cap actually
blocks `smtplib` from being invoked past the limit and that different
recipients get independent quotas — plus re-confirmed `test_access_gate.py`
now logs "not configured"/"Email not sent" instead of attempting real
sends, with real credentials still present in the (disabled) `.env`.

### Addendum: a second, deeper audit before re-enabling credentials

Before turning credentials back on, re-audited every test file for this
class of gap from scratch (not from memory of the fix above) — and
found three more, all inside `test_waitlist_email.py` itself, the file
specifically about testing email safely:

- `test_duplicate_signup_does_not_resend_email` and
  `test_signup_succeeds_when_admin_notification_fails` each set a
  real-looking `fake_env` (to exercise the "credentials configured"
  code path) but only mocked ONE of the two functions
  `join_waitlist()` calls — the other ran for real against those fake
  credentials, reaching an actual `smtplib.SMTP_SSL` connection
  attempt (would fail Gmail auth, not deliver, but is exactly the
  "hits real SMTP" class of bug this audit was checking for).
- `test_approval_sends_email_and_still_succeeds_if_it_fails` made a
  bare `/waitlist` POST with no credential patching or mocking at all,
  relying entirely on whatever was ambient in the environment — safe
  only by accident of `run_all_tests.py`'s subprocess env-stripping,
  not by anything in the file itself. Run directly
  (`python3 test_waitlist_email.py`) with real credentials in `.env`,
  this line alone would have repeated the original incident.

Fixed by giving `test_waitlist_email.py` the same import-time
`os.environ.pop("EMAIL_USER"/"EMAIL_APP_PASSWORD")` guard the other two
files already had (protects any call that doesn't explicitly opt back
in), plus mocking the previously-uncovered function at each of the two
specific call sites above.

**Verification method, not just re-reading the code**: wrote a
throwaway script (scratchpad, not committed) that patches
`smtplib.SMTP_SSL` to a sentinel raising immediately if ever invoked
*outside* a test's own inner `mock.patch`, sets real-looking
`EMAIL_USER`/`EMAIL_APP_PASSWORD` as actual OS environment variables
before any import (simulating the worst case — this file run directly,
bypassing `run_all_tests.py`'s own protection entirely), then runs each
of the three email/waitlist-touching test files under that sentinel.
Zero unmocked calls detected in any of the three, across every test
function. Full suite re-confirmed 21/21 afterward.

## Rebrand: Lumen Lease → Abstractly

Straightforward mechanical rename, done exhaustively rather than
assumed complete: `grep -ril "lumen"` across the whole repo (not just
the obvious frontend files) found 7 files, 21 occurrences —
`frontend/index.html`, `frontend/pricing.html`,
`frontend/admin/index.html`, `frontend/admin/dashboard.html`,
`backend/set_admin_password.py`, `backend/app/email_service.py`
(display name, every email subject/body, including the HTML template's
brand line), `backend/app/summary_memo.py` (PDF footer text).
`DECISIONS.md`/`PROGRESS.md` and every README were checked too and
never referenced the name literally, so nothing there needed changing.
Re-ran the same repo-wide grep after all edits — zero remaining
matches, including case-insensitive and the `LumenLease` (no-space)
variant. Full test suite re-confirmed 21/21 after touching the two
backend files (email subject-line assertions in the test suite check
for text that didn't change, e.g. "We've received your request", so
none of the body-copy renames were at risk of breaking an assertion,
but re-ran anyway rather than assuming).

`frontend/admin/dashboard.html` was mid-edit by a concurrent session at
the time — coordinated rather than editing it directly; that session
made the same two replacements itself.

## Landing page: restoring it as the actual homepage

Investigated before assuming anything was actually broken: the report
was "going to the site only shows a login screen, no landing page."
Checked `frontend/index.html` directly (full hero/steps/platform/trust/
FAQ/footer content, byte-identical to the last known-good nav-spacing
fix, nothing missing), checked both static server processes actually
running (`:8000` and `:8080`, both serving the correct file from the
correct directory), and checked every frontend JS file for redirect
logic (`landing.js`, `config.js`, inline `<script>` tags) — none
exists. The landing page was never actually gone; most likely
explanation is a bookmarked/cached `/admin/` URL being mistaken for the
site root, not a code regression. Confirmed live via a CDP-controlled
real Chrome hard-reload: full page renders correctly at the root.

Real, deliberate change made as part of this: the nav's "Client Login"
link (previously pointing at `/app/`, the client-facing product's
lightweight self-reported-email access gate — not real auth) now
points at `/admin/` instead, per explicit user choice after being
asked directly — the original admin-login request had said to keep
admin login separate from any client-facing link, so this is a
deliberate reversal of that, not an oversight. Verified by clicking the
actual rendered link in a real browser and confirming it lands on the
(now also rebranded) admin login page. `pricing.html` has its own
duplicated nav markup (not shared via include/partial) and needed the
same link change independently — updated both.

Pricing page's tier structure (Starter $349/mo, Team $899/mo
"Most Popular", Business $2,499/mo, Concierge "Custom") was
double-checked against the file directly, not assumed intact from
memory of building it earlier this session — full feature lists, CTAs,
and card styling all confirmed present and unchanged.

## Login page: no session-based bypass of the credentials form, ever

Follow-up to the "already signed in, Continue?" panel added earlier
this session (see above) — the user's requirement tightened from
"don't silently redirect" to "never skip the form under any
condition, no exceptions." Removed `checkExistingSession()` from
`login.js` entirely, along with the `#adminAlreadySignedInPanel` /
`#adminGateChecking` markup in `index.html` — the login page no longer
checks `/admin/session` at all on load; it just renders the form,
unconditionally, every time.

Explicitly scoped this to the login *page* only, not session
persistence generally — confirmed directly with the user after a
concurrent session flagged the distinction: `dashboard.html`'s own
session check (in `admin-bootstrap.js`) is unchanged, so a valid
session still reaches the dashboard directly via a bookmarked URL
without re-entering credentials, for its normal 12h lifetime. Killing
that too was considered and explicitly declined — it would remove the
practical point of having sessions at all, and wasn't what "always
show the form" was asking for once the two were disambiguated.

**Verified live**, without ever touching the real admin password
(intentionally never known to me — see `set_admin_password.py`):

- Every rejection path exercised directly: an email never configured
  at all, the correct email with a wrong password (byte-identical
  generic error to the above — no field-level leak), and an empty/
  missing password, the last one confirmed both client-side (HTML5
  `reportValidity()` blocks submission) and server-side via a raw
  `curl` POST bypassing the browser entirely (401, same generic body).
- The login page shows the form immediately with no existing session,
  *and* — the actual point of this change — still shows the form when
  a currently-valid session exists, rather than skipping to the
  dashboard.
- Session-lifecycle behavior (direct dashboard access with a valid
  session, logout actually invalidating server-side per `/admin/session`
  going back to `authenticated: false`, dashboard access correctly
  bouncing to login post-logout) verified using a session cookie
  minted directly with the app's own `FLASK_SECRET_KEY` and session
  serializer (the same technique the test suite's `session_transaction()`
  helper uses) rather than a real login — this tests genuine
  post-authentication behavior without requiring the real password.
- The one thing that couldn't be verified this way — real credentials
  actually succeeding through the real form — was confirmed directly
  by the user themselves.

## Platform "Coming soon" features: building them out for real

User asked for all 5 remaining "Coming soon" Platform items built to
genuinely working, tested completion (not stubs), one at a time,
methodically. Two scope corrections made before starting (confirmed
with the user): MRI stays in scope for rent-roll import (the live copy
already promised it; the user's own written list had dropped it, by
omission not intent), and "feature 4" as the user described it
actually merges two separate existing roadmap items -- WALT/rollover
risk (a pure calculation) and cross-checking the rent roll against
lease documents (a validation feature) -- confirmed the user wants
both, built as two passes since the second one has a real dependency
(below).

Sequencing chosen (lowest-risk/most self-contained first, per the
user's own instruction to pick the order): tenant concentration →
WALT/rollover risk → loss-to-lease → broker Excel/CSV import → [PMS-
specific imports, blocked on real sample files] → rent-roll-vs-lease-
document cross-check → T12 cross-check. The lease-document cross-check
specifically can't come before rent-roll import: there is currently no
"rent roll" data source in this system independent of the lease PDFs
themselves (the only existing "rent roll" is *generated from* the
extracted leases, in rent_roll_export.py) -- nothing to cross-check
against until an externally-sourced rent roll (a PMS export or a
broker file) can actually be imported.

### Feature 1 of 5 (of 6 underlying items): Tenant concentration analysis

`compute_tenant_concentration()` in portfolio.py. Groups leases by
tenant (conservative name normalization -- case/punctuation/whitespace
only, reusing the exact matching philosophy `_normalize_address`
already established: a missed match is far cheaper than a false one,
since merging two genuinely different tenants would understate
concentration risk, the opposite of this check's purpose), sums rent
per tenant, and reports top-1/3/5 cumulative share plus the
Herfindahl-Hirschman Index -- the actual DOJ/FTC merger-guideline
concentration metric, not an invented threshold. `concentration_level`
("high"/"moderate"/"low") triggers off HHI *or* the single largest
tenant's share independently, since HHI alone can under-flag a
portfolio with one dominant tenant sitting among many small ones (a
concrete case built and verified: one tenant at exactly 25% plus 75
tenants at 1% each gives HHI=700, "low" by HHI alone, but is correctly
flagged "high" via the dominant-tenant threshold).

Edge cases designed for up front and covered by tests: empty
portfolio, no lease with both a tenant and a parseable rent, a lease
missing tenant name (excluded, never bucketed as a fake "Unknown"
tenant -- that would fabricate a mega-tenant that doesn't exist), a
chain tenant with several separate lease uploads (correctly merged
into one), two genuinely different but similarly-named tenants
("Acme Corp" vs "Acme Corp West" -- correctly NOT merged), and every
threshold boundary (exact HHI=2500/top-1=25% cases, verified
mathematically impossible to exceed HHI 2500 while keeping every
individual tenant under 25% -- confirmed with a small script before
writing that test, not assumed).

**Two real bugs found and fixed during the mandatory second read-
through** (re-reading the finished function fresh, looking for silent
failures): (1) a genuine $0 base rent (a real, if uncommon, lease
structure -- percentage-only retail deals) was being treated the same
as an unparseable rent and excluded outright, conflating "found and
it's zero" with "not found" -- exactly the distinction this codebase's
other portfolio math (compute_portfolio_metrics et al.) is built
around getting right; (2) fixing that exposed a real
`ZeroDivisionError` risk: a portfolio where every included lease
legitimately has $0 rent has total_rent == 0, and computing a
percentage of that would crash. Both fixed (zero rent included as a
real value; total_rent <= 0 now degrades to the same "not enough data"
shape as an empty portfolio) and both got dedicated regression tests,
not just a fix. A third, smaller precision bug was also caught this
pass: top_N_pct and HHI were being computed from each tenant's
*already-rounded* percentage rather than the raw rent/total fraction,
compounding rounding error across tenants -- confirmed with a real
messy-data run (top_5_pct was 95.70 before the fix, 95.69 after; the
raw-fraction math confirms 95.69 is actually correct).

**Verified against a deliberately messy combined scenario**, not just
clean unit fixtures: a 12-lease mock shopping center mixing a chain
tenant uploaded under three differently-cased/spaced names, a
similarly-named-but-genuinely-different competing entity, a bad-OCR
lease with no tenant name, a lease with a failed rent extraction, and
a genuine $0-rent lease -- every number in the output was hand-traced
and confirmed correct, not just "ran without crashing."

Exposed via `GET /portfolio/tenant-concentration`, tested end to end
through Flask's real test_client() (not just the underlying function)
including that it correctly reflects amendments (reads
`get_all_effective_leases()`, so a rent-increase amendment changes the
concentration numbers, not just the original base lease's figures).
Full suite 22/22 (new file: test_tenant_concentration_api.py).
Platform page copy updated from "Coming soon" to a checkmark with
copy describing what it actually computes.

### Feature 2 of 5 (of 6 underlying items): Rollover risk and WALT

`compute_walt()` and `compute_rollover_schedule()` in portfolio.py.
WALT is rent-weighted (not lease-count-weighted) remaining lease term
-- the standard industry convention, since WALT exists to answer "how
much of my revenue is locked in, for how long," not "how many leases
are left." The rollover schedule is the companion exhibit: what share
of total rent (and lease count) expires in each of the next 5 years
plus a "year_6_plus" catch-all, the standard "lease rollover schedule"
analysts build by hand -- deliberately a different shape than the
existing `compute_expiration_timeline` (which buckets by month,
per-lease, for "what needs attention soon"), not a duplicate of it.

Both share the same inclusion rule: a lease needs a parseable end date
AND a parseable, positive rent to count, and an already-expired lease
(negative days remaining) is excluded from the "remaining term"/
forward-looking math entirely -- same precedent `compute_portfolio_
health` already established. A lease expiring exactly today counts at
0 years remaining (a real data point pulling the average down), not
excluded like a truly expired one.

**A real design bug found and fixed before ever running the code**
(caught while re-tracing the draft, not by a test failing): the
rollover schedule's `lease_count` denominator initially included
already-expired leases while `total_rent` didn't, so the two
percentage bases weren't parallel -- fixed by scoping both to the
forward-looking (bucketed) leases only, with `already_expired` reported
as raw counts with no percentage of its own (there's no single
obviously-correct denominator for one). A second, more consequential
gap: a portfolio where every analyzable lease has ALREADY expired was
originally going to collapse into the same "not enough data" null
result as an empty portfolio -- but that's actually the single worst
possible rollover picture (100% already rolled over) and is real,
important data, not an absence of it. Fixed to return real zero-filled
buckets, the real already-expired count, and `rollover_risk_level`
forced to "high" in that case, rather than silently discarding the
finding.

`rollover_risk_level`'s thresholds (year_1 share of rent >=25% "high",
>=15% "moderate") are an explicitly stated rule of thumb, not an
external standard the way HHI is for tenant concentration -- documented
as such in the docstring and the constants' own comment, same honesty
posture as the pricing page's "recommended, not market-tested" framing.

**Verified against a deliberately messy combined portfolio**: a
dominant anchor tenant expiring in 60 days (real near-term
concentration risk), several ordinary leases laddered across multiple
future years, a bad-OCR lease with no end date, a lease with a failed
rent extraction, and a holdover tenant 45 days past their lease end.
Every number in both WALT and the rollover schedule was hand-computed
and confirmed exact, including that the holdover tenant correctly
stayed out of the forward-looking percentages entirely (kept in
`already_expired`) rather than diluting or inflating year_1.

Exposed via a single combined `GET /portfolio/rollover` endpoint
(`{walt, rollover_schedule}`) -- computes `reference_date` once in the
route and passes the same value to both functions, so the two numbers
shown together can never disagree about what "today" means. Tested
end to end through Flask's real test_client(), including that both
sub-results agree with each other and both correctly reflect lease
amendments (an amendment extending a lease's end date moves it to a
different rollover bucket and changes WALT, not just the base lease's
original figure). Full suite 23/23 (new file: test_rollover_api.py).
Platform copy updated from "Coming soon" to a checkmark.

### Feature 3 of 5 (of 6 underlying items): Loss-to-lease analysis

Asked the user directly before building anything: "loss to lease" is
defined as the gap to *market* rent, and this system has no market-rent
data source at all (no comps feed, no survey integration) -- leases
only say what a tenant actually pays, never what space could rent for
today. Building a version against invented market numbers would be
fabricating data, which the user's own instructions for this whole
batch of work explicitly said to stop and ask about rather than do.
User chose a portfolio-internal proxy: `compute_loss_to_lease()`
compares each lease's rent/sqft against the highest rent/sqft already
achieved by another lease in the SAME BUILDING, as an honest,
clearly-labeled stand-in for market rate -- not real market data, and
documented as such everywhere (docstring, API route comment, and the
Platform page copy itself). A property with only one lease on file has
no internal comp and is honestly excluded, not compared against
unrelated space elsewhere in the portfolio -- this system has no
property-type field, so a portfolio-wide comp would risk comparing a
downtown office suite against a suburban retail kiosk.

Deliberately does NOT attach a "high/moderate/low" risk label the way
tenant concentration (HHI, an external standard) and rollover risk (a
stated rule of thumb) do -- an internal-proxy "market rate" has neither
kind of grounding, and a risk label would lend it more authority than
it honestly has. Reports raw numbers (loss %, and a dollar figure --
monthly_upside -- since a small percentage gap on a huge unit can
matter more than a large percentage gap on a tiny one) and lets the
reader judge.

**A real, meaningful bug found via the required messy-data test, not
caught by the clean unit tests at all**: initially reused
`_normalize_address` (the exact-unit-matching function
`compute_cross_lease_mismatches` uses, designed to catch the SAME unit
disagreeing with itself across two uploads) to group leases by
property. That function keeps the suite number as part of the match
key on purpose -- correct for its own job, wrong for this one. Every
one of this feature's own unit tests happened to use identical address
strings with no suite variation, so they all passed 100% despite the
bug; it only surfaced when testing against a realistic multi-suite
building ("400 Main St, Suite 100/200/300"), where all three units came
back as three separate, comp-less single-lease "properties" instead of
one 3-unit building -- which would have made the feature nearly useless
for the single most common real case it exists to handle. Fixed by
adding a second, purpose-built `_normalize_building_address()` that
strips a recognized suite/unit designator before matching, used only
here -- `_normalize_address` and cross-lease mismatch detection are
completely untouched. Added a dedicated regression test for the exact
scenario (different suites, same building, must group; genuinely
different buildings with similar-looking addresses, must not).

**Verified against messy combined data** after the fix: a 3-suite
building with mixed case/spacing in the address, a single-lease
property with no comp, a lease with no address extracted, and a lease
with a failed square-footage extraction. Hand-traced every number
(including the exclusion-count invariant: leases counted +
leases excluded == leases in) and confirmed exact.

Exposed via `GET /portfolio/loss-to-lease`. Full suite 24/24 (new
file: test_loss_to_lease_api.py, including an end-to-end DB round-trip
confirming the same-building/different-suite grouping fix works
through the real route, not just the unit-level function). Platform
copy updated from "Coming soon" to a checkmark, explicit that this is
an internal comp, not external market data.

### Feature 4 of 5 (of 6 underlying items): Rent roll import (broker Excel/CSV)

Session was paused mid-feature and resumed the next day (see the git/
chat history around this entry for the exact split) -- picking back up
started by re-reading the in-progress checkpoint that used to be here,
not just the code, which is exactly why that checkpoint was written in
that much detail. Kept the parsing-module writeup from that checkpoint
below since it's still accurate; everything after "Resumed and
finished:" is what closed the feature out.

**The parsing engine** (`backend/app/rent_roll_import.py`): reads CSV
and .xlsx files with NO fixed format assumed (matches column headers
against alias lists, e.g. "Tenant"/"Lessee"/"Occupant" all map to the
same field), converts rows into the exact same `extracted_fields`
shape the PDF extractor produces (so every existing portfolio
computation -- tenant concentration, WALT, rollover, loss-to-lease --
works on imported rows with zero special-casing), and skips vacant/
total/subtotal/blank rows rather than importing them as fake tenants.
Source citations for imported fields use a new shape -- `{row, file,
quote}` instead of the PDF extractor's `{page, quote}`, since there's
no PDF page for a spreadsheet cell.

`backend/tests/test_rent_roll_import.py` -- 16 tests. Covers header-
naming diversity, currency with/without "$", real openpyxl numeric/
date cell types (not just strings), vacant/total/blank row skipping,
missing optional columns, and two real bugs found and fixed via
adversarial testing (not by the clean happy-path tests, which all
passed even with these bugs present):
1. A naive CSV-writing test helper split "$4,500.00" into two fields
   because it didn't quote commas -- caught immediately, and confirms
   properly-quoted CSV (what real Excel exports produce) round-trips
   correctly through `csv.reader`.
2. A real header-matching bug: "Rent Commencement"/"Rent Expiration"
   (standard commercial lease terms, distinct from "Lease
   Commencement" -- rent can start later than the lease itself during
   a free-rent period) were getting matched to `rent_amount` via its
   bare "rent" alias before `lease_start_date`'s more specific aliases
   ever got a chance, purely because of dict iteration order. Fixed by
   rewriting the matcher to prefer the LONGEST/most-specific alias
   match across all fields simultaneously rather than "first field
   declared wins," plus adding "rent commencement"/"rent expiration"
   as real, intentional aliases for the date fields (not just a bug
   workaround -- this is actually correct real-estate terminology).

**Resumed and finished:**
- `POST /leases/import-rent-roll` -- multipart file + optional
  `property_address` (most rent rolls state the building once, not per
  row; combined with a per-row Unit/Suite column, if present, into
  each row's full address -- this is also what makes loss-to-lease's
  same-building comp grouping work correctly for imported data). A
  file-level problem (wrong extension, empty, no recognizable columns)
  is a 400, nothing partially imported; a single bad data row is never
  fatal to the rest of the file. `backend/tests/
  test_rent_roll_import_api.py` -- 7 tests through the real Flask
  route, including confirming an imported lease immediately feeds
  `/portfolio/tenant-concentration` correctly (the actual point of
  matching the PDF extractor's field shape, verified end to end, not
  just asserted).
- `frontend/app/detail-view.js` AND `frontend/admin/admin-detail-view.js`
  (the peer session's duplicated copy, found and fixed after flagging
  it to them) -- the source-citation renderer only knew `{page, quote}`
  and would have shown "Page undefined" for an imported field. Added a
  branch keyed on `'row' in fieldData.source`.
- A real upload UI: a second section on the existing Upload Leases
  page (`frontend/app/index.html`/`upload-view.js`/`api.js`) --
  property-address input, drag-drop-or-click .csv/.xlsx picker, and a
  results panel listing every imported lease plus every skipped row
  with its reason (not just a count -- a user needs to see WHY a row
  they expected isn't there). Deliberately a separate flow from the
  PDF Upload object, not unified with it: genuinely different
  semantics (one file → one lease vs. one file → many; an address
  input that only applies here; a different accepted file type).
- Full suite (backend): 26/26 test files passing.

**Verified live, through the real browser, not just curl/pytest**: a
deliberately messy combined CSV (mixed currency formatting with and
without "$", a "Rent Commencement"/"Rent Expiration" header pair
specifically re-testing yesterday's bug fix, a vacant row, a totals
row, and a Unit column) uploaded through the actual running app at
`localhost:8000/app/`. Confirmed: 3 real tenants imported, 2 rows
correctly skipped with the right reasons shown in the UI, suite
numbers correctly combined into full addresses, and -- opening one
imported lease's real detail page -- every field showing a correct
"ROW N OF MESSY_RENT_ROLL.CSV" citation with the actual quoted cell
value, AND risk_analysis.py running automatically on the imported
lease with zero modification (correctly flagged missing insurance/
security-deposit/escalation clauses), which is the concrete proof the
"same shape as a PDF-extracted lease" design goal actually holds, not
just an architectural intention. All test data cleaned up afterward
via the real DELETE route.

Platform copy split into two lines: broker Excel/CSV import is now a
checkmark; the named PMS systems (Yardi/AppFolio/RealPage/MRI/
Buildium) remain "Coming soon" as their own line, since those still
need real sample export files -- see below, unchanged from before.

**Still fully untouched, per the original plan**: PMS-specific
importers (blocked pending real sample export files from the user),
and the T12 cross-check (likely needs a real sample T12, not yet asked
about).

### Feature 5 of 5 (of 6 underlying items): Cross-check rent roll against lease documents

`compute_rent_roll_reconciliation()` in portfolio.py. The design
problem worth recording: both a rent roll row and a PDF-extracted lease
land in the exact same `leases` table with no dedicated "where did this
come from" column, so telling them apart couldn't rely on a schema
field. Solved with the uploaded filename's extension (.csv/.xlsx vs.
everything else) -- the only way a non-PDF file enters this table is
through the rent roll import route, so this is a reliable signal
without a migration.

"Same unit" is exact address match (`_normalize_address`, suite
included -- deliberately the same-UNIT matcher `compute_cross_lease_
mismatches` already uses, NOT `_normalize_building_address`'s same-
BUILDING matcher loss-to-lease uses, since this is about one unit's two
records disagreeing with each other). Compares three fields, each with
its own honest tolerance: tenant name (any disagreement at all --
there's no "close enough" for whether it's the same tenant), rent
amount (flagged only past BOTH a percentage AND an absolute-dollar
tolerance together -- either alone either over-triggers on rounding
noise at one unit-size extreme or under-triggers at the other; verified
with two dedicated tests, a $2 gap on a $100/mo kiosk correctly NOT
flagged despite clearing 1%, a real gap on a $60k/mo anchor correctly
still flagged), and lease end date (any disagreement -- a rent roll
showing the pre-renewal expiration while the lease was actually
extended is exactly the stale-data problem this exists to catch).
Deliberately excludes square footage and lease start date from the
comparison -- neither is a meaningful "went stale" signal the way rent/
tenant/end-date are (a start date is a fixed historical fact; square
footage rarely changes), a deliberate scope choice, not an oversight.

Also deliberately does NOT attach a severity/risk-level classification
the other three features in this batch do -- tenant and date mismatches
are binary (either they agree or they don't, no gradient to classify),
and a rent mismatch already had to clear a real tolerance bar before
being flagged at all, so everything that IS flagged is already
"significant enough."

A rent roll row with no matching lease PDF -- the common case, since a
rent roll typically covers far more units than have an uploaded lease
PDF -- is simply not compared against anything, not an error. An empty
`mismatches` list with real (non-zero) counts is itself a real, positive
result ("reconciliation happened, everything agreed"), deliberately
distinguished from an all-zero-counts result ("nothing to reconcile
yet, most likely because no rent roll has ever been imported") --
this function does NOT use the rest of this module's "None means not
enough data" convention, since an empty mismatch list here is genuinely
good news, not an unknown.

**Verified against a realistic combined portfolio**, not just clean
unit fixtures: 5 rent roll rows and 4 lease PDFs across a small
building, covering both of the realistic scenarios this feature exists
for (a real renewal where the PM system's rent AND expiration date both
went stale, and a tenant turnover the PM system never picked up), a
trivial 3-cent rounding gap correctly not flagged, and one rent roll
row with no lease PDF on file yet correctly excluded rather than
compared against something unrelated. Every mismatch (and every
non-mismatch) hand-traced and confirmed exact.

Exposed via `GET /portfolio/rent-roll-reconciliation`, tested end to
end through Flask's real test_client() against a REAL rent roll import
(through the real import route, not a fixture) compared against a real
inserted "lease PDF" record, including that an amendment on the lease-
document side is correctly reflected (reads `get_all_effective_leases()`,
same as every other function in this batch). Full suite 27/27 (new
file: test_rent_roll_reconciliation_api.py). Consistent with the other
three pure-computation features in this batch (tenant concentration,
WALT/rollover, loss-to-lease), this shipped as an API endpoint only --
no new dedicated dashboard UI widget, matching the bar already set by
those three rather than treating this one differently. Platform copy
updated from "Coming soon" to a checkmark.

### Dashboard UI for the 4 new portfolio metrics — closing the "API-only" gap

**Status: done.** All four of the above features shipped as API-only
endpoints, on the stated reasoning that they'd match the existing
precedent set by `compute_rent_variance_outliers` (also API-only, no
dashboard widget). Revisited that call after all five features were
live: it left the dashboard with genuinely no surface for any of this
new analysis — a user would have to know these endpoints exist and hit
them directly to ever see tenant concentration, WALT/rollover, loss-to-
lease, or reconciliation results. That gap is worth closing on its own,
not something the original "match existing precedent" reasoning
actually justified once four of these existed side by side.

Added one new dashboard panel, "Portfolio Composition & Risk," placed
after the existing "Expiring Soon" panel: `frontend/app/index.html`
(`#compositionPanel` with four `.attention-group` sub-sections),
`frontend/app/api.js` (thin wrappers for the four GET endpoints, already
present from each feature's own API work), and `frontend/app/
dashboard-view.js` (four independent `.then()/.catch()` loads in
`Dashboard.load()` plus one render function per metric). Each render
function handles its own empty state ("not enough data yet," "no rent
roll imported yet") distinctly from its populated state, rather than
one shared generic empty-state message — the four metrics have
genuinely different reasons to be empty (too few tenants/leases vs. no
rent roll ever imported), and a shared message would be honest about
"nothing here" but not about *why*.

**Two real bugs found while building this, neither hypothetical:**

1. **CSS class mismatch.** `_riskBadgeHtml` initially invented a
   `.badge`/`.badge-severity-X` pattern that doesn't exist anywhere in
   `styles.css`. Caught by checking the actual stylesheet before
   shipping rather than trusting the name felt plausible; fixed to
   reuse the real, already-established `.severity-badge` +
   `.severity-high/medium/low` classes the rest of the app already
   uses for this exact purpose.

2. **Dynamically-injected link had no click handler.** `renderReconciliation`'s
   empty state injects `<a href="#" data-goto="upload">import one</a>`
   via `innerHTML`. `app.js`'s `init()` only wires up `[data-goto]`
   click handlers once, at page load, against elements present in the
   DOM at that time — an element injected later by a render function
   never gets one. The link rendered correctly but silently did nothing
   when clicked. Fixed by giving it a unique id and manually attaching
   `addEventListener('click', ...)` right after injecting it, calling
   `showView('upload')` directly instead of relying on the global
   `data-goto` wiring.

**Found a third, more consequential bug during live verification of
this same panel** — not in the dashboard code itself, but surfaced by
it. Testing the reconciliation panel end-to-end required an imported
rent roll row that genuinely disagreed with a lease PDF for the same
unit; the panel showed zero compared pairs even though the planted
mismatch should have matched. Root cause was in `rent_roll_import.py`,
not the dashboard: `parse_rent_roll_rows` built each row's
`property_address` as `f"{base_property_address}, Suite {unit_str}"`
unconditionally — but a rent roll's Unit/Suite column routinely already
contains the designator itself (a cell literally reading "Suite 101",
not bare "101"), producing "500 Commerce Blvd, Suite Suite 101". That
string doesn't match the same unit's lease-PDF address ("500 Commerce
Blvd, Suite 101") under `_normalize_address`'s exact-unit matching, so
`compute_rent_roll_reconciliation` silently never paired the two
records — no error, just zero results, exactly the kind of silent
failure this whole batch's process was designed to catch. Fixed with a
new `_UNIT_DESIGNATOR_RE` check in `rent_roll_import.py`: only prepend
"Suite " when the cell is a bare identifier; if it already starts with
Suite/Ste/Unit/Apt/#, use it as-is. Regression test added
(`test_unit_column_already_spelled_out_does_not_double_prefix`,
covering "Suite 101", "Ste. 101", "Unit 5", "Apt 2B", "#12", and a bare
"101" control case). Full suite re-run: 28/28.

**Live-verified in a real browser** (headless Chrome via CDP, dedicated
instance on a scratch profile so as not to disturb peer sessions' own
browser state), against a realistic 5-lease portfolio built specifically
to exercise every panel's populated state at once (a dominant anchor
tenant for concentration, a near-term expiration for rollover, a
3-suite building for loss-to-lease, and a deliberately-planted $150
rent gap between a rent-roll row and its matching lease PDF for
reconciliation) plus, separately, the reconciliation panel's empty
state with the same portfolio minus its rent-roll row — confirming both
that the empty-state copy renders correctly and that its "import one"
link (bug #2 above) actually navigates to the Upload view when clicked,
not just that it looks clickable. All test data (leases and the
temporary waitlist-approval bypass used to pass the /app access gate
for verification) removed/reverted afterward; nothing durable was left
behind from the verification pass itself.

No backend route or computation logic changed by this work (aside from
the rent_roll_import.py fix above, which is a real bug fix, not part of
"dashboard UI"); full backend suite 28/28 both before and after.

### Addendum: the live-browser verification above didn't actually re-verify the fix it thought it did

Caught during the "re-check your own work a second time" pass, on the
same trip through this feature that shipped it — not a later session.
The browser verification above is genuine and its findings stand (the
reconciliation matching, the dashboard rendering, the empty-state link
click-through all really were confirmed live). What it did NOT do,
despite implying otherwise: re-verify the `_UNIT_DESIGNATOR_RE` fix
itself against the live server. The CSV used for that browser pass
gave its Unit column a bare "101", not an already-designated "Suite
101" -- the bare case takes the same code path and produces the same
correct output under *both* the buggy and fixed versions of the
function, so passing it proves nothing about which version was
actually running. This was the same mistake in miniature as the fix
itself was catching in the app: an input that happens not to exercise
the bug looks identical to a real fix.

Worse, independently of that: the live dev backend had, at that exact
point, been restarted (by an unrelated action -- most likely in
response to this session's own earlier heads-up about the missing
reconciliation route) *before* the `_UNIT_DESIGNATOR_RE` fix was
written to disk, and was never restarted again afterward. So the
running server was serving pre-fix code the entire time the "browser
verification" screenshots above were taken -- undetectable from those
screenshots alone, precisely because the test data used couldn't have
told the difference either way.

Found and closed by building `test_live_composition_api.py` -- a new
automated live-HTTP regression suite for all five endpoints in this
feature batch (tenant-concentration, rollover, loss-to-lease,
reconciliation, import-rent-roll), following the exact convention
already established by `test_live_portfolio_api.py` and
`test_live_dashboard_api.py`: run against the actually-running dev
server over real HTTP, not Flask's `test_client()` (which re-imports
the app fresh every run and so can never catch "the code is right but
the running process is stale" -- exactly the class of bug this was).
Its scenario deliberately DOES use already-designated unit values
("Suite 100", "Suite 200") specifically so it discriminates between
the fixed and unfixed function, unlike the earlier browser pass. First
run against the live server failed exactly as expected, showing
"Suite Suite 100" / "Suite Suite 200" -- confirming the server really
was stale. Backend restarted a second time; re-run confirmed the fix is
now genuinely live (31/31). Two unrelated bugs in the test file itself
were also found and fixed along the way (asserting `status == 200`
against a route that actually, correctly, returns `201` on create; and
an ordering bug where the file's own PDF-fixture upload -- added for
the reconciliation check -- was placed before the tenant-concentration/
rollover/loss-to-lease checks and so polluted their expected totals,
not a backend bug at all). Full suite including live tests: 33/33.

Registered in `run_all_tests.py`'s `LIVE_API_TESTS` list so this
exact class of regression gets caught automatically on every future
`--live` run, rather than depending on a human happening to test the
exact right input by hand again.

## PMS-specific rent roll import: Yardi and AppFolio (Platform feature, using synthetic fixtures)

**Status: done, pending real vendor files.** The last two originally-
blocked Platform items (PMS-specific import; T12 cross-check) genuinely
needed either real sample files from the user or an explicit decision
to build against fabricated ones -- per this whole batch's own rule
("if a feature needs something from me... stop and ask rather than
guessing or faking it"), this was asked, and the user explicitly chose
to have realistic synthetic fixtures generated instead of waiting on
real files, to be swapped in later. This entry covers the PMS import
half; T12 is a separate entry below.

**Design.** The existing generic broker-CSV/Excel importer
(`rent_roll_import.py`, already shipped) assumes row 1 is the header
row and covers one property per import. Neither assumption holds for a
real PMS canned report: Yardi Voyager and AppFolio rent roll exports
both routinely open with several decorative rows (property name,
report title, an "As Of" date) before the real column-header row, use
their own terminology ("Resident" for tenant, "Lease From"/"Lease To",
"Unit SF", "Scheduled Rent"/"Rent Charge" for actual rent vs. "Market
Rent" for the theoretical achievable rate), and a portfolio-wide export
can cover several DIFFERENT properties in one file via a per-row
Property/Community column, not just one building via a single
uploader-typed address.

Three additions, all inside the same existing module (no new file --
this is the same importer gaining PMS awareness, not a separate PMS-
specific code path):

1. **Header-row auto-detection** (`_find_header_row`): scans the first
   20 rows for the first one where BOTH a tenant and a rent column are
   recognizable, treats everything before it as decorative. Requiring
   BOTH (not just one) is what keeps a title row like "Rent Roll
   Report" -- which contains the word "Rent" but has no tenant column
   -- from being mistaken for the real header. Falls back to today's
   existing "no recognizable columns" error if nothing in the scan
   window qualifies, rather than silently misinterpreting a data row as
   a header.
2. **Per-row Property column** overrides the uploader's single
   `base_property_address` for that row specifically, falling back to
   it only when a row's own cell is blank -- makes a portfolio-wide,
   multi-property export group correctly by each unit's REAL building
   for downstream loss-to-lease/T12 comp grouping, instead of every row
   being incorrectly flattened into whichever address the uploader
   happened to type.
3. **PMS terminology aliases**, plus one deliberate exclusion and one
   deliberate denylist:
   - Added: "Resident" (tenant), "Unit SF" (square footage), "Scheduled
     Rent"/"Rent Charge" (rent_amount), "Lease From"/"Lease To" (dates).
   - Deliberately NOT added: "Move-in"/"Move-out" -- these are
     occupancy dates (when a tenant physically took/vacated possession),
     a different real-world fact from the lease's own contractual
     start/end. Conflating them would be wrong in either direction (a
     tenant can move in days after lease start; a lease can renew past
     an original move-in date).
   - Denylisted: any rent-like header containing "market"/"potential"/
     "asking"/"projected"/"proforma" alongside "rent" is NEVER matched
     to rent_amount, even with no better rent column present in the
     file. Market rent is a theoretical, vacancy-inclusive achievable
     rate, not what a tenant is actually, contractually paying --
     silently using it as if it were actual rent would corrupt every
     downstream computation that reads rent_amount, systematically in
     one direction. The honest behavior is to treat the file as if it
     has no recognizable rent column at all.

**A real accuracy bug, found and fixed during self-review, not in
production**: the new bare "property" alias (needed for AppFolio's own
common bare "Property" header) would also match "Property Manager" --
a real, common column holding the on-site PM's PERSON'S NAME, not a
building address -- via pass 2's whole-word substring matching.
Fixed with the same denylist pattern already used for market rent
("manager"/"management"/"type"/"tax"/"id"/"code" alongside "property"
is never eligible), rather than removing the bare "property" alias
(which would have broken the common, legitimate bare-"Property" case
this whole addition exists for). Regression test added.

**A precision bug, found while building the header-detection feature
itself**: with header auto-detection in play, a decorative block
containing a genuinely blank spacer row (a very common real pattern --
title, blank, subtitle, blank, real header) was silently shifting every
later row's `source.row` citation off by one, because blank rows get
dropped before parsing and the old citation math assumed a fixed
row-1-is-header offset. Fixed by tracking each surviving row's TRUE
original file line number end to end (both CSV and xlsx readers),
rather than reconstructing it from position + an offset. Directly
serves the project's own quality bar ("every extracted field must show
its source... so a human can verify it") -- a citation pointing at the
wrong row is a real trust failure, not a cosmetic one.

**Synthetic fixtures** (clearly labeled as such in each file's own
first row, `backend/tests/synthetic_yardi_rent_roll.csv`/`.xlsx` and
`synthetic_appfolio_rent_roll.csv`): built to match the real, publicly-
documented structure of each platform's standard rent roll report as
closely as reasonably possible -- decorative header block, PMS
terminology, a Market-Rent-alongside-actual-rent column, a VACANT unit
row, a trailing Total row, and (AppFolio) a genuine multi-property
export with no single base address supplied at all, relying purely on
the Property column. Verified end to end against all three: correct
header detection, correct rent column chosen over market rent, correct
per-row addresses (including a "Unit 12" cell that already spells out
its own designator, confirming the earlier double-"Suite" fix also
holds for real PMS-shaped unit values), correct VACANT/Total skipping,
and downstream `/portfolio/tenant-concentration` correctly consuming
the combined imported data with zero special-casing -- run against the
REAL live server (not just Flask's `test_client()`), restarting it
first to make sure of it this time (see the addendum immediately
above).

**Tests**: 6 new unit tests for header-detection specifically, 6 for
property-column/aliases/denylists, 4 fixture-driven tests (including
one that round-trips both fixtures through the real
`POST /leases/import-rent-roll` route via `test_client()`) in a new
`test_pms_synthetic_fixtures.py`. Full suite: 34/34.

Platform copy updated: Yardi/AppFolio import moved from "Coming soon"
to a checkmark, with the copy explicitly disclosing it's validated
against synthetic fixtures, not yet a real customer file from either
platform. RealPage/MRI/Buildium remain "Coming soon" -- not specifically
tested, and per this batch's own standing rule, not something to guess
at. Two other places on the landing page overclaiming all five PMS
platforms as already-live were also corrected for accuracy while making
this change (a hero step-card and a FAQ answer), independent of this
specific feature's own Platform-section bullet.

## Rent-roll-vs-T12 cross-check (Platform feature, using a synthetic fixture)

**Status: done, pending a real vendor file.** The last originally-
blocked Platform item, unblocked the same way as the PMS import feature
above -- the user was asked, and explicitly chose to have a realistic
synthetic T12 fixture generated instead of waiting for a real one, to
be swapped in later.

**Design.** "Cross-checks the rent roll against the T12" is a due-
diligence question, not a full financial-statement feature: does what
the rent roll claims a property collects match what its trailing-12
operating statement says it actually collected. Deliberately scoped to
extracting and comparing exactly ONE number -- actual annual rental
income -- not building a general T12/P&L ingestion pipeline (vacancy
loss, expense categories by CAM/tax/insurance, NOI). Nobody asked for a
full operating-statement parser; the Platform feature asked for a
specific cross-check, and that's what got built.

**New document type, new module** (`t12_import.py`), since a T12's
shape is fundamentally different from a rent roll's: one row per
TENANT with fields-as-columns (rent roll) vs. one row per LINE ITEM
with months (and often a Total/Annual column) as columns (T12). Reuses
the rent roll importer's proven patterns where they genuinely transfer
-- decorative-header-row auto-detection (a T12 export routinely opens
with a property name/title/date-range block too), tolerant bare-number
currency parsing, true-row-number citation tracking (built correctly
from the start here, having already found and fixed that exact bug in
the rent roll importer earlier in this same session -- see that
entry's addendum) -- and introduces what's genuinely new: label-based
row matching (instead of header-based column matching) to find the
actual-rental-income line, and a Total-column-or-sum-of-12-months
fallback for computing each row's annual figure.

**The one design decision that actually matters here**: a T12 routinely
has BOTH a "Gross Potential Rent" line (the theoretical, vacancy-
inclusive maximum at 100% occupancy) and an actual "Rental Income"/
"Rent Revenue" line (what was really collected). Only the latter is the
correct comparison -- using gross potential would make a perfectly
healthy, fully-consistent property look "short" by definition, since
potential exceeds actual by construction (that's what vacancy loss
means). A denylist (`_POTENTIAL_INCOME_WORDS`) excludes any rent/income
label containing "potential"/"market"/"proforma"/"projected"/"asking",
mirroring the exact same principle (and near-identical implementation)
as rent_roll_import.py's "Market Rent" denylist from earlier in this
batch. "Gross Rental Income" is deliberately NOT excluded -- "Gross"
there contrasts with "Net" (before vs. after operating expenses), not
"Actual" vs. "Potential," standard operating-statement terminology, a
real accounting distinction this implementation has to get right rather
than pattern-match on the word "Gross" alone.

**A real logic bug, caught by the test suite before shipping, not in
production**: "scheduled" was denylisted (T12s commonly use "Scheduled
Gross Income" for the potential/asking figure), but "Scheduled Rent
Income" was ALSO meant to be an explicit, unambiguous allow-listed
alias for ACTUAL income (documented in a code comment) -- except the
denylist check ran unconditionally before the allow-list check was ever
reached, so the documented exception was never actually implemented.
`test_scheduled_gross_income_excluded_but_scheduled_rent_income_allowed`
failed on first run, exactly as it should have. Fixed by checking for
an EXACT allow-listed alias match first, which now correctly overrides
the denylist -- only a non-exact, substring-based match is subject to
it. A genuine example of why "write the test, run it, don't assume it
passes" matters even when the code and its own comment both look
internally consistent at a glance.

**Reconciliation** (`compute_t12_reconciliation` in portfolio.py):
building-level comparison (via `_normalize_building_address`, same
convention as `compute_loss_to_lease` and for the same reason -- a T12
covers a whole property, not one unit), summing every matching lease's
rent regardless of source (PDF or imported rent roll) and annualizing
it, then comparing against the T12's actual income with a NEW dual-
tolerance pair (5% AND $3,000/year) recalibrated for this comparison's
much larger scale (annual, building-wide dollars, not one lease's
monthly rent) -- reusing `compute_rent_roll_reconciliation`'s exact
$5/1% constants here would have either over-triggered on ordinary
timing noise for a large property or under-triggered for a small one.
Reports `direction` (`rent_roll_higher`/`t12_higher`/`agree`) rather
than just a flag, since which side is bigger changes how a human should
read the result (understating collected income vs. overstating it are
different stories) -- deliberately does NOT guess at WHY a real gap
exists, same restraint already established by the rent-roll-vs-lease-
document reconciliation feature.

**Not persisted anywhere, unlike a rent roll import**: a T12 doesn't
represent a lease or tenant. `POST /portfolio/t12-reconciliation`
parses the uploaded file and compares it against the CURRENT rent roll
in the same request; nothing about the T12 survives past that one
response. Inserting it into the `leases` table the way rent roll import
does would corrupt tenant concentration, WALT, and every other per-
lease computation with a fake non-lease row -- confirmed with a
dedicated test (`test_t12_route_does_not_persist_anything`) and live,
by checking `GET /leases` before and after a real upload.

**Synthetic fixture** (`synthetic_t12_operating_statement.csv`, clearly
labeled as fabricated in its own first row): deliberately built for the
SAME property as the earlier Yardi rent roll fixture (Riverside Commons
Shopping Center), so this exercises the real end-to-end story -- import
a rent roll through one real route, upload a T12 through another, get a
genuine cross-check back -- not two unrelated fixtures tested in
isolation. Its actual rental income ($187,900) sits a small, realistic
4.5% above the rent roll's own annualized total ($179,400, the same 3
real tenants from the Yardi fixture) -- close enough to correctly NOT
be flagged, proving the tolerance logic on believable numbers rather
than a hand-picked clean example, plus a separate large-gap variant
confirming the flagged path too. Verified against the REAL running
server (restarted first to make sure of it, per the lesson from
earlier in this session): real rent roll import, real T12 upload, real
cross-check, real cleanup, real confirmation nothing was persisted.

**Tests**: 12 unit tests for the T12 parser (including the "scheduled"
bug above), 11 for `compute_t12_reconciliation` (agreement, both
discrepancy directions, both tolerance-bar-alone-not-enough cases,
building-vs-unit-level grouping, missing-data honesty), 7 for the
Flask route, 3 fixture-driven tests, and a new permanent live-HTTP
regression file (`test_live_t12_api.py`, following the exact convention
established by `test_live_composition_api.py` earlier this session --
runs against the actually-running server, not `test_client()`, so a
future "code is right but nobody restarted the server" regression gets
caught automatically). Full suite: 38/38.

Platform copy updated: T12 cross-check moves from "Coming soon" to a
checkmark, explicitly disclosing synthetic-fixture validation, not yet
a real customer T12. The FAQ answer describing this as something being
"built toward" was also corrected now that it's real.

Not built (explicitly out of scope, not an oversight): a UI panel for
uploading a T12 from the dashboard. This ships API-only, consistent
with how tenant concentration, rollover, and loss-to-lease also shipped
API-only first before a dedicated dashboard panel was added as a
separate, later piece of work (see "Dashboard UI for the 4 new
portfolio metrics" above) -- a natural next step if wanted, not
required by "cross-checks the rent roll against the T12" as stated.

## PMS-specific rent roll import: RealPage, MRI, and Buildium (Platform feature, using synthetic fixtures)

**Status: done, pending real vendor files.** Closes out PMS import
support for all five platforms named in the original Platform feature
list. Same as Yardi/AppFolio and the T12 cross-check before it:
unblocked by the user explicitly choosing synthetic fixtures over
waiting for real vendor files, clearly labeled as such.

**Design.** The generic machinery built for Yardi/AppFolio (header-row
auto-detection, per-row Property column, market-rent denylist) is
platform-agnostic by construction -- it works on ANY canned PMS report
shape, not something Yardi/AppFolio-specific. The real question for
these three platforms was narrower: does their own terminology need
new aliases, and does building realistic fixtures for them surface any
NEW risk the first two platforms' fixtures happened not to exercise.
Both turned out to be true.

**New aliases**: "Actual Rent"/"Charged Rent" (RealPage's own terms for
actual vs. "Market Rent," same distinction Yardi's "Rent Charge"
already covers -- added to the same allow-list, not a new mechanism).
A bare "Commence" (no "date"/"lease" suffix) -- found during research,
not by symptom: MRI-style exports commonly use single-word "Commence"/
"Expire" column headers, and the EXISTING longer aliases ("commence
date", "lease commencement") can only match a header that CONTAINS the
full alias phrase -- a header that's just "Commence" is shorter than
that phrase and can never contain it, so it silently wouldn't have
matched at all. Fixed by adding a bare "commence" alias alongside the
existing phrases (which still win when both are present, via the
existing longest-alias-first ordering). "Occupant" (MRI's term for
tenant) turned out to already be covered from the original Yardi/
AppFolio pass.

**A second real, more serious bug, also caught during self-review
before shipping**: "Rent PSF" (rent per square foot) is a genuinely
common column on RealPage/MRI-style commercial rent rolls -- a RATE
(e.g. "2.75" meaning $2.75/sqft/month), not the tenant's total dollar
rent. With no better rent column present, the bare "rent" alias
(already existing, not new) would silently match "Rent PSF" and treat
that per-square-foot figure as if it were the tenant's entire monthly
rent -- wrong by roughly the unit's whole square footage, and silently
so. This was a PRE-EXISTING risk in the original rent-roll importer
(the bare "rent" alias already existed before this work), not
something the new RealPage/MRI aliases introduced -- but building
fixtures for exactly the platforms where PSF columns are most common
is what surfaced it. Fixed with the same denylist pattern already used
for "Market Rent" and "Property Manager": any rent-like header
containing "psf" is never eligible for rent_amount, exact match or
not. Regression test added; confirmed a file with BOTH a PSF rate
column and a real dollar column still correctly uses the real one.

**Synthetic fixtures** (clearly labeled, `synthetic_realpage_rent_
roll.csv`, `synthetic_mri_rent_roll.csv`, `synthetic_buildium_rent_
roll.csv`): RealPage and MRI built as single-property exports with a
decorative header block, a VACANT unit, and a trailing Total row (same
messy-data shape as the Yardi fixture); RealPage specifically pairs
Market Rent alongside Actual Rent to exercise that denylist with this
platform's own terminology. Buildium built as a genuine multi-property
export (a realistic pattern for Buildium, commonly used by owners of
several small scattered properties) using simpler, plainer terminology
-- exercises the per-row Property column mechanism with a second,
independent real-world case beyond the AppFolio fixture.

**Verified against the real running server**, not just `test_client()`
-- restarted first, per the standing lesson from earlier in this
session: all three fixtures imported via real HTTP, confirmed correct
rent/address values (Actual Rent over Market Rent, bare Commence/
Expire parsed, multi-property Buildium correctly split by building),
confirmed `/portfolio/tenant-concentration` correctly consumes the
combined 9-tenant portfolio with zero special-casing, and separately
re-verified the PSF fix live after the code changed (a fresh restart,
confirmed a PSF-only file is honestly rejected on the actual running
server, not just proven in a local test run).

**Tests**: 2 new unit tests for the terminology aliases and the PSF
bug, 3 new fixture-driven tests (one per platform) plus the shared
round-trip-through-the-real-route test extended to cover all 5
platforms now. Full suite: 38/38 (test count grew within existing
files; no new test files needed here, unlike the Yardi/AppFolio and T12
work, since this extends already-established test infrastructure
rather than introducing a new capability).

Platform copy updated: the two separate Yardi/AppFolio and RealPage/
MRI/Buildium bullets merged into one checkmarked bullet covering all
five platforms, plus the hero step-card and FAQ answer (both previously
corrected to say "on our roadmap" for these three) updated to reflect
they're live now too.

## T12 dashboard UI panel

**Status: done.** Closes the "ships API-only for now" gap noted when
the T12 cross-check itself shipped -- a real UI surface for
`POST /portfolio/t12-reconciliation`, following user request to build
it alongside RealPage/MRI/Buildium import.

**Design.** Unlike the earlier "Portfolio Composition & Risk" dashboard
panel (four GET endpoints, computed automatically from whatever's
already in the database on page load), the T12 cross-check is
fundamentally request-response: it needs a freshly uploaded FILE each
time, and nothing about it is stored to passively display later. That
rules out a dashboard panel in the same sense as the other four --
there's no standing state to show on load. Placed instead as a new
section on the Upload view, directly parallel to the existing "Import
Rent Roll" section (same upload-box/property-address-field layout,
same visual language), but with a fundamentally different result
display: rent roll import shows a *list* of newly created lease
records; T12 cross-check shows a single structured comparison result
inline, since nothing was created.

Reused, not invented, existing UI patterns throughout -- consistent
with the lesson already learned earlier this session (the
`_riskBadgeHtml` CSS-class mistake): the result's three key figures
(rent roll annualized, T12 actual income, difference) reuse the
`.health-strip`/`.health-metric` classes already built for the
dashboard's top metric row, and the agree/flagged status reuses the
same `.severity-badge`/`.severity-high`/`.severity-low` classes the
risk panel and the composition dashboard already use -- no new CSS
needed at all.

**Four states handled explicitly**, each verified live in a real
browser (headless Chrome via CDP, on a dedicated scratch profile):
1. **Client-side validation** -- property_address is required (a T12
   covers exactly one property; the backend also enforces this, but
   failing fast client-side with a clear toast is better than a round
   trip just to learn the same thing).
2. **No matching leases** -- an honest message distinct from a real
   comparison, showing the T12's own real number (so the check wasn't
   wasted) alongside a clear reason nothing could be compared and what
   to do about it (upload a rent roll/leases for that address first, or
   check the address matches exactly).
3. **Agreement** ("Matches" badge) -- verified against the same
   Riverside Commons Shopping Center scenario the backend's own live
   test uses (real rent roll import through the real route, then a real
   T12 upload through the UI), confirming the exact same $179,400 /
   $187,900 / 4.52% figures render correctly end to end from a real
   browser interaction, not just an API response.
4. **Flagged discrepancy** ("Discrepancy Flagged" badge, red) -- a
   deliberately large gap (27.5%), confirming the visual distinction
   between the two states is real, not just a label difference.

**Verified nothing was persisted** by the UI flow specifically (not
just the API in isolation, already covered by `test_t12_route_does_
not_persist_anything`): checked `GET /leases` before and after
interacting with the actual upload form in the browser.

No new automated test file for the frontend itself (this codebase has
no browser-based JS test runner; frontend correctness is established
the same way it has been all session -- live CDP verification with
screenshots, following the exact process used for the earlier
composition dashboard panel). `node --check` confirms no syntax errors
in the modified files. Backend test suite unaffected by this change:
38/38, confirmed unchanged.
