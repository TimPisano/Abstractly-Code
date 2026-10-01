# Plan: Loan underwriting module for multifamily lenders

Replaces the previous contents of this file (the merged marketing-site
redesign plan — recoverable at `git show a794f0e:PLAN.md`).

New module, feature-flagged **off** by default so current testers see
nothing change. Branch: `feature/loan-underwriting`.

---

## What I read first, and the four things that actually constrain this

I read `deal_mismatch.py`, `investment_memo.py`, `t12_import.py`,
`portfolio.py`'s `compute_t12_reconciliation`, `auth.py`,
`database.py`'s schema, `cre_qa.py`, `test_route_authorization.py`, and
the demo deal package. Four findings change what's buildable, and I'd
rather state them up front than discover them halfway in.

### 1. There is no team isolation in this codebase at all

No `teams` table. **Zero** occurrences of `team_id` in `backend/app/`.
`leases` has no owner/account column; `users` has no team column. Every
logged-in user on a deployment sees every lease. This is deliberate, not
an oversight (the previous `PLAN.md` raised it as an open question and
`DECISIONS.md` treats single-tenancy as the current model).

`test_teams_and_assignments.py` is about team *members* and task
assignment, not tenancy — it does not imply isolation exists.

**Decision (confirmed with you):** this module introduces a real
`teams` table and a `team_id` on its own new tables, and enforces team
scoping plus roles on **every route it adds**. Existing lease /
rent-roll / memo routes are untouched and remain unscoped.

I'll say this plainly in `SUMMARY.md` and in the module docstring: the
application as a whole still has **no** per-team data isolation. This
module's isolation covers loan requests, assumptions and T-12
snapshots only. That is not a product-level "your data is isolated per
team" claim and must not become a homepage trust pillar on the strength
of this branch.

### 2. `t12_import.py` extracts exactly one number, and nothing is persisted

By explicit design (its own docstring): it pulls *only* actual collected
annual rental income, and "deliberately does NOT attempt to parse the
rest of a full operating statement (vacancy loss, expense categories,
NOI)". Worse for us, `compute_t12_reconciliation`'s docstring states a
T-12 "is NOT persisted anywhere... nothing about the T12 itself
survives past this one response."

You asked for underwritten NOI built from **verified T-12 collections**,
with **every input number linked to its source document and page**. Both
are impossible against a single unpersisted number — NOI needs the whole
expense stack, and a saved loan request needs its inputs to still exist
when the memo is regenerated tomorrow.

**Decision (mine, stated rather than asked):** extend T-12 parsing to
read the full line-item stack, and persist a snapshot per deal. I am
**not** rewriting the existing narrow function — `parse_t12_rows` stays
byte-identical because `compute_t12_reconciliation` depends on it. I'm
*adding* `parse_t12_line_items()` + `build_t12_financials()` alongside
it, reusing the same `_match_t12_columns` / `_row_annual_total` /
`_find_t12_header_row` helpers so there's still exactly one place that
understands T-12 file shape.

The demo T-12 confirms the data is there: Gross Potential Rent
$2,177,280, vacancy loss −$107,685.39, bad debt −$122,562, total other
income $86,340.27, total OpEx $766,762.83, NOI $1,229,888.08.

### 3. "Per deal" has no entity — it's an address string

The app scopes a building by `_normalize_building_address(...)`
(`compute_t12_reconciliation`, `compute_loss_to_lease`,
`investment_memo._scoped_leases` all do this). **Decision (confirmed):**
key loan requests by normalized property address. No new `deals` table.

### 4. Provenance on a spreadsheet has no page number

`t12_import` already returns `{"row", "file", "quote"}` — a row, not a
page, because a T-12 is CSV/XLSX. Lease PDF fields return
`{"page", "quote"}` (`field_extractor.py`). So "links to its source
document and page" resolves to: **page for PDF-derived numbers, sheet
row for spreadsheet-derived ones, and `None` for user assumptions** —
never a fabricated page number. Your wording already allows this
("where one exists"); I'm being precise about which inputs have what.

---

## Feature flag

`LOAN_UNDERWRITING_ENABLED`, read via `os.environ.get(...)` with the
same truthy-parsing convention `api.py` already uses for
`LOCAL_DEV_MODE` / `LEASE_ASYNC_EXTRACTION`. **Default off.**

When off, every route returns **404** (not 403) — same reasoning
`require_owner()` already documents: a 403 would advertise that a
hidden feature exists. Tests cover both states explicitly.

The flag gates routes only. The engine module is importable and
unit-testable regardless, which is what lets the formula tests run
without touching Flask.

---

## Files

| File | Purpose |
|---|---|
| `app/loan_underwriting.py` | **Pure-Python engine. No AI, no DB, no Flask.** Every formula. |
| `app/loan_request.py` | Persistence + team/role scoping for loan requests and assumptions. |
| `app/t12_import.py` | *Extended* (additive only): full line-item parse + canonical financial map. |
| `app/credit_memo_template.py` | **The swappable template, alone in its own file** (requirement 4). Section order, headings, which sections are AI-narrated vs engine-only. |
| `app/credit_memo.py` | Assembles engine output + AI narrative into the template. |
| `app/credit_memo_export.py` | Word (.docx) renderer via `python-docx` (already a dependency, 1.2.0). |
| `app/database.py` | *Extended*: `teams`, `team_members`, `loan_requests`, `t12_snapshots`. |
| `app/api.py` | Routes, all flag-gated + `@require_role` + team-scoped. |

Tests: `tests/test_loan_underwriting.py` (formulas, hand-calculated),
`tests/test_loan_request_api.py` (routes, flag, roles, isolation),
`tests/test_credit_memo.py` (template + mocked AI + docx),
`tests/test_loan_underwriting_demo_deal.py` (end-to-end on Maple Ridge).

---

## The engine (`loan_underwriting.py`)

Plain functions over plain dicts, mirroring `deal_mismatch.py`'s "pure
function, no I/O" shape. **No AI touches any number.**

### Underwritten NOI build-up

Standard lender stack. T-12 figures are the verified base; the three
assumptions you named override specific lines:

```
  Gross Potential Rent                 (T-12, verified)
− Vacancy                              (ASSUMPTION % × GPR)
− Concessions                          (T-12)
− Bad debt / collection loss           (T-12)
= Effective Rental Income
+ Other income                         (T-12)
= Effective Gross Income (EGI)
− Operating expenses                   (T-12, management fee REMOVED)
− Management fee                       (ASSUMPTION % × EGI)
− Replacement reserves                 (ASSUMPTION $/unit × units)
= Underwritten NOI
```

Two correctness details worth calling out:

- **The T-12's own management fee is stripped out of OpEx** before the
  assumption fee is added. The demo T-12 carries a real "Management Fee
  (3% of Total Income)" line at $59,899.54; leaving it in while also
  applying the assumption double-counts it. This is the single easiest
  way to get an underwritten NOI quietly wrong, so it's explicit and has
  its own test.
- **Replacement reserves are an underwriting add, not a T-12 line.** The
  demo T-12 has no reserves line at all (normal). So underwritten NOI is
  *structurally* below the T-12's historical NOI even at identical
  vacancy — that's expected, not a bug, and the memo shows both numbers
  side by side so the gap is visible rather than confusing.

Historical T-12 NOI is reported alongside, unmodified, as the
"historical" half of the memo's financials section.

### Debt service

`n = amortization_years × 12`, `i = annual_rate / 12`.

- Amortizing monthly payment: `L × i / (1 − (1+i)^−n)`
- **Zero-rate guard:** when `i == 0`, that formula divides by zero —
  payment is `L / n`. Tested.
- Interest-only monthly payment: `L × i`
- `annual_debt_service_interest_only` = `L × annual_rate`
- `annual_debt_service_amortizing` = `12 × amortizing payment`
- `annual_debt_service_year_one` = blended: `io_months_in_year_1 ×
  io_payment + (12 − io_months_in_year_1) × amortizing payment`

**DSCR is reported on the amortizing payment as the primary figure**,
because that's what sizes a loan — an IO-period DSCR flatters the deal
and expires. Year-one and IO DSCRs are reported too, labelled. All
three, not one, so nobody has to guess which convention was used.

### Ratios

- **DSCR** = underwritten NOI ÷ annual debt service
- **LTV** = loan ÷ value basis, where **value basis = the lesser of
  purchase price and appraised value** when both are given. That's
  standard conservative acquisition practice; the result reports which
  figure bound it and the LTV against each separately, so the choice is
  visible rather than buried.
- **Debt yield** = underwritten NOI ÷ loan amount
- **Breakeven occupancy** = (total underwritten operating expenses +
  annual debt service) ÷ (GPR + other income). Reserves are included in
  the numerator and that's documented on the function — conventions
  differ between lenders, so the choice is stated, not assumed.

### Maximum loan by constraint

- **By DSCR:** supportable annual debt service = NOI ÷ target DSCR, then
  divided by the annual payment factor per dollar of loan
  (`12 × i / (1 − (1+i)^−n)`, or `annual_rate` if sizing interest-only,
  or `12/n` at zero rate).
- **By LTV:** value basis × max LTV
- **By debt yield:** NOI ÷ min debt yield
- **Binding constraint** = the minimum of the three, reported by name
  with all three values shown.

Target DSCR, max LTV and min debt yield are all configurable, with
documented multifamily defaults (1.25×, 75%, 8%).

**Negative or zero NOI:** max loan by DSCR and by debt yield are
`0.0` — a property with no net income supports no debt — never a
negative or absurd loan amount. DSCR and debt yield themselves are
returned as the real negative numbers (they're meaningful signals), not
clamped. Each has a test.

### Stress tests

All five you asked for: rate **+100bp**, rate **+200bp**, occupancy
**−5pt**, occupancy **−10pt**, NOI **−10%**. Each recomputes the full
ratio set and the binding constraint. Rate stresses re-derive debt
service; occupancy stresses re-derive NOI through the vacancy
assumption; the NOI stress scales the final NOI.

---

## Assumptions: visible and editable

Every assumption is a row with `{key, label, value, unit, source,
is_default, edited_by_user_id, edited_at}`. The engine takes an
assumptions dict and returns, alongside the results, the exact
assumption set used — so a stored result can never disagree with the
inputs that produced it. Every T-12-derived input carries its
`{file, row, quote}` (or `{page, quote}` for lease-derived), and
user-entered assumptions carry `source: None` rather than a faked
citation.

---

## Credit memo

Template lives alone in `credit_memo_template.py` so a specific
lender's format can replace that one file. Standard bank structure, in
order:

1. Loan summary + **recommendation placeholder**
2. Property
3. Sponsor **placeholder**
4. Rent roll and lease analysis
5. Historical and underwritten financials
6. Ratios and stress tests
7. Risks and mitigants
8. Conditions

**AI writes narrative prose only** — sections 2, 4, 7, 8's discussion.
Every number is injected from the engine, never generated. The AI call
follows `cre_qa.py`'s pattern exactly, including the injectable
`client: Optional[anthropic.Anthropic] = None` parameter, which is what
makes it mockable in tests. Mocked in **all** tests; no test hits the
real API. (Relevant: the `ANTHROPIC_API_KEY` on this project has no
credit, so the module must degrade gracefully to placeholder narrative
text when the call fails — the numbers still render.)

**The recommendation is never decided by the tool.** Section 1 emits an
explicit "For credit officer determination — this tool does not
recommend approval or denial" placeholder, and the AI is instructed not
to state a recommendation. Tested as a behaviour, not just a prompt
line.

Export: `.docx`.

---

## Routes — all flag-gated, role-checked, team-scoped

| Route | Role |
|---|---|
| `POST /loan-underwriting/requests` | analyst |
| `GET /loan-underwriting/requests` | viewer |
| `GET/PUT /loan-underwriting/requests/<id>` | viewer / analyst |
| `PUT /loan-underwriting/requests/<id>/assumptions` | analyst |
| `POST /loan-underwriting/requests/<id>/t12` | analyst |
| `GET /loan-underwriting/requests/<id>/underwriting` | viewer |
| `POST /loan-underwriting/requests/<id>/credit-memo.docx` | analyst |

Every read and write filters by the caller's `team_id`. A cross-team id
returns **404**, not 403 — an id's existence in another team shouldn't
be confirmable. `test_route_authorization.py` already sweeps
`app.url_map` for unauthenticated mutating routes, so these are picked
up by that existing test automatically; I'm adding explicit
cross-team-isolation tests on top, since that sweep checks auth, not
scoping.

---

## Tests

Hand-calculated expected values, computed independently of the
implementation. Covering: amortizing payment, zero-rate, full-term IO,
partial-year IO, DSCR at each convention, LTV with purchase<appraised
and appraised<purchase, debt yield, breakeven occupancy, each of the
three max-loan constraints, binding-constraint selection including ties,
all five stress tests, zero vacancy, negative NOI, zero NOI, the
management-fee double-count guard, reserves arithmetic, and the
assumption/provenance round-trip.

End-to-end on Maple Ridge (`backend/benchmark_data/demo_deal/`) with a
realistic request: $18,500,000 purchase price, $13,875,000 loan (75%
LTV), 6.25%, 30-year amortization, 10-year term, 24 months IO, 120
units, against the real demo T-12 — producing a full underwriting
result and a .docx memo.

Then run the suite until green, write `SUMMARY.md` in plain English
(what each ratio means and how to use the module), commit, push.
**No merge.**

---

## Explicitly not doing

- Not retrofitting team isolation onto existing routes (your call; large
  separate project).
- Not changing `parse_t12_rows`, `compute_t12_reconciliation`, or any
  existing behaviour — all T-12 work is additive.
- Not letting AI compute, round, or restate a single number.
- Not having the tool recommend approval or denial.
- Not turning the flag on.
- Not claiming the product has per-team data isolation.
