from __future__ import unicode_literals

import logging

from mopidy import backend, models

import spotify

from mopidy_spotify import translator


logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def lookup(self, uri):
        pass  # TODO

    @property
    def playlists(self):
        # XXX We should just return light-weight Ref objects here, but Mopidy's
        # core and backend APIs must be changed first.

        if self._backend._session.playlist_container is None:
            return []

        result = []
        folder = []

        for sp_playlist in self._backend._session.playlist_container:
            if isinstance(sp_playlist, spotify.PlaylistFolder):
                if sp_playlist.type is spotify.PlaylistType.START_FOLDER:
                    folder.append(sp_playlist.name)
                elif sp_playlist.type is spotify.PlaylistType.END_FOLDER:
                    folder.pop()
                continue

            if not sp_playlist.is_loaded:
                continue

            name = '/'.join(folder + [sp_playlist.name])
            # TODO Add "by <playlist owner>" to name

            tracks = [
                translator.to_track(sp_track)
                for sp_track in sp_playlist.tracks
            ]
            tracks = filter(None, tracks)

            playlist = models.Playlist(
                uri=sp_playlist.link.uri,
                name=name,
                tracks=tracks)
            result.append(playlist)

        # TODO Add starred playlist

        return result

    def refresh(self):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO
