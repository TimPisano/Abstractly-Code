# Auth E2E (headless)

Browser checks for the account flows: signup, finish setup, forgot/reset, keep me
signed in, two tabs, back button, double clicks, dead links, slow email, mobile.
Headless Playwright only, never a visible browser (CLAUDE.md rule 1). Emails are
captured to `$AUTH_E2E_DIR/outbox/*.json`, not sent.

```bash
npx -y playwright@latest install chromium webkit      # once
.claude/tools/auth-e2e/run-local.sh                   # API :5731 + site :8731
node .claude/tools/auth-e2e/flows.mjs chromium desktop  # 41 checks; also: webkit mobile, chromium tablet|mobile
.claude/tools/auth-e2e/run-local.sh && node .claude/tools/auth-e2e/round4.mjs webkit
SMTP_DELAY=10 .claude/tools/auth-e2e/run-local.sh && node .claude/tools/auth-e2e/round2.mjs chromium
```

Restart with `run-local.sh` between scripts: each one signs up several accounts
from 127.0.0.1, and the per-IP signup limit (10/hour) is real. `round2.mjs` stops
the API on purpose (its "server unreachable" check). Screenshots land in
`$AUTH_E2E_DIR/shots/`; open and look at them before claiming anything visual.
What each round covers: `AUTH_NOTES.md`.
