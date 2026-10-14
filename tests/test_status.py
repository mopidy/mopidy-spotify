from pathlib import Path

import pytest
from mopidy.config import Config
from pydantic import SecretStr

from mopidy_spotify import Extension, status
from mopidy_spotify.oauth import providers, state, store, tokens


@pytest.mark.parametrize(
    ("auth_state", "configured", "expected"),
    [
        (None, False, "not authorized"),
        (None, True, "configured (legacy)"),
        (state.BridgeConfigured(), False, "not authorized"),
        (state.BridgeConfigured(), True, "configured (legacy)"),
        (state.Cleared(mode="pkce"), True, "configured (legacy)"),
        (state.Cleared(mode="bridge"), False, "not authorized"),
        (
            state.PkceAuthorized(refresh_token=SecretStr("refresh-token")),
            True,
            "authorized (PKCE)",
        ),
        (
            state.PermanentError(mode="pkce", error_code="invalid_grant"),
            True,
            "PKCE authorization rejected",
        ),
        (
            state.PermanentError(mode="bridge", error_code="invalid_grant"),
            True,
            "configured (legacy)",
        ),
    ],
)
def test_describe_local_authorization(
    tmp_path: Path,
    auth_state: state.State | None,
    configured: bool,
    expected: str,
):
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {
                "client_id": "client-id" if configured else None,
                "client_secret": "client-secret" if configured else None,
            },
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    if isinstance(auth_state, state.PkceAuthorized):
        auth_store.persist_pkce_authorization(auth_state.refresh_token)
    elif auth_state is not None:
        assert auth_store.compare_and_set(None, auth_state)
    previous = auth_store.load()

    assert status.describe(config) == (
        f"Spotify Web API: {expected}",
        "Spotify playback: not authorized",
    )
    assert auth_store.load() == previous


@pytest.mark.parametrize("changed_credentials", [False, True])
def test_describe_bridge_rejection_uses_runtime_eligibility(
    tmp_path: Path, changed_credentials: bool
):
    bridge = providers.BridgeProvider("client-id", "client-secret")
    rejection = bridge.process(
        None, tokens.OAuthErrorResponse(error="invalid_grant"), 400
    )
    config = Config(
        {
            "core": {"data_dir": tmp_path},
            "spotify": {
                "client_id": "client-id",
                "client_secret": "new-secret"
                if changed_credentials
                else "client-secret",
            },
        }
    )
    auth_store = store.Store(Extension.get_auth_state_path(config))
    assert auth_store.compare_and_set(None, rejection)
    expected = (
        "configured (legacy)"
        if changed_credentials
        else "legacy authorization rejected"
    )
    assert status.describe(config) == (
        f"Spotify Web API: {expected}",
        "Spotify playback: not authorized",
    )


def test_describe_reports_invalid_web_authorization_and_stored_playback(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    auth_store = store.Store(Extension.get_auth_state_path(config))
    auth_store.path.write_text("not-json")
    credentials_file = Extension.get_credentials_dir(config) / "credentials.json"
    credentials_file.write_text("playback-credentials")

    assert status.describe(config) == (
        "Spotify Web API: invalid authorization state",
        "Spotify playback: stored",
    )


def test_describe_reports_web_when_playback_path_is_blocked(tmp_path: Path):
    config = Config({"core": {"data_dir": tmp_path}})
    store.Store(Extension.get_auth_state_path(config)).persist_pkce_authorization(
        SecretStr("refresh-token")
    )
    (Extension.get_data_dir(config) / "credentials-cache").write_text("blocked")

    web_line, playback_line = status.describe(config)

    assert web_line == "Spotify Web API: authorized (PKCE)"
    assert playback_line.startswith("Spotify playback: unavailable (")
