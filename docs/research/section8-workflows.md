# Section 8 Recurring Compliance Workflows (PBRA, PBV, HCV)

**Date:** 2026-10-19 · **Status:** Research only. No code changed. Builds on [section8.md](./section8.md) (2026-10-04).

**How to read the confidence labels**

- **Verified** = I read the rule text myself (eCFR/LII/govinfo mirror, or a HUD page I could open).
- **Secondary** = taken from a search-result summary, a vendor/industry article, or a HUD PDF I could not parse. Treat as a lead; check against the primary before building logic on it.
- **Unverified** = I could not confirm it at all. Stated so you do not build on a guess.
- **Verify with your PHA / contract administrator** = local practice varies; the rule may be set by HUD, but the operational detail is set locally.

**Tooling limits that matter for this doc.** The fetch tool could not parse most HUD PDFs (form instructions, PIH notices, Handbook 4350.3, the TRACS guides), returning compressed binary. eCFR URLs returned redirects I did not follow. So the primary-source claims below come from the Cornell LII and govinfo CFR text, HUD web pages, and search summaries. Several field-level claims (50059 numbering, TRACS record layouts, 4350.3 notice windows) are therefore **secondary or unverified**. A reviewer with the PDFs should close those gaps first.

---

## At a glance

| Workflow | Cadence | Key docs | Money at risk (what the source supports) |
|---|---|---|---|
| **1. HAP contracts, renewals, opt-outs** | Contract term (often 1 yr PBRA annual; multi-year possible); opt-out notice **at least 1 year** before termination (statute) | HAP contract (HUD-52641 HCV; HUD-52530 family for PBRA/PBV, see §1), MAHRA renewal options 1–6, opt-out notices | Contract loss or unwanted termination; opt-out means tenants shift to enhanced vouchers (secondary) |
| **2. Rent adjustments** | PBRA: annual OCAF or budget-based at renewal/anniversary; HCV: owner request + rent reasonableness; PBV: annual + redetermination | OCAF tables, budget-based package, Rent Comparability Study (RCS), 24 CFR 982.507 rent reasonableness, HCV HAP | Under-collected rent every month until fixed; over-charged rent is a repayment/credit issue |
| **3. Tenant certifications** | Annual, plus interim on triggers; move-in; 120/90/60/30 notices (PBRA, from secondary) | HUD-50059 / 50059-A, HUD-9887 / 9887-A, HUD-92006, EIV, HOTMA notices | Wrong TTP/HAP = overpayment or underpayment; overpayment recovery; MOR findings |
| **4. TRACS (PBRA/PBV owner side)** | Monthly voucher (MAT30); certifications transmitted (MAT10); corrections | MAT10 (50059 data), HUD-52670 / 52670-A (MAT30), MAT15 adjustments, repayment agreements (52670-A Part 6, secondary) | Rejected or flagged vouchers delay payment; corrections after LOCCS payment roll to next month (secondary) |
| **5. NSPIRE / HQS inspections** | HCV/PBV: PHA inspection (NSPIRE-V/NSPIRE, compliance date now Feb 1, 2027 per PIH 2026-18, secondary); multifamily NSPIRE (REAC) | NSPIRE standards, 24 CFR 982.404 (HQS text), deficiency tracking | HAP abatement (withheld amounts), termination of HAP contract (60 days, 982.404(d)(2)); REAC score |
| **6. Utility allowances** | HCV: annual review, revise at ≥10% rate change (verified). PBRA: per Notice H 2015-04 (secondary) | HCV UA schedule (HUD-52667 per common practice, unverified in this pass); PBRA UA analysis; HUD-50059 Utility Reimbursement | Wrong UA = wrong tenant rent and wrong HAP every month |
| **7. MOR (HUD-9834)** | Risk-based: 12 / 24 / 36 months (secondary; conflicting sources) | HUD-9834, tenant file sample, EIV reports | Below Average or Unsatisfactory: recovery, corrective action plan, repeat review in 12 months; APPS flag affects new HUD business (secondary) |

---

## 0. The HOTMA and deadline status, checked today (affects every section)

- **Final rule** for HOTMA §§102, 103, 104 published February 14, 2023 (88 FR 9600); effective January 1, 2024; §103 does not apply to multifamily. [HUD: Multifamily HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma) (verified: HUD page).
- **Notice H 2023-10** (joint with PIH 2023-27) is the implementation notice. It was updated April 16, 2026 per NAHRO (secondary), following a companion notice. [NAHRO: HUD updates HOTMA guidance](https://www.nahro.org/news/hud-updates-hotma-implementation-guidance/) (secondary).
- **Notice H 2025-07 (December 17, 2025)** extended the multifamily full-compliance date from January 1, 2026 to **January 1, 2027**. Owners who adopt HOTMA before then may calculate incomes and rents manually and enter results in TRACS 202D with the rent override function. [HUD: Multifamily HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma) (verified: HUD page). The same page says TRACS 203A requires an annotation in tenant files when the rent override is used (verified: HUD page).
- **Notice PIH 2026-09 / H 2026-05** (dated April 13, 2026 per secondary sources; some say April 16) amends Attachment I of H 2023-10. It requires an **interim reexamination whenever a household adds or removes a member**, whether or not income changed. During a composition-triggered interim, earned-income increases are not counted except under exceptions already in the notice. An agency with a written policy of not processing income-increase reexams in the last three months of a certification may defer composition changes in that window. [HUD PIH 2026-09](https://www.hud.gov/sites/default/files/hudclips/documents/PIH-2026-09.pdf) (secondary: PDF not parsed; summary from [NAHRO](https://www.nahro.org/news/hud-updates-hotma-implementation-guidance/)). **This is missing from section8.md.**
- **The "10% interim threshold" in section8.md.** For HCV, the 24 CFR 982.516 text I retrieved says the PHA must conduct an interim review when adjusted income will rise by **10% or more**, and may decline for decreases under 10% (or a lower PHA threshold) (verified: [24 CFR 982.516 via LII](https://www.law.cornell.edu/cfr/text/24/982.516)). For multifamily, I found only secondary summaries saying the same for unearned-income increases above 10% of adjusted income. **Unverified for multifamily** against H 2023-10 itself.
- **Vendor blogs describe a "0% threshold" for composition changes.** That is a summary of the new composition rule, not a threshold. Treat with care.

---

## 1. HAP contracts, renewals, and opt-outs

### 1a. Steps and cadence

- **HCV (PHA-run):** the HAP contract is between the PHA and the owner, executed per unit, tied to the lease. It is renewed through the lease term; the PHA processes changes. (HUD form for HCV HAP: **HUD-52641**, per section8.md and common practice; the form number is secondary.)
- **PBRA (owner / contract administrator):** the HAP contract runs for a term set by the original contract (often 5 years or more for older contracts; check each contract). At expiration the owner must renew, opt out, or take a different option. The contract administrator (CA) processes the renewal.
- **Renewal options.** HUD's Section 8 Renewal Policy Guidebook describes six options under MAHRA: Option One (mark-up-to-market), Option Two (renew at current rents at or below comparable market), Option Three (referral to the Office of Affordable Housing Preservation), Option Four (projects exempt from OMHAR), Option Five (portfolio reengineering or preservation demonstration), Option Six (opt-out). [NCHM: renewal options](https://www.nchm.org/the-complete-guide-to-your-section-8-contract-renewal-options/) (secondary: option list confirmed from a search summary of the HUD guide). The current guidebook text was **not retrieved** (secondary, unverified in detail).
- **Renewal rent standard.** The guidebook says renewal rents use a **"lesser of"** test: current rent adjusted by OCAF, or the budget-based level, applied at initial and subsequent renewals. [Renewal Guidebook 6-2 (mirror)](https://gocodebook.com/library/us/federal/us-hud-section8-renewal-policy-guidebook/6-2.-renewals) (secondary).
- **Opt-out notice.** The statute requires an owner to give **at least one year's written notice** to tenants and HUD before terminating a Section 8 HAP contract, and to comply with additional HUD requirements. The owner may not evict or raise rent until one year after the notice. [42 U.S.C. §1437f(c)(8)](https://www.law.cornell.edu/uscode/text/42/1437f) (statute text as quoted in court opinions, e.g. [9th Cir. opinion](https://cdn.ca9.uscourts.gov/datastore/opinions/2011/02/25/10-15303.pdf); secondary for the exact text). Enhanced vouchers follow after the notice period (secondary, [1st Cir. summary in the same search](https://www.ca1.uscourts.gov/sites/ca1/files/opnfiles/02-2675-01A.pdf)).
- **The 120-day opt-out notice in older HUD material** (e.g. [HUD 1998 notice 98-34](https://www.hud.gov/sites/documents/98-34hsgn.doc)) is **older guidance and should not be relied on** without checking the current notice. I did not find a current HUD notice confirming the exact timing for each option; **verify with your contract administrator** and the current Renewal Guidebook.

### 1b. Documents and form numbers

- HAP contract (HCV: HUD-52641, secondary). PBRA/PBV HAP contract forms (HUD-52530 series, per section8.md; **sub-form numbers HUD-52530A/B/C not verified in this pass**).
- Renewal request and CA package (form set varies by option; **verify with your CA**).
- Opt-out notices to tenants and HUD (form/format per current HUD notice; not identified).

### 1c. Fields that matter

- **Contract rent** (rent to owner, per unit) and **effective date** of the contract rent. The Exhibit / rent schedule on the HAP contract must match the rent entered in TRACS and on the 50059 (see extraction section).
- **Contract term start / end** and **renewal option selected**.
- **Gross rent** = contract rent + utility allowance (verified via HUD Handbook 4350.3 excerpt, secondary: [4350.3 Exhibit 3-12 mirror](https://gocodebook.com/library/us/federal/us-hud-handbook-4350-3-rev-1-occupancy/exhibit-3-12-section-8-rap-and-rent-supplement-programs-special-instructions-for-determinin/a.-calculate-the-total-tenant-payment-ttp-and-the-resulting-assistance-payment-without-prorati)).

### 1d. Where errors cost money

- **Wrong contract rent after renewal** = under- or over-collected HAP every month until corrected. Over-collected HAP is a repayment exposure (mechanism: repayment on the owner side; the dollar amount depends on the repayment rules; **no published per-case figure found**).
- **Opt-out or late notice** = the owner may face a claim, and the tenant protections in §1(c)(8) apply. **No published penalty figure found.**
- **Lost contract** when an option is missed or the renewal package is incomplete (mechanism: contract termination or expiration; **verify with your CA**).

---

## 2. Rent adjustments

### 2a. PBRA: OCAF and budget-based adjustments

- **Years 2–5 of a multi-year contract:** rents adjust by the published **OCAF** (Operating Cost Adjustment Factor), or at HUD's discretion a budget-based request. [Renewal Guidebook 4-3 (mirror)](https://gocodebook.com/library/us/federal/us-hud-section8-renewal-policy-guidebook/4-3.-annual-rent-adjustments-during-a-multiyear-contract) (secondary).
- **Budget-based requests** must use current debt service and generally need an RCS submitted within the preceding five years. Budget-based adjustments are **not** permitted for a short-term renewal; OCAF is prorated by months. [Renewal Guidebook 2-13 (mirror)](https://gocodebook.com/library/us/federal/us-hud-section8-renewal-policy-guidebook/2-13.-rent-adjustments) (secondary).
- **The 24 CFR 880.607 text I retrieved covers termination and lease modification, not rent increases; it says increases are governed by 880.609** (verified: [24 CFR 880.607 via LII](https://www.law.cornell.edu/cfr/text/24/880.607)). **I did not retrieve 880.609**, so the owner request rules (notice timing, package contents) are unverified.
- **OCAF publication and effective dates** are set by HUD each year. **I did not verify the 2026 OCAF values or effective date.**

### 2b. HCV: owner rent increase and rent reasonableness

- **PHA must determine rent reasonableness** before approving a lease, before any rent increase, when the FMR falls 10% or more in the comparison window, when HUD directs, and at other times. The rent to owner may never exceed the most recent reasonable-rent determination. [24 CFR 982.507 via LII](https://www.law.cornell.edu/cfr/text/24/982.507) (verified).
- **Owner certification:** by accepting each HAP payment, the owner certifies that the rent is not more than the rent for comparable unassisted units, and must provide requested rent information (verified, same source, (d)).
- **Exemption for LIHTC/HOME units:** if the voucher rent does not exceed rents for non-voucher LIHTC or HOME units in the project, a comparison is not required (verified, 982.507(c)).
- **Owner rent-increase timing** is set by the PHA's administrative plan and lease terms, not by 982.507 itself (verified: the section does not contain a timing rule). **Verify with your PHA.**

### 2c. PBV rent redeterminations

- PBV contract rent adjustments and reasonable-rent redeterminations are in 24 CFR 983 (the section I retrieved, 983.354, covered only "other fees and charges," so **I did not verify PBV initial rent, annual adjustment, or cap rules**). **Verify with your PHA.**

### 2d. Documents and fields

- **OCAF table and effective date** (PBRA renewal package); **budget-based package** (current debt service, RCS, operating statements; secondary).
- **HCV rent reasonableness comparables** and the **payment standard** (set by PHA; the FMR-based range is in section8.md).
- **Fields that matter in the HAP tie-out:** contract rent, effective date of the change, FMR effective date (for HCV redetermination triggers).

### 2e. Where errors cost money

- **Rent increase not implemented** = lost rent each month, retroactive recovery is limited by contract terms (**verify with your CA/PHA**).
- **Increase implemented without approval** = over-billed HAP, repayment exposure (mechanism: repayment on the HAP side; no published per-case figure).
- **HCV: rent to owner above reasonable rent** = the PHA can require a reduction; overpayment is a PHA repayment issue, owner-side exposure depends on the HAP contract.

---

## 3. Tenant certifications (HUD-50059 / 50059-A, interim, EIV)

### 3a. Steps and cadence

- **PBRA/PBV owner (certifier):** initial (move-in), annual, and interim recertifications. The owner (or management agent) prepares the **HUD-50059** and transmits data to TRACS (MAT10). [HUD-50059 form page](https://www.hud.gov/sites/documents/50059.pdf) (not parsed; form existence verified via search).
- **HCV:** the PHA runs annual and interim reexams, and the PHA submits the **HUD-50058** (secondary: [24 CFR 982.516 via LII](https://www.law.cornell.edu/cfr/text/24/982.516) confirms the PHA reexamines at least annually and documents verification).
- **Annual cadence and 120/90/60/30 notices:** section8.md cites [a legal summary](https://legalclarity.org/how-the-hud-annual-recertification-process-works/) for these windows. **I could not verify them against Handbook 4350.3** (unverified). Treat the window as a working assumption, and confirm before writing notice logic.
- **Verification validity:** section8.md says third-party verifications are valid 120 days from receipt. **Unverified for HOTMA-era rules.** A Minnesota PHA plan said HUD made a 120-day window for third-party verification optional for PHAs (secondary, from search). **Verify with your PHA / CA.**

### 3b. Documents and form numbers

- **HUD-50059** (owner certification, PBRA/PBV); **HUD-50059-A** (partial certification: e.g. utility, gross rent, TTP, or move-out updates; secondary: the search summary names "UT, GR, TM, MO" codes for the short form).
- **HUD-9887 / 9887-A** (consent for release of information; secondary: section8.md).
- **HUD-92006** (supplement to application; secondary).
- **EIV** reports (Income, New Hires, Discrepancy). Use under 24 CFR 5.233 / 5.236 was **not verified** (the eCFR URL redirected). Section8.md's "120 days" EIV-pull rule is **unverified**.
- **Form HUD-50058** (HCV, PHA) is in section8.md; **not separately verified here**.

### 3c. Fields that matter (50059)

The field names below are the ones the Handbook calculations use. **Field numbers differ between form revisions, so check the revision in effect.** The arithmetic is verified from the Handbook mirror.

- **Total Tenant Payment (TTP)**
- **Gross Rent** = **Contract Rent + Utility Allowance**
- **Assistance Payment (HAP)** = **Gross Rent − TTP**
- **Tenant Rent** = **TTP − Utility Allowance** when TTP exceeds UA; equivalently **Contract Rent − HAP**
- **Utility Reimbursement** = **UA − TTP**, paid to the tenant when UA exceeds TTP (in that case Tenant Rent is zero) (secondary: [Handbook Exhibit 3-12 mirror](https://gocodebook.com/library/us/federal/us-hud-handbook-4350-3-rev-1-occupancy/exhibit-3-12-section-8-rap-and-rent-supplement-programs-special-instructions-for-determinin/a.-calculate-the-total-tenant-payment-ttp-and-the-resulting-assistance-payment-without-prorati); the "UA exceeds TTP" payment rule is from a housing authority policy in search results, so **verify**).
- **Effective Date** (of the certification)
- **Next Recertification Date** (the annual due date; used to drive the notice cascade)
- **Household composition** (members, with dates of entry/exit; drives interim triggers under PIH 2026-09)
- **Income by source** and **asset values** (self-certification rules changed under HOTMA; see §0)

### 3d. Where errors cost money

- **Wrong TTP or Tenant Rent** = HAP paid on the wrong amount every month until corrected; the MOR reviewer finds this in calculation tests (mechanism: overpayment repayment, MOR finding). **No published dollar figure found.**
- **Missed or late recert** = the rent is calculated on the old data, and the increase is often lost or limited by the effective-date rules. (mechanism: lost HAP, MOR finding; the exact effective-date rule was not verified here).
- **HOTMA de minimis:** a rent-calculation error of **$30 or less per month ($360 per year)** is not a noncompliance, but an overcharged family must still be credited or repaid (verified: [24 CFR 982.516 via LII](https://www.law.cornell.edu/cfr/text/24/982.516) for HCV; **multifamily application unverified**).
- **EIV discrepancies** unresolved in writing = MOR finding (secondary: [Navigate Housing](https://www.navigatehousing.com/common-mor-findings-to-avoid-on-property/), which claims EIV errors are nearly half of findings for one firm; treat as anecdotal).

---

## 4. TRACS: MAT10, MAT30 / HUD-52670, MAT15, repayment agreements

### 4a. Steps and cadence

- **MAT10 (certification transmission):** the owner transmits certification data (from the 50059) to TRACS. **Record layouts and transmission timing not verified** (TRACS MAT user guide not parsed).
- **MAT30 / HUD-52670 (monthly voucher):** the owner submits a voucher each month requesting HAP. The contract administrator (CA) reviews and HUD pays through LOCCS. A state HFA page says the CA disburses HAP on the **first business day of the month following voucher submission** (secondary).
- **Corrections:** a "MAT30 Correction" must carry the correct Voucher ID; a correction that arrives after the original voucher has gone to LOCCS for payment is rejected and the adjustment goes on the next voucher (secondary: TRACS status-code appendix via [wvhdf.com mirror](https://www.wvhdf.com/wp-content/uploads/2026/03/TRACS-Voucher-Acknowledgement-Status-Messages-Codes-202D-Appx-G-1.pdf), which the search said came from a 2014 release; **codes may have changed**).
- **Flagged and rejected vouchers:** the search summary of HUD's [voucher flagged/rejected guide](https://www.hud.gov/sites/documents/guide_paid_flag_rejected.pdf) lists status codes **T03, T31, T52** as flagged for manual review by the HUD field office (secondary; the PDF body was not parsed, so **verify the codes in the current guide**). Unsubmitted vouchers older than 60 days are rejected as "Voucher Cancelled by Reviewer" (secondary).
- **MAT15 (adjustments):** **not verified.** Section8.md lists it; I could not confirm its role.

### 4b. Documents and form numbers

- **HUD-52670** (monthly voucher) and **HUD-52670-A** (voucher parts). The parts structure is secondary: Part 1 = regular assistance; Part 2 = special claims schedule; Part 3 = adjustments; Part 4 = miscellaneous accounting requests; Part 5 = approved special claims; Part 6 = repayment agreements and FSS escrow records (from a TRACS release summary, secondary). **Verify against the current 52670-A instructions** ([HUD 52670-A Part 3 instructions](https://www.hud.gov/sites/documents/52670a3-ins.doc), not parsed).
- **Repayment agreements** appear in Part 6 per the secondary summary above. The HUD-52670-A form covers repayment agreements and FSS escrows (secondary, from the same search).
- **TRACS 203A** release changed the rent override process (verified: [HUD multifamily HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma)). The full 203A release notes were not read.

### 4c. Fields that matter

- **Voucher ID** (must match on corrections; a new voucher uses nines in that field per secondary summary).
- **Assistance amount per unit** (must tie to the 50059 HAP for that unit in the period).
- **Tenant rent / TTP per unit** on the voucher must tie to the 50059s.
- **Repayment agreement** amount and schedule (Part 6, secondary).

### 4d. Where errors cost money

- **Flagged or rejected voucher** = payment held until the field office review; the owner carries cash flow risk for the month (mechanism: delayed HAP; **no published figure found**).
- **Correction after the LOCCS payment** = the adjustment waits for the next month (mechanism: timing loss).
- **Wrong Voucher ID on correction** = correction rejected (secondary).
- **Stale voucher (over 60 days, unsubmitted)** = cancelled and must be retransmitted (secondary).

---

## 5. NSPIRE and HQS inspections

### 5a. Standards and dates

- **HCV / PBV (PHA-run):** NSPIRE replaces HQS. The NSPIRE-V demonstration was the earlier name. PIH 2023-28 issued September 29, 2023 set an original effective date of October 1, 2023, and the compliance date was extended in steps (Oct 1, 2024; Oct 1, 2025; then, per a September 30, 2025 notice, **February 1, 2027**) (secondary: [NAHRO](https://nahro.org/?p=38522) and search summaries). **PIH 2026-18 (July 15, 2026, secondary)** reportedly supersedes PIH 2023-28 and PIH 2024-26. A search summary also says a Federal Register notice gives **January 31, 2027** (one day earlier). **Conflicting; check [PIH 2026-18](https://www.hud.gov/sites/default/files/PIH/documents/PIH-2026-18.pdf) directly.**
- **Multifamily / PBRA (REAC):** the scoring of new affirmative requirements was delayed to **October 1, 2026** by PIH 2025-27 (secondary, from search; see [PIH 2025-27](https://www.hud.gov/sites/dfiles/OCHCO/documents/PIH-2025-27.pdf)). Deficiencies must still be corrected on NSPIRE severity timeframes. A Federal Register notice (2026-19881) says the new affirmative requirements count toward scores starting October 1, 2026 (secondary: [FR 2026-19881](https://public-inspection.federalregister.gov/2026-19881.pdf)). **Section8.md says "NSPIRE for multifamily effective 2023"; that is not the scoring date. See Corrections.**

### 5b. Deficiency timeframes

- **HQS (24 CFR 982.404, still the text on LII; verified):**
  - Life-threatening: correct within **24 hours** of notification.
  - Other: correct within **30 calendar days**.
  - If not corrected, the PHA **must abate** HAP, including amounts withheld; termination follows if the unit does not meet HQS within **60 days** (or a longer PHA-set period) (verified: [24 CFR 982.404 via LII](https://www.law.cornell.edu/cfr/text/24/982.404)).
  - **Note:** section8.md's "24-hour / 30-day" framing is the **HQS** rule. NSPIRE uses severity levels, and the timeframes below apply to multifamily.
- **NSPIRE multifamily (secondary: [HUD OIG 2026 report](https://hudoig.gov/sites/default/files/2026-07/2026-oe-0802_508.pdf) and NSPIRE summaries):** life-threatening and severe deficiencies: correct within **24 hours** of notification; evidence of correction submitted in NSPIRE within 48 hours after the deadline (OIG says 2 business days after notification for evidence; one summary says 72 hours). Moderate and low: correct within **30 days**; HUD can authorize longer permanent repairs. **Check 24 CFR 5.711 and the current standards.**

### 5c. Documents and fields

- **Inspection report**, **deficiency list with severity**, **notification date**, **due date**, **evidence of correction**, **abatement record** (HCV: PHA). Field names in the NSPIRE system were not verified.

### 5d. Where errors cost money

- **HQS abatement:** HAP is abated (withheld amounts paid later only if corrected); the owner loses that month's HAP (mechanism: abatement, verified via 982.404(d)(2)).
- **Termination:** HAP contract terminated if not corrected within the PHA period (60 days default, verified).
- **Multifamily:** a low REAC score or a failed severity item affects REAC standing (mechanism: REAC score; **no published dollar figure found**).

---

## 6. Utility allowances

### 6a. HCV (verified)

- The PHA must keep a utility allowance schedule for tenant-paid utilities, tenant-supplied refrigerators and ranges, and other tenant-paid services. The schedule is area-wide based on typical costs for energy-conservative households (verified: [24 CFR 982.517 via LII](https://www.law.cornell.edu/cfr/text/24/982.517)).
- The PHA must **review the schedule each year** and **revise a utility category when the rate changes by 10% or more** since the last revision (verified, 982.517).
- The UA used is the lesser of the unit size leased or the family unit size under the PHA's subsidy standards; a reasonable accommodation can change it (verified).

### 6b. PBRA / multifamily (secondary)

- **Notice H 2015-04** (issued June 22, 2015) standardizes how owners complete the multifamily utility analysis. Owners must establish baseline allowances by bedroom size using a sampling method, typically once every third year, and must adjust the allowance when utilities change by 10% or more (secondary: [NLIHC summary](https://nlihc.org/resource/utility-allowance-analysis-guidance-hud-assisted-multifamily-properties); the notice PDF copy: [thda.org](https://thda.org/pdf/15-04HSGN.PDF), not parsed). **The "factor-based" method named in section8.md is not confirmed.** Verify with your CA.
- Rent adjustments must be held until the owner submits the UA and required paperwork (secondary).

### 6c. Documents and fields

- **HCV:** PHA UA schedule (HUD-52667 per section8.md and common practice; **not verified here**), tenant utility responsibility. **50059 Utility Allowance** field and **Utility Reimbursement** (see §3c).
- **PBRA:** UA analysis package (sample data, bedroom-size averages, utility rate data), gross rent calculation.

### 6d. Where errors cost money

- **UA too high** = tenant overpays rent for the wrong UA; HCV tenant rent and HAP both change every month.
- **UA too low** = HAP and tenant rent wrong in the other direction; repayment exposure.
- **UA not revised after a 10%+ rate change** = noncompliance on the schedule (HCV, verified).
- **Mismatch between UA on 50059 and UA on the lease or HAP exhibit** = MOR finding (secondary, general MOR theme; not sourced to a specific case).

---

## 7. Management and Occupancy Reviews (HUD-9834)

### 7a. Steps and cadence

- **Rating categories.** Form HUD-9834 rates each category as **Superior, Above Average, Satisfactory, Below Average, or Unsatisfactory**, then gives an overall rating. This is five labels, not four (see Corrections). [HUD-9834 (2009 version, NHLP copy)](https://www.nhlp.org/wp-content/uploads/HUD-Form-9834-June-2009.pdf) (secondary: current layout not verified).
- **Schedule (risk-based; sources conflict):** after a Below Average rating, the next MOR is within **12 months**. Satisfactory within 24 months and Above Average or Superior within 36 months for "Not Troubled" properties (secondary: [Habitat Group](https://thehabitatgroup.com/articles/print/1944)). An NCHM table shows a 12-month cycle for Troubled and Potentially Troubled properties regardless of score (secondary: [NCHM streamlining summary](https://www.nchm.org/hud-publishes-final-rule-on-streamlining-management-and-occupancy-reviews-for-the-section-8-programs)). Check the [June 27, 2022 final rule](https://www.federalregister.gov/documents/2022/06/27/2022-13426/streamlining-management-and-occupancy-reviews-for-section-8-housing-assistance-programs) (not parsed here).
- **Effective date of the streamlined rule:** September 26, 2022 (secondary).

### 7b. Documents

- Form 9834, the tenant file sample (50059s, 9887s, EIV reports, notices), the UA analysis, the rent calculation, the HAP contract and vouchers (MAT30 tie-out).

### 7c. Where findings come from (for the extraction section)

- **Calculation errors** (rent and TTP mismatches; a dependent deduction claimed by two households is cited in secondary sources).
- **EIV discrepancies** not resolved in writing.
- **Late or missed recertifications** and notices.
- **Missing or unsigned forms** (9887, race/ethnicity, student status).
- **Undocumented accommodation conversations.**

### 7d. Where errors cost money

- **Below Average or Unsatisfactory:** recovery of overpaid assistance, possible abatement or suspension, a corrective action plan, and a repeat review in 12 months, with HAP contract termination for persistent noncompliance (secondary: [Hawaii Affordable MOR guide](https://www.hawaiiaffordable.com/blog/hud-mor-survival-guide-2026-tips-for-project-based-section-8-managers/) and section8.md). The **APPS** (Active Partners Performance System) flag can affect new HUD business (secondary; **no HUD primary verified here**).
- **No published dollar figures** were found for MOR penalties.

---

## Where document extraction / validation helps

Concrete cross-document checks, ranked by how much money they protect. Each one assumes the source documents are available as data (50059, HAP contract / rent schedule, rent roll, voucher, UA schedule, EIV report, inspection report).

**Top five**

1. **Contract rent tie-out.** Contract rent on the 50059 = contract rent in the HAP contract rent schedule (or Exhibit) = contract rent on the rent roll, for the same unit and effective date. A mismatch on any one is a HAP error or a stale rent. (Mechanism: lost or over-collected HAP every month.)
2. **Gross rent and HAP arithmetic on each 50059.** Gross Rent = Contract Rent + UA. HAP (Assistance Payment) = Gross Rent − TTP. Tenant Rent = Contract Rent − HAP. Utility Reimbursement = UA − TTP when UA is higher. Flag any unit that breaks these identities. (Mechanism: the MOR calculation test.)
3. **Voucher total vs. the 50059s.** For each voucher month, the sum of HAP per unit (50059 Assistance Payment, current effective) = the amount on HUD-52670 / 52670-A for that month. Also check Voucher ID continuity on corrections. (Mechanism: rejected voucher, delayed or lost HAP.)
4. **Recert due-date and notice cascade.** For each unit: Next Recertification Date vs. effective date plus 12 months; flag any unit with no 120/90/60/30 notices logged in the window (the window itself to be confirmed). Flag any unit whose household composition changed (adds or removes a member) without a logged interim, per PIH 2026-09. (Mechanism: late recert, MOR finding.)
5. **UA vs. effective UA schedule and rate change.** The UA on the 50059 (and in gross rent) must match the current UA schedule for that unit size and effective date. For HCV, flag any UA category where the rate changed by 10% or more since the last revision (982.517). (Mechanism: wrong TTP and HAP every month.)

**Additional useful checks**

6. **EIV vs. 50059 income and composition.** Flag income in EIV or the new-hire report that does not match the 50059, and any discrepancy without a written resolution in the file. (Mechanism: MOR finding; repayment.)
7. **Inspection due dates vs. abatement.** For each inspection deficiency (NSPIRE severity or HQS life-threatening / other), compare the due date to the correction evidence date and to the HAP paid that month. (Mechanism: abatement and termination.)
8. **Renewal calendar vs. contract term.** Every HAP contract's expiration, the opt-out notice deadline (one year under the statute), and the renewal option chosen, checked against the current date. (Mechanism: contract loss.)
9. **Repayment agreement tie-out.** Repayment amount and schedule on the voucher (52670-A Part 6, secondary) against the tenant's ledger. (Mechanism: over-collection or missed payments.)

---

## Corrections to section8.md

1. **MOR rating scale.** section8.md says Superior / Satisfactory / Below Average / Unsatisfactory (four labels). HUD-9834 uses five: Superior, Above Average, Satisfactory, Below Average, Unsatisfactory (secondary; the form layout is from a 2009 copy).
2. **HOTMA interim triggers are incomplete.** section8.md omits that PIH / H 2026-09 (April 2026) requires an interim reexamination on any household composition change, regardless of income, with the earned-income limit during that interim. (Secondary: NAHRO summary; the notice PDF was not parsed.)
3. **The "10% interim threshold" is verified for HCV only.** For multifamily, section8.md presents it as settled; I could not confirm it from H 2023-10 itself.
4. **NSPIRE dates.** section8.md says NSPIRE for multifamily is "effective 2023," with no date for HCV/PBV. The current situation (secondary): HCV/PBV compliance date extended to February 1, 2027 (conflict: January 31, 2027 in a Federal Register notice; PIH 2026-18 may supersede PIH 2023-28); multifamily affirmative-requirement scoring starts October 1, 2026.
5. **The 24-hour / 30-day timeframes are the HQS rule (24 CFR 982.404), not NSPIRE for every item.** For multifamily NSPIRE, life-threatening and severe items are 24 hours; moderate and low are 30 days (secondary: HUD OIG).
6. **The 120-day verification and EIV pull windows** in section8.md are not verified. One source says HUD made the 120-day third-party verification window optional for PHAs. Treat as open.
7. **Opt-out notice.** section8.md does not give a notice period. The statute requires at least one year's written notice (verified via court opinions quoting 42 U.S.C. §1437f(c)(8)). An older HUD notice (98-34) mentions 120 days; treat it as superseded until confirmed.
8. **Asset thresholds.** section8.md's 2026 figures ($52,787 imputed-income threshold; $105,574 asset limit) come from Costello (secondary, not checked). The HCV asset self-certification threshold in 982.516 is $50,000 indexed by CPI-W (verified text); the 2026 indexed figure was not checked.
9. **"PIC" submission for HUD-50058.** section8.md says data goes to IMS/PIC. Not verified in this pass.
10. **HUD-52641 / HUD-52530 series.** section8.md does not name these in the HAP section. HUD-52641 for HCV HAP is secondary; the PBRA/PBV sub-forms (52530A/B/C) were not verified.

---

## Sources

**Primary (verified by me or confirmed on a HUD page)**
- [HUD: HOTMA multifamily page (notices, dates, Notice H 2025-07, TRACS 203A rent override)](https://www.hud.gov/hud-partners/multifamily-hotma)
- [24 CFR 982.404 (HQS: 24-hour, 30-day, abatement, 60-day termination) via LII](https://www.law.cornell.edu/cfr/text/24/982.404)
- [24 CFR 982.507 (rent reasonableness, owner certification) via LII](https://www.law.cornell.edu/cfr/text/24/982.507)
- [24 CFR 982.516 (annual and interim reexam, 10% thresholds, $30 de minimis, $50,000 asset self-cert) via LII](https://www.law.cornell.edu/cfr/text/24/982.516)
- [24 CFR 982.517 (utility allowance schedule, 10% revision) via LII](https://www.law.cornell.edu/cfr/text/24/982.517)
- [24 CFR 880.607 (termination; rent governed by 880.609) via LII](https://www.law.cornell.edu/cfr/text/24/880.607)
- [24 CFR Part 982 (govinfo XML, 2019)](https://www.govinfo.gov/content/pkg/CFR-2019-title24-vol4/xml/CFR-2019-title24-vol4-part982.xml) (not read in full; cited as the source file)
- [42 U.S.C. §1437f (statute, LII)](https://www.law.cornell.edu/uscode/text/42/1437f) (cited via court opinions; not fetched directly)

**Primary notices (identified; PDF not parsed, so content is from secondary summaries)**
- [PIH 2026-18 (NSPIRE, HCV/PBV)](https://www.hud.gov/sites/default/files/PIH/documents/PIH-2026-18.pdf)
- [PIH 2026-09 / H 2026-05 (HOTMA interim composition rule)](https://www.hud.gov/sites/default/files/hudclips/documents/PIH-2026-09.pdf)
- [PIH 2025-27 (NSPIRE scoring delay to Oct 1, 2026)](https://www.hud.gov/sites/dfiles/OCHCO/documents/PIH-2025-27.pdf)
- [Federal Register 2026-19881 (NSPIRE scoring notice)](https://public-inspection.federalregister.gov/2026-19881.pdf)
- [Notice H 2015-04 (utility analysis, thda.org copy)](https://thda.org/pdf/15-04HSGN.PDF)
- [HUD-50059 form](https://www.hud.gov/sites/documents/50059.pdf)
- [HUD-52670-A Part 3 instructions](https://www.hud.gov/sites/documents/52670a3-ins.doc)
- [TRACS 203A release](https://hud.gov/sites/documents/TRACSRELEASE203A.PDF)
- [Guide to Getting Paid When Vouchers Are Flagged or Rejected in TRACS (May 2015)](https://www.hud.gov/sites/documents/guide_paid_flag_rejected.pdf)
- [HUD Notice 98-34 (older opt-out 120-day reference)](https://www.hud.gov/sites/documents/98-34hsgn.doc)
- [Federal Register: MOR streamlining final rule, June 27, 2022](https://www.federalregister.gov/documents/2022/06/27/2022-13426/streamlining-management-and-occupancy-reviews-for-section-8-housing-assistance-programs)
- [HUD-9834 (2009 copy, NHLP)](https://www.nhlp.org/wp-content/uploads/HUD-Form-9834-June-2009.pdf)
- [HUD OIG 2026 report (NSPIRE correction timeframes)](https://hudoig.gov/sites/default/files/2026-07/2026-oe-0802_508.pdf)

**Secondary (search summaries, mirrors, and industry)**
- [NAHRO: HUD updates HOTMA implementation guidance](https://www.nahro.org/news/hud-updates-hotma-implementation-guidance/)
- [NAHRO: NSPIRE dates extended](https://www.nahro.org/news/nspire-dates-extended-to-2026-for-public-housing-multifamily-housing-and-community-planning-and-development-programs)
- [NAHRO: NSPIRE HCV/PBV compliance date extended (nahro.org/?p=38522)](https://nahro.org/?p=38522)
- [NCHM: Section 8 contract renewal options](https://www.nchm.org/the-complete-guide-to-your-section-8-contract-renewal-options/)
- [NCHM: MOR streamlining](https://www.nchm.org/hud-publishes-final-rule-on-streamlining-management-and-occupancy-reviews-for-the-section-8-programs)
- [Renewal Policy Guidebook 6-2 renewals (gocodebook mirror)](https://gocodebook.com/library/us/federal/us-hud-section8-renewal-policy-guidebook/6-2.-renewals)
- [Renewal Policy Guidebook 4-3 multiyear rent adjustments (mirror)](https://gocodebook.com/library/us/federal/us-hud-section8-renewal-policy-guidebook/4-3.-annual-rent-adjustments-during-a-multiyear-contract)
- [Renewal Policy Guidebook 2-13 rent adjustments (mirror)](https://gocodebook.com/library/us/federal/us-hud-section8-renewal-policy-guidebook/2-13.-rent-adjustments)
- [HUD Handbook 4350.3 Exhibit 3-12 TTP and assistance payment (mirror)](https://gocodebook.com/library/us/federal/us-hud-handbook-4350-3-rev-1-occupancy/exhibit-3-12-section-8-rap-and-rent-supplement-programs-special-instructions-for-determinin/a.-calculate-the-total-tenant-payment-ttp-and-the-resulting-assistance-payment-without-prorati)
- [TRACS voucher status codes (wvhdf.com copy, 2014 release)](https://www.wvhdf.com/wp-content/uploads/2026/03/TRACS-Voucher-Acknowledgement-Status-Messages-Codes-202D-Appx-G-1.pdf)
- [NLIHC: utility allowance analysis guidance](https://nlihc.org/resource/utility-allowance-analysis-guidance-hud-assisted-multifamily-properties)
- [Habitat Group: MOR intervals](https://thehabitatgroup.com/articles/print/1944)
- [Navigate Housing: common MOR findings](https://www.navigatehousing.com/common-mor-findings-to-avoid-on-property/)
- [Hawaii Affordable: MOR survival guide](https://www.hawaiiaffordable.com/blog/hud-mor-survival-guide-2026-tips-for-project-based-section-8-managers/)
- [Costello: 2026 HOTMA adjustment factors](https://www.costellocompliance.com/blog/news-hud-announces-2026-hotma-adjustment-factors)
- [LegalClarity: annual recertification process](https://legalclarity.org/how-the-hud-annual-recertification-process-works/)
- [9th Cir. opinion quoting §1437f(c)(8)](https://cdn.ca9.uscourts.gov/datastore/opinions/2011/02/25/10-15303.pdf)
- [1st Cir. opinion on enhanced vouchers](https://www.ca1.uscourts.gov/sites/ca1/files/opnfiles/02-2675-01A.pdf)
- [Minnesota Housing: Project Based Section 8 contracts](https://mnhousing.gov/home/rental-housing/property-managers/section-8-811-contracts)
- [South Carolina SC Housing: voucher processing](https://www.schousing.sc.gov/business-and-community-partners/voucher-processing)
- [Prior briefing: section8.md](./section8.md)
