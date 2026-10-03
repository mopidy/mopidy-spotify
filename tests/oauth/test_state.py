from pathlib import Path
from urllib.parse import parse_qs

import pytest

from mopidy_spotify.oauth import pkce, state


def test_file_auth_state_store_returns_none_for_missing_file(tmp_path: Path):
    assert state.FileAuthStateStore(tmp_path / "auth.json").load() is None


def test_file_auth_state_store_round_trips_pkce_authorized(tmp_path: Path):
    store = state.FileAuthStateStore(tmp_path / "auth.json")
    token_id = 1
    refresh_token = f"refresh-token-{token_id}"

    store.save(state.PkceAuthorizedAuthPayload(refresh_token=refresh_token))

    assert store.load() == state.PkceAuthorizedAuthPayload(refresh_token=refresh_token)


def test_pkce_refresh_token_is_redacted_but_serialized_for_storage():
    token = "refresh-token-secret"  # noqa: S105
    payload = state.PkceAuthorizedAuthPayload(refresh_token=token)

    assert token not in repr(payload)
    assert token in payload.model_dump_json()


def test_file_auth_state_store_round_trips_cleared_bridge(tmp_path: Path):
    store = state.FileAuthStateStore(tmp_path / "auth.json")

    store.save(state.ClearedAuthPayload(mode="bridge"))

    assert store.load() == state.ClearedAuthPayload(mode="bridge")


def test_file_auth_state_store_rejects_invalid_json(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    auth_state_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(state.InvalidRefreshTokenError):
        state.FileAuthStateStore(auth_state_path).load()


def test_file_auth_state_store_does_not_chain_invalid_payload(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    auth_state_path.write_text(
        '{"version":1,"mode":"pkce","state":"authorized",'
        '"refresh_token":"must-not-leak","extra":true}',
        encoding="utf-8",
    )

    with pytest.raises(state.InvalidRefreshTokenError) as exc_info:
        state.FileAuthStateStore(auth_state_path).load()

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        (
            "configured-bridge",
            state.BridgeConfiguredAuthPayload(),
        ),
        (
            "cleared-pkce",
            state.ClearedAuthPayload(mode="pkce"),
        ),
        (
            "cleared-bridge",
            state.ClearedAuthPayload(mode="bridge"),
        ),
        (
            "error-pkce",
            state.PermanentErrorAuthPayload(mode="pkce", error_code="invalid_grant"),
        ),
        (
            "error-bridge",
            state.PermanentErrorAuthPayload(mode="bridge", error_code="invalid_grant"),
        ),
    ],
)
def test_refresh_token_request_requires_pkce_authorized(
    tmp_path: Path, name: str, payload: state.AuthPayload
):
    auth_state_path = tmp_path / "auth.json"
    state.FileAuthStateStore(auth_state_path).save(payload)

    with pytest.raises(state.InvalidRefreshTokenError, match="unsupported state"):
        state.refresh_token_request(auth_state_path)


def test_refresh_token_request_rejects_missing_auth_file(tmp_path: Path):
    with pytest.raises(ValueError, match="missing refresh_token"):
        state.refresh_token_request(tmp_path / "auth.json")


def test_refresh_token_request_encodes_persisted_token(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    token = "refresh+/=&?"  # noqa: S105 - Synthetic value exercises form encoding.
    state.FileAuthStateStore(auth_state_path).save(
        state.PkceAuthorizedAuthPayload(refresh_token=token)
    )

    request = state.refresh_token_request(auth_state_path).prepare()

    assert request.method == "POST"
    assert request.url == "https://accounts.spotify.com/api/token"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert isinstance(request.body, str)
    assert parse_qs(request.body) == {
        "client_id": [pkce.CLIENT_ID],
        "grant_type": ["refresh_token"],
        "refresh_token": [token],
    }
