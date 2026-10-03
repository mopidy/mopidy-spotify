"""Adapted from uuid-extension 0.2.0 tests/test_uuid7.py and test_utils.py.

Copyright (c) 2025 mfeyx; MIT license in
src/mopidy_spotify/_ext/licenses/uuid-extension.txt.
Source: https://pypi.org/project/uuid-extension/0.2.0/
Source archive SHA256: e68907184276f47a4b169dc9891477693371b5f3756aebdaffb7cf83b9a6077e

Use pytest assertions and the shim's numeric timestamp seam instead of the
upstream UUID subclass. Freeze time and randomness; omit datetime-only APIs.
"""

import re

import pytest

from mopidy_spotify._ext import uuid as uuid_ext


@pytest.fixture(autouse=True)
def controlled_sources(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(uuid_ext, "time", lambda: 1645557742.123)
    values = iter(range(2000))
    monkeypatch.setattr(uuid_ext.secrets, "randbits", lambda bits: next(values))


def test_uuid7_format():
    u = uuid_ext._uuid7()
    assert u.version == 7
    assert 2 <= (u.int >> 62) & 0x3 <= 3
    uuid_bin = f"{u.int:0128b}"
    assert uuid_bin[48:52] == "0111"
    assert uuid_bin[64:66] == "10"


def test_timestamp_extraction():
    fixed_ts = 1645557742.123
    u = uuid_ext._uuid7(fixed_ts)
    assert (u.int >> 80) / 1000 == pytest.approx(fixed_ts, abs=0.001)


def test_time_ordering():
    timestamps = [
        1645557742.000,
        1645557742.001,
        1645557742.010,
        1645557742.100,
        1645557743.000,
    ]
    uuids = [uuid_ext._uuid7(ts) for ts in timestamps]
    for i in range(1, len(uuids)):
        assert uuids[i] > uuids[i - 1]


def test_uuid_string_format():
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        str(uuid_ext._uuid7()),
    )


def test_uniqueness():
    count = 1000
    uuids = [uuid_ext._uuid7() for _ in range(count)]
    assert len(set(uuids)) == count


def test_millisecond_timestamp_precision():
    base_ts = 1645557742.123456
    u1 = uuid_ext._uuid7(base_ts)
    u2 = uuid_ext._uuid7(base_ts + 0.000001)
    assert u1.int >> 80 == u2.int >> 80
    u3 = uuid_ext._uuid7(base_ts + 0.001)
    assert u1.int >> 80 != u3.int >> 80


def test_timestamp_truncation():
    far_future_ts = 1645557742.123 + (2**48 / 1000) + 1000
    u = uuid_ext._uuid7(far_future_ts)
    expected_ts = far_future_ts % (2**48 / 1000)
    assert (u.int >> 80) / 1000 == pytest.approx(expected_ts, abs=0.001)


@pytest.mark.parametrize("timestamp", [1621234567.89, 1621234567])
def test_numeric_timestamp(timestamp: float):
    assert uuid_ext._uuid7(timestamp).int >> 80 == int(timestamp * 1000)


def test_48bit_masking():
    assert uuid_ext._uuid7(0x1000000000000 / 1000).int >> 80 == 0
    assert uuid_ext._uuid7(0xFFFFFFFFFFFF / 1000).int >> 80 == 0xFFFFFFFFFFFF


def test_counter_masking():
    assert (uuid_ext._uuid7(counter=0x1001).int >> 64) & 0xFFF == 1
