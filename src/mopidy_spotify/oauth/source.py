"""Own Web authorization eligibility, reporting, and refresh.

Status and refresh resolve the same saved authorization and current credentials.
Reporting never contacts Spotify or changes authorization; refresh makes a request
only when that resolution permits it. Saved rejection can forbid requests across
restarts, while changed legacy credentials may permit another attempt.

Refresh persists its result before exposing an access token. HTTP runs without the
store lock, so logout or reauthorization can invalidate an in-flight result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from mopidy_spotify.oauth import providers, state, store
from mopidy_spotify.oauth.tokens import (
    OAuthErrorResponse,
    OAuthPermanentRefreshError,
    OAuthTokenRefreshError,
    OAuthTokenResponse,
    TokenExchange,
)


class SpotifyAccessTokenSource:
    def __init__(
        self,
        *,
        pkce: providers.PkceProvider,
        bridge: providers.BridgeProvider,
        auth_store: store.Store | None = None,
    ) -> None:
        self._store = auth_store
        self._pkce = pkce
        self._bridge = bridge

    def status(self) -> str:
        """Describe local authorization without HTTP requests or state changes."""
        try:
            _, decision = self._resolve()
            return _describe_decision(decision)
        except store.InvalidManifestError:
            return "invalid authorization state"
        except (store.Error, OSError) as exc:
            return f"unavailable ({exc})"

    def refresh(self, exchange: TokenExchange) -> OAuthTokenResponse:
        try:
            snapshot, decision = self._resolve()
        except (store.InvalidManifestError, store.Error) as exc:
            msg = f"{exc}. Run `mopidy spotify auth web` to replace it."
            raise OAuthPermanentRefreshError(msg) from exc

        auth_state = snapshot.state if snapshot is not None else None
        match decision:
            case _Ready(provider=provider):
                request = provider.request(auth_state)
            case _Rejected(error=error):
                detail = error.error_description or error.error_code
                raise OAuthPermanentRefreshError(detail)
            case _LegacyCredentialsMissing():
                msg = (
                    "Legacy authentication is selected. Configure both "
                    "spotify/client_id and spotify/client_secret."
                )
                raise OAuthTokenRefreshError(msg)
            case _NoAuthorization():
                msg = "No refresh provider available."
                raise OAuthTokenRefreshError(msg)
            case _:
                assert_never(decision)

        response, status_code = exchange(request)
        next_state = provider.process(auth_state, response, status_code)
        self._save(snapshot, next_state)
        match response:
            case OAuthTokenResponse() as success:
                return success

            case OAuthErrorResponse() as error:
                if next_state.mode == "pkce":
                    detail = (
                        "Spotify refresh token is no longer valid. "
                        "Run `mopidy spotify auth web` to reauthorize."
                    )
                else:
                    detail = error.error_description or error.error
                raise OAuthPermanentRefreshError(detail)

            case _:
                assert_never(response)

    def _resolve(self) -> tuple[store.Snapshot | None, _Decision]:
        snapshot = self._store.load() if self._store is not None else None
        auth_state = snapshot.state if snapshot is not None else None

        match auth_state:
            case state.PkceAuthorized():
                decision = _Ready(self._pkce)
            case None | state.Cleared():
                # Missing or cleared local authorization permits legacy fallback,
                # but credentials must still be supplied by Mopidy configuration.
                decision = (
                    _Ready(self._bridge)
                    if self._bridge.supports(auth_state)
                    else _NoAuthorization()
                )
            case state.BridgeConfigured():
                # Explicit selection records intent, not credential availability.
                decision = (
                    _Ready(self._bridge)
                    if self._bridge.supports(auth_state)
                    else _LegacyCredentialsMissing()
                )
            case state.PermanentError():
                match auth_state.mode:
                    case "pkce":
                        # Rejected local authorization must not enable fallback.
                        decision = _Rejected(auth_state)
                    case "bridge":
                        # Rejection blocks the rejected credential pair. Changed
                        # credentials, or older records without a fingerprint,
                        # permit retry, but are not verified by that permission.
                        decision = (
                            _Ready(self._bridge)
                            if self._bridge.supports(auth_state)
                            else _Rejected(auth_state)
                        )
                    case _:
                        assert_never(auth_state.mode)
            case _:
                assert_never(auth_state)

        return snapshot, decision

    def _save(self, expected: store.Snapshot | None, next_state: state.State) -> None:
        if self._store is None:
            return

        try:
            saved = self._store.compare_and_set(expected, next_state)
        except (store.InvalidManifestError, store.Error) as exc:
            msg = "could not persist Spotify authorization state"
            raise OAuthTokenRefreshError(msg) from exc

        if not saved:
            msg = "Spotify authorization changed during token refresh"
            raise OAuthTokenRefreshError(msg)


@dataclass(frozen=True)
class _Ready:
    provider: providers.PkceProvider | providers.BridgeProvider


@dataclass(frozen=True)
class _Rejected:
    error: state.PermanentError


@dataclass(frozen=True)
class _LegacyCredentialsMissing:
    pass


@dataclass(frozen=True)
class _NoAuthorization:
    pass


type _Decision = _Ready | _Rejected | _LegacyCredentialsMissing | _NoAuthorization


def _describe_decision(decision: _Decision) -> str:
    match decision:
        case _Ready(provider=provider):
            match provider:
                case providers.PkceProvider():
                    return "authorized (PKCE)"
                case providers.BridgeProvider():
                    return "configured (legacy)"
                case _:
                    assert_never(provider)
        case _Rejected(error=error):
            match error.mode:
                case "pkce":
                    return "PKCE authorization rejected"
                case "bridge":
                    return "legacy authorization rejected"
                case _:
                    assert_never(error.mode)
        case _LegacyCredentialsMissing() | _NoAuthorization():
            return "not authorized"
        case _:
            assert_never(decision)
