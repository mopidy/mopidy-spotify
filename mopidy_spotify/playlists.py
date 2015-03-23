from __future__ import unicode_literals

import operator

from mopidy import backend
from mopidy.models import Ref


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        super(SpotifyPlaylistsProvider, self).__init__(backend)
        self.playlists_map = {}

    def as_list(self):
        refs = [
            Ref.playlist(uri=pl.uri, name=pl.name)
            for pl in self.playlists_map.values()]
        return sorted(refs, key=operator.attrgetter('name'))

    def get_items(self, uri):
        playlist = self.playlists_map.get(uri)
        if playlist is None:
            return None
        return [Ref.track(uri=t.uri, name=t.name) for t in playlist.tracks]

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def lookup(self, uri):
        return self.playlists_map.get(uri)

    def refresh(self):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO
