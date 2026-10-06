# Lease extraction report: `feature/lease-intelligence`

Last run: 2026-10-05, branch tip `d573a2e`. Engine: the **regex engine**
(`FieldExtractor`). It is what every deployment runs today, because there is no
funded Anthropic key. The AI engine was changed but **not measured** (see
"Not verified").

All leases here are synthetic and fictional. No customer data was used.

## Headline

| Corpus | What it is | Before (main) | After |
|---|---|---|---|
| Own (`generate.py`, 48 PDFs) | Written alongside the parser | 51.1% (of 675 checks) | **100%** (771 checks) |
| Held-out #1 (`holdout.py`, 30 PDFs) | Written by a separate agent that never saw the parser; I then tuned against it | 55.6% | **99.6%** |
| **Blind #2** (`holdout2.py`, 30 PDFs) | Written by another separate agent, measured **before any tuning** | — | **87.6% blind** → 95.8% after fixes |
| SEC commercial benchmark (12 real office/retail leases) | Regression guard for commercial | 36.7% | **40.0%** (no lease/field got worse) |

**The honest number for unseen multifamily leases is the blind 87.6%.**
Everything after that was tuned against what the blind set exposed. A third
blind set is the way to re-measure.

On all three corpora, **zero values are "high confidence" and wrong**. On the
blind set before tuning there were 11; the remaining errors are misses or
are flagged medium/low.

## What changed, in plain English

1. **One lease stays one lease.**
   - A Section 8 lease with its HUD Tenancy Addendum and HAP contract was
     being stored as **2–3 separate leases**. Headings like "Tenant Rent:
     $312" and "(To be attached to Tenant Lease)" were read as tenants
     literally named "Rent" and "Lease".
   - Renewal agreements and co-residents' signature lines caused the same
     kind of split.
   - Now addenda, amendments, renewals, HAP contracts, recertifications and
     letters attach to the lease before them. Truly separate leases in one
     PDF still split.
2. **Apartment wording is understood.** The parser now reads:
   - parties labelled "Resident(s)", "Owner", "Lessor/Lessee" and
     "Participant"
   - `hereinafter called "Landlord"`, `X, as Landlord`, an unquoted
     `(Owner)`, and `("we")` / `("you")`
   - co-residents: the first-named resident is the tenant, and everyone
     else is kept and shown on the lease page
   - term ranges ("Term: 1 April 2026 to 31 March 2027", "Period: …",
     "runs … to …") and "ends at 11:59 p.m. on …"
   - rent labels in tables, "$975 a month", rent written only in words,
     and "agree to pay Lessor $X monthly"
   - street addresses without "located at", with the **unit kept in the
     address**
3. **The right rent.**
   - It is the original lease's rent for the apartment.
   - It is never pet rent, a parking fee, a "Total Monthly Rent" that
     includes fees, a concession, or a later renewal's rent.
   - For Section 8 it is the **contract rent**, never the tenant's portion.
4. **Scanned pages inside a typed PDF are now read.**
   - Before, if even one page was a scan (a faxed-back signed HUD addendum,
     say), the whole lease came back "OCR needed" with no fields at all.
   - Now only those pages are OCR'd. This runs inside the upload request, so
     it is bounded by **10 pages and 60 seconds**, and skipped when
     tesseract/poppler aren't installed.
   - Pages beyond the budget get the old "OCR needed" handling, never
     anything worse.
5. **New multifamily fields, behind `LEASE_MULTIFAMILY_FIELDS` (off by default).**
   - `unit_number`
   - `pet_charges` (monthly / one-time fee / deposit)
   - `parking_charges`
   - `utility_charges`: RUBS / bill-back utilities, plus flat monthly fees
     such as valet trash and pest control
   - `section_8`: PHA name, contract rent, tenant rent, HAP, utility
     allowance
   - `lease_changes`: renewals, amendments, PHA rent-change notices and
     recertifications in the file
   - `current_rent_amount` / `current_lease_end_date`: after the latest
     change
   - Every value carries a page citation.
   - If a Section 8 split doesn't add up (tenant rent + HAP ≠ contract
     rent), it is **flagged at medium confidence, never "fixed"**.
   - A failure in this new code can never take the core fields down with
     it.
6. **AI engine prompt v3** (`ai_extraction.py`):
   - The prompt is now residential- and Section 8-aware.
   - The rent rule is the same as above.
   - `termination_options` is added, so both engines return the same keys.
   - With the flag on, the model is asked for the new fields. Their
     numbers are parsed from the model's verbatim quote, never from the
     model's own arithmetic.
7. **Lease detail page: a read-only "Multifamily & Section 8" group**, shown
   only when those fields exist (flag on), plus an "All residents:" line.
8. **Extraction time stays linear in document size.** Review found that a
   long unbroken token (OCR garbage, a base64 blob) made one new
   party-name pattern quadratic: **132 s on a 20,000-character token**,
   past the 120 s worker timeout. Two older digit-run patterns (cure
   period, square feet; ~6 s on 20,000 digits) had the same shape. All are
   anchored now, so every adversarial token in
   `test_lease_extraction_performance.py` runs in under 0.5 s.

## Per-field: blind set #2 before tuning → after

| Field | Blind (before) | After |
|---|---|---|
| tenant / landlord | 90.0 / 80.0 | 100 / 100 |
| rent_amount | 90.0 | 93.3 |
| start / end date | 86.7 / 86.7 | 96.7 / 96.7 |
| unit_number | 90.0 | 100 |
| lease_count (no false splits) | 96.7 | 100 |
| lease_changes.count | 83.3 | 100 |
| Section 8 tenant rent / HAP | 60 / 60 | 80 / 80 |
| utility flat fees | 20 | 100 |
| concession present | 50 | 50 (see hand-offs) |

The remaining blind misses are listed in `tools/lease_corpus/results/holdout2_out.json`
(regenerate with the command below). They fall into three groups:

- **B030:** a coffee-stained scan that OCR reads as "Rent Neds 425.00". This
  is honestly unreadable.
- **B029:** a scanned HUD addendum table that OCR reads amounts-before-labels.
  It's a known limit; a Section 8 lease that only says "Rent: see HAP
  contract" relies on that page.
- **Concessions** worded as "6 weeks free rent" or "credit $300 against the
  first full month's rent". `concessions.py` is outside this branch (see
  hand-offs).

## How to re-run

```bash
cd backend && source venv/bin/activate
python tools/lease_corpus/run_corpus.py --regenerate --failures              # own corpus
python tools/lease_corpus/holdout2.py --out tools/lease_corpus/holdout2_out
python tools/lease_corpus/run_corpus.py --corpus tools/lease_corpus/holdout2_out --failures
LEASE_EXTRACTION_ENGINE=regex PYTHONPATH=. python benchmark_data/run_accuracy_benchmark.py   # commercial guard
python tests/test_lease_corpus.py   # the floors the suite enforces (all three corpora)
```

## Tests added (all registered in `run_all_tests.py`; Anthropic always mocked)

| File | What it covers |
|---|---|
| `test_lease_mf_parties.py` | Splits, co-residents, labels and lead-ins |
| `test_lease_mf_terms.py` | Rent and dates |
| `test_lease_mf_phrasings.py` | Held-out and blind-set wording |
| `test_lease_mf_charges.py` | New fields, Section 8, changes, the flag, crash isolation |
| `test_lease_mixed_scan.py` | Per-page OCR: mocked, plus a real round-trip when tesseract is present |
| `test_lease_ai_multifamily.py` | Prompt v3 and the AI multifamily path (mocked client) |
| `test_lease_corpus.py` | Accuracy floors on all three corpora, and no high-confidence wrong values |
| `test_lease_extraction_performance.py` | 20,000-character adversarial tokens each extract in under 3 s (132 s before the fix) |

Every bug-fix test was checked to fail on the commit before its fix. Full
suite: **90/90** files pass.

## Not verified

- **The AI engine's accuracy.**
  - There is no funded key, and CLAUDE.md rule 8 requires asking before
    any real API run.
  - Prompt v3 and the multifamily AI path are tested only with a mocked
    client.
  - Before turning AI extraction on for testers, run the three corpora with
    `LEASE_EXTRACTION_ENGINE=ai` (small cost, ~108 leases).
- **Real leases.** All corpora are synthetic, written by agents with
  realistic but invented wording. Real scans are messier than these.
- **Lease detail UI with the flag on against a deployed backend.**
  - It was checked only locally: headless at 1440/768/375 with no console
    errors.
  - The screenshots are in this session's scratchpad (`ui/png/`, and the
    ui-checker's `ui-checker/`, 48 PNGs including flag-off) and are not in
    the repo.

## Hand-offs (not done here: other sessions' files or out of scope)

1. **Deal Mismatch Report should use the new fields** (`deal_mismatch.py`,
   gauntlet's file):
   - Compare the rent roll to `current_rent_amount` (after renewals) as
     well as the original rent.
   - Use `section_8.details` so a rent roll that lists only the tenant
     portion isn't a false $X/mo "rent mismatch".
   - Price pet, parking and utility charges against the rent roll's
     "Other Charges".
2. **Address matching is exact-string** (`portfolio._normalize_address`).
   "Apt 204" vs the rent roll's "Suite 204" won't match. Normalising
   Apt/Unit/Suite/# (or matching on `unit_number`) is the fix.
3. **Concession phrasings** "N weeks free" and "credit $X against the first
   month's rent" are missed by `concessions.py`.
4. **Risk flags are commercial-centric.** "No insurance / no default-cure
   clause found" fires on ordinary apartment leases (`risk_analysis.py`).
5. **Editing the new fields.** They are read-only because the
   PATCH/verify routes and the exports use `portfolio.FIELD_NAMES`.
6. **Pre-existing 375px overflow on the lease detail page** (found by the
   ui-checker, also present with the flag off and on `main`'s markup). A long
   unbroken filename in the subtitle and history ("L031_section8_with_charges.pdf")
   makes `.detail-main` 424px wide on a 375px phone. Fix: `overflow-wrap:
   anywhere` / `min-width: 0` on those elements.
