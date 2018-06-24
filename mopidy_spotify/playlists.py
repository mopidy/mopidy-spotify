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
        self._as_list_cache = []
        self._lookup_cache = {}
        self._get_items_cache = {}

    def as_list(self):
        with utils.time_logger('playlists.as_list()'):
            return self._as_list()

    def get_items(self, uri):
        with utils.time_logger('playlist.get_items(%s)' % uri):
            return self._get_items(uri)

    def lookup(self, uri):
        with utils.time_logger('playlists.lookup(%s)' % uri):
            return self._lookup(uri)

    def refresh(self):
        self._as_list_cache = []
        self._lookup_cache = {}
        self._get_items_cache = {}

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO

    def _as_list(self):
        if not self._as_list_cache:
            username = self._backend._session.user_name
            web_playlists = self._get_playlists()

            if not web_playlists:
                return []

            self._as_list_cache = [
                translator.web_to_playlist_ref(web_playlist, username=username)
                for web_playlist in web_playlists]

        return self._as_list_cache

    def _get_items(self, uri):
        if uri not in self._get_items_cache:
            web_tracks = self._get_tracks(uri, refs=True)

            if not web_tracks:
                return None

            self._get_items_cache[uri] = [
                translator.web_to_track_ref(web_track)
                for web_track in web_tracks]

        return self._get_items_cache[uri]

    def _lookup(self, uri):
        if uri not in self._lookup_cache:
            username = self._backend._session.user_name

            web_playlist = self._get_playlist(uri)

            if not web_playlist:
                return None

            web_tracks = self._get_tracks(uri)

            self._lookup_cache[uri] = translator.web_to_playlist(
                web_playlist, username=username, web_tracks=web_tracks)

        return self._lookup_cache[uri]

    def _get_playlist(self, uri):
        user_id = self._user_from_uri(uri)
        playlist_id = self._playlist_from_uri(uri)
        fields = "name,uri,owner(id,display_name)".replace(',', '%2C')

        return self._backend._web_client.get(
            'users/' + user_id + '/playlists/' + playlist_id,
            params={"fields": fields})

    def _get_playlists(self):
        username = self._backend._session.user_name
        fields = "name,uri,owner(id,display_name)".replace(',', '%2C')

        web_playlists = self._api_get_items(
            'users/' + username + '/playlists', params={"fields": fields})

        return web_playlists

    def _get_tracks(self, uri, refs=False):
        user_id = self._user_from_uri(uri)
        playlist_id = self._playlist_from_uri(uri)
        fields = "uri,name"
        if not refs:
            fields += ",artists,album"
        fields = fields.replace(',', '%2C')

        web_tracks = self._api_get_items(
            'users/' + user_id + '/playlists/' + playlist_id + '/tracks',
            params={"fields": fields})

        return web_tracks

    def _api_get_items(self, url, params={}):
        items = []

        while True:
            result = self._backend._web_client.get(url, params=params)
            if 'items' in result:
                items += result['items']

            if 'next' in result and result['next']:
                params['offset'] = result['limit'] + result['offset']
            else:
                break

        return items

    def _user_from_uri(self, uri):
        m = re.search('user:(.*?):', uri)
        return m.group(1) if m else ''

    def _playlist_from_uri(self, uri):
        m = re.search('playlist:(.*)$', uri)
        return m.group(1) if m else ''
