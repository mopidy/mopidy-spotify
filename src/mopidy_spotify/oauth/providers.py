"""Refresh policies for Spotify Web authorization.

Providers choose grants and propose transitions from resolved runtime state.
They neither send HTTP requests nor handle persisted manifests or token storage;
those responsibilities belong to the executor and authorization store. This
keeps PKCE rotation and legacy bridge fallback separate from HTTP handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Literal, Protocol, runtime_checkable

import requests

from mopidy_spotify import web
from mopidy_spotify.oauth import pkce, state


@runtime_checkable
class RefreshProvider(Protocol):
    """Grant-specific policy consulted by the access-token refresh executor.

    Providers see resolved runtime state; the executor and store own HTTP
    exchange and persisted manifests.
    """

    def request_for(
        self,
        auth_state: state.State | None,
    ) -> requests.Request | None:
        """Defer to the next provider when this grant does not apply."""
        ...

    def state_after_success(
        self,
        response: web.OAuthTokenResponse,
        auth_state: state.State | None,
    ) -> state.State:
        """Propose the next state; persistence precedes access-token installation."""
        ...

    def state_after_error(
        self,
        response: web.OAuthErrorResponse,
        auth_state: state.State | None,
        status_code: int | HTTPStatus | None = None,
    ) -> state.State:
        """Propose permanent failure or raise to preserve state for retry."""
        ...


def _is_permanent_error(
    response: web.OAuthErrorResponse,
    status_code: int | HTTPStatus | None,
) -> bool:
    if response.error in {
        "temporarily_unavailable",
        "server_error",
        "errorTransient",  # Spotify historically used this non-standard name.
    }:
        return False

    if status_code in {
        HTTPStatus.INTERNAL_SERVER_ERROR,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }:
        return False

    return response.error in {
        "invalid_request",
        "invalid_client",
        "invalid_grant",
        "unauthorized_client",
        "unsupported_grant_type",
        "invalid_scope",
    }


def _state_after_error(
    response: web.OAuthErrorResponse,
    status_code: int | HTTPStatus | None,
    *,
    mode: Literal["pkce", "bridge"],
) -> state.PermanentError:
    if not _is_permanent_error(response, status_code):
        detail = response.error_description or response.error
        raise web.OAuthTokenRefreshError(detail)
    return state.PermanentError(
        mode=mode,
        error_code=response.error,
        error_description=response.error_description,
    )


class PkceRefreshProvider:
    def request_for(
        self,
        auth_state: state.State | None,
    ) -> requests.Request | None:
        if not isinstance(auth_state, state.PkceAuthorized):
            return None

        return requests.Request(
            "POST",
            web.SPOTIFY_REFRESH_URL,
            data={
                "client_id": pkce.CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": auth_state.refresh_token.get_secret_value(),
            },
        )

    def state_after_success(
        self,
        response: web.OAuthTokenResponse,
        auth_state: state.State | None,
    ) -> state.State:
        if not isinstance(auth_state, state.PkceAuthorized):
            msg = "missing PKCE authorization state"
            raise web.OAuthTokenRefreshError(msg)

        refresh_token = response.refresh_token
        if refresh_token is None or not refresh_token.get_secret_value():
            refresh_token = auth_state.refresh_token
        return state.PkceAuthorized(refresh_token=refresh_token)

    def state_after_error(
        self,
        response: web.OAuthErrorResponse,
        auth_state: state.State | None,
        status_code: int | HTTPStatus | None = None,
    ) -> state.State:
        _ = auth_state
        return _state_after_error(response, status_code, mode="pkce")


@dataclass(frozen=True)
class BridgeRefreshProvider:
    client_id: str | None
    client_secret: str | None

    def request_for(
        self,
        auth_state: state.State | None,
    ) -> requests.Request | None:
        if isinstance(auth_state, state.PkceAuthorized) or (
            isinstance(auth_state, state.PermanentError) and auth_state.mode == "pkce"
        ):
            return None
        if not self.client_id or not self.client_secret:
            return None

        return requests.Request(
            "POST",
            web.BRIDGE_REFRESH_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "client_credentials"},
        )

    def state_after_success(
        self,
        response: web.OAuthTokenResponse,
        auth_state: state.State | None,
    ) -> state.State:
        _ = response, auth_state
        return state.BridgeConfigured()

    def state_after_error(
        self,
        response: web.OAuthErrorResponse,
        auth_state: state.State | None,
        status_code: int | HTTPStatus | None = None,
    ) -> state.State:
        _ = auth_state
        return _state_after_error(response, status_code, mode="bridge")
