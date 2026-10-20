#!/bin/zsh
# (Re)start a local stack for tester-ready.mjs: API on :5741 with team invites
# on, a throwaway owner account, emails captured to $AUTH_E2E_DIR/outbox (never
# sent), and the static site on :8741. Separate ports from run-local.sh so the
# two can't collide. Prints the env tester-ready.mjs needs.
set -e
HERE=${0:A:h}; REPO=${HERE:h:h:h}
DIR=${AUTH_E2E_DIR:-${TMPDIR:-/tmp}/abstractly-tester-ready-e2e}
mkdir -p "$DIR/outbox"
OWNER_EMAIL=owner@abstractly.test
OWNER_PASSWORD="local owner passphrase only"
OWNER_HASH=$("$REPO/backend/venv/bin/python" -c "import bcrypt,sys; print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt()).decode())" "$OWNER_PASSWORD")
"$REPO/backend/venv/bin/python" "$REPO/backend/tests/create_sample_lease.py" >/dev/null 2>&1 || true
LEASE_PDF="$DIR/harbor-sample-lease.pdf"
cp "$REPO/backend/tests/sample_lease.pdf" "$LEASE_PDF"

pkill -f "auth-e2e/devserver.py.*5741" 2>/dev/null || true
lsof -tiTCP:5741 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true
lsof -tiTCP:8741 -sTCP:LISTEN >/dev/null 2>&1 || (cd "$REPO/frontend" && nohup python3 -m http.server 8741 >/dev/null 2>&1 &)
sleep 1
OUTBOX="$DIR/outbox" DB_PATH="$DIR/tester-ready-$(date +%s).db" TEAM_INVITES_ENABLED=true \
  ADMIN_EMAIL="$OWNER_EMAIL" ADMIN_PASSWORD_HASH="$OWNER_HASH" \
  ADMIN_ALLOWED_ORIGINS=http://localhost:8741 FLASK_SECRET_KEY=tester-ready-e2e-local-only PORT=5741 \
  nohup "$REPO/backend/venv/bin/python" "$HERE/devserver.py" 5741 > "$DIR/devserver.log" 2>&1 &
for i in {1..40}; do curl -s http://127.0.0.1:5741/health >/dev/null && break; sleep 0.5; done
curl -s http://127.0.0.1:5741/health; echo
echo "export AUTH_E2E_DIR='$DIR' OWNER_EMAIL='$OWNER_EMAIL' OWNER_PASSWORD='$OWNER_PASSWORD' LEASE_PDF='$LEASE_PDF'"
