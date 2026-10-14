# Plan: qa/section8-fixtures

## Goal

A realistic, fully fictional Section 8 test set that future Section 8
features (rent-roll split checks, HAP reconciliation, recert and
inspection tracking) can be built and graded against. It covers
10 voucher leases with HUD tenancy addenda, 5 HAP contracts, 5 rent rolls,
3 PHA HAP payment registers and 3 HQS/NSPIRE inspection reports. Every
deliberately planted error is listed in `ANSWER_KEY.md` with the file,
the location, the dollar impact where one exists, and the exact flag a
correct checker should raise. This branch adds **data only**: no app
code changes.

## Prior art (searches run 2026-10-11)

- `TASKS.md`: section 8 / s8 / HAP / voucher / fixture.
- `git log --all -i --grep` "section 8|s8|HAP|voucher".
- `git grep` of `rent_roll_import.py` on `main` and `origin/qa/overnight-gauntlet`.
- `git stash list`: nothing relevant.

What turned up:

| Where | What | How this plan relates |
|---|---|---|
| `feature/s8-demo-files` (unmerged) | Oak Hollow: 1 PBRA property, 10 tenant-file PDFs (income certs), 40-unit rent roll, 10 planted **certification** errors, generator `generate_s8_demo.py` | **Reuse its approach**: one deterministic generator is the source of truth, `rl_config.invariant`, reportlab + openpyxl, totals computed and never hand-typed, a fictional-data footer. **No overlap in content**: Oak Hollow is about income certifications. This set is about leases, addenda, HAP contracts, PHA payments and inspections. New names and properties avoid any collision. |
| `feature/lease-intelligence` (`backend/tools/lease_corpus/generate.py`) | Synthetic Section 8 leases used to grade extraction accuracy | Different purpose (per-field extraction grading). Not duplicated here: these leases come as a deal set with cross-document errors. |
| `qa/overnight-gauntlet` `rent_roll_import.py` | Recognises `tenant portion / tenant rent / tenant share` + `HAP` columns; contract rent = portion + HAP | Rent-roll headers use those real PMS spellings, so the importer on that branch can read these files today. |
| `pivot/section8` (plan only, in progress) | Pivot feature list | This set gives that plan's features something to test against. No file overlap. |

## Approach

1. One generator script, `generate_section8_fixtures.py`, inside the fixture folder. It holds all scenario data as Python dicts, with every amount computed from those dicts, and writes every file deterministically (fixed seed, fixed "as-of" review date of **2026-10-01**, invariant PDFs).
2. **Scenario:** a fictional sponsor buying two properties. The PHA is the fictional "Harrow County Housing Authority".
   - **Juniper Row**: scattered Housing Choice Voucher (HCV) tenants, with tenant-based HAP contracts on form-style HUD-52641.
   - **Bellmont Terrace**: project-based units. One Project-Based Voucher (PBV) HAP contract (HUD-52530A style) and one PBRA-style multifamily HAP contract.
   - Fictional names, invented street names and towns. Phone numbers use 555-01xx and emails use `.test` domains, so nothing can match a real person or address.
3. **Documents:**
   - **10 voucher leases** (PDF, text-based, 4–7 pages): owner lease plus the HUD Tenancy Addendum (Part C language paraphrased and labelled "simplified model, not an official HUD form"), with signatures and dates. Varied formats: 2 with a scanned-look image page so the OCR path is exercised, 1 with the addendum before the lease body, and 1 with a renewal/rent-increase notice.
   - **5 HAP contracts** (PDF): 3 HCV tenant-based (one per unit, Parts A–C), 1 PBV with an Exhibit A unit schedule, and 1 PBRA with a contract rent schedule and an expiration date.
   - **5 rent rolls**: 3 CSV and 2 XLSX, in different PMS-style layouts (AppFolio, Yardi, RealPage, Buildium, Excel export). Each splits Contract Rent / Tenant Rent / HAP using different header spellings. One XLSX has a title block and subtotal rows.
   - **3 PHA HAP payment registers** for Aug, Sep and Oct 2026, each as a CSV plus a matching PDF statement. They include shortfalls, an abatement line, a prorated move-in and a one-time HAP adjustment.
   - **3 inspection reports** (PDF): 1 HQS (HCV unit), 1 NSPIRE (PBV) and 1 NSPIRE (PBRA). Each has deficiencies (life-threatening/24h, 30-day), cure deadlines and reinspection dates. One reinspection passes, one fails (which leads to an abatement), and one is overdue with no result.
4. **Planted errors (target 20–25, each with an ID like `S8-01`)**, covering at least:
   - Tenant share entered as full rent: rent-roll contract rent equals tenant rent, HAP blank or zero.
   - HAP mismatch: rent-roll HAP ≠ HAP contract ≠ PHA register.
   - Split doesn't sum: tenant + HAP ≠ contract rent.
   - Lease rent ≠ HAP contract rent to owner. A side-payment case where the lease charges more than the contract allows.
   - Expired HAP contract with rent and HAP still being billed.
   - Missed annual recertification: reexam date has passed, tenant share and HAP unchanged, and the PHA register shows the HAP stopped or changed.
   - Register shortfall: PHA paid less than contract HAP, with no adjustment code.
   - Abatement after a failed reinspection, while the rent roll still books full HAP as collectible.
   - Overdue reinspection with no result. Life-threatening deficiency not cured within 24 hours.
   - HAP still received after move-out (owner owes repayment).
   - Rent increase without the PHA-approved amendment or the 60-day notice.
   - Utility responsibility differs between the lease and the HAP contract.
   - Lease term starts before the HAP contract effective date.
   - At least 3 **clean control units** that must raise no flag.
5. **`ANSWER_KEY.md`** has one row per error: ID, category, file(s) + page/row, what's wrong, expected flag (a proposed snake_case code such as `s8_tenant_share_as_contract_rent`), severity, monthly/annual dollar impact and the rule reference (paraphrased, not practitioner-checked). It also includes the clean-control list and a short "how to regenerate" section. A machine-readable `answer_key.json` is generated from the same dicts so a future grader can use it.
6. **Self-check test** `backend/tests/test_section8_fixtures.py`, registered in `run_all_tests.py`. It needs no network and no Anthropic. It checks the following:
   - The generator is deterministic: a regenerate produces byte-identical files.
   - Every answer-key row points at a file and row/page that exists and shows the planted value.
   - Clean rows really do sum.
   - Every text PDF is readable by the app's own `pdf_extractor`, used read-only.
   - No real-looking SSN, phone or email patterns appear.

## Files to change

- New: `backend/tests/fixtures/section8/**` (generator, generated files, `ANSWER_KEY.md`, `answer_key.json`, `README.md`).
- New: `backend/tests/test_section8_fixtures.py`.
- Edit: `backend/tests/run_all_tests.py` (one line to register the test).
- New: this plan.

## Files not to touch

All of `backend/app/**`, `frontend/**`, `render.yaml`, and other branches' fixtures (`benchmark_data/s8_demo`, `tools/lease_corpus`).

## Team isolation & roles

N/A. No routes, queries or app code.

## Feature flag

N/A. Data and a test only. Nothing in the app reads these files.

## Verification

- Run the full suite in this worktree and quote the result.
- Run the new self-check test.
- Render 2–3 PDF pages to PNG headlessly and look at them to confirm the documents look realistic.
- Open each XLSX and CSV and spot-check it.
- No UI changes, so no screenshots.

## Out of scope

- Any checker or flag implementation. The flag codes in the answer key are proposals for the future builder.
- Wiring the set into the app or the demo deployment.
- Real HUD form reproduction: these are paraphrased models.
- Income/certification errors, which Oak Hollow already covers.

## Open questions

1. **Location.** You wrote `tests/fixtures/section8/`. The repo has no root `tests/`; every test and fixture lives under `backend/tests/`. I plan `backend/tests/fixtures/section8/` so the tests and runner find it naturally. Say so if you want a literal root-level `tests/`.
2. **Self-check test.** It touches `run_all_tests.py`, which is test infra, not app code. Okay?
