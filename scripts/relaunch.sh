#!/usr/bin/env bash
# Stop, delete, and relaunch the knpc-dashboard pm2 process from a clean
# slate. Unlike `pm2 restart` (which reuses the existing process entry and
# can carry over stale env/args from before an ecosystem.config.js or
# backend/.env change), this always re-registers it fresh.
set -euo pipefail

APP_NAME="knpc-dashboard"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

command -v pm2 >/dev/null || { echo "[ERROR] pm2 not found on PATH" >&2; exit 1; }
[ -f "ecosystem.config.js" ] || { echo "[ERROR] ecosystem.config.js not found in $ROOT_DIR" >&2; exit 1; }

echo "==> Stopping ${APP_NAME} (if running)"
pm2 stop "$APP_NAME" 2>/dev/null || echo "   (not running)"

echo "==> Deleting ${APP_NAME} from pm2's process list"
pm2 delete "$APP_NAME" 2>/dev/null || echo "   (nothing to delete)"

echo "==> Relaunching from ecosystem.config.js"
pm2 start ecosystem.config.js

echo "==> Saving pm2 process list (survives a reboot / pm2 resurrect)"
pm2 save

echo
echo "==> Status"
pm2 status "$APP_NAME"

echo
echo "==> Logs (last 30 lines)"
pm2 logs "$APP_NAME" --lines 30 --nostream

PORT="$(grep -m1 '^PORT=' "$ROOT_DIR/backend/.env" 2>/dev/null | cut -d= -f2)"
PORT="${PORT:-8585}"
echo
echo "==> Health check"
healthy=0
for _ in 1 2 3 4 5; do
    if curl -sf "http://127.0.0.1:${PORT}/api/health" >/dev/null; then
        healthy=1
        break
    fi
    sleep 2
done
if [ "$healthy" -eq 1 ]; then
    echo "[OK] responding on :${PORT}"
else
    echo "[WARN] not responding on :${PORT} after 10s -- check the logs above."
fi
