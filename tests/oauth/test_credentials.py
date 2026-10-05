import pytest

from mopidy_spotify.oauth import credentials


def test_fingerprint_matches_only_the_same_credential_pair():
    fingerprint = credentials.create("client-id", "client-secret")
    assert credentials.matches(fingerprint, "client-id", "client-secret")
    assert not credentials.matches(fingerprint, "other-id", "client-secret")
    assert not credentials.matches(fingerprint, "client-id", "other-secret")


def test_fingerprints_use_independent_salts(monkeypatch: pytest.MonkeyPatch):
    salts = iter([bytes(16), bytes([1]) * 16])
    monkeypatch.setattr(credentials.secrets, "token_bytes", lambda size: next(salts))
    first = credentials.create("client-id", "client-secret")
    second = credentials.create("client-id", "client-secret")
    assert first != second
    assert credentials.matches(first, "client-id", "client-secret")
    assert credentials.matches(second, "client-id", "client-secret")


@pytest.mark.parametrize(
    ("first", "second"),
    [(("a:b", "c"), ("a", "b:c")), (("a", "\u00e9"), ("a", "e\u0301"))],
)
def test_credential_encoding_is_unambiguous(
    first: tuple[str, str], second: tuple[str, str]
):
    fingerprint = credentials.create(*first)
    assert credentials.matches(fingerprint, *first)
    assert not credentials.matches(fingerprint, *second)
