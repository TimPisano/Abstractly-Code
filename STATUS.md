# STATUS — Section 8 launch night (2026-10-13)

Written by the launch session (worktree `claude/abstractly-launch-s8-df198f`).
Times are CDT.

## TL;DR

- **Nothing was merged into `main` and `main` was not pushed by this session.**
  Two reasons, both hard stops in this repo:
  1. Other sessions were **still running**. `feature/s8-unit-file-and-phas` (T9)
     got two new commits and fresh uncommitted edits while I worked (its API
     server was started at 22:46). `feature/s8-sample-data` (T13) ran its test
     suite and made a new local commit. Another session also committed to
     `main` at 22:48 (`4a9fbe9`, TASKS.md only).
  2. The repo guard only allows changes to `main` after **you type
     `/merge-branch <branch>`** in the merging session. The pasted brief didn't
     arm it, and I didn't route around it (CLAUDE.md rule 2).
- **The premise was off:** `qa/overnight-gauntlet`, `fix/section8-tenant-share`
  and `feature/s8-data-model` are **not** on `origin/main` yet.
- **Everything is prepared so merging is mechanical.** A trial merge of all five
  branches, in a scratch worktree (not `main`), applies with two known conflicts
  (below). The full suite on that combined tree: see Part 1.
- **The Section 8 landing copy is ready** on `feature/s8-marketing-copy` (`f205979`,
  pushed). It must merge **after** `fix/section8-tenant-share`.
- **The live site deploys from `main` correctly.** The demo API returned 200
  every minute from 22:53 to 23:10. Its first request took 41.5 s (free-tier
  cold start). The **tester** API was down 22:50–22:58 with Render's
  `no-deploy` page, then recovered on its own.

## Part 1 — Merge status

| Branch | On origin/main? | Tip | Tests | Review | Merge-ready? |
|---|---|---|---|---|---|
| `qa/overnight-gauntlet` | **No** | `906eaab` | 88/88 combined | reviewer + security-auditor MERGE (TASKS) | Yes, merge **1st** |
| `fix/section8-tenant-share` | **No** | `5fa9e5f` | 88/88 combined | reviewer MERGE (TASKS) | Yes, **2nd** |
| `feature/s8-data-model` (T1) | **No** | `b6caf9a` | 88/88 combined | security-auditor MERGE; reviewer FIX FIRST done (TASKS) | Yes, **3rd** |
| `feature/s8-unit-file-and-phas` (T9) | No | `d893c56` (moving) | 88/88 combined | **none yet**; TASKS still says "plan awaiting approval" | **No: still being built** |
| `feature/s8-sample-data` (T13) | No | `9ae1be2` + 1 unpushed local commit | 88/88 combined | **none yet** | **No: still being built** |
| `feature/s8-marketing-copy` (new, this session) | No | `f205979` | 84/84 | reviewer FIX FIRST → fixed (see Part 3) | Yes, **after** `fix/section8-tenant-share` |
| `docs/launch-status` (this file) | No | — | docs only | — | Yes, any time |

**Trial merge** (scratch worktree off `origin/main` `ac9e4c8`, merged in the
order above):
- `qa/overnight-gauntlet`: conflict in `backend/tests/run_all_tests.py` (two
  test files registered at the same spot). Fix: keep both lines.
- `fix/section8-tenant-share`: clean.
- `feature/s8-data-model`: conflicts in `backend/app/database.py` and
  `run_all_tests.py`. **Not a logic conflict.** The gauntlet adds
  `insert_rent_roll_unit_summary` / `get_rent_roll_unit_summaries` and T1 adds
  its Section 8 block at the same place, after `list_ai_extraction_runs`. Git
  interleaves them, so taking either side whole is wrong. The correct
  resolution is the gauntlet's two functions **followed by** T1's whole block.
  I verified it compiles, no function from either side is missing, and nothing
  is defined twice. Also dedupe `test_section8_data_model.py` and
  `test_section8_fixtures.py` in `run_all_tests.py`.
- T9: clean. T13: `run_all_tests.py` list only.

**Tests on the combined tree** (Python 3.9 venv, no `ANTHROPIC_API_KEY`):
- First run: 84/88. The four failures:
  - `test_extraction`, `test_synthetic_accuracy`, `test_multi_lease_detection`
    need the **gitignored** fixture `backend/tests/sample_lease.pdf`. It
    doesn't exist in a fresh worktree; `python backend/tests/create_sample_lease.py`
    makes it. Re-run after generating it: all three pass. This is a
    pre-existing clean-checkout problem, not caused by these branches.
  - `test_access_gate`: T9 added `section8_mode` to `/config`. T9's session
    fixed the test in `d893c56`, pushed after my first trial. Re-merged with
    that tip: passes.
- Second full run on the refreshed tree: **88/88 test files passed** (T9 at `d893c56`, T13 at `9ae1be2`, generated `sample_lease.pdf` present). This verifies the merge chain on a scratch tree, not `main` itself; re-run after the real merges.

**"Production build":** there is no build step (vanilla JS frontend; the
backend is built from `backend/Dockerfile` on Render). Docker isn't installed
on this Mac, so the image was **not** built locally.
`python -m compileall app worker.py` on the combined tree: OK.

**Self-review of the diffs (summary):**
- T1: team-scoped tables and `/section8/*` routes behind `SECTION8_MODE`,
  already audited.
- T13: ships its fixture under `backend/benchmark_data/section8_sample/`,
  which *is* in the Docker image. (`backend/.dockerignore` excludes `tests/`,
  so anything the app reads at runtime from `tests/` would 503 on Render.
  T13 got this right.)
- T9 and T13 have no reviewer/security-auditor verdict yet and are still
  changing, so I'm not calling them ready.

**Rebase decision:** the brief said to rebase T9/T13 with `--rebase-merges`.
Both are already pushed, so a rebase would need a force-push, which you ruled
out. I trial-merged instead (the repo's existing convention, e.g. `e43a813`).

**`SECTION8_MODE` in production:** not declared in `render.yaml` for any
service, and the code that reads it isn't on `main`. So today it has no effect
anywhere: effectively **off**. I can't see the Render dashboard, so if you
ever added it there by hand it's invisible to me. **Left untouched** as
instructed.

## Part 2 — Deploy and the demo API 503

**How getabstractly.com deploys:** `render.yaml` Blueprint, 6 services, no
`branch:` and no `autoDeploy: false`, so every service auto-deploys from
`main`.
- `getabstractly.com` → static `abstractly` (Cloudflare in front; `www` 301s
  to the apex).
- `frontend/config.js` picks the API by hostname.

**Proof a push to `main` deploys:** the live `index.html` on getabstractly.com,
abstractly-demo and abstractly-tester is byte-identical to `origin/main`.
The backends serve `main`'s newer routes (`/public-config`, `/auth/options` →
200 on prod and demo). There's no Render CLI here (`render` not installed) and
no API key, so I couldn't read deploy logs.

**Health check:** `/health` exists and runs `SELECT 1` (503 only if the DB is
broken). Prod and demo both return `{"status":"healthy"}`.

**What I measured** (log of a probe every 60 s, 22:53 → 23:10):

| Service | Result |
|---|---|
| abstractly-api (starter, disk) | 200 every time, ~0.3 s |
| abstractly-demo-api (free) | 200 every time; **first hit 41.5 s** (cold start after 15-min idle spin-down) |
| abstractly-tester-api (free) | **502 `x-render-routing: no-deploy`** from ≤22:50 to 22:58 ("This service is currently unavailable"), then 200. No push to `main` happened then; last push was 2026-10-12 17:37. |

**Most likely causes of the demo 503, in order** (I couldn't confirm any
without the dashboard):
1. **Free-tier restarts and redeploys.** The `no-deploy` 502 on tester is the
   same family. While a free instance is restarting or (re)deploying, Render
   serves an error page. Every push to `main` redeploys all three APIs, and the
   free ones rebuild the full Docker image (tesseract + poppler) each time.
2. **Memory (512 MB on free).** Measured locally: ~120 MB per gunicorn worker
   (×2) plus ~25 MB for the RQ worker, so ~300 MB idle. An OCR job (pdf2image
   rasterising pages) can push past 512 MB. Render then kills the instance and
   it 503s until it restarts.
3. **Free instance hours** (750/month per workspace). If they run out, free
   services are suspended until the 1st.

**Code/config fixes:** none were needed for a confirmed cause, so I made none.
I won't guess at worker counts without seeing a memory event.

**Found in passing (not fixed, out of scope):** `POST /leases/sample` returns
503 "Sample data not available" everywhere, because
`backend/sample_data/sample_lease_fixture.json` was never committed. No page
in the UI calls this route (`api.js` defines it, nothing uses it), so it isn't
your 503. T13 changes this route.

### Click-by-click: what to check in Render (only you can)

1. dashboard.render.com → **abstractly-demo-api** → **Events**. Look for
   "Instance failed … Out of memory (used over 512Mi)", "Deploy failed", or
   "Server unhealthy" at the times you saw 503s.
   - **OOM** → either upgrade the plan (Settings → Instance Type → Starter), or
     tell me and I'll make the gunicorn worker count an env var (default 2)
     so you can set `WEB_CONCURRENCY=1` on demo/tester.
2. Same service → **Logs**, filtered to the 503 time. A Python traceback at
   boot (e.g. a missing env var) shows here.
3. Same service → **Environment**. Confirm `FLASK_SECRET_KEY`,
   `TOKEN_ENCRYPTION_KEY`, `DEMO_RESET_TOKEN`, `REDIS_URL` are set. Note
   whether `SECTION8_MODE` exists, and leave it as is.
4. **abstractly-tester-api** → **Events**. What happened ~22:50–22:58
   tonight? A restart wipes tester's database (no disk).
5. Workspace → **Billing / Usage** → free instance hours left this month.
6. For **each** of the 6 services → **Settings → Build & Deploy**. Auto-Deploy
   = **On Commit**, Branch = **main**. (TASKS notes demo/tester once failed to
   redeploy after a merge and needed **Manual Deploy → Deploy latest commit**.)
7. Still open from TASKS: confirm the prod disk is attached and `DB_PATH`
   is set (`docs/DEPLOYMENT.md` → "Verifying data actually survives a redeploy").

## Part 3 — Section 8 landing copy

Branch `feature/s8-marketing-copy`, worktree `~/dev/projects/abstractly-s8-marketing-copy`,
pushed `f205979`. Built on the approved copy in `PIVOT_PLAN.md` Step 3a
(branch `pivot/section8`).
- **Text and meta only.** The HTML tag skeleton before and after is
  identical: every id, class, href, anchor (`#why-multifamily` kept as the
  id), script and form field. The demo button, `#book-demo`, the demo form
  payload, Client Login and pricing are untouched.
- **Not changed:** `pricing.html`, terms/privacy, brand files, `landing.js`,
  CSS, the hero sample card's numbers and the real sample report (I didn't
  invent new dollar figures).
- **Checks:**
  - Suite **84/84** (after generating `sample_lease.pdf`).
  - Headless screenshots at 1440/768/375, top to bottom, all looked at: no
    horizontal overflow; hero, cards, chips and form all intact.
- **Reviewer:** FIX FIRST twice, both fixed. The copy claimed checks that
  aren't built: comparing actual PHA payments (no branch does that) and
  inspection/recert tracking (built only behind the flag). Final copy:
  - tenant share vs HAP claims match `fix/section8-tenant-share`;
  - the PHA/unit-file features are labelled **"(beta)"**;
  - no claim of reading PHA payments.
- **Merge order matters:** merge only after `qa/overnight-gauntlet` +
  `fix/section8-tenant-share`, or the tenant-share claims are false on the
  live site.

### Before → after (visible copy and meta)

| Where | Before | After |
|---|---|---|
| `title` | Abstractly — Check The Rent Roll Before You Close | Abstractly — Section 8 Lease, HAP & Rent Roll Checks |
| `meta description` | Abstractly reads the leases behind a multifamily rent roll and checks them against it unit by unit before your deal closes, then hands you every mismatch with its dollar impact — ready to export for your lender or LP. Built for mid-size multifamily syndicators. | Abstractly reads your Section 8 leases and HAP contracts and checks them against your rent roll unit by unit — contract rent, tenant share and HAP portion — so units where the numbers don't add up get caught, with every finding cited to the page. Built for Section 8 landlords and property managers. |
| `div` | Now onboarding beta testers. | Now onboarding Section 8 beta testers. |
| `a` | Built For Multifamily | Built For Section 8 |
| `span` | Built for multifamily syndicators | Built for Section 8 landlords and property managers |
| `span` | Check the rent roll | Every HAP dollar, |
| `span` | before you close. | accounted for. |
| `p` | Abstractly reads the actual leases behind a rent roll and checks them against it unit by unit — tenant, rent, dates, escalations — before your deal closes, not after. | Abstractly reads your leases and HAP contracts and checks every voucher unit on your rent roll — contract rent, tenant share, HAP portion — so a unit where the numbers don't add up gets caught this month, not at year-end. |
| `h2` | Rent rolls drift from the leases that back them | Your rent roll drifts from your leases and HAP contracts |
| `p` | Not a hypothetical — here's real output from the reconciliation engine, run against a real test lease and a rent roll built to disagree with it. Same severity, dollar-impact, and source-citation format the product produces on your own documents. | A tenant-share change sits in a caseworker's letter and never reaches the ledger. A PHA keeps paying last year's HAP. Each gap is small; across a few hundred voucher units and several housing authorities, it's real money. Below is real output from the reconciliation engine, run against a test lease and a rent roll built to disagree with it — the same severity, dollar-impact and source-citation format you get on your own documents. |
| `p` | this run happened to be on a commercial unit — the reconciliation itself works the same way on a multifamily rent-roll line: same unit-by-unit match against the lease, same dollar-impact and citation format. | this run happened to be on a commercial unit — the reconciliation works the same way on a Section 8 unit: same unit-by-unit match against the lease, same dollar-impact and citation format. |
| `p` | to see it on your own rent roll. | to see it on your own voucher units. |
| `h2` | Two files in. Every mismatch out. | Your documents in. Every gap out. |
| `h3` | Upload your leases and rent roll | Upload leases, HAP contracts and your rent roll |
| `p` | A Yardi, AppFolio, RealPage, MRI, or Buildium export, a broker's hand-built Excel, a PDF, even a scanned one. No reformatting, no fixed column layout. | Leases, HUD tenancy addenda, HAP contracts and PHA notices as PDFs — even scanned ones — plus your rent roll from Yardi, AppFolio, RealPage, MRI, Buildium or Excel. No reformatting, no fixed column layout. |
| `h3` | See every mismatch, with dollar impact | See tenant share and HAP split, unit by unit |
| `p` | Every lease term — tenant, rent, escalation, expiration — is extracted with the exact page and quote it came from, matched unit by unit against the rent roll, and flagged with what the gap actually costs. | Contract rent is split into the tenant's share and the HAP portion and checked against the lease, the HAP contract and the rent roll. When the two parts don't add up, or the rent roll books the tenant share as the full rent, you see the unit, the page it came from, and what the gap costs. |
| `h3` | Export a report for your lender or LP | Take payment discrepancies to the PHA |
| `p` | Every finding traces back to the lease text, so whoever's underwriting the deal confirms it in seconds instead of re-reading the file — and it's ready to hand off, not just to eyeball. | Every finding traces back to the page it came from, so when a unit's HAP doesn't match what the documents say, you can show the housing authority the exact page — and export the list as a PDF or Excel report. |
| `h2` | Built for hundreds of units, not a handful of tenants | Built for voucher portfolios, not office leases |
| `p` | Most lease-review tools were built for commercial CRE — a handful of long, heavily negotiated leases per building. Multifamily is a different problem entirely. | Most lease tools were built for commercial real estate. Section 8 is a three-party deal — you, the tenant and the housing authority — and every unit's rent comes from two payers. |
| `h3` | Volume, not negotiation | Two payers per unit |
| `p` | A mid-size portfolio can mean hundreds of similar residential leases, not a dozen heavily negotiated commercial ones. A tool built to review 15 anchor tenants a year wasn't built for 300 units. | Tenant share and HAP portion are checked separately, so contract rent has to equal the two added together — and a rent roll that books the tenant share as the whole rent gets flagged. |
| `h3` | Constant turnover | Inspections and recertifications (beta) |
| `p` | Unit leases renew and turn over year-round across a portfolio, not on a handful of scheduled dates. The rent roll drifts from the actual leases continuously — which is exactly why it needs checking before every acquisition. | PHA inspection and annual recertification dates drive what you get paid. A missed reinspection can mean an abatement; a recert that changes the tenant share has to reach the rent roll. A per-unit file that keeps each unit's PHA dates in view is rolling out to beta testers now. |
| `h3` | Built for the closing table | Many housing authorities, one view (beta) |
| `p` | This isn't a tool for an owner managing a handful of tenants over years. It's for the diligence window before you sign — checking what the seller's rent roll claims against what the leases actually say, while you can still walk or reprice. | Every PHA has its own forms, notices and payment schedule. Our beta ties each unit to its housing authority and HAP contract, so you see them side by side instead of in separate portals and spreadsheets. |
| `span` | OCR extraction | OCR for scanned PHA letters |
| `span` | T-12 cross-check | Tenant share / HAP split |
| `span` | Citation-linked validation | Citation-linked findings |
| `p` | Every finding links back to the exact page and quote in the lease it came from — nothing is presented as fact without a way to verify it yourself. | Every finding links back to the exact page and quote in the lease or HAP contract it came from — nothing is presented as fact without a way to verify it yourself. |
| `summary` | What file formats and property management systems do you support? | Which documents and systems do you support? |
| `p` | Today: PDF lease documents, including scanned/image-only PDFs (via OCR), including files that bundle multiple leases into one document, plus hand-built broker Excel/CSV rent rolls and direct import from Yardi, AppFolio, RealPage, MRI, and Buildium exports. | PDF documents — leases and the HAP contracts, tenancy addenda and PHA letters that come with them — including scanned/image-only PDFs (via OCR) and files that bundle several documents into one, plus Excel/CSV rent rolls and direct import from Yardi, AppFolio, RealPage, MRI, and Buildium exports. |
| `summary` | How is this different from an analyst just eyeballing the rent roll for outliers? | We work with several housing authorities. Does that matter? |
| `p` | Outlier flagging against portfolio averages is table stakes, and we do that too. The actual difference is validating against source documents, not just internal statistics — every value we surface traces back to the original lease itself, and cross-checking a rent roll against both the T12 and the underlying lease documents is the real differentiator, not a nice-to-have layered on top. | It's what we're building for. Our beta ties each unit to its housing authority and HAP contract, so documents from different PHAs are kept apart and shown together. We read what the PHAs send you; we never submit anything to a PHA or HUD on your behalf. |
| `summary` | Does this replace my analyst? | Does this replace our property management system? |
| `p` | No. It removes the slowest, most error-prone part of their job — manually retyping and cross-referencing a rent roll line by line — so they spend their time on judgment calls: is this deal worth pursuing, not did I transpose a rent figure correctly. | No. Your PMS records what should happen; Abstractly checks it against the leases and the HAP contracts — so your team spends its time resolving gaps, not retyping a rent roll line by line to find them. |
| `h2` | See it on your own rent roll. | See it on your own voucher units. |
| `label` | Number of Units in Portfolio | Number of Section 8 Units |

(Twitter title/description changed identically to the OG ones.)

## Part 4 — Live verification

**Not run: nothing new was pushed to `main`**, so there was nothing to wait
for. The baseline at 23:10: getabstractly.com 200 (old copy); demo API
`/health` 200; tester API 200. After you merge, the check is:
`curl -s https://getabstractly.com/ | grep -c "Every HAP dollar"` (≥1 = new
copy live) and `curl -s -o /dev/null -w "%{http_code}" https://abstractly-demo-api.onrender.com/health`
(allow ~60 s for a cold start, and a few minutes for the Docker rebuild).

## What you need to do, in order

1. Glance at Part 3's copy; it's your public positioning.
2. In **one** session (only one may merge at a time), type, one per message:
   - `/merge-branch qa/overnight-gauntlet`
   - `/merge-branch fix/section8-tenant-share`
   - `/merge-branch feature/s8-data-model` (resolve `database.py` as described
     in Part 1)
   - `/merge-branch feature/s8-marketing-copy`
   - `/merge-branch docs/launch-status`
   Each merge pushes `main`, which redeploys **all three** services. Merging
   them back to back, then pushing once, avoids three rebuilds of the free
   services.
3. T9 / T13: let their sessions finish, then `/review-branch` each, then
   `/merge-branch`. They're behind `SECTION8_MODE` (off), so they're invisible
   on prod either way.
4. Render dashboard checks above (demo 503, tester outage, auto-deploy).
5. Optional: add `backend/tests/sample_lease.pdf` generation to
   `run_all_tests.py`, so fresh worktrees don't fail 3 tests.

## Decisions log

- Didn't touch `main`: other sessions active; merge approval not typed.
- Didn't rebase T9/T13: pushed branches → would need a force-push (forbidden).
  Trial-merged instead.
- STATUS.md lives on branch `docs/launch-status`, not committed to `main`
  directly (the guard allows only TASKS.md-only commits there).
- Copy keeps the existing hero sample card numbers rather than inventing
  Section 8 figures. The T-12 chip and T-12 FAQ were replaced by Section 8
  content (T-12 cross-check still exists in the product).
- No change to `render.yaml`, env vars, pricing, terms or privacy.
