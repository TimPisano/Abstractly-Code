# Affordable Housing Compliance: Founder's Briefing

**Date:** 2026-10-04 · **Status:** Research only. Everything here is sourced from public material and linked inline. Nothing has been confirmed with a practitioner yet — the interview bank at the end is how you do that.

---

## 1. Three programs that get called "affordable housing"

They are not variants of one thing. They have different money, different rulebooks, and different people doing the paperwork. Most confusion in this market comes from conflating them.

| | **Housing Choice Voucher (HCV)** | **Project-Based Section 8 (PBRA)** | **LIHTC** |
|---|---|---|---|
| What the subsidy attaches to | The *household*. Tenant takes it to any landlord who accepts it. | The *building*. A long-term HAP contract covers specific units. | Nothing — it's a *tax credit* paid to the owner's investors up front. |
| Who gets the money | Landlord, via the PHA | Owner, via HUD/contract administrator | Owner's equity investor, as credits over 10 years |
| Governing rulebook | 24 CFR Part 982, PHA Administrative Plan | HUD Handbook 4350.3 | IRC §42, Treas. Reg. §1.42-5, state agency manual |
| Tenant rent | ~30% of adjusted income | ~30% of adjusted income | A **fixed capped rent** (not income-based) |
| **Who does the certification paperwork** | **The PHA** | **The owner / management agent** | **The owner / management agent** |
| Who audits | HUD (via SEMAP, PHA oversight) | HUD or a PBCA, via Management & Occupancy Review | State housing finance agency, reporting to IRS |

**Housing Choice Voucher.** The [PHA does nearly all of it](https://files.hudexchange.info/resources/documents/PIH-HCV-Landlord-The-PHA-Role-in-the-Housing-Choice-Voucher-Program.pdf): waiting lists, applications, eligibility, voucher issuance, unit approval, and contracts with landlords. The landlord's paperwork is thin — they complete and sign part of the Request for Tenancy Approval (RFTA), then the PHA inspects the unit, runs a rent reasonableness determination, and prepares the lease and HAP contract ([PHA process detail](https://www.pha.phila.gov/wp-content/uploads/2021/12/rfta_instruction_guide_2018.pdf)). The PHA, not the owner, [reexamines family income and composition at least annually](https://www.govinfo.gov/content/pkg/CFR-2019-title24-vol4/xml/CFR-2019-title24-vol4-part982.xml). Data goes to HUD on **form HUD-50058**, submitted to IMS/PIC.

**Project-based Section 8 (PBRA).** Here the burden flips. Under PBRA, [property managers handle income recertifications and eligibility verification directly](https://www.nchm.org/what-is-project-based-section-8/) rather than waiting on a PHA. Certifications are made on **form HUD-50059** and transmitted to **TRACS** as MAT10 records; monthly subsidy vouchers go up as HUD-52670/52670-A (MAT30) ([form/system mapping](https://files.hudexchange.info/resources/documents/TRACS-Tip-Sheet.pdf)). Section 202/8 properties work the same way. This is the segment with the heaviest recurring document workload per unit.

**Project-Based Vouchers (PBV)** are a fourth thing and a common source of error: voucher rules and a PHA administrator, but attached to specific units. [HUD treats HCV, PBRA, and PBV as distinct programs.](https://www.nchm.org/what-is-project-based-section-8/)

**LIHTC.** No rent subsidy and no HUD contract — the owner just promises to keep rents and incomes under caps for 15–30+ years. The owner certifies each household on a **Tenant Income Certification (TIC)** at move-in, and [family income is determined using HUD Section 8 rules](https://ohiohome.org/compliance/documents/OHFA-Compliance-Manual.pdf) — which is why HUD rule changes ripple into LIHTC. The owner then [certifies annually to the state agency](https://www.oregon.gov/ohcs/compliance-monitoring/Documents/compliance/lihtc/LIHTC%20Compliance%20Manual%202025.pdf) that the project met §42 requirements for the prior 12 months.

**The real world is layered.** A single unit can carry LIHTC restrictions *and* a PBRA contract *and* house a voucher holder. The rule is that an applicant [must meet the requirements of both programs, and where requirements conflict, the more restrictive one applies](https://www.ndhfa.org/wp-content/uploads/2019/04/Section8PropertieswithTaxCredits.pdf). Layered deals are where compliance staff spend their worst days — and where software mostly doesn't help.

---

## 2. Income certification and recertification, step by step

### Initial certification (PBRA / LIHTC — owner-run)

1. **Intake.** Application with date/time received, plus form HUD-92006 (Supplement to Application) ([file documentation standard](https://www.ndhousing.nd.gov/sites/www/files/documents/Forms/TenantFileDocumentation.pdf)).
2. **Consent.** Forms **HUD-9887 and 9887-A** signed by every household member 18 or over.
3. **Screening.** Household composition, SSNs for all members, citizenship/eligible-noncitizen status, student rules, and an EIV existing-tenant search.
4. **Third-party verification**, in HUD's order of preference — income, then assets, then deductions ([same source](https://www.ndhousing.nd.gov/sites/www/files/documents/Forms/TenantFileDocumentation.pdf)). Critically: [verifications are valid 120 days from the date the owner receives them](https://legalclarity.org/how-the-hud-annual-recertification-process-works/), not from the certification effective date.
5. **Calculate.** Annual income → adjusted income (deductions) → tenant payment. [The first step is determining annual income for the previous 12-month period per 24 CFR §5.609(a)-(b)](https://legalclarity.org/how-the-hud-annual-recertification-process-works/). For LIHTC, the output is a pass/fail against the published income limit, and rent is set at the cap rather than from income.
6. **Execute.** Lease plus HUD-50059 / TIC. The owner [must obtain original signatures from the head, co-head, spouse, and all other adult members](https://legalclarity.org/how-the-hud-annual-recertification-process-works/) and give the tenant a copy.
7. **Transmit.** MAT10 to TRACS (PBRA); state agency reporting (LIHTC).

### Annual recertification (PBRA)

The notice cascade is the thing software should own, and the thing that most often fails:

- **120 days out:** first reminder notice to the resident ([required](https://legalclarity.org/how-the-hud-annual-recertification-process-works/)).
- **90 days out:** second reminder if nothing came back. Then 60- and 30-day notices.
- **Within 120 days of the effective date:** pull the **EIV Income Report** — [it must be pulled within that window to be considered current](https://legalclarity.org/how-the-hud-annual-recertification-process-works/) — and reconcile every discrepancy *in writing, in the file*.
- Verify changes, recalculate, prepare the 50059, collect signatures. A tenant is [considered late if required 50059 signatures aren't provided by the recertification date](https://legalclarity.org/how-the-hud-annual-recertification-process-works/).
- Separately each year: gross rent / utility allowance analysis.

### Interim recertifications

Triggered mid-year by changes in income or household composition. HOTMA reset the trigger — see §5.

### HCV annual reexamination

Same arithmetic, different owner: the PHA sends the packet, the tenant returns documents, the PHA verifies and recalculates, and the tenant [gets a written notice listing the recertification date and required documents](https://voucherready.com/articles/voucher-basics/what-happens-during-a-section-8-annual-recertification). Physical inspections run on the PHA's own cycle.

### LIHTC annual cycle

Owner certification to the state agency, unit status reporting, student-status certifications, and implementation of new income limits — tax credit rules require owners to [implement new MTSP limits within 45 days of the effective date](https://www.huduser.gov/portal/datasets/il.html). **Important quirk to verify in diligence:** annual *income* recertification is generally required for mixed-income and deep-rent-skewed projects, not 100%-affordable buildings ([OHFA manual](https://ohiohome.org/compliance/documents/OHFA-Compliance-Manual.pdf)). State agencies vary; confirm against the specific state manual before building logic around it.

---

## 3. What a tenant file contains

A PBRA file, roughly in order ([ND Housing](https://www.ndhousing.nd.gov/sites/www/files/documents/Forms/TenantFileDocumentation.pdf), [NCHFA](https://www.nchfa.com/rental-housing-partners/rental-owners-managers/policies-resources-forms/resident-files), [Maine Housing](https://www.mainehousing.org/docs/default-source/property-mgmt/required-documents-for-section-8-files.pdf)):

- Application with date/time stamp; HUD-92006 supplement
- Signed HUD-9887 and 9887-A for every adult
- SSN verification for all members; citizenship/eligible-noncitizen documentation
- Executed **HUD-50059 / 50059-A** (move-in and each recertification)
- Third-party verifications: income, assets, deductions — plus affidavits where third-party verification failed
- **EIV reports**: Summary, Income, 90-day New Hires, discrepancy reports — *with written resolution notes*
- Disposal-of-assets declaration
- Lease and all addenda; house rules; pet agreement
- Annual acknowledgement of receipt of rights and responsibilities materials
- Race/ethnicity self-certification
- Student status documentation (and recertification of it)
- Reasonable accommodation requests and the owner's response
- Interim recertification documentation; unit transfer records

LIHTC files replace the 50059 with the TIC and add the rent/income limit documentation for the certification year. Retention: state agencies [keep owner certifications and records for three years from the end of the calendar year received](https://www.nhhfa.org/wp-content/uploads/2019/08/LIHTC_Compliance_Monitoring.pdf); owner-side retention is longer and set by program.

---

## 4. Why files fail, and what failure costs

### PBRA — Management & Occupancy Review (MOR)

Reviewers use **form HUD-9834**. The recurring findings, per practitioners who review these files for a living:

1. **EIV discrepancies** — reports printed but never reconciled in writing, or reports older than 30 days with no follow-up note. One firm reports [EIV errors account for nearly half of all findings](https://www.navigatehousing.com/common-mor-findings-to-avoid-on-property/).
2. **Late recertifications** — effective-date errors, missed 120/90/60/30-day notices, interim recerts not triggered when income or composition changed.
3. **Missing forms and signatures** — no signed 9887/9887-A, expired student documentation, missing race/ethnicity self-certification ([same source](https://www.navigatehousing.com/common-mor-findings-to-avoid-on-property/)).
4. **Undocumented conversations** — especially [reasonable accommodation requests where staff never wrote down a verbal exchange](https://www.navigatehousing.com/common-mor-findings-to-avoid-on-property/).
5. **Calculation errors**, including the [joint-custody dependent deduction claimed by two households at once](https://www.thehabitatgroup.com/watch-for-four-common-household-file-mistakes-as-hud-resumes-mors/).

**What it costs.** HUD Handbook 4350.1 rates reviews Superior / Satisfactory / Below Average / Unsatisfactory. A Below Average or Unsatisfactory rating brings [recovery of overpaid assistance, possible subsidy abatement or suspension, a mandatory corrective action plan, a repeat MOR within 12 months, and a flag in the Active Partners Performance System (APPS) that can block the owner from new HUD contracts or refinancing](https://www.hawaiiaffordable.com/blog/hud-mor-survival-guide-2026-tips-for-project-based-section-8-managers/) — with HAP contract termination as the end state for persistent noncompliance. The APPS flag is the one that scares owners: it's a financing problem, not a paperwork problem.

### LIHTC — state agency monitoring and IRS Form 8823

State agencies must [inspect and audit the lesser of 20% of units or the IRS Minimum Unit Sample Size, and inspect every building at least once every three years](https://www.nhhfa.org/wp-content/uploads/2019/08/LIHTC_Compliance_Monitoring.pdf). Noncompliance is reported to the IRS on **Form 8823**, which carries [17 possible compliance failures, eight of which can cause credit loss or recapture](https://www.nchm.org/irs-form-8823-and-the-8823-guide/). The heavy hitters: household income over the limit at initial occupancy (11a), failure to correctly complete or document annual recertification (11b), and inspection-standard violations (11c) — with habitability the most-reported category by volume ([8823 guide](https://www.irs.gov/pub/irs-pdf/p5913.pdf), [category analysis](https://www.hawaiiaffordable.com/blog/the-investors-guide-to-lihtc-compliance-protecting-your-tax-credits-in-hawaii/)).

**What it costs.** Owners get a [correction period of up to 90 days under §1.42-5(e)(4), extendable to six months for good cause](https://www.michigan.gov/mshda/-/media/Project/Websites/mshda/rental/Property-Managers/Compliance-for-Rental-Housing/Manuals-Policies-and-Codes/LIHTC-Compliance-Manual/CM-Chapter-10-Noncompliance.pdf). Fix it and the agency files a corrected 8823. Don't, and [recapture requires repaying the accelerated portion of credits already claimed, plus interest and penalties](https://legalclarity.org/what-is-the-8823-form-and-how-to-correct-noncompliance/). Missing the minimum set-aside after year one [loses the credit and triggers recapture of credits already taken](https://www.destatehousing.com/wp-content/uploads/2024/02/lihtc-irs-8823.pdf). In practice the general partner has indemnified the investor, so the GP eats it — which is why LIHTC compliance anxiety is disproportionate to the number of files.

**Worth testing in interviews:** my read is that the dominant *cost* isn't penalties, it's labor — staff time on recert chase-downs, pre-MOR file scrubbing, and acquisition-era file cleanup. Penalties are the fear; hours are the bill. Validate or kill this assumption early.

---

## 5. Recent HUD rule changes: HOTMA is the live event

The Housing Opportunity Through Modernization Act rewrote how income and assets are calculated. The final rule took effect **January 1, 2024**; PHA compliance was [mandatory January 1, 2025 for most programs](https://riooapp.com/blog/hotma-nspire-compliance-deadlines-2026). For multifamily, HUD extended full compliance via **Notice H 2025-07 (December 17, 2025)** from January 1, 2026 to **January 1, 2027** ([HUD](https://www.hud.gov/hud-partners/multifamily-hotma)). Implementing guidance is **Notice H 2023-10** (multifamily) and **PIH 2023-27** (PHAs).

**Section 102 — income:**
- Annual income is computed from the previous 12-month period under the rewritten §5.609.
- **Interim recertification threshold:** a 10% increase or decrease in *adjusted* income. Owners may set a lower decrease threshold, must process decreases when a member permanently moves out, and [may not act on increases in earned income unless the family already had an interim decrease that year](https://www.costellocompliance.com/blog/quick-tips-hotma-income-threshold-for-hud-interim-certifications).
- **De minimis safe harbor:** owners are not out of compliance for rent-calculation errors of [≤$30/month in adjusted income ($360/year)](https://www.us-hc.com/blogs/huds-new-hotma-changes-clarified/) — but must still credit or repay an overcharged family.
- **Safe harbor verification:** income determinations from other federal means-tested programs may be accepted.

**Section 104 — assets:**
- Imputed-income asset threshold rose from $5,000 to $50,000, indexed. For **2026: $52,787** ([Costello](https://www.costellocompliance.com/blog/news-hud-announces-2026-hotma-adjustment-factors)).
- **Self-certification** of net family assets is allowed at or below that threshold — a large documentation reduction.
- **Asset limit of $105,574 (2026)** as an eligibility restriction. It applies only to **Section 8 PBRA and Section 202/8** — [not to other multifamily programs](https://www.hud.gov/sites/dfiles/Housing/documents/HOTMA_Talking_Points_for_Multifamily_Programs_No_Asset_Limitation.pdf).
- Other 2026 factors: dependent deduction $500, elderly/disabled household deduction $550, passbook rate 0.4%.

**Two openings for a product.** First, HUD's own systems lagged: before TRACS updates landed, owners were told to [calculate incomes and rents manually, then enter results in TRACS 202D using the rent override function](https://www.hud.gov/hud-partners/multifamily-hotma). Manual calculation at scale with no system of record is exactly where errors and spreadsheets breed. Second, because §42 borrows HUD's income rules, HOTMA bleeds into LIHTC — and guidance has been uneven. Treat the LIHTC/HOTMA interaction as an open question to ask about, not a settled fact.

Also in flight: **NSPIRE** replaced the old physical inspection standards, and both HOTMA and NSPIRE deadlines are being tracked together by operators ([deadline roundup](https://riooapp.com/blog/hotma-nspire-compliance-deadlines-2026)).

---

## 6. Where the numbers come from, and the API

| Data | Source | Cadence |
|---|---|---|
| Income limits (HUD programs) | [huduser.gov/portal/datasets/il.html](https://www.huduser.gov/portal/datasets/il.html) | Annual |
| **MTSP** income limits (LIHTC + bond deals) | [huduser.gov/portal/datasets/mtsp.html](https://www.huduser.gov/portal/datasets/mtsp.html) | Annual — 2025 limits released April 1, 2025 |
| Fair Market Rents | [huduser.gov FMR datasets](https://www.huduser.gov/portal/dataset/fmr-api.html) | Annual, effective Oct 1 — [FY2026 published Aug 22, 2025](https://www.federalregister.gov/documents/2025/08/22/2025-16060/fair-market-rents-for-the-housing-choice-voucher-program-moderate-rehabilitation-single-room) |
| LIHTC rent limits | **Derived**, generally 30% of the applicable MTSP limit at imputed household size ([HUD](https://www.huduser.gov/portal/datasets/il.html)) | Follows MTSP |
| State-specific limit charts | State agencies publish their own, e.g. [CTCAC](https://www.treasurer.ca.gov/sites/default/files/2026-01/income-and-rent-limits-memo_0.pdf) | Annual |
| LIHTC property inventory | [huduser.gov/lihtc](https://www.huduser.gov/lihtc/) | Periodic |

**Yes, there's an API.** HUD User exposes REST endpoints ([docs](https://www.huduser.gov/portal/dataset/fmr-api.html)):

- Base: `https://www.huduser.gov/hudapi/public/fmr` and `https://www.huduser.gov/hudapi/public/il`
- `/{fmr|il}/data/{entityid}` — entity ID is a 5-digit county FIPS, CBSA code, or 2-digit state FIPS
- `/fmr/listStates`, `/fmr/listCounties/{stateid}`, `/fmr/listMetroAreas`
- Free **bearer token** from a HUD User account: `curl -H "Authorization: Bearer $KEY" https://www.huduser.gov/hudapi/public/fmr/data/0801499999`
- Sibling APIs exist for CHAS and the [USPS ZIP crosswalk](https://www.huduser.gov/portal/dataset/uspsncwm-api.html)

**Gaps that matter.** I found no API for: LIHTC rent limits as such (you compute them), utility allowances (local, per-PHA/per-state), payment standards (each PHA sets its own within a HUD range around the FMR), or any of the 4350.3 rule logic. Published rate limits weren't documented in what I could reach — the official docs page didn't render for automated fetching, so **verify endpoint list and limits against the live page before depending on it.** Utility allowances being un-APIed is a genuine data moat opportunity.

---

## 7. The existing software, and what people complain about

**Incumbents.** Yardi sells [Voyager Affordable Housing, with RightSource file review and RentCafe Affordable for online certification](https://www.yardi.com/market/affordable-housing/). RealPage sells OneSite Affordable. MRI sells Affordable Housing and **Bostonpost**. On the housing-authority side: [Emphasys](https://www.emphasys-software.com/) and [Tenmast](https://wifitalents.com/best/hud-compliance-software/), the latter built around tenant records, recertification tasking, and household file documentation. ResMan supports affordable workflows. Both [Yardi and RealPage expanded HOTMA/LIHTC/Section 8 compliance tooling in 2025](https://www.housingfinance.com/management-operations/yardi-realpage-bolster-compliance-offerings_o).

**What reviewers complain about:**

- **Bostonpost / MRI:** reviewers describe [generally terrible customer service and simple functions made convoluted and poorly arranged](https://softwarefinder.com/property-management-software/mri-affordable-housing/reviews), with support quality dependent on reaching one specific person ([also](https://www.itqlick.com/mri-bostonpost)).
- **RealPage OneSite:** operators cite [weak support, billing errors, and a proprietary database customers can't get their own data out of](https://www.multifamilyinsiders.com/apartment-ideas/the-front-lines/116-yardi-voyager-vs-realpages-onesite), plus thin accounting research tools. There's also live legal overhang from the [DOJ's suit over RealPage's algorithmic pricing](https://www.justice.gov/archives/opa/pr/justice-department-sues-realpage-algorithmic-pricing-scheme-harms-millions-american-renters) — reputational, not compliance, but it affects procurement.
- **Yardi:** well-regarded on compliance, but module-priced — [cheap at first, costly as modules accumulate](https://www.doorloop.com/blog/realpage-vs-yardi).
- **Cost generally:** pricing pressure on smaller portfolios is a recurring theme ([comparison](https://www.doorloop.com/blog/realpage-vs-yardi)).

**Structural gaps, stated as hypotheses to test:**

1. These systems **record** certifications; they don't **audit** them. The pre-MOR file scrub is still manual or outsourced — Yardi's own answer, RightSource, is a *service*, not a feature.
2. Portfolios straddle systems. One third-party tool advertises importing from [Yardi Voyager, RealPage OneSite, MRI Bostonpost, and Excel/CSV so one audit can run across files living in three systems](https://wifitalents.com/best/hud-compliance-software/) — that it exists as a product is evidence the problem is real.
3. HOTMA created a 2024–2027 window where the rules changed faster than the incumbents' systems, and HUD itself told owners to compute manually.
4. Document intake is still PDFs, paper, and portals. That's the part closest to what Abstractly already does.

⚠️ Caveat on this section: review-aggregator sites are low-quality and SEO-contaminated, and some pages above are vendor-adjacent. Treat these as leads for interview questions, not as findings. One real user conversation beats all of it.

---

## 8. Interview bank — 15 questions

Ask property managers, site-level compliance staff, and portfolio compliance directors. Separate the last two groups; they experience this differently.

**Shape of the work**
1. Walk me through the last recertification you personally completed, from the first notice to the signed 50059. How long did it actually take in minutes?
2. How many certifications does one person handle a month, and what's your current backlog?
3. Which systems do you touch to finish one certification? Count every spreadsheet, portal, and shared drive.

**Where it breaks**
4. What did your last MOR or state agency audit cite you for? What did fixing it involve?
5. How do you currently resolve an EIV discrepancy, and where does the written explanation live?
6. Tell me about a time a recertification went late. Where in the 120/90/60/30 cascade did it fall apart?
7. What percentage of files would fail if HUD showed up tomorrow unannounced? How do you know?

**Layered deals and HOTMA**
8. For units with both LIHTC and PBRA, how do you decide which rule governs, and who checks that decision?
9. What changed in your day-to-day when HOTMA hit? Are you calculating anything by hand right now?
10. Who at your organization decided your HOTMA interim-recertification threshold policy, and how is it enforced on-site?

**Tools and money**
11. What software are you on, who chose it, and what do you work around rather than through?
12. Do you outsource file review? To whom, how often, and what do you pay per file?
13. If a tool could do exactly one thing for you perfectly, what would it be? (Don't suggest options.)

**Buying**
14. Who signs off on a new compliance tool — you, the asset manager, the investor, or IT? What killed the last tool that was proposed?
15. What happens if compliance goes badly here? Whose problem does it become, and what does it cost them?

---

## Open questions before any build decision

- **How HOTMA actually applies to LIHTC-only properties**, and how uniform state agency guidance is. Unresolved in public sources.
- **Whether annual recertification is truly waived for 100%-affordable LIHTC buildings in the states you'd target.** States layer their own requirements.
- **HUD User API rate limits and reliability** — the official docs page wouldn't render for automated fetching; confirm manually.
- **Where the money actually sits**: penalties vs. labor hours. My working assumption is labor, but it's unverified.
- **Utility allowance data** — no national source found. Confirm whether that's a moat or a swamp.

## Sources

Primary: [HUD Handbook 4350.3](https://www.hud.gov/sites/documents/43503hsgh.pdf) · [HUD form 9834 (MOR)](https://www.hud.gov/sites/documents/9834.pdf) · [HUD form 9887 package](https://www.hud.gov/sites/documents/9887.pdf) · [24 CFR Part 982 (HCV)](https://www.govinfo.gov/content/pkg/CFR-2019-title24-vol4/xml/CFR-2019-title24-vol4-part982.xml) · [HUD Multifamily HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma) · [PIH 2023-27](https://www.hud.gov/sites/dfiles/PIH/documents/PIH%202023-27%20HOTMA.pdf) · [HOTMA multifamily talking points](https://www.hud.gov/sites/dfiles/Housing/documents/HOTMA_Talking_Points_for_Multifamily_Programs_No_Asset_Limitation.pdf) · [HOTMA interim reexaminations resource sheet](https://files.hudexchange.info/resources/documents/Interim-Income-Reexaminations-Resource-Sheet.pdf) · [IRS Pub 5913, Guide for Completing Form 8823](https://www.irs.gov/pub/irs-pdf/p5913.pdf) · [IRS LIHTC Audit Technique Guide](https://www.destatehousing.com/wp-content/uploads/2024/02/lihtc-irs-8823.pdf) · [FY2026 FMR Federal Register notice](https://www.federalregister.gov/documents/2025/08/22/2025-16060/fair-market-rents-for-the-housing-choice-voucher-program-moderate-rehabilitation-single-room) · [MOR streamlining final rule](https://www.federalregister.gov/documents/2022/06/27/2022-13426/streamlining-management-and-occupancy-reviews-for-section-8-housing-assistance-programs) · [HUD FMR/IL API docs](https://www.huduser.gov/portal/dataset/fmr-api.html) · [HUD Income Limits datasets](https://www.huduser.gov/portal/datasets/il.html) · [TRACS tip sheet](https://files.hudexchange.info/resources/documents/TRACS-Tip-Sheet.pdf)

State/industry: [OHFA LIHTC Compliance Manual](https://ohiohome.org/compliance/documents/OHFA-Compliance-Manual.pdf) · [Oregon OHCS LIHTC Manual 2025](https://www.oregon.gov/ohcs/compliance-monitoring/Documents/compliance/lihtc/LIHTC%20Compliance%20Manual%202025.pdf) · [NH Housing compliance monitoring](https://www.nhhfa.org/wp-content/uploads/2019/08/LIHTC_Compliance_Monitoring.pdf) · [MSHDA noncompliance chapter](https://www.michigan.gov/mshda/-/media/Project/Websites/mshda/rental/Property-Managers/Compliance-for-Rental-Housing/Manuals-Policies-and-Codes/LIHTC-Compliance-Manual/CM-Chapter-10-Noncompliance.pdf) · [ND Housing tenant file documentation](https://www.ndhousing.nd.gov/sites/www/files/documents/Forms/TenantFileDocumentation.pdf) · [Maine Housing Section 8 file requirements](https://www.mainehousing.org/docs/default-source/property-mgmt/required-documents-for-section-8-files.pdf) · [NCHFA resident files](https://www.nchfa.com/rental-housing-partners/rental-owners-managers/policies-resources-forms/resident-files) · [CTCAC income & rent limits memo](https://www.treasurer.ca.gov/sites/default/files/2026-01/income-and-rent-limits-memo_0.pdf) · [ND HFA: LIHTC + PBRA layering](https://www.ndhfa.org/wp-content/uploads/2019/04/Section8PropertieswithTaxCredits.pdf) · [NCHM: Project-Based Section 8](https://www.nchm.org/what-is-project-based-section-8/) · [NCHM: Form 8823](https://www.nchm.org/irs-form-8823-and-the-8823-guide/) · [Navigate Housing: common MOR findings](https://www.navigatehousing.com/common-mor-findings-to-avoid-on-property/) · [Habitat Group: household file mistakes](https://www.thehabitatgroup.com/watch-for-four-common-household-file-mistakes-as-hud-resumes-mors/) · [Costello: 2026 HOTMA adjustment factors](https://www.costellocompliance.com/blog/news-hud-announces-2026-hotma-adjustment-factors) · [Costello: HOTMA interim threshold](https://www.costellocompliance.com/blog/quick-tips-hotma-income-threshold-for-hud-interim-certifications) · [US Housing Consultants: HOTMA clarified](https://www.us-hc.com/blogs/huds-new-hotma-changes-clarified/) · [HUD Exchange: PHA role in HCV](https://files.hudexchange.info/resources/documents/PIH-HCV-Landlord-The-PHA-Role-in-the-Housing-Choice-Voucher-Program.pdf)
