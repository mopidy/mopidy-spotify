from __future__ import unicode_literals

import logging
import re

from mopidy import backend

from mopidy_spotify import translator, utils


logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config['spotify']['timeout']

    def as_list(self):
        with utils.time_logger('playlists.as_list()'):
            username = self._backend._session.user_name
            web_playlists = self._backend._web_client.get(
                'users/' + username + '/playlists', params={})

            if not web_playlists:
                return []

            return [
                translator.web_to_playlist_ref(web_playlist, username=username)
                for web_playlist in web_playlists['items']]

    def get_items(self, uri):
        with utils.time_logger('playlist.get_items(%s)' % uri):
            web_tracks = self._backend._web_client.get(
                'users/' + self._user_from_uri(uri) + '/playlists/'
                + self._playlist_from_uri(uri) + '/tracks', params={})

            if not web_tracks:
                return None

            return [translator.web_to_track_ref(web_track)
                    for web_track in web_tracks['items']]

    def lookup(self, uri):
        with utils.time_logger('playlists.lookup(%s)' % uri):
            username = self._backend._session.user_name
            web_playlist = self._backend._web_client.get(
                'users/' + self._user_from_uri(uri) + '/playlists/'
                + self._playlist_from_uri(uri), params={})

            if not web_playlist:
                return None

            return translator.web_to_playlist(web_playlist, username=username)

    def refresh(self):
        pass  # Not needed as long as we don't cache anything.

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO

    def _user_from_uri(self, uri):
        m = re.search('user:(.*?):', uri)
        return m.group(1) if m else ''

    def _playlist_from_uri(self, uri):
        m = re.search('playlist:(.*)$', uri)
        return m.group(1) if m else ''
