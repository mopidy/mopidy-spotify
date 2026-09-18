from http import HTTPStatus

import pytest

from mopidy_spotify import auth_state, pkce, refresh_providers, web


def test_pkce_refresh_provider_builds_refresh_token_request():
    provider = refresh_providers.PkceRefreshProvider()

    request = provider.request_for(
        auth_state.PkceAuthorizedAuthPayload(
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


def test_pkce_refresh_provider_keeps_existing_refresh_token_when_not_rotated():
    provider = refresh_providers.PkceRefreshProvider()
    auth_payload = auth_state.PkceAuthorizedAuthPayload(
        refresh_token="refresh-token-1"  # noqa: S106
    )

    next_payload = provider.state_after_success(
        web.OAuthTokenResponse(
            access_token="access-token-1",  # noqa: S106
            token_type="Bearer",  # noqa: S106
        ),
        auth_payload,
    )

    assert next_payload == auth_payload


def test_pkce_refresh_provider_persists_rotated_refresh_token():
    provider = refresh_providers.PkceRefreshProvider()

    next_payload = provider.state_after_success(
        web.OAuthTokenResponse(
            access_token="access-token-1",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            refresh_token="refresh-token-2",  # noqa: S106
        ),
        auth_state.PkceAuthorizedAuthPayload(
            refresh_token="refresh-token-1"  # noqa: S106
        ),
    )

    assert next_payload == auth_state.PkceAuthorizedAuthPayload(
        refresh_token="refresh-token-2"  # noqa: S106
    )


def test_pkce_refresh_provider_marks_invalid_grant_as_permanent_error():
    provider = refresh_providers.PkceRefreshProvider()

    next_payload = provider.state_after_error(
        web.OAuthErrorResponse(
            error="invalid_grant",
            error_description="Refresh token expired",
        ),
        auth_state.PkceAuthorizedAuthPayload(
            refresh_token="refresh-token-1"  # noqa: S106
        ),
        HTTPStatus.BAD_REQUEST,
    )

    assert next_payload == auth_state.PermanentErrorAuthPayload(
        mode="pkce",
        error_code="invalid_grant",
        error_description="Refresh token expired",
    )


def test_pkce_refresh_provider_raises_transient_error_transient():
    provider = refresh_providers.PkceRefreshProvider()

    with pytest.raises(web.OAuthTokenRefreshError, match="errorTransient"):
        provider.state_after_error(
            web.OAuthErrorResponse(error="errorTransient"),
            auth_state.PkceAuthorizedAuthPayload(
                refresh_token="refresh-token-1"  # noqa: S106
            ),
            HTTPStatus.BAD_REQUEST,
        )


def test_bridge_refresh_provider_builds_client_credentials_request():
    provider = refresh_providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    request = provider.request_for(None)

    assert request is not None
    assert request.url == web.BRIDGE_REFRESH_URL
    assert request.auth == ("client-id", "client-secret")
    assert request.data == {"grant_type": "client_credentials"}


def test_bridge_refresh_provider_returns_none_without_credentials():
    provider = refresh_providers.BridgeRefreshProvider(
        client_id=None,
        client_secret=None,
    )

    assert provider.request_for(None) is None


def test_bridge_refresh_provider_ignores_unexpected_refresh_token():
    provider = refresh_providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    next_payload = provider.state_after_success(
        web.OAuthTokenResponse(
            access_token="access-token-1",  # noqa: S106
            token_type="Bearer",  # noqa: S106
            refresh_token="unexpected-refresh-token",  # noqa: S106
        ),
        None,
    )

    assert next_payload == auth_state.BridgeConfiguredAuthPayload()


def test_bridge_refresh_provider_defers_to_pkce():
    provider = refresh_providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    assert (
        provider.request_for(
            auth_state.PkceAuthorizedAuthPayload(
                refresh_token="refresh-token-1"  # noqa: S106
            )
        )
        is None
    )


def test_providers_implement_refresh_provider_protocol():
    assert isinstance(
        refresh_providers.PkceRefreshProvider(),
        refresh_providers.RefreshProvider,
    )
    assert isinstance(
        refresh_providers.BridgeRefreshProvider(
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
        ),
        refresh_providers.RefreshProvider,
    )


def test_bridge_refresh_provider_marks_invalid_client_as_permanent_error():
    provider = refresh_providers.BridgeRefreshProvider(
        client_id="client-id",
        client_secret="client-secret",  # noqa: S106
    )

    next_payload = provider.state_after_error(
        web.OAuthErrorResponse(
            error="invalid_client",
            error_description="Client not known.",
        ),
        None,
        HTTPStatus.UNAUTHORIZED,
    )

    assert next_payload == auth_state.PermanentErrorAuthPayload(
        mode="bridge",
        error_code="invalid_client",
        error_description="Client not known.",
    )
