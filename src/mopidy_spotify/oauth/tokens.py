"""Contracts between HTTP token exchange and authorization policy.

An exchange parses the endpoint response and returns it with the raw HTTP status.
A token source interprets that response and settles authorization persistence
before returning success to the OAuth client for in-memory token installation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, SecretStr

if TYPE_CHECKING:
    import requests


class OAuthTokenRefreshError(Exception):
    """This attempt cannot supply a token; retry policy belongs to the source.

    Network, transient endpoint, and persistence failures leave authorization
    intact. The OAuth client reports the error without installing a token.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"OAuth token refresh failed: {reason}")


class OAuthPermanentRefreshError(OAuthTokenRefreshError):
    """The endpoint rejected authorization, or persisted authorization is unusable.

    PKCE rejection blocks refresh until reauthorization. Bridge credentials live
    in configuration; a fingerprint saved with bridge rejection blocks the rejected
    pair while allowing another attempt after either credential changes. Legacy
    rejections without a fingerprint permit retry until a new rejection records one.
    """


class OAuthTokenResponse(BaseModel):
    """Endpoint-issued access token and optional refresh-token replacement.

    PKCE policy retains its previous refresh token when no replacement is given;
    bridge policy ignores replacements. The OAuth client uses expiry and scope
    after persistence succeeds: absent expiry means no known expiration, while
    zero means immediate expiry. Secret wrappers redact both token values.
    """

    model_config = ConfigDict(extra="ignore", strict=True)

    access_token: SecretStr
    token_type: str
    expires_in: int | float | None = None
    refresh_token: SecretStr | None = None
    scope: str | None = None


class OAuthErrorResponse(BaseModel):
    """Endpoint rejection interpreted alongside HTTP status by grant policy.

    Transient failures preserve authorization for retry. Permanent failures
    propose persisted rejection. Provider eligibility determines whether that
    rejection blocks subsequent attempts or permits configuration-based recovery.
    """

    model_config = ConfigDict(extra="ignore", strict=True)

    error: str
    error_description: str | None = None


class TokenExchange(Protocol):
    """Execute one token request, returning parsed data and an unnormalized status.

    Transport, malformed-response, and invalid-token failures raise
    `OAuthTokenRefreshError`. Valid OAuth rejections remain values so grant
    policy can distinguish transient failure from permanent rejection.
    """

    def __call__(
        self, request: requests.Request
    ) -> tuple[OAuthTokenResponse | OAuthErrorResponse, int]: ...


class AccessTokenSource(Protocol):
    def refresh(self, exchange: TokenExchange) -> OAuthTokenResponse:
        """Return a token only after required authorization state is persisted."""
        ...
