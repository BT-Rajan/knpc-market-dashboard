#!/usr/bin/env bash
# KNPC Market Intelligence Dashboard - Linux/macOS installer.
# Prerequisites: Python 3.10+, Node.js 18+, a reachable MySQL Server with a
# user/password that can create databases. No mysql.exe/mysql CLI required --
# the database is created via pymysql (see backend/tools/bootstrap_env.py).
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8585}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
ENV_FILE="$BACKEND_DIR/.env"

fail() { echo "[ERROR] $1" >&2; exit 1; }

for bin in python3 npm; do
  command -v "$bin" >/dev/null || fail "$bin not installed"
done

NEED_ENV_BOOTSTRAP=0
if [ -f "$ENV_FILE" ]; then
    echo "[OK] backend/.env already exists - skipping configuration prompts."
    echo "     Delete backend/.env and re-run this installer to reconfigure."
else
    NEED_ENV_BOOTSTRAP=1
    echo "==> Configuration - this runs once and is saved to backend/.env"
    read -r -p "MySQL host [localhost]: " DB_HOST; DB_HOST="${DB_HOST:-localhost}"
    read -r -p "MySQL port [3306]: " DB_PORT; DB_PORT="${DB_PORT:-3306}"
    read -r -p "Database name [knpc_dashboard]: " DB_NAME; DB_NAME="${DB_NAME:-knpc_dashboard}"
    read -r -p "MySQL user [root]: " DB_USER; DB_USER="${DB_USER:-root}"
    read -r -s -p "MySQL password (blank if none): " DB_PASSWORD; echo
    read -r -p "App port [${BACKEND_PORT}]: " APP_PORT; APP_PORT="${APP_PORT:-$BACKEND_PORT}"
    while true; do
        read -r -s -p "New password for the 'admin' account (required): " ADMIN_PASSWORD; echo
        [ -n "$ADMIN_PASSWORD" ] && break
        echo "This value is required."
    done
    while true; do
        read -r -s -p "New password for the 'user' (viewer) account (required): " USER_PASSWORD; echo
        [ -n "$USER_PASSWORD" ] && break
        echo "This value is required."
    done
    read -r -p "DeepSeek API key (optional, press Enter to skip): " DEEPSEEK_API_KEY
    read -r -p "Claude API key (optional, press Enter to skip): " CLAUDE_API_KEY
fi

echo "==> Backend setup (FastAPI)"
cd "$BACKEND_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
echo "Installing Python dependencies..."
pip install -r requirements.txt || fail "pip install failed -- see output above"
echo "[OK] Python dependencies installed"

if [ "$NEED_ENV_BOOTSTRAP" = "1" ]; then
    echo "Generating backend/.env and creating the database..."
    DB_HOST="$DB_HOST" DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" USER_PASSWORD="$USER_PASSWORD" PORT="$APP_PORT" \
    DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}" CLAUDE_API_KEY="${CLAUDE_API_KEY:-}" \
        python tools/bootstrap_env.py || fail "failed to generate backend/.env -- see output above"
    unset DB_PASSWORD ADMIN_PASSWORD USER_PASSWORD
    BACKEND_PORT="$APP_PORT"
fi

if [ -f "$ENV_FILE" ]; then
    EXISTING_PORT="$(grep -m1 '^PORT=' "$ENV_FILE" | cut -d= -f2)"
    [ -n "$EXISTING_PORT" ] && BACKEND_PORT="$EXISTING_PORT"
fi

echo "Verifying Python imports..."
python -c "from app.main import app; print('[OK] FastAPI app imports successfully')" \
  || fail "app failed to import -- check backend/.env"

mkdir -p logs tmp_exports
deactivate

echo "==> Frontend setup (React + Vite)"
cd "$FRONTEND_DIR"
echo "BACKEND_PORT=${BACKEND_PORT}" > .env
npm install --silent || fail "npm install failed"
npm run build || fail "frontend build failed"
[ -d "$FRONTEND_DIR/dist" ] || fail "frontend build did not produce dist/"
echo "[OK] Frontend built successfully"

echo
echo "==> Installation complete."
echo "Gmail sending is NOT set here -- log in as admin and set it under"
echo "Admin -> Email -> Gmail Settings (uses an App Password, not your"
echo "account password)."
echo
echo "Start it:"
echo "  cd backend && source venv/bin/activate && python run.py"
echo "  (serves on :${BACKEND_PORT}, including the built frontend)"
echo
echo "For production process management (auto-restart, log rotation), run"
echo "this under systemd or pm2 instead of a plain foreground process."
