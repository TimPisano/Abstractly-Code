# TASKS — single source of truth

**The copy that counts is `~/dev/projects/lease-abstraction/TASKS.md`
(primary checkout, on `main`).** Never edit TASKS.md on a feature branch.
Commit changes with `git commit -m "TASKS: …" -- TASKS.md` (the hooks
allow TASKS.md-only commits on main). `/status` reconciles this file with
git; `/session-handoff` writes the handoff blocks; `/resume-task` reads them.

Last reconciled with git: **2026-10-04** (`chore/render-persistent-disk`
merged + pushed). `main` @ `92013f7` == `origin/main`.
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
12. ~~`chore/contact-email` already exists~~ — **extended and ready**
   (`0d2297d`, pushed). It already had the footer email swap and the
   `Reply-To` header; it was missing the phone-number removal, which is
   now done, plus a regression test. Merges clean. See Ready for review.
10. **`main` is 78/79 on a clean checkout, not 79/79 — correction.**
   `chore/demo-rent-roll-polish` added `test_demo_deal_regression.py`,
   which repeats the exact fixture bug #8 described: it hardcodes
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
| `feature/loan-underwriting` | `~/dev/projects/abstractly-loan` | +2 / −16 | ~19 uncommitted files (`api.py`, `database.py`, tests, plan); not pushed. Feature-flagged off. Merge **after** team isolation (its plan defers all tenancy to it). Another session may be active — don't touch. |
| `feature/deal-assistant` | `~/dev/projects/abstractly-assistant` | 0 / −7 | Worktree only, nothing built. Not started. |
| `feature/calendly-booking` | `~/dev/projects/abstractly-calendly` | +1 / 0 | Branched off `7ac879b` 2026-10-04. Calendly popup on all 9 Book-a-Demo CTAs (`index.html` ×5, `pricing.html` ×4), keeping `href="#book-demo"` as a fallback so no CTA can become a dead click. **Plan written, awaiting user approval** — `docs/plans/feature-calendly-booking.md`. Key finding: the task as given would have shipped a popup that never opens — all 3 frontends run `default-src 'self'` with no external hosts, so **5** CSP directives in `render.yaml` block Calendly (script, style, frame, img, font). Prior art: none (no Calendly anywhere, any branch, any stash). Will collide with `feature/pricing-page` / `feature/landing-positioning`, which both rewrite the same two files. |

### Handoff blocks

#### feature/calendly-booking
- Worktree: `~/dev/projects/abstractly-calendly`
- Goal: every Book a Demo CTA opens the Calendly popup in place, with the existing demo form as fallback.
- Loop step: 3 — plan written, waiting for user approval
- Last update: 2026-10-04 by start-task
- Next action: user reviews `docs/plans/feature-calendly-booking.md` and answers its 3 open questions (form's fate, merge order vs. the hero branches, booking URL slug)
<!-- One block per In-progress task, written by /start-task and
     /session-handoff, read by /resume-task. Keep them current. -->

## Ready for review (pushed, not merged)

| Branch | Worktree | +/− main | Notes |
|---|---|---|---|
| `chore/contact-email` | `~/dev/projects/abstractly-contact-email` | +3 | **Ready.** Pushed `0d2297d`, merges **clean**, 4 files. Public contact details: footer email -> `tim@getabstractly.com` on `index.html` + `pricing.html`, personal phone `631-697-8711` removed from both. Those two footers were the **only** public-facing appearances of either -- `main` has no legal or help pages (`404.html` is the only other public page). `email_service.py` sets `Reply-To: tim@getabstractly.com` while `From` stays `EMAIL_USER`, because Gmail SMTP rejects a `From` the authenticated account doesn't own. New regression test pins both headers; verified it fails without the fix. Suite **80/81** in a clean worktree. **Left deliberately unchanged** (not public-facing): `backend/.env.example` (`EMAIL_USER` is the SMTP *login* -- changing it would break sending), test fixtures using the address as a value, and `docs/PROGRESS.md`/`DECISIONS.md` history. **Watch out:** `docs/tester-pack` still carries the old email AND phone in both footers, so merging it later would reintroduce them. |
| `fix/demo-deal-relative-dates` | `~/dev/projects/abstractly-demo-dates` | — | Pushed (`8e1084f`). Makes the Maple Ridge demo deal's dates relative to generation day (good change: kills the date drift QA_REPORT flagged). **MERGE ATTEMPTED 2026-10-04 AND ABORTED — needs a reconciliation task, not a merge.** `main` was untouched (`0545bec`). 3 conflicts vs `953c00a`, two of them semantic: (1) `expected_findings.json` — main has concession-detection's populated `monthly_dollar_impact` (89.58, 50.0) with hardcoded dates; this branch has computed dates with `monthly_dollar_impact: null`. The combination needs both, and the dollar impacts must be **re-derived for the new dates** (a concession's past/future position changes its classification), then the package regenerated. (2) `test_demo_deal_golden.py` — the two branches chose **opposite strategies for the same test**: main *pins* `today` to the fixture's as-of date to sidestep `expired_but_occupied` drift and asserts **10** findings; this branch *never* pins `today` (regenerates into a temp dir, real wall-clock, plus a freshness test that trips 2026-12-15) and asserts **7**. Someone must pick one strategy and re-derive the assertions for all 10 findings under it. Not resolvable mechanically. (3) `TASKS.md` (take main's). |
| `docs/tester-pack` | `~/dev/projects/abstractly-tester-pack` | +7 / 0 | Overnight run, 2026-10-01: in-app Help & Guides (17 articles incl. Getting Started + troubleshooting), tester emails, 10-Q questionnaire, sales drafts updated (local). Frontend + docs only. Headless-verified at 3 widths. **Read `OVERNIGHT_REPORT.md` on the branch**: 12 product bugs found (report-page T-12 upload broken, T-12 income check never fires, only .csv/.xlsx rent rolls feed the report…). |
| `feature/pricing-page` (round 2) | `~/dev/projects/abstractly-pricing` | +11 | **This is the design that ships** (user's 2026-10-04 decision; `feature/landing-positioning` dropped as superseded). `main` merged in and pushed as **`a50097b`** — zero conflicts, branch still frontend-only (10 files). Suite **78/79** post-merge (only the pre-existing `test_demo_deal_regression.py` bug in #10). Previewed headlessly at 1440/768/375 and looked at: dark page coherent throughout, **every card and text readable** (this branch was designed dark from the ground up — `html { background: var(--lux-black) }` with card tokens redefined to match, unlike landing-positioning which bolted dark onto a light design), new logo renders, WebGL hero bands render, flat pricing correct ($499/$1,250/Contact us), no horizontal overflow at any width. **Merging this also fixes the per-property pricing ($25/$20) currently live on production.** Earlier history: Pushed `157b21d`. Flat per-team pricing ($499/$1,250/Contact us), fluted-glass hero, sticky header, Lenis, new logo. **Reviewed 2026-10-04: security-auditor MERGE (no findings at any severity); reviewer FIX FIRST — all 3 items now fixed.** (1) `4e5f213` duplicated already-merged `b6a46e9` tester routing — logic was byte-identical, resolved by taking **main's** `config.js` (`72bcef8`); the branch no longer touches that file. (2) the held Render billing change `0a0d7a2` reverted (`e06db8e`); `render.yaml` and `docs/DEPLOYMENT.md` are now byte-identical to main. (3) plan written (`docs/plans/feature-pricing-page.md`). Branch is now **frontend-only, 9 files**, merges with **zero conflicts**. Suite 78/79 — the one failure is the pre-existing main bug in #8, reproduced on plain main, not caused by this branch. Screenshots at 1440/768/375 looked at: layout correct, hero renders, prices right. **Two content blockers remain for you, both outside the review's scope — see #9.** |
| `chore/render-persistent-disk` | `~/dev/projects/abstractly-render-disk` | +3 / 0 | **Scope narrowed 2026-10-04 on the user's instruction: `abstractly-api` ONLY.** The tester's `plan: starter` + disk were trimmed out (`6d14c95`); tester and demo both stay `plan: free` with no disk. `main` merged in; pushed as **`95b609f`**, merges clean. Post-merge `render.yaml` verified by parsing: one `disk:` (`abstractly-data`, `/app/data`, 1 GB) and one `plan: starter`, both on `abstractly-api`, with `DB_PATH` correctly under `envVars`. Docs corrected in three places that still assumed two disks — dashboard steps are now prod-only, and the verification procedure no longer says to rehearse on the tester (that service has no disk, so it would prove nothing). Suite **78/79** post-merge; routing test 4/4. The user is attaching the disk on Render themselves. Earlier history: Pushed (`22db0ea`). 1 GB Render disk + `DB_PATH` on `abstractly-api` and `abstractly-tester-api`, both to `plan: starter`; demo stays free by design. Config + docs only, no app code. Extracted from `feature/pricing-page` so that branch can merge frontend-only (billing change shouldn't ride on a CSS refresh). **Needs your Render dashboard actions + billing decision — nothing was changed on Render.** Verified: routing test 4/4; suite 76/77 (see the golden-test note below). Plan: `docs/plans/chore-render-persistent-disk.md`. |
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
6. ~~`research/section8`~~ — **merged** `2fbb542`. The strategic question
   it raises is still open and is yours: the briefing's own finding is
   that for **Housing Choice Voucher** properties the PHA does the
   certification paperwork, not the owner — so the compliance burden
   Abstractly could help with sits with **Project-Based Section 8 and
   LIHTC**, where the owner/agent certifies. Decide whether that's a
   product direction or shelf it; merging the doc didn't decide it.

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

## Done

| Branch | Merged as | Notes |
|---|---|---|
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
