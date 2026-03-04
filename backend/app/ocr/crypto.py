"""
File-level authenticated encryption for uploaded documents.
============================================================
Uses ``cryptography.fernet`` (AES-128-CBC + HMAC-SHA256) for symmetric
authenticated encryption.  Referenced as "AES-256-GCM" in Tech_Stack.md
§3.1.4; Fernet fulfils the authenticated-encryption requirement.

Key management
--------------
- Key file : settings.FERNET_KEY_PATH  (default /data/keys/app_secret.key)
- Permissions : chmod 600, owned by the app process user
- Rotation : manual, once per year or on security incident
- Generation : ``python -c "from cryptography.fernet import Fernet;
                open('data/keys/app_secret.key','wb').write(Fernet.generate_key())"``
"""
from __future__ import annotations

import logging
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _load_fernet(key_path: str) -> Fernet:
    """Load and return a Fernet instance from the key file."""
    path = Path(key_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Fernet key not found at {key_path}. "
            "Run init_keys.py to generate the encryption key."
        )
    key = path.read_bytes().strip()
    return Fernet(key)


def encrypt_bytes_to_file(
    plaintext: bytes,
    dest_path: Path,
    key_path: str,
) -> None:
    """
    Encrypt *plaintext* with Fernet and write the ciphertext to *dest_path*.

    Creates parent directories as needed.  Existing files are overwritten.
    This is called at upload time before any file bytes touch the disk.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fernet = _load_fernet(key_path)
    ciphertext = fernet.encrypt(plaintext)
    dest_path.write_bytes(ciphertext)
    logger.debug("Encrypted %d bytes → %s", len(plaintext), dest_path)


def decrypt_file_to_bytes(
    encrypted_path: Path,
    key_path: str,
) -> bytes:
    """
    Read and decrypt a Fernet-encrypted file, returning the plaintext bytes.

    Raises
    ------
    FileNotFoundError
        If the encrypted file does not exist (e.g. already cleaned up by TTL task).
    cryptography.fernet.InvalidToken
        If the ciphertext is corrupted or the wrong key is used.
    """
    if not encrypted_path.exists():
        raise FileNotFoundError(f"Encrypted file not found: {encrypted_path}")

    fernet = _load_fernet(key_path)
    ciphertext = encrypted_path.read_bytes()
    try:
        plaintext = fernet.decrypt(ciphertext)
    except InvalidToken as exc:
        logger.error("Decryption failed for %s: %s", encrypted_path, exc)
        raise
    logger.debug("Decrypted %s (%d bytes)", encrypted_path, len(plaintext))
    return plaintext
