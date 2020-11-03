import logging

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
    def _get_user_and_playlist_id_from_uri(uri):
        user_id = uri.split(':')[-3]
        playlist_id = uri.split(':')[-1]
        return user_id, playlist_id

    @staticmethod
    def partitions(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i+n]

    def _playlist_edit(self, playlist, method, **kwargs):
        user_id, playlist_id = self._get_user_and_playlist_id_from_uri(playlist.uri)
        url = f'users/{user_id}/playlists/{playlist_id}/tracks'
        method = getattr(self._backend._web_client, method.lower())
        if not method:
            raise AttributeError(f'Invalid HTTP method "{method}"')

        logger.debug(f'API request: {method} {url}')
        response = method(url, json=kwargs)

        logger.debug(f'API response: {response}')

        # TODO invalidating the whole cache is probably a bit much if we have
        # updated only one playlist - maybe we should expose an API to clear
        # cache items by key?
        self._backend._web_client.clear_cache()
        return self.lookup(playlist.uri)

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
        url = f'users/{web_client.user_id}/playlists'
        response = self._backend._web_client.post(url, json={'name': name})
        self.refresh()
        return self.lookup(response['uri'])

    def delete(self, uri):
        playlist_id = uri.split(':')[-1]
        logger.info(f'Deleting playlist {playlist_id}')
        url = f'playlists/{playlist_id}/followers'
        response = self._backend._web_client.delete(url)
        self.refresh()
        return response.status_ok

    def save(self, playlist):
        # Note that for sake of simplicity the diff calculation between the
        # old and new playlist won't take duplicate items into account
        # (i.e. tracks that occur multiple times in the same playlist)
        saved_playlist = self.lookup(playlist.uri)
        if not saved_playlist:
            return

        new_tracks = {track.uri: track for track in playlist.tracks}
        cur_tracks = {track.uri: track for track in saved_playlist.tracks}
        removed_uris = set(cur_tracks.keys()).difference(set(new_tracks.keys()))

        # Remove tracks logic
        if removed_uris:
            logger.info(f'Removing {len(removed_uris)} tracks from playlist ' +
                    f'{saved_playlist.name}: {removed_uris}')

            for chunk in self.partitions(removed_uris, self._chunk_size):
                saved_playlist = self._playlist_edit(saved_playlist, method='delete',
                        tracks=[{'uri': uri for uri in removed_uris}])
                cur_tracks = {track.uri: track for track in saved_playlist.tracks}

        # Add tracks logic
        position = None
        added_uris = {}

        for i, track in enumerate(playlist.tracks):
            if track.uri not in cur_tracks:
                if position is None:
                    position = i
                    added_uris[position] = []
                added_uris[position].append(track.uri)
            else:
                position = None

        if added_uris:
            for pos, uris in added_uris.items():
                logger.info(f'Adding {uris} to playlist {saved_playlist.name}')
                processed_tracks = 0

                for chunk in self.partitions(uris):
                    saved_playlist = self._playlist_edit(saved_playlist, method='post',
                            uris=chunk, position=pos+processed_tracks)

                    cur_tracks = {track.uri: track for track in saved_playlist.tracks}
                    processed_tracks += len(chunk)

        # Swap tracks logic
        cur_tracks_by_uri = {}

        for i, track in enumerate(playlist.tracks):
            if i >= len(saved_playlist.tracks):
                break

            if track.uri != saved_playlist.tracks[i].uri:
                cur_tracks_by_uri[saved_playlist.tracks[i].uri] = i

                if track.uri in cur_tracks_by_uri:
                    cur_pos = cur_tracks_by_uri[track.uri]
                    new_pos = i+1
                    logger.info(f'Moving item position [{cur_pos}] to [{new_pos}] in ' +
                            f'playlist {saved_playlist.name}')

                    cur_tracks = {
                        track.uri: track
                        for track in self._playlist_edit(
                            saved_playlist, method='put',
                            range_start=cur_pos, insert_before=new_pos).tracks
                        }

        # Playlist rename logic
        if playlist.name != saved_playlist.name:
            logger.info(f'Renaming playlist [{saved_playlist.name}] to [{playlist.name}]')
            user_id, playlist_id = self._get_user_and_playlist_id_from_uri(saved_playlist.uri)
            self._backend._web_client.put(f'users/{user_id}/playlists/{playlist_id}',
                    json={'name': playlist.name})

        self._backend._web_client.clear_cache()
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
