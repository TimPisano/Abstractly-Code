# Affordable Housing Research: Summary

**Date:** 2026-10-19 · **Branch:** `research/affordable-housing` · Research only: no app code changed, nothing pushed.

| File | What it answers |
|---|---|
| [section8-workflows.md](./section8-workflows.md) | Recurring PBRA / PBV / HCV compliance work, documents, fields, where money is lost |
| [lihtc-workflows.md](./lihtc-workflows.md) | The same for LIHTC (TICs, limits, set-asides, 8823, state reporting) |
| [competitors.md](./competitors.md) | Incumbents, AI entrants, public pricing, gaps |
| [feature-priorities.md](./feature-priorities.md) | Top 10 features, scored, with S8 branch coverage |
| [eval-docs.md](./eval-docs.md) | 31 public no-login documents; an 18-document v1 eval set |

## The three things that matter

1. **Our opening is the cross-document check, not the income math.** The systems of record (Yardi, RealPage, MRI, Entrata, ResMan, AppFolio) run certifications inside their own data. AI entrants now target TIC/50059-vs-pay-stub review and pre-MOR scoring: HousingIntellect, EliseAI ($250M Series E), DEVAL PHASE, and RealPage's AI agent. Nobody we found ties the **rent roll ↔ lease ↔ HAP contract ↔ PHA notice ↔ certification** together with page citations and dollar impact. That is Abstractly's existing CRE product, pointed at new documents.
2. **The HCV landlord side is the most open segment.** PHA portals show HAP payments but don't reconcile them. The only public affordable price is Yardi Breeze Premier at $3/unit/month with a $400/month minimum. Demand is unproven: no published dollar figure for HAP shortfalls was found.
3. **Our current customers are acquirers.** No product for affordable acquisition due diligence was found; consultants do it today. The evidence is weak, but the fit is the best of anything here.

## What to build first

| Order | Build | Why now | Depends on |
|---|---|---|---|
| 1 | **Finish the Rent Roll & HAP Check** (feature #1): merge T1 data model, `fix/section8-tenant-share`, `feature/lease-intelligence`; then T2 (HAP contract + PHA notice extraction) and T3 (detectors) | Highest score (18/20), half built, demoable on existing fixtures | Merge order already in TASKS.md |
| 2 | **LIHTC rent and income limit check on the rent roll** (#3) | Needs only the rent roll plus `hud_data`, which already has the LIHTC limit functions. The cheapest honest way to say "we do LIHTC" | `feature/s8-hud-data` merged |
| 3 | **Package 1 + 2 as an affordable diligence report** (#4) for existing CRE customers | Tests the best-fit buyer with no new engine | 1, 2 |
| 4 | **HAP payment reconciliation** (#2, T4 + T5), *only after* 5 HCV landlord interviews confirm the dollars | Scores high, but demand is unproven | T1, interviews |

**Hold:** the tenant-file audit (#7). It has the highest pain, but it's contested, the hardest to build, and blocked until `feature/s8-pii-guard` (T0) merges. Skip a standalone HOTMA tool: the Jan 1, 2027 deadline makes it table stakes for every incumbent.

## Corrections to the earlier briefing (`section8.md`)

- LIHTC inspection sample is a size-keyed table in [26 CFR 1.42-5](https://www.law.cornell.edu/cfr/text/26/1.42-5), **not** "20% of units". First inspection is due by the end of year 2, then at least every 3 years.
- LIHTC utility allowance changes apply **90 days** after the change ([1.42-10(c)](https://www.law.cornell.edu/cfr/text/26/1.42-10)), not 45. The 45-day window applies to new MTSP limits (secondary source).
- MOR ratings have **five** labels, not four.
- The 24-hour / 30-day repair rule is the HQS rule ([982.404](https://www.law.cornell.edu/cfr/text/24/982.404)). HQS termination is at 60 days. The HCV/PBV NSPIRE date is around Feb 1, 2027, and sources conflict by a day.
- PBRA recert reminders are **120 / 90 / 60** days (HUD 4350.3 Exhibits 7-2 to 7-4). The "30-day notice" is not in HUD's samples.
- Opt-out needs **at least one year's** notice (42 U.S.C. §1437f(c)(8)).
- Incumbents do run some rule checks, so "record, don't audit" was too strong. Costello is consulting, not file-review software.
- New since the briefing: **PIH/H 2026-09** reportedly requires an interim on any household composition change. This is secondary only; confirm it on hud.gov before building on it.

## How much to trust this

- **Primary text was read** for the CFR and USC sections linked above, HUD's HOTMA page, CTCAC's forms page, and the title and contents of IRS Pub 5913 (rev. 1/24/2024).
- **Most HUD and IRS PDFs could not be read.** The fetch tool can't decode them, and the permission system blocked a local PDF reader partway through the night. The agents worked around nothing. So the following remain **labelled secondary or unverified** in the docs: 50059 field numbers, TRACS/MAT layouts, the Form 8823 category list and credit-loss subset, Renewal Guide details, Notice H 2015-04, and PIH 2026-09 / 2026-18.
- Every rule claim in the docs carries a source and a confidence label. State and PHA rules are marked "Verify with your state agency / PHA". No scores in feature-priorities come from customer conversations.

## For you in the morning

1. **Permission denials to know about** (not worked around): agents were denied the in-memory PDF reader (`curl | pypdf`, using another worktree's venv), two IRS PDF fetches, two other fetches, and one doc edit, which later landed on retry. If you want the open items closed, decide whether reading public HUD/IRS PDFs locally is OK. That would upgrade most "secondary" labels.
2. **TASKS.md was not updated.** The brief limited me to `docs/research/`. Add a row for `research/affordable-housing` if you want it on the board.
3. **Not pushed** (per the brief). Push with `! git push origin research/affordable-housing` if you want it backed up remotely.
4. **Five questions to ask in the next customer calls:** Who's buying, CRE acquirers or HCV landlords? What did the last HAP shortfall cost? Who runs the pre-MOR scrub today, and for how much? Which systems do you export from? Has a deal ever stalled on compliance findings?
