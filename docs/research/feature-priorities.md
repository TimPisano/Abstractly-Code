# Affordable Housing: Top 10 Features for Abstractly

**Date:** 2026-10-19 · **Status:** Research only, no code. Scores are judgment calls drawn from the companion docs, **not** from customer interviews. Treat the ranking as a hypothesis to test with the interview bank in [section8.md](./section8.md) §8.

Companion docs: [section8-workflows.md](./section8-workflows.md) · [lihtc-workflows.md](./lihtc-workflows.md) · [competitors.md](./competitors.md) · [eval-docs.md](./eval-docs.md)

---

## How the scores work

Each feature gets 1 to 5 on four axes. Higher is always better for us.

| Axis | 5 means | 1 means |
|---|---|---|
| **Pain** | Errors cost real money (lost HAP, repayment, credit loss or recapture, contract loss) | Annoyance only |
| **Frequency** | Monthly or every move-in | Once every few years |
| **Build ease** | Mostly reuses what Abstractly already has: PDF/table extraction, page citations, rent roll import and column matching, the deal-mismatch dollar-impact pattern, the S8 data model, `hud_data` | New document families, new PII handling, new rule engines |
| **Gap** | Incumbents don't do it, or only as a paid human service | Every PMS already does it well |

**Total = sum (max 20).** Ties are broken by fit with Abstractly's current CRE customers (acquisitions and asset management), because that is who we can sell to first.

**What "incumbents" means here.** The systems of record (Yardi Voyager / Breeze Premier, RealPage OneSite Affordable, MRI Bostonpost, Entrata, ResMan, AppFolio) run certifications, TRACS and limits *inside their own data*. Two things they do poorly, per [competitors.md](./competitors.md): checking their records against the **source documents**, and checking **across systems** (portfolios on several PMSs, or a target's files during an acquisition). AI entrants (HousingIntellect, EliseAI) are going after TIC/50059-vs-verification review, so that area is now contested.

---

## Ranking

| # | Feature | Program | Pain | Freq | Build | Gap | **Total** | Covered by S8 branches? |
|---|---|---|---|---|---|---|---|---|
| 1 | Rent roll ↔ lease ↔ HAP contract ↔ PHA notice tie-out | S8 (HCV/PBV/PBRA) | 4 | 5 | 5 | 4 | **18** | **Partly built** |
| 2 | HAP payment reconciliation (HCV/PBV landlords) | S8 HCV/PBV | 4 | 5 | 4 | 4 | **17** | Plan + fixtures only |
| 3 | LIHTC rent and income limit check on the rent roll | LIHTC | 4 | 4 | 4 | 3 | **15** | Limit math built (`hud_data`) |
| 4 | Affordable acquisition due diligence report | Both | 4 | 2 | 4 | 5 | **15** | CRE pipeline + S8 pieces |
| 5 | 50059 arithmetic and HUD-52670 voucher tie-out | S8 PBRA | 3 | 5 | 4 | 2 | **14** | No (demo 50059s only) |
| 6 | Utility allowance check against the PHA/agency schedule | Both | 3 | 3 | 3 | 4 | **13** | No |
| 7 | Tenant file audit: certification vs supporting documents | Both | 5 | 4 | 2 | 2 | **13** | Demo data only (Oak Hollow E1–E10) |
| 8 | Deadline calendar: HAP contract renewals, rent increases, recerts | Both | 4 | 3 | 4 | 2 | **13** | Planned (T7, T7b, T8) |
| 9 | Inspection and abatement tracker | S8 (LIHTC later) | 4 | 3 | 3 | 2 | **12** | Plan + fixtures only (T6) |
| 10 | Set-aside, income averaging and next-available-unit monitor | LIHTC | 5 | 2 | 3 | 2 | **12** | Limit math only |

**Tie-breaks.** #3 is ahead of #4 because it is a component of #4 and ships sooner. #6 is ahead of #7 and #8 because its gap is the widest (there is no national UA dataset; see [section8.md](./section8.md) §6). #7 is ahead of #8 despite the same total because its pain is the highest on the list.

**Not in the top 10, on purpose:**
- **HOTMA recalculation check (before Jan 1, 2027).** Real, but a closing window. HUD set the multifamily full-compliance date at Jan 1, 2027 ([HUD HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma)), and every incumbent has to ship it. By the time we built it, it would be table stakes. Fold the HOTMA rules into #5 and #7 instead.
- **Layered-deal rule conflicts.** Every big platform advertises it ([competitors.md](./competitors.md), "Not a strong gap"). Keep it as a check inside #3 and #10, not a product.
- **TRACS submission.** Needs HUD secure-systems access and a vendor path. That's a different business ([competitors.md](./competitors.md), "Sales cycle and integration realities").

---

## The features

### 1. Rent roll ↔ lease ↔ HAP contract ↔ PHA notice tie-out (18)

- **Problem.** On a voucher unit the rent roll often carries the tenant share, not the contract rent, or keeps a rent that a PHA change notice replaced. Every month the owner under-bills, or reports wrong income to a lender. The core identity is **contract rent = tenant share + HAP**, per unit, as of a date. For PBRA the same rent must also match the HAP contract rent schedule and the 50059 ([section8-workflows.md](./section8-workflows.md), "Where document extraction / validation helps" #1).
- **Reads.** Rent roll (CSV/XLSX/PDF), leases + HUD tenancy addendum, HAP contracts (HUD-52641 for HCV; the HUD-52530 series for PBV; PBRA contract rent exhibit), PHA rent/tenant-share change notices.
- **Outputs.** Per-unit findings with dollar impact per month and annualized, each with page citations: tenant share booked as rent; contract rent mismatch (roll vs lease vs HAP contract); tenant share or HAP mismatch vs the latest PHA notice; voucher unit with no HAP contract on file; lease dated before the HAP contract. Exports in the existing PDF/XLSX report format.
- **Why it ranks first.** It is the CRE deal-mismatch check Abstractly already sells, pointed at three new document types. The monthly dollar error is easy to show in a demo.
- **S8 branch coverage: partly built.**
  - `fix/section8-tenant-share`: built and reviewed. Rent roll import keeps the stated contract rent and validates contract rent = tenant share + HAP per row ($1 tolerance). Waiting on merge order.
  - `feature/lease-intelligence`: lease extraction uses contract rent, not tenant share, on Section 8 leases.
  - `feature/s8-data-model` (T1): built. Tenancies and HAP contracts are stored per unit.
  - **Not built:** HAP contract and PHA notice extraction (T2) and the cross-document detectors (T3). Fixtures exist on `qa/section8-fixtures` (HCV, PBV and PBRA HAP contracts, leases, Buildium and RealPage rolls, with an answer key).

### 2. HAP payment reconciliation for HCV/PBV landlords (17)

- **Problem.** HAP is most of the rent on a voucher unit. Short payments, missed months, abatements and HAP received after move-out (which must be returned) hide in PHA remittance reports, one per PHA, in different layouts. PHA landlord portals *show* payment history but don't reconcile it against what the landlord is owed ([HUD HCV landlord webinar](https://www.hud.gov/sites/dfiles/PIH/documents/HCV_Landlord_Webinar3_Technology.pdf), via [competitors.md](./competitors.md) gap 4).
- **Reads.** PHA HAP payment registers and remittances (CSV, XLSX, PDF tables), HAP contracts and PHA notices (expected HAP), rent roll (move-in and move-out dates), inspection/abatement notices.
- **Outputs.** Expected vs received HAP per unit-month, prorated for move-in and move-out. Findings: shortfall, overpayment, missing payment, abatement, HAP after move-out, unmatched payment, a recurring short pattern by PHA. Rollups by PHA and month, with dollar totals and an export to send to the PHA.
- **Gap evidence.** Yardi Breeze Premier is the only affordable product with public pricing, at $3/unit/month with a **$400/month minimum** ([Yardi Breeze](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/)). That is a lot for a 20–60 voucher-unit landlord. ExactEstate claims HAP reconciliation but sells to multi-program operators. **Demand is unproven.** Interview small HCV landlords before building T5.
- **S8 branch coverage: plan and fixtures only.** `feature/s8-hap-payment-import` (T4) has an approved-pending plan to parse registers into `hap_payments`. Reconciliation (T5) is not started. `qa/section8-fixtures` has three months of synthetic PHA registers (CSV + PDF). The parsing can reuse `rent_roll_import` column matching and `rent_roll_table_extract`.

### 3. LIHTC rent and income limit check on the rent roll (15)

- **Problem.** Gross rent (tenant rent + utility allowance + mandatory fees) over the bedroom rent cap, or a household over the income limit at move-in, is a Form 8823 finding. It can cost the unit its credit for the year ([lihtc-workflows.md](./lihtc-workflows.md) §2, §9 checks 2–3). Limits change every year (MTSP), vary by county and AMI tier, and depend on placed-in-service date and hold-harmless rules.
- **Reads.** Rent roll, UA schedule (or UA column), unit designation list / LURA (AMI tier per unit), MTSP limits (already loaded by `hud_data`), and TICs if available (household size, income).
- **Outputs.** Per-unit status: gross rent vs cap for its bedroom count and AMI tier for the right year; income vs limit for actual household size (when TICs are present); units missing an AMI designation. For income-averaging projects, the average designated AMI vs the 60% cap ([§42(g)(1)(C)](https://www.law.cornell.edu/uscode/text/26/42)). Every flag cites the limit table row and the rule. Anything state-specific is labelled "Verify with your state agency."
- **Why it's cheap.** It needs no new document family beyond the rent roll; the limit math exists. It's the fastest way to say "Abstractly does LIHTC" truthfully.
- **Caveats to build in.** The UA change takes effect 90 days after the change, per [26 CFR 1.42-10(c)(1)](https://www.law.cornell.edu/cfr/text/26/1.42-10), not 45. The 45-day window applies to new MTSP limits, and its source is secondary ([lihtc-workflows.md](./lihtc-workflows.md) §2.1). Hold-harmless and placed-in-service year rules vary; let the user set them.
- **S8 branch coverage: limit math built.** `feature/s8-hud-data` (built, reviewed) has `lihtc_income_limit(limits, household_size, ami_pct)` and `lihtc_rent_limit(limits, bedrooms, ami_pct)` over MTSP data, with a 2025 MTSP fixture. Nothing else is LIHTC-specific.

### 4. Affordable acquisition due diligence report (15)

- **Problem.** A CRE firm buying an affordable property inherits its compliance exposure: an expiring HAP contract, rents over LIHTC caps, a set-aside at risk, open 8823s or MOR findings, recapture exposure that the GP indemnified to the investor ([lihtc-workflows.md](./lihtc-workflows.md) §3.3; [section8-workflows.md](./section8-workflows.md) §1, §7). Today that review is done by consultants.
- **Reads.** The data room: rent roll, HAP contracts and renewal letters, LURA / regulatory agreement, recent MOR (HUD-9834) and state monitoring letters, Forms 8823, REAC/NSPIRE scores, UA schedule, and a sample of tenant files.
- **Outputs.** A compliance exposure memo in the existing investment-memo format: HAP contract term and renewal or opt-out dates; rent roll vs HAP contract rents (#1); rents vs LIHTC caps (#3); set-aside status (#10); open findings with dates; years remaining in the compliance and extended use periods. Dollar impact where computable, with citations.
- **Gap evidence.** No product marketed for affordable acquisition diligence was found. The evidence for demand is weak ([competitors.md](./competitors.md) gap 5). It ranks this high because it is the **best fit with who already buys Abstractly**, and it bundles #1, #3, #6 and #10 rather than needing new engines.
- **S8 branch coverage: the pieces.** The CRE deal pipeline (deal mismatch, investment memo, exports) is on `main`. #1 and #3 components as above. Nothing affordable-specific is in the memo yet.

### 5. 50059 arithmetic and HUD-52670 voucher tie-out (PBRA) (14)

- **Problem.** The MOR tests rent calculations, and each monthly voucher has to tie to the certifications behind it. The identities: Gross Rent = Contract Rent + UA; Assistance Payment = Gross Rent − TTP; Tenant Rent = Contract Rent − HAP; and a Utility Reimbursement when UA exceeds TTP. The sum of per-unit assistance must equal the HUD-52670 total ([section8-workflows.md](./section8-workflows.md) §3c, §4, checks #2–#3).
- **Reads.** HUD-50059 / 50059-A, HUD-52670 / 52670-A, rent roll, HAP contract rent schedule.
- **Outputs.** Per-certification identity breaks; voucher total vs the sum of current certifications; contract rent on the 50059 vs the HAP contract vs the roll; stale certifications (effective date + 12 months passed).
- **Why the gap score is low.** A PMS that *generates* the 50059 and voucher keeps them consistent with each other. The value is when files come from several systems, paper or a seller (pre-MOR audit, acquisition). It's a strong component of #4 and #7, weak on its own.
- **Caveat.** Field numbering differs by 50059 revision, and the TRACS 203A MAT User Guide controls where it conflicts with the form instructions ([section8-workflows.md](./section8-workflows.md) §3c). Build against the current revision and an eval set (see [eval-docs.md](./eval-docs.md)).
- **S8 branch coverage: none.** `feature/s8-demo-files` has 10 synthetic Oak Hollow tenant files with 50059s, but no extraction or checks.

### 6. Utility allowance check against the PHA/agency schedule (13)

- **Problem.** A wrong UA makes tenant rent and HAP wrong every month, in both programs. HCV schedules must be revised when a utility rate changes by 10% or more ([24 CFR 982.517](https://www.law.cornell.edu/cfr/text/24/982.517)). LIHTC owners must review the UA yearly, and new UAs apply 90 days after the change ([26 CFR 1.42-10(c)](https://www.law.cornell.edu/cfr/text/26/1.42-10)). PBRA uses owner UA analyses under Notice H 2015-04 (secondary source, [section8-workflows.md](./section8-workflows.md) §6b).
- **Reads.** PHA UA schedules (HUD-52667 layout: dense bedroom-by-utility PDF tables, a good extraction test per [eval-docs.md](./eval-docs.md)); lease utility responsibility; 50059/TIC UA; rent roll.
- **Outputs.** UA used vs the schedule for that unit's bedroom count, utilities paid by the tenant and effective date; schedules older than a year; units where the lease's utility responsibility doesn't match the UA applied.
- **Gap evidence.** No national UA dataset or API was found ([section8.md](./section8.md) §6). Each PHA publishes its own PDF. A team that extracts these reliably owns data incumbents re-key by hand.
- **S8 branch coverage: none.** T2's plan adds lease utility-responsibility extraction; no UA schedule parsing exists.

### 7. Tenant file audit: certification vs supporting documents (13)

- **Problem.** The top MOR and 8823 findings are file findings. Income on the certification doesn't match the verifications; a signature or HUD-9887 is missing; a verification is too old; an EIV discrepancy is unresolved; a student rule is unmet; a household member is counted twice ([section8-workflows.md](./section8-workflows.md) §7c; [lihtc-workflows.md](./lihtc-workflows.md) §9 check 1). This is the highest-pain item on the list.
- **Reads.** 50059 or TIC, pay stubs, benefit letters, VOEs, bank statements, EIV reports, HUD-9887/9887-A, HUD-92006, student documentation, recert notices.
- **Outputs.** File-level findings with page citations, mirroring the 10 planted Oak Hollow errors: missing adult signature; missing 9887; verification older than the allowed age; EIV employer not on the cert; deductions verified but not taken; overdue recert with no notices; unreported adult income pushing the household over the limit; the same child in two households; rent roll still on the pre-interim rent; a student with no exemption documented.
- **Why it's not higher.** Build ease is 2: many document types, handwriting and scans, and real tenant PII (SSNs, DOBs, bank numbers). And the gap is closing. HousingIntellect reads pay stubs and verifications and drafts TICs under HOTMA; EliseAI is hiring compliance experts to check its automated file audits; Yardi sells RightSource file review as a service ([competitors.md](./competitors.md) gap 2). Abstractly's angle would be the cross-document tie to the rent roll and HAP contract (#1, #5), not the income math alone.
- **Hard prerequisite.** `feature/s8-pii-guard` (T0: SSN/DOB/bank masking before storage and before Anthropic, plus an AI-off switch) must merge before any real tenant file is uploaded.
- **S8 branch coverage: demo data only.** `feature/s8-demo-files` (Oak Hollow, 40-unit PBRA, 10 tenant files, E1–E10 with an expected-findings JSON) is ready-made ground truth. There are no detectors.

### 8. Deadline calendar: HAP contract renewals, rent increases, recerts (13)

- **Problem.** Missing a date costs real money. HAP contract expiration and renewal option, with at least one year's written notice to opt out ([42 U.S.C. §1437f(c)(8)](https://www.law.cornell.edu/uscode/text/42/1437f), via [section8-workflows.md](./section8-workflows.md) §1). OCAF anniversaries. HCV rent increase requests. PBRA recert reminders at 120, 90 and 60 days before the anniversary, per HUD's 4350.3 sample notices, Exhibits 7-2 to 7-4 ([section8-workflows.md](./section8-workflows.md) §3a). LIHTC annual recerts and owner certifications.
- **Reads.** HAP contracts, leases, 50059/TIC effective and next-recert dates, the PHA directory (per-PHA notice periods).
- **Outputs.** Dated tasks and alerts in the existing obligations, action items and alerts views; a "this month" list.
- **Why the gap score is low.** Recert tracking is a core feature of every PMS. HAP contract renewal dates are less well served, but they're rare.
- **S8 branch coverage: planned.** T7 (HCV reexam tracking), T7b (PBRA recert cascade) and T8 (rent increases, renewals, OCAF) are planned. The PHA directory with deadline defaults is built in `feature/s8-unit-file-and-phas` (T9, FIX FIRST on a T1 bug). `obligations` and `action_items` exist on `main`.

### 9. Inspection and abatement tracker (12)

- **Problem.** For HCV under HQS: life-threatening deficiencies must be fixed in 24 hours and others in 30 days. If not, the PHA abates HAP, and the HAP contract terminates after 60 days if the unit still fails ([24 CFR 982.404](https://www.law.cornell.edu/cfr/text/24/982.404)). The NSPIRE compliance date for HCV/PBV is around Feb 1, 2027, and sources conflict on the exact day ([section8-workflows.md](./section8-workflows.md) §5a).
- **Reads.** HQS / NSPIRE / NSPIRE-V inspection reports, PHA abatement notices, HAP registers.
- **Outputs.** Deficiencies with severity and cure deadlines, reinspection status, abatement exposure in dollars, and a link to the matching HAP shortfall in #2.
- **Why the gap score is low.** Inspection apps and PHA portals already cover much of this. The unique value is the link to HAP payments, so build it after #2.
- **S8 branch coverage: plan and fixtures only.** `feature/s8-inspections` (T6) has a plan pending approval. `qa/section8-fixtures` has HQS, NSPIRE and NSPIRE-V report PDFs.

### 10. Set-aside, income averaging and next-available-unit monitor (12)

- **Problem.** Failing the minimum set-aside (20-50, 40-60 or income averaging) loses credit, and can mean recapture during the 15-year compliance period ([§42(g)(1)](https://www.law.cornell.edu/uscode/text/26/42); [lihtc-workflows.md](./lihtc-workflows.md) §2.2, §3). An existing household over 140% of the limit (170% for deep-rent-skewed) triggers the next available unit rule ([26 CFR 1.42-15](https://www.law.cornell.edu/cfr/text/26/1.42-15)).
- **Reads.** LURA / unit designation list, TICs, rent roll, MTSP limits.
- **Outputs.** Per-building set-aside status, average designated AMI for averaging projects, over-income households and next-available-unit status, and a rough applicable fraction (unit vs floor-space). Every flag shows its rule source.
- **Why it's not higher.** The PMSs do this inside their own data, and HousingIntellect advertises 140% rule tracking. The value is again in diligence (#4) and cross-system portfolios.
- **S8 branch coverage: limit math only** (`feature/s8-hud-data`).

---

## Summary: what the S8 branches already give us

| Branch | State (from `git log main..branch` and TASKS.md) | Feeds features |
|---|---|---|
| `fix/section8-tenant-share` | Built, reviewed, waiting on merge order | #1 |
| `feature/lease-intelligence` | Built (contract rent on S8 leases) | #1, #4 |
| `feature/s8-data-model` (T1) | Built, unmerged; everything stacks on it | #1, #2, #8, #9 |
| `feature/s8-unit-file-and-phas` (T9) | Built; reviewer FIX FIRST on a T1 bug | #8 |
| `feature/s8-hud-data` | Built (IL, FMR, MTSP; LIHTC income/rent limit functions) | #3, #10 |
| `feature/s8-sample-data` (T13) | Ready | demos |
| `feature/s8-demo-files` | Oak Hollow PBRA demo, E1–E10 ground truth, no detectors | #5, #7 |
| `qa/section8-fixtures` | HAP contracts, leases, registers, inspections, rolls, answer key | #1, #2, #9 |
| `feature/s8-hap-payment-import` (T4) | Plan only | #2 |
| `feature/s8-inspections` (T6) | Plan only | #9 |
| `feature/s8-pii-guard` (T0) | Plan only; **blocks #7 and any real tenant file** | #5, #7 |
| `feature/s8-marketing-copy` (T11) | Copy written; must not merge before the features it claims | — |

**Nothing LIHTC-specific exists beyond the limit math.** No 50059 or TIC extraction exists on any branch.

---

## Open questions that would change the ranking

1. **Who is the first buyer?** If it's existing CRE customers, #4 jumps to first and #3 comes with it. If it's small HCV landlords, #2 leads. One question in each of the next five customer calls settles this.
2. **Does PII readiness come first?** #5 and #7 can't touch real files until T0 merges, and the pivot plan's Q5 (encryption at rest, MFA, export/delete) is still open.
3. **How bad is the HAP shortfall problem, in dollars?** No published figure was found ([section8-workflows.md](./section8-workflows.md)). Ask landlords for one PHA's last 6 months of remittances.
4. **Are the AI entrants real in production?** HousingIntellect lists no named customers; EliseAI's income verification was "coming soon" as of its July 2025 post ([competitors.md](./competitors.md)). If they're shipping at scale, drop #7 further.
