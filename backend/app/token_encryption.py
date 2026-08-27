"""
Symmetric encryption for OAuth tokens at rest (linked_email_accounts'
access_token_encrypted / refresh_token_encrypted columns). Never store
a user's real email password anywhere -- OAuth tokens are the only
credential this app ever holds for someone else's mailbox, and even
those are encrypted, not plaintext, in the database file.

Uses Fernet (AES-128-CBC + HMAC, from the `cryptography` package) --
authenticated symmetric encryption, appropriate here because the app
itself is both the encrypter and the only decrypter (this isn't
public-key signing/verification, just "don't leave tokens in the
clear if the DB file leaks").

TOKEN_ENCRYPTION_KEY must be set in the environment. Generate one with:
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
Losing this key means every linked email account becomes unusable
(the encrypted tokens can never be recovered) -- users would need to
reconnect. Rotating it requires decrypting all existing tokens with
the old key and re-encrypting with the new one; not implemented here
since no rotation has been needed yet.
"""
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

_ENV_VAR = "TOKEN_ENCRYPTION_KEY"


class TokenEncryptionNotConfigured(RuntimeError):
    pass


def _get_fernet() -> Fernet:
    key = os.environ.get(_ENV_VAR)
    if not key:
        raise TokenEncryptionNotConfigured(
            f"{_ENV_VAR} is not set. Generate one with: "
            "python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\" "
            "and set it in the environment before linking any email accounts."
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        raise TokenEncryptionNotConfigured(f"{_ENV_VAR} is not a valid Fernet key: {e}")


def encrypt_token(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> Optional[str]:
    """Returns None (rather than raising) on a token that fails to decrypt -- e.g. the encryption key was rotated/changed since this token was stored. Callers should treat None the same as an expired/invalid token: force a reconnect."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None
