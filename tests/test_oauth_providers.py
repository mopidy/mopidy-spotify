from http import HTTPStatus

import pytest

from mopidy_spotify import web
from mopidy_spotify.oauth import pkce, providers, state


def test_pkce_refresh_provider_builds_refresh_token_request():
    provider = providers.PkceRefreshProvider()

    request = provider.request_for(
        state.PkceAuthorized(
            refresh_token="refresh-token-1"  # noqa: S106
        )
    )

    assert request is not None
    assert request.url == web.SPOTIFY_REFRESH_URL
    assert request.auth is None
    assert request.data == {
        "client_id": pkce.CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": "refresh-token-1",
    }


def test_pkce_refresh_provider_declines_non_authorized_state():
    assert providers.PkceRefreshProvider().request_for(None) is None


def test_pkce_refresh_provider_keeps_existing_refresh_token_when_not_rotated():
    provider = providers.PkceRefreshProvider()
    auth_state = state.PkceAuthorized(
        refresh_token="refresh-token-1"  # noqa: S106
    )

    next_state = provider.state_after_success(
        web.OAuthTokenResponse(
            access_token="access-token-1",  # noqa: S106
            token_type="Bearer",  # noqa: S106
        ),
        auth_state,
    )

    assert next_state == auth_state


def test_pkce_refresh_provider_requires_authorized_state_for_success():
    with pytest.raises(web.OAuthTokenRefreshError, match="missing PKCE"):
        providers.PkceRefreshProvider().state_after_success(
            web.OAuthTokenResponse(
                access_token="access-token",  # noqa: S106
                token_type="Bearer",  # noqa: S106
            ),
            None,
        )


def test_pkce_refresh_provider_persists_rotated_refresh_token():
    provider = providers.PkceRefreshProvider()

    next_state = provider.state_after_success(
        web.OAuthTokenResponse(
            access_token="access-token-1",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            refresh_token="refresh-token-2",  # noqa: S106
        ),
        state.PkceAuthorized(
            refresh_token="refresh-token-1"  # noqa: S106
        ),
    )

    assert next_state == state.PkceAuthorized(
        refresh_token="refresh-token-2"  # noqa: S106
    )


def test_pkce_refresh_provider_marks_invalid_grant_as_permanent_error():
    provider = providers.PkceRefreshProvider()

    next_state = provider.state_after_error(
        web.OAuthErrorResponse(
            error="invalid_grant",
            error_description="Refresh token expired",
        ),
        state.PkceAuthorized(
            refresh_token="refresh-token-1"  # noqa: S106
        ),
        HTTPStatus.BAD_REQUEST,
    )

    assert next_state == state.PermanentError(
        mode="pkce",
        error_code="invalid_grant",
        error_description="Refresh token expired",
    )


def test_pkce_refresh_provider_raises_transient_error_transient():
    provider = providers.PkceRefreshProvider()

    with pytest.raises(web.OAuthTokenRefreshError, match="errorTransient"):
        provider.state_after_error(
            web.OAuthErrorResponse(error="errorTransient"),
            state.PkceAuthorized(
                refresh_token="refresh-token-1"  # noqa: S106
            ),
            HTTPStatus.BAD_REQUEST,
        )


def test_pkce_refresh_provider_treats_temporary_unavailability_as_transient():
    with pytest.raises(web.OAuthTokenRefreshError, match="temporarily_unavailable"):
        providers.PkceRefreshProvider().state_after_error(
            web.OAuthErrorResponse(error="temporarily_unavailable"),
            state.PkceAuthorized(refresh_token="refresh-token"),  # noqa: S106
            HTTPStatus.BAD_REQUEST,
        )


def test_pkce_refresh_provider_treats_server_error_status_as_transient():
    provider = providers.PkceRefreshProvider()

    with pytest.raises(web.OAuthTokenRefreshError, match="invalid_grant"):
        provider.state_after_error(
            web.OAuthErrorResponse(error="invalid_grant"),
            state.PkceAuthorized(
                refresh_token="refresh-token-1"  # noqa: S106
            ),
            HTTPStatus.INTERNAL_SERVER_ERROR,
        )


def test_bridge_refresh_provider_builds_client_credentials_request():
    provider = providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    request = provider.request_for(None)

    assert request is not None
    assert request.url == web.BRIDGE_REFRESH_URL
    assert request.auth == ("client-id", "client-secret")
    assert request.data == {"grant_type": "client_credentials"}


def test_bridge_refresh_provider_returns_none_without_credentials():
    provider = providers.BridgeRefreshProvider(
        client_id=None,
        client_secret=None,
    )

    assert provider.request_for(None) is None


def test_bridge_refresh_provider_ignores_unexpected_refresh_token():
    provider = providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    next_state = provider.state_after_success(
        web.OAuthTokenResponse(
            access_token="access-token-1",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            refresh_token="unexpected-refresh-token",  # noqa: S106
        ),
        None,
    )

    assert next_state == state.BridgeConfigured()


def test_bridge_refresh_provider_defers_to_pkce():
    provider = providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    assert (
        provider.request_for(
            state.PkceAuthorized(
                refresh_token="refresh-token-1"  # noqa: S106
            )
        )
        is None
    )


def test_bridge_refresh_provider_does_not_fall_back_after_pkce_failure():
    provider = providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    assert (
        provider.request_for(
            state.PermanentError(mode="pkce", error_code="invalid_grant")
        )
        is None
    )


def test_providers_implement_refresh_provider_protocol():
    assert isinstance(
        providers.PkceRefreshProvider(),
        providers.RefreshProvider,
    )
    assert isinstance(
        providers.BridgeRefreshProvider(
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
        ),
        providers.RefreshProvider,
    )


def test_bridge_refresh_provider_marks_invalid_client_as_permanent_error():
    provider = providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    next_state = provider.state_after_error(
        web.OAuthErrorResponse(
            error="invalid_client",
            error_description="Client not known.",
        ),
        None,
        HTTPStatus.UNAUTHORIZED,
    )

    assert next_state == state.PermanentError(
        mode="bridge",
        error_code="invalid_client",
        error_description="Client not known.",
    )


def test_bridge_refresh_provider_treats_unknown_error_as_transient():
    provider = providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    with pytest.raises(web.OAuthTokenRefreshError, match="unexpected_error"):
        provider.state_after_error(
            web.OAuthErrorResponse(error="unexpected_error"),
            None,
            HTTPStatus.BAD_REQUEST,
        )
