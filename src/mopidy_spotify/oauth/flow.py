"""Interactive Spotify auth flow orchestration.

This module coordinates the user-facing PKCE auth exchange: generate the
challenge, validate the callback, exchange the code for a refresh token, and
persist the resulting auth state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

import requests
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from mopidy_spotify import utils
from mopidy_spotify.oauth import pkce, state

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pathlib import Path

    from mopidy.config import Config


type OAuthErrorCode = Literal[
    "invalid_request",
    "invalid_client",
    "invalid_grant",
    "unauthorized_client",
    "unsupported_grant_type",
    "invalid_scope",
]


class TokenExchangeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    refresh_token: SecretStr | None = None
    # The enum covers RFC-defined values; `str` keeps non-compliant provider
    # errors like Spotify's `errorTransient`.
    error: OAuthErrorCode | str | None = None
    error_description: str | None = None


@dataclass(frozen=True)
class AuthChallenge:
    authorization_url: str
    state: str
    verifier: str


@dataclass(frozen=True)
class AuthSuccess:
    refresh_token: str


class AuthFlowError(Exception):
    pass


class AuthInvalidStateError(AuthFlowError):
    def __init__(self) -> None:
        super().__init__("Incorrect state returned, please try again.")


class AuthMissingCodeError(AuthFlowError):
    def __init__(self) -> None:
        super().__init__("Authentication code missing, please try again.")


class AuthExchangeError(AuthFlowError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"Something went wrong: {detail}")


class PkceVerifierGenerator(Protocol):
    """Build the PKCE verifier and derived code challenge."""

    def __call__(self) -> tuple[str, str]: ...


class StateGenerator(Protocol):
    """Generate the CSRF state value for an auth attempt."""

    def __call__(self) -> str: ...


class AuthorizationUrlGenerator(Protocol):
    """Build the user-facing Spotify authorization URL."""

    def __call__(self, challenge: str, state: str, /) -> str: ...


class AuthorizationResultParser(Protocol):
    """Parse the pasted auth callback payload into auth parameters."""

    def __call__(self, pasted_result: str, /) -> pkce.AuthorizationResult: ...


class AuthorizationCodeExchanger(Protocol):
    """Exchange an authorization code for the token endpoint payload."""

    def __call__(
        self, config: Config, code: str, verifier: str, /
    ) -> TokenExchangeResponse: ...


def _exchange_authorization_code(
    config: Config, code: str, verifier: str
) -> TokenExchangeResponse:
    session = utils.get_requests_session(config.get("proxy", {}))
    request = session.prepare_request(pkce.exchange_code_request(code, verifier))
    timeout = max(config.get("spotify", {}).get("timeout", 10), 1)

    try:
        payload = session.send(request, timeout=timeout).json()
    except ValueError as exc:
        msg = "invalid token response."
        raise ValueError(msg) from exc
    except (OSError, requests.RequestException) as exc:
        msg = str(exc) or exc.__class__.__name__
        raise ValueError(msg) from exc

    try:
        result = TokenExchangeResponse.model_validate(payload)
    except ValidationError as exc:
        logger.debug(
            "Invalid OAuth token exchange response: %s",
            exc.errors(include_url=False, include_context=False, include_input=False),
        )
        msg = "invalid token response."
    else:
        if result.error is None and result.refresh_token is None:
            msg = "missing refresh_token."
            raise ValueError(msg)
        return result

    raise ValueError(msg)


class AuthFlow:
    def __init__(  # noqa: PLR0913
        self,
        config: Config,
        auth_state_path: Path,
        *,
        # Inject collaborators so tests can replace side effects cleanly.
        generate_pkce_verifier: PkceVerifierGenerator = pkce.generate_pkce_verifier,
        generate_state: StateGenerator = pkce.generate_state,
        generate_authorization_url: AuthorizationUrlGenerator = (
            pkce.generate_authorization_url
        ),
        parse_authorization_result: AuthorizationResultParser = (
            pkce.parse_authorization_result
        ),
        exchange_authorization_code: AuthorizationCodeExchanger = (
            _exchange_authorization_code
        ),
    ) -> None:
        self._config = config
        self._auth_state_store = state.FileAuthStateStore(auth_state_path)
        self._generate_pkce_verifier = generate_pkce_verifier
        self._generate_state = generate_state
        self._generate_authorization_url = generate_authorization_url
        self._parse_authorization_result = parse_authorization_result
        self._exchange_authorization_code = exchange_authorization_code

    def start_auth(self) -> AuthChallenge:
        """Create the PKCE challenge shown to the user before auth completes."""
        verifier, challenge = self._generate_pkce_verifier()
        state = self._generate_state()
        return AuthChallenge(
            authorization_url=self._generate_authorization_url(challenge, state),
            state=state,
            verifier=verifier,
        )

    def finish_auth(self, challenge: AuthChallenge, pasted_result: str) -> AuthSuccess:
        try:
            params = self._parse_authorization_result(pasted_result)
        except ValueError as exc:
            raise AuthExchangeError(str(exc)) from exc

        if params.state != challenge.state:
            raise AuthInvalidStateError

        if not params.code:
            raise AuthMissingCodeError

        try:
            result = self._exchange_authorization_code(
                self._config, params.code, challenge.verifier
            )
        except ValueError as exc:
            raise AuthExchangeError(str(exc)) from exc

        if result.error is not None:
            raise AuthExchangeError(result.error_description or result.error)

        secret = result.refresh_token
        if secret is None:
            msg = "missing refresh_token."
            raise AuthExchangeError(msg)
        self._auth_state_store.save(
            state.PkceAuthorizedAuthPayload(refresh_token=secret)
        )
        return AuthSuccess(secret.get_secret_value())
