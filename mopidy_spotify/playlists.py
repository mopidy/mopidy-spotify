from __future__ import unicode_literals

import copy

from mopidy import backend


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        super(SpotifyPlaylistsProvider, self).__init__(backend)
        self._playlists = []

    @property
    def playlists(self):
        return copy.copy(self._playlists)

    @playlists.setter
    def playlists(self, playlists):
        self._playlists = playlists

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def lookup(self, uri):
        for playlist in self._playlists:
            if playlist.uri == uri:
                return playlist

    def refresh(self):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO
