"""
Minimal auth for two fixed accounts (admin / viewer). No user table,
no signup — matches the brief. Tokens are a signed, timestamped blob so we
don't need a sessions table either. Passwords are bcrypt-hashed at rest
(config.py loads the hashes from env) and a simple in-memory rate limiter
throttles repeated failed logins per username.
"""
import base64
import hashlib
import hmac
import time
import bcrypt
from fastapi import Depends, Header, HTTPException, Request, status

from app.config import USERS, SESSION_SECRET, SESSION_TTL_HOURS

# username -> (fail_count, locked_until_epoch)
_login_attempts: dict[str, tuple[int, float]] = {}
_MAX_ATTEMPTS = 5
_LOCKOUT_SECONDS = 300


def _sign(payload: str) -> str:
    return hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(username: str, role: str) -> str:
    expiry = int(time.time()) + SESSION_TTL_HOURS * 3600
    payload = f"{username}:{role}:{expiry}"
    sig = _sign(payload)
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _is_locked(username: str) -> bool:
    fail_count, locked_until = _login_attempts.get(username, (0, 0))
    return locked_until > time.time()


def _record_failure(username: str):
    fail_count, _ = _login_attempts.get(username, (0, 0))
    fail_count += 1
    locked_until = time.time() + _LOCKOUT_SECONDS if fail_count >= _MAX_ATTEMPTS else 0
    _login_attempts[username] = (fail_count, locked_until)


def _clear_failures(username: str):
    _login_attempts.pop(username, None)


def verify_credentials(username: str, password: str):
    if _is_locked(username):
        return None
    user = USERS.get(username)
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        # Still run a dummy check when the user doesn't exist to keep timing
        # roughly constant and avoid leaking valid usernames.
        if not user:
            bcrypt.checkpw(password.encode(), bcrypt.gensalt())
        _record_failure(username)
        return None
    _clear_failures(username)
    return user["role"]


def _decode_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        username, role, expiry, sig = raw.split(":")
    except Exception:
        return None
    payload = f"{username}:{role}:{expiry}"
    if not hmac.compare_digest(_sign(payload), sig):
        return None
    if int(expiry) < time.time():
        return None
    return {"username": username, "role": role}


def get_current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ").strip()
    session = _decode_token(token)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    return session


def get_current_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
