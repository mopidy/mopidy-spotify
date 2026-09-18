"""Standalone refresh-provider policies for Spotify OAuth.

The providers here decide whether they can handle the current auth state,
build the token request, and map token responses back to auth state payloads.
They are intentionally small and internal so the wrapper can stay thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Protocol, runtime_checkable

import requests

from mopidy_spotify import auth_state, pkce, web


@runtime_checkable
class RefreshProvider(Protocol):
    def request_for(
        self,
        auth_payload: auth_state.AuthPayload | None,
    ) -> requests.Request | None:
        """Return a request, or ``None`` to let the next provider try."""
        ...

    def state_after_success(
        self,
        response: web.OAuthTokenResponse,
        auth_payload: auth_state.AuthPayload | None,
    ) -> auth_state.AuthPayload:
        """Return the state to persist after the executor validates a response."""
        ...

    def state_after_error(
        self,
        response: web.OAuthErrorResponse,
        auth_payload: auth_state.AuthPayload | None,
        status_code: int | HTTPStatus | None = None,
    ) -> auth_state.AuthPayload:
        """Return permanent error state, or raise when the failure is transient."""
        ...


def _is_permanent_error(
    response: web.OAuthErrorResponse,
    status_code: int | HTTPStatus | None,
) -> bool:
    match response.error:
        case "temporarily_unavailable" | "server_error":
            return False
        case "errorTransient":
            # Spotify historically used this non-standard error name.
            return False

    if status_code in {
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


class PkceRefreshProvider:
    def request_for(
        self,
        auth_payload: auth_state.AuthPayload | None,
    ) -> requests.Request | None:
        if not isinstance(auth_payload, auth_state.PkceAuthorizedAuthPayload):
            return None

        return requests.Request(
            "POST",
            web.SPOTIFY_REFRESH_URL,
            data={
                "client_id": pkce.CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": auth_payload.refresh_token.get_secret_value(),
            },
        )

    def state_after_success(
        self,
        response: web.OAuthTokenResponse,
        auth_payload: auth_state.AuthPayload | None,
    ) -> auth_state.AuthPayload:
        if not isinstance(auth_payload, auth_state.PkceAuthorizedAuthPayload):
            msg = "missing pkce auth payload"
            raise web.OAuthTokenRefreshError(msg)

        refresh_token = response.refresh_token
        if refresh_token is None or not refresh_token.get_secret_value():
            refresh_token = auth_payload.refresh_token
        return auth_state.PkceAuthorizedAuthPayload(refresh_token=refresh_token)

    def state_after_error(
        self,
        response: web.OAuthErrorResponse,
        auth_payload: auth_state.AuthPayload | None,
        status_code: int | HTTPStatus | None = None,
    ) -> auth_state.AuthPayload:
        _ = auth_payload
        if not _is_permanent_error(response, status_code):
            detail = response.error_description or response.error
            raise web.OAuthTokenRefreshError(detail)
        return auth_state.PermanentErrorAuthPayload(
            mode="pkce",
            error_code=response.error,
            error_description=response.error_description,
        )


@dataclass(frozen=True)
class BridgeRefreshProvider:
    client_id: str | None
    client_secret: str | None

    def request_for(
        self,
        auth_payload: auth_state.AuthPayload | None,
    ) -> requests.Request | None:
        if isinstance(auth_payload, auth_state.PkceAuthorizedAuthPayload):
            return None
        if self.client_id is None or self.client_secret is None:
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
        auth_payload: auth_state.AuthPayload | None,
    ) -> auth_state.AuthPayload:
        _ = response, auth_payload
        return auth_state.BridgeConfiguredAuthPayload()

    def state_after_error(
        self,
        response: web.OAuthErrorResponse,
        auth_payload: auth_state.AuthPayload | None,
        status_code: int | HTTPStatus | None = None,
    ) -> auth_state.AuthPayload:
        _ = auth_payload
        if not _is_permanent_error(response, status_code):
            detail = response.error_description or response.error
            raise web.OAuthTokenRefreshError(detail)
        return auth_state.PermanentErrorAuthPayload(
            mode="bridge",
            error_code=response.error,
            error_description=response.error_description,
        )
