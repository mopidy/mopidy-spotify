import logging
import math

from mopidy import backend

import spotify
from mopidy_spotify import translator, utils

_sp_links = {}

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    # Maximum number of items accepted by the Spotify Web API
    _chunk_size = 100

    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]
        self._loaded = False

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

    @staticmethod
    def _get_playlist_id_from_uri(uri):
        return uri.split(':')[-1]

    @staticmethod
    def partitions(lst, n=_chunk_size):
        for i in range(0, len(lst), n):
            yield lst[i:i+n]

    @staticmethod
    def _span(p, l):  # like haskell's Data.List.span
        i = next((i for i,v in enumerate(l) if not p(v)), len(l))
        return l[:i], l[i:]

    def _patch_playlist(self, playlist, operations):
        delta_f = 0
        delta_t = 0
        unwind_f = []
        unwind_t = []
        for op in operations:
            ##
            ended_ranges_f, unwind_f = self._span(lambda e: e[0] < op.frm, unwind_f)
            ended_ranges_t, unwind_t = self._span(lambda e: e[0] < op.to, unwind_t)
            delta_f -= sum((v for k,v in ended_ranges_f))
            delta_t -= sum((v for k,v in ended_ranges_t))
            ##
            l = len(op.tracks)
            if op.op == '-':
                self._playlist_edit(playlist, method='delete',
                    tracks=[
                        {'uri': t, 'positions': [op.frm+i+delta_f]}
                        for i,t in enumerate(op.tracks)
                    ]
                )
                delta_f -= l
                delta_t -= l
            elif op.op == '+':
                self._playlist_edit(playlist, method='post',
                    uris=op.tracks, position=op.frm+delta_f
                )
                delta_f += l
                delta_t += l
            elif op.op == 'm':
                self._playlist_edit(playlist, method='put',
                    range_start=op.frm+delta_f, insert_before=op.to+delta_t,
                    range_length=l
                )
                # if we move right, the delta is active in the range (op.frm, op.to); if we move left, it's in the range (op.to, op.frm+l)
                position = op.to if op.frm < op.to else op.frm+l
                amount = l * (-1 if op.frm < op.to else 1)
                unwind_f.append((position, amount))
                unwind_t.append((position, amount))
                delta_f += amount
                delta_t += amount

    def _replace_playlist(self, playlist, tracks):
        for i, uris in enumerate(self.partitions(tracks)):
            # on the first chunk (i.e. when i == 0), we use PUT to replace the
            # playlist, on the following chunks we use POST to append to it.
            method = 'post' if i else 'put'
            self._playlist_edit(playlist, method=method, uris=uris)

    def _playlist_edit(self, playlist, method, **kwargs):
        playlist_id = self._get_playlist_id_from_uri(playlist.uri)
        url = f'playlists/{playlist_id}/tracks'
        method = getattr(self._backend._web_client, method.lower())
        if not method:
            raise AttributeError(f'Invalid HTTP method "{method}"')

        logger.debug(f'API request: {method} {url}')
        response = method(url, json=kwargs)
        if not response.status_ok:
            raise RuntimeError(response)

        logger.debug(f'API response: {response}')

        self._backend._web_client.remove_from_cache(url)
        self._backend._web_client.remove_from_cache(f'playlists/{playlist_id}') # this also fetches the first 100 tracks

    def refresh(self):
        if not self._backend._web_client.logged_in:
            return

        with utils.time_logger("playlists.refresh()", logging.DEBUG):
            _sp_links.clear()
            self._backend._web_client.clear_cache()
            count = 0
            for playlist_ref in self._get_flattened_playlist_refs():
                self._get_playlist(playlist_ref.uri)
                count = count + 1
            logger.info(f"Refreshed {count} Spotify playlists")

        self._loaded = True

    def create(self, name):
        logger.info(f'Creating playlist {name}')
        url = f'users/{self._backend._web_client.user_id}/playlists'
        response = self._backend._web_client.post(url, json={'name': name, 'public': False})
        self._backend._web_client.remove_from_cache("me/playlists")
        self._get_flattened_playlist_refs()
        return self.lookup(response['uri'])if response.status_ok else None

    def delete(self, uri):
        playlist_id = uri.split(':')[-1]
        logger.info(f'Deleting playlist {playlist_id}')
        url = f'playlists/{playlist_id}/followers'
        response = self._backend._web_client.delete(url)
        self._backend._web_client.remove_from_cache("me/playlists")
        self._get_flattened_playlist_refs()
        return response.status_ok

    @staticmethod
    def _len_replace(playlist, n=_chunk_size):
        return math.ceil(len(playlist.tracks) / n)

    def save(self, playlist):
        saved_playlist = self.lookup(playlist.uri)
        if not saved_playlist:
            return

        new_tracks = [track.uri for track in playlist.tracks]
        cur_tracks = [track.uri for track in saved_playlist.tracks]

        operations = utils.diff(cur_tracks, new_tracks, self._chunk_size)

        # calculate number of operations required for each strategy:
        ops_patch   = len(operations)
        ops_replace = self._len_replace(playlist)

        try:
            if ops_replace < ops_patch:
                self._replace_playlist(saved_playlist, new_tracks)
            else:
                self._patch_playlist(saved_playlist, operations)
        except RuntimeError as e:
            logger.error(f"Failed to save Spotify playlist {saved_playlist} -> {playlist}")
            # todo: worst case: we might have started overwriting the playlist, and are now truncated.
            raise e.message

        # Playlist rename logic
        if playlist.name != saved_playlist.name:
            logger.info(f'Renaming playlist [{saved_playlist.name}] to [{playlist.name}]')
            playlist_id = self._get_playlist_id_from_uri(saved_playlist.uri)
            self._backend._web_client.put(f'playlists/{playlist_id}',
                    json={'name': playlist.name})
            self._backend._web_client.remove_from_cache("me/playlists")
            self._backend._web_client.remove_from_cache(f'playlists/{playlist_id}')

        return self.lookup(saved_playlist.uri)


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
