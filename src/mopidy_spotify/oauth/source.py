"""Spotify Web access-token acquisition and authorization-state transitions."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from mopidy_spotify.oauth import providers, state, store
from mopidy_spotify.oauth.tokens import (
    OAuthErrorResponse,
    OAuthPermanentRefreshError,
    OAuthTokenRefreshError,
    OAuthTokenResponse,
    TokenExchange,
)

if TYPE_CHECKING:
    from pathlib import Path


class SpotifyAccessTokenSource:
    def __init__(
        self,
        *,
        client_id: str | None,
        client_secret: str | None,
        auth_state_path: Path | None = None,
    ) -> None:
        self._store = (
            store.Store(auth_state_path) if auth_state_path is not None else None
        )
        self._providers: tuple[providers.RefreshProvider, ...] = (
            providers.PkceRefreshProvider(),
            providers.BridgeRefreshProvider(
                client_id=client_id, client_secret=client_secret
            ),
        )

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

    def refresh(self, exchange: TokenExchange) -> OAuthTokenResponse:
        snapshot = self._load()
        auth_state = snapshot.state if snapshot is not None else None
        # TODO: A saved bridge permanent error currently retries even with the
        # same credentials. A follow-up PR will distinguish bridge OAuth failures
        # from Web API 401 rejection before deciding when to stop retrying.
        if isinstance(auth_state, state.PermanentError) and auth_state.mode == "pkce":
            detail = auth_state.error_description or auth_state.error_code
            raise OAuthPermanentRefreshError(detail)

        for provider in self._providers:
            request = provider.request_for(auth_state)
            if request is not None:
                break
        else:
            msg = "No refresh provider available."
            raise OAuthTokenRefreshError(msg)

        response, status_code = exchange(request)
        match response:
            case OAuthTokenResponse() as success:
                self._save(snapshot, provider.state_after_success(success, auth_state))
                return success
            case OAuthErrorResponse() as error:
                next_state = provider.state_after_error(error, auth_state, status_code)
                self._save(snapshot, next_state)
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
