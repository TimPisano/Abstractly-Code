# Affordable housing software: competitors and gaps

**Date:** 2026-10-19
**Scope:** Software and services sold to affordable housing owners, operators, property managers, and compliance staff (HUD PBRA/Section 8, HCV/PBV landlord side, PHA side, LIHTC, HOME, USDA RD). Research only. No accounts created, no demos requested, no code touched.
**Companion brief:** [section8.md](./section8.md), section 7. This document tests several claims from that brief and corrects one of them (see Summary).

**Source quality key.** Vendor pages are marked **(vendor)**. Competitor sites that sell rival products are marked **(competitor)**. Review aggregators and listicles are marked **(aggregator)**. Job postings are marked **(job post)**. Items I could read directly are marked **(fetched)**. Items I only saw as search-result snippets are marked **(snippet)**. Where a page returned 403 or an unreadable PDF, I say so.

---

## Summary

- **The most important competitors are the four big platforms plus MRI.** Yardi (Voyager Affordable, RentCafe Affordable, RightSource, Breeze Premier), RealPage (OneSite Affordable), MRI (Bostonpost, plus Tenmast and HAPPY for PHAs), and Entrata (Entrata Affordable). ResMan and AppFolio both sell affordable modules. Emphasys is the main PHA-side system. Nan McKay & Associates is a consulting and services firm with some software, not a platform.
- **Pricing is mostly not public.** The one clear public figure is Yardi's Breeze Premier for affordable housing at **$3 per unit per month with a $400 monthly minimum** (fetched from [Yardi Breeze's pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/)). Voyager, Entrata, OneSite, Bostonpost, AppFolio's affordable tier, and ResMan are all quote-only. Third-party figures exist but conflict, and I do not rely on them.
- **Correction to the section 7 brief.** The brief says these systems "record certifications; they don't audit them." That is only partly right. ResMan advertises built-in error checking and approval workflows ([ResMan](https://myresman.com/blog/why-conventional-software-wont-cut-it-lihtc-compliance)). MRI Bostonpost blocks move-ins that fail program eligibility ([MRI-cited Ohio customer](https://www.mrisoftware.com/blog/bostonpost-property-manager-tracs-202d-affordable-housing-software/), snippet). Yardi's RentCafe Affordable offers optional income verification and document upload ([Yardi brochure](https://www.yardi.com/resources/rentcafe-affordable-housing-brochure/pdf/), snippet). The accurate version is narrower: incumbents do rule checks inside their own system, and the independent cross-file, pre-MOR audit is mostly a service (RightSource) or consulting, not a product.
- **The five most credible gaps** (detail in the gaps section):
  1. A pre-MOR audit that runs across exports from several systems against HUD rules and TIC/50059 support documents.
  2. Checking TICs and 50059s against the underlying verification documents (pay stubs, EIV, benefit letters), with an audit trail.
  3. A HOTMA transition check before the January 1, 2027 full-compliance date. HUD lets owners compute by hand and enter via TRACS 202D rent override until then.
  4. HAP and rent reconciliation for small HCV landlords who are not on enterprise software, using the free PHA landlord portals as the baseline to beat.
  5. Compliance due diligence on affordable portfolios in acquisitions. This is the weakest-evidenced of the five.
- **Layered-deal rule conflicts are NOT a strong gap.** Yardi, MRI, ResMan, and Entrata all advertise layered-subsidy handling. Do not lead with it.
- **Incumbents can close most gaps.** Yardi already sells an audit service and an opt-in verification service, so it can extend either. The exceptions are gaps that cut across vendors (a neutral multi-system audit) and small-landlord economics, where the $400/month minimum on Breeze Premier is already high for a small landlord.

---

## Per-vendor profiles

### Big platforms

#### Yardi (Voyager Affordable, RentCafe Affordable, RightSource, Breeze Premier, Elevate)

- **What it does for affordable.** Voyager is the enterprise system with affordable modules. The Yardi Breeze Premier page says it covers HOME, RD, HUD 50058/50059, and LIHTC in all 50 states ([Yardi Breeze pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/), fetched; the 50-state LIHTC line is from a Yardi-affiliated page, snippet). Yardi's 2020 Breeze Premier release says it covers public housing, HCV, PBV, 50058/50059, and layered subsidies ([Yardi press release](https://yardi.com/?p=308179), snippet). RentCafe Affordable is the resident-facing certification portal. Its April 2026 brochure says it works with Compliance Manager and Voyager 8 and automates initial and recurring certifications ([Yardi brochure](https://www.yardi.com/resources/rentcafe-affordable-housing-brochure/pdf/), snippet).
- **Programs.** HUD PBRA, HCV/PBV (PHA side and owner side), LIHTC, HOME, RD. Yardi also launched an online RFTA tool for HCV landlords inside RentCafe ([Mann Report, 2023](https://www.mannpublications.com/mannreport/2023/03/16/yardi-introduces-solution-to-ease-voucher-acceptance-makes-it-easier-for-landlords-to-accept-vouchers/), snippet).
- **RightSource.** An outsourced file review and TRACS/MINC voucher processing and reconciliation service. Per Yardi's marketing, it works with Voyager and Compliance Manager and findings show on the Compliance Manager dashboard ([Yardi RightSource page](https://www.yardi.com/product/rightsource/), **snippet only; the page returned 403 on fetch**). Yardi's own PDF gives a 9.8-minute average review time and a 96% within-24-hour return rate ([Yardi PDF](https://www.yardi.com/resources/streamlined-affordable-housing-workflows-with-yardi-rightsource/pdf/), snippet, vendor-reported). A search snippet says RightSource requires Voyager and a RightSource license and does not work with Breeze Premier. I could not verify this from the Yardi page.
- **System of record or add-on?** System of record (Voyager, Breeze Premier). RightSource is a **service** layered on top.
- **Target customer.** Voyager: mid-size to large affordable portfolios and PHAs. Breeze Premier: smaller operators.
- **Public pricing.**
  - Breeze Premier affordable: **$3/unit/month, $400/month minimum, annual agreement** ([Yardi Breeze pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/), fetched; a Spendbase listing shows $2 for a different tier, treated as an outlier).
  - Yardi says it charges no separate onboarding, training, or support fees for Breeze, per [Buildium's review](https://www.buildium.com/blog/yardi-breeze-review/) (aggregator-adjacent, snippet).
  - Voyager, RentCafe Affordable, RightSource, Elevate: **not public.** A third-party estimate puts residential Voyager at $1.50–$3.00 per unit per month, which is not Yardi's figure ([Vendr](https://www.vendr.com/marketplace/yardi), aggregator, snippet). An "Elevate" pricing claim appeared in a search snippet from a source I could not pin down. I do not rely on it.
- **Strengths reported.** Well regarded on compliance depth and layered subsidies (the section 7 brief's claim, not re-verified here). Breeze Premier has published pricing.
- **Complaints reported.** Module-priced, costly as modules accumulate (per the section 7 brief, [DoorLoop comparison](https://www.doorloop.com/blog/realpage-vs-yardi), aggregator/competitor).
- **Integration and partner terms.** The Yardi Interface Partner program charges an **annual license fee per interface**, varying by interface type and sometimes by transaction volume. Yardi does not publish a dollar figure on the page ([Yardi interface partner page](https://www.yardi.com/?p=359162), **snippet; 403 on fetch**). Eligibility is a company at least two years old. A third-party API review site cites about $25K per interface per year and "3+ mutual Voyager clients." That is **unverified**, and the site is an aggregator ([Supergood](https://supergood.ai/api-report-card/yardi-systems)). The RentCafe API Terms of Use say fees are "identified in the Agreement," so actual pricing is in the contract ([Yardi RentCafe API ToU](https://resources.yardi.com/?p=18614), snippet).

#### RealPage (OneSite Affordable, OneSite general, Windsor Compliance, Domin-8)

- **What it does for affordable.** OneSite Affordable's own page says: "Seamlessly stay in compliance with HUD, Tax Credits, Rural Housing regulations and the 50058 Public Housing program," plus LIHTC state reporting ([RealPage OneSite Affordable page](https://www.realpage.com/lp/property-management-for-affordable-housing), fetched). The same page **does not** mention HOTMA, TRACS, HOME, or AI for affordable. A competitor review says RealPage updated OneSite Affordable for TRACS 2.0.3.A and HOTMA, with state HOTMA TICs added as agencies release them ([ExactEstate, Aug 2026](https://www.exactestate.com/blog/best-affordable-housing-software-12-platforms-compared), **competitor, snippet**). I could not confirm that from a RealPage or HUD source. Older RealPage releases describe LIHTC data-transfer support ([RealPage news](https://realpage.com/news/realpage-now-supports-lihtc-data-transfer-standard-for-compliance-reporting), dated).
- **Acquisitions (verified).**
  - **Windsor Compliance, October 2013.** Fetched from [HousingWire](https://housingwire.com/articles/27670-realpage-acquires-compliance-monitoring-firm): "a provider of compliance monitoring services for the affordable housing industry," with more than 30,000 affordable units. The SEC 10-Q for that period gives a $2.7 million price ([SEC 10-Q, snippet](https://www.sec.gov/Archives/edgar/data/0001286225/000128622514000030/rp-2014093010q.htm)).
  - **Domin-8, around 2014.** Described as broadening RealPage into small, medium, and affordable managers ([Multi-Housing News](https://www.multihousingnews.com/with-acquisition-of-domin-8-realpage-will-cater-to-small-medium-sized-and-affordable-housing-managers/), snippet).
  - **Notivus, May 2014.** General rental compliance and vendor risk, not affordable-specific ([SEC 10-Q, snippet](https://www.sec.gov/Archives/edgar/data/0001286225/000128622514000030/rp-2014093010q.htm)).
  - I found **no** RealPage affordable-compliance acquisition after 2014. My search was not exhaustive.
- **System of record or add-on?** System of record.
- **Target customer.** Mid-size to large operators. Also has a certified partner tier (RealPage AppPartner). A 2022 Grace Hill release says it became a certified AppPartner on RealPage Exchange ([Grace Hill](https://gracehill.com/grace-hill-announces-partnerships-with-yardi-and-realpage/), snippet). The cost of that tier is not public.
- **Public pricing.** **Not public.** G2 says RealPage has not provided pricing ([G2 pricing](https://www.g2.com/products/realpage-onesite/pricing), snippet). The only per-unit number I found is a 2005 review (about $1/unit/month, too old to use). A 2026 third-party estimate puts the category at $1–$5/unit/month, which is an estimate, not a RealPage quote. One aggregator lists "about $400 per property per month" for "OneSite Property," a different product.
- **Complaints reported.** G2 aggregate ratings conflict across pages (3.8/5 from 107 reviews, 3.9/5 from 40). Support is the most common weak spot (G2 comparison, snippet). Capterra reviews are mostly 2016–2017 (dated).
- **Legal overhang.** The DOJ suit over RealPage's algorithmic pricing is cited in the section 7 brief. Reputational, not compliance. I did not re-fetch it in this session.

#### MRI Software (Bostonpost / MRI Affordable Housing, Tenmast, HAPPY, HAB, PHA Pro)

- **What it does for affordable.** MRI says its affordable product "automates compliance for HUD Multi-Family, Tax Credit, HOME, and USDA Rural Development," and submits resident certification data to TRACS and MINC ([MRI affordable compliance page](https://mrisoftware.com/products/affordable-housing-compliance-software/), vendor, snippet). Bostonpost is described as handling layered subsidies, including HUD Sec. 8/202/236, USDA RD 515, LIHTC, HOME, public housing, and third-party vouchers ([MRI Bostonpost blog](https://www.mrisoftware.com/blog/bostonpost-property-manager-9-1-affordable-housing-property-management-software/), vendor, snippet). An MRI release says Bostonpost supports TRACS 202D ([MRI news](https://www.mrisoftware.com/news/mri-software-releases-latest-version-bostonpost-ensure-tracs-202d-compliance), vendor, snippet).
- **Tenmast (verified).** MRI acquired Tenmast, a PHA and private affordable housing software firm. The announcement is dated October 10, 2017 ([Software Equity Group](https://softwareequity.com/transactions/tenmast-acquired-by-mri-software), **fetched**). Days later, on October 16, 2017, MRI acquired **HAB, Inc.**, another PHA software firm ([MRI news](https://www.mrisoftware.com/sa/?p=23343), snippet). Tenmast says it served PHAs with more than 20,000 units.
- **HAPPY Software (verified, dated).** MRI acquired HAPPY Software in March 2018 for PHA and HCV work ([MRI news](https://www.mrisoftware.com/nz/news/happy-software-public-affordable-housing-tech-powerhouse/), snippet). I did not confirm whether HAPPY is still sold separately.
- **Bostonpost vs Tenmast.** I found no source on whether Tenmast's technology was folded into Bostonpost or PHA Pro (launched May 2024, [Mann Report](https://www.mannpublications.com/mannreport/2024/05/29/mri-software-unveils-pha-pro-for-public-housing-and-voucher-management-compliance/), snippet, is MRI's flagship PHA voucher product). Treat the product mapping as **unknown**.
- **System of record or add-on?** System of record.
- **Target customer.** Affordable owners and managers (Bostonpost), and PHAs (PHA Pro, Tenmast, HAPPY).
- **Public pricing.** **Not public.** ITQlick says Bostonpost "starts at $300 per month" on one page and shows **$2,500–$5,000/month license** in a comparison table on another page ([ITQlick pricing](https://www.itqlick.com/mri-bostonpost/pricing), aggregator, snippet). Those figures conflict and the sources are weak. Use neither as a benchmark.
- **Complaints reported.** Capterra customer service rated 2.0/5 by one reviewer. Another called it relatively inexpensive ([Capterra AU listing](https://www.capterra.com.au/software/1009740/mri-affordable-housing), snippet). Section 7's brief cites a softwarefinder review ("simple functions made convoluted"). I did not re-fetch it. The G2 page for MRI Affordable & Public Housing shows one review, 3.0/5, dated 2022 ([G2](https://www.g2.com/products/mri-affordable-public-housing/reviews), snippet). That sample is too small to rely on.

#### Entrata (Entrata Affordable)

- **What it does for affordable.** Entrata's product page lists tax credit compliance dashboards, LIHTC reporting and e-reporting, and HUD ledgers that update automatically when income is backdated or certifications overlap. It also says one household can be certified under multiple programs at once ([Entrata affordable page](https://www.entrata.com/affordable), vendor, snippet). A March 2025 Entrata blog says the platform handles TRACS certification and monthly HAP requests ([Entrata blog](https://www.entrata.com/blog/entrata-affordable-bridging-the-gap-between-affordable-and-traditional-property-management), vendor, snippet).
- **Launch date.** A competitor (ExactEstate) says Entrata Affordable launched in February 2023 ([ExactEstate](https://www.exactestate.com/blog/entrata-vs-exactestate-a-property-management-software-comparison), **competitor, snippet**). Fortress, another competitor, says the affordable functionality is newer and still adding program workflows ([Fortress](https://fortresstech.io/compare/entrata), **competitor**).
- **System of record or add-on?** System of record for conventional plus affordable.
- **Target customer.** Competitor reviews say 1,000+ unit operators ([ExactEstate](https://www.exactestate.com/blog/best-affordable-housing-software-12-platforms-compared), competitor, snippet).
- **Public pricing.** **Not public.** [G2 pricing](https://www.g2.com/products/entrata/pricing) says Entrata has not provided pricing (snippet). Third-party estimates of $4–$8/unit/month for enterprise stacks are estimates only.
- **Complaints reported.** One G2 reviewer said the software is not helpful for affordable units (G2, snippet, reviewer not pinned). Capterra reviewers say customer service is inconsistent ([Capterra](https://www.capterra.com/p/20372/Entrata/reviews/?page=7), snippet). Ratings are high: G2 4.6 from 817 reviews, Capterra 4.6 from 444 users. Those are mostly conventional-property reviews.
- **Verdict.** Entrata does affordable, but its affordable depth is less proven than Yardi's or MRI's. I found no independent compliance audit of it.

#### ResMan (Affordable module)

- **What it does for affordable.** ResMan says its affordable module covers LIHTC, HUD (including RAD), RD, and state and local set-asides ([ResMan affordable page](https://www.myresman.com/affordable/), vendor, snippet). It advertises built-in error checking, user-level permissions, approval workflows, and a "Build-A-Program" feature for layered funding ([ResMan compliance page](https://myresman.com/solutions/affordable-compliance), vendor, snippet). The blog says its dashboard shows recertifications and program compliance in one place ([ResMan blog](https://myresman.com/blog/why-conventional-software-wont-cut-it-lihtc-compliance), vendor, snippet).
- **Integrations.** Nationwide Compliant for lease compliance and evictions (vendor, snippet).
- **System of record or add-on?** System of record for conventional plus affordable.
- **Target customer.** Mid-size operators.
- **Public pricing.** **Not public.** A third-party FitGap summary is secondary and does not give a price.
- **Complaints or strengths.** One 2019 trade-press customer quote says it made voucher and certificate submission more efficient (dated, single customer). A Capterra reviewer praised ease of use and reporting (snippet, single review).

#### AppFolio (affordable tier)

- **What it does for affordable.** AppFolio says users can submit PBRA certifications and vouchers to TRACS, manage HAP requests and subsidy receipts, define unit set-asides, income and rent limits, and utility allowances, and generate TIC forms and XML reports for state portals, where XML upload depends on the state ([AppFolio affordable page](https://www-dyn.appfolio.com/markets/affordable-housing), vendor, snippet). A third-party review (SoftwareConnect) says a property-level HOTMA toggle exists ([SoftwareConnect roundup](https://softwareconnect.com/roundups/best-affordable-housing-property-management-software/), aggregator, snippet).
- **Gaps (competitor claim).** ExactEstate says the Plus tier lacks AIT validation and 140% rule automation ([ExactEstate AppFolio alternative](https://www.exactestate.com/appfolio-alternative), **competitor, unverified**).
- **Target customer.** SMB to mid-size. SoftwareConnect reports a 50-unit minimum for the affordable offering. **Unverified** (aggregator).
- **Public pricing.** Not confirmed as public for the affordable tier.
- **Customer evidence.** One AppFolio-published story (Laguna Management Services). Vendor-authored.

### PHA side and PHA-leaning systems

#### Emphasys (Emphasys Elite, HQS app)

- **What it does.** Emphasys Elite is a platform built for PHAs administering HCV and other HUD programs. It claims automation of applicant tracking, eligibility checks, rent calculations, and compliance reporting, including Form 50059 and Moving to Work ([Miami-Dade board memo](https://www.miamidade.gov/govaction/legistarfiles/MinMatters/Y2025/250968min.pdf), county record, snippet). Emphasys says it serves 36% of PHA units at the largest agencies (vendor, self-reported, [myhousing.com](https://myhousing.com/housing-programs/), snippet). The Emphasys HQS mobile app runs HQS inspections and syncs to Elite ([Apple App Store](https://apps.apple.com/us/app/-/id1616876475), snippet).
- **System of record or add-on?** System of record (PHA side).
- **Target customer.** PHAs, including large agencies.
- **Public pricing.** **Not public.** A county contract shows an extension for maintenance and support, and says Emphasys is the sole vendor able to license the software (Miami-Dade, 2021 item, snippet).
- **Relevance to Abstractly.** Emphasys is a PHA system. It is not an owner-side tool. An owner-side tool would need to reconcile against PHA HAP data, not replace Emphasys.

#### Nan McKay & Associates (NMA)

- **What it does.** A full-service consulting and services firm for housing agencies (HCV, LIHTC, PBRA, PBV, public housing, RAD). It also sells some tools, such as rent reasonableness software (GoSection8). A Santa Ana Housing Authority document shows a contract of up to $23,922 over three years for that tool ([Santa Ana contract record](https://cc-publicdocs.santa-ana.org/WebLink/1/doc/111028/Page2.aspx), public record, snippet).
- **Risk and legal context (check before any partnership).** A Jacksonville news report says NMA runs that city's voucher program after outsourcing, and that it was fined $3.7 million by DOJ in 2024 over a federally funded contract's cybersecurity requirements. The same report says the San Francisco Housing Authority has sued NMA for breach of contract ([WOKV](https://www.wokv.com/news/local/firm-hired-by-jacksonville-housing-authority-run-voucher-program-paid-millions-federal-fines/RRQYGDULO5DYZGJOKFRI2JJQ34/), news, snippet). I did not check the current status of these matters.
- **System of record or service?** Service, with some software.
- **Public pricing.** Not public, except the Santa Ana contract figure above.

### Mid-size and smaller tools

#### ExactEstate (competitor, cited heavily)

- ExactEstate sells affordable compliance software. Its pages claim HUD-50059 generation, append-only audit logs designed for MOR and IRS §42 audits, and HAP reconciliation and PHA payment splits for HCV and PBV ([ExactEstate affordable page](https://exactestate.com/markets/affordable-housing), competitor, snippet; [HCV section 8 page](https://www.exactestate.com/software/section-8-property-management-software), competitor, snippet).
- Its AI blog cites a May 2026 survey: 44% of operators name compliance and data privacy as the top barrier to more AI, and income certification and recertification remain "painstakingly manual, largely pen and paper" ([ExactEstate AI blog](https://www.exactestate.com/blog/ai-for-affordable-housing-compliance-closing-the-audit-gap), **competitor, fetched; survey not independently verified**).
- **Weight.** High competitor and vendor bias. Useful as a list of what a rival claims to do. Not independent evidence.

#### Costello Compliance (consulting, not software)

- A 2024 RIHousing board document recommends engaging Costello Compliance for $30,000 to update RIHousing's LIHTC compliance manual ([RIHousing RFA](https://rihousing.com/wp-content/uploads/Costello-Consulting-RFA-2024-08-15.pdf), public record, snippet). I found **no** Costello file-review *service* or software. The section 7 brief's "Costello compliance file review" is not supported.

#### Zeffert & Associates (consulting, with a portal)

- A St. Louis compliance firm founded in 1994, covering utility allowances, tenant file reviews, accessibility, and training ([Zeffert CARH listing](https://www.carh.org/member-directory-training/name/zeffert-associates-inc/), trade listing, snippet). A job posting says audits are run through a secured web portal ([job post](https://recruiting.paylocity.com/Recruiting/Jobs/Details/3393045), **job post**). No Zeffert-branded software product found.

#### Snappt (applicant income and fraud verification)

- Snappt sells AI document fraud detection and income verification (added June 2024), with payroll connection reported to cover about 90% of the U.S. workforce ([Snappt income verification](https://snappt.com/income-verification), vendor). It is priced per applicant through the TenantCloud partnership, and I found no public per-applicant figure ([Business Wire, Sept 2025](https://www.businesswire.com/news/home/20250910558211/en), press release). Its 99.8% accuracy claim is vendor-reported.
- **Fit.** Applicant screening for conventional and small landlords. Not a LIHTC or 50059 recertification system. Adjacent, not a direct competitor.

#### Pronto Housing (compliance and recertification startup)

- New York company. Closed a $2.5M seed round in November 2021, led by Wilshire Lane ([Business Wire](https://www.businesswire.com/news/home/20211102005853/en/Pronto-Housing-Closes-%242.5M-Seed-Round-Led-By-Wilshire-Lane), press release). Its platform covers resident qualification and recertification, with an owner dashboard for deadlines and files ([CB Insights](https://www.cbinsights.com/company/pronto-housing), data site, snippet). Funding totals conflict across listings ($3.0M in a 2024 listing, $4.5M in 2022 coverage). I did not confirm the current product or status.
- **Relevance.** This is the closest named startup doing owner-side affordable compliance. It is a direct competitor to watch, though I could not confirm its 2025–2026 status.

#### Neighborly Software, LandlordAI (HCV-focused)

- Neighborly is a PHA-side voucher platform ([Neighborly](https://www.neighborlysoftware.com/housing-choice-vouchers/), vendor, snippet). LandlordAI says it targets HAP and voucher workflows for landlords in California, Arizona, and Nevada ([Product Hunt](https://www.producthunt.com/products/landlordai), vendor, snippet). I did not verify LandlordAI's product or traction.

#### HAPPY Software, HAB, Tenmast (MRI-owned PHA tools)

- See the MRI section. These are PHA systems now inside MRI. Public pricing not found.

### Names checked and dropped (could not confirm)

- **Rioo.** No results. Dropped.
- **VoucherReady.** No results. Dropped.
- **Foresight (housing) and Ascent.** "Ascent" surfaced only as a regulatory-compliance automation firm, not housing. "Foresight Affordable" not found. Dropped.
- **ApartmentSmart.** No affordable compliance product found. Dropped.
- **HappyCo (NSPIRE).** Its app listing does not mention NSPIRE or affordable housing. Not confirmed. Other NSPIRE inspection tools found were SnapInspect, InspectCheck, and Property Inspect, all vendor marketing with no pricing. Listed as unverified.
- **Spectrum / Aspire, Rent Manager affordable, BlueMoon.** No affordable-compliance product found in searches. Dropped.
- **Boston Post.** This is Bostonpost (MRI), covered above.
- **HDS / ShofCorp.** Named by ExactEstate as TRACS access channels. Vendor-described, not verified against HUD ([ExactEstate TRACS page](https://www.exactestate.com/software/tracs-software), competitor).

### TRACS and HUD compliance context

- **NLHA list.** The National Leased Housing Association keeps a list of vendors and service bureaus that offer TRACS and MTCS occupancy software. NLHA says the list is not complete and is not an endorsement ([NLHA](https://hudnlha.com/?p=14099), snippet). This is the closest thing to a TRACS vendor list I found. HUD does not appear to certify vendors.
- **HUD guide.** "Choosing TRACS Compliant Software" (January 2023) ([HUD PDF](https://www.hud.gov/sites/dfiles/Housing/documents/Choosing_TRACS_Compliant_Software_Jan_2023.pdf), **could not read: the PDF returned binary only**). I could not confirm what it says about vendor certification or required functions. Read it directly before relying on it.
- **HOTMA.** HUD's multifamily HOTMA page says full compliance for income certifications is now **January 1, 2027**, moved from January 1, 2026. Owners who want to adopt early can compute incomes and rents manually and enter them in TRACS 202D with the rent override function ([HUD HOTMA page](https://www.hud.gov/hud-partners/multifamily-hotma), **fetched**). A TRACS 203A release is mentioned in a competitor blog, but I found no HUD source on its status. **Unverified.**

---

## Comparison table

Pricing: "Public" means a figure is on a vendor page I could read. "Quote" means not public. Confidence reflects how well the claims are sourced.

| Vendor / product | Programs (affordable) | Role | Target size | Public price | Main complaints or strengths reported | Confidence |
|---|---|---|---|---|---|---|
| Yardi Voyager Affordable | HUD PBRA, HCV/PBV, LIHTC, HOME, RD | System of record | Mid to large; PHAs | Quote (third-party est. $1.50–$3/unit/mo, unverified) | Strong compliance depth; module pricing | Medium |
| Yardi Breeze Premier (affordable) | HUD, LIHTC, HOME, RD, 50058/59 | System of record | Small operators | **$3/unit/mo, $400/mo min** | Published price; small-operator fit | High (price), Medium (features) |
| Yardi RentCafe Affordable | Online certification for Voyager/CM | Add-on portal | Voyager clients | Quote | Applicant self-service, optional income verification | Medium (vendor brochure) |
| Yardi RightSource | Voyager and CM file review, TRACS/MINC voucher processing | **Service** | Voyager clients | Quote | 9.8 min avg review, 96% in 24h (vendor-reported) | Medium (vendor; page 403) |
| RealPage OneSite Affordable | HUD, LIHTC, RD, 50058 (HOTMA/TRACS unconfirmed) | System of record | Mid to large | Quote | Support weak (G2 snippets); ratings conflict | Medium |
| RealPage / Windsor Compliance | Compliance monitoring, 30k+ affordable units (2013 acquisition) | Service (acquired) | Monitoring clients | n/a | Shows compliance monitoring was a service line | High (acquisition), Low (current use) |
| MRI Bostonpost | HUD, LIHTC, HOME, RD, layered subsidies, TRACS 202D | System of record | Owners and managers | Quote (conflicting: $300/mo vs $2.5–5k/mo) | Customer service complaints (Capterra 2.0/5, one review) | Medium |
| MRI Tenmast / HAB / HAPPY / PHA Pro | PHA HCV, public housing, FSS | System of record (PHA) | PHAs (Tenmast >20k units) | Quote | Acquisitions 2017–2018; product mapping unknown | High (acquisitions), Low (product) |
| Entrata Affordable | LIHTC, HUD, TRACS, HAP requests | System of record (mixed portfolio) | 1,000+ unit operators (competitor claim) | Quote | Affordable depth less proven; high conventional ratings | Medium-low |
| ResMan Affordable | LIHTC, HUD incl. RAD, RD, state set-asides | System of record | Mid-size | Quote | Error checks, layered funding ("Build-A-Program") | Medium-low (vendor) |
| AppFolio affordable | PBRA TRACS submission, LIHTC TICs | System of record (SMB) | SMB (50-unit min, unverified) | Not confirmed | Competitor says lacks AIT and 140% rule | Low-medium |
| Emphasys Elite | HCV, HUD PHA programs, 50059 | System of record (PHA) | PHAs | Quote | Sole licensed vendor per county record | Medium |
| Nan McKay & Associates | HCV, LIHTC, PBRA, PBV, RAD | Service + some software | PHAs | Quote (one contract: $23,922 / 3 yrs) | DOJ fine 2024, SF Housing Authority suit (news; unverified status) | Medium |
| ExactEstate | LIHTC, HUD MF, HCV/PBV HAP | System of record | Mid-size | Not confirmed | Competitor blog; survey claims | Low (self-described) |
| Snappt | Applicant income and fraud verification | Add-on (screening) | Small landlords | Per applicant (not published) | 99.8% accuracy (vendor) | Medium |
| Pronto Housing | Recertification, owner dashboard | Startup | Owners (unknown) | Not public | 2021 seed $2.5M | Low (status unknown) |
| Costello Compliance | LIHTC manual update (RIHousing) | Consulting | State HFAs | $30k (one RFA) | No file-review software found | Medium (consulting only) |
| Zeffert & Associates | Utility allowances, tenant file reviews | Service (+ portal) | Owners | Quote | Web portal per job posting | Low |

---

## Gaps a small team could fill

Each gap lists the evidence, what the incumbents already do, and how easily they could close it. Weak evidence is marked as such.

### 1. Cross-system pre-MOR file audit (strongest)

- **The gap.** A neutral audit that takes exports from Yardi, RealPage, MRI, and Excel, runs HUD rules and program checks across all of them, and produces a findings list before a HUD MOR or a state monitoring visit.
- **Evidence.** Single-audit findings for HUD-assisted properties show repeat patterns: a 50059 with no support for reported income, inaccurate income support at move-in, recertification calc errors, and missing third-party verification ([FAC finding 549](https://fac.procurementexpress.com/findings/549), [FAC audit 20246](https://fac.procurementexpress.com/audits/20246), snippets; [The Habitat Group list](https://www.thehabitatgroup.com/articles/print/7845), industry, snippet). One audit cited the owner for not having internal controls to catch missing support. A consultant-run file review (RightSource, Zeffert, Costello) is the current answer, and it is manual.
- **What incumbents have.** Yardi RightSource is a file review **service** tied to Voyager. ExactEstate claims audit logs built for MOR reviews. I found no product that audits across vendors.
- **Could incumbents close it?** Partly. Yardi could extend RightSource into a feature for Voyager clients. A cross-vendor neutral audit is harder for them, because it would mean auditing rival systems' data. This is the most defensible position if the wedge is "works on whatever you already use."
- **Caution.** I did not find a HUD MOR statistic or a buyer willing to pay for this. This needs interviews.

### 2. Checking TICs and 50059s against the underlying verification documents

- **The gap.** Compare the income figures on a 50059 or TIC with pay stubs, EIV, benefit letters, and bank statements, flag mismatches with citations, and keep an audit trail. The problem is the same as Abstractly's current lease-versus-roll check, applied to tenant income files.
- **Evidence.** A sampled 50059 had no support for its reported income ([FAC audit](https://fac.procurementexpress.com/audits/20246), snippet). Income certification and recertification are still "painstakingly manual" per ExactEstate's May 2026 survey (competitor, [ExactEstate](https://www.exactestate.com/blog/ai-for-affordable-housing-compliance-closing-the-audit-gap), fetched). EliseAI is hiring compliance reviewers to check its AI output across LIHTC, HCV, PBV, PBRA, and RD files ([EliseAI job post](https://www.builtinboston.com/job/affordable-housing-compliance-expert-housing/10515908), **job post**). That shows a player building this with humans in the loop. A CLA article says HUD accountability stays with people, so any product needs human sign-off ([CLA](https://www.claconnect.com/en/resources/articles/26/ai-in-hud-lihtc), snippet).
- **What incumbents have.** Yardi offers opt-in Verification Services inside RentCafe Affordable ([Yardi brochure](https://www.yardi.com/resources/rentcafe-affordable-housing-brochure/pdf/), snippet). Snappt does applicant income verification for screening (not recertification).
- **Could incumbents close it?** Yes, and Yardi has already started. Expect incumbents to extend this first. Abstractly's advantage would be the cross-document citation and the audit trail, not the verification itself.

### 3. HOTMA transition check before January 1, 2027

- **The gap.** Compute HOTMA incomes and rents for each file, flag where a 2026 or early-adoption file differs from the old method, and produce the TRACS 202D rent-override entries. Support the owner while the TRACS 203A spec is still open.
- **Evidence.** HUD moved the full-compliance date to January 1, 2027, and allows manual computation with TRACS 202D rent override for early adopters ([HUD HOTMA](https://www.hud.gov/hud-partners/multifamily-hotma), fetched). A competitor says RealPage has added HOTMA TICs by state, while also warning that vendors claiming full HOTMA compliance may be overselling (ExactEstate, snippet). The TRACS 203A status is **unverified** (no HUD source found).
- **What incumbents have.** RealPage and AppFolio claim HOTMA support (RealPage competitor-reported; AppFolio toggle per aggregator). Neither is independently verified.
- **Could incumbents close it?** Yes. Their vendors are already working on it, and the deadline makes it a must-have for them. This gap is a **timing** window, not a durable moat.

### 4. HAP and rent reconciliation for small HCV landlords

- **The gap.** A small landlord (under roughly 50 voucher units) who is not on Breeze Premier, Voyager, or a PHA portal, needs to match monthly HAP remittances to tenants, catch short or late payments, and track rent-reasonableness letters.
- **Evidence.** A HUD webinar slide describes free PHA landlord portals that show HAP history and remittances by tenant and unit ([HUD HCV Landlord Webinar](https://www.hud.gov/sites/dfiles/PIH/documents/HCV_Landlord_Webinar3_Technology.pdf), federal, snippet). This means the free baseline is already there, which limits the gap. Breeze Premier's $400/month minimum is a real barrier at small scale (vendor price, [Yardi](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/), fetched). ExactEstate claims HAP reconciliation but aims at multi-program operators ([ExactEstate](https://www.exactestate.com/software/section-8-property-management-software), competitor). LandlordAI targets three western states (vendor).
- **Could incumbents close it?** Unlikely to go down-market. Their minimums and sales motion do not fit this segment. Yardi's RFTA tool already covers part of the landlord side.
- **Caution.** The evidence is about price and minimum, not demand. Interview small landlords before building.

### 5. Compliance due diligence on affordable portfolios in acquisitions

- **The gap.** A buyer or lender reviews a target's LIHTC or HUD portfolio for compliance exposure (recapture risk, late certifications, missing 50059s) before close.
- **Evidence (weak).** RealPage bought Windsor Compliance in 2013 for monitoring of 30k+ affordable units, which shows compliance monitoring has been valued as a service line ([HousingWire](https://housingwire.com/articles/27670-realpage-acquires-compliance-monitoring-firm), fetched). Consulting firms do file reviews. I found no product marketed for acquisition diligence on affordable portfolios.
- **What incumbents have.** Services (RightSource, consulting firms). No product found.
- **Could incumbents close it?** Possibly, but buyers in diligence are not their current customer. This is a hypothesis to test, not a finding.

### Not a strong gap: layered-deal rule conflicts

- Yardi, MRI (Bostonpost "multi-layered subsidies"), ResMan ("Build-A-Program"), and Entrata (multiple programs per household) all advertise layered-subsidy handling. Leading with this would be easy to rebut in a demo. Keep it as a feature, not a wedge.

---

## Sales cycle and integration realities

- **Who buys.** Owner-side: asset managers, compliance directors at third-party management firms, and regional managers. PHA-side: procurement, and the HCV or public housing director, through formal RFPs (for example, a 2025 Miami-Dade extension for Emphasys). Small landlords buy on price and minimums, often never at all (use the PHA portal).
- **Integrations needed.**
  - **Yardi.** Interface partners pay an **annual license fee per interface** that varies by interface type and transaction volume (not published). The program requires the company to have existed for at least two years. A third-party aggregator cites about $25K/interface/year and "3+ mutual Voyager clients" (**unverified**; [Supergood](https://supergood.ai/api-report-card/yardi-systems)). A Standard Interface partner gets a sandbox and API access (per Yardi page, snippet; 403 on fetch).
  - **RealPage.** Has a certified AppPartner tier (2022 Grace Hill release, snippet). Terms and fees not public.
  - **RentCafe API.** Access terms say pricing is in the contract, so the RentCafe API is not usable without a signed agreement ([Yardi RentCafe API ToU](https://resources.yardi.com/?p=18614), snippet).
  - **MRI.** No public partner program or fee found in this session. **Not verified.**
  - **TRACS submission.** TRACS access runs through HUD's secure systems and authorized vendors (per ExactEstate, competitor; [HUD secure systems guide](https://www.hud.gov/sites/dfiles/Housing/documents/Guide_to_Accessing_HUD_Secure_Systems_Jan_2023.pdf), not read in this session). Any Abstractly product that touches TRACS needs a real vendor path and HUD access. This is a real cost and timing item I did not size.
- **Implementation.** One Yardi-era source says implementation can equal or exceed the first year of licensing (aggregator, snippet). Yardi's 2020-era fast-track promised about two weeks, capped and likely no longer offered (snippet).
- **Procurement timing.** PHA contracts run through county boards and RFPs (Miami-Dade item, Georgia DCA RFP, snippet). Expect 3–9 month cycles. **Unverified** as a general rule.

---

## Open questions for interviews

1. Who actually runs the pre-MOR scrub today: in-house, RightSource or another consultant, or nobody? What does it cost?
2. Which systems do you export from, and how often? Does the audit span more than one system?
3. What HOTMA workflow are you using before January 1, 2027? Manual calc, TRACS rent override, or a vendor?
4. For a small landlord with 20–60 voucher units, what do you pay today for HAP tracking? Do you use the PHA portal?
5. Has an acquisition ever stalled on compliance findings? Who did the review?

---

## Sources

Fetched in this session (full page read):
- [Yardi Breeze pricing blog](https://www.yardibreeze.com/blog/2024/11/yardi-breeze-pricing/)
- [RealPage OneSite Affordable page](https://www.realpage.com/lp/property-management-for-affordable-housing)
- [HousingWire: RealPage acquires Windsor Compliance](https://housingwire.com/articles/27670-realpage-acquires-compliance-monitoring-firm)
- [Software Equity Group: Tenmast acquired by MRI](https://softwareequity.com/transactions/tenmast-acquired-by-mri-software)
- [HUD HOTMA multifamily page](https://www.hud.gov/hud-partners/multifamily-hotma)
- [ExactEstate AI compliance blog](https://www.exactestate.com/blog/ai-for-affordable-housing-compliance-closing-the-audit-gap) (competitor)

Blocked or unreadable (search snippet only, not verified on the page):
- [Yardi RightSource product page](https://www.yardi.com/product/rightsource/) (403)
- [Yardi interface partner page](https://www.yardi.com/?p=359162) (403)
- [HUD Choosing TRACS Compliant Software (PDF)](https://www.hud.gov/sites/dfiles/Housing/documents/Choosing_TRACS_Compliant_Software_Jan_2023.pdf) (binary only)

Search-result snippets (cited inline, not individually fetched):
- [Yardi brochure, RentCafe Affordable](https://www.yardi.com/resources/rentcafe-affordable-housing-brochure/pdf/)
- [Yardi RentCafe API terms](https://resources.yardi.com/?p=18614)
- [Yardi press release, Breeze Premier 2020](https://yardi.com/?p=308179)
- [Yardi PDF, RightSource](https://www.yardi.com/resources/streamlined-affordable-housing-workflows-with-yardi-rightsource/pdf/)
- [Mann Report, Yardi RFTA 2023](https://www.mannpublications.com/mannreport/2023/03/16/yardi-introduces-solution-to-ease-voucher-acceptance-makes-it-easier-for-landlords-to-accept-vouchers/)
- [Vendr, Yardi pricing](https://www.vendr.com/marketplace/yardi) (aggregator)
- [Buildium, Yardi Breeze review](https://www.buildium.com/blog/yardi-breeze-review/) (aggregator-adjacent)
- [DoorLoop, RealPage vs Yardi](https://www.doorloop.com/blog/realpage-vs-yardi) (aggregator)
- [RealPage news, LIHTC data transfer](https://realpage.com/news/realpage-now-supports-lihtc-data-transfer-standard-for-compliance-reporting) (dated)
- [Multi-Housing News, Domin-8](https://www.multihousingnews.com/with-acquisition-of-domin-8-realpage-will-cater-to-small-medium-sized-and-affordable-housing-managers/)
- [SEC 10-Q, RealPage 2014](https://www.sec.gov/Archives/edgar/data/0001286225/000128622514000030/rp-2014093010q.htm)
- [G2 RealPage OneSite pricing](https://www.g2.com/products/realpage-onesite/pricing)
- [ExactEstate best-of comparison, Aug 2026](https://www.exactestate.com/blog/best-affordable-housing-software-12-platforms-compared) (competitor)
- [Grace Hill, RealPage AppPartner](https://gracehill.com/grace-hill-announces-partnerships-with-yardi-and-realpage/)
- [MRI Bostonpost TRACS 202D blog](https://www.mrisoftware.com/blog/bostonpost-property-manager-tracs-202d-affordable-housing-software/)
- [MRI Bostonpost 9.1 blog](https://www.mrisoftware.com/blog/bostonpost-property-manager-9-1-affordable-housing-property-management-software/)
- [MRI affordable compliance page](https://mrisoftware.com/products/affordable-housing-compliance-software/)
- [MRI news, Bostonpost TRACS 202D](https://www.mrisoftware.com/news/mri-software-releases-latest-version-bostonpost-ensure-tracs-202d-compliance)
- [MRI news, HAB acquisition](https://www.mrisoftware.com/sa/?p=23343)
- [MRI news, HAPPY acquisition](https://www.mrisoftware.com/nz/news/happy-software-public-affordable-housing-tech-powerhouse/)
- [Mann Report, MRI PHA Pro 2024](https://www.mannpublications.com/mannreport/2024/05/29/mri-software-unveils-pha-pro-for-public-housing-and-voucher-management-compliance/)
- [ITQlick, Bostonpost pricing](https://www.itqlick.com/mri-bostonpost/pricing) (aggregator; conflicting figures)
- [G2, MRI Affordable & Public Housing](https://www.g2.com/products/mri-affordable-public-housing/reviews)
- [Capterra AU, MRI Affordable Housing](https://www.capterra.com.au/software/1009740/mri-affordable-housing)
- [Entrata affordable page](https://www.entrata.com/affordable) (vendor)
- [Entrata blog, March 2025](https://www.entrata.com/blog/entrata-affordable-bridging-the-gap-between-affordable-and-traditional-property-management) (vendor)
- [ExactEstate, Entrata comparison](https://www.exactestate.com/blog/entrata-vs-exactestate-a-property-management-software-comparison) (competitor)
- [Fortress, Entrata comparison](https://fortresstech.io/compare/entrata) (competitor)
- [G2, Entrata pricing](https://www.g2.com/products/entrata/pricing)
- [Capterra, Entrata reviews](https://www.capterra.com/p/20372/Entrata/reviews/?page=7)
- [ResMan affordable page](https://www.myresman.com/affordable/) (vendor)
- [ResMan compliance solution page](https://myresman.com/solutions/affordable-compliance) (vendor)
- [ResMan blog, LIHTC](https://myresman.com/blog/why-conventional-software-wont-cut-it-lihtc-compliance) (vendor)
- [AppFolio affordable page](https://www-dyn.appfolio.com/markets/affordable-housing) (vendor)
- [ExactEstate, AppFolio alternative](https://www.exactestate.com/appfolio-alternative) (competitor)
- [SoftwareConnect roundup](https://softwareconnect.com/roundups/best-affordable-housing-property-management-software/) (aggregator)
- [Emphasys, myhousing.com](https://myhousing.com/housing-programs/) (vendor)
- [Miami-Dade board memo, 2025](https://www.miamidade.gov/govaction/legistarfiles/MinMatters/Y2025/250968min.pdf) (public record)
- [Apple App Store, Emphasys HQS](https://apps.apple.com/us/app/-/id1616876475)
- [Santa Ana contract record, NMA](https://cc-publicdocs.santa-ana.org/WebLink/1/doc/111028/Page2.aspx) (public record)
- [WOKV, NMA Jacksonville](https://www.wokv.com/news/local/firm-hired-by-jacksonville-housing-authority-run-voucher-program-paid-millions-federal-fines/RRQYGDULO5DYZGJOKFRI2JJQ34/) (news)
- [RIHousing RFA, Costello](https://rihousing.com/wp-content/uploads/Costello-Consulting-RFA-2024-08-15.pdf) (public record)
- [Zeffert, CARH listing](https://www.carh.org/member-directory-training/name/zeffert-associates-inc/) (trade listing)
- [Zeffert job post](https://recruiting.paylocity.com/Recruiting/Jobs/Details/3393045) (job post)
- [Snappt income verification](https://snappt.com/income-verification) (vendor)
- [Business Wire, Snappt and TenantCloud, Sept 2025](https://www.businesswire.com/news/home/20250910558211/en) (press release)
- [Business Wire, Pronto Housing seed, 2021](https://www.businesswire.com/news/home/20211102005853/en/Pronto-Housing-Closes-%242.5M-Seed-Round-Led-By-Wilshire-Lane) (press release)
- [CB Insights, Pronto Housing](https://www.cbinsights.com/company/pronto-housing) (data site)
- [Neighborly Software, HCV](https://www.neighborlysoftware.com/housing-choice-vouchers/) (vendor)
- [Product Hunt, LandlordAI](https://www.producthunt.com/products/landlordai) (vendor)
- [ExactEstate, section 8 software](https://www.exactestate.com/software/section-8-property-management-software) (competitor)
- [ExactEstate, affordable housing page](https://exactestate.com/markets/affordable-housing) (competitor)
- [ExactEstate, TRACS software page](https://www.exactestate.com/software/tracs-software) (competitor)
- [NLHA, TRACS vendor list](https://hudnlha.com/?p=14099) (trade group)
- [HUD HCV Landlord Webinar, technology slides](https://www.hud.gov/sites/dfiles/PIH/documents/HCV_Landlord_Webinar3_Technology.pdf) (federal)
- [HUD Guide to Accessing Secure Systems, Jan 2023](https://www.hud.gov/sites/dfiles/Housing/documents/Guide_to_Accessing_HUD_Secure_Systems_Jan_2023.pdf) (federal; not read)
- [FAC finding 549](https://fac.procurementexpress.com/findings/549) (federal audit database)
- [FAC audit 20246](https://fac.procurementexpress.com/audits/20246) (federal audit database)
- [The Habitat Group, review issues list](https://www.thehabitatgroup.com/articles/print/7845) (industry, undated)
- [Supergood, Yardi API report card](https://supergood.ai/api-report-card/yardi-systems) (aggregator; unverified fee)
- [EliseAI job post, compliance expert](https://www.builtinboston.com/job/affordable-housing-compliance-expert-housing/10515908) (job post)
- [CLA, AI in HUD and LIHTC](https://www.claconnect.com/en/resources/articles/26/ai-in-hud-lihtc) (accounting firm)
- [AI Consulting Network, AI affordable compliance 2026](https://www.theaiconsultingnetwork.com/blog/ai-affordable-housing-compliance-lihtc-section-8-recertification-2026) (blog)
- [Fortress, affordable vs standard PM](https://fortresstech.io/blog/affordable-housing-software-vs-standard-pm-platforms) (competitor)
- [DOJ, RealPage suit](https://www.justice.gov/archives/opa/pr/justice-department-sues-realpage-algorithmic-pricing-scheme-harms-millions-american-renters) (cited in section 7 brief; not re-fetched)
- [Section 8 briefing, section 7](./section8.md) (internal)

**Weak-source list for this document:** ExactEstate, Fortress, SoftwareConnect, ITQlick, FitGap, ToolRadar, Spendbase, Vendr, DoorLoop, Supergood, CB Insights, Product Hunt, and the wifitalents listicle cited by the section 7 brief. Treat all of them as leads, not findings. The wifitalents page was not re-checked here and I did not rely on it.

**Not verified in this session:** Yardi RightSource and interface-partner terms (403); HUD TRACS vendor guidance (unreadable PDF); RealPage partner fees; MRI partner program; the 2025–2026 status of Pronto Housing, LandlordAI, and HAPPY; the DOJ suit status; the NMA litigation status; any HUD MOR statistic.
