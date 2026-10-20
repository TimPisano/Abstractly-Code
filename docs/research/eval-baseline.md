# Affordable-Housing Extraction: Baseline

**Date:** 2026-10-19 · **Branch:** `research/affordable-housing` · **Engine measured:** regex (the default; offline) · **AI engine:** not run (see "Not measured")
**Harness:** [`tests/eval/affordable/`](../../tests/eval/affordable/README.md) · raw results: [`results/regex.json`](../../tests/eval/affordable/results/regex.json)

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

- **The AI engine wasn't run.** It sends each document to the Anthropic API, and CLAUDE.md says to ask before live API calls. It's likely to do far better on forms, but its schema has the same 15 lease fields, so program fields would still be 0%. To run it (clean only, about 16 calls):
  `ANTHROPIC_API_KEY=… backend/venv/bin/python -I tests/eval/affordable/run_eval.py --engine ai --variants clean`
- **Synthetic fills.** Values are typed in Helvetica: no handwriting, no stamps, no real-world mess. Scans are simulated, not from a real scanner. One household per form.
- **Answer keys are our own.** The mapping of form fields to lease fields is a judgment call; for example, TIC tenant rent counts as `rent_amount`, and move-in date doesn't count as lease start. Change the key and rerun if you disagree.
- **Matcher looseness.**
  - Text-layer checks for small integers (bedrooms "2", unit counts) can false-positive.
  - The app's address and tenant matcher accepts substrings; that's how the five scan hits score.
  - $0 amounts were left out of keys.
- **Edition and form-identity caveats.** The HUD-50059 is the 2014 edition (expired 2017; layout only). The IHDA TIC is **Illinois** (joint with Chicago and Cook County), not Indiana; eval-docs.md is corrected.
- **Unchanged areas.** Nothing in `backend/` was modified. No program-field extractor exists yet, so this is the "before" picture.
