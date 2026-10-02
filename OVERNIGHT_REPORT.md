# Overnight Report — `feature/loan-underwriting`

All 6 phases requested are complete, committed, and pushed. `main` was
never touched. No users/teams/auth schema was created or modified.

**Read this first, before anything else below:** "What you should review
first."

---

## What you should review first

1. **`main` has moved since this branch was last synced — `feature/usage-limits`
   (the real `teams` table) and `fix/rent-roll-hardening` (the real Maple
   Ridge fixture package) are both merged into `main` now.** I found this
   at the very end of tonight's work, after Phase 6 was already done. I
   deliberately **did not** merge `main` into this branch to get the real
   fixture, because doing so would pull in `database.py` changes that add
   the teams schema into the same file I've edited — exactly the "don't
   touch users/teams/auth tables" boundary you set for tonight. That's a
   judgment call for you, not one I'll make unprompted this late in an
   autonomous run. If you want it: merge `main` into this branch, resolve
   the `database.py` conflict by keeping both sides' additions side by
   side (my `loan_requests`/`t12_snapshots` migration is independent of
   their `teams` migration — see `app/database.py`'s
   `_migrate_loan_underwriting_tables` docstring for exactly where a
   `team_id` column would attach once you're ready for that), then
   re-run `tests/test_loan_underwriting_demo_deal.py` against the real
   `maple_ridge_t12.xlsx` instead of my CSV reconstruction.
2. **`demo_output/Maple_Ridge_Credit_Memo.docx`** — open this first. It's
   the real, final output of this whole branch: a complete credit memo
   with every number traced to its source, generated through the live
   API (not a test shortcut). See `demo_output/README.md` for exactly how
   it was produced and what to know about its provenance.
3. **The headline finding the demo deal produces:** the requested
   $13,875,000 loan exceeds the $12,979,387.71 maximum by $895,612.29 —
   DSCR binds below the 1.25x target. The memo states this in bold in
   Section 1. That's the module doing its job.
4. **This module has no team isolation**, by your own instruction mid-session
   (see "Decisions made" below). `SUMMARY.md` → "Where team isolation
   plugs in" names exactly what to add once you decide to wire it up
   against the now-merged usage-limits teams model.

---

## Phase-by-phase summary

### Phase 1 — Full suite green
Confirmed clean before touching anything further, and re-confirmed after
every subsequent phase. **Final state: 69/70 suite files pass.** The one
failure, `test_document_extractor.py`, is pre-existing (needs local
`tesseract`, fails identically on `main`) — not something this branch
caused or could fix.

### Phase 2 — Three fictional deals, hand-calculated, including negative NOI
`backend/tests/test_loan_underwriting_three_deals.py` (4 tests):
- **Sunset Gardens** (healthy deal) — LTV binds, requested loan oversized
  by exactly $125,000.
- **Oakmont Terrace** (interest-only, tighter margins) — LTV and DSCR
  land within ~$83K of each other.
- **Distressed Pointe** (negative-NOI edge case) — NOI of **-$87,775**,
  DSCR **-0.36x**, debt yield **-2.93%**, breakeven **120.70%** (above
  100%, itself a finding), maximum loan correctly floored at **$0** by
  both the DSCR and debt-yield constraints while LTV alone would still
  suggest $2.85M is available — exactly the scenario that shows why a
  lender needs all three tests, not one.

Every expected value was independently computed via the standard
annuity formula (shown in each test's docstring) and cross-checked
against the engine; all four pass.

### Phase 3 — Sensitivity grid + stress tests
Stress tests already existed from the prior session; added
`build_dscr_sensitivity_grid()` to `app/loan_underwriting.py` — a full
matrix (5 interest-rate rows x 4 occupancy-level columns by default,
both configurable) showing DSCR's interaction between rate and
occupancy, which the five independent stress cases can't show. Wired
into `underwrite()`'s result as `sensitivity_grid`.
`backend/tests/test_sensitivity_grid.py` (10 tests): shape, monotonicity
in both axes, the zero-vacancy column matched by hand, a rate-floor
guard (never tests a negative rate), the negative-NOI edge case, and
that the grid's own base cell agrees with the top-level DSCR from the
same `underwrite()` call.

### Phase 4 — Professional Word memo
`app/credit_memo_export.py`: an Executive Summary cover table before
Section 1 (property, headline ratios, binding constraint, and the
requested-vs-maximum shortfall/headroom, bolded in red when it's a
shortfall); one consistent navy heading style and one consistent
shaded-header-row table style throughout (`_style_heading`/`_add_table`);
numeric columns right-align like a ledger; the sensitivity grid from
Phase 3 now renders in Section 6 with below-1.00x cells marked. The
template file (`credit_memo_template.py`) stayed untouched — the new
`sensitivity_grid_table` block is just one more name in its existing
list, so a swapped-in lender template still only needs to touch that
one file. 5 new tests in `test_credit_memo.py` (cover table ordering,
consistent header shading, the grid rendering with its marker).

### Phase 5 — UI, behind the flag, matching app style
`frontend/app/loan-underwriting-view.js` (new) + `index.html` (new nav
item + view section) + `api.js` (8 new `Api.*` functions) + `app.js`
(`applyFeatureFlags()`) + `access-gate.js` (script registration) +
`styles.css` (new `.loan-uw-*` classes, reusing `.panel`/`.data-table`/
`.health-strip` rather than inventing parallel ones).

**The flag actually hides the nav item**, not just the routes: `GET
/config` now also returns `loan_underwriting_enabled` (same pattern as
the existing `local_dev_mode` flag), and the sidebar item starts
`display:none` in the HTML, only shown by JS once `/config` confirms the
flag is on. A tester on a deployment where the backend flag is off sees
no trace of this feature anywhere in the UI, not just a 404 if they
guessed a URL.

**Verified with headless Playwright** (installed via `npx playwright
install chromium` for tonight, not a permanent repo dependency): logged
in, created a loan request, uploaded a T-12, viewed the full results
(every figure matched the hand-verified numbers), downloaded... — see
the bug below, found and fixed via this same verification.

**A real bug found and fixed:** the sidebar briefly (~120ms) mis-sized
on the detail panel's very first render, then self-corrected. Isolated
through systematic instrumentation — frame-by-frame width tracing,
A/B testing against existing views (clean), isolated simulation of
every individual render step (all clean) — which proved it only
reproduces under real async/network timing, never in a synchronous
simulation, and is specific to this view (not a generic "first
navigation" quirk). Root cause: this is the first view in the app to
combine a CSS Grid with `auto-fit` columns *and* receive real
network-timed content while the shared `.view.active` fade-in transform
is still running. Fixed with `contain: layout` on the two grid
containers (`.loan-uw-detail-grid`, `.loan-uw-form-grid`) — confirmed
fixed via a live frame-trace that now stays flat at 248px throughout,
where it previously swept from ~449px down to 248px over ~120ms.
This bug would never have surfaced without the real browser
verification you asked for; it doesn't show up in Python-side testing
at all.

Also fixed a small cosmetic issue found in the same pass: the LTV ratio
row was showing the raw API field name (`purchase_price`) instead of a
human label (`purchase price`).

### Phase 6 — End-to-end on Maple Ridge, saved to the worktree
`demo_output/` (committed): the generated `.docx` memo, the full JSON
API response behind it, the T-12 CSV used, and a README explaining
exactly how each was produced and the T-12's provenance (a verified
reconstruction of the real workbook's figures, since the real fixture
package wasn't on this branch at the time — see "What you should review
first" above, since that's now changed).

---

## Decisions made (logged as I went)

1. **Your mid-session instruction** ("Do not touch users, teams, or auth
   tables") was the single governing constraint for everything tonight.
   This branch creates exactly two tables (`loan_requests`,
   `t12_snapshots`), both with **no** tenancy column, by design — see
   `app/database.py`'s `_migrate_loan_underwriting_tables` docstring and
   `SUMMARY.md`'s "Where team isolation plugs in" for exactly where that
   attaches later.
2. **Cleaned up incidental fixture regeneration noise** from earlier in
   the session (four binary test fixtures that got regenerated with
   fresh timestamps when I re-ran a generator script) before committing,
   to keep this branch's diff focused on the loan underwriting feature
   only.
3. **Fixed a stale `CLAUDE.md` sentence** left over from before your
   "don't touch teams" instruction — it still said this branch "plans its
   own" teams table. Corrected to reflect what actually shipped.
4. **Installed Playwright + Chromium locally** (via `npm`/`npx`, not
   added to the repo) specifically to fulfil "verify with headless
   Playwright screenshots and look at them." Not a permanent dependency;
   nothing in the repo references it.
5. **Ran a real local test backend** (temp SQLite DB, a seeded test
   admin account, the feature flag on, regex extraction engine so no
   real lease-extraction AI calls fired) on port 5001 to drive the
   Playwright verification and the Phase 6 API calls — never touched the
   real dev ports or any real data.
6. **One real Anthropic API call was attempted** (not by my choice to
   force it — it's what the credit-memo route does whenever
   `ANTHROPIC_API_KEY` is present in the environment) during the Phase 6
   memo generation. It failed immediately (`BadRequestError` — this
   account's key has no credit, already documented elsewhere in this
   project's history) and cost nothing. The module's graceful-degradation
   path handled it exactly as designed: the memo still rendered complete
   with every number intact, plus a visible note that the narrative
   wasn't generated. I did not retry it. All automated tests mock the
   Anthropic client; this was the one live attempt, inherent to actually
   running the real route end-to-end as Phase 6 asked, and it's now done
   — no need to run it again.
7. **Did not merge `main` into this branch** at the very end despite
   discovering the real demo fixture is now available there — see "What
   you should review first," item 1.
8. Where I had genuine autonomy (exact field layouts, button labels,
   default stress-test/sensitivity-grid ranges, CSS class names), I
   matched the existing app's conventions as closely as possible rather
   than inventing new patterns — e.g. the view's list/detail shape
   mirrors `deal-mismatch-view.js` almost exactly, and every new CSS
   class reuses `.panel`/`.data-table`/`.health-strip` rather than
   duplicating them.

## What's broken

**Nothing, as far as I found.** The one suite failure
(`test_document_extractor.py`, needs local `tesseract`) is pre-existing
and unrelated, confirmed identical on `main`. The one real bug found
during tonight's work (the sidebar flicker) was fixed and verified
fixed before moving on.

## What's NOT done (explicitly out of scope, not overlooked)

- Team isolation on the new tables (your instruction; documented where
  it plugs in).
- Merging `main`'s now-available real Maple Ridge fixture package or its
  teams model into this branch (see item 1 above).
- A real, successful AI-generated narrative in the credit memo (this
  account's Anthropic key has no credit — a pre-existing, documented
  constraint on this whole project, not something introduced tonight).

## Test counts, for reference

| File | Tests |
|---|---|
| `test_loan_underwriting.py` | 48 |
| `test_loan_underwriting_three_deals.py` | 4 |
| `test_sensitivity_grid.py` | 10 |
| `test_loan_request_api.py` | 22 |
| `test_credit_memo.py` | 29 |
| `test_loan_underwriting_demo_deal.py` | 4 |
| **Total** | **117** |

All registered in `tests/run_all_tests.py`. Every Anthropic call in the
automated suite is mocked (see item 6 above for the one live exception,
outside the test suite, in Phase 6 only).

## Commits on this branch tonight

```
cc34184  Phase 6: end-to-end run on the Maple Ridge demo deal
cdf96e8  Add Loan Underwriting UI, behind the feature flag, matching app style
e3e7bc5  Polish credit memo Word export to a professional bank memo
2e6bbff  Add loan request persistence, credit memo, API routes, and DSCR sensitivity grid
```

All pushed to `origin/feature/loan-underwriting`. **Not merged, as instructed.**
