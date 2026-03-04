#!/usr/bin/env python3
"""
init_keys.py — Dimerco IEEPA Refund Calculator
Document Reference: DMX-TRS-IEEPA-2026-001

Generates a Fernet (AES-256) symmetric key and writes it to
data/keys/app_secret.key with restrictive permissions (chmod 600).

Usage:
    python init_keys.py [--key-path data/keys/app_secret.key] [--force]

This key is used for:
  - AES-256-GCM encryption of uploaded Form 7501 files
  - AES-256-GCM encryption of PII fields (email, phone, full_name) in the leads table

IMPORTANT: Back up data/keys/app_secret.key offline after generation.
           Losing this key makes all encrypted data unrecoverable.
"""

import argparse
import os
import stat
import sys
from pathlib import Path


def generate_fernet_key(key_path: Path, force: bool = False) -> None:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("ERROR: 'cryptography' package not installed.", file=sys.stderr)
        print("       Run: pip install cryptography", file=sys.stderr)
        sys.exit(1)

    if key_path.exists() and not force:
        print(f"ERROR: Key file already exists at '{key_path}'.", file=sys.stderr)
        print("       Use --force to overwrite (this will invalidate all existing encrypted data!).", file=sys.stderr)
        sys.exit(1)

    key_path.parent.mkdir(parents=True, exist_ok=True)

    key = Fernet.generate_key()

    key_path.write_bytes(key)

    # Restrict permissions: owner read/write only (600)
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    except NotImplementedError:
        # Windows does not support chmod; permissions are managed via ACLs
        pass

    print(f"✅  Fernet key generated: {key_path}")
    print(f"    Size : {len(key)} bytes (base64url-encoded 32-byte AES-256 key)")
    print()
    print("⚠️  ACTION REQUIRED:")
    print(f"   1. Verify permissions: ls -la {key_path.parent}")
    print(f"   2. Back up '{key_path}' to a secure offline location immediately.")
    print("   3. Never commit this file to version control (.gitignore covers data/keys/).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Fernet AES-256 encryption key for the IEEPA Refund Calculator."
    )
    parser.add_argument(
        "--key-path",
        type=Path,
        default=Path("data/keys/app_secret.key"),
        help="Output path for the generated key (default: data/keys/app_secret.key)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing key file (WARNING: invalidates all encrypted data)",
    )
    args = parser.parse_args()

    generate_fernet_key(args.key_path, args.force)


if __name__ == "__main__":
    main()
