from __future__ import unicode_literals

from mopidy import backend


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
        return []  # TODO

    def refresh(self):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO
