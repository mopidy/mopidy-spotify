from pathlib import Path

import pytest

from mopidy_spotify import auth_state


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


def test_refresh_token_request_requires_pkce_authorized(tmp_path: Path):
    auth_state_path = tmp_path / "auth.json"
    auth_state_path.write_text(
        '{"version":1,"mode":"bridge","state":"configured"}',
        encoding="utf-8",
    )

    with pytest.raises(auth_state.InvalidRefreshTokenError):
        auth_state.refresh_token_request(auth_state_path)
