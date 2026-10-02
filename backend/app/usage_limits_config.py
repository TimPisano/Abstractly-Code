"""
Usage limits and quotas for protecting Anthropic API spend.

These module-level constants define the default limits for all teams.
A team's teams.monthly_document_quota, monthly_page_quota, or monthly_budget_usd
being non-NULL overrides the matching default below for that team only.
"""

# Default monthly quotas (per team). Can be overridden per team.
DEFAULT_MONTHLY_DOCUMENT_QUOTA = 200
DEFAULT_MONTHLY_PAGE_QUOTA = 2000
DEFAULT_MONTHLY_BUDGET_USD = 50.0

# Per-file constraints (hard limits, not per-team).
MAX_PAGES_PER_FILE = 150
MAX_FILE_SIZE_MB = 25

# Rate limiting per user (extraction endpoints only).
EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE = 10

# Anthropic Claude Sonnet 5 pricing (as of model release).
# Used to estimate spend in budget-alert logic, never billed anywhere.
COST_PER_INPUT_TOKEN_USD = 3.0 / 1_000_000
COST_PER_OUTPUT_TOKEN_USD = 15.0 / 1_000_000

# Budget alert thresholds: fire exactly once per month when monthly
# spend reaches these percentages of monthly_budget_usd.
BUDGET_ALERT_THRESHOLD_PCTS = [50, 80]

# ----------------------------------------------------------------------
# Deal assistant: a separate monthly dollar allowance from the
# extraction budget above -- a team that's burned through its
# extraction budget should still be able to ask the assistant
# questions about leases it's already uploaded, and vice versa. Same
# override pattern: teams.monthly_assistant_credit_usd non-NULL wins
# over this default for that team.
# ----------------------------------------------------------------------
DEFAULT_MONTHLY_ASSISTANT_CREDIT_USD = 15.0

# Claude Haiku 4.5 pricing -- the assistant's default model (see
# ASSISTANT_MODEL in app/assistant.py), deliberately a cheaper tier
# than extraction's Sonnet pricing above since this is direct-answer
# chat Q&A, not multi-field structured extraction. If ASSISTANT_MODEL
# is overridden to a different tier, these two constants should be
# updated to match -- same caveat as COST_PER_INPUT_TOKEN_USD above.
ASSISTANT_COST_PER_INPUT_TOKEN_USD = 1.0 / 1_000_000
ASSISTANT_COST_PER_OUTPUT_TOKEN_USD = 5.0 / 1_000_000

# Per-user rate limit on assistant questions (separate limiter from
# EXTRACTION_RATE_LIMIT_PER_USER_PER_MINUTE above -- asking questions
# and uploading documents are different endpoints with different
# abuse profiles).
ASSISTANT_RATE_LIMIT_PER_USER_PER_MINUTE = 20
