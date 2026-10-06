# Abstractly — Production Readiness Audit

**Date:** 2026-10-05 (overnight run) · **Code audited:** `origin/main` @ `3f1d3aa` (worktree `~/dev/projects/abstractly-audit`, branch `audit/production-readiness`, nothing committed)
**Method:** read-only. No code changed, nothing committed or pushed, no Render service or live URL touched, no real Anthropic calls. Local experiments ran against throwaway SQLite files in the session scratchpad.
**Test suite at audit time:** `python backend/tests/run_all_tests.py` in this clean worktree (with `sample_lease.pdf` copied in, no `.env`) → **82/82 test files passed**.

How to read the evidence tags:
- **CONFIRMED**: I (or a subagent whose output I re-checked) ran something and saw the failure. The command or output is quoted.
- **READ**: established by reading the code at the cited lines, not executed.
- **UNVERIFIED**: depends on something outside the repo (Render dashboard, Anthropic account terms, legal), so I can't check it from here.

Subagents produced first drafts of several sections. **Every finding below was re-checked against the code by me.** Claims that failed that check were dropped; they're listed in the appendix so nobody re-raises them.

---

## Summary

Abstractly is in better shape than most products at this stage in some places. Every route carries `@require_role` and is team-scoped. There's a CSRF origin check, HSTS/CSP headers, bcrypt, short-lived bearer tokens, password-reset tokens that are one-time-use, and 82 green test files. The parts customers can see are mostly right.

**The core product is partly broken right now:**

1. **The T-12 cross-check is broken in four separate ways** (CONFIRMED, §6.1):
   - The report page never sends `property_address`, so a T-12 upload from the UI always returns 400.
   - The income check compares a *monthly* rent sum to an *annual* T-12 figure, so it can never fire. A $600k/yr shortfall produced 0 findings.
   - Vacant rows are dropped on import, so the rent roll always looks 100 % occupied. The occupancy check therefore flags nearly every deal, even when the T-12 and rent roll agree.
   - The bad-debt trend analyses calendar Oct–Dec instead of the latest three months.
2. **The report invents or hides money on ordinary lease files** (CONFIRMED, §6.11):
   - When a unit's folder holds both the expired original lease and the current renewal, the rent roll is compared against both. A correct unit gets ~$28,800/yr of false overstatement ($3,600 rent mismatch + $25,200 expired-but-occupied).
   - A rent roll that says "Unit 101" or "Oak St" never pairs with a lease that says "Apt 101" or "Oak Street", so real rent gaps vanish into unpriced "no lease" rows.
   - A scheduled step-up is ignored, so a correct rent roll gets flagged.
   - "First month 50 % off" is priced as 12 months of discount.
   - Re-importing a seller's updated rent roll doubles every unit.
   - The regex extractor (which testers use today, with no API key) finds rent in only 5 of 12 everyday phrasings, and a lease with no rent is silently unchecked. (§6.16, §6.17)
3. **Some inputs are silently lost.**
   - A CSV rent roll with ISO dates (`2024-12-31`) loses every lease date with no warning.
   - Comma-decimal rents (`1250,00`) are read 100× too high.
   - OCR-garbled rents drop out of totals.

   (§6.2, §6.5, §6.10)
4. **The advertised limits don't hold.**
   - The 150-page cap is skipped for every PDF.
   - A long scanned PDF is rasterized all at once at 200 dpi inside the web request: OOM or a 120 s timeout on a 512 MB instance.
   - Tiny .docx "bombs" expand to hundreds of MB.
   - Upload size is 16 MB in Flask but 25 MB everywhere else.

   (CONFIRMED, §3.1, §2.2)

**The detector arithmetic itself is sound.** On a clean one-lease-per-unit deal, the rent mismatch, expired-but-occupied, concession and missing-lease detectors reproduce the Maple Ridge golden deal exactly ($45,355/yr, 10/10). **Team isolation held up** under a ~130-request cross-team attack (§2.1).

**The data layer isn't production grade yet.** Prod is one SQLite file on a 1 GB Render disk. There's no backup in the repo and no restore drill. It runs in default rollback-journal mode with a 5-second lock timeout, and three processes write to it (2 gunicorn workers + the RQ worker). It's fine for a handful of beta testers and not for paying customers' deal data. §1 has the short-term hardening and a step-by-step Postgres plan.

**Background extraction has failure modes nobody sees.** A Redis hiccup returns a 500 after the leases are already inserted, so they sit in "processing" forever. Any gunicorn worker restart marks *every* in-flight lease, across all teams, as "failed, delete and re-upload". The job then quietly flips it back to complete (CONFIRMED). If the AI call fails, extraction falls back to regex without telling the user.

**Cost is not a risk at current prices; metering is.** One typical lease costs about **$0.03–0.08** in Claude Sonnet 5 tokens. A 200-unit deal is about **$11–17** all-in, which is roughly **2–5 % of a Starter subscription** (§4). But the metering behind quotas and budget alerts is broken. Pages and dollars are never recorded for the main (async) upload path, so the page quota and the $ budget alert are dead code. The default 200-documents-a-month quota would also stop a customer partway through a single 250-unit deal.

**Section 8 / tenant PII: not ready.** Before a PBRA/LIHTC owner uploads tenant files, Abstractly needs four things: a zero-data-retention or DPA arrangement with Anthropic, encryption at rest, SSN/DOB redaction, and published privacy/terms/subprocessor documents. Most of it is paperwork plus about 1–2 weeks of engineering (§5).

**Dependencies:** 32 known advisories across 8 pinned packages. Pillow 11.3 has 18 of them, including out-of-bounds writes. Those are reachable because uploaded images are decoded by content, not by extension (CONFIRMED, §2.4).

### Ranked top 10 fixes

Ranked by (likelihood × damage) for the next 60 days: beta testers now, first paying syndicators soon after. Estimates are focused engineering time for one person, including the regression test CLAUDE.md requires.

| # | Fix | Why it's ranked here | Est. |
|---|---|---|---|
| 1 | **Make the Deal Mismatch Report trustworthy on real lease files** (§6.1, §6.11): compare each rent-roll unit only against its *operative* lease (latest or current term), not every lease on file, and auto-link renewals; build one canonical address key (unit labels `Unit 101`/`Apt 101`/`#101`, street suffixes `St`/`Street`, property-name prefixes) used for both pairing and property scoping; make a rent-roll re-import replace the previous one instead of doubling units; repair the T-12 cross-check (send or derive `property_address`, annualize per building, import vacant rows so occupancy is real, order T-12 months by period). Add golden fixtures for a renewal chain, mixed unit labels, and an Oct–Sep T-12 with a planted gap. | It's the product. Today a normal lease folder (original + renewal) adds ~$29k/yr of phantom overstatement per renewed unit; "St" vs "Street" and "Unit" vs "Apt" hide real gaps; a seller's updated rent roll doubles every unit; and the T-12 pillar is silent or cries wolf. | 3.5–4.5 days |
| 2 | **One upload gate for every route** (§3.1, §2.2 H2/H3): count PDF pages with `pypdf`; reject zip bombs (size/ratio) and huge images (`MAX_IMAGE_PIXELS`, catch the error); align the 16 MB/25 MB limit; OCR page by page at 150 dpi inside the RQ job, not the request; apply the same gate and usage logging to `/leases/batch`, rent-roll, T-12 and AI-validation routes; `/extract` → analyst. | Today one small file from any logged-in user can OOM-kill prod, which also kills the extraction worker. | 1.5–2 days |
| 3 | **Back up the prod DB, and prove you can restore it** (§1.2): nightly `sqlite3` online backup to off-Render object storage, 14-day retention, failure alert, one restore drill; confirm in the dashboard whether Render snapshots this disk. | A bad migration, disk-full event or fat-fingered delete is unrecoverable today. | 0.5–1 day |
| 4 | **SQLite hardening while it lives** (§1.4): `journal_mode=WAL`, `timeout=30`, `synchronous=NORMAL`, `UNIQUE(team_id, content_hash)`, disk-usage alert at 70 %. | Three writer processes on a rollback journal turn concurrent work into "database is locked" 500s. ~10 lines that buy months. | 0.5 day |
| 5 | **Make background extraction honest** (§3.2–3.5): guard `enqueue` (mark leases failed + 503); store `job_id` and only fail leases whose job is dead; move the orphan sweep from import time to a reaper; supervise the worker; `/health` checks Redis and worker heartbeat. | A worker restart currently tells every team's in-flight leases to "delete and upload again", and the job then revives them. Redis blips strand leases and charge quota. | 1–1.5 days |
| 6 | **Session integrity** (§2.2 H1, M5): `instance_id` + `token_version` in tokens and sessions; logout, password change and reset revoke old tokens; reset tokens carry a `purpose`. | On tester/demo, after any restart, a previous user's token silently becomes *another* user's account. | 2–3 h |
| 7 | **Patch dependencies** (§2.4): Pillow ≥ 12.3, pypdf ≥ 6.19, pdfminer.six ≥ 20251230, pillow-heif ≥ 1.3, Flask ≥ 3.1.3, Werkzeug ≥ 3.1.9, requests ≥ 2.33, python-dotenv ≥ 1.2.2; `Image.open(..., formats=[...])`; non-root container user. | Known memory-corruption bugs sit in the code path that parses customer uploads, and are reachable (format sniffed from content). | 0.5 day |
| 8 | **Stop silently losing data** (§6.2, §6.5, §6.16, §3.6): regex rent patterns cover everyday residential wording (5/12 today); never store "per annum" as monthly; "first month X % off" = one month; a **"rent not found" finding** so blind spots show; ISO dates in `parse_date`; flag unparseable money and dates in import/extraction responses; persist and show the extraction engine (AI vs. regex fallback), truncation, and `max_tokens` stops; surface a failed post-import reconciliation. | The product's promise is "catch it before close". Silently missing a date or rent is the failure customers won't forgive. | 2–2.5 days |
| 9 | **Repair metering and quotas** (§4.3, §6.4): log pages and tokens from the RQ job; price constants $3/$15 → $2/$10; per-plan document quotas (200 docs/month blocks a single 250-unit deal); count per lease, not per file; don't charge `ocr_needed` or dedup hits; team-level assistant cap. | Without it there's no spend control, and real customers get blocked mid-deal. | 1 day |
| 10 | **Quick-win hardening bundle** (§2.2): CSV/XLSX formula-injection guard; ReportLab escaping in `summary_memo.py`; return real codes for `HTTPException` (stops 405→500 + alert emails); reject >72-byte passwords before consuming the token; `ProxyFix` so rate limits aren't one global bucket. | Each is small and confirmed. Together they remove the easiest ways an outsider or a hostile seller document can break things. | 3–4 h |

**Totals:** about 13–16 focused days for the top 10.

**Before inviting testers with real deals (parallel to the top 10):** build a 20–30-lease **real, redacted multifamily** accuracy corpus with ground truth (§6.14, 2–3 days). Nothing today measures extraction on the documents customers will actually upload.

**Right after the top 10:** the Postgres migration (§1.6, about 1.5–3 weeks), then the Section 8 bundle (§5, about 2 weeks engineering plus legal). Neither is needed for the first 3 beta testers. Both are needed before a paying customer's real deal data lives only on our infrastructure.

---

## 1. Database

### 1.1 What's actually deployed (READ, `render.yaml`, `backend/start.sh`, `backend/app/database.py:57-61`)

- **Prod** (`abstractly-api`, plan `starter`): SQLite at `DB_PATH=/app/data/lease_portfolio.db` on a 1 GB Render disk (`abstractly-data`). **Tester and demo have no disk**, so they lose everything on every deploy, restart, and free-tier spindown. CLAUDE.md still says "No Render service has a persistent disk". That's stale since `92013f7`.
- Whether the disk is really mounted and used in prod is **UNVERIFIED** (TASKS.md "Waiting on you" #7 still stands).
- `start.sh` runs `python worker.py &` and `gunicorn --workers 2`. That's **three OS processes writing one SQLite file**.
- `get_connection()` is `sqlite3.connect(_db_path)` + `row_factory` + `PRAGMA foreign_keys = ON`. There's no `journal_mode`, no explicit `timeout`, and no `busy_timeout`. So the defaults apply: **rollback journal (DELETE mode) and Python's 5.0 s lock wait**.
- Schema is managed by `CREATE TABLE IF NOT EXISTS` plus hand-written `_migrate_*` functions run at import time. There's no version table, so it isn't obvious which migrations a given file has had.

### 1.2 Backup: none (READ / UNVERIFIED)
- Nothing in the repo copies, snapshots, or exports the database. There's no documented restore procedure.
- Render's paid disks are described as getting automatic snapshots. **I can't verify that from the repo** for this service, or how long they're kept. Check the dashboard's Disk tab, and write down the RPO in `docs/OPERATIONS.md`.
- Copying a live SQLite file with `cp` while a writer is active can produce a corrupt copy. Use `sqlite3 .backup` / `conn.backup()`, which is safe online.
- **Recommendation (top-10 #3):** a nightly job (an RQ scheduled job, or a Render cron job reading the same disk; a cron job is a separate service and **can't** mount the disk, so run it in-container) that does `src.backup(dst)`, gzips the result, uploads it to object storage with 14-day retention, and alerts on failure. Then do one restore drill into the tester service.

### 1.3 Corruption risk
- **Disk full (1 GB):** SQLite returns `SQLITE_FULL` and the transaction rolls back. Data loss is unlikely; failed writes are certain. Growth is moderate: no document files are stored, but `extracted_fields` JSON, `activity_log`, `usage_events`, `lease_field_edits`, `ai_extraction_runs`, assistant conversations and discrepancy history all grow without limit. There's no monitoring. Add a disk-usage line to `/health` or a daily log line, and alert at 70 %.
- **Kill during deploy:** disk-backed services stop the old instance before starting the new one. With a rollback journal, SQLite recovers a hot journal on next open, so this is safe as long as the journal file sits next to the DB on the same disk, which it does.
- **No WAL:** readers block writers and writers block everyone for the length of the write transaction.

### 1.4 Concurrency risk
- Three writers, a 5 s wait, then `sqlite3.OperationalError: database is locked`. That's a 500 to the user. The likely triggers are a multi-lease upload being finalized by the worker while another user uploads, plus the import-time `fail_orphaned_processing_leases()` UPDATE (§3.4) running inside every new gunicorn worker. Likelihood at 3 testers: low. At 20 concurrent analysts in one deal room: real. (READ; not reproduced under load.)
- **Check-then-insert races** (READ):
  - Upload dedup: `find_duplicate_upload` → extract → `UPDATE leases SET content_hash` (`api.py:1061-1090`) has no unique constraint. Two simultaneous uploads of the same file both extract and both bill.
  - Quota: `check_team_quota` counts, then a later insert. Concurrent uploads can overshoot by the number in flight. That's low impact.
- WAL plus `timeout=30` removes most lock failures. A `UNIQUE(team_id, content_hash)` index (partial, `WHERE content_hash IS NOT NULL`) removes the dedup race.

### 1.5 Schema notes (READ)
- Money is stored as TEXT inside the `extracted_fields` JSON (for example `"$1,250.00"`) and parsed at read time by `normalize.parse_currency`. A value that doesn't parse (OCR `"$1,2OO.00"`) returns `None` and **drops out of every total silently** (`normalize.py:133-135`). See §6.
- Owner-console revenue/expense amounts are REAL (floats). That's acceptable for internal bookkeeping; use `NUMERIC` in Postgres.
- Dates are ISO TEXT. That's fine. Month bucketing uses `strftime('%Y-%m', created_at)` on UTC ISO strings, which is correct.

### 1.6 Step-by-step migration to Render Postgres

Scope found in code (counted by the DB subagent and spot-checked): about 1,120 `?` placeholders, 27 `AUTOINCREMENT`, 20 `PRAGMA`, 17 `lastrowid`, 16 `strftime(...)`, 5 `COLLATE NOCASE`, `INSERT OR IGNORE/REPLACE`, `sqlite3.Row`, `sqlite3.IntegrityError` catches. Almost all of it is in `database.py`; a few modules (`usage_limits.py`, `api.py:1083-1090`, tests) open connections directly.

| Step | What | Est. |
|---|---|---|
| 0 | **Before anything else**, do §1.2 backups and §1.4 WAL/timeout. They protect the data you migrate from. | (top-10) |
| 1 | **One DB seam.** Route *every* connection through `database.get_connection()`, including the stray `usage_limits.py` and `api.py` raw connections and tests. Add a tiny adapter that exposes `execute()`, `fetchone/all()`, `lastrowid`-equivalent, and translates `?`→`%s`. Use **psycopg 3** with a `dict_row` factory to mimic `sqlite3.Row`. Not SQLAlchemy ORM; Core is optional later. | 2–3 days |
| 2 | **Dialect differences:** `AUTOINCREMENT` → `GENERATED BY DEFAULT AS IDENTITY`; `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`; `INSERT OR REPLACE` → `ON CONFLICT (...) DO UPDATE`; `lastrowid` → `RETURNING id`; `strftime('%Y-%m', x)` → `to_char(x::timestamptz,'YYYY-MM')` (or store `timestamptz`); `COLLATE NOCASE` → `lower()` or `citext`; remove PRAGMAs; `IntegrityError` → `psycopg.errors.UniqueViolation`; JSON columns → `jsonb`; booleans 0/1 → `boolean`. | 3–4 days |
| 3 | **Migrations as numbered SQL files** (`backend/migrations/0001_init.sql` …) applied by a ~50-line runner with a `schema_migrations` table. Replace the import-time `_migrate_*` functions. Alembic is fine too, but overkill for raw SQL. | 1 day |
| 4 | **Dual-backend test run:** parametrize the test harness on `DATABASE_URL`, run all 82 files against both SQLite and a local Postgres (Docker) until green. | 2–3 days |
| 5 | **Render infra:** create a Render Postgres instance in the same region (check Render's current pricing; the entry paid tier is what you want for backups and PITR). Add `DATABASE_URL` from the dashboard, not `render.yaml` (`sync: false`). Deploy with a flag `DB_BACKEND=sqlite` still on. | 0.5 day |
| 6 | **Copy script:** read every table from the SQLite backup, write to Postgres in FK order, preserve ids, then reset identity sequences (`setval`). Verify row counts and checksums per table. Rehearse on the tester DB first. | 1 day |
| 7 | **Cutover:** announce a window, enable maintenance mode (a 503 on writes), take the final SQLite backup, run the copy, flip `DB_BACKEND=postgres`, smoke test (login, upload, rent roll, report, exports), lift maintenance. **Rollback** = flip the flag back; the SQLite file is untouched. | 2–4 h |
| 8 | **Afterwards:** move the RQ worker to its own Render background-worker service (no shared disk needed any more), allow >1 web instance, drop the disk, give tester its own Postgres database so it stops losing data. | 1 day |

**Total: about 1.5–3 weeks** of focused work. The payoff: real backups/PITR, no lock errors, a separate scalable worker, and a tester environment that keeps data.

---

## 2. Security

### 2.1 Team isolation — **no cross-team leak found** (CONFIRMED)
CLAUDE.md's Tenancy paragraph is stale: `feature/team-isolation` (`3cff20b`) is on main.

**Routes.** All 163 `@app.route` handlers were enumerated by script.
- Every document-touching route has `@require_role(...)`.
- Every `/owner/*`, `/teams*` and `GET /waitlist` route has `@require_owner()`.
- The only undecorated routes are the intentionally public ones: auth flows, OAuth callback, waitlist/demo-request, `/public-config`, `/analytics/pageview`, `/health`, `/config`, and `/demo/reset` (token-gated, 404 unless `DEMO_MODE`).

**Queries.** Every by-id getter in `database.py` takes `team_id` and filters on it, and `current_team_id()` is re-read from the DB on each request. These are scoped too:
- cache keys
- discrepancy and alert natural keys
- assistant context
- the RQ job
- every export

**Live test.** A two-team matrix ran about 130 requests as Team A's admin using Team B's real ids (security subagent, `scratchpad/audit/idor.py`).
- By-id reads, writes and deletes all returned 404.
- Bulk endpoints reported B's ids as `not_found` and changed nothing.
- List and aggregate endpoints contained none of B's data.
- Body-supplied `team_id` / `is_owner` were ignored.
- Analyst/viewer self-promotion returned 403.
- I re-ran the roles part (`misc.py`):
  ```
  viewer PATCH self role: 403 · analyst PATCH self role: 403 · admin patch is_owner/team_id: 200 {'is_owner': 0, 'team_id': 2} · admin /owner/teams: 404
  ```

### 2.2 Findings

| Sev | Finding | Evidence | Fix · est. |
|---|---|---|---|
| **HIGH** | **A stale token becomes a different user after a DB wipe.** `auth._live_user` trusts only the `user_id` inside a signed bearer token/cookie (`auth.py:100-159`). Tester and demo wipe their DB on every restart, but `FLASK_SECRET_KEY` survives, so a 12 h token issued before the wipe resolves to whoever now has that id. A previous tester can read/write the next tester's team. | CONFIRMED (re-run): `old token now acts as: 200 {'email': 'owner@seed.t', 'role': 'admin', 'team_id': 2}` · `team/members w/ old token: 200 ['owner@seed.t', 'victim@newcustomer.t']` | Random `instance_id` in a `meta` table, embedded in token and session and checked; also compare the token's email to the row's. Fold in a `token_version` (see M5). ~1.5 h |
| **HIGH** | **Document bombs.** There's no zip-ratio check on .docx/.xlsx. A 50 KB .docx expanding to 20 MB took 28 s and about 390 MB RSS in python-docx; a few hundred KB would OOM the container (which also hosts the worker). `Image.MAX_IMAGE_PIXELS` is left at the default (179 M px is the hard error), and `DecompressionBombError` isn't caught, so it surfaces as a generic 500. `/extract` is open to **viewer** role. | CONFIRMED (security subagent, `bombs.py`); the extrapolation to OOM was not run | Before parsing, cap total uncompressed size at ~50 MB and ratio at ~100:1; set `MAX_IMAGE_PIXELS≈25M` and catch the error; cap sheet/row counts; `/extract` → analyst. ~2 h |
| **HIGH** | **Limits don't bind** (see also §3.1, §4.3). The PDF page cap is dead code. Quota and rate-limit checks live in `_validate_upload`, but `POST /leases/batch`, `/leases/import-rent-roll`, `/portfolio/t12-reconciliation`, the deal-mismatch `t12_file`, and `/portfolio/rent-roll-ai-validation` (one model call per pair, no rate limit, no usage log) all bypass it. `/extract` checks the quota but never logs usage. | CONFIRMED (`viewer /extract: 200`; page-cap repro in §3.1) | One `check_upload_limits()` used by every upload/AI route, logging pages and tokens. ~2 h |
| MED | **Rate limits keyed on the proxy's IP.** Limiters use `request.remote_addr` (`api.py:1997, 2215, 2260, 2293, 3493, 3553, 3649`) and there's no `ProxyFix`. Behind Render's proxy all clients likely share one bucket, so one script can lock out *all* logins (20 per 5 min), all password resets (3/h), and the Book-a-Demo form (8/min), which is the sales funnel. The limiters are also in-memory per gunicorn worker. | READ; verify on tester by logging `remote_addr` once | `ProxyFix(x_for=1)`; later move counters to Redis. 30 min |
| MED | **Targeted lockout.** The per-email login limiter (7 per 15 min) counts attempts for any email, including the owner's. Anyone can keep a known account locked indefinitely. | READ `api.py:2000-2004` | Key on email+IP, add backoff. 1 h |
| MED | **CSV/Excel formula injection** in `/discrepancies/export.csv`, `/alerts/export.csv` (`api.py:4575-4590, 4728-4745`), `rent_roll_export.py` (CSV and XLSX; openpyxl stores `=…` as a formula cell) and likely `deal_mismatch_export.py`. The content comes from the *seller's* documents, and these files go to lenders and LPs. | CONFIRMED (tenant `=HYPERLINK(...)` written as a live formula) | Prefix `'` to strings starting `= + - @ \t \r`. 45 min |
| MED | **ReportLab markup injection** in `summary_memo.py` (`Paragraph(...)` with raw tenant and field text). A tenant named `Acme <b>unclosed` makes `/leases/<id>/summary.pdf`, `/portfolio/summary.pdf` and `/portfolio/monthly-report.pdf` 500 for the whole team until that lease is deleted. `<img src="file:///…">` makes the server open local files, and remote fetches are possible (untested). `deal_mismatch_export.py` already escapes. | CONFIRMED (security subagent) | `xml.sax.saxutils.escape()` every value. 30 min |
| MED | **Reset tokens: wrong purpose, no session revocation.** A 3-day-old *forgot-password* token (meant to live 1 h) still works at `/auth/team-setup`, which allows 7 days. Changing or resetting a password doesn't invalidate existing tokens, and logout only clears the cookie, so the bearer token stays valid. | CONFIRMED (re-run): `3-day-old reset token at /auth/team-setup: 200` · `old token after pw change: 200` · `after logout token still valid: True` | `purpose` column on reset tokens; `users.token_version` checked in `_live_user`. 1 h |
| MED | **Every HTTP error becomes a 500.** The global `@app.errorhandler(Exception)` catches werkzeug `HTTPException`s, so `GET /auth/login` (a 405) returns 500 and logs an ERROR with a traceback. Prod has `ERROR_ALERT_EMAILS=true`, so an anonymous scanner generates operator alert emails. | CONFIRMED: `GET /auth/login -> 500 {"error":"Internal server error"}` | Return `e` for `HTTPException` first. 15 min |
| MED | **Passwords over 72 bytes → 500 and a burned reset token.** bcrypt 5 raises on >72 bytes. | CONFIRMED: `reset w/ 80-byte password: 500 ; token reuse now: 400` | Validate length before consuming the token. 15 min |
| MED | **Google Sheets export shares "anyone with the link"** (`sheets_export.py:213-215`). It's off unless `GOOGLE_APPLICATION_CREDENTIALS` is set. | READ | Keep it off, or share with named emails only. |
| MED | **Demo deployment publishes credentials** (`demo_seed.py:39-41`), and the analyst login reaches `/extract`, `/leases` and `/assistant/ask`. If an Anthropic key is ever set on demo, anyone can spend it. | READ | Never set `ANTHROPIC_API_KEY` on demo, or gate AI in `DEMO_MODE`. |
| LOW | The OAuth callback reflects `error` into HTML (CSP blocks scripts, so it's HTML injection only). `/waitlist/check` is an unauthenticated email-enumeration oracle. Some GET routes write derived rows at viewer role. The session cookie is `SameSite=None`. The bearer token lives in `sessionStorage`, so it's XSS-exposed (no XSS found). `request.path` is logged unescaped. RQ payloads (page text) go to an Upstash instance shared by prod/tester/demo, and a deployment that forgets `LEASE_EXTRACTION_QUEUE` would consume **prod's** queue against its own DB. `.env.example` contains the operator's real Gmail address. | READ / CONFIRMED (callback reflect) | Small individual fixes. ~2 h total |

### 2.3 Checked and clean
- **Passwords and accounts:** bcrypt with timing equalisation on unknown users; no user enumeration on login or forgot-password.
- **Session cookie:** `Secure` + `HttpOnly`.
- **Tokens:** bearer tokens are signed with their own salt and expire after 12 h. Reset tokens are 256-bit, stored hashed, and single-use.
- **Roles:** an admin can't make themselves owner; `is_owner` is set only by `set_owner.py`. Deactivation takes effect immediately (`deactivated viewer token: 401`).
- **CSRF and CORS:** CSRF is an Origin/Referer allow-list (`evil origin → 403`, `null → 403`), and an evil-origin preflight gets no ACAO.
- **Secrets:** no hardcoded secrets; the git history scan was clean; `TOKEN_ENCRYPTION_KEY` has no insecure fallback.
- **SQL:** f-string SQL interpolates only constants and placeholders.
- **XSS:** the frontend consistently escapes server text.
- **Prompt injection:** the assistant uses one forced-tool call with team-scoped context and validated navigation ids, so a poisoned lease can only skew answers within its own team.
- **Headers and errors:** API security headers are present, and errors return generic JSON.
- **Uploads:** upload filenames can't traverse paths; temp files are unlinked.

### 2.4 Dependency vulnerabilities (CONFIRMED: `uvx pip-audit -r backend/requirements.txt`, 2026-10-05)

| Package | Pinned | Advisories | Fixed in | Reachable? |
|---|---|---|---|---|
| **Pillow** | 11.3.0 | 18 (incl. PSD out-of-bounds write CVE-2026-25990, CVE-2026-42311 memory corruption, JPEG2000/TGA/raw-codec heap overflows, FITS/PDF decompression DoS) | 12.3.0 | **Yes.** `document_extractor._extract_image` and `rent_roll_table_extract` call `Image.open()` with no `formats=` restriction, so content is sniffed. CONFIRMED: a TGA file uploaded as `lease.png` decodes as `format: TGA`. |
| **pypdf** | 6.16.2 | 8 (crafted-PDF CPU and memory DoS) | 6.19.0 | **Yes.** Every PDF upload. |
| pdfminer.six (via pdfplumber) | 20251107 | 1 (CVE-2025-70559) | 20251230 | Yes, rent-roll PDF tables. |
| pillow-heif | 1.1.1 | 1 (CVE-2026-28231) | 1.3.0 | Yes, HEIC rent-roll photos. |
| Flask | 3.0.0 | 1 (missing `Vary: Cookie`, CVE-2026-27205) | 3.1.3 | Low: the API sends JSON, but cookie-session responses could be cached by a shared proxy. |
| Werkzeug | 3.1.8 | 1 (`safe_join` Windows device names) | 3.1.9 | No (Linux). |
| requests | 2.32.5 | 1 (`extract_zipped_paths` temp file) | 2.33.0 | Unlikely. |
| python-dotenv | 1.2.1 | 1 (symlink follow in `set_key`) | 1.2.2 | No (only reads). |

Also: the Docker image runs as **root** (no `USER` in `backend/Dockerfile`), and `apt` packages (tesseract, poppler) aren't pinned. The frontend has one vendored library (`frontend/vendor/lenis.min.js`) and no npm dependencies.

---

## 3. Reliability

### 3.1 CRITICAL — the 150-page limit is never enforced for PDFs, and OCR rasterizes the whole file in-request (CONFIRMED)
- `usage_limits.check_file_limits` counts PDF pages by calling `document_extractor.extract_pages(file_bytes, filename, None)` (`usage_limits.py:104-115`). `_extract_pdf` then does `open(temp_path)` with `temp_path=None`, which raises `TypeError`. The bare `except Exception: pass` swallows it. **Every PDF passes the page check.**
  ```
  160-page PDF check_file_limits -> None     # limit is 150
  ```
- The upload route then extracts pages **inside the web request** (`api.py:557`, temp file then `extract_pages`). If the text layer is thin, `PDFExtractor._extract_with_ocr` calls `convert_from_path(pdf_path)` (`pdf_extractor.py:126`) with **no `dpi`, `first_page` or `last_page`**. pdf2image's default is 200 dpi, and it rasterizes **every page into memory at once**. One US-letter page at 200 dpi RGB is about 1700×2200×3 ≈ 11 MB, so **150 pages ≈ 1.6 GB** against Render starter's 512 MB.
- Measured OCR speed is about 0.9 s per page locally (reliability subagent, tesseract 5). So even when memory survives, about 130+ scanned pages exceeds gunicorn's `--timeout 120`. The worker is SIGKILLed, the user gets a 502, and see §3.4 for what the replacement worker then does.
- The `except Exception: return []` in `_extract_with_ocr` (`pdf_extractor.py:139-142`) also turns "OCR crashed" into "no text", which the pipeline reports as `ocr_needed`.
- **Fix:** top-10 #2.

### 3.2 HIGH — Redis failure after leases are inserted (READ)
`POST /leases` inserts the leases in `processing`, logs usage, *then* calls `jobs.extraction_queue.enqueue(...)` with no try/except (`api.py:980-984`). If Redis is unreachable (Upstash outage, `REDIS_URL` unset, which makes `jobs.py:33` default to `redis://localhost:6379`), the request 500s. The leases stay `processing` until the next process boot, and the user has already been charged one document of quota. **Fix:** catch it, mark those leases failed with a clear message, return 503.

### 3.3 HIGH — the worker isn't supervised; `/health` doesn't know (READ)
`start.sh` backgrounds `worker.py` with no restart (its own comment admits it). If it dies (OOM from §3.1 is the likely cause), every later upload sits `processing` while `/health` (`api.py:5624`, DB `SELECT 1` only) keeps reporting healthy, so Render never restarts the container. **Fix:** supervise both processes (e.g. a 15-line Python supervisor, or `honcho`/`supervisord`), and have `/health` ping Redis and check worker heartbeat keys (`rq.Worker.all()`).

### 3.4 HIGH — any gunicorn worker boot marks every in-flight lease, across all teams, as failed (CONFIRMED)
`api.py:270` runs `database.fail_orphaned_processing_leases()` at **module import**. That UPDATE (`database.py:1195-1213`) sets every `processing` lease in the database to `failed` with "Processing was interrupted by a server restart. Delete this and upload again." Gunicorn imports the app once per worker, and replaces a worker whenever one is killed by the 120 s timeout (§3.1), dies, or restarts. Reproduced with two processes against one DB file:
```
before: [(1, 'processing')]
after a 2nd process imports app.api: [(1, 'failed', 'Processing was interrupted by a server restart. Delete this and upload again.')]
```
Meanwhile the RQ job carries on and `finalize_lease_processing` (`database.py:1173-1188`, `UPDATE … WHERE id = ?` with no status guard) flips it **back to `complete`** a minute later. The user, following the on-screen instruction, has already deleted and re-uploaded it. That's double extraction, double quota, and a confusing flicker. The sweep was written for the old in-process thread model; with RQ the job survives in Redis, so the premise no longer holds. **Fix:** only fail leases whose RQ job is not queued or started (store `job_id` on the lease), and run the sweep from a reaper, not at import.

### 3.5 MEDIUM — no reaper for jobs that time out (READ)
The RQ job timeout is 600 s (`jobs.py:36`). A timed-out or crashed job leaves its leases `processing` until the next boot sweep, which (§3.4) is itself wrong. Add a periodic sweep: `processing` older than job timeout + margin, with the RQ job failed or missing → `failed`.

### 3.6 MEDIUM — Anthropic slow or down (READ)
- `ai_extraction.py`: client `timeout=90 s`, `max_retries=0`, plus its own loop of up to 4 attempts with backoff (`:406-470`). That's up to about 6 minutes of wall time in the worst case. This runs **in the RQ job**, not the request (the upload returns 202), so it's within the 600 s job timeout. Good.
- After the last failure, `AIExtractionError` is caught and the pipeline **falls back to regex extraction silently**. The engine is recorded only in `_ai_meta` and telemetry, not shown on the lease. The customer gets lower-quality fields with no indication (top-10 #8).
- `tool_payload()` takes the forced `tool_use` block's input but **never checks `stop_reason == "max_tokens"`** (`ai_extraction.py:472-490`). Extraction runs at `MAX_TOKENS = 4096` with 16 fields, each carrying a value, page and quote. A lease with long clauses can be cut off and stored with missing fields that look like "not found" (READ, not reproduced).
- Documents over 200 000 characters (about 70+ pages) are truncated with a note to the model but **not to the user** (`ai_extraction.py:205-229`).
- `assistant.py` has no fallback; with no key or an outage it returns 502. That's acceptable, and honest.
- **Model upgrade trap:** both `ai_extraction.call_forced_tool` (`:443`) and `assistant.py:233` use forced `tool_choice={"type":"tool"}`. That works on `claude-sonnet-5` but **returns HTTP 400 on Claude Sonnet 5.5 / Opus 5.5**. Bumping `LEASE_EXTRACTION_MODEL` in the dashboard would silently push every lease onto the regex fallback. Move to `tool_choice: auto` + `strict: true`, or structured outputs, before any model bump.

### 3.7 MEDIUM — silent failures that hide wrong data (READ)
- After a rent-roll import, the auto-reconciliation sweep failure is caught and logged; the import reports success (`api.py:1456-1461`). The user believes the rent roll was reconciled.
- `normalize.parse_currency` returns `None` for OCR-garbled money (`"$1,2OO.00"`). That lease then drops out of portfolio totals with no flag (`normalize.py:133-135`).

### 3.8 LOW — misc
- Rent-roll imports have no row cap. A 50k-row sheet will be parsed in-request.
- Tester has `plan: free` (spindown, about 30–60 s cold start) and has twice shown `x-render-routing: no-deploy` 502s after a push (TASKS.md Decisions log). That's expected free-tier behaviour, but testers will see it. Warn them, or move tester to starter.

---

## 4. Cost

### 4.1 Where Anthropic is called (READ; models from code defaults)

| Call site | Model (env override) | When | max_tokens | Notes |
|---|---|---|---|---|
| `ai_extraction.py:437` lease extraction | `claude-sonnet-5` (`LEASE_EXTRACTION_MODEL`) | once per lease (each split lease of a bundle), in the RQ job | 4096 | System prompt about 0.5 k tokens + tool schema about 3.3 k tokens (13,330 chars, measured) + document text capped at 200 k chars. No prompt caching. Up to 4 attempts on errors. |
| `ai_rent_roll_validation.py:201` | same as extraction | `POST /portfolio/rent-roll-ai-validation`, once per rent-roll row ↔ lease pair | 2048 | about 1–2 k tokens in. Unbounded pairs per request. |
| `assistant.py:227` portfolio assistant | `claude-sonnet-5` (`ASSISTANT_MODEL`) | per question | 1024 | Portfolio context of 5–15 k tokens (up to 500 leases). Rate limit 20/min **per user**, none per team. |
| `cre_qa.py:74` | `claude-haiku-4-5` (`CRE_QA_MODEL`) | not wired to a live route | 1024 | Uses prompt caching. |
| Rent-roll import, T-12 import, Deal Mismatch Report, exports | — | — | — | **No AI calls.** Pure parsing and math. |

**Today's real spend is about $0.** TASKS.md says Anthropic credits aren't funded and `render.yaml` leaves `ANTHROPIC_API_KEY` commented out, so prod runs the regex engine. Everything below is what it costs once AI extraction is turned on.

### 4.2 Unit costs at current list prices
Prices: Claude Sonnet 5 **$2 / $10 per million input / output tokens**; Haiku 4.5 $1 / $5 (Anthropic list prices from the bundled API reference, cached 2026-09-25). Token sizes come from the cost subagent's measurements of benchmark leases at about 4 chars/token. Output is assumed to be 1.5–3 k tokens per extraction (16 fields × value + page + quote).

| Unit | Input tokens | Output | Cost |
|---|---|---|---|
| Short lease (3 pp) | ≈ 5.4 k | ≈ 1.5 k | **≈ $0.03** |
| Typical multifamily lease (13 pp) | ≈ 13.7 k | ≈ 2.5 k | **≈ $0.05** |
| Long lease (31 pp) | ≈ 25 k | ≈ 2.5 k | **≈ $0.075** |
| Very long / capped (70+ pp, 200 k chars) | ≈ 54 k | ≈ 3 k | **≈ $0.14** |
| Rent roll import (any size) | 0 | 0 | **$0** |
| Optional AI rent-roll validation | ≈ 1.5 k / unit | ≈ 0.5 k | ≈ $0.008 / unit → **$1.60 for 200 units** |
| T-12 import + cross-check | 0 | 0 | **$0** |
| Assistant question | 6–16 k | ≤ 1 k | ≈ $0.02–0.04 |
| Transient-error retry | ×1 per extra attempt | | worst case ×4 |

**Per deal (200 units, 200 leases averaging about 15 pp, AI validation on, 20 assistant questions):** 200 × $0.055 + $1.60 + $0.60 ≈ **$13** (range $9–20).

### 4.3 Per customer per month vs. pricing

| Plan (monthly / annual-equivalent) | Assumed usage | Anthropic cost | Share of revenue |
|---|---|---|---|
| Starter $499 ($399) | 1 deal ≈ 200 leases | ≈ $11–17 | **≈ 2–4 %** |
| Growth $1,250 ($999) | 3–4 deals ≈ 750 leases | ≈ $45–65 | **≈ 4–6 %** |
| Enterprise | 10 deals ≈ 2,500 leases | ≈ $150–220 | depends on price |

Fixed infrastructure on top: Render `starter` web instance + 1 GB disk for prod, free tier for tester/demo, Upstash free tier. That's tens of dollars a month; check Render's current price sheet, which I can't verify from here. Postgres adds one more paid Render instance.

**Gross margin on AI is not the problem. The problems are:**
1. **Metering doesn't work** (CONFIRMED by reading the call): the async upload path logs `usage_events` with `pages=None, tokens=None` (`api.py:1094`), and `jobs.run_deferred_extraction` never records anything afterwards (`grep usage jobs.py` → nothing). So `monthly_page_quota` (2,000) is never reached and the `$50` monthly budget alert never fires for normal uploads. `usage_limits_config.py:23-24` also prices tokens at $3/$15 (an older Sonnet price, 50 % high).
2. **The default quota blocks real customers:** `DEFAULT_MONTHLY_DOCUMENT_QUOTA = 200` per team, counted per uploaded file. One 250-unit deal uploaded lease by lease hits it, and the user sees "Your team has used all 200 documents included this month" mid-deal. Per-team overrides exist (`teams.monthly_document_quota`) but nothing sets them per plan. A 40-lease PDF bundle, meanwhile, counts as 1 document.
3. **Unbounded spend paths:** assistant 20/min **per user** with no team cap (a 5-seat team scripting it is about $180/hour theoretical); AI rent-roll validation has no cap on pairs per request.
4. **Cheap wins when the key goes live:** prompt caching on the extraction system prompt + 3.3 k-token tool schema (identical every call) saves roughly 20–25 % of input cost on typical leases. The Batch API (50 % off) suits bulk deal uploads that don't need answers in seconds.

---

## 5. Section 8 / tenant data: what's missing before we can be trusted

Context: Project-Based Section 8 and LIHTC files contain SSNs, dates of birth, household income, benefits letters, and sometimes disability or reasonable-accommodation material. `docs/research/section8.md` explains why those owners are the ones who carry the certification burden.

### 5.1 What we store and send today (READ)
- **Uploaded files are deleted** after parsing (`api.py` temp file + `os.unlink` in `finally`). Good.
- **Stored per lease:** extracted field values (tenant names, unit, rent, dates…) and, for every field, a **source quote**: a padded snippet of surrounding document text (`field_extractor.py:417, 562, 1069, 1100, 1167, 1229` → `{"source": {"page", "quote"}}`). An SSN or DOB printed next to a tenant's name can land in a quote. There's **no SSN/DOB masking anywhere** (`grep -ri ssn backend/app` → nothing).
- **Sent to Anthropic (when AI is on):** the full document text up to 200 k chars, unredacted. Under default commercial terms Anthropic retains API inputs for a limited period. **The exact current terms and whether you can get zero-data-retention are UNVERIFIED and need to be asked of Anthropic.**
- **Logs:** per-request logging has no bodies, and AI telemetry logs counts and latency only (S8 subagent; spot-checked). But `ERROR_ALERT_EMAILS` mails full tracebacks to the founder via Gmail SMTP. A parser exception whose message contains document text would leave our infrastructure in an email.
- **At rest:** the SQLite file sits unencrypted on the Render disk. Field-level encryption exists only for OAuth tokens (`token_encryption.py`). Redis uses TLS (`rediss://`); job args are lease ids and page text (`sub_pages`), so **page text sits in Upstash** until the job result expires.
- **Deletion:** leases can be deleted. `activity_log`, `usage_events` and `ai_extraction_runs` keep orphaned rows (FK `SET NULL`), and there's **no team/account deletion or export** endpoint.
- **Access:** no MFA; 8-character minimum password; 12-hour sessions; no per-user audit log of who *viewed* or *exported* a tenant file (only change activity). Owner-console routes return team and usage metadata, and I found no owner route that returns another team's lease content (the security subagent covers this in §2).
- **Marketing claims** (`frontend/index.html`): the "Isolated per team" card is now true (team isolation merged). Any copy saying data is "never shared with a third party" is **false once AI extraction is on**, because Anthropic is a subprocessor. Fix the copy or name Anthropic.

### 5.2 Minimum bar before the first Section 8 / LIHTC customer

**Engineering (about 8–12 days):**
1. SSN / DOB / bank-account masking before storage (source quotes, fields) **and** before sending text to Anthropic. Regex plus tests on the `feature/s8-demo-files` planted SSNs. 2–3 days
2. Encryption at rest: Postgres with encrypted storage (§1.6), or SQLCipher in the interim. Plus encrypted off-site backups. Comes with the Postgres work, +1 day
3. A per-team "AI processing off" switch, so a cautious customer can use regex-only until the DPA is signed. 1 day
4. Read/export audit log (who opened or exported which lease, when) and a team data export + hard-delete (cascade through activity, usage, ai runs, conversations, Redis job data). 3–4 days
5. MFA (TOTP) for admin and owner roles; stronger password rule (12+ chars + breached-password check). 2 days
6. Scrub tracebacks in alert emails (exception type + location only). 0.5 day

**Paperwork / legal (needs a lawyer — I can't verify any of this):**
1. Anthropic: zero-data-retention or DPA addendum, confirmed in writing.
2. Privacy policy, terms of service, a customer DPA template, and a **subprocessor list**: Anthropic, Render, Upstash, Google (Sheets export, Gmail SMTP), Calendly.
3. Incident-response and breach-notification plan (state breach laws turn on SSNs).
4. HUD-specific: whether the customer's tenant data includes **EIV** (Enterprise Income Verification) output. HUD's EIV rules restrict disclosure to authorized parties. **Ask counsel whether a SaaS processor may hold EIV-derived data at all**, and whether customers must strip it before uploading.
5. A short security page (encryption, isolation, retention, subprocessors) and a SOC 2 roadmap answer. Customers will ask; "on the roadmap, Type I targeted <date>" is an acceptable answer for a startup, but nothing is not.

---

## 6. Deep pass: bugs found tracing routes and jobs end to end

### Severity index (all functional bugs in §3 and §6, most severe first)

| # | Sev | Bug | Where | Evidence |
|---|---|---|---|---|
| 1 | CRIT | Original + renewal lease for one unit both compared → ~$28.8k/yr phantom overstatement per renewed unit | §6.11 | CONFIRMED |
| 2 | CRIT | T-12 income check compares monthly to annual → never fires | §6.1b | CONFIRMED |
| 3 | CRIT | Report page never sends `property_address` → every UI T-12 upload 400s | §6.1a | CONFIRMED |
| 4 | CRIT | PDF page cap dead + whole-PDF rasterization in-request → OOM/timeout | §3.1 | CONFIRMED |
| 5 | HIGH | Vacant rows dropped → occupancy always 100 % → false T-12 occupancy finding on almost every deal | §6.1c | CONFIRMED |
| 6 | HIGH | Unit labels not canonicalized ("Unit 101" ≠ "Apt 101") → real rent gaps hidden | §6.11 | CONFIRMED |
| 7 | HIGH | Scheduled rent step-ups ignored → correct rent roll flagged as overstatement | §6.11 | CONFIRMED |
| 8 | HIGH | Regex extractor misses 7 of 12 common residential rent phrasings → rent `None` → unit silently unchecked | §6.16 | CONFIRMED |
| 9 | HIGH | "Tenant Name: Maria Lopez" → tenant `"Name"` (high confidence) → tenant mismatch on every such unit; "from 03/01/2026 to 02/28/2027" → no dates | §6.16 | CONFIRMED |
| 10 | HIGH | "$72,000 per annum ($6,000 per month)" stored as monthly rent → ×12 phantom | §6.16 | CONFIRMED |
| 11 | HIGH | "First month 50 % off" priced as 50 % off all 12 months (12× concession) | §6.16 | CONFIRMED |
| 12 | HIGH | Re-importing a rent roll (e.g. seller's updated version) duplicates every unit | §6.17 | CONFIRMED |
| 13 | HIGH | Street-suffix / property-name variants ("St" vs "Street") break unit pairing and property scoping | §6.11, §6.17 | CONFIRMED |
| 14 | HIGH | Dashboard KPIs double-count units that have a rent-roll row and a lease PDF (4 leases / $6,200 for 2 units / $3,100); disagrees with the memo | §6.18 | CONFIRMED |
| 15 | HIGH | Worker boot fails every team's in-flight leases, which then flip back to complete | §3.4 | CONFIRMED |
| 16 | HIGH | ISO dates in CSV rent rolls silently dropped | §6.2 | CONFIRMED |
| 17 | HIGH | T-12 months with a year in the header lose all monthly data (no Total column → import error) | §6.13 | CONFIRMED |
| 18 | HIGH | Bad-debt trend uses calendar Oct–Dec, not the latest 3 months | §6.1d | CONFIRMED |
| 19 | HIGH | Redis enqueue failure → 500 after insert, leases stuck, quota charged | §3.2 | READ |
| 20 | HIGH | Worker unsupervised; `/health` blind to Redis/worker | §3.3 | READ |
| 21 | HIGH | Metering: pages/tokens never logged on async path → page quota and $ budget dead; 200-doc default blocks one deal | §4.3, §6.4 | READ |
| 22 | HIGH | Regex accuracy on real leases unmeasured for multifamily; 49 % precision of "high" confidence on the real (commercial) corpus | §6.14 | subagent benchmark |
| 23 | MED | No per-property report in the UI; investment memo has no view | §6.17 | READ |
| 24 | MED | Comma-decimal rents read 100–1000× off | §6.10 | CONFIRMED |
| 25 | MED | Yardi charge-per-row rent roll rejected | §6.10 | CONFIRMED |
| 26 | MED | T-12 picks the first matching income line, not the total | §6.13 | CONFIRMED |
| 27 | MED | AI→regex fallback, truncation, `max_tokens` invisible to user | §3.6 | READ |
| 28 | MED | Forced `tool_choice` will 400 on Sonnet/Opus 5.5 → silent regex fallback after a model bump | §3.6 | READ |
| 29 | MED | OCR-garbled money returns `None` → unit drops out of totals | §6.5 | READ |
| 30 | MED | Dedup response shape differs; duplicate notice never shown | §6.6 | READ |
| 31 | MED | `.xls` T-12 accepted but unparseable | §6.6 | READ |
| 32 | MED | No reaper for timed-out jobs | §3.5 | READ |
| 33 | MED | Post-import reconciliation failure swallowed | §3.7 | READ |
| 34 | MED | `GET /leases` unpaginated (multi-MB on large deals) | §6.12 | READ |
| 35 | MED | Scanned-T-12 OCR has no confidence threshold | §6.13 | READ |
| 36 | MED | Deactivated member's tasks orphaned; unvalidated `due_date` | §6.7 | READ |
| 37 | LOW | Escalation-schedule parsing only handles `Year N: $X` | §6.5 | READ |
| 38 | LOW | Dashboard widgets hide backend error text; `/discrepancies/summary` loads all to count | §6.12 | READ |
| 39 | LOW | Upload polling ignores network errors until the 5-min timeout | §6.12 | SUSPECTED |
| 40 | LOW | Commercial-oriented AI prompt and demo seed for a multifamily product | §6.5 | READ |
| 41 | LOW | Concession rounding ≤ $0.05; assistant 502 with no key | §6.8 | READ |

(Security findings are ranked separately in §2.2.)

**Coverage.** Six subagents traced api.py in slices (lease pipeline + RQ job; auth/teams/tasks; assistant/messaging/discrepancies/alerts; portfolio + Deal Mismatch math; exports/owner/health; frontend↔backend contract), and I spot-traced the T-12 and rent-roll paths myself.

**Re-check.** Every finding below was re-checked by me. Some subagent "all clean" verdicts turned out to be wrong:
- The Deal Mismatch math agent called the core math "production-ready", but it only replayed the Maple Ridge golden deal, which has no T-12 gap. The bugs in §6.1 are mine.
- The exports agent likewise missed formula and markup injection.

### 6.1 CRITICAL — T-12 cross-check (the "T-12 cross-check" product pillar)

**(a) The report page can never send a T-12** (CONFIRMED, READ)
- `frontend/app/deal-mismatch-view.js:46` calls `Api.dealMismatchReport({ t12File, materialityThresholdPct })` with no `propertyAddress`.
- `POST /portfolio/deal-mismatch-report` (`api.py:4069-4071`) returns `400 "t12_file requires property_address"`.
- The PDF/XLSX export calls do the same.
- Previously reported in `OVERNIGHT_REPORT.md` on `docs/tester-pack` (2026-10-01) and still unfixed.

**(b) The income-gap check can never fire** (CONFIRMED)
- `detect_t12_income_gap` (`deal_mismatch.py:725-790`) is documented as "rent roll's building-level **annualized** rent".
- It actually sums **monthly** rent-roll rents and subtracts the T-12 **annual** collections. The difference is always negative, so it returns `[]`.
- It also only ever looks at the *first* building in the dict.
  ```
  rent roll $1.8M/yr vs T-12 collected $1.2M/yr -> 0 finding(s)      # 100 units × $1,500/mo; a 33 % shortfall
  ```

**(c) The occupancy check is a false positive on almost every deal** (CONFIRMED)
- `rent_roll_import` drops VACANT rows (`_NON_TENANT_KEYWORDS`, `rent_roll_import.py:262`).
- So `detect_t12_occupancy_mismatch` (`deal_mismatch.py:791-848`) always computes rent-roll occupancy as 100 %.
- It then flags any T-12 that shows vacancy loss, including one that agrees exactly with the rent roll.
- The same 100 % assumption silences `detect_t12_bad_debt_trend` whenever there really is vacancy.
  ```
  rent roll rows: 100 (90 leased + 10 vacant); imported leases: 90 ; skipped: 10
  T-12 occupancy 90% == true rent-roll occupancy 90% -> [('100.0%', '90.0% (T12)')]
  ```

**(d) The bad-debt "last 3 months" are calendar months, not the latest months** (CONFIRMED)
- T-12 months are keyed `jan…dec` with no year (`t12_import.py:63-64`, `t12_statement.py:30`).
- `detect_t12_bad_debt_trend` (`deal_mismatch.py:905-911`) takes `monthly_values[-3:]`, which is always Oct–Dec.
- For any T-12 that doesn't end in December (most of them: trailing twelve months to the latest close) it analyses the wrong months:
  ```
  spike in most recent 3 months (Jul-Sep) -> 0 finding(s)
  spike in OLDEST 3 months (Oct-Dec) -> 1 finding(s)
  ```

**Fix (≈1–1.5 days for all four, with tests):**
- Send or derive `property_address`.
- Annualize and compare per building.
- Import vacant rows as units with no tenant (or count them separately), so occupancy is real.
- Keep `(year, month)` keys in the T-12 parser and order by period.
- Add a T-12 golden fixture with a deliberate gap, a deliberate vacancy, and an Oct–Sep period.

### 6.2 HIGH — ISO dates in CSV rent rolls are silently dropped (CONFIRMED)
`normalize.parse_date('2026-08-31')` returns `None`. `rent_roll_import` only stores a date if `parse_date` accepts it (`rent_roll_import.py:631-634`). Excel date cells survive (converted to "August 31, 2026"), but a CSV export with ISO dates loses every lease start and end date. **No warning is shown**, and every downstream check (expired-but-occupied, date mismatch, rollover, expirations) silently skips those units.
```
Jane Doe None None            # CSV row: 2023-01-01, 2024-12-31   -> both dates dropped
John Roe 01/01/2023 12/31/2024
```
Fix: accept ISO (and `YYYY-MM-DDTHH:MM:SS`) in `parse_date`. Separately, count unparsed date cells in the import response so the user sees them. 1 h.

### 6.3 HIGH — background extraction state machine (CONFIRMED / READ)
See §3.2–§3.5. Every gunicorn worker boot marks every in-flight lease (all teams) failed, with "Delete this and upload again", and the job later flips it back to complete. A failed Redis enqueue leaves leases `processing` and charges quota. There's no reaper for timed-out jobs.

### 6.4 HIGH — metering and quota (READ)
- The async path logs `pages=None, tokens=None` and the job never back-fills them, so the page quota and $ budget alerts can never trip (`api.py:1094`, `jobs.py`).
- Quotas are counted per *file*, so a 40-lease bundle costs 1 document.
- A lease that ends up `ocr_needed` (unreadable scan) still consumes a document.
- `_validate_upload` checks quota *before* dedup, so re-uploading an existing file is refused at quota even though it would cost nothing.

### 6.5 MEDIUM — silent wrong-but-plausible data
- **OCR-garbled money vanishes from totals** (READ). `"$1,2OO.00"` is stored as-is. `parse_currency` returns `None`, the unit drops out of portfolio rent totals and rent comparisons, and nothing flags it (`normalize.py:133-135`, `field_extractor.py:921-952`). Flag unparseable money fields as low-confidence at extraction time.
- **AI→regex fallback, truncation, and `max_tokens` are invisible to the user** (§3.6).
- **Auto-reconciliation failure after a rent-roll import is swallowed** (`api.py:1456-1461`).
- **Rent-escalation schedules only parse the literal `Year N: $X` shape** (`normalize.py:322-340`). Other phrasings make the escalation-consistency risk check silently skip the lease.
- The **AI system prompt is written for commercial leases** ("commercial real estate lease abstraction specialist", example tenant "Blue Sky Coffee Roasters, Inc.", CAM charges). The product is multifamily. That's not a bug, but residential-specific fields (pet rent, parking, utilities, RUBS, renter's insurance) have no slots. (READ `ai_extraction.py:123-160`)
- **The demo deployment seeds commercial sample leases** (coffee shop) rather than Maple Ridge (`demo_seed.py`), which undercuts the multifamily pitch on the public demo. (READ, from the tester-pack report, not re-verified line by line.)

### 6.6 MEDIUM — upload/UI contract
- **The duplicate-upload notice is never shown.** The API returns `reused_existing_upload: true` + `message`, but `grep -rn reused_existing_upload frontend` finds nothing. The dedup response also has a different shape from a normal upload (`fields`, not `extracted_fields`; no `processing_status`), so a duplicate of a still-processing lease looks like a finished lease with empty fields (`usage_limits.py:137-143`).
- **`.xls` T-12s are accepted, then fail.** The route allows `xls`, but `parse_xlsx_t12_statement` uses `openpyxl` (`t12_statement.py:210`), which can't read the legacy format. The rent-roll path has `xlrd`; the T-12 path doesn't use it.
- **Deal-mismatch rows show the raw `deal_mismatch` type** in the discrepancies UI (missing label; tester-pack report). (Not re-verified.)
- **Non-CSV/XLSX rent rolls (PDF, image) are only fed to the report via the lease path**, not as rent-roll rows (`api.py:566-570`; tester-pack report).

### 6.7 MEDIUM — team lifecycle (READ)
- **Deactivating a member leaves their tasks and assignments pointing at them.** `task_detail` then shows `assigned_to: None` with no "needs reassignment" state (`api.py:2399-2426`, `tasks.py:47-50`).
- **`POST /tasks` accepts any `due_date` string** (`api.py:2747`). `"2026-13-45"` is stored and later breaks date sorting and alerts.

### 6.8 LOW
- Rounding in concession annualization can differ by ≤ $0.05 between the monthly and annual figures (`concessions.py`). Cosmetic.
- `/assistant/ask` with no API key returns 502 with no fallback. That's acceptable and honest, but testers on a key-less deploy will see the Assistant as broken; hide it when no key is configured (`GET /config` could expose the flag).

### 6.10 Wave 2 — real-world rent-roll formats (CONFIRMED unless noted)
Nine PMS-style exports were run through the real importer. Passed:
- AppFolio with property group headers and total rows
- RealPage OneSite with an 8-row header block, merged two-row headers, and text currency
- Entrata co-resident rows (co-tenants without rent were correctly not made into units)
- a 600-unit file (0.01 s)
- duplicate unit numbers across buildings
- mixed Excel cell types
- formula cells (`data_only`)
- the rent roll on a non-first sheet

Problems:
- **MEDIUM — comma-decimal rents are misread by 100–1000× with no error.** `_parse_import_currency` (`rent_roll_import.py:389-431`):
  ```
  '1.250,00' -> 1.25        '1250,00' -> 125000.0        ('1,250.00' -> 1250.0 is fine)
  ```
  This is rare in US multifamily, but a single seller spreadsheet saved in a European locale would make every unit a "rent mismatch" with absurd dollar impacts. Fix: detect `d.ddd,dd` / `dddd,dd` and either normalize or reject the column with a clear error. 30 min.
- **MEDIUM — Yardi "Rent Roll with Lease Charges" (one row per charge code: rent, petrent, parking, concession…) is rejected outright.** You get `RentRollImportError: Couldn't find a row with a recognizable tenant name column and rent column…` because the rent lives in a generic `Amount` column keyed by `Charge Code`. It fails loudly, which is better than silently. But Yardi is one of the most common PMS exports a seller will hand over, so this is a real gap. Simply adding `amount` as an alias would be **wrong**: every charge row would become a unit. The fix is to group charge rows under their unit, take `rent` as rent, and treat `concession`/`conc*` negatives as concessions. 0.5–1 day with fixtures.
- **LOW — `skipped_rows` are returned but shown weakly.** The import response lists them and `upload-view.js:~401` reads them, but there's no prominent warning listing *why* rows were dropped (READ).
- *Rejected:* "rows with a tenant but blank rent should be skipped". Importing the unit with `rent_amount = None` is the right behaviour, because skipping it would hide a unit. The real gap is that a missing rent isn't flagged as a finding (fold into top-10 #8).

### 6.11 CRITICAL / HIGH — Deal Mismatch pairing (wave 2, CONFIRMED by me)
The detectors pass the Maple Ridge golden deal, but that deal has exactly one lease per unit and uses one unit-label format everywhere. Real lease files have neither property.

**CRITICAL: an original lease plus its renewal for the same unit produce phantom findings.**
- Setup: the rent roll shows $2,100 and the current 2026 renewal says $2,100, but the expired 2025 original ($1,800) is also on file. That's normal; buyers receive the whole lease folder.
- Result:
  ```
  rent_mismatch:        [('rent_mismatch', 3600.0, 'overstate')]   # compares rent roll to the OLD lease
  expired_but_occupied: [('expired_but_occupied', 25200.0)]        # old lease ended 12/31/2025, unit still occupied
  ```
- That's $28,800/yr of false "overstatement" on a unit that's fully correct, and it's counted in the headline total.
- Cause: `get_all_effective_leases` (`database.py:~1882-1890`) only folds documents with `document_type != 'lease'` and a `base_lease_id`, which happens via the explicit amendment route (`api.py:1785`) or `/resubmit`. A renewal uploaded normally is its own `lease`. `detect_rent_mismatch` and `detect_expired_but_occupied` then compare the rent roll row against **every** lease document at that address (`deal_mismatch.py:211-302`).
- Fix: per unit, pick the *operative* lease (latest start date / covering today) for comparison. Treat older ones as history, or as a "renewal on file" note. Auto-link renewals (same unit + tenant, later term). Add a golden fixture with a renewal chain.
- Estimate: 1 day.

**HIGH: unit labels don't normalize, so real rent gaps disappear.**
- `_normalize_address` (`portfolio.py:270-279`, used by `deal_mismatch._address_groups`) lowercases and strips punctuation but **keeps "unit"/"apt"/"#" designators**. `_normalize_building_address` (`portfolio.py:293`) already strips them via `_SUITE_DESIGNATOR_RE`.
  ```
  '123 Main St, Unit 101' -> 123 main st unit 101      '123 Main St, Apt 101' -> 123 main st apt 101      '123 Main St, #101' -> 123 main st 101
  rent roll "Unit 101" $2,100 vs lease "Apt 101" $1,800 -> rent_mismatch: []   unit_no_lease: 1   lease_no_unit: 1
  ```
- A $3,600/yr overstatement becomes two unpriced "no lease" / "no unit" rows, which are excluded from the dollar total.
- **The street part has the same problem** (wave 3, CONFIRMED). "Street" vs "St", and a leading property name ("Maple Ridge Apartments, 100 Oak St"), produce different keys at both unit and building level:
  ```
  '100 Oak Street, Unit 101, Austin, TX' -> unit key: 100 oak street unit 101 austin tx
  '100 Oak St., Unit 101, Austin, TX'    -> unit key: 100 oak st unit 101 austin tx
  rent roll 'Oak St' $2,100 vs lease 'Oak Street' $1,800 -> rent_mismatch: [] unit_no_lease: 1
  ```
  Rent-roll rows get their address from the uploader-typed property name plus the unit column; lease addresses come out of the PDF. The two will differ like this routinely.
- Fix: one canonical address key (USPS suffix table, drop property-name prefixes, a canonical unit token, leading zeros, `A-101`/`A101`), shared by unit pairing and property scoping. Plus a "suggested matches" step for leftover unpaired rows. 1 day with tests.

**HIGH: scheduled rent step-ups are ignored, so a correct rent roll gets flagged** (CONFIRMED by me).
- `deal_mismatch.py` never reads `rent_escalation`; `detect_rent_mismatch` compares the rent roll to the lease's *initial* rent only.
  ```
  2-yr lease with scheduled step to $1,545 in year 2; rent roll $1,545 -> [('rent_mismatch', 540.0, 'overstate')]
  ```
- Fix: compute the rent in effect on the report's as-of date from the parsed escalation schedule (`normalize.parse_escalation_schedule`) before comparing. If the schedule can't be parsed, mark the finding "may reflect a scheduled increase" rather than pricing it as an overstatement. 3–4 h.

**Checked clean:** the $5-and-1 % rent tolerance (both must be exceeded); the monthly→annual ×12; `income_direction` signs; the total = Σ priced rows (unverified rows correctly excluded); concession vs. rent-mismatch de-duplication (`deal_mismatch.py:237-241`).

### 6.12 MEDIUM / LOW — UI at scale and failure states (wave 2)
- **`GET /leases` has no pagination** (`api.py:1499-1518`). It returns every lease with full `extracted_fields`. The dashboard renders at most 500 rows (`dashboard-view.js:9, 966-968`) with "Showing 500 of N — use search or filters". So the rows are reachable, but a 600-unit deal ships a multi-MB JSON payload on every dashboard load. MEDIUM (READ; payload size estimated, not measured).
- **Eight dashboard widgets swallow the backend error** and show a generic "Failed to load" (`dashboard-view.js:60-88`), while two widgets on the same page show the real message. LOW.
- **`/discrepancies/summary` loads every open discrepancy to count the new ones** (`api.py:4418-4421`). LOW now, and grows with deal size.
- **Upload polling ignores network errors** (`upload-view.js:200-201`, `.catch(() => l)`) and keeps polling until its 5-minute timeout, then reports a timeout for work that finished. That invites a duplicate re-upload. LOW (SUSPECTED).
- Checked fine: 202 → polling → `complete`/`failed`/`ocr_needed` all render with their messages; 429s are shown per file; 401 → re-login.

### 6.13 HIGH — T-12 parsing on real exports (wave 2, CONFIRMED by me)
- **Month headers that carry a year lose all monthly data.** Real exports (Yardi "Oct 2025", AppFolio "10/2026", "October 2025") hit this. Both parsers match month headers by exact name (`t12_import.py:108-123`; same approach in `t12_statement.py`). With a `Total` column, the annual figure survives but monthly is empty, so every monthly-based check (bad-debt trend) silently can't run. Without a `Total` column, the import fails outright.
  ```
  t12_statement, bare "Oct".."Sep":     rental_income_collected (1176000.0, 12 months)
  t12_statement, "Oct 2025".."Sep 2026": rental_income_collected (1176000.0, 0 months)
  t12_import,    "Oct 2025" no Total:    T12ImportError Couldn't find a column to compute an annual total from…
  ```
  Fix: parse month and year from the header and key by `(year, month)`. That also fixes §6.1(d). 2–3 h.
- **The first matching income line wins, not the right one.** With "Gross Rental Income $900,000", "Other Rental Income", then "Total Rental Income $924,000", both parsers return $900,000. Which line counts as collections is a judgement call. The parser should prefer the explicit total/collected line and **show which line it used** in the report (it already stores `source.quote`; surface it). MEDIUM. 2 h.
- **Partial-year T-12s** (fewer than 12 months, no total) are rejected with an error rather than annualized. That's acceptable (loud), so LOW.
- **Scanned T-12 PDFs** go through OCR with no confidence threshold (`t12_statement.py:246-280`), so OCR'd numbers are trusted like typed ones. MEDIUM (READ).
- *Rejected:* "negative / contra-signed income comes through negative". Both parsers return `1200000.0` for a row of `-100000` × 12. Parenthesised negatives also parse correctly.

### 6.14 HIGH — extraction accuracy is unmeasured where it matters (wave 2, subagent benchmark)
**Prod and tester run the regex extractor today**, because there's no Anthropic key. The `accuracy-tester` subagent ran the existing harness with the engine forced to regex. **I did not re-run it.** It wrote its output into the primary checkout, which I restored; its copy is kept in the scratchpad.

| Corpus | What it is | Regex accuracy |
|---|---|---|
| Maple Ridge (15 leases) | **Synthetic** multifamily leases from `generate_demo_deal.py`, all one template | 100 % on tenant, rent, start, end, concessions |
| 12-lease benchmark | **Real commercial** leases from SEC filings | **36.7 % overall**: rent 41.7 % (PSF/annual vs monthly confusion), end date 16.7 %, address 16.7 %, renewal options 0 % |

**Confidence is not calibrated.** Only **48.8 %** of values marked *high* confidence were correct, with 43 high-confidence wrong values (for example, tenant = `"Sovereign Drive, Lansing, Michigan 48911"`).

**What it means:**
- There's **no benchmark of real multifamily leases at all**. The one corpus that passes is synthetic, and the one built from real documents is the wrong asset class.
- Before testers upload real leases, build a 20–30-lease **real** multifamily corpus (redacted) with ground truth. Report regex and AI accuracy on it.
- Until then, treat every regex value as *medium* confidence at most. A wrong rent or end date becomes a phantom dollar finding (§6.11 shows how fast those add up).
- 2–3 days to assemble and label; it's ongoing after that.

### 6.16 HIGH — residential lease language vs. the regex extractor and concession parser (wave 3, CONFIRMED by me)
This is what testers get today: no Anthropic key means the regex engine. The wave-3 subagent ran 40 residential clause variants and 25 passed. I re-ran the important ones and widened one probe myself.

**HIGH: common rent phrasings return no rent at all.** `field_extractor.FieldExtractor().extract_fields(...)` gets **5 of 12** everyday residential wordings:
```
   $1,525.00  Monthly Rent: $1,525.00
        None  Rent: $1,525.00 per month
   $1,525.00  The monthly rent is $1,525.00.
        None  Resident agrees to pay rent of $1,525.00 per month.
        None  Tenant shall pay Landlord $1,525.00 per month as rent.
        None  Resident will pay $1,525.00 each month for rent.
   $1,525.00  RENT. Resident shall pay monthly rent in the amount of $1,525.00 on or before…
   $1,525.00  Rent is $1,525.00 per month, due on the first day of the month.
        None  Monthly Base Rent ......................... $1,525.00
   $1,525.00  The total monthly rent … ($1,525.00).
        None  Lessee shall pay as rent the sum of $1,525.00 per month.
        None  Rent: $1,525/mo
5 / 12
```
- A lease with no extracted rent can never produce a rent mismatch, so **the unit is silently unchecked**.
- Maple Ridge passes only because its generator always writes `Monthly Rent:`. "Payable in monthly installments of $X" also fails (subagent).
- Fix: broaden the patterns using this table as tests. Even better, add a "rent not found" finding so a blind spot is visible. 0.5 day.

**HIGH: annual figures stored as monthly rent.**
- `"Base Rent: $72,000.00 per annum ($6,000.00 per month)"` is stored as `$72,000.00`.
- In the report that's a ×12 phantom rent mismatch: about $792 k/yr on one unit. The pattern that matches "per annum" wins before the monthly one (`field_extractor.py:~921`).
- Fix: prefer the explicitly-monthly figure; never store a "per annum" figure as monthly rent. 1 h.

**HIGH: "First month's rent is 50% off" is priced as 50 % off every month.**
- `_recurring_duration` defaults to full term when no duration is stated (`concessions.py:412-426`), even when the sentence says "first month".
  ```
  First month's rent is 50% off ($1,600 rent, 12-mo lease) -> {'monthly_value': 800.0, 'applies_months': 12.0, 'total_value': 9600.0}   # should be $800 once
  ```
- That's a 12× concession. Confidence drops to *medium*, but the dollar figure is still used.
- Fix: when the clause names a specific month ("first month", "13th month"), set `months=1`. 1 h.

**HIGH: tenant, date and deposit probes** (my own probe, same method):
```
tenant:  ('Name', 'high')      <- "Tenant Name: Maria Lopez"                         # label word captured, HIGH confidence
tenant:  (None, None)          <- "RESIDENT(S): Maria Lopez, James Lopez"
tenant:  (None, None)          <- "between Oak Partners LLC, as Landlord, and Maria Lopez and James Lopez, as Tenants."
tenant:  ('Maria Lopez','high')<- "...entered into by Oak Partners LLC ("Owner") and Maria Lopez ("Resident")."
dates:   None | None           <- "Lease Term: 12 months, from 03/01/2026 to 02/28/2027."
dates:   None | 2/28/2027      <- "This lease starts 3/1/2026 and expires 2/28/2027."
dates:   OK for "begins on … ends on …", "Commencement Date / Expiration Date", "Beginning/Ending Date", "1st day of March, 2026"
deposit: (None, None)          <- "Deposit: $500.00 (refundable); Pet Deposit: $300.00"
```
- `Tenant Name:` is probably the single most common label on residential lease forms. Producing `"Name"` at *high* confidence means **every such unit gets a tenant-mismatch finding** against the rent roll.
- Fix: add these wordings as regression cases and patterns; reject label words ("Name", "Resident", "Tenant") as values. 0.5 day, alongside the rent patterns.

**Smaller items:**
- **MEDIUM:** comma-decimal and `$1.450` typos misread (same root cause as §6.10, here in `normalize.parse_currency`).
- **LOW:** a concession end date stated after the amount ("…$75 off per month through September 30, 2026") isn't captured, so timing shows as unknown.

**Checked fine:**
- A month-to-month continuation clause isn't flagged as expired (no fixed end date is extracted).
- A Section 8 split ("Tenant portion $412; HAP contract rent $1,380") extracts the contract rent.
- Deposit, casualty-abatement and parking/RUBS lines aren't mistaken for concessions.
- Move-in credits are classified as one-time.

**Not reproduced by me (dropped):** "base rent line parsed as a $1,500/mo discount". With a separate `Concession:` sentence, only the $75 discount was found. The subagent's variant may differ, but I couldn't confirm it.

### 6.17 HIGH — re-imports and multi-property teams (wave 3, CONFIRMED by me)
**Importing a rent roll twice doubles every unit.**
- `POST /leases/import-rent-roll` (`api.py:1384-1480`) inserts every parsed row as a new lease. There's no content hash, no "replace previous rent roll for this property", and no supersede.
  ```
  Second import: 3 leases created with IDs [4, 5, 6]
  Total leases after second import: 6     (Alice Smith ×2, Bob Jones ×2, Carol White ×2)
  ```
- Sellers routinely send an *updated* rent roll mid-diligence. After the second upload, every unit is compared against both the old and the new row: duplicate or contradictory findings, unit counts doubled in KPIs, and an occupancy figure built on doubled rows.
- Fix: a rent-roll import replaces the prior import for the same property (keep it as a superseded version for audit), with content-hash dedup for identical files. 0.5 day.

**There is no way to run the report for one property.**
- The Deal Mismatch view says so itself ("Whole-portfolio scope only for now (no property_address picker)", `deal-mismatch-view.js:10-13`).
- The investment-memo PDF/XLSX routes exist (`api.py:4985, 5017`) but have no frontend view.
- A syndicator with two deals in diligence gets one blended report.
- Even through the API, `_scoped_leases` (`investment_memo.py:77-84`) compares `_normalize_building_address` strings exactly. Scoping to "100 Oak Street…" silently drops that property's units written as "100 Oak St." or "Maple Ridge Apartments, 100 Oak St" (subagent repro: 1 of 3 units kept, no warning).
- `trends-view.js` already has a property picker to copy.
- Fix: depends on the canonical address key above; then add a picker plus a "units not assigned to any property" bucket. 0.5–1 day.

**Checked fine (wave 3):**
- Manual field edits land on whichever document currently governs the field (base or amendment; `api.py:1612-1626`, `database.get_field_source_chain`), so every consumer sees the edit.
- Superseded (resubmitted) leases drop out of `get_all_effective_leases`.
- A superseded lease's amendments don't leak onto its replacement.
- Deleting a lease keeps its discrepancy history.
- `get_amendments()` has no `team_id` parameter, but every caller has already team-checked the base lease (hardening only).

### 6.18 HIGH — dashboard KPIs double-count every unit that has both a rent-roll row and a lease (CONFIRMED by me)
`GET /portfolio/summary` → `compute_portfolio_metrics(get_all_effective_leases(team))` (`api.py:3736-3740`) treats rent-roll rows and lease documents as separate leases. After the normal diligence upload (rent roll + the lease PDFs), every unit counts twice:
```
2 units (rent roll + 2 lease PDFs): {'lease_count': 4, 'total_monthly_rent': 6200.0, 'total_square_footage': 3400.0}   # truth: 2 units, $3,100/mo, 1,700 sf
```
- The investment memo already dedups by unit, preferring the PDF (`investment_memo.py:127-130`), so **the dashboard and the memo disagree** on the same deal.
- The other KPIs built from the same list (WALT, rollover, tenant concentration, loss-to-lease, health score) are exposed to the same double-weighting. READ, not each run.
- Fix: one "unit view" (rent roll ∪ leases, deduped by the canonical unit key from §6.11) that every KPI consumes. 0.5 day after the address key exists.

### 6.19 Traced and found clean (so coverage is visible)
- **Auth:** all `/auth/*` flows except M5 and M7; reset-token one-time use.
- **Team management:** `/team/members*` scoping and owner protection; `/assignments*`.
- **Tasks:** `/tasks*` incl. bulk ops partial-failure reporting; lease-field undo window.
- **Alerts:** generation is idempotent (natural-key upsert + auto-resolve, respects dismissals).
- **Discrepancies:** resolve/reopen state machine and history; `/comments/recent` (single JOIN).
- **Messaging:** threads and unread counts (participant-scoped, excludes own messages).
- **Public endpoints and OAuth:** email-account OAuth (real Google/Microsoft wiring, state expires in 600 s); waitlist duplicate handling; demo-request validation and honeypot.
- **Deal Mismatch:** the rent/expired/concession/missing-lease detectors reproduce the Maple Ridge golden totals exactly ($45,355.00/yr, 10/10 findings).
- **Exports and owner console:** PDF/XLSX export numbers match the JSON; owner finance summary arithmetic and month bucketing; portfolio weighted $/sf; empty-portfolio and missing-field edge cases.
- **Frontend contract:** every frontend `fetch` maps to an existing route with matching method and snake_case fields; 401 → `login.html?expired=1`; no redirect loop.

---

## Appendix A — subagent claims I checked and **rejected**
Kept here so they don't get re-raised:
- "`get_connection()` has no timeout (defaults to 0)." **False.** Python's `sqlite3.connect` default is 5.0 s. The real issue is that 5 s is short and there's no WAL.
- "`usage_limits.log_usage_event` reuses a closed connection." **False.** One connection is opened at the top and closed in the `finally` at the end (`usage_limits.py:164-224`).
- "`leases` has no tenant column; isolation is route-level only." **Stale.** `team_id` is on `leases` and the other document tables since `3cff20b`, and queries filter on it.
- "OCR runs during the upload page-count check and times out." **Wrong mechanism.** That check never OCRs; it crashes on `temp_path=None` and skips the limit (§3.1). OCR does run in-request, but later.
- "The `dedup_reuse` event inflates the budget." It's logged with cost `None`, so `SUM()` ignores it. No effect.
- "`strftime` month bucketing breaks on `+00:00` timestamps." SQLite parses ISO-8601 with offsets. Not a bug.
- "`test_demo_deal_golden.py` still depends on `.env`." **Fixed** on main (`953c00a`, `521b204`); the suite is 82/82 in a clean worktree.
- "Exports/owner routes are production-ready, no bugs." True for the arithmetic tested (Maple Ridge, 31 leases), but that subagent didn't look at the CSV-injection issue, which applies to the export routes in its own scope.

- Wave 2: "rows with a tenant but no rent should be skipped" (§6.10), "contra-signed T-12 income comes out negative" (§6.13), and "multiple leases per unit is working as designed" (wrong; see §6.11, it creates phantom dollar findings).
- Wave 2: "T-12 month headers with a year break *all* parsing". **Overstated.** The annual figure survives when there's a Total column; the monthly data is what's lost (§6.13).
- Wave 2: "the dashboard can't show leases past 500". The rows are reachable through search/filters; the real issue is the unpaginated payload (§6.12).
- Process note: the accuracy subagent wrote `backend/benchmark_data/last_run.json` in the **primary checkout**, against instructions. I backed it up to the scratchpad (`audit/w2-acc-last_run.json`) and restored the committed version. The primary checkout now differs from `main` only by the TASKS.md claim.

## Appendix B — files and commands
- Dependency scan: `uvx pip-audit -r backend/requirements.txt` (JSON kept in the session scratchpad).
- Tests: `python backend/tests/run_all_tests.py` → 82/82.
- Repro scripts for §3.1 and §3.4 are quoted inline above.
