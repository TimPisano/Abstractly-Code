# Section 8 sample portfolio

What **Load Sample Deal** loads when `SECTION8_MODE` is on (and what the
demo deployment seeds when both `DEMO_MODE` and `SECTION8_MODE` are on).
With the flag off, Maple Ridge (`../demo_deal/`) loads exactly as before.

- `precomputed_section8_sample.json` is what the loader reads (`app/sample_deal.py:load_section8_sample`).
- `capture_section8_sample.py` builds that JSON. Never hand-edit the JSON.

Everything is fictional. The source documents are the graded fixture set in
`backend/tests/fixtures/section8/`, whose `ANSWER_KEY.md` lists every
planted error.

## What's in it

| Part | Source |
|---|---|
| 10 voucher leases, 5 HAP contracts, both October rent rolls (Juniper Row AppFolio CSV, Bellmont Terrace RealPage CSV) as documents tagged `Sample` | The fixture files, run through the **real** `POST /leases` and `POST /leases/import-rent-roll` routes on a throwaway database with the regex engine. |
| 1 PHA, 2 properties, 32 units, 30 tenancies (29 current + unit 112's past tenancy), 13 HAP contract rows (3 HCV; the PBV contract as one row per Exhibit A unit; the PBRA contract as one row per unit), and document-to-unit links | The fixture generator's own data. Tenancy amounts are what the October rent rolls **show**, planted errors included, so later checks (T3/T5) have real problems to find. |

The PHA registers and inspection reports are not loaded yet; their
tables don't exist until T4 (`hap_payments`) and T6 (`inspections`).
Those tasks should extend this capture.

## Re-capturing

Run this whenever the fixtures or the extraction/import code change:

```bash
cd backend && venv/bin/python benchmark_data/section8_sample/capture_section8_sample.py
venv/bin/python tests/test_section8_sample_data.py
```

`test_section8_sample_data.py` fails if any fixture file's sha256 no
longer matches what the capture recorded.

**Capture history:**

- **2026-10-13: re-captured after `qa/overnight-gauntlet` (P2) merged** (`b63927d`). RealPage
  `Bldg/Unit` is now read, so Bellmont rows carry their unit.
- **Still to re-capture: after `feature/lease-intelligence` (P1) merges.** On `main` today the regex
  extractor splits each Section 8 lease PDF (lease + addendum + acknowledgment) into three
  "leases" and reads the tenant from the utilities table ("Gas"). P1 fixes both.

`dropped_rows` in the JSON lists importer rows that matched no unit and
were left out. Today that's one row: the AppFolio **Total** row, which the
importer reads as a tenant called "16 occupied / 18 units". That's an
importer bug, tracked in TASKS.md, and it is still present on `main` after the
gauntlet merge.
