# TASKS — single source of truth

**The copy that counts is `~/dev/projects/lease-abstraction/TASKS.md`
(primary checkout, on `main`).** Never edit TASKS.md on a feature branch.
Commit changes with `git commit -m "TASKS: …" -- TASKS.md` (the hooks
allow TASKS.md-only commits on main). `/status` reconciles this file with
git; `/session-handoff` writes the handoff blocks; `/resume-task` reads them.

Last reconciled with git: **2026-10-05** (`chore/contact-email`
round 2 merged + pushed). `main` @ `9392a66` == `origin/main` before this TASKS commit.
`+a/−b` = commits ahead/behind `main`; the per-branch numbers below
predate recent merges. **Every open branch now also conflicts in
`TASKS.md`** (they each edited it before that rule existed) — resolve
those by taking **main's** TASKS.md, not the branch's.

## ⚠️ Waiting on you

1. **Type `/merge-branch <branch>` for each branch you want merged.** The
   guard ties approval to the branch the user names, and the regex only
   matches `/merge-branch …`, `approve merge`, or `merge approved` — prose
   like "merge these one at a time" does **not** arm it (`guard.py:427-440`,
   `APPROVE_RE`). A 2026-10-04 request to merge five branches in one pass
   was therefore not actionable; see #2–#4 for what each one actually needs.
2. ~~`feature/team-isolation` is ready to merge~~ — **MERGED** `3cff20b`
   (2026-10-04), pushed, all three services healthy. See Done.
3. ~~`feature/pricing-page` would ship the held Render billing change~~ —
   **RESOLVED**: `0a0d7a2` was reverted on the branch (`e06db8e`), the
   `config.js` duplication dropped, and the branch merged frontend-only
   as `c21ced5`. It never touched `render.yaml`.
4. ~~`fix/concession-detection`~~ — **fully merged**: rounds 1–2 as
   `953c00a`, rounds 3–4 as `f68a287` (2026-10-04). Both pushed. See Done.
   **It landed first, so `feature/team-isolation` now owes the `team_id`
   test update** — and note rounds 3–4 added 65 more lines to
   `test_concessions.py`, so that update is now slightly larger.
   team-isolation makes `team_id` a required arg of
   `build_deal_mismatch_report_data` and `insert_lease`; whichever branch
   lands second must update `tests/test_concessions.py` (report/insert
   calls + session `team_id`). **Done** in `d8aeed5` on the branch, plus the
   one predicted `test_demo_deal_golden.py` conflict. (An earlier note here
   called the `team_id` test update a no-op — wrong: it referred to
   document-level `team_id` on `main`, not these required args.)
5. ~~GateGuard decision~~ — **done**: tuned in `~/.claude/settings.json`
   (routine-Bash and per-file prompts off; destructive-command check kept).
6. ~~Pick one fluted-glass hero~~ — **decided 2026-10-04: `feature/pricing-page`.**
   `feature/landing-positioning` is superseded and must not be merged
   (see its row in Ready for review for why a blend was impossible).
7. ~~Render plan upgrade hold~~ — **released and merged** `92013f7`
   (2026-10-04), narrowed to `abstractly-api` only on your
   instruction. **Still yours to confirm on Render:** that the disk is
   actually attached and `DB_PATH` is set in the dashboard. A healthy
   `/health` does NOT prove the database is on the disk — it only
   proves the app can open *a* database. The real proof is the
   procedure in `docs/DEPLOYMENT.md` -> "Verifying data actually
   survives a redeploy": create a record, redeploy, confirm it lives.
   That needs login credentials, so it could not be done from here.
9. ~~Two content blockers on the pricing page~~ — **RESOLVED 2026-10-04**:
   you chose to drop the placeholder-pricing banner entirely. Removed
   markup + its dead CSS in `67afbe1`, shipped in `c21ced5`. That
   cleared all three problems at once — the false "no usage-limits
   system exists" claim, the page undercutting its own prices, and a
   customer-facing page exposing an internal TODO and the
   `pricing-config.js` path. The DoD "no placeholder text" line now passes.
11. ~~The marketing page makes a security claim that is false~~ —
   **RESOLVED by merging `feature/team-isolation` (`3cff20b`).** The
   `index.html` card "Isolated per team — Each team's documents and
   results are only visible to that team's members" is now accurate:
   document tables are team-scoped as of that merge, and 17
   cross-team isolation tests pass. **CLAUDE.md is now stale on this
   point** — its Tenancy section still says document tables are "not
   scoped" and that `feature/team-isolation` is unmerged. Worth a
   follow-up edit so the next session isn't misled.
12. ~~`chore/contact-email` already exists~~ — **MERGED `5701b8b` + round 2 `0f9de09` 2026-10-05** (was: extended and ready)
   (`0d2297d`, pushed). It already had the footer email swap and the
   `Reply-To` header; it was missing the phone-number removal, which is
   now done, plus a regression test. Merges clean. See Ready for review.
10. **`main` is 78/79 on a clean checkout, not 79/79 — correction.**
   `chore/demo-rent-roll-polish` added `test_demo_deal_regression.py`,
   (**symptom changed 2026-10-05:** since team isolation merged it fails with `401 Login required` on the first upload, reproduced on clean `origin/main` `b18bbe3`, not the FK error below), which repeats the exact fixture bug #8 described: it hardcodes
   `sess["user_id"] = 1` (`:59`) without inserting a `users` row, so every
   `/leases` upload 500s on a FOREIGN KEY in `usage_limits.log_usage_event`.
   It passes **only** where a gitignored `backend/.env` seeds a user with
   id 1 — i.e. in the primary checkout, which is where I ran it and
   reported "79/79". Verified failing on plain `main` @ `7ac879b` in a
   clean worktree. Fix is one line, mirroring what `fix/concession-detection`
   did to the golden test (`database.create_user`, use the real id) — needs
   its own branch.
8. ~~`main` is 76/77 on a clean checkout~~ — **partly fixed** by
   `fix/concession-detection` (`953c00a`), which replaced
   `test_demo_deal_golden.py`'s hardcoded `sess["user_id"] = 1` with a
   real inserted user. `main` is now **78/78 on a clean checkout**, no
   `backend/.env` needed. `chore/demo-rent-roll-polish` no longer needs
   to carry this fix — expect its version of the fixture to conflict.

## In progress

| Branch | Worktree | +/− main | State |
|---|---|---|---|
| `refactor/organize` | `~/dev/projects/lease-abstraction/.claude/worktrees/abstractly-refactor-organize-6c64dd` | 0 | Branched off `main` `01e3ba6` 2026-10-21. Structural refactor only (no behavior change): app factory + Flask blueprints, `app/shared/` vs `app/cre/` (affordable reserved for `feature/affordable-forms`), `config.py` for env vars, smoke tests, README layout section. Baseline suite **90/90**. **Plan written, awaiting user approval** — `docs/plans/refactor-organize.md` on the branch. Will conflict with every open branch that edits `api.py`. |
| `feature/lease-accuracy` | `~/dev/projects/abstractly-accuracy` | — | Branched off `origin/main` 2026-10-21. Lease accuracy eval + fixes: 30 LLM-written synthetic leases (exact keys) + 10 hand-labeled EDGAR leases, field-by-field scoring, fix biggest failure causes one at a time, every run logged in `docs/eval-accuracy.md`. Builds on `fix/ai-not-found-values`. **PAUSED 2026-10-21: no API calls without user approval + cost estimate.** Don't push/merge/deploy. |
| `fix/ai-not-found-values` | `~/dev/projects/abstractly-ai-not-found` | +1 / 0 | **Built 2026-10-20, not reviewed, not pushed** (`6b72165`). The AI's "Not found" / "None" / "N/A" text is now saved as empty, not as a value: lease fields and rent-roll validation values both go through `ai_extraction.clean_ai_value`. Prompt bumped to v3: null instead of placeholder text, and flat rent reported as "Flat -- no escalation". 2 regression tests fail before the fix, plus 1 over-matching guard. Suite **90/90**. Plan: `docs/plans/fix-ai-not-found-values.md`. Follow-ups: rows already saved with placeholder values aren't cleaned; eval-baseline AI numbers are for prompt v2. Next: `/review-branch fix/ai-not-found-values`, then merge. |
| `feature/affordable-forms` | `~/dev/projects/abstractly-research` | +27 / 0 | **Built, pushed 2026-10-21, not reviewed** (`c6a14ff`). Reading affordable-housing documents (HUD/IRS/LIHTC forms, HAP contracts, LURAs) behind `AFFORDABLE_FORMS_MODE` (off). New `backend/app/affordable/` form reader (13 form mappings), router (form reader first, AI fallback), AI field lists for HAP contracts and LURAs; eval harness `tests/eval/affordable/` (synthetic) + `tests/eval/real/` (11 public docs). **Not wired into uploads.** One change is live for every upload: the rent-roll gate no longer counts statute citations like `59-7-607` as dates (regression test). Real-doc eval after fix 3: program 13/25 verified, 59/111 proposed; lease 1/2 verified, 12/21 proposed. Synthetic: 94% lease / 92% program on clean forms, 56–58% on held-back scans. Scores: `docs/research/eval-baseline.md`. Merged `origin/main` (test isolation) and added `import _test_env` to the 7 affordable test files: suite **97/97**. Open: 132 proposed answers in `tests/eval/real/REVIEW.md` and the AI-run verdicts in `cre_benchmark_ai_review.md` await the user's check; Amasa unit mix not summed per bedroom size; LURA owner → landlord mapping; wiring needs the S8 data model (T1) and `check_team_quota`. Next: `/review-branch feature/affordable-forms`. |
| `fix/test-isolation` | `~/dev/projects/abstractly-test-isolation` | +1 / 0 | **Reviewed 2026-10-20: MERGE** (reviewer + security-auditor both MERGE, no critical/high/medium; reviewer re-ran suite 90/90 in the worktree). Not pushed (`b6303c8`). **Merge hazard:** after this lands, any branch adding a `test_*.py` fails the runner until the new file starts with `import _test_env` (affordable-forms, deal-assistant, demo-requests-view, large-files-any-type, lease-intelligence, loan-underwriting, section8-tenant-share, S8 branches). Optional nits: bytes host in `_guarded_connect`, patch `gethostbyname`, `import _test_env` in the two child scripts (test_auth_flow, test_demo_request), `test_live_assistant_api.py:104` uses the real DB path. Suite failed 9 files in the primary checkout because `app/api.py` loaded the real `backend/.env` into tests (ADMIN_EMAIL seeded into test DBs, real Gmail login sent real email, init_db() opened the real `backend/lease_portfolio.db`). New `tests/_test_env.py` imported first by every offline test: no .env, no app env vars, temp DB (real one refused), outbound network blocked. Suite **90/90** plainly and with main's .env + real shell env loaded. Real DB unmodified (mtime Oct 13); backup in `~/dev/projects/abstractly-db-backups/`. Next: user pushes the branch and merges. |
| `feature/tester-ready` | `~/dev/projects/abstractly-tester-ready` | +13 / 0 | **Reviewed 2026-10-20: MERGE** (reviewer + security-auditor both MERGE, no critical/high). Pushed. Testers on prod as teams: auth-hardening merged; invites by email behind `TEAM_INVITES_ENABLED`; removal ends sessions; monthly page limit (default 1,000) before any AI; two-team isolation test; headless click-through 16/16 (desktop + iPhone). Suite **89/89** at `e733412`. Report: `docs/plans/tester-ready-REPORT.md` on the branch. **Owns usage limits.** Non-blocking follow-ups in the handoff block. Steps 7 and 9 undefined; waiting on user. |
| `feature/s8-inspections` | `~/dev/projects/abstractly-s8-inspections` | — | **T6 of the Section 8 pivot.** Stacked on `feature/s8-data-model` (T1, unmerged) + `main`, 2026-10-13. Team-scoped `inspections` + `inspection_items`, manual entry + PHA inspection-report import, cure-deadline / reinspection tracking with per-PHA rule defaults, expected-abatement context for T5. Behind `SECTION8_MODE`. **Merge only after T1.** **Plan written, awaiting user approval** — `docs/plans/feature-s8-inspections.md`. |
| `feature/s8-hap-payment-import` | `~/dev/projects/abstractly-s8-hap-payments` | — | **T4 of the Section 8 pivot.** Stacked on `feature/s8-data-model` (T1, unmerged) + `main`, 2026-10-13. Parse PHA HAP payment registers (CSV/XLSX/PDF) into a team-scoped `hap_payments` table behind `SECTION8_MODE`. **Merge only after T1.** **Plan written, awaiting user approval** — `docs/plans/feature-s8-hap-payment-import.md`. |
| `feature/s8-pii-guard` | `~/dev/projects/abstractly-s8-pii-guard` | — | **T0 of the Section 8 pivot.** Branched off `main` 2026-10-13. Mask/drop SSN, DOB and bank numbers before storage (extraction quotes, date candidates, free-text notes) and before Anthropic; scrub tracebacks from alert emails; per-team "AI processing off" switch (Q5 decision). Must merge before testers upload real tenant docs. **Plan written, awaiting user approval** — `docs/plans/feature-s8-pii-guard.md`. |
| `feature/s8-unit-file-and-phas` | `~/dev/projects/abstractly-s8-unit-file` | +5 / −0 | **Built, pushed `d893c56`; reviewer FIX FIRST on a T1 bug (see handoff).** T9 of the Section 8 pivot, stacked on `feature/s8-data-model` `b6caf9a` (T1, unmerged). Section 8 nav group (above Overview; hidden unless `GET /config` → `section8_mode: true`) with Units list (grouped by property, household/PHA/program/contract/tenant/HAP), unit file (current tenancy edit + record new w/ `end_current`, HAP contracts, documents link/kind/unlink → lease detail, past tenancies), Housing Authorities directory (add/edit/archive, show archived), admin “Group uploads into units” backfill with dry-run preview. Only backend change: `/config` boolean. Suite **84/84** on `d893c56`. security-auditor **MERGE**. Headless click-through + screenshots 1440/768/375 looked at (flag on/off, viewer read-only, no horizontal overflow). **Cannot merge before T1.** |
| `fix/quick-wins` | `~/dev/projects/abstractly-quick-wins` | — | Branched off `main` 2026-10-06. (1) lease detail cards cut off on the right at 375px + sweep every page at 375px; (2) upgrade Pillow and every dependency with a known security advisory, full suite green. **Plan approved, building** — `docs/plans/fix-quick-wins.md`. |
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | +2 / −16 | ~19 uncommitted files (`api.py`, `database.py`, tests, plan); not pushed. Feature-flagged off. Merge **after** team isolation (its plan defers all tenancy to it). Another session may be active — don't touch. |
| `feature/deal-assistant` | `~/dev/projects/abstractly-assistant` | 0 / −7 | Worktree only, nothing built. Not started. |
| `feature/affordable-real-accuracy` | `~/dev/projects/abstractly-affordable-real` | — | Claimed 2026-10-21. **Stacked on `feature/affordable-forms` `c6a14ff`** (merge only after it). Raise the 11-real-document affordable eval from 85/159 (53%) toward 90%: free fixes first (eval response cache keyed by request hash, OCR/value cleanup, 50059 mapping, arithmetic cross-checks that flag but never alter, Amasa bedroom sums, OCR-gated docs unblocked inside the affordable router, PBV Exhibit A table reader), then one paid AI run (~$0.75–0.90) only after a cost estimate + user OK. User has ~$14 API credit total. Behind `AFFORDABLE_FORMS_MODE`. Plan: `docs/plans/feature-affordable-real-accuracy.md`. |
| `fix/upload-hardening` | `~/dev/projects/abstractly-upload-hardening` | — | Claimed 2026-10-21. **Stacked on `feature/large-files-any-type` `085debe`** (merge only after it). Security re-audit follow-ups, one commit each, suite after each: (1) no route accepts the .xlsx entity bomb (`POST /leases`, `/leases/import-rent-roll`), regression test per route; (2) time limit on PDF reading; (3) 3-active-jobs cap holds under simultaneous uploads; (4) rate limit on `POST /uploads`. User's prompt is the spec and approval; don't merge. |

| `qa/overnight-gauntlet` | `~/dev/projects/abstractly-gauntlet` | — | **Reviewed: MERGE (reviewer + security-auditor).** Branched off `main` `3f1d3aa` 2026-10-05. Overnight reliability gauntlet: 60+ synthetic messy rent rolls, 30+ T-12s, matching leases with planted mismatches + manifest; full local pipeline graded each cycle; root-cause fixes with regression tests; `QA_REPORT.md` updated per cycle. User's prompt is the approved scope (autonomous, no questions). Never merges/deploys. |
| `audit/production-readiness` | `~/dev/projects/abstractly-audit` | 0 | Started 2026-10-05 off `origin/main` `3f1d3aa`. **Read-only** production readiness audit (DB, security, reliability, cost, Section 8 trust) → `AUDIT.md` at the worktree root, **uncommitted by user instruction** (no code edits, commits, pushes, or Render changes). Overnight deep pass: every route + job traced, bugs added ranked by severity. |
| `pivot/section8` | `~/dev/projects/abstractly-pivot-section8` | — | Branched off `main` `323d85f` 2026-10-11. **Plan only, no code:** `PIVOT_PLAN.md` — audit (KEEP/ADAPT/REMOVE), Section 8 feature set, copy/positioning, parallel build order for pivoting Abstractly to Section 8 landlords/PMs. **Plan approved 2026-10-11** (`623e884`); tasks T0–T13 queued in Up next → "Section 8 pivot". Open questions Q1–Q7 still unanswered — plan defaults assumed. Builds on `research/section8`, `feature/lease-intelligence`, `feature/s8-hud-data`, `feature/s8-demo-files`. |
| `chore/repo-layout` | `~/dev/projects/abstractly-repo-layout` | — | Branched off `main` `1d203d2` 2026-10-05. Repo tidy-up: move stray root reports/plans into `docs/`, fill `.gitignore` gaps, README project-layout section. File moves + doc-comment path fixes only, no code behavior change. **Plan approved 2026-10-21** (`3fb8583`, not pushed) — `docs/plans/chore-repo-layout.md`; now also covers `feature/large-files-any-type` and `feature/affordable-forms` files. Moves not started: wait for both to land on main. |


### Handoff blocks

### fix/upload-hardening
- Worktree: ~/dev/projects/abstractly-upload-hardening
- Base: stacked on feature/large-files-any-type 085debe (unmerged); merge only after it
- Goal: close the security auditor's open upload items (entity bomb on existing routes, PDF read time limit, atomic job cap, POST /uploads rate limit)
- Loop step: 4 — building (user's 2026-10-21 prompt is the spec and approval)
- Last update: 2026-10-21 by the large-files session
- Next action: fix 1 (entity bomb on existing routes)

### feature/affordable-real-accuracy
- Worktree: ~/dev/projects/abstractly-affordable-real
- Base: stacked on feature/affordable-forms c6a14ff (unmerged); merge only after it
- Goal: 11 real affordable documents from 85/159 (53%) toward 90%, free fixes first, cached AI responses, every API call estimated and approved first.
- Loop step: 4 — building free steps (user's 2026-10-21 reply asked for the fix-3 flag + regression test + REVIEW note; taken as go-ahead for the no-cost steps 0–5 only; no API calls without estimate + OK)
- Last update: 2026-10-21 by build session
- Spent: $0.00 this task. Budget: ~$14 total left; projected ~$1.00–1.20
- Done (pushed 2026-10-21, tip after `9212f7e`): steps 0–5, all free. 4 form-reader docs 22 → 53/62; combined est. ~116/159 (73%) mixing runs. Suite 102/102; synthetic unchanged. Scores in docs/research/eval-baseline.md (last section).
- Next action: user approves the combined paid run (10 calls, estimate ~$0.72), then score, then optional follow-ups (811 lease list, street_address key question)

### feature/lease-accuracy
- Worktree: ~/dev/projects/abstractly-accuracy
- Goal: raise lease extraction accuracy toward ~90% on realistic leases; step 1 = 30-lease LLM-written synthetic corpus with exact answer keys + grader.
- Loop step: 4 — building, PAUSED 2026-10-21 ~15:13 by user: stop all API spending; no API calls without user approval + cost estimate.
- Last update: 2026-10-21 by build session
- Spent: $4.64 logged ($0.87 pilot + $3.77 main run); main run was killed before its log write, so up to ~$3–4 more may be billed for calls in flight / completed after the last print. Check the Console for the exact figure.
- Done: tooling committed `cf1e75e` (grader, generator, verifier, renderer, 8 tests). Synthetic: 7/30 leases verified with keys (s01–s06, s09), 5 more have ground truth only (s07, s08, s10–s12). EDGAR10: none downloaded yet (agent stopped after picking 10 candidates; UA with user's Gmail approved).
- Found: the rent-roll gate (`field_extractor.looks_like_rent_roll_table`) refuses 5/12 existing EDGAR leases + 1 synthetic lease at upload; fix (density per 1,000 words) designed, not applied.
- Next action: user decides what to approve next (finish generation / AI baseline / EDGAR set), with cost estimates.
- Follow-up (not building now, user asked 2026-10-21): if a rent roll gets past `looks_like_rent_roll_table`, it is saved and shown as a normal lease with confidently wrong values. There's no error and no message; `_looks_like_lease` (`api.py:896`) only checks that an identity field has a value. The user wants a clear message instead (e.g. a second check after extraction, or a "this may be a rent roll" warning on the lease). Needs its own task + plan.

#### feature/tester-ready
- Worktree: ~/dev/projects/abstractly-tester-ready (venv symlinked to the primary checkout's)
- Goal: testers sign in to prod as teams, invite teammates by email, share one team's data, and stay inside a monthly page limit.
- Loop step: 6 done; report written. Commits: 8125f04 (step 1), 10c3ef1 (2), 92ae950 (3), 495717e (team-setup fix), 8f6c45e (4), fb11c30 (5), 28d8e2d (6), e733412 (report). Suite 89/89 (re-run by reviewer). Pushed 2026-10-20. /review-branch verdict: MERGE. Then 14f1084 (review follow-ups 1, 5, 7), suite 89/89, not pushed.
- Last update: 2026-10-20 by the tester-ready session (/review-branch)
- Read first: `docs/plans/tester-ready-REPORT.md` on the branch: 12 decisions for the user, deal-assistant review (FINISH FIRST), Python 3.9 local vs 3.11 Render, Render env vars (`TEAM_INVITES_ENABLED=true` on abstractly-api).
- Blocked: steps 7 and 9 were requested but aren't defined anywhere; step 8 skipped by the user (Google/Microsoft credentials).
- Follow-up, not this branch: 2 GB chunked resumable direct-to-R2 uploads (local fallback, R2 setup doc) as a new branch stacked on `feature/large-files-any-type`. Correction: `api._claim_monthly_pages` is request-bound (uses `current_user()`), so background jobs can't call it; add `usage_limits.claim_pages(team_id, user_id, pages)` on tester-ready's side first. Until then large-files' worker uploads skip and don't count against the page limit. Suggested per-file limits (documented only): `MAX_PAGES_PER_FILE` 1000, `MAX_FILE_SIZE_MB` 2048, job timeout 3600.
- Review follow-ups (non-blocking): (1) DONE in 14f1084: batch runs `_precheck_upload_file` per file; (2) .txt/.docx/.csv count as 1 page regardless of length, so the limit doesn't cap AI spend for them; (3) `count_pdf_pages` parses twice per upload, before the rate limit (~1.8 s per 2.5 MB crafted PDF); (4) expired pending invites never expire and reserve the email; (5) DONE in 14f1084; (6) POST /teams quota and PATCH `monthly_document_quota` unvalidated; (7) DONE in 14f1084 (37 more record routes, 15 body-id requests, per-table before/after compare).
- Next action: user decides on decisions + follow-ups, sends steps 7/9; `/merge-branch feature/tester-ready` when ready.

#### feature/s8-inspections
- Worktree: ~/dev/projects/abstractly-s8-inspections
- Goal: track every unit's inspections, deficiencies, cure deadlines and reinspections (per-PHA rules), and expose expected HAP abatement for T5, behind SECTION8_MODE.
- Loop step: 3 — plan written, waiting for user approval
- Last update: 2026-10-13 by start-task
- Next action: user reviews docs/plans/feature-s8-inspections.md (base = T1; merge after T1)

#### feature/s8-hap-payment-import
- Worktree: ~/dev/projects/abstractly-s8-hap-payments
- Goal: upload a PHA's HAP payment register and get one hap_payments row per unit-month payment/adjustment, matched to the team's units/tenancies, behind SECTION8_MODE.
- Loop step: 3 — plan written, waiting for user approval
- Last update: 2026-10-13 by start-task
- Next action: user reviews docs/plans/feature-s8-hap-payment-import.md (base = T1; merge after T1)

#### feature/s8-pii-guard
- Worktree: ~/dev/projects/abstractly-s8-pii-guard
- Goal: SSNs, dates of birth and bank numbers never stored and never sent to Anthropic; alert emails carry no tracebacks; a team can turn AI processing off.
- Loop step: 3 — plan written, waiting for user approval
- Last update: 2026-10-13 by start-task
- Next action: user reviews docs/plans/feature-s8-pii-guard.md (answer its open questions)

#### feature/s8-sample-data
- Worktree: ~/dev/projects/abstractly-s8-sample
- Goal: with SECTION8_MODE on, "Load sample deal", /leases/sample and the DEMO_MODE seed load the Section 8 sample portfolio built from qa/section8-fixtures; flag off unchanged.
- Loop step: 10 — READY, waiting for the user's morning review (user: T9 and T13 are NOT merged from worker windows)
- Last update: 2026-10-13 by the s8-sample session — tip 14df5fb pushed (main merged in, capture re-run after gauntlet merge), suite 87/87, reviewer MERGE (re-checked), security-auditor MERGE, UI check PASS
- Next action: user reviews; merge order T1 (feature/s8-data-model) first, then this. After P1 (lease-intelligence) merges, re-run backend/benchmark_data/section8_sample/capture_section8_sample.py.

#### fix/section8-tenant-share
- Worktree: ~/dev/projects/abstractly-s8-tenant-share
- Goal: rent roll import never treats a Section 8 tenant share as the unit's rent; validates contract rent = tenant share + HAP per row and flags mismatches clearly.
- Loop step: 10 — waiting for user to approve merge (after qa/overnight-gauntlet)
- Last update: 2026-10-11 by ship-branch
- Next action: user types `/merge-branch qa/overnight-gauntlet`, then `/merge-branch fix/section8-tenant-share`

#### feature/s8-unit-file-and-phas
- Worktree: ~/dev/projects/abstractly-s8-unit-file
- Goal: Section 8 operators can see every unit with its current tenancy, open a per-unit file (tenancy, HAP contracts, linked documents), and manage their housing authorities — behind SECTION8_MODE.
- Base: stacked on feature/s8-data-model (b6caf9a); rebase onto main once T1 merges
- Loop step: 9 — built + pushed (`d893c56`), suite 84/84, security-auditor MERGE; reviewer FIX FIRST item belongs to T1
- Last update: 2026-10-13 by the T9 build session. User approved plan; wording "Group uploads into units"; nav group placed ABOVE existing groups (my recommendation, user accepted)
- Blocker (T1 bug, found by reviewer): unlink = PATCH archived:true, but `unit_documents` UNIQUE(team_id, lease_id, unit_id) counts archived rows, so re-linking an unlinked upload 409s with no UI way out. Fix belongs on `feature/s8-data-model` (POST /section8/units/<id>/documents should un-archive the existing row) + regression test (link → unlink → re-link = 201). Not done: T1's worktree belongs to another session and the plan says T1 bugs are fixed on T1. Waiting on user decision.
- Not verified: real tester deployment with the flag on; contextual toolbar on S8 views falls back to dashboard quick actions (app.js out of plan scope); s8unit view highlights no nav item.
- Screenshots: scratchpad of session 3b7e8ed2 (s8/shots4, shots5, shots6) — temporary
- Next action: user decides on the T1 unlink/re-link fix; then re-review, then `/merge-branch feature/s8-data-model` before this branch

#### feature/s8-data-model
- Worktree: ~/dev/projects/abstractly-s8-data-model
- Goal: the Section 8 data foundation (properties, units, PHAs, tenancies, HAP contracts, unit documents), team-scoped, behind SECTION8_MODE.
- Loop step: 10 — waiting for user to approve merge (`/merge-branch feature/s8-data-model`)
- Last update: 2026-10-11 by the s8-data-model session — tip `b6caf9a` pushed, suite 84/84, security-auditor MERGE, reviewer FIX FIRST items done
- Next action: user types `/merge-branch feature/s8-data-model` in the merger session; then T4/T9/T12/T13 can start

#### pivot/section8
- Worktree: ~/dev/projects/abstractly-pivot-section8
- Goal: a reviewed pivot plan (PIVOT_PLAN.md) turning Abstractly into a Section 8 landlord / PM tool, split into claimable tasks.
- Loop step: plan approved 2026-10-11 by the user ("yes continue"); tasks queued in Up next. Branch holds only PIVOT_PLAN.md — nothing to merge until the user wants the plan on main.
- Last update: 2026-10-11 by the pivot planning session
- Q4 + Q5 answered 2026-10-12 (see Up next → Section 8 pivot → User decisions). Still assumed until the user answers Q1–Q3, Q6, Q7: HCV first, PBRA phase 2; pricing unchanged until Q2; T11 copy does not merge before T3+T5 are live on tester; T0 required before real tenant docs.
- Next action: other windows claim tasks from Up next → "Section 8 pivot" with /start-task (read PIVOT_PLAN.md on branch pivot/section8 first)

#### fix/quick-wins
- Worktree: `~/dev/projects/abstractly-quick-wins`
- Goal: fix lease detail cards cut off at 375px (and any page with the same issue); upgrade every dependency with a known security advisory; suite green.
- Loop step: 4 — building (plan approved 2026-10-06; branch tests in its own Python 3.11 venv, shared venv untouched)
- Last update: 2026-10-06 by the quick-wins session
- Next action: build per plan

#### feature/auth-hardening
- Worktree: `~/dev/projects/abstractly-auth-hardening`
- Goal: keep hardening the merged auth flows (double clicks, back button, expired/reused links, two tabs, mobile Safari, slow email, signing up twice, login during reset); fix with failing-first tests; push each round; never merge.
- Loop step: rounds 4–6 pushed (`55cf729`, `f2cbf0e`, `5537aad`). **reviewer (rounds 4–5): MERGE**, its follow-ups done in round 6. Suite 83/83; `test_auth_flow.py` 49 tests; headless E2E now in the repo (`.claude/tools/auth-e2e/`): flows 41/41, round2 6/6, round4 16/16, round5 7/7, round6 7/7 (Chromium + WebKit).
- Last update: 2026-10-05 by the auth-flow session (plan approved: `docs/plans/feature-auth-hardening.md`)
- Log: `AUTH_NOTES.md` on the branch (summary at top)
- **Needs you:** Manual Deploy of `abstractly-tester-api` and `abstractly-demo-api` in Render (they didn't redeploy after the auth-flow merge; reset on tester is broken until then); `EMAIL_USER`/`EMAIL_APP_PASSWORD` on tester-api
- Next action: user reviews; `/merge-branch feature/auth-hardening` when ready; never merged by this session

#### qa/overnight-gauntlet
- Worktree: ~/dev/projects/abstractly-gauntlet
- Loop step: 11 — MERGED LOCALLY, NOT PUSHED. Merge commit `b63927d` on local `main` (user approved 2026-10-13: "approve merge qa/overnight-gauntlet"). Only conflict: `run_all_tests.py` list (kept both entries).
- Suite on merged main: **85/85** in a clean detached worktree (no `backend/.env`). In the primary checkout it gave 77/85 (known non-hermetic env, see Decisions log). (Earlier note said a real email was sent — WRONG: the "Email sent … via smtp.gmail.com" log line comes from test_demo_request.py's mocked SMTP; nothing left the machine.)
- `git push origin main` was DENIED by the Claude Code auto-mode permission classifier — not retried. Merge lock still held by session 10959d5d so no other session pushes this merge by accident.
- Next action: USER pushes main (or allows the push), then smoke-test tester, move row to Done, remove worktree, release lock.

#### chore/repo-layout
- Worktree: `~/dev/projects/abstractly-repo-layout`
- Goal: a clean, self-explanatory repo layout (root = README, CLAUDE, TASKS, render.yaml; docs grouped by purpose) with nothing broken.
- Loop step: 3 done — plan approved 2026-10-21 (`3fb8583`, not pushed). Plan now also covers files added by `feature/large-files-any-type` and `feature/affordable-forms` (rows tagged LF/AF).
- Last update: 2026-10-21
- Next action: wait for large-files and affordable-forms to land on main, sync this branch with main, then start the moves. Open questions 1-4 in the plan are still unanswered (README positioning, depth, public repo, fold in main's newer root files).

#### feature/lease-intelligence
- Worktree: `~/dev/projects/abstractly-lease-intel`
- Goal: make lease extraction as accurate and complete as possible for multifamily and Section 8 leases, measured against synthetic graded corpora.
- Loop step: 10 — waiting for user to approve merge (`/merge-branch feature/lease-intelligence`)
- Last update: 2026-10-05 by the lease-intelligence session — tip `568c53d` pushed, suite 90/90, reviewer MERGE
- Screenshots: session scratchpad `ui/png/` and `ui-checker/` (1440/768/375, flag on + off)
- Next action: user decides on merge; optional: turn on `LEASE_MULTIFAMILY_FIELDS` for the tester deployment; run the corpora on the AI engine once a key is funded. Report: `docs/LEASE_EXTRACTION_REPORT.md`.

<!-- One block per In-progress task, written by /start-task and
     /session-handoff, read by /resume-task. Keep them current. -->

## Ready for review (pushed, not merged)

| Branch | Worktree | +/− main | Notes |
|---|---|---|---|
| `feature/large-files-any-type` | `~/dev/projects/abstractly-large-files` | +9 / 0 | **Ready to merge: pushed 2026-10-21 at `085debe`, verdict MERGE** (security-auditor re-audit of `085debe` PASS: PoC + 15 variants rejected (UTF-16 LE/BE, BOMs, DOCTYPE after 3 MB comment/PI, external DTD, parameter entity, image-named part, lxml-fails fallback), check itself cheap and expands nothing, 0 false positives on 71 real Office files; reviewer MERGE). Waiting on user `/merge-branch`. The "(local, NOT pushed)" and "Next:" notes below are superseded. **Re-reviewed 2026-10-21 at `a8bd0bc`: FIX FIRST** (security-auditor HIGH, reviewer agreed and reproduced: ~1 KB .xlsx with nested `<!ENTITY>` "billion laughs" passed every cap, openpyxl expanded it to a 300M-char cell / ~2.5 GB). **Fixed in `085debe` (local, NOT pushed):** `file_types._declares_dtd` refuses any Office XML part declaring a DOCTYPE; regression test failed before the fix; 74 real .xlsx/.docx fixtures still pass; suite **95/95**. Reviewer checked `085debe`: MERGE once pushed (auditor has not re-checked it). Cross-team isolation, roles, secrets clean. Follow-ups 4, 6, 7 closed. **Still open (non-blocking):** 2 (`convert_from_path` no timeout), 3 (no rate limit on `POST /uploads` kind=rent_roll; body spooled before checks), 5 (job cap check-then-insert), 1 and 8 unconfirmed; ~320 MB team-wide reload after a 5,000-row rent-roll import; existing `POST /leases` + `/leases/import-rent-roll` still parse entity-bomb xlsx (pre-existing; options: `defusedxml` in requirements, or same check there; user to decide). Next: push `085debe`, then `/merge-branch`. **Pushed 2026-10-21 at `a8bd0bc`** (origin == local; not merged). Adds main-merge `b17b45d` + 3 post-review commits (`94177e6` `_test_env` imports, `716986d` follow-ups 6/7, `a8bd0bc` follow-up 4); suite **95/95**. **Reviewed 2026-10-20 at `bcb7b0e`: MERGE** (reviewer MERGE + security-auditor MERGE, no critical/high). Large leases/rent rolls of any type: content-based type detection, per-page OCR (multi-page TIFF/HEIC), chunked AI extraction with page citations, background upload jobs + progress UI behind `LARGE_FILE_UPLOADS` (default off). Suite **90/90** (reviewer re-ran, no --live). Routes `@require_role`, job lookups `team_id`-scoped, cross-team poll → 404. Report: `docs/plans/large-files-REPORT.md`. **Merge notes:** real conflict in `backend/app/ai_extraction.py` with `feature/lease-intelligence` (second to merge resolves by hand); trivial `run_all_tests.py` with `fix/rent-roll-hardening`. **Before turning the flag on:** `GUNICORN_TIMEOUT=300`; background jobs don't count against the monthly page limit until tester-ready adds `usage_limits.claim_pages`. **Non-blocking follow-ups:** (1) screenshot paths for the UI check not recorded (re-run `screenshots.mjs`); (2) M: no timeout on PDF rasterize/text step (`pdf_extractor.py` `convert_from_path`), one crafted PDF can hold the single worker up to 3h; (3) M: no per-user rate limit on `POST /uploads` and body is spooled before the job cap/disk checks; (4) L: 250 MB zip uncompressed cap allows memory spikes on 512 MB; (5) L: active-job cap is check-then-insert; (6) L: `AIExtractionError` text shown to client unmapped; (7) L: error telemetry row has no team; (8) bulk-delete/tag regression test not confirmed failing-before-fix. |
| `feature/s8-sample-data` | `~/dev/projects/abstractly-s8-sample` | +16 / 0 vs main (includes T1's 6) | **READY — user reviews in the morning; do not merge from a worker window.** Tip `14df5fb` (`main` incl. the gauntlet merge `b63927d` merged in; capture re-run on the new importer). **T13.** Stacked on `feature/s8-data-model` (T1): **merge only after T1.** With `SECTION8_MODE` on: "Load Sample Deal" loads the fictional Juniper Row + Bellmont Terrace portfolio (65 documents tagged Sample + 1 PHA, 2 properties, 32 units, 30 tenancies, 13 HAP contract rows, 73 doc links) into the caller's team, all-or-nothing, 409 on a second/concurrent load; `/leases/sample` returns the Juniper Row 214 voucher lease; DEMO_MODE seed uses it and demo reset wipes Section 8 tables. Flag off: unchanged (Maple Ridge). Planted fixture errors survive into the records (checked against answer_key.json). Tests: `test_section8_sample_data.py` 12/12 (3 regression tests verified failing first), new isolation case; suite **87/87** in the worktree. Headless UI check PASS (toast flag on/off + 409 at 1440/768/375; scratchpad `shots-s8-sample-after/`, looked at). **reviewer: FIX FIRST → fixed → MERGE (re-checked at `14df5fb` incl. the `database.py` merge resolution); security-auditor: MERGE.** **Caveat:** captured documents reflect `main`'s regex extraction (Section 8 leases split into 3, tenant read as "Gas") — P2 recapture done; re-run `capture_section8_sample.py` after P1 lease-intelligence merges. |
| `fix/section8-tenant-share` | `~/dev/projects/abstractly-s8-tenant-share` | 4 own commits on top of `qa/overnight-gauntlet` `906eaab` (+79 / −38 vs main incl. gauntlet) | **Ready. Merge AFTER `qa/overnight-gauntlet`** (built on its `a1cff89`, user-approved base). Pushed `5fa9e5f`. Rent roll import: contract rent = tenant share + HAP, checked per row with $1 tolerance; mismatch → rent column kept, confidence low, flagged with $ gap; explicit tenant-share column with no HAP never used as rent; bare "Tenant Rent" = rent on market rolls, but blank + flagged ambiguous when any header or that unit's row shows a voucher sign (unit/address/name columns ignored); "-"/N/A HAP = $0; "Subsidy Type" no longer read as HAP dollars; honest citations for derived rents; OCR warnings merged not overwritten. Flags go to the existing upload warnings box (grouped, first 10 units) + `section8_checks` in the parse result (not passed through the API yet). Only `rent_roll_import.py` + tests; no routes/UI. Suite **84/84** (no API key). New `test_section8_rent_roll.py` 23 tests (16 failed before the fix; 2 review regressions failed before their fix). 123 repo rent-roll fixtures re-parsed: **0 rent changes**, only 2 S8 fixtures' citations changed. **reviewer: MERGE** (after FIX FIRST: dash/N/A HAP and unit-id/address false positives — fixed with tests). **Not verified:** real PMS Section 8 exports; the warnings box rendering (no UI change, not screenshotted). |
| `feature/s8-data-model` | `~/dev/projects/abstractly-s8-data-model` | +6 / −5 | **Ready.** Pushed `b6caf9a`. T1 of the Section 8 pivot: team-scoped tables phas/properties/units/tenancies/hap_contracts/unit_documents (additive only, money in integer cents, no deletes — archive via PATCH), 18 `/section8/*` routes (viewer read / analyst write / admin backfill), address backfill (dry run by default, idempotent, never edits leases; backfilled units always `unknown` per user), all behind `SECTION8_MODE` (default off → every route 404s, even logged out). No UI, no `render.yaml`/env changes. Tests: `test_section8_data_model.py` 18 + 3 cases in `test_team_isolation.py` (mutation-checked: disabling the same-team guard makes them fail). Suite **84/84** in a clean worktree on the pushed tip. **security-auditor: MERGE** (3 low items fixed in `b6caf9a` with failing-first tests); **reviewer: FIX FIRST → done** (push `b6caf9a` + re-run suite; no code issues). Overlap: `fix/section8-tenant-share` rewrites `portfolio.py` but keeps all 5 names this branch imports (checked); both it and `feature/s8-hud-data` add lines to `run_all_tests.py` (trivial conflict). Whichever merges second re-runs the suite. **Not verified:** a real tester deployment with the flag on. |
| `feature/lease-intelligence` | `~/dev/projects/abstractly-lease-intel` | +16 / −22 | **Ready.** Tip `568c53d`. Lease extraction accuracy for multifamily + Section 8 (regex engine; AI prompt v3 mocked only). Measured on synthetic, fictional corpora: own 51.1% → 100%, held-out #1 55.6% → 99.6%, **blind #2 87.6% before tuning** → 95.8%, 0 high-confidence wrong values on all three; SEC commercial benchmark 36.7% → 40.0% (no lease/field regressed); Maple Ridge fields identical to main. Fixes: Section 8 lease + HUD addendum/HAP contract/renewals no longer split into 2–3 leases; co-residents; apartment wording; contract rent (not tenant portion/pet/parking/renewal rent); addresses keep the unit; per-page OCR of scanned attachments (≤10 pages / 60s). New fields behind `LEASE_MULTIFAMILY_FIELDS` (off): unit, pet/parking/utility (RUBS + flat fees), Section 8 split, in-file renewals/amendments/PHA notices, current rent/end; read-only lease-detail group. Suite **90/90**; **91/91 on a trial merge with current `main`** (incl. merged `feature/auth-flow`), merges clean. Headless screenshots 1440/768/375 flag on + off, looked at: session scratchpad `ui/png/` and `ui-checker/` (ui-checker PASS). **reviewer: MERGE** (after FIX FIRST: quadratic regex on long tokens 132s→0.4s, OCR time budget — both fixed with tests). Overlap: `qa/overnight-gauntlet` only in `run_all_tests.py` (list merge). Report + hand-offs for the gauntlet (report should use current rent / Section 8 split; Apt-vs-Suite address matching; concession phrasings): `docs/LEASE_EXTRACTION_REPORT.md`. **Not verified:** AI engine accuracy (no funded key — run the 3 corpora with `LEASE_EXTRACTION_ENGINE=ai` before enabling AI); real customer leases. |
| `feature/demo-requests-view` | `~/dev/projects/abstractly-demo-requests` | +2 | **Ready.** Pushed `bb9c634`, off `origin/main` `b18bbe3`. Owner console **Demo Requests** tab (date, name, email, company, units, message; newest first) + **Export CSV**, on the `demo_requests` table that already existed on main. Routes `GET /owner/demo-requests` and `/owner/demo-requests/export.csv` are **`@require_owner()`, not `role=admin`**: the user said "admin-only", but these are Abstractly's own sales leads, and a customer firm's admin must not see them (same as `GET /waitlist`). CSV cells are formula-injection guarded. Optional forwarding of each new request to a Google Sheet via an Apps Script web app (`DEMO_REQUEST_SHEET_WEBHOOK_URL` + `DEMO_REQUEST_SHEET_SECRET`, both unset = off). Apps-Script-only URL allow-list, no redirects, background thread capped at 4 in flight, never blocks the public form. Setup guide `docs/DEMO_REQUESTS_SHEET.md`. Owner tab strip now scrolls sideways on phones (a sixth tab overflowed 375px). Tests: `test_demo_requests_view.py` 15/15, all network mocked; the owner-route list in `test_owner_console.py` is extended. Suite **81/82** in a clean worktree (only `test_demo_deal_regression.py`, pre-existing). Headless screenshots at 1440/768/375 against a mocked API, looked at. **reviewer: MERGE; security-auditor: MERGE** (no critical/high/medium findings). The concurrency cap was the auditor's low-severity suggestion, applied afterwards with a regression test. **Not verified:** a real Apps Script round-trip (needs your sheet); the console against a real backend session. **To turn on:** set the two env vars on `abstractly-api` in the Render dashboard. |
| `feature/landing-interactive` | `~/dev/projects/abstractly-landing-interactive` | +2 | Pushed (`5c17f8a`). Landing page: (1) hero scan animation over 10 rows of the **fictional** Maple Ridge sample rent roll, labeled "Sample deal", gold mono ticker counts to the same $42,780 as before, replays on re-entry; (2) text-only marquee of import sources (**Entrata dropped** — nothing claims/tests it; uses the FAQ's AppFolio/Yardi/RealPage/MRI/Buildium/Excel/CSV); (3) exposure calculator, units × rent × 12 × a stated 0.5–2% assumption, Book a call → `#book-demo`. Reduced motion = finished state, static marquee. Headless screenshots 1440/768/375 + mid-scan, reduced-motion, 2560 marquee all inspected. Suite **81/82** (only known #10). Reviewer **MERGE**; minor notes fixed. Overlap: `feature/calendly-booking` will need to update one more `#book-demo` href. Open framing question for user: 6 of 10 visible rows are flagged. |
| `feature/s8-demo-files` | `~/dev/projects/abstractly-s8-demo` | +2 | Pushed (`1faa1ea`). Fictional 40-unit PBRA property **Oak Hollow Apartments**: 10 tenant-file PDFs (fake data, SSNs `000-00-0001`–`0021`), 40-unit rent roll, `expected_findings.json`, README listing **10 planted errors** (E1–E10) with rule, citation, page, and dollar impact ($1,451 confirmed / $17,981 potential as of fixed review date 10/01/2026). Unit 102 is a clean control. Data-only, all files in `backend/benchmark_data/s8_demo/`; generator `generate_s8_demo.py` is the source of truth. Suite **80/81** (only `test_demo_deal_regression.py`, known #10). Reviewer **MERGE**; its low-severity notes fixed. Not wired into the app. Rule citations paraphrased, **not practitioner-checked**. User said don't merge. |
| `feature/s8-hud-data` | `~/dev/projects/abstractly-s8-data` | +3 | **Ready.** Pushed `130e784`, off `origin/main` `b18bbe3`. New self-contained `backend/app/section8/hud_data/`: HUD Section 8 income limits, Fair Market Rents and MTSP (LIHTC) limits from HUD's bulk CSV/XLSX files, in its **own** SQLite file (`HUD_DATA_DB_PATH`, else `hud_data.db` beside `DB_PATH`), versioned by effective year (a reload replaces one year atomically; append-only load log with sha256). Lookups by year / as-of date / latest; derived LIHTC income limits (20–80% AIT) and §42 gross rent caps; CLI `python -m app.section8.hud_data refresh|status` (`--url` only https huduser.gov, no redirects, 50 MB cap). Behind `SECTION8_HUD_DATA_ENABLED` (off); no routes, nothing in the app imports it. Only outside edit: one line in `run_all_tests.py`. Tests: `test_section8_hud_data.py` 16 functions, small illustrative fixtures, no network. Suite **81/82** in a clean worktree (only `test_demo_deal_regression.py`, reproduced on clean `origin/main`). **reviewer: MERGE**; its follow-ups 1–4 applied anyway in `130e784` (filename year check, zero/inf/nan + monotonic checks, flag wording), with regression tests verified failing first; not re-reviewed (small, test-covered). **Not verified:** header patterns against real FY2025/26 HUD files — run `refresh --url` on the live files before depending on it. |
| `fix/demo-deal-relative-dates` | `~/dev/projects/abstractly-demo-dates` | — | Pushed (`8e1084f`). Makes the Maple Ridge demo deal's dates relative to generation day (good change: kills the date drift QA_REPORT flagged). **MERGE ATTEMPTED 2026-10-04 AND ABORTED — needs a reconciliation task, not a merge.** `main` was untouched (`0545bec`). 3 conflicts vs `953c00a`, two of them semantic: (1) `expected_findings.json` — main has concession-detection's populated `monthly_dollar_impact` (89.58, 50.0) with hardcoded dates; this branch has computed dates with `monthly_dollar_impact: null`. The combination needs both, and the dollar impacts must be **re-derived for the new dates** (a concession's past/future position changes its classification), then the package regenerated. (2) `test_demo_deal_golden.py` — the two branches chose **opposite strategies for the same test**: main *pins* `today` to the fixture's as-of date to sidestep `expired_but_occupied` drift and asserts **10** findings; this branch *never* pins `today` (regenerates into a temp dir, real wall-clock, plus a freshness test that trips 2026-12-15) and asserts **7**. Someone must pick one strategy and re-derive the assertions for all 10 findings under it. Not resolvable mechanically. (3) `TASKS.md` (take main's). |
| `docs/tester-pack` | `~/dev/projects/abstractly-tester-pack` | +7 / 0 | Overnight run, 2026-10-01: in-app Help & Guides (17 articles incl. Getting Started + troubleshooting), tester emails, 10-Q questionnaire, sales drafts updated (local). Frontend + docs only. Headless-verified at 3 widths. **Read `OVERNIGHT_REPORT.md` on the branch**: 12 product bugs found (report-page T-12 upload broken, T-12 income check never fires, only .csv/.xlsx rent rolls feed the report…). |
| ~~`feature/landing-positioning`~~ | `~/dev/projects/abstractly-landing` | — | **SUPERSEDED 2026-10-04 by `feature/pricing-page` — do not merge.** The user's decision: pricing-page carries the design that ships (dark theme, cursor spotlight, new logo, flat per-team pricing, Book-a-call CTAs). Kept on the branch for history, not queued. Work done before the call, in case any of it is ever wanted back: its 4 uncommitted files were committed (`ff2fe40`) and `main` was merged in and resolved (`a2c2a23`, pushed) — that merge is **knowingly broken** and must never reach `main`: `main`'s cards keep ivory backgrounds while the branch's dark token override turns their text ivory too, so the sample-report card and all three pricing cards render white-on-white. Root cause worth remembering: the two branches are **opposite polarity** (`main` = light body, dark hero; this branch = dark body sitewide), so "take main's code but this branch's design" was unsatisfiable — the design *was* the code. `main` also already had a better-engineered fluted-glass hero (`landing.js` `#heroCanvas`: respects `prefers-reduced-motion`, pauses off-screen and on hidden tabs, CSS fallback) than this branch's WebGL `#bgfx-canvas` re-implementation. |

Recommended order: pricing-page → team-isolation (when built) →
loan-underwriting. (`landing-positioning` dropped — superseded.)

## Blocked (needs you)

- **Anthropic API credits** — without them AI extraction/assistant fall
  back to regex and the AI path can't be QA'd.
- **No persistent storage on Render** (free tier). Tester *data* vanishes on
  every deploy/restart/15-min spindown. The `render.yaml` side is now
  prepared on `chore/render-persistent-disk` (disk + `DB_PATH` + `plan:
  starter` on prod and tester); what's left is yours: the billing decision
  and the dashboard steps in `docs/DEPLOYMENT.md` → "Adding persistent
  storage". Render requires a paid instance type for disks, confirmed from
  Render's docs. Note: attaching the disk does **not** migrate the existing
  database, and uploaded *files* are never persisted by design
  (`app/api.py:545` unlinks them; only extracted fields + page numbers are
  stored), so the DB disk covers everything durable.
- ~~No document-level team isolation on main~~ — **resolved**, merged as
  `3cff20b`. Documents carry `team_id` and queries are scoped to the
  authenticated caller, so multiple firms can now share a deployment.
  Each still has its own in practice; that is a choice now, not a limit.

## Up next

- **Stacked Section 8 branches now conflict with `main` in `database.py`** (2026-10-13, after the gauntlet merge `b63927d` added `rent_roll_unit_summaries`): `feature/s8-data-model` (T1) and anything stacked on it (T9) will conflict on merge. Both sides only ADD at the end of the file; correct resolution = `main`'s file + T1's own diff (+336/−0). Done and reviewer-checked on `feature/s8-sample-data` (`96fa0a5`) and `feature/s8-hap-payment-import` (`0da9450`) — copy that file or redo it the same way.
- **Rent-roll importer reads a totals row as a tenant** (found 2026-10-13 by `feature/s8-sample-data`): the Section 8 fixture `juniper_row_rent_roll_2026-10-01_appfolio.csv` has a final row `Total,,16 occupied / 18 units,...`; `parse_csv_rent_roll` imports it as tenant "16 occupied / 18 units" at $20,785.00, unit "Suite Total". Reproduced on `main` and on `qa/overnight-gauntlet` `906eaab`. Own `fix/` branch + regression test; then re-run `capture_section8_sample.py`.
- **Test suite fails 8 files in the primary checkout only** (found 2026-10-05 during the auth-flow merge): `backend/tests/_session_users.py` inserts test users whose email collides with the first admin that `backend/.env` seeds (`ADMIN_EMAIL`), `UNIQUE constraint failed: users.email`. Clean worktrees (no `.env`) pass 83/83. Same on pre-merge main. Small fix, own branch.

1. ~~Push local `main`~~ — done (`f68a287`).
2. **Merge train.** Each needs the user to type `/merge-branch <branch>`
   — **the slash form specifically**: prose like "approve merge X" arms
   the lock but records `branch: ""`, and the merge-branch skill is
   `disable-model-invocation`, so it cannot be run any other way.
   Queued next, verified to merge **clean**:
   `chore/render-persistent-disk`.
   Then: `feature/pricing-page` (ready, `a50097b`, merges clean — but
   see the two content blockers in #9 and the false trust claim in #11);
   `feature/team-isolation` (#2); `docs/tester-pack`.
   `fix/demo-deal-relative-dates` still needs a reconciliation task, not
   a merge. `feature/landing-positioning` is **superseded — do not merge**.
3. Smoke test the tester deployment **beyond `/health`**: login, Maple Ridge
   lease + rent roll upload, Deal Mismatch Report, PDF/Excel export, T-12.
   Only `/health` was checked on 2026-10-04 (all three healthy); the rest
   needs real tester credentials.
4. Invite the first 3 testers.
5. Finish `feature/team-isolation`; then rebase `feature/loan-underwriting` on it.
   - Follow-up from `fix/section8-tenant-share` review: on a Yardi charge-code
     ledger, gauntlet's collapse turns a non-rent charge row (parking) into a
     phantom $0.00 lease; with tenant-share/HAP columns it now also gets a
     contract_rent_mismatch warning. Fix the collapse (root cause). Also:
     surface Section 8 flags in the Deal Mismatch Report (pass
     `section8_checks` through the import API).
6. ~~`research/section8`~~ — **merged** `2fbb542`. The strategic question
   it raises is still open and is yours: the briefing's own finding is
   that for **Housing Choice Voucher** properties the PHA does the
   certification paperwork, not the owner — so the compliance burden
   Abstractly could help with sits with **Project-Based Section 8 and
   LIHTC**, where the owner/agent certifies. Decide whether that's a
   product direction or shelf it; merging the doc didn't decide it.

### Section 8 pivot (approved 2026-10-11 — full detail in `PIVOT_PLAN.md` on branch `pivot/section8`)

**User decisions 2026-10-12 (answer PIVOT_PLAN.md Q4 + Q5; binding for every Section 8 task):**
- **Q5 — data minimization.** Store only what the features need: tenant name, unit, tenant share, HAP amount, contract rent, recert dates, inspection dates. **Never store** SSNs, full income documents, or bank details (DOB is not on the list either, so don't store it). Everything stays scoped by `team_id`. Consequences: T0 masks/drops SSN, DOB and bank numbers in stored `extracted_fields` `source_text` quotes, in free-text `notes` on write, and in text sent to Anthropic; income-verification documents must not be kept as uploads (extract the allowed fields, keep nothing else); every new table carries `team_id NOT NULL`. Encryption at rest / MFA / export-delete were not part of the answer — still tracked separately, not made prerequisites here.
- **Q4 — deadline rules configurable per PHA.** Cure deadlines, notice periods, renewal lead times etc. live in per-PHA settings (`phas.settings_json`, from T1) with code defaults as fallback; never hard-coded in a detector. Every rule-driven date shows **"Verify with your PHA"** in the UI. **Launch gate:** the user's Section 8 contacts check the defaults before launch (before T11 copy or `SECTION8_MODE` goes live on prod).

Claim with `/start-task <branch>`; read PIVOT_PLAN.md Step 4 first (`git show pivot/section8:PIVOT_PLAN.md`). Every new surface behind `SECTION8_MODE` (default off); additive schema only; brand files untouched; never edit Render env vars. Test bed = `qa/section8-fixtures` answer key.

**Phase 0 — prerequisites**
- P1 `/merge-branch feature/lease-intelligence` (user) · P2 `/merge-branch qa/overnight-gauntlet` (user, after its 3 QA_REPORT decisions) · P5 `/merge-branch feature/s8-hud-data` (user; only T8 needs it)
- P3 `fix/section8-tenant-share` and P4 `qa/section8-fixtures` — in flight in other sessions; user approves their plans
- **T0 `feature/s8-pii-guard`** (M) — SSN/DOB/bank masking before storage + before Anthropic, traceback scrub in alert emails, per-team AI-off switch. **Can start now. Must merge before testers upload real tenant docs.**

**Phase 1 — core** (claimable as soon as deps are met)
- **T1 `feature/s8-data-model`** (M) — **Ready for review 2026-10-11 (`b6caf9a`)** — `SECTION8_MODE` helper + team-scoped tables: properties, units, phas, tenancies, hap_contracts, unit_documents. **Can start now.** Owns `database.py` schema for these.
- T2 `feature/s8-hap-contract-extraction` (M) — HAP contract / PHA notice doc kinds + new fields. Needs P1, P4.
- T3 `feature/s8-rent-roll-check` (M) — contract/tenant/HAP detectors in deal_mismatch, report relabel under flag. Needs P1, P3, P4.
- T4 `feature/s8-hap-payment-import` (M) — PHA payment registers → `hap_payments`. Needs T1, P4.
- T5 `feature/s8-hap-reconciliation` (L) — expected vs received HAP by unit/PHA/month, $ findings, export. Needs T1, T4.

**Phase 2 — compliance calendar**
- T6 `feature/s8-inspections` (L) — needs T1 · T7 `feature/s8-recert-tracking` (M, HCV) — needs T1, T2 · T7b `feature/s8-pbra-recerts` (L) — needs T7, T0 · T8 `feature/s8-rent-increases-renewals` (M) — needs T1, T2, P5 · T9 `feature/s8-unit-file-and-phas` (M) — needs T1 — **built + pushed 2026-10-13 (`d893c56`), stacked on T1** · T10 `feature/s8-this-month` (M) — needs T5, panels from T6–T8

**Phase 3 — repositioning**
- T11 `feature/s8-marketing-copy` (M) — **can be drafted now; must NOT merge until T3 + T5 are live on tester** (one push to main = public on prod). Pricing waits on Q2.
- T12 `feature/s8-app-reframe` (M) — nav/labels, hide CRE views under the flag. Needs T1.
- T13 `feature/s8-sample-data` (S–M) — Section 8 sample + DEMO_MODE seed under the flag. Needs P4, T1.

**Phase 4** — T14 `feature/s8-assistant` on `feature/deal-assistant`; plan later.

**Startable right now in parallel:** T0, T1, T11 (draft only).

### Housekeeping (safe, low priority — each needs a yes)

- Delete merged/stale branches: `worktree-agent-a3fcc0f…`, `-a640a39f…`,
  `-a671d27b…`, `feature/deal-mismatch-report` (all 0 ahead of main).
- Delete `worktree-agent-ade7619750bfa9a9f` (+3/−82, stale 2026-09-02,
  competing `accounts` schema with a confirmed cross-tenant leak; already
  mined for team-isolation's route checklist) and its worktree under
  `.claude/worktrees/`.
- Remove merged worktrees: `abstractly-tester-routing`,
  `abstractly-t12crosscheck`, `abstractly-usage`, `abstractly-rentroll-qa`
  (all 0 ahead; `abstractly-usage` has 1 untracked file — check it first).
- 3 stashes (`git stash list`): team-isolation schema start, t12 test WIP,
  agent-ade76 WIP. Check before dropping.
- Root `PLAN.md`/`SUMMARY.md` on main are `feature/usage-limits` leftovers;
  remove once no open branch edits them (new plans live in `docs/plans/`).
- `backend/tests/sample_lease.pdf` is gitignored: new worktrees run
  `python backend/tests/create_sample_lease.py` (start-task does this).
- Bug in `.claude/hooks/guard.py` (found 2026-10-20, not fixed by request):
  typing `/merge-branch <branch>` records the approval's branch as
  `/merge-branch`, so the guard then blocks `git merge <branch>`. In
  `prompt()`, the slash-command event arrives with empty arguments, so it
  builds `"/merge-branch \n/merge-branch <branch>"`, and the
  `/merge-branch\s+(\S+)` match skips the space and newline and takes the
  second `/merge-branch` as the branch. Fix: skip the `"/%s %s"` prefix
  when args are empty (or match `[^\s/]\S*`). Until fixed, `/merge-branch`
  can't merge; workaround is a plain message containing
  `merge approved: /merge-branch <branch>`.

## Done

| Branch | Merged as | Notes |
|---|---|---|
| `docs/design-tokens` | `04e3798` | `DESIGN_TOKENS.md` (root) inventory of every color/font/spacing/radius/shadow/z-index/logo asset; repeated colors centralized into `design-system.css` tokens with identical values (6 CSS files). Before/after: 45 screenshots 0 px differ, computed styles + every resolved CSS rule identical, negative control caught. Reviewer **MERGE**. Merged 2026-10-12 together with `qa/section8-fixtures`; suite on `04e3798` in a clean worktree **84/84** (primary checkout 76/84 = the known `.env` `users.email` UNIQUE collision in `_session_users.py`, confirmed on `test_cache.py`). Pushed `390d110..04e3798`. Smoke 2026-10-12: new `design-system.css` served on getabstractly.com + tester within ~4 min; prod + tester APIs `/health` healthy; headless screenshots of tester home/login (1440+375) and prod home looked at — render correctly, landing sample-report MEDIUM amber now comes from the token. **`abstractly-demo-api` returned 503 `x-render-routing: hibernate-wake-error` for 2+ min after the push** (demo static site 200). No backend code in either merge; check Render's demo-api event log. Not smoke-tested (needs login): lease/rent-roll upload, Deal Mismatch Report, exports, T-12 — and neither merge touches them. Follow-ups: stale `@import` comments (design-system.css, app/styles.css, admin/dashboard.html); `landing.js` comment says `--lux-accent-rgb` is in landing.css; leftover blue focus ring `rgba(37,99,235,.2)` in app/styles.css; app sidebar still the generic building icon. |
| `qa/section8-fixtures` | `e0341a6` | Fictional two-property Section 8 fixture set in `backend/tests/fixtures/section8/` (leases + HUD addenda, HAP contracts, rent rolls, PHA HAP registers, inspections) with 23 planted errors in `ANSWER_KEY.md` / `answer_key.json`; new `test_section8_fixtures.py`. Data + test only, no app code. Reviewer **MERGE**. Merged 2026-10-12; pushed with `docs/design-tokens` (suite 84/84 clean, see that row). Future Section 8 checkers grade against `answer_key.json`. |
| `docs/claude-md-tenancy` | `a36a085` | CLAUDE.md Tenancy bullet now says document tables are team-scoped (`3cff20b`); same stale claim removed from `.claude/agents/security-auditor.md`, `reviewer.md`, `.claude/skills/start-task/SKILL.md`. Docs only. Reviewer MERGE. Suite 83/83 on `c6300f7` in its worktree; merged tree differs only in TASKS.md. Pushed 2026-10-11 (`a02259d..31947c9`). Tester smoke (headless): `/health` 200, `/leases` `/tags` `/portfolio/health-score` 401 unauthenticated, bad login 401, landing + `/app/` sign-in render at 1440/375. Logged-in flows (upload, report, export, T-12) not run: need tester credentials. |
| `feature/auth-flow` | `77e25f0` | Self-serve email-link signup (behind `SELF_SERVE_SIGNUP_ENABLED`, on for tester only), polished forgot/reset, keep me signed in, sign-out-everywhere on any password change, app Sign out, dark landing-style auth pages; also fixed admin dashboard 401→404 loop, staff consoles in Safari, Render per-IP limits, >72-byte 500s, 405→500, reset token at team-setup. Reviewer **MERGE**, security-auditor no critical/high. Merged 2026-10-05; suite on the merge commit in a clean worktree **83/83** (the primary checkout shows 8 failures that also occur on pre-merge main — `_session_users.py` collides with the admin `backend/.env` seeds; see Up next). User approved the push. Pushed `3f1d3aa..eb2a4f8`. **Smoke:** prod `abstractly-api` has the new code (`/auth/options` → signup off, `/auth/link-status` + forgot message correct, signup 404); live login pages on getabstractly.com and tester render correctly (headless, looked at). **`abstractly-tester-api` and `abstractly-demo-api` did NOT redeploy** (still old code 13+ min later, both healthy) while their static sites did — tester's new reset/finish pages call `POST /auth/link-status`, which the old tester API lacks, so **reset on tester is broken until you trigger a Manual Deploy of tester-api (and demo-api) in Render.** Also still needed for tester signup: `EMAIL_USER`/`EMAIL_APP_PASSWORD` on tester-api. |
| `design/og-image-minimal` | `8837327` | User-approved minimal link preview: hero shader as a soft gold glow + centred 120px mark/wordmark, no other text; `og-image.png` 2400x1260 (~578 KB); all 14 pages `?v=5` + width/height + new alt text. Reviewer **MERGE** (twice). Merged 2026-10-05, zero conflicts. Suite on the merge commit in a clean worktree **82/82**. Pushed `198d0b8..8837327`. Smoke: all three APIs healthy (this deploy also **brought `abstractly-tester-api` back** — see the calendly row); `og-image.png` served at 591,787 B on prod + tester; downloaded and looked at — correct. **Follow-up:** og/twitter image URLs still point at `abstractly-n0id.onrender.com`, not `getabstractly.com`. Worktree left in place: holds 2 untracked rejected-variant files (`design/logo/og/build_og.mjs`, `og-image.svg`) — user to OK a force-remove. **Not verified:** a real iMessage/Slack/WhatsApp unfurl. |
| `feature/calendly-booking` | `e1f1d8b` | Demo form emails rebuilt: requester gets a personal note (CALENDLY_URL link, Reply-To tim@, plain-text part); admin notice -> `ADMIN_EMAIL` (`DEMO_REQUEST_NOTIFY_EMAIL` removed); every send logs success/exact failure; **fixed live bug: `From:` header had no parseable address since `2a7e344`**. "Book a call" links -> CALENDLY_URL via new public `GET /public-config` (no `@require_role` by design, like `/health`; falls back to the form). `CALENDLY_URL` declared `sync: false` on abstractly-api. Also fixed `test_demo_deal_regression.py` (#10). Reviewer + security-auditor **MERGE**. Merged 2026-10-05, zero conflicts. Suite on the merge commit in a clean worktree **82/82** — first fully green run. Pushed `33b8665..198d0b8`. Smoke: prod `/public-config` -> `{"calendly_url":"https://calendly.com/timpisano/abstractly-intro-call"}` (dashboard var is set), CORS allows getabstractly.com, `Cache-Control: public, max-age=300`; demo returns `null` (not set there — expected); live pages carry `data-book-call` hooks. **`abstractly-tester-api` returned 502 with `x-render-routing: no-deploy` for 10+ min after this push** (prod + demo healthy). Not caused by the code as far as verified: the merged app boots locally with tester-like env (`/health` 200, `/public-config` null) and demo runs the same image. **Recovered on the next deploy (`8837327`)** — still worth checking the dashboard's event log for why that deploy failed. **Not verified:** a real demo-form submission + both emails (would send real mail) — user to test live. |
| `design/logo` | `47f2a7b` | **Seven rows** A logomark (user's pick, round 3): header/footer mark on index + pricing, `favicon.svg`/`.ico`, `apple-touch-icon.png`, new `og-image.png`, og+twitter tags on all 14 pages (`?v=2`); concept SVGs + `build.py` kept in `design/logo/`. Reviewer **MERGE**. Merged 2026-10-05 on the user's typed approval, zero conflicts. Suite on the merge commit in a clean worktree **81/82** (only known `test_demo_deal_regression.py`). Pushed `9392a66..47f2a7b`. Smoke: all three APIs healthy; new favicon/apple-touch/og-image served on getabstractly.com and tester at the new byte sizes; screenshots looked at — new mark in the prod header at 1440 + 375 and in the tester pricing footer, og-image renders correctly. **Follow-ups:** `og:image`/`twitter:image` URLs point at `abstractly-n0id.onrender.com`, not `getabstractly.com` (works, but should move to the real domain); app/admin/owner/404 still use the generic building icon |
| `chore/contact-email` (round 2) | `0f9de09` | Prod demo-form fix + demo email routing: `abstractly-api` `ADMIN_ALLOWED_ORIGINS` adds `https://getabstractly.com` + `https://www.getabstractly.com` (keeps n0id; tester/demo unchanged); demo notification -> `DEMO_REQUEST_NOTIFY_EMAIL` (default tim@getabstractly.com) with Reply-To = visitor (CR/LF-guarded); confirmation carries `CALENDLY_URL` (user-confirmed `calendly.com/timpisano/abstractly-intro-call`); email subjects flattened; mailto links in both FAQs + Book a Demo section; `EMAIL_USER`/`EMAIL_APP_PASSWORD` declared `sync: false` on `abstractly-api`. Pushed to the branch by another session **after** round 1 merged. security-auditor PASS; reviewer **MERGE** 2026-10-05. Only conflict TASKS.md (took main's). Suite on the merge commit in a clean worktree **81/82** (only known `test_demo_deal_regression.py`). Pushed `2a777b7..9392a66`. Smoke: all three APIs healthy; preflight to `/demo-request` allowed from getabstractly.com, www., and n0id, refused (no ACAO) for evil.example.com; live pages show 3 tim@ mailto links, 0 phone matches on all three sites. **Not verified:** an actual demo-form POST + notification email (would send real mail). **User to confirm in Render dashboard:** `EMAIL_USER`/`EMAIL_APP_PASSWORD` set on `abstractly-api` (else notifications silently no-op; request still saved). Cosmetic follow-up: `render.yaml:87` comment still says `ADMIN_EMAIL` is needed for demo notifications. |
| `chore/contact-email` | `5701b8b` | Public contact: footer email -> `tim@getabstractly.com` + "Book a call" link (`#book-demo`) on `index.html`/`pricing.html`; personal phone removed; `Reply-To: tim@getabstractly.com` on outgoing mail (`From` stays `EMAIL_USER`). New `test_public_contact.py` + Reply-To test. Reviewer **MERGE** 2026-10-05 (incl. the late commit `6e2b9fa`). Merged 2026-10-05 on the user's typed approval, zero conflicts; pushed `b18bbe3..290a1ad` (also carried other sessions' TASKS-only commits). Suite on merged main in a **clean worktree: 81/82** — only the known `test_demo_deal_regression.py`; baseline `origin/main` was 80/81 the same way. Smoke: all three APIs `{"status":"healthy"}`; prod (`abstractly-n0id.onrender.com`), tester and demo frontends all serve the new footer with zero phone matches on `/` and `/pricing.html`; tester screenshots at 1440/768/375 looked at — footer correct. Not verified: login / upload / report / export flows (need credentials; this change touched none of them). Watch: `feature/calendly-booking`'s plan predates this footer link, and `test_public_contact.py`'s regex will need a one-line update if Calendly adds attributes to it. |
| `chore/demo-rent-roll-polish` | `5d7fdbe` | Maple Ridge demo polish: rent rolls regenerated as PMS-style **xlsx + landscape PDF** (the two `*_appfolio.csv` files are **deleted** — fixture paths now point at the xlsx), 15 lease PDFs reworked into real-looking signed leases, T-12 as a clean operating statement, institutional-looking Deal Mismatch Report PDF (`deal_mismatch_export.py`), new data-driven `test_demo_deal_regression.py`, and `DEMO_WALKTHROUGH.md` sales script. Merged 2026-10-04. **Resolved on the branch, not on main:** the primary checkout is read-only (rule 3), so a combined conflict resolution is impossible there — merged `main` *into* the branch instead (`5139d3f`), fixed it up (`7dec3d1`), pushed, after which main merged with **zero conflicts**. Two stale expectations fixed in the process: the golden test still demanded `"(no concession shown)"` though the new rent rolls carry a real `$0.00` Concessions column (detector deliberately distinguishes the two; all 3 `concession_missing` findings fire correctly), and the demo README still warned that `detect_concession_missing` is a stub — false since `953c00a`, and actively misleading for sales. Suite **79/79 on merged main**, run post-merge. |
| `chore/render-persistent-disk` | `92013f7` | 1 GB persistent disk (`abstractly-data`, `/app/data`) + `DB_PATH` + `plan: starter` on **`abstractly-api` only**. Config + docs, no app code. **Scope narrowed from the original branch on the user's instruction** (`6d14c95`): the tester's disk and `plan: starter` were removed, so tester and demo both stay `plan: free` with no disk and keep losing data on restart. Docs corrected in three places that still assumed two disks. Merged 2026-10-04, zero conflicts. `test_frontend_api_routing.py` (the test that parses `render.yaml`) passes; suite **80/81 in a clean worktree**. Smoke test: all three APIs healthy. **`abstractly-demo-api` returned 502/503 for ~7 minutes after the push and then recovered on its own** — a slow free-tier redeploy plus `DEMO_MODE` reseed, not a failure, and notable because demo is the service this change does not touch. Expect that window on future pushes. **Not verified from here:** whether the disk is actually mounted and in use — see Waiting-on-you #7. |
| `feature/pricing-page` (round 2) | `c21ced5` | **The marketing design that ships.** Flat per-team pricing ($499/$399, $1,250/$999, Enterprise), dark theme, cursor-spotlight cards, new logo, Lenis, Book-a-demo CTAs with no self-serve checkout. 10 files, frontend-only. Merged 2026-10-04 on the user's typed approval, **zero conflicts** (fast-forward after `main` was merged into the branch first). **Fixes the per-property pricing ($25/$20) that was live on production.** Suite **80/81 in a clean worktree**; the primary checkout reported 72/81, which is the `.env` artifact in the Decisions log, not this merge — a frontend-only diff cannot break backend tests. Smoke test went beyond `/health`: polled production until the banner disappeared from the served HTML (11130 -> 10838 bytes), confirmed `pricing-config.js` now serves 499/399/1250/999, confirmed all three frontends serve the new build with zero `per-property` occurrences, and **looked at the live production page** — flat prices, no banner, readable. |
| `feature/team-isolation` | `3cff20b` | **Real document-level multi-tenancy** — `team_id` on `leases`, `discrepancies`, `alerts`, `tasks`, etc., every document query scoped to the authenticated caller's team. 82 files, +7948/−1117; adds `app/sample_deal.py`, `tests/_session_users.py`, `test_team_isolation.py`, `test_team_isolation_fixes.py`, `frontend/app/team-setup.html`. Merged 2026-10-04 on the user's typed approval; **zero conflicts** (the branch had already merged `main` at `0ae5438` and fixed the `test_concessions.py` `team_id` args in `d8aeed5`). Suite **80/81 in a clean worktree** — only the pre-existing `test_demo_deal_regression.py` bug (#10). Smoke test: all three services `{"status":"healthy"}` across a 2-minute window after the push, and `/app/team-setup.html` (a file new on this branch) returns 200 with real content on the tester — which is what proves the redeploy actually landed rather than just reporting healthy. **Caveat:** merged tip `d8aeed5` is 2 commits past the reviewed `fe520c9`; both are a mechanical `main` merge and a 6-line test-only change, so no unreviewed production code shipped. **Follow-up (not blocking):** bind tokens to the user's email so an old token can't act as a different user after a deploy-time DB wipe (`auth._live_user`); and `feature/deal-assistant` must rebase (3 trivial `api.py` conflicts + its session-faking tests need `sync_session_user`). |
| `research/section8` | `2fbb542` | Section 8 / LIHTC founder's briefing by another session — **docs only**, one new file (`docs/research/section8.md`, 224 lines), nothing modified, no code. Merged 2026-10-04 on the user's typed approval. Scanned before merging: no placeholders, secrets, or PII (the one `$KEY` hit is a shell variable in an illustrative `curl` example). Suite **79/79** post-merge; all three Render services healthy after the push. **Merging it was not a product decision** — see Up next #6 for the question it leaves open. Deviation worth noting: it was in Up next, not "Ready for review", and carried no reviewer verdict; merged anyway as an additive docs-only file on the user's explicit instruction. |
| `fix/concession-detection` (rounds 3–4) | `f68a287` | **Merged 2026-10-04 on the user's typed approval; pushed.** The gap this closed: `main`'s earlier merge `953c00a` took the branch at its **round-2** tip (`1380198`), but the branch then gained three more commits — `b4e3f4a` (round 3), `1f8ec14` (round 4), `500f368` — which stayed unmerged and untracked while TASKS.md recorded the branch as done. Brings `concessions.py` (+40/−9), `rent_roll_import.py`, and 65 lines of tests: interest-free deposit wording no longer reads as free rent, default **forfeiture** clauses now read as negations rather than conditional grants, credits **applied to the deposit** are excluded from effective rent, plus clause-splitting fixes. Merged **clean** (prepared on the branch first — see the Decisions log). Suite **79/79** in the primary checkout post-merge; note that is 78/79 on a clean checkout because of the separate fixture bug in #10, which this merge does not touch. All three Render services returned `{"status":"healthy"}` after the push and all three frontends serve bytes identical to `main`. Backend-only change, so no UI to verify. |
| `fix/concession-detection` (rounds 1–2) | `953c00a` | Real concession detection in the Deal Mismatch Report (was a stub): new `app/concessions.py` (free months, recurring discounts, one-time credits, net effective rent), `concessions` from both extraction engines, rent-roll Concession column, new `concession_missing`/`concession_mismatch`/`concession_expiring` checks, effective-rent-aware `rent_mismatch`. Maple Ridge now catches all 10 planted issues ($45,355/yr). Two reviewer rounds fixed (`7b67ea2`, `1380198`). Merged 2026-10-04 on the user's typed approval, **ahead of team-isolation** (TASKS.md recommended the reverse): verified safe to reorder — no new API routes, `api.py` untouched, its only SQL is in a test helper, so there was no team-scoping surface. Cost of the reorder: team-isolation inherits the `test_demo_deal_golden.py` conflict and owes the `test_concessions.py` `team_id` update (#4). Suite **78/78 on merged main**, run post-merge; also fixed the long-standing 76/77 fixture bug (#8). `concessions` deliberately **not** editable in the lease-detail UI yet. |
| `chore/agent-os` | `c6c873d` | Agent OS v2: CLAUDE.md + Definition of Done, TASKS.md handoff blocks, reviewer/security-auditor/qa-tester/ui-checker, 8 skills incl. resume-task + prompt-builder, safety hooks, `docs/HOW_TO_RUN_AGENTS.md`. Merged 2026-10-04 by finishing the half-done merge left in the primary checkout (21 staged files already matched the branch tip byte-for-byte; only `TASKS.md` needed resolving — taken as a union of main's rent-roll-hardening facts and the branch's new structure). Suite **77/77 on merged main**, run post-merge. Pushed; prod + tester + demo all returned `{"status":"healthy"}`. Tooling/docs only — no app code, so the redeploy was functionally a no-op. |
| `fix/rent-roll-hardening` | `03cebb5` (+ test fix `74d3237`) | Rent roll edge cases, negative-rent sign loss, multifamily tenant extraction, route roles, Maple Ridge demo deal + golden test. Merged on the user's explicit instruction. An earlier "72/72 passed" claim in this file was false; real post-merge run was 76/77, fixed to 77/77. Pushed. |
| `feature/usage-limits` | `ab7fb6f` | `teams` table + `users.team_id`, per-team limits/quotas, upload dedup (billing scope only). Pushed. |
| `feature/t12-crosscheck` | `0ee711c` | T-12 cross-check in the Deal Mismatch Report. Pushed. |
| `fix/tester-api-routing` | `b6a46e9` | Tester frontend → tester API (CSP); render.yaml/config.js pairing test. Pushed. |
| `feature/deal-mismatch-report` | `e2c4848` | Report with dollar impact, citations, export; analyst role. Pushed. |
| `feature/landing-positioning` r1 | `d6ff92d` | Multifamily landing + Book a Demo. Pushed. |
| `feature/pricing-page` r1 | `a794f0e` | Config-driven pricing page + redesign. Pushed. |
| (docs) | `64af20a`, `d55fef9`, `70ed972` | First CLAUDE.md / TASKS.md / agents / skills. |

## Decisions log

- **2026-10-13 — qa/overnight-gauntlet QA_REPORT decisions: all three accepted as built (user).** (1) Unit matching ignores designator wording (Suite = Apt = Unit; Building A + Apt 101 = A-101) — reverses the old `test_unit_designator_preservation_is_intentional` docstring stance; revert is one function (`portfolio._normalize_address`). (2) New team-scoped table `rent_roll_unit_summaries` (vacant/down unit counts for occupancy). (3) Re-import supersedes an earlier rent-roll file only when ≥ half its units reappear; "replaced N rows" not shown in the upload UI yet (frontend follow-up).

- **2026-10-12 — Section 8 PII = data minimization; deadline rules per PHA (user, PIVOT_PLAN Q5/Q4).** Store only tenant name, unit, tenant share, HAP, contract rent, recert + inspection dates; never SSNs, full income documents, or bank details; all team-scoped. Deadline rules configurable per PHA with defaults, labelled "Verify with your PHA", defaults checked by the user's Section 8 contacts before launch. Detail under Up next → Section 8 pivot.

- **2026-10-11 — The test suite isn't hermetic in the primary checkout.** On merged `a36a085` it gave 75/83 there (gitignored `backend/.env` + local `*.db`: `UNIQUE constraint failed: users.email`, email-backend assertion), 80/83 in a fresh detached worktree (missing gitignored `backend/tests/sample_lease.pdf`), 83/83 in the branch worktree on an identical tree. User approved the push on that evidence. Also seen: a test attempted real SMTP (`550` for jane@example.com) and one hit `anthropic.APIConnectionError` — candidate fix branch (rule 8). Run merge-gate suites in a clean worktree with fixtures generated, not the primary.

- **2026-10-05 — `x-render-routing: no-deploy` on a 502 means Render has no live deploy for that service** (failed/cancelled build), not a slow cold start. Seen on `abstractly-tester-api` after `198d0b8`; the next push redeployed it fine. If it recurs, check the service's Events tab before suspecting the code.

- **2026-10-05 — Before removing a merged branch's worktree, re-fetch and confirm the branch tip is in `main`.** `chore/contact-email` gained 5 commits from another session after its first merge; the merger's cleanup deleted the local ref and worktree (restored immediately, nothing lost). Merged branches can keep moving while other sessions work on them.

- **2026-10-05 — The merge guard holds ONE approved branch per session; the latest `/merge-branch` wins** (`guard.py:480`). Typing several `/merge-branch` commands in a row while one merge is in flight silently replaces the earlier approvals. Type the next one only when the merger asks for it.
- **2026-10-05 — Clean-worktree test runs need `backend/tests/sample_lease.pdf` copied in.** It is gitignored (`backend/.gitignore:26`), so a fresh worktree fails `test_extraction`, `test_multi_lease_detection` and `test_synthetic_accuracy` with FileNotFoundError — environment, not code. With it copied in, clean runs match the recorded counts. The primary checkout's `backend/.env` still skews results the other way (73/82 there today).
- **2026-10-05 — Prod frontend lives at `abstractly-n0id.onrender.com`, not `abstractly.onrender.com`** (the latter 404s). Smoke-check that URL.

- **2026-10-04 — On this marketing page, changing page HEIGHT can break
  text legibility.** Dropping the pricing banner shortened the page,
  which moved the scroll-linked shader's bright ribs up behind the
  pricing header and washed out the eyebrow and subhead at 375px. It
  looked like an animation-phase artifact; re-capturing at a different
  delay reproduced it, proving it real. Fixed with the scrim pattern the
  index hero already uses (`.hero-copy::before`), radial here because the
  pricing heading is centered. **Any future edit to `index.html` /
  `pricing.html` needs a visual check at 375px, not just a diff review** —
  content that reads fine locally can be unreadable once the shader moves.

- **2026-10-04 — `backend/.env` in the primary checkout corrupts test
  results in BOTH directions; trust a clean worktree instead.** Merging
  team-isolation gave **72/81** in the primary checkout — 8 failures
  (`test_ai_extraction`, `test_async_extraction`, `test_cache`,
  `test_audit_trail`, `test_team_isolation`, …) that looked like a broken
  merge. All 8 were artifacts of the local `.env`: `EMAIL_USER` /
  `EMAIL_APP_PASSWORD` make the team-setup test's "no email backend
  configured" assumption false, and `LEASE_AI_EXTRACTION` /
  `LEASE_EXTRACTION_ENGINE` redirect the extraction tests. The same file
  simultaneously makes a genuinely broken test *pass* (#10). Re-run in a
  clean detached worktree: **80/81**, only the known failure. The clean
  worktree is also closer to production, since Render injects env vars
  from the dashboard and has no `.env` file. **Run the suite in a clean
  worktree before believing any failure or any pass.**

- **2026-10-04 — A merged branch can still have unmerged commits; check
  the tip, not the table.** `fix/concession-detection` was recorded here
  as done at `953c00a`, but that merge captured only its round-2 tip.
  Rounds 3 and 4 — real detection fixes, reviewed, with a MERGE verdict
  in their own commit messages — sat on `origin` for days, invisible
  because the row said "merged". Found by diffing `main` against every
  branch tip rather than trusting this file. Worth repeating that diff
  periodically: `git diff --stat main...<branch>` on anything marked
  done is cheap and catches exactly this.
- **2026-10-04 — Two unrelated reports collided on `OVERNIGHT_REPORT.md`.**
  Merging rounds 3–4 hit an add/add conflict on that filename: `main`'s
  copy is the `chore/demo-rent-roll-polish` run, the branch's is the
  concession run. Taking either side would have silently destroyed a
  document, so both were kept — `main`'s keeps the root filename and the
  concession one moved to `docs/reports/2026-10-02-concession-detection.md`,
  following the path `feature/team-isolation` already chose. Root-level
  `OVERNIGHT_REPORT.md` is a collision magnet for autonomous runs;
  new reports should go straight to `docs/reports/<date>-<topic>.md`.
- **2026-10-04 — Resolve merge conflicts on the feature branch, not on
  `main`.** The read-only-primary-checkout hook (rule 3) blocks editing any
  file but `TASKS.md` there, so a conflict needing a *combined* resolution
  cannot be finished in the primary checkout at all — `--ours`/`--theirs`
  are the only options, and neither is right when both sides have true
  content. Standing pattern from now on: `git merge main` **into** the
  branch in its own worktree, resolve and test there, push, then merge into
  `main` conflict-free. Worked first try on `chore/demo-rent-roll-polish`.
  The merge-branch skill's step 2 should be updated to say this.
- **2026-10-04 — The demo-deal merge order had a real cost after all.**
  Merging `fix/concession-detection` first was safe for *production* code
  (no routes, no queries), but both it and `fix/demo-deal-relative-dates`
  rewrote `test_demo_deal_golden.py` and `expected_findings.json` with
  incompatible designs — pin `today` vs. never pin `today`. Whoever went
  second was always going to inherit a semantic conflict; merging
  concessions first put that cost on relative-dates. Lesson: for branches
  that share a *fixture*, check the fixture's conflicts before choosing an
  order, not just the production-code surface.
- **2026-10-04 — Merged `fix/concession-detection` before
  `feature/team-isolation`**, reversing this file's recommended order,
  because the user typed that branch's approval. Checked first that the
  order wasn't correctness-critical: concession-detection adds no API
  routes, doesn't touch `api.py`, and its only SQL is in a test helper,
  so there was no unscoped-query surface for team-isolation to cover
  (rule 4). The deferred cost is real but mechanical and lives in tests:
  team-isolation now resolves the `test_demo_deal_golden.py` conflict and
  updates `test_concessions.py` for the required `team_id` args.
- **2026-10-04 — Merge approval is per-branch and must be typed.** A prose
  request to merge five branches in one pass didn't arm the guard (only
  `/merge-branch <branch>` / `approve merge` / `merge approved` match
  `APPROVE_RE`, and `git merge` is then checked against the named branch).
  Kept as-is rather than loosened: one typed approval per branch is the
  point of the gate, and the batch included a branch under a security BLOCK.
- **2026-10-04 — Another session switched the primary checkout off `main`**
  (to `research/section8`) mid-merge, against rule 3. Harmless this time —
  `main` and the merge commit were intact, and the branch work is safe —
  but a `git log` run inside that window reported the wrong branch's
  history. If the primary checkout's HEAD looks wrong, check
  `git reflog` before concluding `main` was rewound.
- **2026-10-01 — Agent operating system v2** (`chore/agent-os`): hooks now
  enforce no-browser, no-main-changes-without-typed-approval, a single
  merge lock, and a read-only primary checkout. TASKS.md lives only in
  the primary checkout. Plans move to `docs/plans/<branch>.md`.
- **2026-10-01 — Team isolation converges on `usage-limits`' `teams`/`team_id`**,
  not the stale branch's `accounts`/`account_id`. Reached independently by
  `~/dev/projects/TEAM_AUDIT.md` and `feature/team-isolation`'s plan.
  Reason: already merged and reviewed; billing and visibility on one entity.
- **2026-10-01 — Merge order on local main:** tester-api-routing →
  t12-crosscheck → usage-limits → rent-roll-hardening (test conflicts
  resolved by taking t12's versions).
- **(prior) One firm per deployment** until document-level isolation lands.
