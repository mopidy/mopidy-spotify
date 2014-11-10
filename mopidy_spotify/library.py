from __future__ import unicode_literals

from mopidy import backend


class SpotifyLibraryProvider(backend.LibraryProvider):

    def __init__(self, backend):
        self._backend = backend

