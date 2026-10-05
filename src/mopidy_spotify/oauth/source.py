"""Coordinate Web authorization before exposing an access token.

Load a snapshot, select its provider, exchange its request, then conditionally
persist the processed result. Only after persistence succeeds
may the OAuth client install the returned access token. HTTP runs without the
store lock, so logout or reauthorization can invalidate an in-flight result.
"""

from __future__ import annotations

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
        self._providers: tuple[providers.RefreshProvider, ...] = (pkce, bridge)

    def _load(self) -> store.Snapshot | None:
        if self._store is None:
            return None

        try:
            return self._store.load()

        except (store.InvalidManifestError, store.Error) as exc:
            msg = f"{exc}. Run `mopidy spotify auth web` to replace it."
            raise OAuthPermanentRefreshError(msg) from exc

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

    def _select_provider(
        self, auth_state: state.State | None
    ) -> providers.RefreshProvider | None:
        for provider in self._providers:
            if provider.supports(auth_state):
                return provider

        return None

    def refresh(self, exchange: TokenExchange) -> OAuthTokenResponse:
        snapshot = self._load()
        auth_state = snapshot.state if snapshot is not None else None
        provider = self._select_provider(auth_state)
        if provider is None:
            if isinstance(auth_state, state.PermanentError):
                detail = auth_state.error_description or auth_state.error_code
                raise OAuthPermanentRefreshError(detail)

            msg = "No refresh provider available."
            raise OAuthTokenRefreshError(msg)

        request = provider.request(auth_state)
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
