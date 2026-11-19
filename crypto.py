"""
Encrypts/decrypts sensitive text before it touches the database, so that if
vpnbot.db is ever copied, leaked, or stolen, the actual VPN configs/links
inside it aren't sitting there in plain text.

Key handling:
- If ENCRYPTION_KEY is set in .env, that's used (lets you back up/restore
  the same key across servers).
- Otherwise, a key is generated once and saved to secret.key next to the
  bot. This file IS the key - back it up somewhere safe, and never share it
  or commit it to a repo (it's already in .gitignore). If you lose it, any
  previously-encrypted data in vpnbot.db becomes unrecoverable.
"""

import os
import pathlib
from cryptography.fernet import Fernet, InvalidToken

from config import ENCRYPTION_KEY, BASE_DIR

KEY_FILE = str(BASE_DIR / "secret.key")


def _load_or_create_key():
    if ENCRYPTION_KEY:
        return ENCRYPTION_KEY.encode()
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt_text(plain):
    if plain is None:
        return None
    return _fernet.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(token):
    """Returns the decrypted string, or the original value unchanged if it
    doesn't look like something this key can decrypt (e.g. rows saved
    before encryption was added)."""
    if token is None:
        return None
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return token
