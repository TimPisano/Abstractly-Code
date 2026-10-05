# Demo Property: Oak Hollow Apartments (Section 8)

A fully fictional 40-unit **Project-Based Section 8 (PBRA)** property with
10 complete tenant files and **10 planted compliance errors**, for
demoing affordable-housing file review. Nothing here is real: every person,
employer, address, case number, and dollar figure was invented. SSNs all use
the never-issued `000` area number (`000-00-0001` to `000-00-0021`).
Forms are simplified models of the HUD forms, not the official forms.

- **Property:** Oak Hollow Apartments, 1180 Oak Hollow Drive, Riverton, OH 45099
- **Owner:** Oak Hollow Housing Partners, LP · **Agent:** Brightwater Residential Management, LLC
- **Program:** Project-Based Section 8 (PBRA), HAP contract `DEMO-HAP-0040` (fictional)
- **Units:** 40 (12 one-bed / 24 two-bed / 4 three-bed), 38 occupied, 2 vacant (402, 410)
- **Review date:** 10/01/2026 - every "late" or "stale" error and every
  dollar total is measured to this fixed date, so the demo never drifts.

## Files

```
tenant_files/unit_XXX_<name>.pdf               10 tenant files, one multi-page PDF each
rent_roll/oak_hollow_rent_roll_40unit.xlsx     40-unit affordable rent roll (also .csv)
expected_findings.json                         machine-readable answer key (pages + dollars)
generate_s8_demo.py                            generator - the source of truth for everything here
```

Each tenant file has: a cover page (file index + certification history),
rental application & supplement, 9887/9887-A consent signatures, household
composition / SSN / citizenship, student status, the owner certification
(50059 model) with the full rent calculation and signatures, one page per
third-party verification (income, child care, assets, medical), EIV income
report with the written discrepancy resolution, recertification notice log,
lease & rent summary, and race/ethnicity form status. **Every document is
exactly one page**, so page citations are stable (the generator asserts this).

| Unit | File | Pages | Errors |
|---|---|---|---|
| 102 | `tenant_files/unit_102_delgado.pdf` | 13 | **clean** (control) |
| 105 | `tenant_files/unit_105_whitfield.pdf` | 15 | E1 |
| 108 | `tenant_files/unit_108_okafor.pdf` | 13 | E2, E3 |
| 203 | `tenant_files/unit_203_petrakis.pdf` | 12 | E4 |
| 206 | `tenant_files/unit_206_hollis.pdf` | 13 | E5 |
| 207 | `tenant_files/unit_207_ramirez_cole.pdf` | 12 | E6 |
| 301 | `tenant_files/unit_301_lindqvist.pdf` | 12 | E7 |
| 304 | `tenant_files/unit_304_brooks_t.pdf` | 11 | E8, E9 |
| 307 | `tenant_files/unit_307_ostrander.pdf` | 12 | E10 |
| 309 | `tenant_files/unit_309_brooks_d.pdf` | 13 | E8 |

The other 30 occupied units appear only on the rent roll, with internally
consistent numbers and nothing planted.

## Planted errors

Totals as of 10/01/2026: **$1,451 confirmed** (tenant
overcharges owed back, plus HAP overpaid on the duplicate dependent), and **$17,981 potential** subsidy at risk
(HAP that HUD could recover, or understated rent if the EIV wages hold up).

### E1 - Unit 105: Spouse did not sign the annual certification

- **Severity:** high · **Category:** Missing signature
- **What's wrong:** Doreen Whitfield (Spouse, age 67) has a blank signature and date on the 04/01/2026 certification. Only the head and the agent signed.
- **Rule it breaks:** Every adult household member (head, spouse, co-head, and other adults) must sign the certification. Without all signatures it is not a valid certification, and assistance paid on it can be recovered.
- **Citation:** HUD Handbook 4350.3, Ch. 7 (recertification) and the HUD-50059 signature requirements
- **Where to look:** `unit_105_whitfield.pdf` p.6
- **Dollar impact:** $2,886 potential ($481/mo x 6 mo). HAP paid on an invalid certification is at risk of recovery.

### E2 - Unit 108: Adult son never signed HUD-9887 / 9887-A

- **Severity:** medium · **Category:** Missing consent form
- **What's wrong:** Emeka Okafor turned 18 on 11/14/2025 and is listed as an adult on the 07/01/2026 certification, but his 9887 and 9887-A signature lines are blank.
- **Rule it breaks:** Every household member age 18 or older must sign the consent forms (HUD-9887 and 9887-A), including members who turn 18 between certifications. Without consent the owner cannot verify that member's income.
- **Citation:** 24 CFR 5.230; HUD Handbook 4350.3, Ch. 5
- **Where to look:** `unit_108_okafor.pdf` p.3, `unit_108_okafor.pdf` p.4
- **Dollar impact:** None directly - compliance finding

### E3 - Unit 108: Head's employment verification was too old when used

- **Severity:** medium · **Category:** Stale verification
- **What's wrong:** Grace Okafor's employment verification was received 01/20/2026; the certification it supports was signed 06/24/2026 and took effect 07/01/2026: 155 days from receipt to signing and 162 days to the effective date, both past the 120-day limit.
- **Rule it breaks:** Third-party verifications are valid for 120 days from the date the owner receives them. Older verifications must be redone before the certification is completed.
- **Citation:** HUD Handbook 4350.3, Ch. 5 (verification); see docs/research/section8.md §2
- **Where to look:** `unit_108_okafor.pdf` p.7, `unit_108_okafor.pdf` p.6
- **Dollar impact:** None directly - compliance finding

### E4 - Unit 203: EIV shows a second employer that is not on the certification

- **Severity:** high · **Category:** Unresolved EIV discrepancy
- **What's wrong:** The EIV report pulled 05/10/2026 shows wages from Lakeside Logistics, Inc. ($3,120 in each of Q4 2025 and Q1 2026). The certification lists only Riverton Public Library income, and the discrepancy-resolution section is blank.
- **Rule it breaks:** Owners must review EIV income reports and resolve every income discrepancy with the tenant, documenting the resolution in writing in the file. EIV discrepancies are the most common MOR finding.
- **Citation:** 24 CFR 5.233; HUD Handbook 4350.3, Ch. 9 (EIV)
- **Where to look:** `unit_203_petrakis.pdf` p.9, `unit_203_petrakis.pdf` p.6
- **Dollar impact:** $936 potential ($312/mo x 3 mo). If the Lakeside wages are current (~$12,480/yr), tenant rent is understated by $312/mo ($382 certified vs $694) and HAP is overpaid by the same amount.

### E5 - Unit 206: Dependent and child-care deductions verified but not taken

- **Severity:** high · **Category:** Rent calculation error
- **What's wrong:** The file verifies two dependent children and $3,600/yr of child care, but the certification shows $0 for both deductions. Adjusted income is $43,680 on the cert; it should be $39,120.
- **Rule it breaks:** Adjusted income must subtract $480 per dependent and reasonable child-care expenses that enable a family member to work. TTP is the greater of 30% of monthly adjusted income, 10% of monthly gross income, or the minimum rent.
- **Citation:** 24 CFR 5.611 (adjusted income), 5.628 (TTP); HUD Handbook 4350.3, Ch. 5
- **Where to look:** `unit_206_hollis.pdf` p.6, `unit_206_hollis.pdf` p.4, `unit_206_hollis.pdf` p.8
- **Dollar impact:** $456 confirmed ($114/mo x 4 mo). Tenant overcharged $114/mo ($982 charged vs $868 correct); owed back to the tenant.

### E6 - Unit 207: Annual recertification is 2 months overdue and reminders were never sent

- **Severity:** high · **Category:** Late recertification
- **What's wrong:** The annual recertification was due 08/01/2026. The 120-day notice went out 04/03/2026; the tenant never responded and no 90-, 60-, or 30-day reminder was sent. As of 10/01/2026 the household is still on the 08/01/2025 certification.
- **Rule it breaks:** Owners must send the initial notice 120 days before the recertification date and reminders at 90 and 60 days (plus a 30-day notice) if the tenant has not responded, and complete the recertification by the anniversary date.
- **Citation:** HUD Handbook 4350.3, Ch. 7 (annual recertification notices and deadlines)
- **Where to look:** `unit_207_ramirez_cole.pdf` p.10, `unit_207_ramirez_cole.pdf` p.6
- **Dollar impact:** $1,630 potential ($815/mo x 2 mo). HAP paid after the anniversary date on an expired certification is at risk.

### E7 - Unit 301: Adult daughter's income left off the move-in certification; household was over the income limit

- **Severity:** critical · **Category:** Over income at admission
- **What's wrong:** The application and a third-party verification in the file show Freya Lindqvist employed at Harbor Coffee Roasters ($13,400/yr), but the move-in certification counts only Karin's $48,500. True household income is $61,902, over the $59,400 low-income limit for 2 people. The certified $48,502 made the household look eligible.
- **Rule it breaks:** Annual income includes all adult members' income. At admission, household income may not exceed the applicable low-income limit for the household size.
- **Citation:** 24 CFR 5.609 (annual income), 5.653 (income eligibility at admission); HUD Handbook 4350.3, Ch. 3
- **Where to look:** `unit_301_lindqvist.pdf` p.2, `unit_301_lindqvist.pdf` p.8, `unit_301_lindqvist.pdf` p.6
- **Dollar impact:** $959 potential ($137/mo x 7 mo). Household was not eligible; all HAP since move-in is at risk.

### E8 - Unit 304 & 309: Same child counted in two assisted households

- **Severity:** high · **Category:** Duplicate household member
- **What's wrong:** Jaylen Brooks (SSN 000-00-0021, DOB 02/11/2019) is a dependent on both the Unit 304 certification (mother) and the Unit 309 certification (father). Unit 309's own custody summary says he spends 2 of 7 nights there, so he belongs to Unit 304 only.
- **Rule it breaks:** A person may be a member of only one assisted household. For joint custody, the child is counted in the household where they live more than 50% of the time, and only that household takes the dependent deduction.
- **Citation:** 24 CFR 5.216 (SSN disclosure lets duplicates be caught); HUD Handbook 4350.3, Ch. 3 (household composition, joint custody)
- **Where to look:** `unit_304_brooks_t.pdf` p.4, `unit_304_brooks_t.pdf` p.6, `unit_309_brooks_d.pdf` p.4, `unit_309_brooks_d.pdf` p.6, `unit_309_brooks_d.pdf` p.9
- **Dollar impact:** $60 confirmed ($12/mo x 5 mo). Unit 309 took a $480 dependent deduction it isn't entitled to: tenant rent $918 should be $930, so HAP is overpaid by the difference. Unit 309 is also certified at household size 2 instead of 1 (which would leave one person in a 2BR - occupancy standards are out of scope for this demo)..

### E9 - Unit 304: Rent roll still charges the pre-interim rent

- **Severity:** high · **Category:** Rent roll vs certification
- **What's wrong:** The 05/01/2026 interim recertification lowered tenant rent to $428, but the rent roll still charges $615 (the 01/01/2026 amount). On the rent roll, tenant rent plus HAP ($812) adds up to $1,427, which is $187 more than the $1,240 contract rent.
- **Rule it breaks:** Tenant rent must equal the amount on the current effective certification. When an interim decrease is processed, the new rent applies from its effective date.
- **Citation:** HUD Handbook 4350.3, Ch. 7 (interim recertifications)
- **Where to look:** `unit_304_brooks_t.pdf` p.6, `unit_304_brooks_t.pdf` p.10, `oak_hollow_rent_roll_40unit.xlsx` (Unit 304)
- **Dollar impact:** $935 confirmed ($187/mo x 5 mo). Tenant overcharged $187/mo; owed back to the tenant.

### E10 - Unit 307: Full-time student household with no exemption or parental-income documentation

- **Severity:** critical · **Category:** Ineligible student
- **What's wrong:** Tyler Ostrander (age 20) is a full-time student living alone. He is unmarried, not a veteran, not disabled, and has no dependent child. The file has no independent-student documentation and no certification of his parents' income.
- **Rule it breaks:** A student under 24 who is not a veteran, not married, has no dependent child, and is not a person with disabilities is ineligible for Section 8 assistance unless the student is individually income-eligible and either is independent of their parents or the parents are also income-eligible - and that must be documented.
- **Citation:** 24 CFR 5.612; HUD Handbook 4350.3, Ch. 3 (student eligibility)
- **Where to look:** `unit_307_ostrander.pdf` p.5, `unit_307_ostrander.pdf` p.4, `unit_307_ostrander.pdf` p.6
- **Dollar impact:** $11,570 potential ($890/mo x 13 mo). Household may never have been eligible; HAP since move-in is at risk (amount uses the current HAP for every month).

## Rules the demo applies

The calculations use the **pre-HOTMA** rules (dependent deduction $480,
elderly/disabled family deduction $400, medical expenses over 3% of income,
TTP = greater of 30% of monthly adjusted income, 10% of monthly gross
income, or $25 minimum rent; tenant rent = TTP minus utility allowance). Per
`docs/research/section8.md` §5, HUD extended full multifamily HOTMA
compliance to 01/01/2027, so a 2026 file plausibly still uses these. Income
limits, contract rents, and utility allowances are **made up** (2-person low
income limit $59,400; 1BR/2BR/3BR contract rents
$1,050/$1,240/$1,480).

⚠️ The rule summaries and citations are paraphrased from public sources
(HUD Handbook 4350.3, 24 CFR Part 5, and `docs/research/section8.md`). They
have **not been checked by a compliance practitioner**. Confirm the
citations before showing this to anyone who does this work for a living.

## Regenerating

From `backend/`: `venv/bin/python benchmark_data/s8_demo/generate_s8_demo.py`.
Output is deterministic (fixed dates, seeded RNG, invariant PDFs): a re-run
with no code changes leaves the PDFs, CSV, JSON, and README byte-identical.
The `.xlsx` differs only because openpyxl stamps the save time into it.
