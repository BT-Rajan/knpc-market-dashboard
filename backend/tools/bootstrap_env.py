"""
Non-interactive .env bootstrapper, invoked by installer.bat (Windows) /
installer.sh style flows after the backend venv + requirements are
installed. Reads plain values from environment variables (never from
argv, so passwords with special characters don't get mangled by shell
quoting), generates the secrets config.py requires, creates the MySQL
database if it doesn't exist yet, and writes backend/.env.

Required env vars: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (may
be empty string), ADMIN_PASSWORD, USER_PASSWORD.
Optional: DEEPSEEK_API_KEY, CLAUDE_API_KEY, ALLOWED_ORIGINS,
SCRAPE_FREQUENCY_MINUTES.

Idempotent: if backend/.env already exists, does nothing and exits 0 --
the installer is expected to check for this too, but this script checks
again so it's safe to call directly.
"""
import os
import secrets
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"


def fail(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if ENV_PATH.exists():
        print(f"[OK] {ENV_PATH} already exists, skipping generation")
        return

    db_host = os.environ.get("DB_HOST", "").strip()
    db_port = os.environ.get("DB_PORT", "").strip()
    db_name = os.environ.get("DB_NAME", "").strip()
    db_user = os.environ.get("DB_USER", "").strip()
    db_password = os.environ.get("DB_PASSWORD", "")
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    user_password = os.environ.get("USER_PASSWORD", "")

    if not (db_host and db_port and db_name and db_user):
        fail("DB_HOST, DB_PORT, DB_NAME, and DB_USER must all be set")
    if not admin_password or not user_password:
        fail("ADMIN_PASSWORD and USER_PASSWORD must both be set")

    try:
        import bcrypt
    except ImportError:
        fail("bcrypt is not installed in the venv -- run pip install -r requirements.txt first")
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        fail("cryptography is not installed in the venv -- run pip install -r requirements.txt first")
    try:
        import pymysql
    except ImportError:
        fail("pymysql is not installed in the venv -- run pip install -r requirements.txt first")

    print(f"Creating database `{db_name}` on {db_host}:{db_port} if it doesn't exist...")
    try:
        conn = pymysql.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        fail(
            f"Could not connect to MySQL / create database `{db_name}`: {exc}\n"
            "  Check that MySQL Server is installed and running, and that "
            f"DB_HOST/DB_PORT/DB_USER/DB_PASSWORD are correct for user '{db_user}'."
        )
    print(f"[OK] Database `{db_name}` ready")

    session_secret = secrets.token_urlsafe(48)
    encryption_key = Fernet.generate_key().decode()
    admin_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
    user_hash = bcrypt.hashpw(user_password.encode(), bcrypt.gensalt()).decode()

    allowed_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173")
    scrape_frequency = os.environ.get("SCRAPE_FREQUENCY_MINUTES", "30")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    claude_key = os.environ.get("CLAUDE_API_KEY", "")

    env_content = f"""DB_HOST={db_host}
DB_PORT={db_port}
DB_NAME={db_name}
DB_USER={db_user}
DB_PASSWORD={db_password}

SCRAPE_FREQUENCY_MINUTES={scrape_frequency}

SESSION_SECRET={session_secret}

ADMIN_PASSWORD_HASH={admin_hash}
USER_PASSWORD_HASH={user_hash}

ENCRYPTION_KEY={encryption_key}

ALLOWED_ORIGINS={allowed_origins}

DEEPSEEK_API_KEY={deepseek_key}
CLAUDE_API_KEY={claude_key}
"""
    ENV_PATH.write_text(env_content, encoding="utf-8")
    print(f"[OK] Wrote {ENV_PATH}")


if __name__ == "__main__":
    main()
