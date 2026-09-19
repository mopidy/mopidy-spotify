from pathlib import Path
from urllib.parse import parse_qs

import pytest

from mopidy_spotify import auth_state, pkce


def test_file_auth_state_store_returns_none_for_missing_file(tmp_path: Path):
    assert auth_state.FileAuthStateStore(tmp_path / "auth.json").load() is None


def test_file_auth_state_store_round_trips_pkce_authorized(tmp_path: Path):
    store = auth_state.FileAuthStateStore(tmp_path / "auth.json")
    token_id = 1
    refresh_token = f"refresh-token-{token_id}"

    store.save(auth_state.PkceAuthorizedAuthPayload(refresh_token=refresh_token))

    assert store.load() == auth_state.PkceAuthorizedAuthPayload(
        refresh_token=refresh_token
    )


def test_file_auth_state_store_round_trips_cleared_bridge(tmp_path: Path):
    store = auth_state.FileAuthStateStore(tmp_path / "auth.json")

    store.save(auth_state.ClearedAuthPayload(mode="bridge"))

    assert store.load() == auth_state.ClearedAuthPayload(mode="bridge")


def test_file_auth_state_store_rejects_invalid_json(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    auth_state_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(auth_state.InvalidRefreshTokenError):
        auth_state.FileAuthStateStore(auth_state_path).load()


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        (
            "configured-bridge",
            auth_state.BridgeConfiguredAuthPayload(),
        ),
        (
            "cleared-pkce",
            auth_state.ClearedAuthPayload(mode="pkce"),
        ),
        (
            "cleared-bridge",
            auth_state.ClearedAuthPayload(mode="bridge"),
        ),
        (
            "error-pkce",
            auth_state.PermanentErrorAuthPayload(
                mode="pkce", error_code="invalid_grant"
            ),
        ),
        (
            "error-bridge",
            auth_state.PermanentErrorAuthPayload(
                mode="bridge", error_code="invalid_grant"
            ),
        ),
    ],
)
def test_refresh_token_request_requires_pkce_authorized(
    tmp_path: Path, name: str, payload: auth_state.AuthPayload
):
    auth_state_path = tmp_path / "auth.json"
    auth_state.FileAuthStateStore(auth_state_path).save(payload)

    with pytest.raises(auth_state.InvalidRefreshTokenError, match="unsupported state"):
        auth_state.refresh_token_request(auth_state_path)


def test_refresh_token_request_rejects_missing_auth_file(tmp_path: Path):
    with pytest.raises(ValueError, match="missing refresh_token"):
        auth_state.refresh_token_request(tmp_path / "auth.json")


def test_refresh_token_request_encodes_persisted_token(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    token = "refresh+/=&?"  # noqa: S105 - Synthetic value exercises form encoding.
    auth_state.FileAuthStateStore(auth_state_path).save(
        auth_state.PkceAuthorizedAuthPayload(refresh_token=token)
    )

    request = auth_state.refresh_token_request(auth_state_path).prepare()

    assert request.method == "POST"
    assert request.url == "https://accounts.spotify.com/api/token"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert isinstance(request.body, str)
    assert parse_qs(request.body) == {
        "client_id": [pkce.CLIENT_ID],
        "grant_type": ["refresh_token"],
        "refresh_token": [token],
    }
