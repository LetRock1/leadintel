#!/usr/bin/env bash
# X Education CRM on macOS or Linux: install what is missing, prepare the data, and start the API, the website and
# the CRM in the background (logs in backend/data/logs). ./stop-all.sh stops them.
# The first start takes about 15 minutes (packages, models, the six-month simulated history); later starts take
# seconds. Needs Python 3.10 or newer (3.12 recommended) and Node.js 20.19 or newer.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
RUN="$ROOT/backend/data/run"
LOGS="$ROOT/backend/data/logs"
export PYTHONUTF8=1 PIP_DISABLE_PIP_VERSION_CHECK=1

say() { printf '  %s\n' "$*"; }
fail() { printf '\n  %s\n  Fix the problem above and run ./start-all.sh again.\n' "$*" >&2; exit 1; }
hash_of() { "${PY:-python3}" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1"; }

printf '\n  X Education CRM\n  ===============\n\n'

PY=""
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
    "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.10 or newer was not found (https://www.python.org/downloads/)."
command -v node >/dev/null 2>&1 || fail "Node.js was not found (https://nodejs.org/, the LTS version)."
node -e "const [a,b]=process.versions.node.split('.').map(Number);process.exit(a>20||(a===20&&b>=19)?0:1)" ||
  fail "Node.js 20.19 or newer is needed (https://nodejs.org/)."

VPY="$ROOT/backend/.venv/bin/python"
if [ ! -x "$VPY" ]; then
  say "[1/5] Creating the Python environment in backend/.venv ..."
  "$PY" -m venv "$ROOT/backend/.venv"
else
  say "[1/5] Python environment found."
fi
if [ "$(hash_of "$ROOT/backend/requirements.txt")" != "$(cat "$ROOT/backend/.venv/requirements.sha" 2>/dev/null)" ]; then
  say "[2/5] Installing the API's packages (a few minutes the first time) ..."
  "$VPY" -m pip install --quiet --upgrade pip
  "$VPY" -m pip install -r "$ROOT/backend/requirements.txt"
  hash_of "$ROOT/backend/requirements.txt" > "$ROOT/backend/.venv/requirements.sha"
else
  say "[2/5] API packages are up to date."
fi

[ -f "$ROOT/backend/.env" ] || cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"

say "[3/5] Preparing the database and the models ..."
(cd "$ROOT/backend" && "$VPY" -m app.cli bootstrap) || fail "Preparing the data failed."

if [ "$(hash_of "$ROOT/frontend/package-lock.json")" != "$(cat "$ROOT/frontend/node_modules/.lock.sha" 2>/dev/null)" ]; then
  say "[4/5] Installing the website's and the CRM's packages (a few minutes the first time) ..."
  (cd "$ROOT/frontend" && npm ci --no-audit --no-fund) || fail "Installing the frontend packages failed."
  hash_of "$ROOT/frontend/package-lock.json" > "$ROOT/frontend/node_modules/.lock.sha"
else
  say "[4/5] Website and CRM packages are up to date."
fi

say "[5/5] Starting the API, the website and the CRM ..."
"$ROOT/stop-all.sh" quiet || true
mkdir -p "$RUN" "$LOGS"
(cd "$ROOT/backend" && nohup "$VPY" -m app.cli serve > "$LOGS/api.out" 2>&1 & echo $! > "$RUN/api.pid")
(cd "$ROOT/frontend" && nohup npm run dev -w web > "$LOGS/website.out" 2>&1 & echo $! > "$RUN/website.pid")
(cd "$ROOT/frontend" && nohup npm run dev -w crm > "$LOGS/crm.out" 2>&1 & echo $! > "$RUN/crm.pid")

for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    printf '\n  Running:\n'
    say "  Website (learners)   http://localhost:5173"
    say "  CRM (the team)       http://localhost:5174"
    say "  API documentation    http://127.0.0.1:8000/api/docs"
    say "  Logs                 backend/data/logs"
    if [ -f "$ROOT/backend/data/initial-admin-password.txt" ]; then
      printf '\n  First sign-in to the CRM (you choose your own password straight after):\n'
      grep -E '^ +(email|password) ' "$ROOT/backend/data/initial-admin-password.txt" | sed 's/^ */    /' || true
    fi
    printf '\n  Without email set up in backend/.env, sign-up codes are written to backend/data/logs/api.out.\n'
    printf '  To stop everything: ./stop-all.sh\n\n'
    exit 0
  fi
  sleep 2
done
fail "The API did not answer within two minutes. See backend/data/logs/api.out."
