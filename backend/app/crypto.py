"""Symmetric encryption for secrets we store in the DB (currently: the
Gmail app password). Uses the app-wide ENCRYPTION_KEY (Fernet) from .env --
never store this kind of credential in plaintext."""
from cryptography.fernet import Fernet, InvalidToken

from app.config import ENCRYPTION_KEY

_fernet = Fernet(ENCRYPTION_KEY.encode())


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return ""
