import sys
import uuid

import pytest

from mopidy_spotify._ext import uuid as uuid_ext


@pytest.mark.skipif(sys.version_info >= (3, 14), reason="Python 3.13 fallback")
@pytest.mark.parametrize("random_bits", [0, (1 << 74) - 1])
def test_fallback_preserves_timestamp_and_random_bits(
    monkeypatch: pytest.MonkeyPatch, random_bits: int
):
    timestamp_ms = 1_759_536_123_456
    monkeypatch.setattr(uuid_ext, "time", lambda: timestamp_ms / 1000)

    def randbits(bits: int) -> int:
        assert bits in (12, 62)
        return random_bits >> 62 if bits == 12 else random_bits & ((1 << 62) - 1)

    monkeypatch.setattr(uuid_ext.secrets, "randbits", randbits)

    result = uuid_ext.uuid7()

    assert result.version == 7
    assert result.variant == uuid.RFC_4122
    assert result.int >> 80 == timestamp_ms
    assert (result.int >> 64) & 0xFFF == random_bits >> 62
    assert result.int & ((1 << 62) - 1) == random_bits & ((1 << 62) - 1)


def test_uuid7_returns_standard_uuid():
    result = uuid_ext.uuid7()

    assert isinstance(result, uuid.UUID)
    assert result.version == 7
    assert result.variant == uuid.RFC_4122


@pytest.mark.skipif(sys.version_info < (3, 14), reason="Requires standard UUIDv7")
def test_uses_standard_uuid7(monkeypatch: pytest.MonkeyPatch):
    expected = uuid.UUID("01999999-9999-7000-8000-000000000000")
    monkeypatch.setattr(uuid, "uuid7", lambda: expected)

    assert uuid_ext.uuid7() is expected
