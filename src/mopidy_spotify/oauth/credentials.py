"""Fingerprints identifying the bridge credentials rejected by an endpoint.

Only permanent bridge errors retain a fingerprint. This detects configuration
changes; it does not protect credentials already stored in plaintext config.
Scrypt is likely overkill for generated Spotify secrets, but makes guessing from
the stored hash more expensive without introducing a dependency.
"""

import hashlib
import hmac
import json
import secrets
from typing import NewType

Fingerprint = NewType("Fingerprint", str)


def create(client_id: str, client_secret: str) -> Fingerprint:
    """Identify both credentials without persisting their plaintext values."""
    salt = secrets.token_bytes(16)
    digest = _digest(client_id, client_secret, salt)
    return Fingerprint(f"scrypt-v1${salt.hex()}${digest.hex()}")


def matches(fingerprint: Fingerprint, client_id: str, client_secret: str) -> bool:
    """Compare current credentials to a validated, persisted fingerprint."""
    _, salt, expected = fingerprint.split("$")
    actual = _digest(client_id, client_secret, bytes.fromhex(salt))
    return hmac.compare_digest(actual, bytes.fromhex(expected))


def _digest(client_id: str, client_secret: str, salt: bytes) -> bytes:
    # JSON encoding keeps different credential pairs distinct, including delimiters.
    value = json.dumps([client_id, client_secret], ensure_ascii=True).encode("utf-8")
    # Use the 16 MiB / five-pass scrypt profile to bound memory in a music daemon.
    # https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt
    return hashlib.scrypt(value, salt=salt, n=16384, r=8, p=5, dklen=32)
