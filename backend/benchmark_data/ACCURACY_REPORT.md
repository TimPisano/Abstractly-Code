# Accuracy Report — Lease Extraction Benchmark + Demo Deal Mismatch Report

Generated 2026-09-25. Covers two runs against the **real pipeline** (same
`document_extractor` → `resolve_engine()` → extraction/import code an actual
upload uses):

1. `benchmark_data/run_accuracy_benchmark.py` — the 12 real EDGAR sample
   leases scored against `ground_truth.json`.
2. A one-off pipeline run against `benchmark_data/demo_deal/` (15 lease PDFs
   + the 16-unit rent-roll subset), reconciled through
   `app/deal_mismatch.py`'s `build_deal_mismatch_report_data()` and checked
   against `demo_deal/expected_findings.json`.

No app code was modified to produce this report. Test/diagnostic scripts
used for the demo-deal runs live outside the repo (session scratchpad), not
under `backend/`.

## ⚠️ AI engine could not be tested — this is the single biggest gap

`LEASE_AI_EXTRACTION=true` is set and an `ANTHROPIC_API_KEY` is present in
`backend/.env`, but every call to the Anthropic API during this session
failed with **"Your credit balance is too low to access the Anthropic API."**
This was re-verified with a direct `curl` against `api.anthropic.com`
(bypassing the app entirely) both before and ~10 minutes after being told
credits had been added — same error both times, so this isn't a propagation
delay on the app's side.

**Consequence: every number in this report is from the regex fallback
engine (`LEASE_EXTRACTION_ENGINE=regex`), not the AI engine.** The
benchmark script's own docstring is explicit about this: *"NOT the product
claim — do not publish a number from this path."* Regex is what ships when
the AI engine is unreachable — deliberately conservative, pattern-matching
only, no semantic understanding. Treat every accuracy number below as a
**floor / sanity check**, not Abstractly's real accuracy. **Re-run both
scripts with a funded key before quoting any accuracy number to a tester or
customer.**

---

## Part 1 — Lease field-extraction accuracy (12-lease benchmark, regex engine)

Raw auto-score and a manually-reviewed score are both given, because the
scorer uses substring/parse matching for narrative fields
(`property_address`, `permitted_use`, `exclusivity_clause`,
`insurance_requirements`, `default_cure_period`, `rent_escalation`) against
full human-written ground-truth descriptions — a correct-but-differently-
phrased extraction can auto-score as "wrong." The reviewed column corrects
for that; it does **not** turn a real extraction error into a pass.

| Field | Raw auto-score | Reviewed | Note |
|---|---|---|---|
| security_deposit | 83.3% (10/12) | 83.3% | Strong — explicit dollar figure |
| exclusivity_clause | 83.3% (10/12) | 83.3% | Strong — mostly correct absence-detection |
| default_cure_period | 58.3% (7/12) | 83.3% | Core period number usually right; raw score hurt by missing monetary-vs-non-monetary breakdown |
| tenant | 66.7% (8/12) | 75.0% | Fails mainly when the lease names a guarantor or multiple legal entities |
| landlord | 33.3% (4/12) | 75.0% | Raw score mostly an artifact — correct name embedded in boilerplate ("AGREEMENT OF LEASE GATEWAY 44, LLC" vs "Gateway 44, LLC") |
| rent_amount | 41.7% (5/12) | 41.7% | Real errors: regex can't tell monthly vs. annual vs. $/sqft apart |
| square_footage | 41.7% (5/12) | 41.7% | Real errors: scale confusion (whole building vs. one suite) |
| property_address | 16.7% (2/12) | 33.3% | Real weakness: a lease states several addresses (premises, landlord, notices) and regex grabs whichever appears first |
| permitted_use | 25.0% (3/12) | 33.3% | Real weakness: narrative, multi-clause field |
| lease_start_date | 25.0% (3/12) | 25.0% | Real weakness: no derivation logic |
| rent_escalation | 16.7% (2/12) | 25.0% | Real weakness: formulas/tiered schedules |
| insurance_requirements | 25.0% (3/12) | 25.0% | Real weakness: grabs a dollar figure from the wrong clause (e.g. a premium instead of the coverage requirement) |
| cam_charges | 16.7% (2/12) | 16.7% | Real weakness: complex formulas |
| lease_end_date | 16.7% (2/12) | 16.7% | Real weakness: **no derivation** — modern leases state a term length, not an end date |
| renewal_options | 0.0% (0/12) | 0.0% | **Complete failure** — every lease either missed or returned a garbage text fragment |

**Overall: 36.7% raw / ~43.9% reviewed, n=180 (lease, field) pairs across 12 leases.**
43 fields were marked **high-confidence AND wrong** — the most operationally
dangerous failure mode, since a high-confidence tag invites a reviewer to
skip double-checking it.

### Weakest fields (genuine extraction failures, not scoring artifacts)

1. **`renewal_options` — 0%.** Complete failure on every lease. Regex has
   no way to parse conditional, multi-option renewal language.
2. **`lease_end_date` — 16.7%.** E.g. `14_bareescentuals_office_2006`:
   extracted "March 31, 2011" vs. actual "July 31, 2015" (the real end date
   requires computing "10th anniversary of the commencement date" —
   regex can't derive this).
3. **`property_address` — 33.3% reviewed.** E.g. `05_conns_retail_2003`:
   extracted a P.O. Box (the landlord's mailing address) instead of
   "Beaumont Shopping Center" (the actual premises).
4. **`rent_amount` — 41.7%.** E.g. `02_convera_office_2005`: extracted
   "$23.00" (the per-square-foot rate) instead of "$4,531.00/month" (the
   actual payment) — right number on the page, wrong meaning.
5. **`insurance_requirements` — 25%.** E.g. `05_conns_retail_2003`:
   extracted "$5,297.04" (a pro-rata insurance-premium reimbursement line)
   instead of the actual liability-coverage requirement.

### Where regex does fine (for calibration)

`security_deposit`, `exclusivity_clause`, and (once corrected for
boilerplate) `landlord` and `tenant` — short, structurally consistent
fields with an explicit dollar figure or proper-noun answer, no derivation
or disambiguation required.

---

## Part 2 — Demo Deal Mismatch Report (`benchmark_data/demo_deal/`)

Ran the 15 lease PDFs + `maple_ridge_rent_roll_demo_subset_16unit_appfolio.csv`
through the real pipeline exactly as `demo_deal/README.md` instructs
(typing the base property address as `4500 Maple Ridge Trail, Dallas, TX
75248`), then compared `build_deal_mismatch_report_data()`'s output against
the 10 planted issues in `expected_findings.json`.

### 🔴 Bug #1 (blocking): the demo, run exactly as documented, catches 0 of 10 planted issues

Result of the unmodified run: **31 discrepancies, none of them the planted
ones** — 16 `unit_no_lease` + 15 `lease_no_unit`, i.e. every single
documented unit's rent-roll row and lease PDF failed to match up as the
same unit.

**Root cause:** `maple_ridge_rent_roll_demo_subset_16unit_appfolio.csv` has
its own `Property` column, populated with the *property name*
("Maple Ridge Apartments") on every row. `app/rent_roll_import.py`'s
`_COLUMN_ALIASES` maps a bare `"property"` header (and `"property name"`)
to the same `property` field slot used for a real *address*, and
`parse_rent_roll_rows` documents that a populated per-row `Property` column
**always overrides** whatever base address the uploader typed
(`effective_base = property_str or base_property_address`). So no matter
how correctly the demo README's instructions are followed, every rent-roll
row's `property_address` becomes `"Maple Ridge Apartments, Suite A102"`
while every lease PDF states `"4500 Maple Ridge Trail, Dallas, TX 75248,
Suite A102"` — two strings that will never match under `_normalize_address`.
Confirmed directly against `app/api.py`'s upload route (`api.py:1337-1341`),
which passes the typed address straight through unmodified — this is not a
quirk of my test script.

This isn't just a demo artifact: any real AppFolio-style rent-roll export
with a bare `"Property"` (name) column, and a lease PDF whose stated address
differs at all from that name, will hit the same silent failure.

### 🟡 Bug #2: date-drift false positive in `detect_expired_but_occupied`

With the address-matching bug worked around (confirming the underlying
detectors), `detect_expired_but_occupied` compares each lease's end date
against **real wall-clock `date.today()`**, not the rent roll's own
"as of" date (2026-08-31). The demo's lease end dates are fixed at
generation time. Today (2026-09-25) is already past two of them
(`2026-08-31`, for both `B104` and clean-control `H204`) — so as of today,
the demo now:
- **Double-flags `B104`** (already correctly flagged for its planted
  `rent_mismatch`) with a second, unplanted "expired but occupied" finding.
- **Spuriously flags clean-control `H204`** — a unit the README explicitly
  promises "should say nothing" — as expired-but-occupied.

This will get worse over time as more of the demo's hardcoded lease end
dates pass into the past relative to whatever day the demo is actually run.

### Detection accuracy once addresses are fixed (validates the underlying logic)

With the `Property`-column override worked around, the 7 live-detectable
planted issues (excludes the 3 stubbed `concession_missing` findings) are
all found, with dollar amounts matching `expected_findings.json` exactly:

| Unit | Type | Expected annual $ | Detected annual $ | Match |
|---|---|---|---|---|
| B104 | rent_mismatch | $900.00 | $900.00 | ✅ |
| D203 | rent_mismatch | $1,440.00 | $1,440.00 | ✅ |
| G204 | rent_mismatch | $3,120.00 | $3,120.00 | ✅ |
| J303 | rent_mismatch | $1,200.00 | $1,200.00 | ✅ |
| C203 | expired_but_occupied | $15,480.00 | $15,480.00 | ✅ |
| H104 | expired_but_occupied | $20,640.00 | $20,640.00 | ✅ |
| F203 | unit_no_lease | $20,520.00 | $20,520.00 | ✅ |
| A104, E301, I204 | concession_missing | $1,075 / $600 / $900 | — | Known stub, see below |

**7/7 live-detectable planted issues found, 100% recall, exact dollar
amounts on every one.** The reconciliation math itself is correct.

**False positives (once addresses are fixed):** only the 2 date-drift rows
above (B104 duplicate, H204 spurious). All 5 other clean-control units
(A102, B303, D104, G303, J102) correctly produced zero findings. No
`tenant_mismatch` or `dates_mismatch` false positives anywhere in the
16-unit set.

### Concession detection — known stub, not counted as a failure

`detect_concession_missing` in `app/deal_mismatch.py` always returns `[]`
(documented stub, pending a Phase 2 `concessions` field). All 3 planted
concession units (A104, E301, I204 — $2,575/year combined) are correctly
absent from the report today. This matches the demo README's own
disclosure and is **not scored as a defect** here.

---

## Top 3 problems to fix before testers

1. **Demo Deal Mismatch Report finds 0 of 10 planted issues out of the box.**
   The flagship sales-demo artifact, run exactly per its own README, produces
   31 noise rows and none of the real findings — the opposite of what it's
   supposed to demonstrate. Root cause is a real, general bug (not demo-only):
   a rent roll's own `Property` name column silently overrides the
   uploader's typed base address in `rent_roll_import.py`. Fix the alias/
   priority logic (e.g., don't let a bare `"Property"`/`"Property Name"`
   column override an explicitly-typed base address, or detect when the
   per-row value looks like a name rather than an address) — this is
   customer-facing risk beyond just the demo.

2. **`detect_expired_but_occupied` compares against real wall-clock time,
   not the rent roll's stated "as of" date**, so a static demo/test dataset
   silently degrades and starts producing false positives as real time
   passes it by. At minimum, regenerate the demo deal on a rolling basis
   before every use, or thread an `as_of` date through the detector so it's
   pinned to the rent roll's own effective date rather than `date.today()`.

3. **AI-engine field accuracy is completely unverified** — every number in
   this report is the conservative regex fallback, and the two weakest
   fields there (`renewal_options` at 0%, `lease_end_date` at 16.7%) are
   exactly the kind of derivation-heavy fields the AI engine exists to
   handle better. Get the API key funded and re-run
   `run_accuracy_benchmark.py` with `LEASE_AI_EXTRACTION=true` before any
   accuracy number reaches a tester — right now there is no verified number
   for the actual product experience.

*(Concession detection is a known, disclosed stub — not included above as
a "before testers" blocker per the demo README's own framing, but worth
prioritizing once the Phase 2 `concessions` field lands.)*
