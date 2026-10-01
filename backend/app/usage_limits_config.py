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
