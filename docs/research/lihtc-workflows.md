# LIHTC (IRC §42) Compliance Workflows: Owner and Property Manager Research

**Date:** 2026-10-19 · **Status:** Research only. No code, data, or accounts touched. Companion to [section8.md](./section8.md), which this document extends and partly corrects (see the last section).

**How to read the confidence labels**

- **[P]** Primary source read in this session (statute, regulation, or HUD/IRS text), linked inline.
- **[S]** Secondary source (industry firm, state agency summary, or vendor page). Useful, but check against the primary text before building logic on it.
- **[U]** Unverified. I could not open the source (PDF extraction failed, or the page returned 404 or empty) or did not find it. Treat as a lead, not a rule.
- **Verify with your state agency.** Anything that varies by state is labeled this way.

---

## 0. The shape of LIHTC compliance

LIHTC is not a subsidy contract. The owner takes a credit allocation from a state housing credit agency (HCA), sells equity to investors, and then promises to keep specific units rent-restricted and occupied by qualified households for a long period. Three clocks run at once:

1. **Compliance period**, 15 taxable years from the first year of the credit period. [P: 26 U.S.C. §42(i)(1)](https://www.law.cornell.edu/uscode/text/26/42)
2. **Extended use period**, which under §42(h)(6)(D) runs 15 years past the end of the compliance period, so about 30 years total for a standard deal. [P: §42(h)(6)](https://www.law.cornell.edu/uscode/text/26/42). Exact tail mechanics (qualified contract, the one-year buyer-search window beginning after year 14) are in §42(h)(6)(I) [P, as excerpted].
3. **Annual certification cycle**, where the owner certifies to the state agency each year that the project met its set-aside for the prior 12 months. [P: 26 CFR §1.42-5(c)(1)](https://www.law.cornell.edu/cfr/text/26/1.42-5)

The IRS does not audit most properties directly. The state HCA monitors, and reports noncompliance to the IRS on Form 8823. [P: §1.42-5 (c)–(d)](https://www.law.cornell.edu/cfr/text/26/1.42-5); [S: Form 8823 context](https://www.nchm.org/irs-form-8823-and-the-8823-guide/)

### At a glance

| Workflow | Cadence | Key docs | Money at risk |
|---|---|---|---|
| 1. Initial Tenant Income Certification (TIC) | Each move-in, before occupancy | State TIC form (IRS does not prescribe one); HUD-50059 is used in some layered deals; verifications; lease | Unit is not a low-income unit from day one. Affects set-aside test and credit for that unit. Form 8823 category 11a-type finding [S] |
| 2. Annual recertification / self-cert / exemption | Annually, unless waived | TIC (recert), verifications or self-cert where allowed, Form 8877 if IRS waiver is sought [S] | Missed recert = Form 8823 finding; if the unit is over-income with no compliance, credits in that year can be lost |
| 3. Student status determination | At each cert | Student affidavit / documentation; §42(i)(3)(D) exceptions | Ineligible unit counted as low-income |
| 4. Next Available Unit / over-income tracking | When an existing household's income rises above 140% (170% deep-rent) | Income tracking log; rent-roll flags; lease for next unit | Unit loses low-income status if the next comparable unit goes to a non-qualified household [P: §1.42-15] |
| 5. Unit transfers and vacancy handling | On each internal move | Transfer TIC; unit status report | Mis-assigned status moves between units [P: §1.42-15(d)] |
| 6. Rent and utility allowance (gross rent) | Each year, plus on UA change | Rent schedule; UA method documentation; annual UA review record | Rent over the cap = overcharge finding, rent credit or refund owed; affects 8823 |
| 7. Income limit / MTSP update | Annually, on HUD release | MTSP table; state limit chart | Late implementation = rent over cap [U timing] |
| 8. Set-aside designation and income averaging | At allocation, annually in the compliance report | Land use restriction agreement (LURA); set-aside election; unit designation list | Missed minimum set-aside = credit loss/recapture exposure [P: §42(g)(1)] |
| 9. Physical inspections and file reviews (state monitoring) | Year 2 after last building placed in service, then at least every 3 years | Agency inspection (NSPIRE or state standard), file review checklist | Correction period, then 8823 filing [P: §1.42-5(c)(2)(iii), (e)] |
| 10. Form 8823 noncompliance reporting and correction | Per finding; filed to IRS | Form 8823 + Pub 5913 guide [U: current version] | Credit recapture if not corrected [S]; investor indemnity (GP/owner) [S] |
| 11. Annual owner certification and state reporting | Annually | Owner annual certification; state portals/forms; unit status / tenant data | Late or false certification = state fines and monitoring escalation |
| 12. HUD annual tenant data (HERA §2835) | Annually via the state HFA | State-submitted tenant data file | Reporting gap; HUD publishes state-level data [S/P summary of HUD docs] |
| 13. Layered deal rules (LIHTC + HOME/PBRA/bonds) | Continuous | Each program's rules; more-restrictive-applies | Conflicting rules = findings under both programs [S] |

---

## 1. Tenant Income Certifications (TIC)

### 1.1 Initial certification

**Steps (cadence: once per household, before move-in or at first occupancy after the building is placed in service).**

1. Confirm the unit is in a designated low-income unit (see §3). Unit must be rent-restricted and designated before the household moves in.
2. Collect household composition: every person who will occupy the unit as a member, including children, live-in aides (who generally are not members for income), and full-time students (see §1.3).
3. Verify each member's income for the 12 months following the effective date (anticipated annual income). The regulation expects a documented method. The federal standard is the HUD Section 8 income definition, which the Treasury regs incorporate by reference. [S: several state manuals say so; the exact incorporation is in §1.42-5 and the state manual. Verify with your state agency.]
4. Verify assets (including imputed income on assets above threshold, where the state uses HOTMA-style rules). [U: how HOTMA changes apply to LIHTC-only buildings is unresolved; see section8.md §5.]
5. Compute annual income. Compare to the income limit for household size and AMI tier (§2).
6. Certify: sign the TIC. Each adult member signs. The owner signs. Keep the verifications in the file.
7. Compute the rent limit for the unit and confirm the tenant's rent plus utility allowance (UA) does not exceed it (§2.4).

**Documents.**

- Tenant Income Certification (state form). Each HCA publishes its own. California (CTCAC) forms page, read via WebFetch this session [P as read: [CTCAC forms](https://www.treasurer.ca.gov/ctcac/compliance/forms.asp)]:
  - Required: Tenant Income Certification (updated April 2021); Tenant Income Certification Questionnaire (July 2022); Under $5,000 Asset Certification (July 2022); Section 42 LIHTC Lease Rider (July 2022); Good Cause Eviction Documents (April 2022); Child/Spousal Support Affidavit (July 2022).
  - If applicable: Tenant Household Information Form (April 2021); Verification of Employment; Certification of Zero Income; Student Verification; Single Parent Full-Time Student Self-Affidavit; Student Financial Aid Verification Form; Foster Care Verification Form; Live-In Aide Verification Form; Separated or Estranged Status Affidavit; Project Status Report (PSR) with PSR A.I.T. Form.
  - HOTMA versions: HOTMA Tenant Income Certification Form (updated December 2025); HOTMA Under $52,787 Asset Certification Form (December 2025).
  - The CTCAC forms page does not list a Unit Status Report or Annual Owner Certification by those names. The owner annual certification is listed on the compliance index page instead. [P as read]
  - Verify with your state agency. Other states' form names differ.
- Verification documents: pay stubs, benefit letters, bank statements, third-party income verification, self-certification where permitted.
- Student status documentation (see §1.3).
- Lease, and the household's signed rent disclosure.
- Unit status record (unit number, bedroom count, set-aside, move-in date).

**Fields that matter on a typical TIC** (names vary by state; the set below is what each form needs in substance):

- Property name, building ID, unit number, bedroom count, unit square footage (for applicable fraction)
- Household member name, age, relationship to head, date of birth, student status (Y/N), full-time student documentation
- Income by source, per member (wages, benefits, asset income, other)
- Total annual anticipated income (sum)
- Asset values and any imputed income
- Applicable income limit (AMI tier, household size) and the limit number used
- Set-aside designation for the unit (e.g., 50% AMI, 60% AMI, averaging tier)
- Gross rent (tenant rent + UA) and the rent limit for that unit
- Move-in date, effective date of certification, next recert due date
- Signatures and dates (each adult member, owner or agent)

### 1.2 Annual recertification

- **Cadence.** Annual, unless the building qualifies for an exemption (§1.4). [P: annual owner certification in §1.42-5(c)(1)]
- **Steps.** Re-verify income for the next 12 months. Compare to the limit for the year (the current year's MTSP table, not the old one). If income is over the limit, see §4 (next available unit). Document the result on a new TIC.
- **Key risk.** Recert paperwork done late, or the unit was not re-certified at all. Form 8823 category 11b (per the 2011 guide's table of contents; see §8) [U: current categories].

### 1.3 Student status

- **Federal rule.** A unit is not disqualified merely because it is occupied by certain students. [P: §42(i)(3)(D)] The exceptions include:
  - Students receiving assistance under Title IV of the Social Security Act (TANF-related, quoted in the statute summary) [P, paraphrased from the excerpt]
  - Students in a job training program receiving assistance under the Job Training Partnership Act (or successor) [P]
  - Full-time students who are single parents with dependents who are not dependents of another individual, and whose children are not full-time students (summarized) [P, see (ii)(I)]
  - Full-time students who are married and file a joint return [P, (ii)(II)]
- **Practical.** Student status is determined on the TIC and must be documented each year. Full-time student status must be checked against the exceptions. [S]
- **Verify with your state agency.** States publish their own student-determination checklists. Example: [CTCAC's student status guidance is in its compliance manual](https://www.treasurer.ca.gov/ctcac/compliance/index.asp) [U: the specific manual section was not opened].

### 1.4 Self-certification and the 100% low-income exemption

- **Federal waiver.** §42(g)(8)(B) lets the Secretary waive annual income recertification for a building where the entire building is occupied by low-income tenants. [P: 26 U.S.C. §42(g)(8)] The waiver is applied for by the owner, with the monitoring agency signing, on Form 8877, under Rev. Proc. 2004-38. Procedure details, from secondary summaries [S]: scope is projects consisting entirely of 100% low-income buildings; owner and agency each complete their part of Form 8877; the agency's signature confirms 100% status; the owner consents to IRS disclosure of later revocation; the waiver takes effect when the IRS signs and generally runs for the rest of the 15-year compliance period unless revoked (revocation on loss of 100% status, a serious violation, or change of federal tax ownership). The form version cited in these summaries is 7-2004; I did not confirm a newer revision. [U] [S: [Rev. Proc. 2004-38](https://www.irs.gov/pub/irs-drop/rp-04-38.pdf) and [Novoco on Form 8877](https://www.novoco.com/news/irs-invites-comments-form-8877-request-waiver-annual-income-recertification); the Rev. Proc. was not opened in full, so verify its current status.] The predecessor procedure is Rev. Proc. 94-64 [S: [NCSHA copy](https://ncsha.org/wp-content/uploads/2018/04/proc_94-64.pdf)].
- **HERA 2008.** State agencies describe the 2008 change (HERA) as an exemption from annual recertification for 100% LIHTC buildings, subject to their own conditions. [S, state agency summaries]. I did not open HERA's text to confirm the wording. [U]
- **State variation (examples, not a survey).**
  - **Maryland:** exemption requires that all units be set aside for tax-credit-eligible families, and 24 months after the end of the calendar year the last building is placed in service, so initial households have been recertified at least once. [S: [MD DHCD procedure](https://dhcd.maryland.gov/HousingDevelopment/Documents/lihtc/Annual-Income-Recertification-Exemption-Procedures.pdf)]
  - **West Virginia:** same 100%-set-aside and 24-month conditions, plus the most recent inspection and file review must be satisfactory. [S: [WVHDF procedure](https://www.wvhdf.com/wp-content/uploads/2018/10/WVHDF-Certification-Waiver-Procedures.pdf)]
  - **New York:** 9 NYCRR §2040.8 says that once initial certifications are done, recertification is not required where 100% of units are LIHTC-qualified, unless the agency finds noncompliance and notifies the owner. [P: [9 NYCRR 2040.8](https://www.law.cornell.edu/regulations/new-york/9-NYCRR-2040.8)]
  - **Verify with your state agency.** Other states may still require annual income certifications. Do not assume the exemption without the agency's written approval.
- **Self-certification.** Some states permit self-certification of assets or income below thresholds. [U: specifics vary; the HOTMA asset self-cert rules apply to HUD programs.]

### 1.5 Next Available Unit Rule (over-income tenants)

- **Threshold.** A unit that was qualified at move-in stays low-income if income later rises, unless it becomes over-income AND a non-qualified household occupies a comparable unit that becomes available in the same building. [P: 26 CFR §1.42-15(b), (c)(1)]
- **Over-income level.** 140% of the applicable income limit for standard projects using the 20-50 or 40-60 tests. 170% for deep-rent-skewed projects (where the applicable limit is 40% AMGI). [P: §1.42-15(a) definitions]
- **Average income test (AIT).** The threshold is 140% of the greater of 60% AMGI or the unit's imputed limit (170% for deep-rent-skewed). [P: §1.42-15(a), (c)(2)] The rule for the next available unit under AIT is in §1.42-15(c)(2). The 2020 proposed AIT regulation is a proposal, not final law. [S: [NCSHA AIT guide](https://www.ncsha.org/wp-content/uploads/Mastering-Average-Income-Test-Compliance.pdf)]
- **Practical rule.** When an over-income unit exists, the owner must rent the next available comparable (equal or smaller) unit to a qualified household. The owner cannot lease it to a non-qualified household without losing low-income status on the over-income unit. [P: §1.42-15(c)(1), (f)]
- **"Vacant unit rule."** The §1.42-15 text does not use that name. The closest provisions are §1.42-15(d) (when a current resident moves within the building, unit status moves with the household) and (h) Example 2 (an over-income resident who moves to an available unit can remain qualified). [P] I did not confirm a separate "140 percent vacant unit" rule. [U]
- **Documentation.** Some states require a file note when the next available unit is rented. [S: [Georgia DCA next-available-unit form](https://dca.georgia.gov/document/forms/next-available-unit-lihtc/download)]

### 1.6 Unit transfers

- A transfer is a new move-in for TIC purposes if the household changes unit. [U: the exact rule for internal transfers varies by state; verify with your state agency.]
- Under §1.42-15(d), the over-income status moves with the household. [P]
- Record the transfer on the unit status report and on a new TIC.

### 1.7 Household size and the income limit

- **Imputed household size.** For rent limit purposes, the unit's imputed household size is typically bedrooms × 1.5 (a studio counts as one person). Blended limits average the two adjacent household-size limits. [S: [City of Madison rent-limit export](https://www.cityofmadison.com/council/district10/documents/rent-limits-export.pdf), which applies the MTSP convention. The federal source for the 1.5 rule was not opened. Verify with your state agency and the current HUD MTSP table.]
- **Household size for income limit.** The actual household (not the imputed one) is used to pick the income limit row, for the TIC. [S]
- **Gross rent.** Rent (plus UA) may not exceed 30% of the imputed income limit for the unit. [S: same Madison source] This is the number to recompute each year.

---

## 2. AMI, income limits, rent limits, and utility allowances

### 2.1 Income limits and the MTSP table

- HUD publishes Multifamily Tax Subsidy Project (MTSP) income limits each year for LIHTC and tax-exempt bond deals. [P/S: [HUD MTSP dataset page](https://www.huduser.gov/portal/datasets/mtsp.html). The page was empty when fetched in this session. Verify the current release.]
- Several states publish their own limit charts (for example, [CTCAC's 2026 income limits](https://www.treasurer.ca.gov/ctcac/compliance/index.asp) appear on its page as "2026 Income Limits and Maximum Rents"). [P: page lists the document; contents not opened]
- **Implementation deadline for new limits.** Owners must adopt new limits by the later of the limits' effective date or 45 days after HUD publishes them, per Rev. Proc. 94-57. [S: search summary citing Rev. Proc. 94-57; the Rev. Proc. itself was not opened; secondary sources give the 2025 example of HUD publishing April 1, 2025 and a May 16, 2025 deadline.] Verify the 2026 release date on HUD's MTSP page (the page was empty on fetch). [U for 2026 date]

### 2.2 Set-asides (minimum set-aside tests)

- **20-50 test.** At least 20% of units rent-restricted and occupied by households at or below 50% AMI. [P: §42(g)(1)(A)]
- **40-60 test.** At least 40% of units rent-restricted and occupied by households at or below 60% AMI. [P: §42(g)(1)(B)]
- **Income averaging.** At least 40% of units (25% for §142(d)(6) projects) average at or below 60% AMI, with each unit designated at 20%, 30%, 40%, 50%, 60%, 70%, or 80% AMI, and the average of the designated limits capped at 60%. [P: §42(g)(1)(C)(i), (ii)(II)]
- **Deep-rent-skewed (15/40).** Owners may elect 15% of units at 40% AMI (described in §142(d)(4)(B)). [P/S: statute cross-reference; verify the current text and state treatment]
- **Layered state set-asides.** The LURA may impose stricter set-asides (for example, a 10% at 30% AMI tier). [S] Verify with your state agency.

**Applicable fraction.** The percentage of qualified basis attributable to low-income units. The unit fraction (units) and floor-space fraction (square footage) are the two variants. The lesser of the two governs. [S; the statute's applicable fraction definition is in §42(c)(1); verify exact method in the state manual.]

### 2.3 Rent and income limit by bedroom (worked form)

For each unit:

1. Look up the unit's bedroom count and designated AMI tier.
2. Compute the imputed household size (bedrooms × 1.5).
3. Find the MTSP income limit at that household size for the county.
4. Gross rent limit = 30% × imputed income limit ÷ 12, rounded down. [S: Madison export describes the convention]
5. Subtract the UA to get the maximum tenant rent.

Example structure (illustrative only, not a real limit): a 2-bedroom unit at 60% AMI has an imputed household size of 3. The rent limit is 30% of the 60% AMI income limit for 3 persons, divided by 12. [S]

### 2.4 Gross rent = tenant rent + utility allowance

- **Definition.** Gross rent includes the tenant's rent plus the utility allowance for tenant-paid utilities, plus any mandatory fees. [P/S: §42(g)(2) defines rent-restricted by gross rent; the mandatory fee rule is in IRS regulations and state manuals]
- **Utility allowance methods.** [P: §1.42-10(b)(4)]
  - **(i) PHA allowance** for units with tenants receiving HUD rental assistance.
  - **(ii)(A) PHA allowance** (general rule for non-RHS, non-HUD-regulated buildings where the owner selects it).
  - **(ii)(B) Utility company estimate**, a written estimate for each utility, for a unit of similar size and construction. [S: HUD HOMEfires, cited in search results]
  - **(ii)(C) Agency estimate** (the HCA may set one).
  - **(ii)(D) HUD Utility Schedule Model (HUSM)**.
  - **(ii)(E) Energy consumption model**, which must consider unit size, orientation, design, mechanical systems, appliances, and location. [S: NJ DCA guidance]
- **Timing.** A new UA must be used to compute gross rent 90 days after the change. Owners need not implement new allowances until the building reaches 90% occupancy for 90 consecutive days or the end of the first year of the credit period, whichever is earlier. [P: §1.42-10(c)(1)]
- **Annual review.** The owner must review the UA basis at least once per calendar year. [P: §1.42-10(c)(2)]
- **Correction to the research brief.** The 45-day UA window was in the task brief, not in section8.md. The regulation says 90 days (see above). [P]

### 2.5 Placed-in-service and which limits apply

- The credit period begins on the placed-in-service date (or the later election). Which income limits apply to a new project depends on the year of the allocation or placed-in-service date, and the state's hold-harmless rules. [S] Hold-harmless: once a project has a limit, the limit can be held at its initial level for a set number of years. [S: the Madison export references a 04/01/2025 placed-in-service hold-harmless provision]. Verify with your state agency.

---

## 3. Compliance period, extended use, and recapture

### 3.1 Years 1-15 (compliance period)

- The project must keep its minimum set-aside (§2.2) throughout the 15-year compliance period. [P: §42(i)(1), (g)(1)]
- Credit is claimed over 10 years (the credit period). [S]
- Owner annual certifications are the main check. [P: §1.42-5(c)]
- **Recapture.** If the project fails to meet its set-aside or other requirements during the compliance period, the IRS may recapture part of the credits previously claimed. [S: recapture is in §42(j); the statute text was not opened. Verify the calculation with the investor's tax counsel.]

### 3.2 Years 16-30 (extended use period)

- The LURA continues the restriction for 15 more years (under §42(h)(6)(D)). [P]
- Recapture under §42 generally ends after the compliance period. The extended use period is enforced by the state through the LURA, not by IRS recapture. [S, verify]
- **Qualified contract.** After year 14, the owner can request that the HCA find a buyer, and the state has a one-year window to find a qualified buyer. If it does not, the restriction may end. [P: §42(h)(6)(F), (I) as excerpted; verify the qualified-contract procedure in the state's plan]
- Some states have stricter extended use terms. [S] Verify with your state agency.

### 3.3 Where errors cost the most

- Credit loss or recapture in years 1-15, which the investor's indemnity pushes to the GP/owner. [S]
- Default under the LURA in years 16-30 (state enforcement, possible loss of compliance status). [S]

---

## 4. Form 8823, monitoring, and correction

### 4.1 Monitoring (state HCA)

- **Scope.** The HCA must review certifications, conduct on-site inspections, and review tenant certifications, supporting documentation, and rent records. [P: §1.42-5(c)(2)(i)-(ii)]
- **Timing.** First inspection and review of all buildings by the end of the second calendar year after the last building is placed in service, then at least once every three years. [P: §1.42-5(c)(2)(iii)(A)]
- **Sample size.** The HCA must review at least the minimum number of units in a table keyed to project size (from 1 unit for a 1-unit project up to 27 units for 1,462-9,999 low-income units). [P: §1.42-5(c)(2)(iii)(B)]
- **Correction on the sample.** The 20% figure in section8.md is not a general rule in the regulation. The only 20% reference is an example for RHS-financed buildings. [P] Section8.md's "lesser of 20% of units or the minimum unit sample size" is wrong as written. See the corrections section.
- **Random selection.** Units to inspect are selected randomly. [P: §1.42-5(c)(2)(iii)(C)(1)]
- **Access.** The HCA's right of access runs at least through the end of the compliance period. [P: §1.42-5(d)(1)]
- **Inspection standard.** Units must be suitable for occupancy under local codes or HUD's uniform physical condition standards. [P: §1.42-5(d)(2)]

### 4.2 NSPIRE and inspection standards

- HUD's NSPIRE (National Standards for the Physical Inspection of Real Estate) replaces UPCS and HQS for HUD programs. [S: [Habitat Group on NSPIRE](https://www.thehabitatgroup.com/nspire-inspection-protocols-to-replace-upcs-hqs-standards)]
- The 2026 HOME/HTF Federal Register notice says the NSPIRE compliance date for CPD programs was pushed from October 2025 to October 1, 2026. [S: search summary; the Federal Register notice was not opened]
- **LIHTC switch.** Secondary sources say §1.42-5 points to the physical standards at 24 CFR 5.703, which HUD has moved to NSPIRE, replacing UPCS. [S: search summary citing Habitat Group commentary; the regulation paragraph was not confirmed from primary text] State agencies may still choose local codes or UPCS for LIHTC inspections, per the same commentary. [S]
- **Open item at the IRS.** NCSHA's comments on the IRS priority guidance plans for 2024-2025 and 2025-2026 asked the IRS to clarify NSPIRE's application to the Housing Credit and to remove the word "uniform" from §1.42-5. [S: NCSHA comment letters] I found no published IRS notice or regulation from 2025 or 2026 that settles the question. [U]
- **Notice mismatch flagged by NCSHA.** NSPIRE provides a 28-day reasonable notice period, while the Housing Credit regulations provide 15 days. [S: NCSHA comments] Verify with your state agency.

### 4.3 Form 8823 and the Guide

- **Form 8823.** The HCA reports noncompliance and building dispositions to the IRS on this form. [P/S: IRS form page was not reachable in this session (404). The form and guide are at IRS.gov.]
- **Pub 5913 (Guide for Completing Form 8823).** The current version is not confirmed. The most recent copies I found are older state-hosted versions (2009, 2011). [U] Confirm the current revision at [IRS Pub 5913](https://www.irs.gov/pub/irs-pdf/p5913.pdf) (the PDF did not extract to text in this session).
- **Filing.** The form must be filed regardless of whether the owner corrected the noncompliance, per the 2011 guide. [S: [Form 8823 guide (2011 rev.)](https://ohiohome.org/compliance/IRS/8823guide_10-09.pdf) is the 2009 Ohio copy; the 2011 version was seen in search results]. Timing: no later than 45 days after the building was disposed of or the correction period ended, per an older form instruction. [S, U for current form]
- **Categories.** The 2011 guide's table of contents shows sections for 11a (household income exceeding limit at initial occupancy), 11b (annual recertification / income recertification handling), and 11c (physical inspection violations). [S: search summary of the 2011 guide]. Section8.md says there are 17 possible categories and eight can cause credit loss. **I could not confirm the total or the credit-loss subset.** [U]
- **Other categories to check against the current Pub 5913:** building-level set-aside failures, residential rental property status, tenant file documentation, and building disposition. [U]

### 4.4 Correction period

- **Federal rule.** The correction period is not to exceed 90 days from the notice to the owner. The HCA may extend it up to six months for good cause. [P: §1.42-5(e)(2), (e)(4)]
- **Result.** If corrected, the HCA files a corrected 8823 or closes the finding. If not, recapture risk applies. [S]

### 4.5 Money at risk (what is published)

- **Recapture formula.** Accelerated recapture of credits already taken, plus interest and penalties, is the usual description. [S: [Legal Clarity on 8823](https://legalclarity.org/what-is-the-8823-form-and-how-to-correct-noncompliance/)]
- **Investor indemnity.** The general partner often indemnifies the investor. [S, claim in section8.md; not verified here]
- **Dollar examples.** I did not find a published, reliable dollar figure for a typical recapture event. [U] Use this as a question for interviews, not a number in the product.

---

## 5. Form 8609, Schedule A, and Form 8586 (credit administration)

- **Form 8609.** The HCA issues this certification of credit allocation for each building. It is the starting point for the owner's compliance file. [S, form name; not opened]
- **Schedule A.** Attached to Form 8609 for multi-building projects (building-level information). [S, U for details]
- **Form 8586.** The owner's annual credit claim form filed with the tax return. [S, U]
- **Compliance link.** The 8609 and LURA define the set-aside and the compliance period dates the monitoring uses. [S]

---

## 6. State agency reporting

### 6.1 Annual owner certification

- **Federal basis.** The owner certifies at least annually that the project met the minimum set-aside and other §42 requirements for the prior 12 months. [P: §1.42-5(c)(1)]
- **Common content.** Unit-by-unit occupancy status, household income, rent, set-aside designation, vacancy, and whether any noncompliance was found. [S]
- **Example (California, CTCAC).** The compliance page lists a "2025 Annual Owner Certification" and says owners must report complete and accurate project information annually. [P as read: [CTCAC compliance page](https://www.treasurer.ca.gov/ctcac/compliance/index.asp)]

### 6.2 Tenant data and unit status

- **Unit status reports and tenant data.** Usually submitted through state portals or spreadsheets. Names vary (for example, WCMS, Procorem, or state-specific systems). [S, verify each state's system]. I did not confirm WCMS or Procorem for any specific state in this session. [U]
- **HUD annual tenant data (HERA §2835).** Each HFA that administers LIHTC must send HUD annual tenant data. The data covers race, ethnicity, family composition, age, income, use of rental assistance, disability, and monthly rent. [S: [NCHM on HUD data collection](https://www.nchm.org/hud-data-collection-for-lihtc/); [HUD LIHTC tenant data documentation](https://www.huduser.gov/portal/Datasets/lihtc/LIHTC-TenantDataDocumentation.pdf) (not opened in full)]
- **Forms and renewal.** HUD's LIHTC collection uses HUD-52695 (Property Data Collection Form) and HUD-52697 (Tenant Data Collection Form). HUD did not require specific forms, so states could fold the data into their own forms. [S: search summary of HUD notices] HUD published a 60-day notice (Federal Register 2025-09866) and a 30-day notice (2025-21929) on renewing the collection, OMB Control No. 2528-0320. I did not confirm final OMB approval or the current submission deadline. [S/U]
- **Owner's role.** The owner collects the data at move-in and at recert; the state transmits to HUD. [S] HUD's 2010 notice let states fold the required data into existing forms; after initial certification, only data at recerts and new move-ins are required. [S] Some states' submissions have been incomplete. [S]
- **Demographic collection.** The CTCAC page lists "HUD Tenant Demographic Data Collection" guidance (Oct. 2025). [P as read; content not opened]

### 6.3 State agency examples: what they require

These are examples of what states publish. I did not open every form; links are to pages I reached or pages from search results. Verify with your state agency before relying on any form name.

| State HFA | What I could confirm | Link |
|---|---|---|
| California (CTCAC) | Compliance forms and manual; 2025 Annual Owner Certification; rent increase waiver forms; AIT guidance; 2026 income limits; joint monitoring of co-regulated projects (AB 2006) [P as read] | [CTCAC compliance](https://www.treasurer.ca.gov/ctcac/compliance/index.asp) |
| Maryland (DHCD) | Annual income recertification exemption procedure [S] | [MD procedure](https://dhcd.maryland.gov/HousingDevelopment/Documents/lihtc/Annual-Income-Recertification-Exemption-Procedures.pdf) |
| New York (HCR) | 9 NYCRR 2040.8 annual certification rule [P] | [9 NYCRR 2040.8](https://www.law.cornell.edu/regulations/new-york/9-NYCRR-2040.8) |
| West Virginia (WVHDF) | Certification waiver procedure [S] | [WVHDF procedure](https://www.wvhdf.com/wp-content/uploads/2018/10/WVHDF-Certification-Waiver-Procedures.pdf) |
| Ohio (OHFA) | Utility allowance policy (2022); compliance manual [S] | [OHFA UA policy](https://www.ohiohome.org/compliance/documents/utilityallowancepolicy-2022.pdf) |
| Texas (TDHCA) | 10 TAC §10.1004 (housing tax credit properties) [S, found in search, not opened] | [10 TAC 10.1004](https://www.law.cornell.edu/regulations/texas/10-Tex-Admin-Code-SS-10-1004) |
| Florida, Michigan, others | Not checked in this session. Section8.md cites MSHDA's noncompliance chapter, which is a PDF I could not extract. [U] | [MSHDA ch. 10](https://www.michigan.gov/mshda/-/media/Project/Websites/mshda/rental/Property-Managers/Compliance-for-Rental-Housing/Manuals-Policies-and-Codes/LIHTC-Compliance-Manual/CM-Chapter-10-Noncompliance.pdf) |

**Gap.** I did not reach a current IRS Form 8823 PDF, Pub 5913, or a complete list of state form names with their current revision dates. These are the first things to pull directly before building anything.

---

## 7. Layered deals (LIHTC + Section 8, HOME, bonds)

- **Rule.** Where two programs apply to the same unit, the more restrictive requirement governs. [S: [ND HFA on LIHTC + Section 8](https://www.ndhfa.org/wp-content/uploads/2019/04/Section8PropertieswithTaxCredits.pdf), as cited in section8.md]
- **Common layers.** LIHTC + PBRA; LIHTC + HOME (HOME uses its own income limits and rent limits); LIHTC + tax-exempt bonds (MTSP limits apply). [S]
- **Income limits.** HOME, PBRA, and LIHTC each use their own income limit table. Using the wrong table is the most common layered-deal error. [S]
- **Rent.** The lower of the applicable rent limits governs. [S]
- **Verify with your state agency and the program's own rules.** Program-specific rules override general summaries.

---

## 8. Corrections to section8.md

Section8.md is dated 2026-10-04. Corrections from this session's primary-source checks:

1. **Inspection sample size.** Section8.md says the HCA inspects "the lesser of 20% of units or the IRS Minimum Unit Sample Size." The regulation uses a table of minimum units by project size. The 20% figure is not a general rule. [P: §1.42-5(c)(2)(iii)(B)]
2. **UA implementation window.** Section8.md does not give a UA window. The 45-day figure for UA changes appeared in the task brief, and it is wrong: the regulation says 90 days for a UA change. [P: §1.42-10(c)(1)]
3. **MTSP implementation window.** Section8.md says owners must implement new MTSP limits within 45 days. Supported by a secondary summary of Rev. Proc. 94-57: the later of the effective date or 45 days after HUD publishes. [S] Confirm against the Rev. Proc. itself.
4. **Annual recert exemption.** Section8.md says annual recert is "generally required" for mixed-income and deep-rent-skewed projects, not 100% buildings. That is directionally right, but the federal basis is §42(g)(8)(B) waiver through an IRS/agency procedure (Form 8877, Rev. Proc. 2004-38), with state conditions (MD, WV, NY examples). An exemption is not automatic. [P/S]
5. **Form 8823 categories.** Section8.md says 17 possible failures and eight that can cause credit loss. I could not confirm these numbers. [U]
6. **Form 8823 categories named.** Section8.md's 11a/11b/11c mapping matches the 2011 guide's table of contents, but the current Pub 5913 may differ. [U]
7. **Recapture.** Section8.md describes the recapture mechanism as accelerated recapture plus interest and penalties. Consistent with the secondary source; not verified against §42(j). [S]
8. **Retention.** Section8.md says state agencies keep owner records for three years. Not verified. [U]
9. **HERA 2008.** Section8.md describes a HERA exemption without naming a source. The federal waiver is in §42(g)(8)(B). HERA's text not verified. [U]
10. **Student rule.** Section8.md did not cover the student rule. The LIHTC student rule is in §42(i)(3)(D). [P]
11. **Next available unit.** Section8.md did not cover the rule. It is in §1.42-15 and uses 140% (170% deep-rent). [P]

---

## 9. Where document extraction and validation helps

Concrete cross-document checks the product could run. Each assumes the document fields in §1.1 and §2. These are the checks to build, prioritized.

1. **TIC income vs verifications sum.** For each household member, the sum of income line items on the TIC must equal the sum of the verification documents (pay stubs annualized, benefit letters, asset income). Flag any gap over $1 or any missing source.
2. **TIC rent + UA vs bedroom rent limit for that year and AMI tier.** Gross rent (tenant rent + UA) must not exceed 30% of the imputed income limit for the unit's bedroom count and the MTSP limit for the year and designated AMI. Flag over-limit units. Check the UA method and date against §1.42-10(c).
3. **Household size vs income limit row.** The actual household size on the TIC must pick the right income limit row. Flag if the limit used does not match the household size, or if a child or member is listed in the household but absent from the income limit lookup.
4. **Rent roll vs TIC.** For every unit on the rent roll, the tenant name, move-in date, rent, UA, and set-aside designation must match the most recent TIC. Flag any mismatch, and flag any unit with no TIC on file.
5. **Unit set-aside designation vs income averaging target.** Each unit's designated AMI (from the LURA or unit designation list) must match the TIC's set-aside field. For averaging projects, the average of designated limits must stay at or below 60%. Flag a unit whose TIC income is over its designated limit and check whether the next available unit rule applies (140% / 170% threshold).

Other useful checks, lower priority:

- Recert due date vs last TIC effective date: flag any unit whose annual recert is past due.
- Student status on TIC vs §42(i)(3)(D) exceptions: flag a student-only household with no documented exception.
- Household composition change without a new TIC (interim change): flag when the rent roll shows a new occupant not on the TIC.
- Placed-in-service date vs applicable MTSP year and hold-harmless flag: flag limits that use the wrong year.
- Unit count and bedroom count on the rent roll vs the unit designation list: flag mismatches before the annual owner certification.

**Build caution.** None of these checks is legal advice. The product should show the rule source for each flag (regulation paragraph, state manual section, or MTSP table) and let the owner decide. Mark every state-specific rule "Verify with your state agency."

---

## Open questions for the next pass

1. Current Form 8823 and Pub 5913 (revision date, full category list, credit-loss subset). Needs a readable copy; the IRS PDF did not extract in this session.
2. Current MTSP release date and the implementation window (45 days or other) for new limits.
3. Whether any state HCA now requires NSPIRE for LIHTC monitoring, and the effective date.
4. HERA §2835 text and HUD's current tenant data guidance.
5. The 1.5-persons-per-bedroom convention: confirm the primary source (Treasury/IRS or HUD MTSP).
6. Current Rev. Proc. 2004-38 status and any update to Form 8877.
7. Whether the 2020 AIT proposed regulation has been finalized.
8. Dollar figures for recapture and 8823 penalties (none verified).

---

## Sources

**Primary (read in this session)**

- [26 U.S.C. §42 (Cornell LII)](https://www.law.cornell.edu/uscode/text/26/42)
- [26 CFR §1.42-5 (Cornell LII)](https://www.law.cornell.edu/cfr/text/26/1.42-5)
- [26 CFR §1.42-10 (Cornell LII)](https://www.law.cornell.edu/cfr/text/26/1.42-10)
- [26 CFR §1.42-15 (Cornell LII)](https://www.law.cornell.edu/cfr/text/26/1.42-15)
- [26 CFR §1.42-9 (Cornell LII)](https://www.law.cornell.edu/cfr/text/26/1.42-9)
- [9 NYCRR §2040.8 (Cornell LII)](https://www.law.cornell.edu/regulations/new-york/9-NYCRR-2040.8)
- [CTCAC compliance page](https://www.treasurer.ca.gov/ctcac/compliance/index.asp)

**Primary (linked but not read, or not readable in this session)**

- [IRS Pub 5913, Guide for Completing Form 8823](https://www.irs.gov/pub/irs-pdf/p5913.pdf) (PDF did not extract)
- [Rev. Proc. 2004-38](https://www.irs.gov/pub/irs-drop/rp-04-38.pdf)
- [HUD MTSP dataset page](https://www.huduser.gov/portal/datasets/mtsp.html) (returned empty)
- [HUD LIHTC tenant data documentation](https://www.huduser.gov/portal/Datasets/lihtc/LIHTC-TenantDataDocumentation.pdf)
- [MSHDA LIHTC Compliance Manual ch. 10](https://www.michigan.gov/mshda/-/media/Project/Websites/mshda/rental/Property-Managers/Compliance-for-Rental-Housing/Manuals-Policies-and-Codes/LIHTC-Compliance-Manual/CM-Chapter-10-Noncompliance.pdf) (not opened)

**State and agency (secondary or partial)**

- [Maryland DHCD annual recert exemption procedure](https://dhcd.maryland.gov/HousingDevelopment/Documents/lihtc/Annual-Income-Recertification-Exemption-Procedures.pdf)
- [WVHDF certification waiver procedure](https://www.wvhdf.com/wp-content/uploads/2018/10/WVHDF-Certification-Waiver-Procedures.pdf)
- [OHFA utility allowance policy 2022](https://www.ohiohome.org/compliance/documents/utilityallowancepolicy-2022.pdf)
- [NJ DCA 2012 utility allowance guidance](https://www.nj.gov/dca/hmfa/developers/docs/lihtc/compliance/utilityallowance/2012_util.pdf)
- [Ohio 8823 guide (2009)](https://ohiohome.org/compliance/IRS/8823guide_10-09.pdf)
- [South Carolina 8823 guide](https://www.schousing.sc.gov/sites/schousing/files/Documents/Development/Manuals%20and%20Forms/Guide-for-Completing-Form-8823.pdf) (not opened)
- [NYC HPD 8823 guide](https://www.nyc.gov/assets/hpd/downloads/pdfs/services/8823-Guide.pdf) (not opened)
- [Georgia DCA next-available-unit form](https://dca.georgia.gov/document/forms/next-available-unit-lihtc/download)
- [Texas 10 TAC §10.1004](https://www.law.cornell.edu/regulations/texas/10-Tex-Admin-Code-SS-10-1004) (not opened)
- [City of Madison rent-limit export](https://www.cityofmadison.com/council/district10/documents/rent-limits-export.pdf)
- [NCSHA: Mastering Average Income Test Compliance](https://www.ncsha.org/wp-content/uploads/Mastering-Average-Income-Test-Compliance.pdf) (not opened)
- [NCSHA copy of Rev. Proc. 94-64](https://ncsha.org/wp-content/uploads/2018/04/proc_94-64.pdf) (not opened)

**Industry (secondary)**

- [Novoco: Form 8877 waiver comment request](https://www.novoco.com/news/irs-invites-comments-form-8877-request-waiver-annual-income-recertification)
- [NCHM: Form 8823 and the 8823 Guide](https://www.nchm.org/irs-form-8823-and-the-8823-guide/)
- [NCHM: HUD data collection for LIHTC](https://www.nchm.org/hud-data-collection-for-lihtc/)
- [Habitat Group: NSPIRE replaces UPCS/HQS](https://www.thehabitatgroup.com/nspire-inspection-protocols-to-replace-upcs-hqs-standards)
- [Legal Clarity: Form 8823 and correcting noncompliance](https://legalclarity.org/what-is-the-8823-form-and-how-to-correct-noncompliance/)
- [ND HFA: LIHTC + Section 8 layering](https://www.ndhfa.org/wp-content/uploads/2019/04/Section8PropertieswithTaxCredits.pdf)

**Earlier briefing**

- [section8.md](./section8.md) (2026-10-04)
