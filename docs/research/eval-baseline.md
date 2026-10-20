# Affordable-Housing Extraction: Baseline

**Date:** 2026-10-19 · **Branch:** `research/affordable-housing` · **Engine measured:** regex (the default; offline) · **AI engine:** attempted 2026-10-19, blocked by API billing (see "Regex vs AI")
**Harness:** [`tests/eval/affordable/`](../../tests/eval/affordable/README.md) · raw results: [`results/regex.json`](../../tests/eval/affordable/results/regex.json)

> **Update, third pass (branch `feature/affordable-forms`).** The non-AI fixes from the plan were built as a standalone module, `backend/app/affordable/`. On the 16 forms, lease fields went from **0% to 94%** on flattened forms, both on the development copies and on a holdout set the mappings were never tuned on. Program fields (HAP, TTP, limits…) went from **0% to 89–92%**. Scans are weaker (88% dev, 56–58% holdout). Before/after scores per fix are in the last section, "After: the non-AI fixes". Everything above that section is the "before" picture and is unchanged.

## What was measured

- **16 public blank forms** (HUD, IRS, five state housing agencies), each filled with fictional but internally consistent values, with a JSON answer key. Examples: HAP contract rent = tenant share + HAP, and TIC income stays under the computed AMI limit.
- **3 variants of each, 41 runs in total:**
  - **clean:** values drawn into the page and flattened, like a filled form printed to PDF.
  - **acroform:** values left in the form's own fillable fields, as Acrobat or Preview saves them. Only the 9 forms that have fillable fields.
  - **scan:** an image-only copy with skew and speckle, which forces our OCR path.
- **The pipeline is the upload path in `api.py`, unchanged:** page text extraction, then the "needs OCR" gate, the rent-roll gate, lease boundary detection, then field extraction.
- **Two scores:**
  - **Lease fields:** our 15 lease fields (tenant, landlord, rent, dates, address, deposit…) against the key, using the app's own matcher (`extraction_scoring.py`), with money compared numerically.
  - **Program fields:** HAP, TTP, AMI limit, household size, contract number and so on. The engine has no fields for these, so extraction is 0% by construction. We measure **text-layer recall** instead: does the value survive into the text the extractor sees?

## Headline

| Variant | Runs | Lease fields right | Wrong or invented values | Lease values in text | Program values in text | Program fields extracted |
|---|---|---|---|---|---|---|
| clean | 16 | **0 / 48 (0%)** | 3 invented + 17 wrong | 100% | 100% | 0% |
| acroform | 9 | **0 / 24 (0%)** | 1 invented + 6 wrong | **21%** | **21%** | 0% |
| scan (OCR) | 16 | **5 / 48 (10%)**\* | 6 invented + 13 wrong | 100% | 95% | 0% |

\* All five scan "hits" are addresses that only pass the matcher's substring rule. The extracted value carries trailing label text, e.g. "2250 Magnolia Ferry Road, … Unit Number: 114 #Bedrooms: 1". A strict matcher would score them wrong.

**In one line:** the text gets through, but the extractor doesn't read forms, and when it's wrong it says "high confidence".

## Regex vs AI

| Variant | Lease fields right: regex | Lease fields right: AI (`claude-sonnet-5`, prompt v2) | Program fields extracted: regex | Program fields extracted: AI |
|---|---|---|---|---|
| clean | 0 / 48 (0%) | **not run** | 0% | not run (0% by construction) |
| acroform | 0 / 24 (0%) | **not run** | 0% | not run (0% by construction) |
| scan | 5 / 48 (10%) | **not run** | 0% | not run (0% by construction) |

- **Why the AI column is empty.** The run was approved and attempted. The first call returned HTTP 400, "Your credit balance is too low to access the Anthropic API" (request `req_011CgChTW6Ezbv7PeSfEmsb2`). I stopped there: no retries, no other key. The runner now records a failed AI call as a failed upload instead of crashing.
- **To fill it in once credits are added** (41 calls, all variants):
  `backend/venv/bin/python -I tests/eval/affordable/run_eval.py --engine ai`
  It writes `results/ai.json`, with the model, call count and token totals.
- **What to expect.** The AI engine fills the same 15 lease fields, so **program fields stay at 0% whatever it scores**. It also reads the same text, so on unflattened fillable forms it starts from the same 21% of values. Its lease-field score is the open question: it decides how much form-specific work the plan needs ([affordable-extraction-plan.md](../plans/affordable-extraction-plan.md), step 0).

## Accuracy by document type

Lease-field recall is right / stated. "Program text" is the share of program values present in the extracted text.

| Doc type | Docs | Lease recall: clean | Lease recall: scan | Lease recall: acroform | Program text: clean | Program text: scan | Program text: acroform |
|---|---|---|---|---|---|---|---|
| HAP contract (HCV 52641 ×2, PBV 52530A/B) | 4 | 0/18 | 0/18 | 0/6 | 54/54 | 49/54 | 6/26 |
| RFTA (HUD-52517) | 1 | 0/6 | 0/6 | 0/6 | 10/10 | 10/10 | 1/10 |
| PBRA certification (HUD-50059) | 1 | 0/4 | 0/4 | 0/4 | 38/38 | 38/38 | 8/38 |
| PBRA voucher (HUD-52670) | 1 | (none stated) | (none stated) | (none stated) | 19/19 | 19/19 | 6/19 |
| LIHTC TIC (SC, LA, NJ, IL) | 4 | 0/12 | 3/12\* | 0/3 | 140/140 | 134/140 | 3/35 |
| HUD LIHTC tenant data (52697) | 1 | 0/1 | 1/1\* | (no form fields) | 24/24 | 23/24 | (no form fields) |
| IRS LIHTC forms (8609, 8823, 8586) | 3 | 0/5 | 1/5\* | 0/5 | 40/40 | 38/40 | 11/40 |
| LURA (CHFA template) | 1 | 0/2 | 0/2 | (no form fields) | 14/14 | 12/14 | (no form fields) |

## Worst fields

**Lease fields.** Every field is at or near 0%, so they're ranked by how harmful the failure is.

| Field | Stated | Right (clean / scan) | What the engine returned instead | Harm |
|---|---|---|---|---|
| **tenant** | 8 | 0 / 0 | Form words: "Income Certification" (all four TICs and the LURA), "Enter" (both 52641s), "Eligibility" (50059), "Assistance Payments" (52670), "Data Collection Form" (52697) | **Worst.** A wrong name asserted at high confidence |
| **property_address** | 13 | 0 / 5\* | Label text: "of Unit (street address, unit #, city, state, zip code)", "City or town, state, and ZIP code", "Unit Number: #Bedrooms:", underscores | Wrong value at high confidence |
| **rent_amount** | 8 | 0 / 0 | Nothing. Never found, even with "$1,325.00" on the page | Missed (contract rent and TIC tenant rent) |
| **landlord / owner** | 10 | 0 / 0 | Nothing, except "assigns" on one scan | Missed |
| **lease_start_date** | 5 | 0 / 0 | Missed. On three TIC scans it returned the effective date where the key has no lease start | Missed, plus 3 invented (debatable: move-in ≈ lease start) |
| **lease_end_date** | 2 | 0 / 0 | Missed | Missed |
| **security_deposit** | 2 | 0 / 0 | Missed | Missed |

**Confidence is not a safety net.** **45 of the 46** wrong or invented lease values were labelled **"high"** confidence. The confidence check doesn't recognize form labels, titles or blank underscores as non-values.

**Program fields.**
- Extraction is 0% for all 339 program values: HAP, TTP, tenant rent, utility allowance, gross rent, AMI limits, household size, income by source, contract and BIN numbers, effective and recert dates.
- Survival into the text the extractor sees:
  - **acroform:** 133 of 168 values are invisible. In effect, every value typed into a fillable field is missing; only values drawn outside fields survive. On the 50059, 30 of 38 are gone, including every rent and income figure. The RFTA's one "surviving" value is bedrooms = "2", a false positive from the small-integer matcher.
  - **scan:** 16 values lost to OCR, mostly short or isolated values: the initial HAP on both 52641s, the TIC's BIN, county and unit number, small unit counts, one income limit, one gross rent, one signature date. Mean OCR confidence per document is 79–93.

## Findings, in order of what to fix

1. **The extractor reads lease prose, not forms.**
   - On flattened forms every value is in the text, and it still gets 0 of 48.
   - Is text order the cause? pypdf emits filled values after the printed labels. A what-if run on layout-ordered text (pdfplumber) only reached **2 of 48**, so order is a minor factor.
   - The regex patterns look for lease phrasing ("Tenant:", "hereinafter the Tenant"), and on forms they match the label instead of the value next to it.
   - Affordable documents need a form-aware path: label-to-value pairing, or the AI engine (unmeasured).
2. **High-confidence garbage.**
   - Title words and field labels come back as the tenant's name or the address, marked "high".
   - This is the dangerous failure mode `extraction_scoring.py` itself calls out.
   - A cheap guard: reject values that match the document's own labels, all-caps headings, or underscore runs.
3. **Unflattened fillable forms are silently empty.**
   - When a TIC, 50059 or RFTA is filled in Acrobat and saved without flattening, our PDF text never sees the values (21% survival, and only the values that weren't in fields).
   - The pipeline reports "ok", not "needs OCR", so the user gets an empty result with no warning.
   - pypdf can read the field values directly (`get_fields()`, each field's `/V`). Reading them, or flattening before extraction, would fix it.
4. **The rent-roll gate rejects a real PBV HAP contract.**
   - HUD-52530A prints "(exp. 07/31/2022)" on every page. With a few filled dates it passes the gate's 15-date limit (`field_extractor.py:114`).
   - The upload is refused as "looks like a rent roll" (422), in both the clean and scan variants.
5. **One form becomes several "leases".**
   - Boundary detection splits single forms into 2–5 ranges: TICs 2–5, the 52697 3, the LURA 2–3, the 52641 scans 2.
   - The user would see several partial records for one document.
6. **Unsigned money is invisible to the money parser.**
   - `normalize.parse_currency` returns None for "1,325.00", "415,800" or "1325" (no `$`).
   - HUD and IRS forms print the `$` in the label and leave it off the value, so rent extraction and the scoring matcher both miss these.
   - The eval works around this for its own comparisons. The app code was not changed.
7. **OCR is not the bottleneck.**
   - Scanned copies keep 95% of program values, with mean confidence 79–93.
   - Lease recall is actually *higher* on scans (5 vs 0), because OCR emits text in reading order. But those hits are lenient matches.

**What this means for the roadmap** ([feature-priorities.md](./feature-priorities.md)):
- Every top feature (#1 tie-out, #3 LIHTC limit check, #5 50059 arithmetic, #7 file audit) depends on reading HAP contracts, 50059s and TICs. Today we can't read any of them.
- **Before** building those checks, add three things: a form-aware extraction path with program fields in the schema, AcroForm value reading, and a label/heading guard on confidence.
- This harness is the regression test for all three.

## Not measured, and limits

- **The AI engine is unmeasured.** It was blocked on API billing; see "Regex vs AI" for the error and the rerun command.
- **Synthetic fills.** Values are typed in Helvetica: no handwriting, no stamps, no real-world mess. Scans are simulated, not from a real scanner. One household per form.
- **Answer keys are our own.** The mapping of form fields to lease fields is a judgment call; for example, TIC tenant rent counts as `rent_amount`, and move-in date doesn't count as lease start. Change the key and rerun if you disagree.
- **Matcher looseness.**
  - Text-layer checks for small integers (bedrooms "2", unit counts) can false-positive.
  - The app's address and tenant matcher accepts substrings; that's how the five scan hits score.
  - $0 amounts were left out of keys.
- **Edition and form-identity caveats.** The HUD-50059 is the 2014 edition (expired 2017; layout only). The IHDA TIC is **Illinois** (joint with Chicago and Cook County), not Indiana; eval-docs.md is corrected.
- **Unchanged areas.** Nothing in `backend/` was modified. No program-field extractor exists yet, so this is the "before" picture.

---

## After: the non-AI fixes (`feature/affordable-forms`)

**Date:** 2026-10-19 · **Code:** `backend/app/affordable/` (new; nothing in the upload pipeline or `ai_extraction.py` was touched; flag `AFFORDABLE_FORMS_MODE`, default off) · **Raw results:** [`results/`](../../tests/eval/affordable/results/) (`regex.json`, `regex+acroform.json`, `regex+layout.json`, `affordable.json`)

### How it was measured

- **Same 16 forms and answer keys, now in five variants (73 runs per engine):**
  - **clean, acroform, scan:** as above.
  - **holdout (new):** every value redrawn shifted ±2.5 pt, in Helvetica, Times or Courier, at 85–112% size, with dates and amounts reformatted ("Dec. 1, 2026", "1325.00").
  - **holdout_scan (new):** a scanned copy of the holdout.
- **The guard against tuning to the test set:**
  - The form mappings were written from the *blank* forms and debugged only on clean, acroform and scan.
  - The holdout files were never opened while writing mappings.
  - The holdout was scored once at the end. One setting (OCR resolution) changed afterwards, for a reason found on the dev scans; both measurements are shown.
- **Each fix measured on its own, as a separate engine in `run_eval.py`:**
  - `regex`: today's upload path.
  - `regex+acroform`: fix 1, reading fillable-form values.
  - `regex+layout`: fixes 1 + 2, adding reading-order text from word positions and OCR.
  - `affordable`: fixes 1 + 2 + 3, adding per-form field mappings.
  - The first three still use today's regex extractor; only the last reads program fields.

### Before and after, by fix

Lease-field recall (tenant, owner, rent, dates, address, deposit) / program-field accuracy (HAP, TTP, limits, household, IDs…):

| Engine | clean | acroform | scan | holdout | holdout_scan |
|---|---|---|---|---|---|
| `regex` (before) | 0% / 0% | 0% / 0% | 10% / 0% | 0% / 0% | 6% / 0% |
| `regex+acroform` (fix 1) | 0% / 0% | 8% / 0% | 10% / 0% | 0% / 0% | 6% / 0% |
| `regex+layout` (fixes 1+2) | 10% / 0% | 8% / 0% | 13% / 0% | 10% / 0% | 6% / 0% |
| **`affordable` (fixes 1+2+3)** | **94% / 92%** | **92% / 95%** | **88% / 85%** | **94% / 89%** | **56% / 58%**\* |

\* The first holdout-scan measurement, with OCR at 300 dpi, was **58% / 63%**. OCR was then lowered to 200 dpi (the app's own setting) because dev scans improved (program 81% → 85%, values recovered 89% → 95%). On the holdout scans it went the other way, and two TICs stopped being recognised. Both numbers are reported; see "What's left".

**What each fix did:**
1. **Reading fillable-form values** (`acroform.py`). On unflattened forms, the share of values the extractor can see went from **21% to 100%** of lease values and **98%** of program values. The regex extractor still can't use them (0% → 8% recall), because it doesn't read forms. With the per-form mappings, unflattened forms score **92% / 95%**, the best of any variant.
2. **Layout-aware text** (`layout.py`). Values now sit beside their labels in the page text. On its own it lifts the regex extractor only **0% → 10%** (clean and holdout). That confirms the baseline finding: text order was a minor cause, and the regex patterns were the major one.
3. **Per-form field mapping** (`extract.py` + `forms/`). 13 mappings cover all 16 forms: RFTA, HAP contract 52641 (both PHA re-saves), PBV 52530A/B, 50059, 52670, 52697, the SC/LA/NJ TIC template, the Illinois TIC, IRS 8609/8823/8586, and a partial CHFA LURA. This is the fix that moves the scores: **0% → 94%** lease and **0% → 89–92%** program on flattened forms, dev and holdout alike.

**Confidence is now honest.**
- Before: today's engine produced **46** wrong or invented lease values across clean, acroform and scan, all marked **"high"**.
- After: the new module invents **none**. It is wrong on **11** lease values across all 73 runs, all marked **"medium"**: typed or OCR'd values are "medium"; only values read from form fields are "high".
- The 11 are almost all OCR punctuation noise on scans ("1450. Maple Ridge Drive", "enata Quillfeather", "Cedar Hollow. Housing LP").

### By document type (`affordable` engine)

Lease right/stated · program right/total:

| Doc type | clean | acroform | scan | holdout | holdout_scan |
|---|---|---|---|---|---|
| RFTA (52517) | 6/6 · 10/10 | 6/6 · 10/10 | 6/6 · 10/10 | 6/6 · 10/10 | 5/6 · 10/10 |
| HAP contracts (52641 ×2, 52530A/B) | 16/18 · 47/54 | 4/6 · 22/26 | 15/18 · 40/54 | 16/18 · 47/54 | 11/18 · 39/54 |
| PBRA certification (50059) | 4/4 · 37/38 | 4/4 · 36/38 | 4/4 · 37/38 | 4/4 · 37/38 | 2/4 · 21/38 |
| PBRA voucher (52670) | none stated · 19/19 | none stated · 19/19 | none stated · 18/19 | none stated · 19/19 | none stated · 17/19 |
| HUD LIHTC tenant data (52697) | 1/1 · 23/24 | n/a | 1/1 · 21/24 | 1/1 · 20/24 | 0/1 · 19/24 |
| LIHTC TICs (SC, LA, NJ, IL) | 12/12 · 129/140 | 3/3 · 34/35 | 11/12 · 119/140 | 12/12 · 126/140 | 4/12 · 56/140 |
| IRS 8609 / 8823 / 8586 | 5/5 · 39/40 | 5/5 · 39/40 | 4/5 · 36/40 | 5/5 · 38/40 | 4/5 · 29/40 |
| CHFA LURA (partial) | 1/2 · 7/14 | n/a | 1/2 · 7/14 | 1/2 · 6/14 | 1/2 · 5/14 |

**The ceiling.** 13 of the 339 program values are dates of birth, which the module refuses to extract (PII). So the maximum is 96.2%, and clean's 92% is 95% of what's allowed.

### Worst fields after the fixes

| Field | Misses | Why |
|---|---|---|
| Dates of birth (TIC members, 50059, 52697) | every time | **By design.** DOB is never extracted until the PII masking work lands |
| PBV `contract_number`, `project`, and so `property_address` | 10/10 | Part 1 of the 52530A/B has no printed field for them (Exhibit A, a separate attachment, lists units). The samples typed them in the margin |
| LURA owner, project, dates, contacts, signers | 7 of 14 fields | Prose with inline blanks; label anchors don't fit. This is the AI route's job |
| 52641 `payee_address` | 8/8 | Returns street *and* city; the answer key holds only the street line. A key choice, not a reading error |
| 8609 `building_name` | 5/10 | Returns "Cedar Hollow Apartments (Building 1)", which the form shows; the key has the shorter name |
| PBV `initial_term` | 4/10 | Returns "years" without the number on some copies |
| Scans: short numbers (initial HAP 712 → 742, 0 → 9) | a few per scan | OCR misreads; the module doesn't check plausibility yet |

### What's left (ordered)

1. **Holdout scans: 56–58% lease and program.**
   - Form detection uses exact text, so an OCR-garbled title (TENANT INCOME CERTIFICATION in small serif type) means the form isn't recognised. Two TICs at 200 dpi.
   - Fix: fuzzy detection on OCR pages, and OCR at the scan's native image resolution instead of re-rendering at a fixed dpi.
2. **OCR punctuation noise in names and addresses** ("1450. Maple"). Strip a period glued between a number and a word, and a lone leading or trailing period.
3. **Nothing calls this module yet.** Wiring it into uploads is a separate change for `api.py` and `document_extractor`, files another session was editing tonight. It goes behind `AFFORDABLE_FORMS_MODE`.
4. **The AI engine is still unmeasured** (billing). Once credits are added, the useful comparison is AI vs this module on the LURA and the holdout scans, the two places the module is weakest.
