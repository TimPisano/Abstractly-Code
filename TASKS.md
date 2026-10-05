# TASKS — single source of truth

**The copy that counts is `~/dev/projects/lease-abstraction/TASKS.md`
(primary checkout, on `main`).** Never edit TASKS.md on a feature branch.
Commit changes with `git commit -m "TASKS: …" -- TASKS.md` (the hooks
allow TASKS.md-only commits on main). `/status` reconciles this file with
git; `/session-handoff` writes the handoff blocks; `/resume-task` reads them.

Last reconciled with git: **2026-10-04** (`fix/concession-detection`
rounds 3–4 merged + pushed). `main` @ `f68a287` == `origin/main`.
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
2. **`feature/team-isolation` is ready to merge** (2026-10-04). All review
   findings fixed in `fe520c9` (pushed); reviewer **MERGE**, security-auditor
   **MERGE** on that commit; suite 79/79. Merge it **before**
   `fix/concession-detection` and before rebasing `feature/deal-assistant`
   (see its row for the expected conflicts). Merging needs
   `/merge-branch feature/team-isolation` typed in the merger session.
3. **`feature/pricing-page` r2 would ship the Render billing change you
   asked to hold.** Its tip commit *is* `0a0d7a2` — the persistent disk +
   `plan: free → starter` on `abstractly-api` and `abstractly-tester-api`,
   the same change as `chore/render-persistent-disk`. The TASKS.md note
   claiming that part was "split out" is wrong: it was *copied* out, not
   removed from pricing-page. To merge pricing-page frontend-only, drop or
   revert `0a0d7a2` on the branch first. Also still conflicts in
   `frontend/config.js`, and has no reviewer verdict.
4. ~~`fix/concession-detection`~~ — **fully merged**: rounds 1–2 as
   `953c00a`, rounds 3–4 as `f68a287` (2026-10-04). Both pushed. See Done.
   **It landed first, so `feature/team-isolation` now owes the `team_id`
   test update** — and note rounds 3–4 added 65 more lines to
   `test_concessions.py`, so that update is now slightly larger. team-isolation makes `team_id` a required arg of
   `build_deal_mismatch_report_data` and `insert_lease`; whichever branch
   lands second must update `tests/test_concessions.py` (report/insert
   calls + session `team_id`). That is now team-isolation's job, plus the
   one predicted `test_demo_deal_golden.py` conflict. (An earlier note here
   called the `team_id` test update a no-op — wrong: it referred to
   document-level `team_id` on `main`, not these required args.)
5. ~~GateGuard decision~~ — **done**: tuned in `~/.claude/settings.json`
   (routine-Bash and per-file prompts off; destructive-command check kept).
6. **Pick one fluted-glass hero**: `feature/pricing-page` and
   `feature/landing-positioning` both rewrite the same marketing files.
7. **Render plan upgrade** — you asked (2026-10-04) to hold
   `chore/render-persistent-disk` until you confirm the plan is upgraded.
   Held. Nothing on Render was changed. Same hold applies to pricing-page's
   `0a0d7a2` (#3): `plan: starter` on a non-upgraded account risks a
   failed deploy.
9. **Two content blockers on the pricing page — your call, I didn't touch
   them** (outside what you asked me to fix, but both are customer-facing):
   (a) `pricing.html` carries a visible **"Placeholder launch pricing"**
   banner saying the prices "are not market-tested". It is **already live
   on production** (`main:frontend/pricing.html:71`), not new to the
   branch. CLAUDE.md states $499/$1,250 as the actual pricing, so the page
   currently undercuts its own numbers to every visitor. (b) The branch's
   version of that banner adds a claim that is now **false** — "no
   usage-limits system exists in the product yet" — `feature/usage-limits`
   merged as `ab7fb6f`. Decide whether to drop the banner, or keep it and
   correct the usage-limits clause. Related: the pricing DoD line "no
   placeholder text in the diff" fails until this is settled.
11. **The marketing page makes a security claim that is false on `main`.**
   Under the heading "Trust & Security — What's actually true today",
   `index.html` states **"Isolated per team — Each team's documents and
   results are only visible to that team's members."** That is not true:
   CLAUDE.md records that document tables (`leases`, `discrepancies`,
   `alerts`, `tasks`, …) are **not** team-scoped, so any user on a
   deployment sees every lease on it. `feature/team-isolation` is what
   makes it true, and it is unmerged. The claim is already live on
   production and is carried forward by `feature/pricing-page`. Either
   merge team-isolation before/with pricing-page, or reword the card.
   Spotted 2026-10-04 while reviewing the pricing-page preview.
12. **`chore/contact-email` already exists** (worktree
   `~/dev/projects/abstractly-contact-email`, tip `9171d36`), created by
   another session. It overlaps the requested "change displayed contact
   email to tim@getabstractly.com" work. **Check it before starting that
   task** — do not build a parallel second version (rule 5).
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
| `feature/team-isolation` | `~/dev/projects/abstractly-teams` | +5 / 0 | **Ready to merge.** Pushed `fe520c9`. Re-reviewed 2026-10-04: reviewer MERGE, security-auditor MERGE (every original attack re-run and now fails), suite 79/79 incl. 14 new regression tests in `test_team_isolation_fixes.py` (12 fail on `b75b947`). Fixed: undo-edit cross-team write; field-edit/version-chain helpers require team_id; `/teams` + `/waitlist` owner-only; per-team natural keys (migration) for tenant-concentration alerts and T-12 discrepancies; assignments UNIQUE per team (table rebuild); live sessions re-read user/team per request; owner account protected from team admins; root report moved to `docs/reports/`. **Merge order / conflicts:** before `fix/concession-detection` (1 conflict, `test_demo_deal_golden.py`); `feature/deal-assistant` must rebase after (3 trivial `api.py` conflicts + its session-faking tests need `sync_session_user`); `TASKS.md` conflicts (take main's). **Follow-up (not blocking):** bind tokens to the user's email so an old token can't act as a different user after a deploy-time DB wipe (`auth._live_user`). |
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
- **No document-level team isolation on main** — fine while each firm has
  its own deployment; blocks multiple firms per deployment until
  `feature/team-isolation` lands.

## Up next

1. ~~Push local `main`~~ — done (`f68a287`).
2. **Merge train.** Each needs the user to type `/merge-branch <branch>`
   — **the slash form specifically**: prose like "approve merge X" arms
   the lock but records `branch: ""`, and the merge-branch skill is
   `disable-model-invocation`, so it cannot be run any other way.
   Approved by the user 2026-10-04 and queued next, both verified to
   merge **clean** against `f68a287`:
   `research/section8` → `chore/render-persistent-disk`.
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
6. `research/section8` (`2050414`, pushed) — Section 8 / LIHTC market
   research by another session, docs only. Decide whether it's a product
   direction or shelf it.

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
