import base64
from pathlib import Path

import pytest

from mopidy_spotify import tokens


def test_parse_authorization_result_parses_redirect_url() -> None:
    result = tokens.parse_authorization_result(
        "https://example.com/callback?code=code-123&state=state-123"
    )

    assert result == tokens.AuthorizationResult(
        code="code-123",
        state="state-123",
    )


def test_parse_authorization_result_parses_base64_query_string() -> None:
    payload = (
        base64.urlsafe_b64encode(b"code=code-123&state=state-123")
        .decode("ascii")
        .rstrip("=")
    )

    result = tokens.parse_authorization_result(payload)

    assert result == tokens.AuthorizationResult(
        code="code-123",
        state="state-123",
    )


def test_parse_authorization_result_raises_on_provider_error() -> None:
    with pytest.raises(ValueError, match="access_denied"):
        tokens.parse_authorization_result(
            "https://example.com/callback?error=access_denied&error_description=Denied"
        )


def test_file_auth_state_store_round_trips_pkce_authorized(tmp_path: Path):
    store = tokens.FileAuthStateStore(tmp_path / "auth.json")
    refresh_token = "refresh-token-1"  # noqa: S105

    store.save(tokens.PkceAuthorizedAuthPayload(refresh_token=refresh_token))

    assert store.load() == tokens.PkceAuthorizedAuthPayload(
        refresh_token=refresh_token
    )


def test_file_auth_state_store_round_trips_cleared_bridge(tmp_path: Path):
    store = tokens.FileAuthStateStore(tmp_path / "auth.json")

    store.save(tokens.ClearedAuthPayload(mode="bridge"))

    assert store.load() == tokens.ClearedAuthPayload(mode="bridge")


def test_refresh_token_request_requires_pkce_authorized(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    auth_state_path.write_text(
        '{"version":1,"mode":"bridge","state":"configured"}',
        encoding="utf-8",
    )

    with pytest.raises(tokens.InvalidRefreshTokenError):
        tokens.refresh_token_request(auth_state_path)
