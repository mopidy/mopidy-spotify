import logging

from mopidy import backend

from mopidy_spotify import translator, utils

_cache = {}

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]
        self._loaded = False

    def as_list(self):
        with utils.time_logger("playlists.as_list()", logging.INFO):
            if not self._loaded:
                return []

            return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self):
        if self._backend._web_client is None:
            return

        if self._backend._web_client.user_id is None:
            return

        web_client = self._backend._web_client
        for web_playlist in web_client.get_user_playlists(_cache):
            playlist_ref = translator.to_playlist_ref(
                web_playlist, web_client.user_id
            )
            if playlist_ref is not None:
                yield playlist_ref

    def get_items(self, uri):
        with utils.time_logger(f"playlist.get_items({uri})", logging.INFO):
            if not self._loaded:
                return []

            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger(f"playlists.lookup({uri})", logging.DEBUG):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False):
        return playlist_lookup(
            self._backend._web_client, uri, self._backend._bitrate, as_items
        )

    def refresh(self):
        with utils.time_logger("Refresh Playlists", logging.INFO):
            _cache.clear()
            count = 0
            for playlist_ref in self._get_flattened_playlist_refs():
                self._get_playlist(playlist_ref.uri)
                count = count + 1
            logger.info(f"Refreshed {count} playlists")

        self._loaded = True

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO


def playlist_lookup(web_client, uri, bitrate, as_items=False):
    if web_client is None:
        return

    logger.debug(f'Fetching Spotify playlist "{uri}"')
    web_playlist = web_client.get_playlist(uri, _cache)

    if web_playlist == {}:
        logger.error(f"Failed to lookup Spotify playlist URI {uri}")
        return

    return translator.to_playlist(
        web_playlist,
        username=web_client.user_id,
        bitrate=bitrate,
        as_items=as_items,
    )


def on_playlists_loaded():
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug("Spotify playlists loaded")

    # This event listener is also called after playlists are added, removed and
    # moved, so since Mopidy currently only supports the "playlists_loaded"
    # event this is the only place we need to trigger a Mopidy backend event.
    backend.BackendListener.send("playlists_loaded")
