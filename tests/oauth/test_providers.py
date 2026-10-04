from http import HTTPStatus

import pytest

from mopidy_spotify.oauth import credentials, pkce, providers, state
from mopidy_spotify.oauth.tokens import (
    OAuthErrorResponse,
    OAuthTokenRefreshError,
    OAuthTokenResponse,
)


@pytest.fixture
def authorized() -> state.PkceAuthorized:
    return state.PkceAuthorized(refresh_token="refresh-token-1")  # noqa: S106


@pytest.fixture
def bridge() -> providers.BridgeProvider:
    return providers.BridgeProvider("client-id", "client-secret")


def test_pkce_provider_builds_refresh_token_request(authorized: state.PkceAuthorized):
    provider = providers.PkceProvider()
    assert provider.supports(authorized)
    request = provider.request(authorized)
    assert request.method == "POST"
    assert request.url == providers.SPOTIFY_REFRESH_URL
    assert request.auth is None
    assert request.data == {
        "client_id": pkce.CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token-1",
    }


def test_pkce_provider_requires_authorized_state():
    provider = providers.PkceProvider()
    assert not provider.supports(None)
    with pytest.raises(OAuthTokenRefreshError, match="missing PKCE"):
        provider.request(None)
    with pytest.raises(OAuthTokenRefreshError, match="missing PKCE"):
        provider.process(None, OAuthErrorResponse(error="invalid_grant"), 400)


@pytest.mark.parametrize("replacement", [None, "", "refresh-token-2"])
def test_pkce_provider_retains_or_rotates_refresh_token(
    authorized: state.PkceAuthorized, replacement: str | None
):
    response = OAuthTokenResponse(
        access_token="access-token-1",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        refresh_token=replacement,
    )
    expected = replacement or "refresh-token-1"
    assert providers.PkceProvider().process(
        authorized, response, HTTPStatus.OK
    ) == state.PkceAuthorized(refresh_token=expected)


def test_pkce_provider_marks_invalid_grant_as_permanent_error(
    authorized: state.PkceAuthorized,
):
    response = OAuthErrorResponse(
        error="invalid_grant", error_description="Refresh token expired"
    )
    assert providers.PkceProvider().process(
        authorized, response, HTTPStatus.BAD_REQUEST
    ) == state.PermanentError(
        mode="pkce",
        error_code="invalid_grant",
        error_description="Refresh token expired",
    )


@pytest.mark.parametrize(
    ("error", "status"),
    [
        ("errorTransient", HTTPStatus.BAD_REQUEST),
        ("temporarily_unavailable", HTTPStatus.BAD_REQUEST),
        ("invalid_grant", HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
def test_pkce_provider_preserves_authorization_on_transient_error(
    authorized: state.PkceAuthorized, error: str, status: int
):
    with pytest.raises(OAuthTokenRefreshError, match=error):
        providers.PkceProvider().process(
            authorized, OAuthErrorResponse(error=error), status
        )


def test_bridge_provider_builds_client_credentials_request(
    bridge: providers.BridgeProvider,
):
    assert bridge.supports(None)
    request = bridge.request(None)
    assert request.method == "POST"
    assert request.url == providers.BRIDGE_REFRESH_URL
    assert request.auth == ("client-id", "client-secret")
    assert request.data == {"grant_type": "client_credentials"}


@pytest.mark.parametrize(
    ("client_id", "client_secret"),
    [(None, None), ("client-id", None), (None, "client-secret")],
)
def test_bridge_provider_requires_complete_credentials(
    client_id: str | None, client_secret: str | None
):
    provider = providers.BridgeProvider(client_id, client_secret)
    assert not provider.supports(None)
    with pytest.raises(
        OAuthTokenRefreshError, match="bridge authorization unavailable"
    ):
        provider.request(None)


@pytest.mark.parametrize(
    "auth_state",
    [
        None,
        state.Cleared(mode="pkce"),
        state.Cleared(mode="bridge"),
        state.BridgeConfigured(),
        state.PermanentError(mode="bridge", error_code="invalid_client"),
    ],
)
def test_bridge_provider_supports_fallback_states(
    bridge: providers.BridgeProvider, auth_state: state.State | None
):
    assert bridge.supports(auth_state)


@pytest.mark.parametrize(
    "auth_state",
    [
        state.PkceAuthorized(refresh_token="refresh-token-1"),  # noqa: S106
        state.PermanentError(mode="pkce", error_code="invalid_grant"),
    ],
)
def test_bridge_provider_rejects_pkce_authorization(
    bridge: providers.BridgeProvider, auth_state: state.State
):
    assert not bridge.supports(auth_state)
    with pytest.raises(
        OAuthTokenRefreshError, match="bridge authorization unavailable"
    ):
        bridge.request(auth_state)
    with pytest.raises(
        OAuthTokenRefreshError, match="bridge authorization unavailable"
    ):
        bridge.process(auth_state, OAuthErrorResponse(error="invalid_client"), 401)


def test_bridge_provider_ignores_unexpected_refresh_token(
    bridge: providers.BridgeProvider,
):
    response = OAuthTokenResponse(
        access_token="access-token-1",  # noqa: S106
        token_type="Bearer",  # noqa: S106
        refresh_token="unexpected-refresh-token",  # noqa: S106
    )
    assert bridge.process(None, response, HTTPStatus.OK) == state.BridgeConfigured()


def test_providers_implement_refresh_provider_protocol(
    bridge: providers.BridgeProvider,
):
    assert isinstance(providers.PkceProvider(), providers.RefreshProvider)
    assert isinstance(bridge, providers.RefreshProvider)


def test_bridge_provider_marks_invalid_client_as_permanent_error(
    bridge: providers.BridgeProvider,
):
    response = OAuthErrorResponse(
        error="invalid_client", error_description="Client not known."
    )
    next_state = bridge.process(None, response, HTTPStatus.UNAUTHORIZED)

    assert isinstance(next_state, state.PermanentError)
    assert next_state.mode == "bridge"
    assert next_state.error_code == "invalid_client"
    assert next_state.error_description == "Client not known."
    assert next_state.credential_fingerprint is not None
    assert credentials.matches(
        next_state.credential_fingerprint, "client-id", "client-secret"
    )


@pytest.mark.parametrize("status", [HTTPStatus.BAD_REQUEST, 599])
def test_bridge_provider_treats_unknown_error_as_transient(
    bridge: providers.BridgeProvider, status: int
):
    with pytest.raises(OAuthTokenRefreshError, match="unexpected_error"):
        bridge.process(None, OAuthErrorResponse(error="unexpected_error"), status)
