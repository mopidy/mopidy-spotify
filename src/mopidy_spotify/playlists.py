from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Literal, overload, override

from mopidy import backend
from mopidy.core import CoreListener

from mopidy_spotify import translator, utils

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mopidy.models import Playlist, Ref
    from mopidy.types import Uri

    from mopidy_spotify.backend import SpotifyBackend
    from mopidy_spotify.web import SpotifyOAuthClient

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    def __init__(self, backend: SpotifyBackend) -> None:
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]
        self._refresh_mutex = threading.Lock()

    @override
    def as_list(self) -> list[Ref]:
        with utils.time_logger("playlists.as_list()", logging.DEBUG):
            return self._get_flattened_playlist_refs()

    def _get_flattened_playlist_refs(
        self,
        *,
        refresh: bool = False,
    ) -> list[Ref]:
        web_client = self._backend._web_client
        if web_client is None or not web_client.logged_in:
            return []

        user_playlists = web_client.get_user_playlists(refresh=refresh)
        return list(translator.to_playlist_refs(user_playlists, web_client.user_id))

    @override
    def get_items(self, uri: Uri) -> list[Ref] | None:
        if self._backend._web_client is None:
            return None
        with utils.time_logger(f"playlist.get_items({uri!r})", logging.DEBUG):
            return playlist_lookup(
                self._backend._web_client,
                uri,
                bitrate=self._backend._bitrate,
                as_items=True,
            )

    @override
    def lookup(self, uri: Uri) -> Playlist | None:
        if self._backend._web_client is None:
            return None
        with utils.time_logger(f"playlists.lookup({uri!r})", logging.DEBUG):
            return playlist_lookup(
                self._backend._web_client,
                uri,
                bitrate=self._backend._bitrate,
                as_items=False,
            )

    @override
    def refresh(self) -> None:
        if self._backend._web_client is None or not self._backend._web_client.logged_in:
            return
        if not self._refresh_mutex.acquire(blocking=False):
            logger.info("Refreshing Spotify playlists already in progress")
            return
        try:
            uris = [ref.uri for ref in self._get_flattened_playlist_refs(refresh=True)]
            logger.info(f"Refreshing {len(uris)} Spotify playlists in background")
            threading.Thread(
                target=self._refresh_tracks,
                args=(uris,),
                daemon=True,
            ).start()
        except Exception:
            logger.exception("Error occurred while refreshing Spotify playlists")
            self._refresh_mutex.release()

    def _refresh_tracks(self, playlist_uris: Iterable[Uri]) -> list[Uri]:
        if not self._refresh_mutex.locked():
            logger.error("Lock must be held before calling this method")
            return []
        try:
            with utils.time_logger("playlists._refresh_tracks()", logging.DEBUG):
                refreshed = [uri for uri in playlist_uris if self.lookup(uri)]
                logger.info(f"Refreshed {len(refreshed)} Spotify playlists")

            CoreListener.send("playlists_loaded")
        except Exception:
            logger.exception("Error occurred while refreshing Spotify playlists tracks")
            return []
        else:
            return refreshed  # For test
        finally:
            self._refresh_mutex.release()

    @override
    def create(self, name: str) -> Playlist | None:
        pass  # TODO: Implement

    @override
    def delete(self, uri: Uri) -> bool:
        return False  # TODO: Implement

    @override
    def save(self, playlist: Playlist) -> Playlist | None:
        pass  # TODO: Implement


@overload
def playlist_lookup(
    web_client: SpotifyOAuthClient,
    uri: Uri,
    *,
    bitrate: int | None,
    as_items: Literal[True],
) -> list[Ref] | None: ...


@overload
def playlist_lookup(
    web_client: SpotifyOAuthClient,
    uri: Uri,
    *,
    bitrate: int | None,
    as_items: Literal[False] = False,
) -> Playlist | None: ...


def playlist_lookup(
    web_client: SpotifyOAuthClient,
    uri: Uri,
    *,
    bitrate: int | None,
    as_items: bool = False,
) -> Playlist | list[Ref] | None:
    if not web_client.logged_in:
        return None

    logger.debug(f"Fetching Spotify playlist {uri!r}")
    web_playlist = web_client.get_playlist(uri)

    if not web_playlist:
        logger.error(f"Failed to lookup Spotify playlist URI {uri!r}")
        return None

    playlist = translator.to_playlist(
        web_playlist,
        username=web_client.user_id,
        bitrate=bitrate,
        as_items=as_items,
    )
    # TODO: cache the Mopidy tracks? And handle as_items here instead of translator
    if playlist is None:
        return None

    return playlist
