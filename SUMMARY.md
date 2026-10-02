# Loan Underwriting Module — plain-English guide

A lender-facing module that takes a loan request and a property's T-12
operating statement, and produces the numbers a bank credit officer needs:
underwritten NOI, debt service, four ratios, the maximum loan each
constraint allows, five stress tests, and a Word credit memo.

**It is turned off.** Every route 404s unless `LOAN_UNDERWRITING_ENABLED`
is set. Current beta testers see nothing change.

---

## Read this first: two honest limitations

**1. This module is NOT team-isolated.** Everyone logged into a
deployment can see every loan request on it. That is the app's existing
single-tenant posture, not something this module adds or fixes — a
separate branch owns the team data model, and this branch creates and
modifies no users/teams/tenant tables at all. Fine when one deployment
serves one customer; **not** safe for two customers sharing a deployment.
Please don't turn this into a "your data is isolated per team" claim on
the website — it isn't one yet. (See "Where team isolation plugs in" at
the bottom for the exact retrofit.)

**2. The tool never recommends approval or denial.** The memo's
recommendation line is always a placeholder for a human. That's a
deliberate product decision, not an unfinished feature — see "Why the
tool won't recommend" below.

---

## The ratios, in plain English

Four numbers decide whether a multifamily loan works. Each one asks a
different question, which is why lenders use all four rather than picking
a favourite.

### DSCR — Debt Service Coverage Ratio

> **Does the property earn enough to pay the mortgage?**

`DSCR = underwritten NOI ÷ annual debt service`

**1.25x means** the property earns $1.25 for every $1.00 of mortgage
payment — a 25% cushion. **Below 1.00x means the property does not cover
its own debt**, and the owner must fund the shortfall from elsewhere.
Most multifamily lenders want 1.25x.

One subtlety worth understanding, because it is the easiest way to be
misled by an interest-only loan. During an interest-only period you pay
only interest, so payments are lower and DSCR looks better — but that
period expires. We therefore report **three** DSCRs:

| Which | What it means |
|---|---|
| `dscr` (**the headline**) | On the full amortizing payment — the one the property must survive after interest-only ends. This is what sizes the loan. |
| `dscr_year_one` | What actually gets paid in the first 12 months. |
| `dscr_interest_only` | During the interest-only period only. |

On the Maple Ridge demo deal: year-one DSCR is a comfortable **1.38x**,
but the real, post-interest-only DSCR is **1.17x** — below the 1.25x
target. A tool reporting only the first number would make an oversized
loan look fine.

### LTV — Loan to Value

> **How much of the property's value is borrowed?**

`LTV = loan amount ÷ value`

**75% means** the loan is three quarters of the property's value and the
buyer is putting 25% in. Lower is safer for the lender: more cushion
before a price drop wipes out their collateral.

**Which "value"?** When both a purchase price and an appraisal exist, we
use **the lower of the two**, and the output says which one was used.
This matters in both directions: if a buyer pays $19M for a property that
appraises at $18M, a lender sizes against $18M — it won't lend against a
premium the market didn't confirm. And if the appraisal comes in *above*
the price, the price still governs, because the buyer's actual cost is
the real exposure.

### Debt Yield

> **If the lender had to foreclose tomorrow, what return would the
> building alone give them?**

`Debt yield = NOI ÷ loan amount`

**8% means** the property's income equals 8% of the loan. Unlike DSCR and
LTV, debt yield **ignores the interest rate and the appraisal entirely**
— which is exactly why lenders added it after 2008. A cheap interest rate
can flatter DSCR, and a generous appraisal can flatter LTV; debt yield
can't be dressed up by either. It is the most honest of the four. 8–10%
is a typical floor.

### Breakeven Occupancy

> **How empty can the building get before it stops paying its bills?**

`Breakeven = (operating expenses + debt service) ÷ potential income`

**80% means** the building must stay 80% occupied to cover expenses plus
the mortgage. Below that, it bleeds cash. The gap between breakeven and
actual occupancy is the real margin for error: a property at 95% occupancy
with an 80% breakeven can lose 15 points of occupancy before trouble.

Two convention choices, stated because lenders genuinely differ: we
**include** replacement reserves (the conservative choice), and we hold
operating expenses fixed as occupancy falls (the standard simplification —
the true breakeven is marginally lower, so our figure errs safe).

---

## How underwritten NOI is built

The whole module rests on this one number, so it's worth understanding.
"NOI" is income minus operating expenses, before any mortgage payment.

A T-12 tells you what the property *actually did* last year. An
underwriter doesn't use those actuals unchanged — they substitute
forward-looking assumptions for three specific lines. The build-up:

```
  Gross potential rent          from the T-12   every unit at market rent, 100% full
− Vacancy                       YOUR ASSUMPTION  the share you expect empty
− Loss to lease                 from the T-12   gap between market and actual lease rents
− Concessions                   from the T-12   free months, move-in discounts
− Bad debt                      from the T-12   rent billed but never collected
= Effective rental income                        realistically collectible rent
+ Other income                  from the T-12   parking, pet rent, utility reimbursement, fees
= Effective gross income (EGI)                   all the money coming in
− Operating expenses            from the T-12   taxes, insurance, payroll, repairs, utilities
− Management fee                YOUR ASSUMPTION  % of EGI
− Replacement reserves          YOUR ASSUMPTION  $/unit/year set aside for roofs, appliances
= UNDERWRITTEN NOI
```

Three things in here are easy to get quietly wrong, so the module handles
each explicitly:

- **The management fee is counted once, not twice.** A T-12's expense
  total already *includes* the management fee the property actually paid.
  Since we apply your fee assumption on top, we first strip the actual fee
  out. On the demo deal that's **$59,899.54** that would otherwise be
  double-charged. The memo discloses the adjustment.
- **Loss to lease is deducted.** It's easy to miss and it silently
  overstates NOI. On the demo deal, omitting it would inflate NOI by
  **$25,521.97**.
- **Replacement reserves are an underwriting addition, not a T-12 line.**
  An operating statement records what was *spent*; a lender charges a
  forward-looking reserve regardless. So underwritten NOI sits *below*
  historical NOI even at identical vacancy. That's expected. The memo
  shows both side by side so the gap is visible instead of confusing.

**Vacancy applies to rent only, not to other income.** Parking and pet
rent on a T-12 are already actual collected figures; applying a vacancy
factor would deduct the same loss twice.

---

## Maximum loan, and which constraint binds

The module computes the largest loan each constraint permits, then reports
the **smallest** — that's the real maximum, and the constraint that
produced it "binds".

| Constraint | Maximum loan it allows |
|---|---|
| Target DSCR | (NOI ÷ target DSCR) converted to a loan balance at the given rate and amortization |
| Max LTV | value × max LTV% |
| Min debt yield | NOI ÷ min debt yield% |

All three targets are configurable. Defaults: **1.25x DSCR, 75% LTV, 8%
debt yield**.

Knowing *which* constraint binds tells you what to negotiate. If DSCR
binds, a longer amortization or a lower rate helps. If LTV binds, more
equity or a higher appraisal helps. If debt yield binds, only more NOI
helps.

**On the demo deal:**

| Constraint | Maximum loan | |
|---|---|---|
| Target DSCR 1.25x | **$12,979,387.71** | ← **binds** |
| Max LTV 75% | $13,875,000.00 | |
| Min debt yield 8% | $14,984,310.50 | |

The request was for **$13,875,000** — so the deal as requested is
**oversized by $895,612.29**, and the memo says so in bold. That's the
module doing its job.

**If NOI is zero or negative**, the DSCR and debt-yield maximums are
**$0** — a property with no income supports no debt. The ratios themselves
are still reported as real negative numbers, because the *size* of a
shortfall is useful information; only the loan amounts are floored, since
a negative maximum loan is nonsense rather than conservatism.

---

## Stress tests

Five cases, each recomputing everything — NOI, debt service, all four
ratios, and the binding constraint. Not just DSCR, because a stress often
changes *which* constraint binds, and that's usually the point.

| Case | What it models |
|---|---|
| Rate +100 bps | Rate 1.00 point higher (a "basis point" is 1/100th of a percent) |
| Rate +200 bps | Rate 2.00 points higher |
| Occupancy −5 points | 5 points *more* vacancy than assumed |
| Occupancy −10 points | 10 points more vacancy |
| NOI −10% | Income 10% below underwriting |

Note the occupancy cases **add to** your vacancy assumption: "occupancy
−10 points" against a 5% vacancy assumption means **15% vacancy**.

On the demo deal, DSCR falls below **1.00x** at both rate +200 bps and
occupancy −10 points — i.e. either shock stops the property covering its
debt. That is the single most useful line in the table.

---

## How to use it

### Turn it on

```bash
# backend/.env — or a real env var in any deployment
LOAN_UNDERWRITING_ENABLED=true
```

Leave it unset and every route returns 404. (404, not 403, deliberately:
a 403 would advertise that a hidden feature exists.)

### The workflow

```bash
# 1. Save the loan request (analyst role)
POST /loan-underwriting/requests
{
  "deal_name": "Maple Ridge Apartments",
  "property_address": "4500 Maple Ridge Trail, Dallas, TX 75248",
  "loan_amount": 13875000, "annual_rate_pct": 6.25,
  "amortization_years": 30, "term_years": 10,
  "interest_only_months": 24,
  "purchase_price": 18500000, "appraised_value": 18750000,
  "unit_count": 120
}

# 2. Upload the T-12 operating statement (.csv or .xlsx)
POST /loan-underwriting/requests/<id>/t12      (file field: "file")

# 3. Read the full underwriting
GET  /loan-underwriting/requests/<id>/underwriting

# 4. Adjust any assumption and re-read step 3
PUT  /loan-underwriting/requests/<id>/assumptions
{ "assumptions": { "vacancy_pct": 7.5 }, "constraints": { "target_dscr": 1.35 } }

# 5. Export the credit memo as Word
POST /loan-underwriting/requests/<id>/credit-memo.docx
```

A loan request is saved per **deal**, where a deal is a building
identified by its normalized street address — the same convention the T-12
cross-check and investment memo already use.

### Roles

| Routes | Role |
|---|---|
| Reads (list, get, underwriting) | `viewer` |
| Writes (create, update, assumptions, T-12 upload) | `analyst` |
| Credit memo export | `analyst` — it produces a document that leaves the building |

### Editing assumptions

All six are editable, and the API returns them with labels, units, and an
`is_default` flag so a UI can render an editable list without hardcoding
anything:

| Assumption | Default | Unit |
|---|---|---|
| Vacancy | 5.0 | percent |
| Management fee | 3.0 | percent of EGI |
| Replacement reserves | 250 | $/unit/year |
| Target DSCR | 1.25 | ratio |
| Maximum LTV | 75.0 | percent |
| Minimum debt yield | 8.0 | percent |

Edits **merge** — changing vacancy alone won't reset the management fee.
The assumptions in force are stored on the request, so a result can never
disagree with the inputs that produced it, even if the defaults change
later.

### Where every number came from

The underwriting response includes `input_rows`, one entry per input:

- Figures from the T-12 carry a real citation — **file, row, and the row
  label quoted**. A T-12 is a spreadsheet, so the citation is a *row*, not
  a page; the module will not invent a page number for a worksheet.
- Loan terms you typed (amount, rate, price) carry **no** source. They
  came from a term sheet this app has never seen, and attaching a citation
  would be a fabrication.

Both populations appear in the memo's Appendix B.

---

## The credit memo

Standard bank structure, eight sections:

1. Loan summary and recommendation
2. Property
3. Sponsor
4. Rent roll and lease analysis
5. Historical and underwritten financials
6. Ratios and stress tests
7. Risks and mitigants
8. Conditions

Plus Appendix A (every assumption, flagged default or edited) and
Appendix B (every input and its source).

**Word, not PDF**, because this is a document an analyst edits — they add
the sponsor section, write the recommendation, and put it on their own
letterhead.

### Who writes what

```
numbers  →  loan_underwriting.py   plain Python arithmetic, no AI
prose    →  Claude, narrative sections ONLY (2, 4, 7, 8)
layout   →  credit_memo_template.py
document →  credit_memo_export.py
```

**AI never produces a number.** The model receives already-computed
figures as read-only context and writes prose referring to them. That's
why a credit officer can check this document: every figure is reproducible
by hand from the cited source row, and no figure passed through a model on
its way to the page. There's a test that feeds the model a response full
of wrong numbers and asserts the document's figures don't budge.

If there's no Anthropic API key or the call fails, **the memo still
renders** with every table intact and a visible note that the prose wasn't
generated. The numbers are the part a lender needs. (This is the path that
runs today — the project's API key has no credit.)

### Why the tool won't recommend

Section 1 always reads:

> `[ FOR CREDIT OFFICER DETERMINATION — this analysis does not recommend
> approval or denial. ]`

Approving a loan is a credit decision with legal and fiduciary weight,
made with context this tool never sees: borrower relationship, portfolio
concentration, market knowledge, the lender's own appetite. A model
emitting "recommend approval" would be producing the most consequential
sentence in the document from the least information.

So the engine computes every ratio and names the binding constraint, and a
human writes the verdict. The model is instructed not to state one — and
because a prompt instruction is not a guarantee, there's a test that feeds
it pushy approval language and asserts the recommendation line is still
the placeholder.

### Swapping in a lender's format

The entire template is in **one file**: `backend/app/credit_memo_template.py`.
Section order, headings, which sections carry tables, and which carry
prose all live there. Editing it needs no changes anywhere else. The one
requirement is that the loan summary keeps its
`recommendation_placeholder` block.

---

## Files

| File | Role |
|---|---|
| `app/loan_underwriting.py` | The engine. Every formula. No AI, no database, no Flask. |
| `app/loan_request.py` | Saving requests, assumptions, and T-12 snapshots. |
| `app/t12_import.py` | *Extended*: full line-item parsing (the original one-number function is untouched). |
| `app/credit_memo_template.py` | The swappable template. |
| `app/credit_memo.py` | AI narrative generation + memo assembly. |
| `app/credit_memo_export.py` | Word renderer. |
| `app/database.py` | *Extended*: `loan_requests` + `t12_snapshots` tables only. |
| `app/api.py` | 8 routes, all flag-gated and role-checked. |

### Why the T-12 is snapshotted

The existing T-12 cross-check parses a statement and throws it away —
fine for a one-shot comparison. But a saved loan request must be
reproducible: regenerate the memo next week and it must show the same NOI
with the same citations. So the **parsed figures** are stored.

**The uploaded file itself is never stored** — only the figures and the
row each came from, matching the app's existing delete-after-processing
posture for uploaded documents. Re-uploading a corrected T-12 adds a new
snapshot rather than overwriting the old one, so a memo generated last
week can still be explained.

---

## Tests

```bash
cd backend
python tests/run_all_tests.py                    # whole suite
python tests/test_loan_underwriting.py           # formulas only
```

| File | Covers |
|---|---|
| `test_loan_underwriting.py` | 48 formula tests, every expected value hand-calculated with the arithmetic shown in a comment. Edge cases: interest-only (full and partial year), 0% interest rate, zero vacancy, zero and negative NOI, the management-fee double-count guard, loss to lease, missing appraisal, constraint ties. |
| `test_loan_request_api.py` | 22 route tests: the flag off on every route, roles, and validation that refuses rather than guessing. |
| `test_credit_memo.py` | 25 tests: template structure, mocked Anthropic (no real call ever), the recommendation placeholder surviving pushy model output, model figures not reaching the document, and the .docx contents. |
| `test_loan_underwriting_demo_deal.py` | End-to-end on the fictional Maple Ridge deal through the real HTTP routes. |

**Every Anthropic call is mocked.** No test spends money.

Current state: **67 of 68 suite files pass.** The one failure,
`test_document_extractor.py`, is pre-existing and unrelated — it needs
`tesseract` installed locally and fails the same way on `main` (see
CLAUDE.md rule 9).

The demo-deal test **skips cleanly** when `benchmark_data/demo_deal/` is
absent, because that fixture is untracked and arrives with
`fix/rent-roll-hardening`. To run it against a copy elsewhere:

```bash
ABSTRACTLY_DEMO_DEAL_DIR=/path/to/demo_deal python tests/test_loan_underwriting_demo_deal.py
```

---

## Where team isolation plugs in

This module has **no tenancy column**, deliberately — a separate branch
owns the team data model. When it lands, the retrofit is small and
confined, because it was designed for:

**1. Schema** (`app/database.py`, `_migrate_loan_underwriting_tables`):
add `team_id INTEGER NOT NULL` to `loan_requests` and `t12_snapshots`,
plus a composite index on `(team_id, normalized_property_address)`.
`NOT NULL`, not nullable — a nullable tenant column is how isolation
silently degrades to "visible to everyone" for any row written before the
team was resolved. If a caller has no team, the write must fail, not land
unscoped.

**2. Queries** (`app/loan_request.py`): every single-request read goes
through `_require_request()` and every list through
`list_loan_requests()`. Those two functions are the **only** places that
build a `WHERE` clause against `loan_requests`. Add a `team_id` parameter
to each and an `AND team_id = ?` to their queries. That funnel exists
specifically so this is a reviewable diff rather than an audit of every
call site — please keep new queries going through it.

**3. Routes** (`app/api.py`): pass the caller's team into those two
functions. Return **404**, not 403, for a request belonging to another
team — an id's existence in someone else's team shouldn't be confirmable.

**4. Tests** (`tests/test_loan_request_api.py`): add the cross-team cases.
A request created under team A must be 404 for a caller in team B, on
every one of the eight routes. The file's docstring already names these as
the tests to add.

Until that's done: **this module is not team-isolated, and the app isn't
either.**
