import json
import sys
from pathlib import Path

import pytest
import requests
from pydantic import SecretStr

from mopidy_spotify.oauth import providers, state, store
from mopidy_spotify.oauth.source import SpotifyAccessTokenSource
from mopidy_spotify.oauth.tokens import (
    OAuthErrorResponse,
    OAuthPermanentRefreshError,
    OAuthTokenRefreshError,
    OAuthTokenResponse,
)


def _legacy_rejection() -> state.State:
    return providers.BridgeProvider("client-id", "client-secret").process(
        None, OAuthErrorResponse(error="invalid_client"), 401
    )


@pytest.mark.parametrize(
    ("auth_state", "credentials", "expected_status", "endpoint", "expected_error"),
    [
        (None, (None, None), "not authorized", None, OAuthTokenRefreshError),
        (
            None,
            ("client-id", "client-secret"),
            "configured (legacy)",
            providers.BRIDGE_REFRESH_URL,
            None,
        ),
        (
            state.Cleared(mode="pkce"),
            ("client-id", "client-secret"),
            "configured (legacy)",
            providers.BRIDGE_REFRESH_URL,
            None,
        ),
        (
            state.Cleared(mode="bridge"),
            (None, None),
            "not authorized",
            None,
            OAuthTokenRefreshError,
        ),
        (
            state.BridgeConfigured(),
            ("client-id", None),
            "not authorized",
            None,
            OAuthTokenRefreshError,
        ),
        (
            state.BridgeConfigured(),
            ("client-id", "client-secret"),
            "configured (legacy)",
            providers.BRIDGE_REFRESH_URL,
            None,
        ),
        (
            state.PkceAuthorized(refresh_token=SecretStr("refresh-token")),
            ("client-id", "client-secret"),
            "authorized (PKCE)",
            providers.SPOTIFY_REFRESH_URL,
            None,
        ),
        (
            state.PermanentError(mode="pkce", error_code="invalid_grant"),
            ("client-id", "client-secret"),
            "PKCE authorization rejected",
            None,
            OAuthPermanentRefreshError,
        ),
        (
            _legacy_rejection(),
            ("client-id", "client-secret"),
            "legacy authorization rejected",
            None,
            OAuthPermanentRefreshError,
        ),
        (
            _legacy_rejection(),
            ("new-id", "client-secret"),
            "configured (legacy)",
            providers.BRIDGE_REFRESH_URL,
            None,
        ),
        (
            _legacy_rejection(),
            ("client-id", "new-secret"),
            "configured (legacy)",
            providers.BRIDGE_REFRESH_URL,
            None,
        ),
        (
            _legacy_rejection(),
            (None, None),
            "legacy authorization rejected",
            None,
            OAuthPermanentRefreshError,
        ),
        (
            state.PermanentError(mode="bridge", error_code="invalid_client"),
            ("client-id", "client-secret"),
            "configured (legacy)",
            providers.BRIDGE_REFRESH_URL,
            None,
        ),
    ],
)
def test_status_and_refresh_use_the_same_authorization_decision(
    tmp_path: Path,
    *,
    auth_state: state.State | None,
    credentials: tuple[str | None, str | None],
    expected_status: str,
    endpoint: str | None,
    expected_error: type[OAuthTokenRefreshError] | None,
):
    auth_store = store.Store(tmp_path / "auth.json")
    if isinstance(auth_state, state.PkceAuthorized):
        auth_store.persist_pkce_authorization(auth_state.refresh_token)
    elif auth_state is not None:
        assert auth_store.compare_and_set(None, auth_state)
    source = SpotifyAccessTokenSource(
        auth_store=auth_store,
        pkce=providers.PkceProvider(),
        bridge=providers.BridgeProvider(*credentials),
    )
    previous = auth_store.load()
    previous_bytes = auth_store.path.read_bytes() if auth_store.path.exists() else None
    calls: list[requests.Request] = []
    token = _token_response()

    def exchange(request: requests.Request) -> tuple[OAuthTokenResponse, int]:
        calls.append(request)
        return token, 200

    assert source.status() == expected_status
    assert source.status() == expected_status
    assert auth_store.load() == previous
    assert (
        auth_store.path.read_bytes() if auth_store.path.exists() else None
    ) == previous_bytes

    if expected_error is not None:
        with pytest.raises(expected_error) as exc:
            source.refresh(exchange)
        assert type(exc.value) is expected_error
        assert calls == []
    else:
        assert source.refresh(exchange) is token
        assert len(calls) == 1
        assert calls[0].url == endpoint
        expected_auth = (
            credentials if endpoint == providers.BRIDGE_REFRESH_URL else None
        )
        assert calls[0].auth == expected_auth


@pytest.mark.parametrize("configured", [False, True])
def test_status_and_refresh_support_an_absent_store(configured: bool):
    source = SpotifyAccessTokenSource(
        pkce=providers.PkceProvider(),
        bridge=providers.BridgeProvider(
            "client-id" if configured else None,
            "client-secret" if configured else None,
        ),
    )
    calls: list[requests.Request] = []
    token = _token_response()

    def exchange(request: requests.Request) -> tuple[OAuthTokenResponse, int]:
        calls.append(request)
        return token, 200

    if configured:
        assert source.status() == "configured (legacy)"
        assert source.refresh(exchange) is token
        assert len(calls) == 1
        assert calls[0].url == providers.BRIDGE_REFRESH_URL
    else:
        assert source.status() == "not authorized"
        with pytest.raises(OAuthTokenRefreshError):
            source.refresh(exchange)
        assert calls == []


def test_status_and_refresh_reload_authorization_between_calls(tmp_path: Path):
    auth_store = store.Store(tmp_path / "auth.json")
    source = SpotifyAccessTokenSource(
        auth_store=auth_store,
        pkce=providers.PkceProvider(),
        bridge=providers.BridgeProvider("client-id", "client-secret"),
    )
    assert source.status() == "configured (legacy)"
    auth_store.persist_pkce_authorization(SecretStr("refresh-token"))
    assert source.status() == "authorized (PKCE)"

    auth_store.clear()
    assert source.status() == "configured (legacy)"
    calls: list[requests.Request] = []

    def exchange(request: requests.Request) -> tuple[OAuthTokenResponse, int]:
        calls.append(request)
        return _token_response(), 200

    source.refresh(exchange)
    assert len(calls) == 1
    assert calls[0].url == providers.BRIDGE_REFRESH_URL


@pytest.mark.parametrize(
    ("contents", "expected"),
    [
        ("not-json", "invalid authorization state"),
        (
            json.dumps(
                {
                    "version": 1,
                    "mode": "pkce",
                    "state": "authorized",
                    "refresh_token": {"storage": "keyring", "username": "token-id"},
                }
            ),
            "unavailable (Spotify refresh-token keyring is unavailable)",
        ),
    ],
    ids=["corrupt-manifest", "unavailable-keyring"],
)
def test_status_and_refresh_fail_closed_on_unusable_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
    expected: str,
):
    auth_store = store.Store(tmp_path / "auth.json")
    auth_store.path.write_text(contents)
    monkeypatch.setitem(sys.modules, "keyring", None)
    source = SpotifyAccessTokenSource(
        auth_store=auth_store,
        pkce=providers.PkceProvider(),
        bridge=providers.BridgeProvider("client-id", "client-secret"),
    )
    calls: list[requests.Request] = []

    def exchange(request: requests.Request) -> tuple[OAuthTokenResponse, int]:
        calls.append(request)
        return _token_response(), 200

    assert source.status() == expected
    with pytest.raises(OAuthPermanentRefreshError):
        source.refresh(exchange)
    assert calls == []
    assert auth_store.path.read_text() == contents


def _token_response() -> OAuthTokenResponse:
    return OAuthTokenResponse(
        access_token=SecretStr("access-token"),
        token_type="Bearer",  # noqa: S106
    )
