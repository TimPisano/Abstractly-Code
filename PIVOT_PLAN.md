# PIVOT_PLAN — Abstractly for Section 8 landlords and property managers

Branch `pivot/section8` · worktree `~/dev/projects/abstractly-pivot-section8` ·
written 2026-10-11 off `main` `323d85f`. **Plan only. No code is changed on this
branch.** Each task in Step 4 gets its own branch + worktree via `/start-task`.

## Hard constraints

These apply to every task below.

1. **Brand stays as it is.** Do not touch the files in the list below. Only content, copy, features and structure change.
   - `frontend/design-system.css`
   - the token blocks in `frontend/landing.css`
   - `frontend/app/auth.css`
   - `frontend/fonts/`
   - the logo, favicon and og files
   - `design/logo/`
   - the shader colours in `landing.js`
   - the email palette in `email_service.py`

   Changing component CSS is fine only if it uses existing tokens. A `docs/design-tokens` task is in flight in TASKS.md, so coordinate with it rather than adding tokens.
2. **These keep working:** auth (signup, login, reset, team-setup), team isolation, the Calendly "Book a call" flow, demo-request and other emails, `render.yaml`, and the deploy config. **Nobody edits Render env vars.** New flags are read from the environment with a default of **off**, and only the user turns them on in the dashboard.
3. **No user data or DB tables are deleted.** CRE features are *deprecated*: hidden from nav and copy when Section 8 mode is on, with code, routes and tables kept. Schema changes are additive only: new tables, new nullable columns.
4. CLAUDE.md standing rules apply:
   - `@require_role` on every route.
   - Every new document table has `team_id NOT NULL`, scoped to the authenticated caller. Team isolation **is merged on main** (`3cff20b`); the CLAUDE.md Tenancy bullet is stale and `docs/claude-md-tenancy` fixes it.
   - Anthropic is mocked in tests.
   - Every bug fix gets a regression test.

---

## 0. What already exists (prior art) — build on it, don't redo it

**Searches run:**
- TASKS.md for section 8 / HAP / PHA / voucher / pivot.
- `git log --all` for the same terms plus HQS / NSPIRE / recert.
- All branches and worktrees, and both stashes (no Section 8 content in the stashes).

| Where | State | What it gives the pivot |
|---|---|---|
| `docs/research/section8.md` (main) | merged `2fbb542` | **Key finding:** for **HCV** the *PHA* does certifications, inspections and rent reasonableness. The landlord's paperwork is thin: the RFTA, the lease, the HAP contract, and getting paid. For **PBRA** the *owner/agent* certifies (50059 / TRACS / MOR). This shapes everything below: HCV features are about **getting paid and staying in compliance with the PHA**, and PBRA features add **owner-run recerts and HAP contract renewals**. |
| `feature/lease-intelligence` | Ready, reviewer MERGE, unmerged | Section 8 lease extraction behind `LEASE_MULTIFAMILY_FIELDS` (off): `section_8 {is_section_8, pha_name, contract_rent, tenant_rent, hap_amount, utility_allowance, hap_contract_start}`, `lease_changes` (PHA rent-change notices, recerts, renewals), `current_rent_amount`, `unit_number`. The HUD Tenancy Addendum and HAP contract no longer split one lease into 2–3. Rent is always the contract rent. Prompt v3 is Section 8-aware but **AI accuracy is unmeasured** (no funded key). |
| `qa/overnight-gauntlet` `a1cff89` | Reviewed MERGE, unmerged | Rent-roll aliases for `tenant_portion` and `hap`; contract rent wins, otherwise rent = portion + HAP. **`main` still has the tenant-share bug.** Reproduced on this branch: `Unit,Resident,Tenant Rent,Subsidy` → rent **$412**, should be $1,400. `Tenant Portion,HAP` only → rejected. |
| `fix/section8-tenant-share` | Plan written, awaiting approval (another session) | Per-row check that contract rent = tenant share + HAP, plus import warnings, on top of `a1cff89`. **This *is* "fix the known tenant-share vs rent confusion bug." Do not duplicate it.** |
| `qa/section8-fixtures` | Plan written, awaiting approval (another session) | Fictional HCV + PBV + PBRA fixture set: voucher leases + addenda, 5 HAP contracts, 5 rent rolls, **3 PHA HAP payment registers** (shortfall, abatement, proration), **3 HQS/NSPIRE inspection reports**, 20–25 planted errors with an `ANSWER_KEY`. **This is the test bed for tasks T2–T8.** |
| `feature/s8-hud-data` | Ready, reviewer MERGE, unmerged | `app/section8/hud_data/`: income limits, FMRs and MTSP by area/year in its own SQLite file, behind `SECTION8_HUD_DATA_ENABLED`. Natural home for payment standards / SAFMR / utility allowance schedules later. |
| `feature/s8-demo-files` | Reviewer MERGE; the user said don't merge | Oak Hollow, a 40-unit **PBRA** income-certification demo with 10 planted recert errors. Reuse for the PBRA recert track (T7b), not for the HCV core. |
| `docs/audit-2026-10-05` (`AUDIT.md`) | Committed, unmerged | **"Section 8 / tenant PII: not ready."** No SSN/DOB masking, full text sent to Anthropic, unencrypted SQLite, no team export/delete, no MFA. Its §5.2 minimum bar is T0 below. |
| `feature/deal-assistant` | Reviewed, unmerged | Team-scoped, citation-safe LLM assistant + credit metering. Base for the Phase 4 assistant. |
| `feature/loan-underwriting` | Unmerged, ~19 uncommitted files | DSCR / credit memo, lender-only. **Park it.** Not part of the pivot. |
| `docs/tester-pack` | Unmerged | In-app Help (17 articles, all deal-framed). The Help *framework* is reusable; its content gets rewritten in T12. |

---

## Step 1 — Audit: KEEP / ADAPT / REMOVE

**KEEP** = useful to Section 8 operators as is. **ADAPT** = keep but rework.
**REMOVE** = CRE-only. "Remove" means **deprecate**: hidden when Section 8 mode is on, with code, routes and tables left in place (constraint 3). Real deletion is a later, separate decision.

### 1a. Features

| Feature | Tag | Reason |
|---|---|---|
| Lease abstraction with page citations | ADAPT | The core engine stays; the field set changes from CRE terms to contract rent / tenant share / HAP / PHA / UA / addendum (lease-intelligence did most of this). |
| Field edit / verify / undo audit trail | KEEP | Operators need to correct an extracted HAP amount and show who changed it. |
| Amendments + versions | ADAPT | Becomes "PHA notices and renewals attached to the tenancy" (rent-change notices, HAP contract amendments). |
| Rent roll import (any PMS / Excel / PDF) | ADAPT | Must separate contract rent, tenant share and HAP (`a1cff89` + `fix/section8-tenant-share`), and keep the PHA and voucher columns. |
| Rent roll ↔ lease reconciliation | ADAPT | Compare all three numbers per unit (contract / tenant / HAP) against lease, HAP contract and latest PHA notice, not one "rent". |
| Deal Mismatch Report (dollar impact, citations, PDF/XLSX) | ADAPT | Same engine and export, reframed as the **Section 8 Rent Roll & HAP Report**. The audience becomes the operator, not a lender or LP. |
| Concession detection / effective rent | ADAPT | Keep for mixed (market + voucher) buildings. On voucher units a concession not reported to the PHA is itself a red flag (side payments are prohibited). |
| T-12 cross-check | REMOVE | An acquisition/underwriting artifact. HAP payment reconciliation answers "did we actually collect it?" better. Also has a live annual-vs-monthly bug in `t12_income_gap` (`deal_mismatch.py:753`). |
| Investment memo PDF/XLSX | REMOVE | IC/lender memo. |
| Lease summary memo PDF ("for IC, lender, broker") | ADAPT | Becomes a one-page unit/tenancy summary for the operator's file. |
| Portfolio metrics (CAM exposure, rent/sqft) | REMOVE | Commercial metrics. |
| Tenant concentration / HHI | REMOVE | Commercial credit-risk concept. The Section 8 analogue is "share of income by PHA" (T10). |
| WALT / rollover | REMOVE | Office/retail concept. Expirations remain via the timeline. |
| Loss-to-lease by $/sqft | REMOVE | psf comps are CRE. Rent reasonableness vs FMR / payment standard comes later (T8). |
| Expirations timeline | ADAPT | Lease end dates → HAP contract end dates, recert dates, reinspection deadlines. |
| Obligations (renewal notice, escalations, insurance) | ADAPT | Deadline engine stays. Inputs become recert, inspection, rent-increase notice and HAP renewal dates. Escalation/insurance inputs go. |
| Action items / Today | KEEP | Merged due-date list. Becomes the backbone of the "This month" dashboard (T10). |
| Alerts | ADAPT | Keep the framework. Drop `below_market_rent` (psf) and `tenant_concentration`; add HAP shortfall, missed payment, reinspection due and recert due. |
| Discrepancies (persistent, resolve/reopen, comments) | KEEP | Exactly what HAP and rent-roll findings need. New `discrepancy_type`s only. |
| Tasks, assignments, comments, team notes | KEEP | Operators assign "call PHA about unit 4B shortfall". |
| Risk analysis (missing protections, escalation outliers) | REMOVE | Commercial-centric; fires wrongly on apartment leases (lease-intelligence hand-off #4). |
| Lease compare / benchmark | REMOVE | Compares rent, psf, CAM and escalation across tenants. Little Section 8 value. |
| Portfolio trends / property trends | ADAPT | Keep history; trend HAP collected vs expected by month and by PHA. |
| Health score / confidence summary | KEEP | Data trust applies equally. |
| Extraction quality (field reliability, owner trend) | KEEP | Internal QA. Field list updates with the new fields. |
| Rule-based Q&A (`/qa`) | ADAPT | Swap CAM / exclusivity / psf intents for HAP / tenant share / PHA / recert intents (small), or retire it once the Phase 4 assistant ships. |
| LLM assistant (`/assistant/ask`) | ADAPT (Phase 4) | Final phase; build on `feature/deal-assistant`. |
| CRE knowledge chatbot (`cre_qa.py`) | REMOVE | Already dead code (imported nowhere). |
| Team chat / messaging | KEEP | Neutral. |
| Linked email accounts (send-as Gmail/Graph) | KEEP | Useful later for emailing PHA caseworkers. No change now. |
| Google Sheets / CSV / XLSX exports | ADAPT | Keep the mechanism; drop CAM and psf columns, add contract / tenant / HAP / PHA columns. |
| Sample deal loader (Maple Ridge) | ADAPT | Replace with a Section 8 sample portfolio from `qa/section8-fixtures` (T13). Keep Maple Ridge files for the regression tests. |
| Demo deployment seed (`demo_seed.py`: coffee shop, office, CAM) | ADAPT | Reseed with Section 8 sample data (T13). |
| Auth, signup, reset, team-setup, team members, roles | KEEP | Constraint 2. |
| Usage limits / quotas / dedup | KEEP | Constraint 2. Tier limits get re-labelled in units. |
| Owner console (teams, accounts, finance, analytics, extraction quality) | KEEP | Internal. |
| Waitlist / access requests | KEEP | Its email copy ("real estate firms") gets reworded in T11. |
| Demo request form + emails + Calendly (`/public-config`) | KEEP | Mechanics untouched. Copy reworded in T11. |
| Analytics pageviews | KEEP | Neutral. |
| Loan underwriting (unmerged branch) | REMOVE | Lender DSCR tool; parked, never merged in the pivot. |

### 1b. Routes (all in `backend/app/api.py`, no blueprints)

The tag applies to the whole group unless an exception is named.

| Route group | Tag | Reason |
|---|---|---|
| `/auth/*` (login, logout, session, change-password, forgot/reset, team-setup, options, signup, link-status, resend-link, complete-signup) | KEEP | Constraint 2. |
| `/team/members*`, `/team/usage`, `/teams*` | KEEP | Tenancy and quotas. |
| `/extract`, `POST /leases`, `/leases/batch`, `/leases/<id>/resubmit`, `/leases/<id>/versions`, `GET /leases`, `GET /leases/<id>` | ADAPT | Same upload pipeline. Doc kinds widen to HAP contract, PHA notice, inspection report, PHA payment register. |
| `/leases/<id>/fields/<f>` (GET source, PATCH, verify, undo) | KEEP | Citation + correction mechanics are field-agnostic. |
| `/leases/<id>/amendments*` | ADAPT | Attach PHA notices / HAP amendments to the tenancy. |
| `/leases/<id>` PATCH, DELETE, `/leases/bulk-delete`, tags, bulk-tag, `/tags`, lease comments | KEEP | Neutral housekeeping. |
| `/leases/sample`, `/sample-deal/load` | ADAPT | Section 8 sample (T13). |
| `/leases/compare`, `/leases/<id>/benchmark` | REMOVE | CRE comparison (rent/psf/CAM/escalation). |
| `/leases/selection-summary` | KEEP | Neutral aggregate. |
| `/leases/<id>/risks`, `/portfolio/risks` | REMOVE | Commercial risk rules. |
| `/leases/import-rent-roll` | ADAPT | Contract/tenant/HAP split (in flight). |
| `/portfolio/rent-roll-reconciliation`, `/portfolio/reconciliation/run`, `/portfolio/rent-roll-ai-validation` | ADAPT | Three-number comparison. Drop `square_footage` and `cam_charges` from `ai_rent_roll_validation.COMPARABLE_FIELDS`. |
| `/portfolio/deal-mismatch-report` (+ `.pdf`, `.xlsx`) | ADAPT | Becomes the Section 8 Rent Roll & HAP Report. The **route path stays** for compatibility, with new labels. |
| `/portfolio/t12-reconciliation` | REMOVE | T-12 is acquisition-only. |
| `/portfolio/investment-memo.pdf` / `.xlsx` | REMOVE | Lender/IC memo. |
| `/leases/<id>/summary.pdf`, `/leases/<id>/export.xlsx`, `/leases/export.xlsx`, `/portfolio/rent-roll.csv` / `.xlsx`, Google Sheets ×3 | ADAPT | Swap CRE columns for Section 8 columns. |
| `/portfolio/report`, `/portfolio/summary.pdf`, `/portfolio/monthly-report.pdf` | ADAPT | Monthly report becomes "HAP collected vs expected, inspections, recerts due". |
| `/portfolio/summary` | ADAPT | Drop `total_cam_exposure` and rent/sqft; add voucher-unit count, HAP share of income, PHAs. |
| `/portfolio/tenant-concentration`, `/portfolio/rollover`, `/portfolio/loss-to-lease` | REMOVE | Commercial metrics. |
| `/portfolio/timeline`, `/portfolio/expiration-alerts`, `/portfolio/obligations` | ADAPT | Section 8 deadlines. |
| `/portfolio/attention`, `/portfolio/health`, `/portfolio/health-score`, `/portfolio/confidence-summary`, `/portfolio/trends`, `/portfolio/property-trends`, `/activity` | KEEP | Neutral (trends gain HAP series in T10). |
| `/alerts*` | ADAPT | New alert types; CRE types hidden. |
| `/discrepancies*`, `/comments/recent` | KEEP | New types only. |
| `/tasks*`, `/assignments*`, `/today`, `/action-items` | KEEP | Backbone of the "This month" view. |
| `/assistant/ask`, `/assistant/conversations` | ADAPT (Phase 4) | Final phase. |
| `/qa` | ADAPT | Section 8 intents, or retire later. |
| `/threads*`, `/messages/unread-count`, `/email-accounts*` | KEEP | Neutral. |
| `/waitlist*`, `/demo-request`, `/public-config`, `/analytics/pageview` | KEEP | Constraint 2. Copy only. |
| `/owner/*`, `/extraction-quality/*` | KEEP | Internal. |
| `/health`, `/config`, `/demo/reset` | KEEP | Deploy plumbing. |

### 1c. Backend modules

| Module | Tag | Reason |
|---|---|---|
| `auth`, `password_rules`, `security`, `token_encryption`, `logging_config`, `cache`, `jobs`, `usage_limits*`, `email_service`, `email_accounts`, `messaging`, `tasks`, `assignments`, `action_items`, `discrepancies`, `portfolio_history`, `portfolio_health_score`, `extraction_quality`, `pdf_extractor`, `document_extractor`, `sample_deal` | KEEP | Neutral infrastructure. |
| `field_extractor.py` | ADAPT | Keep the engine. Section 8 fields come from lease-intelligence; CRE extractors (`cam_charges`, `exclusivity_clause`, `permitted_use`, `insurance_requirements`, `square_footage`, `rent_escalation`) are no longer *shown* in Section 8 mode but still run, since that is harmless. |
| `ai_extraction.py` | ADAPT | `SYSTEM_PROMPT` "commercial real estate…" and "Abstract the following commercial lease" become residential/Section 8 (v3 on lease-intelligence); add the HAP contract doc kind. |
| `multifamily_charges.py` (lease-intelligence) | KEEP | Already Section 8-aware. |
| `concessions.py` | KEEP | Multifamily. |
| `normalize.py` | KEEP | psf/% helpers are harmless. |
| `rent_roll_import.py`, `rent_roll_table_extract.py` | ADAPT | Contract/tenant/HAP + PHA + voucher-holder columns. |
| `rent_roll_export.py`, `sheets_export.py`, `report.py`, `summary_memo.py` | ADAPT | Swap CAM/psf columns and lender framing. |
| `deal_mismatch.py`, `deal_mismatch_export.py` | ADAPT | Section 8 checks and labels; drop the "lender/LP" wording. |
| `portfolio.py` | ADAPT | Keep reconciliation. CAM, HHI, WALT and psf functions are no longer called in Section 8 mode. Also fix `_is_rent_roll_import` treating only `.csv/.xlsx` filenames as rent rolls (`portfolio.py:1384`). |
| `obligations.py`, `alerts.py` | ADAPT | Section 8 deadline and alert types. |
| `risk_analysis.py`, `comparison.py` | REMOVE | Commercial rules and benchmarks. |
| `t12_import.py`, `t12_statement.py` | REMOVE | Acquisition artifact. |
| `investment_memo.py` | REMOVE | IC/lender memo. |
| `cre_qa.py` | REMOVE | Dead code already. |
| `qa_engine.py` | ADAPT | Section 8 intents. |
| `assistant.py` | ADAPT (Phase 4) | — |
| `demo_seed.py` | ADAPT | Section 8 demo seed. |
| `extraction_scoring.py` | ADAPT | Weighted fields → Section 8 fields. |
| `app/section8/hud_data/` (unmerged) | KEEP | Reference data for T8. |

### 1d. Data model (all in `database.py`)

| Table | Tag | Reason |
|---|---|---|
| `leases` (every document + every rent-roll row, fields in JSON) | ADAPT | Stays the document store. Gains links to unit/tenancy/PHA through new tables, not new columns. |
| `discrepancies`, `discrepancy_resolutions` | KEEP | New `discrepancy_type`s; `estimated_dollar_impact` already exists. |
| `alerts` | ADAPT | New alert types. |
| `tasks`, `assignments`, `comments`, `activity_log`, `lease_tags`, `lease_field_edits` | KEEP | Neutral. |
| `teams`, `users`, `usage_events`, `password_reset_tokens`, `signup_requests` | KEEP | Constraint 2. |
| `waitlist_signups`, `demo_requests`, `pageviews`, `revenue_entries`, `expense_entries` | KEEP | Marketing/owner. |
| `assistant_conversations`, `message_threads*`, `messages`, `linked_email_accounts`, `oauth_states` | KEEP | Neutral. |
| `ai_extraction_runs`, `training_rounds` | KEEP | Telemetry. |
| `loan_requests`, `t12_snapshots` (loan branch only, not on main) | REMOVE | Never merged. |
| **Missing today** | NEW | No properties, units, households, PHAs, HAP contracts, HAP payments, inspections, recerts or rent-change requests. A unit is only an address string inside JSON. T1 adds them. |

### 1e. Extraction fields

| Field | Tag | Reason |
|---|---|---|
| tenant | ADAPT | Becomes head of household + co-residents (lease-intelligence). |
| landlord | ADAPT | Owner / management agent, the payee on the HAP contract. |
| rent_amount | ADAPT | Must be **contract rent** (rent to owner), never tenant share (lease-intelligence). |
| lease_start_date / lease_end_date | KEEP | Needed; also check that the lease starts on/after the HAP contract start. |
| property_address | ADAPT | Split out `unit_number` (lease-intelligence). |
| security_deposit | KEEP | Relevant (PHAs cap deposits in some jurisdictions; just extract it). |
| concessions | KEEP | Mixed buildings; side-payment flag on voucher units. |
| renewal_options | ADAPT | Residential renewal terms / month-to-month conversion. |
| termination_options | ADAPT | Notice to vacate terms; the regex engine only, so add to AI. |
| default_cure_period | ADAPT | Residential notice periods; low priority. |
| cam_charges | REMOVE | Commercial. |
| rent_escalation | REMOVE | Commercial. Residential rent changes come through PHA notices (`lease_changes`). |
| permitted_use | REMOVE | Commercial. |
| exclusivity_clause | REMOVE | Commercial. |
| insurance_requirements | REMOVE | Commercial CGL limits (renter's insurance is rarely relevant to HAP). |
| square_footage | REMOVE | Used only for psf metrics. Bedrooms matter instead (new field). |
| *(lease-intelligence)* unit_number, pet/parking/utility charges, section_8{…}, lease_changes, current_rent_amount / current_lease_end_date | KEEP | Already built behind `LEASE_MULTIFAMILY_FIELDS`. |
| **NEW** (T2) | NEW | `bedrooms`, `utility_responsibility` (who pays which utility; must match the HAP contract), `tenancy_addendum_present` (HUD-52641-A attached and unmodified), `hap_contract{number, form (52641 / 52530 / PBRA), pha, owner, unit, contract_rent, term start/end, initial HAP, UA}`, `voucher_size`, `pha_caseworker` (optional). |

### 1f. Frontend pages and views

| Page / view | Tag | Reason |
|---|---|---|
| `index.html` | ADAPT | Same sections and layout, all copy rewritten (Step 3). |
| `pricing.html`, `pricing-config.js`, `pricing.js` | ADAPT | Same tier cards, Section 8 copy and limits. |
| `404.html` | KEEP | Only its shared meta description changes. |
| `app/login`, `signup`, `forgot-password`, `reset-password`, `finish-signup`, `team-setup` | KEEP | Meta description + the signup "private beta" line only. |
| App: Dashboard | ADAPT | Becomes the **This Month** dashboard (T10). Drops CAM exposure, tenant concentration, rollover and loss-to-lease panels. |
| App: Action Items, Tasks, Discrepancies, Team, Team Notes | KEEP | Neutral. |
| App: Alerts | ADAPT | Section 8 types. |
| App: Deal Mismatch Report | ADAPT | Renamed **Rent Roll & HAP Check**. The T12 upload is removed from the form. |
| App: Upload (leases / rent roll / T12) | ADAPT | Upload leases & HAP contracts, rent roll, PHA payment report, inspection report. T12 removed. |
| App: Expirations | ADAPT | Becomes the **Deadlines** view (HAP contract end, recert, reinspection, rent-increase notice). |
| App: Rent Roll | ADAPT | Contract / tenant / HAP / PHA columns. |
| App: Compare | REMOVE | CRE benchmark. |
| App: Portfolio Trends | ADAPT | HAP collected vs expected by month/PHA. "Rollover Risk Timeline" removed. |
| App: Ask a Question | ADAPT | Section 8 example chips (no "CAM exposure", "exclusivity"). |
| App: Portfolio Report | ADAPT | Monthly Section 8 report. |
| App: Lease Detail | ADAPT | Section 8 group becomes primary; CRE groups hidden. |
| App: Export modal (investment memo) | REMOVE | IC/lender memo. |
| App: Messaging | KEEP | Neutral. |
| **NEW** views | NEW | HAP Payments (T5), Inspections (T6), Recerts & Rent Changes (T7), Rent Increases & Renewals (T8), Units / Unit file (T9), PHAs (T9). |
| `admin/*` | ADAPT | Same views as the app (it reuses the app JS); "Deal Assistant" label becomes "Assistant". |
| `owner/*` | KEEP | Internal. The funnel heading is fine. |
| In-app Help (`docs/tester-pack`, unmerged) | ADAPT | Keep the framework, rewrite all 17 deal-framed articles. |

### 1g. Marketing and outbound copy

| Copy | Tag | Reason |
|---|---|---|
| Title / og / twitter meta: "Check The Rent Roll Before You Close", "…before your deal closes… lender or LP… syndicators" (copied into 14 pages) | REMOVE | Deal/syndicator framing. One new description is propagated everywhere. |
| Announcement "Now onboarding beta testers. Book a demo →" | KEEP | Still true. |
| Nav: How It Works · Built For Multifamily · Trust · Pricing · FAQ | ADAPT | "Built For Multifamily" becomes "Built For Section 8". |
| Hero eyebrow / H1 / subhead / CTAs | ADAPT | Step 3. |
| Hero deal-card (Maple Ridge, "$42,780 Annual Income Overstated", "Rent roll as of") | ADAPT | Same card component with fictional Section 8 rows (HAP shortfall, abatement, tenant share booked as rent). |
| Problem section + commercial sample (2200 Larimer St Suite 140, Ridgeline Coffee Roasters) | REMOVE | A commercial unit. Replace with a fictional voucher unit. |
| How It Works ("broker's hand-built Excel", "Export a report for your lender or LP", "underwriting the deal") | ADAPT | Steps are leases + HAP contracts + PHA reports in, mismatches and money owed out, a monthly report for the owner. |
| Built For Multifamily cards ("15 anchor tenants", "acquisition", "closing table", "seller's rent roll", "walk or reprice") | REMOVE | Acquisition framing. |
| Chips: OCR, PMS import, "T-12 cross-check", citations | ADAPT | Swap T-12 for "PHA payment reconciliation". |
| Trust pillars | KEEP | Isolated per team and source citations are true. **"Never used to train AI" carries a `TODO: verify`**; resolve it before relaunch, and do **not** add "SSN masking" until T0 ships. |
| Pricing preview, "Free pilot available" | ADAPT | New tier names and limits. |
| FAQ (6 questions incl. "Does this replace my analyst?", "is this deal worth pursuing") | ADAPT | Rewrite (Step 3). |
| Book a Demo section + form labels ("Number of Units in Portfolio") | ADAPT | Field ids and payload unchanged; labels only. |
| Footer, contact email, `data-book-call` | KEEP | Constraint 2. |
| Pricing tier descriptions ("small syndicators doing a few deals", "underwriting deals every week", "embedded in how they underwrite") and features (Deal Mismatch Report, T-12) | ADAPT | Step 3. |
| Pricing FAQ (contracts, pilot, accuracy, security, training, cancel) | KEEP | Reworded lightly; two TODOs remain open. |
| Demo confirmation email ("how {company} handles leases and rent rolls today") | ADAPT | Section 8 wording; same function and Calendly link. |
| Demo admin notification | KEEP | "Units in portfolio" becomes "Assisted units". |
| Waitlist email ("limited number of real estate firms") | ADAPT | Becomes "Section 8 owners and managers". |
| Auth emails (signup, reset, team setup) | KEEP | Product-neutral. |
| `landing-interactive` branch calculator ("seller's rent roll", "deal you're looking at") | ADAPT | Becomes "What could unreconciled HAP cost you?" (units × HAP × assumed shortfall rate). Only if that branch merges. |
| App sidebar / 404 generic "building" icon | KEEP | Brand constraint; not this pivot's job. |

---

## Step 2 — The Section 8 feature set

### Who we're building for

- **HCV landlords and PMs** are the **primary ICP for launch**: 20–2,000 voucher units, often across **several PHAs**, frequently mixed with market-rate units. Their pain is cash and compliance with the PHA:
  - HAP that arrives short, late or not at all, and is hard to reconcile per unit across PHA portals.
  - Abatements after failed inspections.
  - Tenant-share changes after PHA reexams that never reach the ledger.
  - Rent increases that need PHA approval and notice.
  - Paperwork scattered across email and portals.
- **Project-based owners and agents (PBRA, and PBV)** are the **secondary ICP, Phase 2**. HAP contract renewals and rent adjustments (OCAF, MAHRA renewal options, rent comparability studies) carry heavy stakes. Owners run recerts themselves (50059, TRACS, MOR findings), which is the Oak Hollow demo's territory. This involves more tenant PII; see T0.

**Regulatory caveat.** Rules below (cure deadlines, notice periods, renewal lead times) vary by PHA admin plan, HAP contract form and HUD notice, and **none has been practitioner-checked** (same caveat as the research doc). The rule:
- Every deadline is a **per-PHA / per-contract configurable setting** with a default, never hard-coded.
- The UI says where each default comes from.
- Before launch, a Section 8 practitioner reviews the defaults (open question Q4).

### Features

| # | Feature | Why operators need it | Reuses | Size | Depends on |
|---|---|---|---|---|---|
| F1 | **Lease + HAP contract abstraction.** Lease: contract rent, tenant share, HAP, UA, PHA, unit, bedrooms, utility responsibility, Tenancy Addendum present. HAP contract (HCV 52641, PBV 52530A/B, PBRA): contract number, PHA/CA, owner/payee, unit(s), contract rent, term start/end, initial HAP. PHA notices: rent change, tenant share change, effective date. | Every other check needs these three numbers per unit with a page citation. Today they live in PDFs the operator re-keys. | `field_extractor`, `ai_extraction`, `multifamily_charges.parse_section_8` + `lease_changes` (lease-intelligence), citations, edit/verify UI, amendment linking | M | Merge lease-intelligence; T1 for linking |
| F2 | **Rent roll validation (three numbers).** Contract = tenant + HAP per row (in flight). Rent roll vs lease vs HAP contract vs latest PHA notice for each of contract / tenant / HAP. Flags: tenant share booked as rent, HAP on roll ≠ PHA notice, contract rent ≠ HAP contract, voucher unit with no HAP contract, lease starting before the HAP contract, utility responsibility differs between lease and HAP contract. | The roll is the operator's billing source. If the tenant share is stale, they over/under-bill the tenant and mis-forecast HAP. | `rent_roll_import` (+ `a1cff89`, `fix/section8-tenant-share`), `deal_mismatch` detectors + dollar impact, `deal_mismatch_export`, `discrepancies` | M | fix/section8-tenant-share, lease-intelligence |
| F3 | **HAP payment reconciliation.** Import PHA payment registers / remittance reports (CSV, XLSX, PDF from PHA portals). Expected HAP per unit-month (from the latest notice or HAP contract, prorated for move-in/out) vs received. Group by unit, PHA and month. Flags: shortfall, overpayment, missing payment, abatement, HAP received after move-out (must be returned), payment to the wrong unit/owner, and a recurring short pattern by PHA. Dollar impact plus export. | HAP is often 60–100% of rent on a voucher unit. A $200 shortfall unnoticed for 6 months is $1,200 the operator may never recover. Today reconciliation is a spreadsheet per PHA. | Column matching from `rent_roll_import`, `document_extractor` (PDF tables), `rent_roll_table_extract`, the `deal_mismatch` dollar-impact pattern, `discrepancies`, `rent_roll_export` / `deal_mismatch_export` | L (split into T4 + T5) | T1, F1/F2 for expected HAP; fixtures for testing |
| F4 | **Inspection tracking (HQS / NSPIRE).** Per unit: inspection type (initial / annual / biennial / special / reinspection / QC), standard (HQS or NSPIRE-V, set per PHA), date, result, failed items (life-threatening vs not), cure deadline, reinspection date, owner-vs-tenant responsibility. Import PHA inspection notice PDFs via extraction, with a manual-entry fallback. Links a failed inspection to the expected **abatement start** that F3 then checks. | A missed cure deadline means abated HAP the operator can't recover from the tenant. Inspection letters arrive by mail/email per PHA on different cycles. | Upload pipeline, AI/regex extraction, citations, `tasks` (auto-create "fix item X by date"), `obligations`, `alerts` | L | T1; inspection fixtures |
| F5 | **Recertification and rent-change tracking.** **HCV:** the PHA runs the reexam. The operator tracks the expected reexam month per tenancy, receives the PHA's change notice, and confirms new tenant share and HAP took effect on both the roll and the HAP received (closes the loop with F2/F3). **PBRA (T7b):** owner-run recert cascade (120/90/60/30-day notices, 50059 signatures, EIV, 120-day verification validity), using Oak Hollow's rules. | HCV: a tenant-share change that never hits the ledger is the most common rent-roll error. PBRA: late recerts and missing signatures are top MOR findings and can mean HAP recapture. | `lease_changes` (lease-intelligence), `obligations`, `action_items`, `alerts`, Oak Hollow demo + rules (PBRA) | M (HCV) + L (PBRA) | T1, T2 |
| F6 | **Rent increase requests + HAP contract renewals.** **HCV:** request record (current / requested contract rent, PHA, date submitted, required notice period (configurable, commonly 60 days), earliest allowed effective date, since no increase is allowed during the initial term, status submitted → approved / denied / countered, approved amount, effective date); checks the approved rent then shows on the roll and in HAP received. Optional rent-reasonableness context from FMR / payment standard via `hud_data`. **PBRA / PBV:** HAP contract expiration, renewal option, submission deadline (configurable lead time), the one-year tenant notice if opting out, and annual OCAF / rent adjustment anniversary. | A rent increase submitted late is a year of lost rent. A missed PBRA renewal deadline endangers the whole building's subsidy. | `obligations`, `tasks`, `alerts`, `hud_data` (FMR), F1 HAP contract fields | M | T1, T2; `s8-hud-data` merged for the FMR context |
| F7 | **Multi-PHA support + unit/tenant document file.** A PHA directory per team (name, jurisdiction, payment day, inspection standard, notice periods, portal URL, contacts) is where the configurable deadline defaults live. A unit page shows the current tenancy (household, PHA, voucher size, contract / tenant / HAP), all documents (lease, addendum, HAP contract, notices, inspections, payment lines) in date order with citations, open findings, and tasks. | Operators think in units and PHAs, not documents. One place per unit is what they show a PHA, auditor or buyer. | `leases` as the document store, amendments linking, `assignments` (property/unit owner), `comments`, `tasks` | M | T1 |
| F8 | **This Month dashboard.** Due / overdue / underpaid for the current month: HAP expected vs received (by PHA), units underpaid, abatements in effect, inspections due and cure deadlines, recerts due, rent-increase notices due, HAP contracts nearing renewal, with dollar totals and one-click tasks. | The question an operator asks every month: "what's due and what am I owed?" | `action_items`, `/today`, `alerts`, `discrepancies/summary`, dashboard view shell | M | T5, T6, T7, T8 (each panel lights up when its feature lands) |
| F9 | **AI assistant** ("Which units at Harrow County Housing Authority were short last month?") | Natural-language access to all of the above. | `feature/deal-assistant` (team-scoped citations, credit metering) | — | **Phase 4. Not planned in detail yet.** |

**Explicitly not in this plan (Out of scope):**
- Tenant-facing anything.
- Submitting to PHA portals or TRACS (we read their exports; we don't write to them).
- Bank-feed reconciliation (later: match HAP deposits to bank lines).
- LIHTC compliance (TIC, 8823).
- HOTMA income calculation.
- Payment standard / utility allowance databases beyond what `hud_data` already holds.
- PMS integrations / APIs.
- Deleting CRE code.

---

## Step 3 — Copy and positioning

**Positioning line:** *Abstractly checks every Section 8 unit against its lease, HAP contract and PHA payments, so you catch shortfalls, abatements and missed deadlines this month, not at year-end.*

**vs. what they use now:**
- Yardi / AppFolio / RealPage *record* HAP and certifications; they don't *audit* them against the documents.
- PHA portals each show one PHA.
- Spreadsheets don't read PDFs.

We read the documents, cite the page, and put a dollar figure on every gap. **Prophia is no longer the comparison** (office/CRE); drop it from positioning.

**Claims discipline:** copy only claims what is shipped and verified at the time it merges. The copy below assumes T2, T3 and T5 are live. Lines that depend on later tasks are marked **[T6]**, **[T7]**, **[T8]**, and stay out of the page until those tasks merge.

### 3a. Homepage (`index.html`, same sections, same order, same components)

**Meta (title / og / twitter, all 14 pages):**
- Title: "Abstractly — Every HAP dollar, accounted for"
- Description: "Abstractly reads your Section 8 leases, HAP contracts and PHA payment reports and checks them unit by unit — contract rent, tenant share and HAP — with every finding cited to the page. Built for Section 8 landlords and property managers."

**Announcement bar:** "Now onboarding Section 8 beta testers. Book a demo →"

**Nav:** How It Works · Built For Section 8 · Trust · Pricing · FAQ · Client Login · Book a Demo

**Hero**
- Eyebrow: "Built for Section 8 landlords and property managers"
- H1: "Every HAP dollar, / **accounted for.**" (same two-line split, second line in the accent style)
- Subhead: "Abstractly reads your leases, HAP contracts and PHA payment reports and checks every voucher unit — contract rent, tenant share, HAP — so shortfalls and missed changes get caught this month, not at year-end."
- CTAs: "Book a Demo" · "See a sample report"
- Card (same component, fictional data): tag "Sample Report — Juniper Row, fictional demo portfolio · 3 PHAs"; count-up "**$X** HAP owed to you" (figure taken from the fixture answer key in T11, not invented here). Rows:
  - 4B "HAP short 3 months — PHA notice not applied"
  - 12 "Tenant share booked as full rent"
  - 7A "HAP still paid after move-out — must be returned"
  - 3C "Abatement: reinspection missed" **[T6]**, or drop it until T6
  - "+ N more findings · Payments through 09.30.2026"

**The Problem**
- Eyebrow: "The Problem"
- H2: "Your rent roll, your HAP contracts and your PHA payments don't agree."
- Body: "A tenant-share change lands in a caseworker's letter and never reaches the ledger. A PHA pays last year's HAP for months. A unit fails reinspection and the abatement shows up as a short deposit nobody can explain. Each one is small. Across a few hundred voucher units and three PHAs, it's real money."
- Sample finding card (fictional voucher unit, same three-card layout):
  - Unit 4B, Harrow County Housing Authority: contract rent $1,400 (HAP contract p.2) · tenant share $412 (PHA notice 07/01, p.1) · HAP received $788 vs $988 expected — **$200/mo short**
  - "Rent roll shows tenant share $312" (rent roll row 14) — tenant under-billed $100/mo
  - Each with page citations, same as today's cards.

**How It Works** — "Three kinds of files in. Every gap out."
1. "Upload your leases, HAP contracts and PHA payment reports." Body: "PDFs straight from the PHA portal, scanned addenda, and your rent roll from Yardi, AppFolio, RealPage, MRI, Buildium or Excel."
2. "See every unit that doesn't add up, with a dollar figure." Body: "Contract rent, tenant share and HAP checked against the lease, the HAP contract, the latest PHA notice and what the PHA actually paid. Every finding links to the page it came from."
3. "Work the list, and keep a file per unit." Body: "Assign findings, export a PDF or Excel report for the owner, and keep each unit's documents in one place for the next PHA question." **[T9 for the unit file; otherwise drop the second clause.]**

**Built For Section 8** (replaces "Built For Multifamily")
- H2: "Built for voucher portfolios, not office leases"
- Sub: "Most lease tools were built for commercial real estate. Section 8 is a three-party deal — you, the tenant and the PHA — and the money comes from two places."
- Cards:
  - "Two payers per unit": "We track tenant share and HAP separately, so a short HAP payment never hides behind a full tenant payment."
  - "Many PHAs, one view": "Payment reports, notices and deadlines from every housing authority you work with, side by side."
  - "Deadlines that cost money": "Reinspections, recerts, rent-increase notices and HAP contract renewals on one calendar **[T6/T7/T8]**."
- Chips: "OCR for scanned PHA letters" · "Yardi / AppFolio / RealPage / MRI / Buildium import" · "PHA payment reconciliation" · "Citation-linked findings"

**Trust** — "What's actually true today". Keep the three pillars:
- "Isolated per team"
- "Every finding cites its source"
- "Never used to train AI": resolve the TODO before relaunch

Add only after T0 ships: "Sensitive numbers masked: SSNs and dates of birth are redacted before anything is stored or sent to an AI model."

**Pricing preview** — "Straightforward monthly pricing" · "Three plans, flat monthly or annual per team, sized by assisted units." · "Free pilot available for early testers." · "Compare All Plans →"

**FAQ** — "Questions we'd ask too"
1. "What happens to our data — including tenant information?" (current answer + T0 masking once shipped; plain about what we store)
2. "How accurate is the extraction?" (keep current honest answer; mention scanned PHA letters + page citations)
3. "Which files do you read?" Answer: "Leases and HUD Tenancy Addenda, HAP contracts, PHA rent-change and tenant-share notices, PHA payment reports, and rent rolls from Yardi, AppFolio, RealPage, MRI, Buildium, or Excel/CSV. Inspection notices **[T6]**."
4. "We work with several housing authorities. Does that matter?" Answer: "That's the point. Each PHA's payments and notices are reconciled separately and shown together."
5. "Does this replace our PMS?" Answer: "No. Your PMS records what should happen; Abstractly checks it against the documents and the money that arrived."
6. "Do you submit anything to the PHA or HUD for us?" Answer: "No. We read what they send you; you stay in control of every submission."
7. "How do I reach you?" (unchanged, `data-book-call`)

**Book a Demo**
- Eyebrow: "Book a Demo"
- H2: "See it on your own voucher units."
- Sub: "Send us one PHA payment report and the rent roll for the same month — we'll show you every unit that doesn't match."
- Form labels (ids, names and payload **unchanged**):
  - "Name"
  - "Work email"
  - "Company"
  - `#demoUnits`: "Number of Section 8 units"
  - `#demoMessage` placeholder: "Which housing authorities do you work with? (optional)"
- Fallback: "Prefer email? tim@getabstractly.com"

**Footer:** unchanged.

### 3b. Pricing page

- H1: "Straightforward monthly pricing"
- Sub: "Every plan starts with a walkthrough on your own units, not a self-serve checkout."
- Tiers (same cards, same toggle). **Prices are a proposal; see open question Q2.** Today's $499 / $1,250 was set for syndicators.

| Tier | Description | Monthly / annual | Limits | Features |
|---|---|---|---|---|
| Starter | "For independent landlords with a voucher portfolio." | $199 / $159 *(proposal)* | Up to 100 Section 8 units · 3 users | Lease & HAP contract abstraction · Rent roll check (contract / tenant / HAP) · HAP payment reconciliation · PDF & Excel reports |
| Growth *(Most Popular)* | "For property managers working with several housing authorities." | $599 / $479 *(proposal)* | Up to 750 units · 10 users | Everything in Starter · Multi-PHA dashboard · Inspection & recert deadlines **[T6/T7]** · Rent increase tracking **[T8]** · Priority support |
| Enterprise | "For project-based owners and large portfolios." | Contact us | Custom | HAP contract renewals & rent adjustments **[T8]** · Custom onboarding · Dedicated support · Security review |

- Pricing FAQ: keep all questions. Reword "How accurate is the extraction?" for PHA documents; add "Do you price per unit?" → "Plans are flat per team, sized by the number of Section 8 units you manage."
- Statement: "Tell us how many voucher units and housing authorities you work with, and we'll point you to the right plan."

### 3c. Demo booking (emails, same functions, Calendly unchanged)

- **Confirmation email** — subject unchanged ("Thanks for reaching out, {first_name}"). Body change, one sentence: "I'd love to hear how {company} keeps track of HAP payments, PHA notices and inspections today, then show you how Abstractly catches the units that don't add up — it takes about 20 minutes." Calendly line and sign-off unchanged.
- **Admin notification:** "Units in portfolio" becomes "Section 8 units".
- **Waitlist confirmation:** "a limited number of real estate firms" becomes "a limited number of Section 8 owners and property managers".
- **Signup closed state:** "We're in private beta" (unchanged) + link to `#book-demo`.

---

## Step 4 — Build order (claimable tasks)

### How tasks run

- Each row is **one branch + one worktree**, claimed through `/start-task` in TASKS.md, with its own `docs/plans/<branch>.md` approved before building.
- All new Section 8 surfaces sit behind **`SECTION8_MODE`** (default **off**): the new routes 404 and new nav items stay hidden. With it on, CRE views (the REMOVE rows above) are hidden.
- Flags are read from the environment; the user flips them in the Render dashboard (constraint 2).
- Every task: `@require_role` on all routes, `team_id NOT NULL` on all new tables, Anthropic mocked, tests registered in `run_all_tests.py`, headless screenshots for UI.
- The test bed is the `qa/section8-fixtures` answer key: each task's tests assert its planted errors are caught.

**Phase 0 — prerequisites (mostly existing branches; each needs the user's `/merge-branch`)**

| ID | Task | Size | Notes |
|---|---|---|---|
| P1 | Merge `feature/lease-intelligence` | — | Section 8 lease fields. Ready, MERGE. |
| P2 | Merge `qa/overnight-gauntlet` (carries `a1cff89`) | — | Waiting on the user's 3 QA_REPORT decisions. |
| P3 | `fix/section8-tenant-share` — approve its plan, build, merge | S | In flight (other session). **This is the tenant-share bug fix.** |
| P4 | `qa/section8-fixtures` — approve its plan, build, merge | M | In flight (other session). Test bed for everything. |
| P5 | Merge `feature/s8-hud-data` | — | Ready, MERGE. Needed by T8 only, so not blocking. |
| T0 | `feature/s8-pii-guard`: SSN/DOB/bank-number masking before storage **and** before Anthropic; scrub tracebacks from alert emails; per-team "AI processing off" switch | M | From AUDIT.md §5.2. **Must merge before any real tenant documents are uploaded by testers.** Independent of everything else; can start now. Encryption at rest, MFA and export/delete are tracked separately (Q5). |

**Phase 1 — core (abstraction + rent roll + HAP reconciliation)**

| ID | Branch | What | Reuses | Size | Depends on | Parallel with |
|---|---|---|---|---|---|---|
| T1 | `feature/s8-data-model` | `SECTION8_MODE` flag helper. New tables, all `team_id NOT NULL`, scoped CRUD in `database.py`, minimal team-scoped CRUD routes, no UI: `properties` (program HCV/PBV/PBRA/mixed), `units` (bedrooms), `phas` (per-team settings, deadline defaults), `tenancies` (household, unit, PHA, voucher size, move-in/out, current contract/tenant/HAP + source doc), `hap_contracts`, `unit_documents` (links `leases.id` ↔ unit/tenancy/PHA + doc kind). Backfill helper that groups existing lease/rent-roll rows into units by normalized address (read-only on old data). | `database` patterns, team-isolation tests, `_address_groups` | M | — | T2, T3, T11 |
| T2 | `feature/s8-hap-contract-extraction` | HAP contract and PHA notice doc kinds; new fields (Step 1e NEW); utility-responsibility and addendum-present checks; fields shown in the Section 8 lease-detail group. Measured on the fixture answer key. | `field_extractor`, `ai_extraction` (v3), `multifamily_charges`, citations, amendments | M | P1, P4 | T1, T3 |
| T3 | `feature/s8-rent-roll-check` | New `deal_mismatch` detectors: `s8_tenant_share_as_contract_rent`, `s8_contract_rent_mismatch` (roll vs lease vs HAP contract), `s8_tenant_share_mismatch` / `s8_hap_mismatch` (roll vs latest PHA notice), `s8_voucher_unit_no_hap_contract`, `s8_lease_before_hap_contract`. Dollar impact per finding. Report + PDF/XLSX relabelled "Rent Roll & HAP Check" under the flag (route paths unchanged). T12 input hidden under the flag. Fix the `t12_income_gap` ×12 bug only if T-12 stays visible anywhere (else note it). | `deal_mismatch*`, `rent_roll_import`, lease-intelligence `section_8` + `current_rent_amount` | M | P1, P3, P4 (T2 for HAP contract comparisons; ship roll-vs-lease first) | T1, T2 |
| T4 | `feature/s8-hap-payment-import` | Parse PHA payment registers / remittances (CSV, XLSX, PDF tables) into a `hap_payments` table (team, PHA, unit, tenant, period, amount, type: regular / adjustment / abatement / proration). Column aliases per common PHA export layouts. Upload block + route. | `rent_roll_import` column matching, `rent_roll_table_extract`, `document_extractor` | M | T1, P4 | T2, T3 |
| T5 | `feature/s8-hap-reconciliation` | Expected HAP per unit-month (latest PHA notice → HAP contract → roll, with source), prorated on move-in/out. Compare to `hap_payments`. Findings as `discrepancies` with dollar impact: `hap_shortfall`, `hap_overpayment`, `hap_missing`, `hap_after_move_out`, `hap_abatement`, `hap_unmatched_payment`. Per-PHA and per-month rollups. "HAP Payments" view, PDF/XLSX export. | `deal_mismatch` dollar-impact pattern, `discrepancies`, exports | L | T1, T4 (+ T2/T3 for best expected-HAP source) | T6 once T1 is in |

**Phase 2 — the compliance calendar**

| ID | Branch | What | Size | Depends on |
|---|---|---|---|---|
| T6 | `feature/s8-inspections` | `inspections` + `inspection_items` tables. PHA inspection-notice extraction plus a manual entry form. Cure-deadline + reinspection tracking with per-PHA defaults. Auto-tasks. Expected abatement start fed to T5 as `hap_abatement` context. "Inspections" view. | L | T1 (T5 for the abatement link) |
| T7 | `feature/s8-recert-tracking` (HCV) | Expected reexam month per tenancy; PHA change notice received → confirm the new tenant share and HAP landed on the roll (T3) and in payments (T5); due/overdue alerts. "Recerts & Rent Changes" view. | M | T1, T2 |
| T7b | `feature/s8-pbra-recerts` | Owner-run recert cascade (120/90/60/30), signature / 9887 / verification-age checks, built on the Oak Hollow rules and demo. Under the flag; Enterprise/PBRA only. | L | T1, T7, T0; merge or adapt `feature/s8-demo-files` |
| T8 | `feature/s8-rent-increases-renewals` | Rent increase request records (HCV) with notice-period / initial-term checks and approved-rent follow-through. HAP contract expiration / renewal / OCAF anniversary deadlines (PBRA/PBV). Optional FMR context from `hud_data`. | M | T1, T2; P5 for FMR |
| T9 | `feature/s8-unit-file-and-phas` | Unit page (tenancy, all docs with citations, findings, tasks) + PHA directory/settings UI. | M | T1 |
| T10 | `feature/s8-this-month` | "This Month" dashboard replacing the CRE dashboard under the flag: HAP expected vs received by PHA, underpaid units, abatements, inspections / recerts / increases / renewals due, with dollar totals and one-click tasks. Panels appear as their features land. Monthly report PDF. | M | T5 (first panel); T6–T8 add panels |

**Phase 3 — repositioning (frontend/copy; can start early, merges are gated)**

| ID | Branch | What | Size | Depends on / merge gate |
|---|---|---|---|---|
| T11 | `feature/s8-marketing-copy` | Step 3 copy into `index.html`, `pricing.html`, `pricing-config.js`, the meta descriptions on all 14 pages, demo form labels, and demo / waitlist email copy. **Brand files untouched.** 375px visual check required (TASKS decision log: copy length moves the shader). | M | Can be written now. **Must not merge until T3 + T5 are live on tester**, because one push to `main` makes the copy public on prod. Pricing numbers wait on Q2. |
| T12 | `feature/s8-app-reframe` | Under `SECTION8_MODE`: nav renames (Rent Roll & HAP Check, Deadlines, HAP Payments…); hide REMOVE views (Compare, investment memo, T-12, CAM/HHI/rollover panels, risk flags); Section 8 Q&A chips and `qa_engine` intents; CRE extraction fields hidden in lease detail; app meta. Help articles rewritten if `docs/tester-pack` merges. | M | T1 (flag). Merge any time; invisible with the flag off. |
| T13 | `feature/s8-sample-data` | "Load sample portfolio" and the `DEMO_MODE` seed switch to the Section 8 fixtures when `SECTION8_MODE` is on. Maple Ridge stays for tests and flag-off. | S–M | P4, T1 |

**Phase 4 — AI assistant (not planned in detail yet)**

T14 `feature/s8-assistant` builds on `feature/deal-assistant` (team-scoped citations, credit metering) over the Section 8 tables. Plan it once Phases 1–2 are live and testers tell us which questions they ask.

**Parallel windows, at a glance:**
- Right now: T0, T1, T11 (draft), plus the two in-flight branches.
- After P1/P3/P4: T2 and T3.
- After T1: T4, T9, T12, T13.
- After T4: T5.
- After T1/T2: T6, T7, T8 in parallel.
- Last: T10, then T7b, then T14.

**Collision watch:**
- T2, T3 and T12 all touch the lease-detail / report labels. T12 owns nav and labels; T2/T3 own backend fields and detectors only.
- T1 owns `database.py` schema for all new tables. Later tasks add their own tables in their own migration blocks, rebasing on T1.
- T11 and any `landing-interactive` / `docs/design-tokens` merge touch the same marketing files. Merge those first or resolve in T11's branch.

---

## Open questions for the user

1. **ICP order.** This plan launches **HCV landlords/PMs first** and puts PBRA (owner recerts, renewals) in Phase 2, because the research shows HCV paperwork is thin and the pain is payments. Agree, or lead with PBRA?
2. **Pricing.** Re-band to the proposed $199 / $599 / custom by Section 8 units, or keep $499 / $1,250 and only change copy?
3. **Cutover.**
   - Does prod flip to Section 8 copy (T11) at the same time as `SECTION8_MODE` on tester, or does tester go first for N weeks?
   - Do the existing CRE beta conversations need a heads-up?
4. **Rule defaults.** Who checks the cure-deadline / notice-period / renewal-lead-time defaults: a Section 8 practitioner you know, or the beta testers?
5. **PII bar.** Is T0 (masking + traceback scrub + AI-off switch) enough to let testers upload real voucher leases? Or do encryption at rest, MFA and team export/delete (AUDIT.md §5.2) also have to land first? Anthropic ZDR/DPA and privacy/terms pages are legal work only you can start.
6. **Merges you'd need to type:** `/merge-branch` for lease-intelligence, overnight-gauntlet and s8-hud-data, plus approving the plans for `fix/section8-tenant-share` and `qa/section8-fixtures`.
7. **`feature/loan-underwriting`:** park it indefinitely (recommended), or close it out?
