# Usage Limits Feature — Plain-English Summary

## What This Does

This feature protects the team from accidentally burning through Anthropic API credits by implementing per-team quotas and usage tracking.

### Day-to-Day Impact

**For Team Members (analysts/viewers):**
- When you upload a lease, the system now checks if your team has hit its monthly limits before processing.
- If you re-upload the exact same PDF, the system recognizes it and reuses the extraction result instead of running it through the AI again, saving cost.
- If you try to upload more than 10 documents in a single minute, the request is rejected (rate limiting).
- You can visit `/team/usage` to see how many documents and pages your team has used this month.

**For Admin/Owner:**
- You can now manage teams (create, view, update quota overrides) via new `/teams` routes.
- The system sends email alerts when a team reaches 50% and 80% of its monthly budget.
- You can assign team members to different teams and manage their quotas independently.
- Monthly quotas reset automatically on the first of each month.

## What Changed in the Code

### New Tables
- **`teams`**: Stores team names and optional quota overrides (monthly_document_quota, monthly_page_quota, monthly_budget_usd). If a quota is NULL, it uses the system default.
- **`usage_events`**: Logs every extraction attempt (success or failure), including token counts and estimated costs.
- **`users.team_id`**: Every user is now assigned to a team (defaults to "Legacy" on first migration).
- **`leases.content_hash`**: SHA-256 hash of uploaded file content for duplicate detection.

### New Configuration (app/usage_limits_config.py)
Sets reasonable defaults that admins can override per-team:
- Monthly document quota: 200
- Monthly page quota: 2,000
- Monthly budget: $50 (USD)
- Max pages per file: 150
- Max file size: 25MB
- Extraction rate limit: 10 per user per minute
- Claude Sonnet 5 pricing: $3 per million input tokens, $15 per million output tokens

### Core Logic (app/usage_limits.py)
Five main functions:
1. **check_team_quota()**: Computes month-to-date usage from `usage_events` and rejects uploads if quota is exhausted.
2. **check_file_limits()**: Rejects oversized files or files with too many pages.
3. **find_duplicate_upload()**: Finds existing leases with the same content_hash and returns them instead of re-extracting.
4. **log_usage_event()**: Inserts a row in `usage_events` and fires budget-alert emails exactly once per threshold per month.
5. **_extraction_rate_limited()**: In-memory rate limiter tracking extraction attempts per user per minute.

### API Routes
- **GET /team/usage**: Shows current month's usage for caller's team (no admin bypass — you always see your own).
- **POST /teams**: Admin-only. Create a new team.
- **PATCH /teams/<id>**: Admin-only. Update team quota overrides.
- **GET /teams**: Admin-only. List all teams.
- **PATCH /team/members/<id>**: Extended with optional `team_id` field to reassign users.

### Upload Pipeline Changes
Every upload route (/leases, /leases/batch, /leases/sample, etc.) now:
1. Validates the team assignment and current quota.
2. Checks file size and page count.
3. Enforces per-user rate limit.
4. Computes content hash and checks for duplicate (reuses if found).
5. Logs the usage event after extraction (or logs a "dedup_reuse" event if the file already existed).

### Sample Lease Optimization
The `/leases/sample` route no longer calls the live extraction pipeline. Instead, it loads a precomputed fixture (JSON) to avoid burning API credits on demo/onboarding users. The fixture is stored at `backend/sample_data/sample_lease_fixture.json`.

## User-Facing Messages

When a quota is hit:
- "Your team has used all 200 documents included this month. Contact an admin to raise your limit."
- "Your team has used all 2,000 pages included this month. Contact an admin to raise your limit."

When a file is too large:
- "File too large: X.XMB exceeds limit of 25MB."

When rate-limited:
- "Rate limit exceeded: maximum 10 extractions per minute."

When a duplicate is detected:
- HTTP 200 with a flag `"reused_existing_upload": true` and the existing lease data.

## Migration & Backward Compatibility

All database migrations run automatically on first boot via `_migrate_*` functions in `database.py`:
- Existing single-tenant deployments get a "Legacy" team.
- All existing users are assigned to the Legacy team.
- Existing leases get NULL `content_hash` (dedup only applies to new uploads).
- Monthly quotas reset automatically using `strftime('%Y-%m', created_at)`.

Admin users must be aware:
- After the first login following deployment, users should see `team_id` in their session.
- The system is backward-compatible with old API clients (team_id is optional in requests; it falls back to the logged-in user's team).

## Testing

Two new plain-script test files (no pytest required):
1. **test_usage_limits.py**: Tests quota checks, file limits, dedup, rate limiting, and budget alerts. All tests pass.
2. **test_leases_sample_precomputed.py**: Tests that /leases/sample loads a fixture instead of calling the extraction pipeline. All tests pass.

The Anthropic API is mocked in all tests (never a real API call, even under test).

## Numbers

**Default quotas** (can be overridden per team):
- 200 documents per month
- 2,000 pages per month
- $50 USD per month
- 10 extractions per user per minute (burst limit)

**Pricing** (used for budget tracking only, not billed):
- Claude Sonnet 5: $3 per million input tokens, $15 per million output tokens

**Budget alerts**: Fire at 50% and 80% of monthly budget, exactly once per threshold per month.

## Deployment Notes

No new environment variables required. Existing setup works unchanged. If ADMIN_EMAIL is set, budget alerts will be sent there; otherwise, they silently skip (no error).

The feature is transparent to end users until a quota is hit or they visit `/team/usage` to check usage.
