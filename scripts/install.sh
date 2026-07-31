#!/usr/bin/env bash
# KNPC Market Intelligence Dashboard - Linux/macOS installer.
# Assumes the MySQL DB/user already exist (see backend/schema.sql to create
# them). Reads DB + admin credentials from the environment or prompts for
# them -- never hardcode credentials in this script.
set -euo pipefail

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME:-knpc_dashboard}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

fail() { echo "FAILED: $1" >&2; exit 1; }

prompt() { # prompt VAR_NAME "Question" [default]
    local __var="$1" __q="$2" __default="${3:-}" __val=""
    if [ -n "${!__var:-}" ]; then return; fi
    read -r -p "$__q${__default:+ [$__default]}: " __val
    printf -v "$__var" '%s' "${__val:-$__default}"
}

prompt_secret() { # prompt_secret VAR_NAME "Question"
    local __var="$1" __q="$2" __val=""
    if [ -n "${!__var:-}" ]; then return; fi
    read -r -s -p "$__q: " __val
    echo
    printf -v "$__var" '%s' "$__val"
}

for bin in mysql python3 npm; do
  command -v "$bin" >/dev/null || fail "$bin not installed"
done

echo "==> [1/6] Database connection"
prompt DB_USER "MySQL user for this app"
prompt_secret DB_PASSWORD "MySQL password for $DB_USER"
mysql -u "$DB_USER" -p"$DB_PASSWORD" -h "$DB_HOST" "$DB_NAME" -e "SELECT 1;" \
  || fail "cannot connect as $DB_USER to $DB_NAME -- check credentials/grants (see backend/schema.sql)"

echo "==> [2/6] Admin account setup"
prompt_secret ADMIN_PASSWORD "Password for the 'admin' account"
prompt_secret USER_PASSWORD "Password for the 'user' (viewer) account"

echo "==> [3/6] Generating backend/.env"
cd "$BACKEND_DIR"
mkdir -p logs tmp_exports
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
ENCRYPTION_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
ADMIN_PASSWORD_HASH="$(python3 -c "import bcrypt,sys; print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt()).decode())" "$ADMIN_PASSWORD")"
USER_PASSWORD_HASH="$(python3 -c "import bcrypt,sys; print(bcrypt.hashpw(sys.argv[1].encode(), bcrypt.gensalt()).decode())" "$USER_PASSWORD")"

cat > "$BACKEND_DIR/.env" <<ENV
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
SESSION_SECRET=${SESSION_SECRET}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH}
USER_PASSWORD_HASH=${USER_PASSWORD_HASH}
ALLOWED_ORIGINS=http://localhost:5173
SCRAPE_FREQUENCY_MINUTES=30
DEEPSEEK_API_KEY=
CLAUDE_API_KEY=
ENV
unset ADMIN_PASSWORD USER_PASSWORD DB_PASSWORD
echo "[OK] backend/.env written (Gmail sending is configured later, from Admin -> Email in the app)"

echo "==> [4/6] Verifying the app imports with this config"
python -c "from app.main import app" || fail "app failed to import -- check backend/.env"
deactivate

echo "==> [5/6] Frontend build (served by FastAPI as static files)"
cd "$FRONTEND_DIR"
npm install --silent
npm run build
[ -d "$FRONTEND_DIR/dist" ] || fail "frontend build did not produce dist/"

echo "==> [6/6] Starting the backend"
cd "$BACKEND_DIR"
source venv/bin/activate
nohup python run.py > "$BACKEND_DIR/logs/server.log" 2>&1 &
BACKEND_PID=$!
deactivate
sleep 2

echo "==> Health check"
curl -sf "http://127.0.0.1:${BACKEND_PORT}/api/health" \
  && echo -e "\nOK - serving on :${BACKEND_PORT} (pid $BACKEND_PID)" \
  || fail "backend not responding -- check $BACKEND_DIR/logs/server.log"

echo "For production process management (auto-restart, log rotation), run"
echo "this under systemd or pm2 instead of the background nohup above."
