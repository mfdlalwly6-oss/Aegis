"""Symmetric encryption for at-rest secrets (hmac_secret).

Derives a Fernet key from settings.SECRET_KEY so no extra env var is required.
Ciphertexts are transparently detected (Fernet 'gAAAA' prefix) so legacy
plaintext values keep working until migration 012 encrypts them in place.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    # 32-byte key derived deterministically from SECRET_KEY; urlsafe-base64 for Fernet
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted(value: str | None) -> bool:
    """Cheap check: Fernet tokens are urlsafe-base64 starting with 'gAAAAA'."""
    return bool(value) and value.startswith("gAAAAA")


def encrypt_secret(plaintext: str) -> str:
    if plaintext is None:
        return plaintext
    if is_encrypted(plaintext):
        return plaintext  # already encrypted, idempotent
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    """Return plaintext. Legacy unencrypted values pass through unchanged."""
    if value is None:
        return None
    if not is_encrypted(value):
        return value
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return value  # last-resort: return as-is, caller will fail auth explicitly
