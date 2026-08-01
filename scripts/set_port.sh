#!/usr/bin/env bash
# Change the port this app runs on -- updates the live config (backend/.env,
# frontend/.env) if present, and the project-wide defaults baked into
# source (config.py, run.py, vite.config.ts, .env.example files, both
# installers) so a fresh clone/install also uses the new port.
#
# Usage: scripts/set_port.sh <port>
set -euo pipefail

if [ $# -ne 1 ] || ! [[ "$1" =~ ^[0-9]+$ ]] || [ "$1" -lt 1 ] || [ "$1" -gt 65535 ]; then
    echo "Usage: $0 <port>   (1-65535)" >&2
    exit 1
fi

NEW_PORT="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

changed=0

upsert_env_var() { # upsert_env_var FILE KEY VALUE
    local file="$1" key="$2" value="$3"
    [ -f "$file" ] || return 0
    if grep -q "^${key}=" "$file"; then
        sed -i.bak "s#^${key}=.*#${key}=${value}#" "$file" && rm -f "${file}.bak"
    else
        printf '%s=%s\n' "$key" "$value" >> "$file"
    fi
    echo "  updated $file"
    changed=1
}

replace_default() { # replace_default FILE PATTERN REPLACEMENT
    local file="$1" pattern="$2" replacement="$3"
    [ -f "$file" ] || return 0
    if grep -q "$pattern" "$file"; then
        if sed -i.bak "s#${pattern}#${replacement}#g" "$file"; then
            rm -f "${file}.bak"
            echo "  updated $file"
            changed=1
        else
            echo "  FAILED to update $file (pattern: $pattern)" >&2
            rm -f "${file}.bak"
            exit 1
        fi
    fi
}

echo "==> Live config (only touched if the file exists)"
upsert_env_var "backend/.env" "PORT" "$NEW_PORT"
upsert_env_var "frontend/.env" "BACKEND_PORT" "$NEW_PORT"

echo "==> Project defaults (so a fresh clone/install also uses :$NEW_PORT)"
replace_default "backend/.env.example" '^PORT=[0-9]\+' "PORT=${NEW_PORT}"
replace_default "backend/app/config.py" 'os\.getenv("PORT", "[0-9]\+")' "os.getenv(\"PORT\", \"${NEW_PORT}\")"
replace_default "backend/tools/bootstrap_env.py" 'os\.environ\.get("PORT", "[0-9]\+")' "os.environ.get(\"PORT\", \"${NEW_PORT}\")"
replace_default "frontend/.env.example" '^BACKEND_PORT=[0-9]\+' "BACKEND_PORT=${NEW_PORT}"
replace_default "frontend/vite.config.ts" "env\.BACKEND_PORT || '[0-9]\+'" "env.BACKEND_PORT || '${NEW_PORT}'"
replace_default "scripts/install.sh" 'BACKEND_PORT:-[0-9]\+' "BACKEND_PORT:-${NEW_PORT}"
replace_default "scripts/install.bat" 'set "APP_PORT_IN=[0-9]\+"' "set \"APP_PORT_IN=${NEW_PORT}\""
replace_default "scripts/install.bat" 'App port \[[0-9]\+\]' "App port [${NEW_PORT}]"
replace_default "scripts/install.bat" 'set "DISPLAY_PORT=[0-9]\+"' "set \"DISPLAY_PORT=${NEW_PORT}\""

if [ "$changed" -eq 0 ]; then
    echo "Nothing matched -- is this being run from the repo root/scripts dir?"
    exit 1
fi

echo
echo "Done. Port is now ${NEW_PORT} everywhere it's tracked."
echo "If the app is already running, restart it for this to take effect:"
echo "  cd backend && source venv/bin/activate && python run.py"
