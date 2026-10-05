"""Refresh providers for Spotify Web authorization.

A provider owns grant-specific eligibility, request construction, and response
processing so the coordinator can persist transitions without knowing grant
details. Providers perform neither HTTP nor persistence. An exchange failure
never selects a different provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import (
    TYPE_CHECKING,
    Literal,
    Protocol,
    TypeGuard,
    override,
    runtime_checkable,
)

import requests

from mopidy_spotify.oauth import pkce, state
from mopidy_spotify.oauth.tokens import (
    OAuthErrorResponse,
    OAuthTokenRefreshError,
    OAuthTokenResponse,
)

if TYPE_CHECKING:
    from pydantic import SecretStr

BRIDGE_REFRESH_URL = "https://auth.mopidy.com/spotify/token"
SPOTIFY_REFRESH_URL = "https://accounts.spotify.com/api/token"


@runtime_checkable
class RefreshProvider(Protocol):
    """Grant policy selected once for the current authorization snapshot."""

    def supports(self, auth_state: state.State | None) -> bool: ...

    def request(self, auth_state: state.State | None) -> requests.Request: ...

    def process(
        self,
        auth_state: state.State | None,
        response: OAuthTokenResponse | OAuthErrorResponse,
        status_code: int,
    ) -> state.State:
        """Propose state for persistence, or raise to preserve it for retry."""
        ...


class PkceProvider(RefreshProvider):
    """Refresh locally authorized PKCE tokens, retaining or rotating the secret."""

    @override
    def supports(
        self, auth_state: state.State | None
    ) -> TypeGuard[state.PkceAuthorized]:
        return isinstance(auth_state, state.PkceAuthorized)

    @override
    def request(self, auth_state: state.State | None) -> requests.Request:
        if not self.supports(auth_state):
            msg = "missing PKCE authorization state"
            raise OAuthTokenRefreshError(msg)

        return requests.Request(
            "POST",
            SPOTIFY_REFRESH_URL,
            data={
                "client_id": pkce.CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": auth_state.refresh_token.get_secret_value(),
            },
        )

    @override
    def process(
        self,
        auth_state: state.State | None,
        response: OAuthTokenResponse | OAuthErrorResponse,
        status_code: int,
    ) -> state.State:
        if not self.supports(auth_state):
            msg = "missing PKCE authorization state"
            raise OAuthTokenRefreshError(msg)

        if isinstance(response, OAuthErrorResponse):
            return _state_after_error(response, status_code, mode="pkce")

        if _has_secret(response.refresh_token):
            return state.PkceAuthorized(refresh_token=response.refresh_token)

        return state.PkceAuthorized(refresh_token=auth_state.refresh_token)


@dataclass(frozen=True)
class BridgeProvider(RefreshProvider):
    """Exchange configured bridge credentials without adopting refresh tokens."""

    client_id: str | None
    client_secret: str | None

    @override
    def supports(self, auth_state: state.State | None) -> bool:
        # Each refresh attempts the bridge again after permanent rejection,
        # even with unchanged credentials, to allow configuration-based recovery.
        # The credential-fingerprint follow-up will block unchanged credentials.
        # PKCE rejection stays blocked until reauthorization.
        # TODO: Bind bridge rejection to a safely stored credential fingerprint
        # so only changed credentials permit retry; include it in stale-result checks.
        first_time = auth_state is None
        authorization_reset = isinstance(auth_state, state.Cleared)
        bridge_configured = isinstance(auth_state, state.BridgeConfigured)
        rejected_credentials_may_have_changed = (
            isinstance(auth_state, state.PermanentError) and auth_state.mode == "bridge"
        )

        return self._credentials() is not None and (
            first_time
            or authorization_reset
            or bridge_configured
            or rejected_credentials_may_have_changed
        )

    @override
    def request(self, auth_state: state.State | None) -> requests.Request:
        credentials = self._credentials()
        if credentials is None or not self.supports(auth_state):
            msg = "bridge authorization unavailable"
            raise OAuthTokenRefreshError(msg)

        return requests.Request(
            "POST",
            BRIDGE_REFRESH_URL,
            auth=credentials,
            data={"grant_type": "client_credentials"},
        )

    @override
    def process(
        self,
        auth_state: state.State | None,
        response: OAuthTokenResponse | OAuthErrorResponse,
        status_code: int,
    ) -> state.State:
        if not self.supports(auth_state):
            msg = "bridge authorization unavailable"
            raise OAuthTokenRefreshError(msg)

        if isinstance(response, OAuthErrorResponse):
            return _state_after_error(response, status_code, mode="bridge")

        return state.BridgeConfigured()

    def _credentials(self) -> tuple[str, str] | None:
        if not self.client_id or not self.client_secret:
            return None

        return self.client_id, self.client_secret


def _has_secret(secret: SecretStr | None) -> TypeGuard[SecretStr]:
    return secret is not None and bool(secret.get_secret_value())


def _is_permanent_error(
    response: OAuthErrorResponse,
    status_code: int,
) -> bool:
    # Keep raw integer codes: endpoints may return statuses outside HTTPStatus.
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
    response: OAuthErrorResponse,
    status_code: int,
    *,
    mode: Literal["pkce", "bridge"],
) -> state.PermanentError:
    if not _is_permanent_error(response, status_code):
        detail = response.error_description or response.error
        raise OAuthTokenRefreshError(detail)

    return state.PermanentError(
        mode=mode,
        error_code=response.error,
        error_description=response.error_description,
    )
