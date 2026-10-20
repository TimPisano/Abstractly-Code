# Plan: make extraction read affordable-housing forms

**Date:** 2026-10-19 · **Status:** proposal, nothing built. No app code was changed to write this. Each step below becomes its own branch through `/start-task`, with its own plan, tests and review.
**Evidence:** [eval-baseline.md](../research/eval-baseline.md) and the harness in [`tests/eval/affordable/`](../../tests/eval/affordable/README.md). The "measured" gains below come from what-if runs on that harness: the same samples and answer keys, with the proposed fix simulated outside the app.

---

## Where we start

| | Today (regex engine) |
|---|---|
| Lease fields right (tenant, owner, rent, dates, address, deposit) | **0 / 48** on filled forms, 5 / 48 on scans (lenient) |
| Wrong or invented values, marked "high" confidence | **45 of 46** |
| Program fields extracted (HAP, TTP, AMI limit, household, contract #…) | **0%**: no such fields exist |
| Values on the page that reach the extractor | 100% flattened · 95% scanned · **21% unflattened fillable forms** |
| Uploads refused or split | 1 HAP contract refused as a "rent roll"; 15 of 41 runs split into 2–5 "leases" |
| AI engine | Unmeasured (API billing blocked the run) |

## Why each form scores low

Root causes, used in the table:

| Code | Cause | Where in the code |
|---|---|---|
| **R1** | **Patterns are written for lease prose.** They look for "Tenant: …" or "hereinafter the Tenant", not a form label with a value beside or below it. Layout-ordered text barely helps (2/48 in a what-if), so this is the main cause. | `field_extractor.py` (`_extract_defined_party`, `_extract_rent`, `_extract_property_address`, …) |
| **R2** | **Labels and titles are taken as values**, and confidence never questions them. | `field_extractor.py:357` `_apply_confidence_validation` has range checks for money and dates only |
| **R3** | **Unflattened fillable forms are invisible.** pypdf's page text doesn't include form-field values. | `document_extractor._extract_pdf` → `pdf_extractor.PDFExtractor.extract_text` |
| **R4** | **The rent-roll gate counts repeated header dates.** "(exp. 07/31/2022)" on every page pushes a PBV contract past 15 dates. | `field_extractor.py:114` `_RENT_ROLL_DATE_THRESHOLD`, `looks_like_rent_roll_table` |
| **R5** | **One form is split into several "leases".** | `FieldExtractor.detect_lease_boundaries` |
| **R6** | **Money without a `$` isn't recognized.** 42 of 87 money values on these forms print bare ("1,325", "415,800"). | `normalize.parse_currency` |
| **R7** | **OCR drops some short values**: IDs, unit numbers, small counts (16 of 339). | `pdf_extractor._extract_with_ocr` |
| **R8** | **No schema for program fields.** The engines only have the 15 lease fields. | `field_extractor.extract_fields`, `ai_extraction.LEASE_FIELDS` |

| Form | Score today (clean / scan) | Causes | What goes wrong |
|---|---|---|---|
| HUD-52517 RFTA | 0/6 · 0/6 | R1, R2, R3, R8 | Address = "of Unit (street address, unit #…)"; rent "$1,325.00" is on the page but missed; values all invisible when unflattened |
| HUD-52641 HAP contract ×2 | 0/6 · 0/6 each | R1, R2, R5 (scan), R6, R8 | Tenant = "Enter" (from "Enter full name of tenant"); address = instruction text; rent printed as "1,325" with no `$` |
| HUD-52530A PBV contract | refused · refused | **R4**, R3, R8 | Upload rejected as a rent roll |
| HUD-52530B PBV contract | 0/3 · 0/3 | R1, R3, R8 | Owner, effective date, project address all missed |
| HUD-50059 | 0/4 · 0/4 | R1, R2, R3, R5 (scan), R8 | Tenant = "Eligibility"; 30 of 38 values invisible when unflattened; every rent figure is a program field we can't hold |
| HUD-52670 voucher | none stated · none stated | R2, R3, R8 | Invents tenant "Assistance Payments"; it's a property-level form, so all of its value is program fields |
| HUD-52697 LIHTC tenant data | 0/1 · 1/1 | R2, R5, R8 | Tenant = "Data Collection Form"; split into 3 |
| IRS 8609 / 8823 / 8586 | 0/5 · 1/5 | R1, R2, R3, R6, R8 | Address = "City or town, state, and ZIP code"; amounts print without `$` |
| CHFA LURA | 0/2 · 0/2 | R1, R2, R5, R8 | Tenant = "Income Certification", landlord = "assigns"; prose with inline blanks, so templates don't fit (see step 5) |
| TICs: SC, LA, NJ, IL | 0/12 · 3/12 | R1, R2, R5, R7, R8 (+R3 for IL) | Tenant = "Income Certification" on all four; address = "Unit Number: #Bedrooms:"; tenant rent missed; split into 2–5 |

---

## The fixes, the gain from each, and the order

Order rule: **measure first, then stop the harm, then unblock cheaply, then build the big piece.** Every step is a separate small branch, and every one is checked against the harness:

```
backend/venv/bin/python -I tests/eval/affordable/run_eval.py --variants clean acroform   # ~seconds
```

### Step 0: Run the AI engine on the eval set (no code)

- **What:** add API credits, then run `run_eval.py --engine ai`: 41 calls, a few dollars at most.
- **Why first:** it decides how big step 5 is. If AI gets most lease fields right on forms, step 5 can lean on AI with a bigger schema. If it doesn't, step 5 is template-driven.
- **Expected gain:** none by itself. It's the measurement that sets direction.
- **Effort:** minutes.

### Step 1: Guard against label and heading text (`fix/extraction-label-guard`)

- **What:**
  - Before a value is accepted, reject it, or drop it to low confidence, when it is:
    - mostly underscores,
    - an all-caps heading or form title, or
    - text that is printed on the form itself.
  - For known forms (step 4) that last test is exact: compare against the stored blank form. For unknown documents, use a list of common form-label phrases ("street address", "city, state", "enter full name", "certification").
  - Lives in `_apply_confidence_validation`.
- **Measured gain:**
  - Exact version (blank-form text): suppresses **39 of 46** wrong or invented values and drops **0** of the 5 correct ones.
  - Remaining 7: 3 wrong, 4 invented (e.g. "assigns", TIC effective date as lease start).
  - The generic label-list version for unknown documents is unmeasured and will catch fewer.
- **Recall gain:** none. It turns "confidently wrong" into "not found", which is the honest answer.
- **Who else benefits:** CRE leases too, since title words and labels can leak there as well.
- **Effort:** S. Needs regression tests (CLAUDE.md: every fix gets one). The eval's wrong values make good fixtures.

### Step 2: Read fillable-form values (`fix/pdf-acroform-values`)

- **What:**
  - When a PDF has form fields, add their values to the page text as `Field label: value` lines, on the page that holds the widget.
  - Or flatten a copy before extracting.
  - Either way, also tell the user the PDF had form fields, so a silent empty result can't happen.
  - Lives in `document_extractor._extract_pdf`.
- **Measured gain:** values the extractor can see on unflattened forms go from **40/192 (21%) to 189/192 (98%)**. Recall stays near 0 until step 5, but nothing is invisible anymore.
- **Bonus:** for fillable forms the field *names* ("6 Proposed Rent", "Print or Type Name of Household Head") are a deterministic map to our fields. Step 5 uses that.
- **Effort:** S.

### Step 3: Count unique dates in the rent-roll gate (`fix/rent-roll-gate-unique-dates`)

- **What:**
  - Count *distinct* dates (and amounts) in `looks_like_rent_roll_table`, not every occurrence.
  - Or skip the gate when a known form ID is detected (step 4).
- **Measured gain:**
  - HUD-52530A drops from 15 dates to **3 distinct**, so both refused runs go through. HUD-52530B: 10 → 1.
  - **Must confirm:** the existing rent-roll fixtures still trip the gate when counted distinctly (the gate's comment cites a 120-row roll with 242 ISO dates). That check is the regression test.
- **Effort:** S.

### Step 4: Recognize the form and keep it whole (`feature/form-detection`, behind a flag)

- **What:**
  - Detect a known form from its printed ID or title: "HUD-52641", "HUD-50059", "Form 8609", "TENANT INCOME CERTIFICATION", OMB numbers.
  - When a form is recognized: don't split it into several leases, skip the rent-roll gate, and record `doc_kind` (HAP contract, 50059, TIC…). Steps 1 and 5 rely on that.
  - The same record of each document's kind is what plan task T2 (HAP contract extraction) needs.
- **Measured gain:**
  - Removes **all 15** splits seen in the eval (TICs 2–5 each, 52697, LURA, 52641 and 50059 scans).
  - Removes the remaining reason a known form could hit the rent-roll gate.
- **Effort:** S–M. Flag default off (CLAUDE.md).

### Step 5: Extract form fields, program fields included (`feature/form-extraction`, behind a flag)

This is the big one, and the one that moves scores. It has two parts that share one output schema.

- **5a. Program-field schema per document kind.** These are the fields the eval keys already define.
  - **HAP contract:** contract number, PHA, owner, tenant, unit address, term start/end, contract rent, utilities and who pays, initial HAP.
  - **50059:** effective date, next recert, household, income by source, TTP, tenant rent, HAP, utility allowance, utility reimbursement.
  - **TIC:** effective and move-in dates, BIN, household, income, AMI tier, income limit, tenant rent, UA, gross rent, max rent.
  - **IRS and HUD-52670 forms:** their line items.
  - Stored with citations like the lease fields, in the T1 data model, not the lease JSON.
  - Lease fields are filled from the same values (owner → landlord, contract rent → rent) so the existing checks work.
- **5b. Getting the values.** Two routes; step 0 picks the balance.
  - **Template route, for known public forms:**
    - Store each blank form (already in `tests/eval/affordable/sources/`) with a field map: which label or region holds which field. The eval specs are a first draft of those maps.
    - Fillable forms map by field name (step 2).
    - Flattened forms: diff the upload against the blank to isolate what was typed, then assign each value to the field whose label it sits next to.
    - **Measured:** the blank-form diff isolates **323 of 387 (83%)** of the answer-key values as clean, separate chunks on the flattened samples. Several forms score 100% (50059, RFTA, 52670, IRS 8586 and 8609, NJ TIC).
    - The misses are a word-splitting artifact: values written on underscore lines (HUD-52697 7/25), letter-spaced text (SC TIC 19/37), and inline prose blanks (LURA 6/16). A character-level diff should recover most of them.
    - **Expected:** about 80% lease and program recall on the covered flattened forms, near 100% on fillable ones after step 2.
    - Scans need OCR word positions and deskew; expect lower, bounded by the 95% that survives OCR. Unmeasured.
  - **AI route, for everything else** (LURAs and other prose documents, unknown state forms):
    - Give the model the detected document kind and that kind's schema, not the lease schema.
    - Gain unknown until step 0, and it has to be re-measured on this harness.
- **Prerequisite:** `feature/s8-pii-guard` (T0) must merge before 50059s and TICs from real tenants are uploaded. Those carry names, dates of birth and income.
- **Effort:** L, split into branches: schema + HAP contracts first (feeds feature #1 in [feature-priorities.md](../research/feature-priorities.md)), then TICs (#3), then 50059 and the voucher (#5).

### Step 6: Read money printed without a `$` in form fields (inside step 5)

- **What:** an amount parser for *form fields that are known to be money* that accepts "1,325" and "415,800".
  - **Don't** loosen `normalize.parse_currency` globally. It's shared with rent-roll import and the lease matchers, where a bare number may not be money.
- **Gain:** needed for 42 of 87 money values (48%) on these forms. Nothing on its own, since the regex never finds rent anyway. Without it, step 5 loses about half its money fields.
- **Effort:** S.

### Step 7: OCR touch-ups (later)

- **What:** higher render resolution, or a page-segmentation mode suited to forms, for short values.
- **Gain:** at most the 16 of 339 values (about 5%) that OCR drops today.
- **Effort:** S–M. Do it only once step 5 works on scans.

---

## Summary of order and expected gains

| Order | Step | Branch | Effort | What it changes (measured unless noted) |
|---|---|---|---|---|
| 0 | Run the AI eval | none | minutes | Decides step 5's balance |
| 1 | Label/heading guard | `fix/extraction-label-guard` | S | Wrong or invented values **46 → 7**; 0 correct lost |
| 2 | Read fillable-form values | `fix/pdf-acroform-values` | S | Visible on unflattened forms **21% → 98%** |
| 3 | Unique dates in the rent-roll gate | `fix/rent-roll-gate-unique-dates` | S | HAP contract no longer refused (**2 runs**) |
| 4 | Form detection, no splitting | `feature/form-detection` | S–M | Splits **15 → 0** |
| 5 | Form + program-field extraction | `feature/form-extraction` (several) | L | Lease recall **0% → ~80%** on covered flattened forms; program fields **0% → ~80%** (estimated from 83% isolation) |
| 6 | Bare-amount money parser | inside step 5 | S | Unlocks the **48%** of money values printed without `$` |
| 7 | OCR touch-ups | later | S–M | Up to **+5%** of values on scans |

Steps 1–3 are independent; they can run in parallel and each merges alone. Step 4 should land before 5. Step 5 waits for step 0's result and for T0 (the PII guard).

## Risks and open questions

- **The 80% is a ceiling, not a promise.** The diff shows a value can be isolated. It still has to be assigned to the right field, and these samples are clean, typed and one household per form. Real files are messier (handwriting, stamps, photocopies of photocopies). Get 3–5 real, anonymized forms from a design partner before trusting the number.
- **Form editions change.** HUD and states revise forms (the 50059 here is the 2014 edition). Templates need a version per edition and a fallback to the AI route.
- **The guard's generic version could hide real values** on unusual leases (a tenant really named "Enterprise Holdings"?). Downgrade confidence rather than delete when unsure, and test on the existing CRE corpus.
- **Don't invent rules.** Steps 4–5 extract what the form says. Any check of HUD or state rules built on top (TTP math, rent limits) cites its source and says "Verify with your PHA / state agency" (CLAUDE.md).
