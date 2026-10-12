import json
from pathlib import Path

import pytest
import responses

from mopidy_spotify import web
from mopidy_spotify.oauth import providers, state, store
from mopidy_spotify.oauth.source import SpotifyAccessTokenSource


def client(
    path: Path, client_id: str | None, client_secret: str | None
) -> web.OAuthClient:
    return web.OAuthClient(
        base_url="https://api.spotify.com/v1",
        token_source=SpotifyAccessTokenSource(
            pkce=providers.PkceProvider(),
            bridge=providers.BridgeProvider(client_id, client_secret),
            auth_store=store.Store(path),
        ),
    )


@responses.activate
@pytest.mark.parametrize(
    ("client_id", "client_secret"),
    [(None, None), ("bridge-id", None), (None, "bridge-secret")],
)
def test_configured_bridge_intent_survives_missing_credentials_until_supplied(
    tmp_path: Path,
    client_id: str | None,
    client_secret: str | None,
    caplog: pytest.LogCaptureFixture,
):
    path = tmp_path / "auth.json"
    auth_store = store.Store(path)
    auth_store.configure_bridge()
    selected = auth_store.load()

    assert client(path, client_id, client_secret).token() is None

    assert len(responses.calls) == 0
    assert auth_store.load() == selected
    assert "Configure both spotify/client_id and spotify/client_secret" in caplog.text

    responses.post(
        web.BRIDGE_REFRESH_URL,
        json={"access_token": "bridge-token", "token_type": "Bearer"},
    )
    assert client(path, "bridge-id", "bridge-secret").token() == "bridge-token"
    assert len(responses.calls) == 1
    assert auth_store.load() == selected


@responses.activate
def test_rejected_credentials_stay_blocked_across_client_restarts(tmp_path: Path):
    path = tmp_path / "auth.json"
    responses.post(
        web.BRIDGE_REFRESH_URL,
        json={"error": "invalid_client", "error_description": "Rejected credentials"},
        status=401,
    )
    first = client(path, "rejected-id", "rejected-secret")
    assert first.token() is None
    saved = path.read_bytes()

    store.Store(path).configure_bridge()

    assert first.token() is None
    assert client(path, "rejected-id", "rejected-secret").token() is None
    assert len(responses.calls) == 1
    assert path.read_bytes() == saved


@responses.activate
@pytest.mark.parametrize(
    ("client_id", "client_secret"),
    [("corrected-id", "rejected-secret"), ("rejected-id", "corrected-secret")],
)
def test_changing_either_credential_allows_recovery(
    tmp_path: Path, client_id: str, client_secret: str
):
    path = tmp_path / "auth.json"
    responses.post(web.BRIDGE_REFRESH_URL, json={"error": "invalid_client"}, status=401)
    assert client(path, "rejected-id", "rejected-secret").token() is None
    saved = json.loads(path.read_text())
    assert saved["credential_fingerprint"]
    assert "rejected-id" not in path.read_text()
    assert "rejected-secret" not in path.read_text()

    responses.post(
        web.BRIDGE_REFRESH_URL,
        json={"access_token": "recovered-token", "token_type": "Bearer"},
    )
    assert client(path, client_id, client_secret).token() == "recovered-token"
    assert len(responses.calls) == 2
    assert json.loads(path.read_text()) == {
        "version": 1,
        "mode": "bridge",
        "state": "configured",
    }
    assert store.Store(path).load() is not None


@responses.activate
def test_legacy_rejection_retries_once_then_remembers_credentials(tmp_path: Path):
    path = tmp_path / "auth.json"
    auth_store = store.Store(path)
    assert auth_store.compare_and_set(
        None, state.PermanentError(mode="bridge", error_code="invalid_client")
    )
    responses.post(web.BRIDGE_REFRESH_URL, json={"error": "invalid_client"}, status=401)

    assert client(path, "client-id", "client-secret").token() is None
    assert json.loads(path.read_text())["credential_fingerprint"]
    assert client(path, "client-id", "client-secret").token() is None
    assert len(responses.calls) == 1


@responses.activate
def test_new_rejection_replaces_fingerprint_and_blocks_new_credentials(tmp_path: Path):
    path = tmp_path / "auth.json"
    responses.post(web.BRIDGE_REFRESH_URL, json={"error": "invalid_client"}, status=401)
    assert client(path, "client-id", "old-secret").token() is None
    previous = json.loads(path.read_text())["credential_fingerprint"]

    assert client(path, "client-id", "new-secret").token() is None
    assert json.loads(path.read_text())["credential_fingerprint"] != previous
    assert client(path, "client-id", "new-secret").token() is None
    assert len(responses.calls) == 2


@responses.activate
def test_transient_failure_after_config_change_preserves_previous_rejection(
    tmp_path: Path,
):
    path = tmp_path / "auth.json"
    responses.post(web.BRIDGE_REFRESH_URL, json={"error": "invalid_client"}, status=401)
    assert client(path, "client-id", "old-secret").token() is None
    saved = path.read_bytes()
    responses.post(
        web.BRIDGE_REFRESH_URL, json={"error": "temporarily_unavailable"}, status=400
    )

    changed = client(path, "client-id", "new-secret")
    assert changed.token() is None
    assert changed.token() is None
    assert len(responses.calls) == 3
    assert path.read_bytes() == saved


@responses.activate
def test_clearing_authorization_removes_rejected_credential_fingerprint(tmp_path: Path):
    path = tmp_path / "auth.json"
    responses.post(web.BRIDGE_REFRESH_URL, json={"error": "invalid_client"}, status=401)
    assert client(path, "client-id", "client-secret").token() is None

    store.Store(path).clear()

    assert json.loads(path.read_text()) == {
        "version": 1,
        "mode": "bridge",
        "state": "cleared",
    }
