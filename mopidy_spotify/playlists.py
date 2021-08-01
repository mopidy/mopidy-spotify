import logging
import threading

from mopidy import backend
from mopidy.core import listener

import spotify
from mopidy_spotify import translator, utils

_sp_links = {}

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]
        self._loaded = False

        self._refreshing = False

    def as_list(self):
        with utils.time_logger("playlists.as_list()", logging.DEBUG):
            if not self._loaded:
                return []

            return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self):
        if not self._backend._web_client.logged_in:
            return []

        user_playlists = self._backend._web_client.get_user_playlists()
        return translator.to_playlist_refs(
            user_playlists, self._backend._web_client.user_id
        )

    def get_items(self, uri):
        with utils.time_logger(f"playlist.get_items({uri!r})", logging.DEBUG):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger(f"playlists.lookup({uri!r})", logging.DEBUG):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False):
        return playlist_lookup(
            self._backend._session,
            self._backend._web_client,
            uri,
            self._backend._bitrate,
            as_items,
        )

    def refresh(self):
        if not self._backend._web_client.logged_in:
            return
        elif self._refreshing:
            return

        self._refreshing = True

        logger.info("Refreshing Spotify playlists")

        def refresher():
            try:
                with utils.time_logger("playlists.refresh()", logging.DEBUG):
                    _sp_links.clear()
                    self._backend._web_client.clear_cache()
                    count = 0
                    for playlist_ref in self._get_flattened_playlist_refs():
                        self._get_playlist(playlist_ref.uri)
                        count += 1
                    logger.info(f"Refreshed {count} Spotify playlists")

                listener.CoreListener.send("playlists_loaded")
                self._loaded = True
            except Exception as e:
                logger.exception(
                    f"An error occurred while refreshing Spotify playlists: {e}"
                )
            finally:
                self._refreshing = False

        thread = threading.Thread(target=refresher)
        thread.daemon = True
        thread.start()

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO


def playlist_lookup(session, web_client, uri, bitrate, as_items=False):
    if web_client is None or not web_client.logged_in:
        return

    logger.debug(f'Fetching Spotify playlist "{uri!r}"')
    web_playlist = web_client.get_playlist(uri)

    if web_playlist == {}:
        logger.error(f"Failed to lookup Spotify playlist URI {uri!r}")
        return

    playlist = translator.to_playlist(
        web_playlist,
        username=web_client.user_id,
        bitrate=bitrate,
        as_items=as_items,
    )
    if playlist is None:
        return
    # Store the libspotify Link for each track so they will be loaded in the
    # background ready for using later.
    if session.connection.state is spotify.ConnectionState.LOGGED_IN:
        if as_items:
            tracks = playlist
        else:
            tracks = playlist.tracks

        for track in tracks:
            if track.uri in _sp_links:
                continue
            try:
                _sp_links[track.uri] = session.get_link(track.uri)
            except ValueError as exc:
                logger.info(f"Failed to get link {track.uri!r}: {exc}")

    return playlist
