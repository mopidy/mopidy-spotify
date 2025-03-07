import logging
import threading

from mopidy import backend
from mopidy.core import listener

from mopidy_spotify import translator, utils

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]
        self._refresh_mutex = threading.Lock()

    def as_list(self):
        with utils.time_logger("playlists.as_list()", logging.DEBUG):
            return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self, *, refresh=False):
        if not self._backend._web_client.logged_in:
            return []

        user_playlists = self._backend._web_client.get_user_playlists(refresh=refresh)
        return translator.to_playlist_refs(
            user_playlists, self._backend._web_client.user_id
        )

    def get_items(self, uri):
        with utils.time_logger(f"playlist.get_items({uri!r})", logging.DEBUG):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger(f"playlists.lookup({uri!r})", logging.DEBUG):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, *, as_items=False):
        return playlist_lookup(
            self._backend._web_client,
            uri,
            bitrate=self._backend._bitrate,
            as_items=as_items,
        )

    def refresh(self):
        if not self._backend._web_client.logged_in:
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

    def _refresh_tracks(self, playlist_uris):
        if not self._refresh_mutex.locked():
            logger.error("Lock must be held before calling this method")
            return []
        try:
            with utils.time_logger("playlists._refresh_tracks()", logging.DEBUG):
                refreshed = [uri for uri in playlist_uris if self.lookup(uri)]
                logger.info(f"Refreshed {len(refreshed)} Spotify playlists")

            listener.CoreListener.send("playlists_loaded")
        except Exception:
            logger.exception("Error occurred while refreshing Spotify playlists tracks")
        else:
            return refreshed  # For test
        finally:
            self._refresh_mutex.release()

    def create(self, name):
        pass  # TODO: Implement

    def delete(self, uri):
        pass  # TODO: Implement

    def save(self, playlist):
        pass  # TODO: Implement


def playlist_lookup(
    web_client,
    uri,
    *,
    bitrate,
    as_items=False,
):
    if web_client is None or not web_client.logged_in:
        return None

    logger.debug(f'Fetching Spotify playlist "{uri!r}"')
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
