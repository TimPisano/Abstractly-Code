#!/bin/zsh
# (Re)start the local auth E2E stack: the API on :5731 with emails captured to
# $AUTH_E2E_DIR/outbox (never sent unless REAL_EMAIL=1), and the static site on
# :8731. Restarting clears the in-memory rate limits between runs.
# Extra env (SMTP_DELAY=10, SELF_SERVE_SIGNUP_ENABLED=...) passes through.
set -e
HERE=${0:A:h}; REPO=${HERE:h:h:h}
DIR=${AUTH_E2E_DIR:-${TMPDIR:-/tmp}/abstractly-auth-e2e}; mkdir -p "$DIR/outbox"
pkill -f "auth-e2e/devserver.py" 2>/dev/null || true
lsof -tiTCP:8731 -sTCP:LISTEN >/dev/null 2>&1 || (cd "$REPO/frontend" && nohup python3 -m http.server 8731 >/dev/null 2>&1 &)
sleep 1
OUTBOX="$DIR/outbox" DB_PATH="$DIR/e2e.db" SELF_SERVE_SIGNUP_ENABLED=${SELF_SERVE_SIGNUP_ENABLED:-true} \
  ADMIN_ALLOWED_ORIGINS=http://localhost:8731 FLASK_SECRET_KEY=auth-e2e-local-only PORT=5731 \
  nohup "$REPO/backend/venv/bin/python" "$HERE/devserver.py" > "$DIR/devserver.log" 2>&1 &
for i in {1..30}; do curl -s http://127.0.0.1:5731/auth/options >/dev/null && break; sleep 0.5; done
curl -s http://127.0.0.1:5731/auth/options; echo
