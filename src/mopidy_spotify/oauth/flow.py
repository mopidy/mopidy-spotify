"""Initial authorization for Spotify's public Web API.

This flow is separate from librespot playback authorization. It creates a PKCE
challenge and CSRF state, validates the callback pasted back from the website,
exchanges the authorization code locally, and passes the refresh token to an
injected authorization writer. The writer factory composes initial storage
policy; the browser flow itself does not select backends or own persistence.

Starting and finishing are separate so the CLI can hand control to the user
without persisting the verifier or CSRF state. The callback website only
displays values for the user to copy; it never receives the verifier or tokens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol, assert_never

import requests
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from mopidy_spotify import utils
from mopidy_spotify.oauth import manifest, pkce, store

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mopidy.config import Config


class StoragePolicy(StrEnum):
    """Initial authorization choices, distinct from the persisted storage backend."""

    AUTO = "auto"
    PLAINTEXT = "plaintext"
    KEYRING = "keyring"


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


class AuthFlowError(Exception):
    pass


class AuthStateMismatchError(AuthFlowError):
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


class AuthorizationWriter(Protocol):
    """Persist an initial refresh token, or raise `AuthFlowError` on failure."""

    def __call__(self, token: SecretStr, /) -> None: ...


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
        *,
        persist_authorization: AuthorizationWriter,
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
        self._persist_authorization = persist_authorization
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

    def finish_auth(self, challenge: AuthChallenge, pasted_result: str) -> None:
        try:
            params = self._parse_authorization_result(pasted_result)
        except ValueError as exc:
            raise AuthExchangeError(str(exc)) from exc

        if params.state != challenge.state:
            raise AuthStateMismatchError

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
        self._persist_authorization(secret)


def authorization_writer(
    auth_store: store.Store,
    policy: StoragePolicy = StoragePolicy.AUTO,
) -> AuthorizationWriter:
    """Build an initial authorization writer with flow-facing errors.

    Auto retries as plaintext only if keyring staging fails before manifest
    publication. Manifest persistence errors never change the chosen backend.
    """

    def write(token: SecretStr) -> None:
        try:
            _persist_initial(auth_store, token, policy)
        except store.Error as exc:
            raise AuthExchangeError(str(exc)) from exc

    return write


def _persist_initial(
    auth_store: store.Store,
    token: SecretStr,
    policy: StoragePolicy,
) -> None:
    """Apply the initial storage policy without fallback after manifest failure."""
    match policy:
        case StoragePolicy.PLAINTEXT:
            auth_store.persist_pkce_authorization(token, manifest.StorageType.INLINE)
        case StoragePolicy.KEYRING:
            auth_store.persist_pkce_authorization(token, manifest.StorageType.KEYRING)
        case StoragePolicy.AUTO:
            try:
                auth_store.persist_pkce_authorization(
                    token, manifest.StorageType.KEYRING
                )
            except store.KeyringWriteError:
                logger.warning(
                    "Could not store the refresh token in keyring. It will be stored "
                    "in plaintext in auth.json, protected by file permissions. "
                    "For keyring storage, install mopidy-spotify[keyring] and "
                    "configure an accessible keyring, or use --storage keyring "
                    "to require it."
                )
                auth_store.persist_pkce_authorization(
                    token, manifest.StorageType.INLINE
                )
        case _:
            assert_never(policy)
