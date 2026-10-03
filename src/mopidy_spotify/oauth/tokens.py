"""Token exchange values shared by HTTP and Spotify refresh policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, SecretStr

if TYPE_CHECKING:
    import requests


class OAuthTokenRefreshError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(f"OAuth token refresh failed: {reason}")


class OAuthPermanentRefreshError(OAuthTokenRefreshError):
    pass


class OAuthTokenResponse(BaseModel):
    """Validated in-memory success, separate from persisted authorization."""

    model_config = ConfigDict(extra="ignore", strict=True)

    access_token: SecretStr
    token_type: str
    expires_in: int | float | None = None
    refresh_token: SecretStr | None = None
    scope: str | None = None


class OAuthErrorResponse(BaseModel):
    """Validated failure whose code informs provider transition policy."""

    model_config = ConfigDict(extra="ignore", strict=True)

    error: str
    error_description: str | None = None


class TokenExchange(Protocol):
    def __call__(
        self, request: requests.Request
    ) -> tuple[OAuthTokenResponse | OAuthErrorResponse, int]: ...


class AccessTokenSource(Protocol):
    def refresh(self, exchange: TokenExchange) -> OAuthTokenResponse:
        """Return a token only after required authorization state is persisted."""
        ...
