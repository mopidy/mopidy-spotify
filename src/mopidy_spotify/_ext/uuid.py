"""Time-encoded keyring IDs on Python 3.13 and newer.

The fallback is adapted from uuid-extension 0.2.0 by Markus Feiks (mfeyx),
specifically `UUID7._generate` and `generate_unix_ts_in_ms`. Copyright (c) 2025
mfeyx; MIT license in `licenses/uuid-extension.txt`.
Source: https://pypi.org/project/uuid-extension/0.2.0/

Only UUID generation is retained; datetime conversion and the UUID subclass
are unnecessary for keyring names. Ordering within a millisecond or across
clock adjustments is not guaranteed. Use the standard library from Python 3.14.
"""

import secrets
import sys
import uuid
from time import time

__all__ = ["uuid7"]


def uuid7() -> uuid.UUID:
    if sys.version_info >= (3, 14):
        return uuid.uuid7()

    # NOTE: Replace with uuid.uuid7() when bumping minimum Python version to 3.14.
    return _uuid7()


def _uuid7(timestamp: float | None = None, counter: int | None = None) -> uuid.UUID:
    """Upstream generation algorithm with its numeric timestamp test seam."""
    unix_ts_ms = int((time() if timestamp is None else timestamp) * 1000)
    unix_ts_ms &= 0xFFFFFFFFFFFF
    time_high = (unix_ts_ms << 16) & 0xFFFFFFFFFFFF0000
    version = 0x7000
    rand_a = counter & 0xFFF if counter is not None else secrets.randbits(12)
    msb = time_high | version | rand_a
    rand_b = secrets.randbits(62)
    lsb = (0x8000000000000000 | rand_b) & 0xFFFFFFFFFFFFFFFF
    return uuid.UUID(int=(msb << 64) | lsb)
