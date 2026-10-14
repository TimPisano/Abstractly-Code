# Usage Controls (Anthropic API Spend Protection)

Branch: `feature/usage-limits`, based on `feature/t12-crosscheck` (this
worktree was already branched there at commit `b397b40`). Not rebased
onto `main` -- doing so would drop unmerged work from
`feature/deal-mismatch-report`/`feature/t12-crosscheck` that isn't
this task's concern to reconcile.

## The one real scope call, flagged before writing any code

**This app has no "team" concept anywhere in its data model.** Confirmed
directly in `database.py`: there's a single flat `users` table (staff
members, each with a role -- viewer/analyst/admin) and no `team_id`
anywhere. The word "team" in existing code/docs always means "everyone
using this one deployment" (see the T12 cross-check `PLAN.md`'s
"this app is single-tenant per deployment" note, and `demo_seed.py`'s
docstring: "this codebase has no per-account data isolation").

But per-team quotas, a per-team usage meter, and "admin raises a
specific team's limit" only make sense if multiple independent
testing orgs can exist and be capped independently -- which requires
a real team entity. Recommended default: add a minimal `teams` table
and a `team_id` column on `users`. Every existing user is migrated
into one `Legacy` team (so nothing breaks for current logins); going
forward, an admin creates a team (name + optional quota/budget
overrides) when onboarding a new tester org and assigns each of that
org's users to it via the existing `POST /team/members` /
`PATCH /team/members/<id>` routes (extended with an optional
`team_id`). A user with no `team_id` is temporarily blocked from the
extraction/upload routes with a clear 403 ("not assigned to a team
yet -- ask an admin") rather than silently exempted from every limit
in this feature. Flag if a different meaning of "team" was intended.

## 1. Data model (`database.py`)

- New `teams` table: `id`, `name`, `monthly_document_quota` (nullable
  int -- NULL means "use the config default"), `monthly_page_quota`
  (nullable int, same convention), `monthly_budget_usd` (nullable
  float, same convention), `budget_alert_50_sent_month` /
  `budget_alert_80_sent_month` (nullable `TEXT` "YYYY-MM", so each
  threshold alert fires at most once per calendar month per team --
  compared against the current month string, so it "resets" for free
  every month with no cron needed), `created_at`.
- `users` gets a nullable `team_id` FK (migration adds the column,
  creates the one `Legacy` team, points every existing user at it --
  same rename/recreate SQLite migration style `database.py`'s other
  `_migrate_*` functions already use).
- New `usage_events` table: `id`, `team_id`, `user_id`, `lease_id`
  (nullable -- a rejected/failed upload still logs an attempt),
  `pages` (int, nullable if unknown), `input_tokens`, `output_tokens`
  (both nullable -- absent when the regex engine was used, since
  there's no API call to meter), `estimated_cost_usd` (nullable, same
  reason), `event_type` (`"extraction"` for now, room to grow),
  `created_at`. One row per real extraction attempt (success or
  failure), not a running counter -- monthly usage is always computed
  by summing/counting this table for the current month, the same
  "one source of truth, no drift" principle `portfolio_health_score.py`
  already had to learn the hard way (see its own DECISIONS.md entry
  about orphaned-row double-counting). No separate rollup table to
  keep in sync.
- `leases` gets a new `content_hash` column (sha256 hex, indexed) for
  the dedup check below.

## 2. Config (`app/usage_limits_config.py`, new file)

One file, plain module-level constants, matching this codebase's
existing "constants live near where they're used" convention
(`_T12_MATERIALITY_THRESHOLD_PCT_DEFAULT` etc.):

```
DEFAULT_MONTHLY_DOCUMENT_QUOTA = 200
DEFAULT_MONTHLY_PAGE_QUOTA = 2000
DEFAULT_MONTHLY_BUDGET_USD = 50.0
MAX_PAGES_PER_FILE = 150
MAX_FILE_SIZE_MB = 25
EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE = 10
# Fork fills these in from the real model/pricing constant already
# used in ai_extraction.py -- used only to estimate spend for the
# budget alert, never billed anywhere.
COST_PER_INPUT_TOKEN_USD = ...
COST_PER_OUTPUT_TOKEN_USD = ...
BUDGET_ALERT_THRESHOLD_PCTS = [50, 80]
```

A team's `teams.monthly_document_quota`/`monthly_page_quota`/
`monthly_budget_usd` being non-NULL overrides the matching default
above for that team only.

## 3. Quota + file-limit enforcement (`app/usage_limits.py`, new module)

- `check_team_quota(team_id) -> Optional[str]`: returns a plain-English
  block message ("Your team has used all 200 documents included this
  month. Contact an admin to raise your limit.") if this month's
  `usage_events` count/page-sum for the team already meets or exceeds
  its effective quota, else `None`. Computed fresh each call (current
  calendar month, `usage_events.created_at`), not cached.
- `check_file_limits(file_bytes, filename) -> Optional[str]`: rejects
  (returns a friendly message) over `MAX_FILE_SIZE_MB` or (after a
  cheap page-count check, reusing whatever page-counting helper
  `pdf_extractor.py`/`document_extractor.py` already has for PDFs;
  non-PDF formats without a "page count" skip that specific check and
  rely on the size check) over `MAX_PAGES_PER_FILE`.
- `find_duplicate_upload(team_id, content_hash) -> Optional[dict]`:
  looks up an existing, non-superseded lease for this team whose
  stored `content_hash` matches. Returns that lease's effective
  fields if found.
- `log_usage_event(team_id, user_id, lease_id, pages, token_usage,
  event_type) -> None`: inserts one `usage_events` row, computes
  `estimated_cost_usd` from the config's per-token rates, then checks
  the team's monthly spend against `BUDGET_ALERT_THRESHOLD_PCTS` and
  fires `email_service.send_operational_alert` (reusing the existing
  function and `ADMIN_EMAIL` convention) exactly once per threshold
  per month, using the new `budget_alert_*_sent_month` guard columns.
- `_extraction_rate_limited(user_id) -> bool` /
  `_reset_extraction_rate_limit_for_tests()`: same in-memory
  timestamp-window pattern as `api.py`'s existing login/forgot-password
  limiters and `email_service.py`'s `_rate_limited`, just keyed by user
  id instead of IP/email.

## 4. Content-hash dedup

This app never stores raw uploaded file bytes -- confirmed:
`document_extractor.py`'s pipeline goes straight from bytes to
extracted text/fields. So dedup only needs the hash, computed once at
upload time (`hashlib.sha256(file_bytes).hexdigest()`), stored on the
new `leases.content_hash` column.

On every upload route that calls `_extract_leases_from_file_storage`
(`/leases`, `/leases/batch`; `/leases/sample` is handled separately
below): compute the hash first. If `find_duplicate_upload` finds a
match for this team, skip extraction entirely, log a `usage_events`
row with `event_type="dedup_reuse"` and null token/cost fields (no API
call happened), and return the existing lease's data with
`"reused_existing_upload": true` in the response rather than creating
a new row or re-extracting.

## 5. Route changes (`api.py`)

- `_validate_upload()` (already called by every upload route) extended
  to also run `check_file_limits`, `check_team_quota`, and
  `_extraction_rate_limited`, in that order (cheapest checks first),
  returning the existing `(message, status)` tuple shape on failure --
  400 for file limits, 403 for quota/team-not-assigned, 429 for rate
  limit, each with a plain-English message.
- `_extract_leases_from_file_storage` (or its callers) gets the hash
  dedup check inserted before it would otherwise call into AI
  extraction, and every real call now logs a `usage_events` row via
  `log_usage_event` (success or failure -- a failed extraction still
  cost tokens if it got that far).
- New `GET /team/usage` (`@require_role('analyst')`, scoped to the
  caller's own `team_id` -- never another team's, no override param,
  same isolation convention `assistant.py`'s conversations already
  use): returns `{"documents_used": N, "documents_quota": N,
  "pages_used": N, "pages_quota": N, "month": "YYYY-MM",
  "message": "127 of 200 documents used this month." | the at-cap
  plain-English block message}`.
- `POST /team/members` / `PATCH /team/members/<id>` (existing,
  admin-only) gain an optional `team_id` field.
- New `POST /teams` (`@require_role('admin')`): create a team, optional
  quota/budget overrides.
- New `PATCH /teams/<id>` (`@require_role('admin')`): raise (or lower)
  a specific team's quota/budget overrides.
- New `GET /teams` (`@require_role('admin')`): list teams for the
  admin UI to manage.

## 6. Fix `/leases/sample` (item 4)

Currently calls the real `_extract_leases_from_file_storage` pipeline
live on every call (its own docstring says so explicitly: "never a
canned/fake response"). That's a real, direct violation of "sample
data must be precomputed and never call the API." Fix: precompute the
bundled sample lease's extraction result once (a checked-in JSON
fixture, generated once by actually running extraction against
`_SAMPLE_LEASE_PATH` during this implementation) and have the route
persist that precomputed result directly via the same
`_persist_split_leases` call, never touching
`_extract_leases_from_file_storage` at all. No API call, no
`usage_events` row.

`demo_seed.py` (the separate `DEMO_MODE` deployment) was checked
separately and already never calls the API -- it seeds hardcoded
account/lease rows directly into a dedicated demo database. No change
needed there; noted here rather than skipped silently, per item 4's
own fallback instruction.

## 7. Isolation & roles

- Every new/extended route requires at least `@require_role('analyst')`
  to act, `@require_role('admin')` for team-management writes
  (create/raise-limit) -- `admin` is a real, distinct role rank
  (`ROLE_RANK = {"viewer": 0, "analyst": 1, "admin": 2}` in
  `auth.py`), separate from `require_owner()` which stays reserved for
  the existing true-owner-only action set.
- Every read (`GET /team/usage`) is scoped to `session`'s own
  `team_id`, server-side, never a client-supplied team id -- the same
  "no override param" isolation convention already established for
  `/assistant/conversations` and `/today`.
- A user with `team_id IS NULL` gets a clear 403 on every
  quota-gated route rather than silently bypassing every limit.

## 8. Tests -- Anthropic API mocked everywhere

Every new test that exercises the AI extraction path uses
`test_ai_extraction.py`'s existing pattern exactly: a `mock.Mock()`
client with `fake_response.usage = mock.Mock(input_tokens=..,
output_tokens=..)`, passed via `extract_lease_fields(..., client=...)`
-- never a real `ANTHROPIC_API_KEY` call, never dependent on
`LEASE_EXTRACTION_ENGINE`'s env value (`run_all_tests.py` already
forces `regex` suite-wide, so any test needing to exercise the
token-logging/budget-alert path calls the AI path directly with a
mock client rather than relying on the env switch).

New files, following this project's plain-script `test_*.py`
convention (`sys.path.insert`, manual asserts, `if __name__ ==
"__main__"` runner -- see `test_t12_statement.py` for the exact
shape) and registered in `run_all_tests.py`'s `UNIT_TESTS` list:

- `test_usage_limits.py`: quota block/allow at the boundary, file
  size/page-count rejection with the right message, dedup-by-hash
  reuse (no API call made -- assert the mock client's `.create` was
  never invoked), rate limit trip and reset, budget-alert email fires
  exactly once per threshold per month (mock
  `email_service.send_operational_alert` and assert call count),
  admin-only team creation/limit-raise 403s for a non-admin.
- `test_leases_sample_precomputed.py` (or extend an existing upload
  test file if one already covers `/leases/sample`): asserts the
  route no longer calls the real extraction pipeline (mock/patch
  `_extract_leases_from_file_storage` and assert it's never called)
  and still returns the correct sample fields.
- Route-level 403/429/400 checks for every new/extended endpoint,
  mirroring `test_route_authorization.py`'s existing per-route
  pattern.

Run the full suite (`python run_all_tests.py`, unit tests only, no
`--live`, no localhost server) and fix failures until everything
passes except this environment's pre-existing, already-documented
gaps (missing `tesseract`/`poppler` system binaries -- confirmed
separately as `test_extraction.py`, `test_synthetic_accuracy.py`,
`test_multi_lease_detection.py`, `test_document_extractor.py` failing
the same way on this machine even before this feature's work).

## 9. `SUMMARY.md`

Plain-English writeup for a non-technical reader: what got added, the
`teams` concept and why it was introduced, the actual default numbers
chosen, what a tester sees when they hit a limit, and confirmation
that sample/demo paths never call the API. No demo-deal feature beyond
`/leases/sample` and `demo_seed.py` exists in this codebase --
confirmed by search -- noted here per item 4's fallback instruction.

## Order of work

1. `teams`/`usage_events`/`users.team_id`/`leases.content_hash`
   migrations in `database.py`.
2. `app/usage_limits_config.py` + `app/usage_limits.py`.
3. Wire into `_validate_upload()` / upload routes + new
   `/team/usage`, `/teams`, `/teams/<id>` routes.
4. Fix `/leases/sample` to use a precomputed fixture.
5. Tests (mocked Anthropic throughout), run full suite, fix failures.
6. `SUMMARY.md`.
7. Commit (clear message), push `feature/usage-limits`.
