from __future__ import unicode_literals

import collections
import logging
import time

from mopidy import backend

import spotify

from mopidy_spotify import translator, utils


_API_BASE_URI = 'https://api.spotify.com/v1'

logger = logging.getLogger(__name__)


CachedItem = collections.namedtuple('CachedItem', ['item', 'version', 'expires'])


class ItemCache(object):

    def __init__(self, lifetime):
        self._data = collections.OrderedDict()
        self.expires = 0
        self.lifetime = lifetime

    def get(self, uri, default=None):
        return self._data[uri] if uri in self._data else default

    def update(self, item=None, version=0):
        self.expires = time.time() + self.lifetime
        if item:
            self._data[item.uri] = CachedItem(item, version, self.expires)

    def clear(self):
        self._data.clear()
        self.expires = 0

    def valid(self, uri=None):
        if uri is None:
            expires = self.expires
        elif uri in self._data:
            expires = self._data[uri].expires
        else:
            return False
        return expires > time.time()

    @property
    def items(self):
        for v in self._data.values():
            yield v

    def validate(self, item):
        uri = item.get('uri')
        if uri in self._data:
            if self._data[uri].version != item.get('snapshot_id'):
                del self._data[uri]


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend
        self._ref_cache = ItemCache(60)
        self._full_cache = ItemCache(60*60)

    def as_list(self):
        with utils.time_logger('playlists.as_list()'):
            return list(self._get_flattened_playlist_refs())

    def _get_all_items(self, first_result, params=None):
        if params is None:
            params = {}
        items = first_result['items']
        uri = first_result['next']
        while uri is not None:
            logger.debug("Getting next page")
            next_result = self._backend._web_client.get(uri, params=params)
            #for item in next_result.get('items', []):
                #yield item
            items.extend(next_result['items'])
            uri = next_result.get('next', None)
        return items

    def _get_flattened_playlist_refs(self):
        if self._ref_cache.valid():
            logger.debug("Getting playlist references using cache")
            for p in self._ref_cache.items:
                yield p.item
            return

        logger.debug("Resetting playlist references cache")
        self._ref_cache.clear()
        if self._backend._session is None:
            return

        username = self._backend._session.user_name

        result = self._backend._web_client.get('me/playlists', params={
            'limit': 50 })

        if result is None:
            logger.error("No playlists found") # is this an error condition or normal?
            self._ref_cache.update()
            return

        for web_playlist in self._get_all_items(result):
            self._full_cache.validate(web_playlist)
            playlist_ref = translator.web_to_playlist_ref(
                web_playlist, username=username)
            if playlist_ref is not None:
                self._ref_cache.update(playlist_ref)
                logger.info("Got playlist ref %s %s" % (playlist_ref.name, playlist_ref.uri))
                yield playlist_ref

    def get_items(self, uri):
        with utils.time_logger('playlist.get_items(%s)' % uri):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger('playlists.lookup(%s)' % uri):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False):
        logger.debug("Getting playlist URI %s", uri)
        def gen_fields(name, fields=[]):
            fields = ['uri', 'name'] + fields
            return '%s(%s)' % (name, ','.join(fields))


        fields = ['name', 'owner', 'type', 'uri', 'snapshot_id']
        if as_items:
            fields.append('tracks')

        link = translator.parse_uri(uri)
        web_playlist = self._full_cache.get(uri, None)

        if web_playlist is not None:
            if web_playlist.item.tracks:
                logger.debug('Playlist %s found in cache', uri)
                return web_playlist.item
            else:
                logger.debug('Cached copy for playlist %s without tracks so re-requesting', uri)
                web_playlist = None

        if web_playlist is None:
            if 'tracks' not in fields:
                fields.append('tracks')

            params = {'fields': ','.join(fields), 'market': 'from_token'}
            web_playlist = self._backend._web_client.get(
                'users/%s/playlists/%s' % (link.owner, link.id),
                params=params)

            if web_playlist is not None and 'tracks' in web_playlist:
                web_playlist['tracks'] = [
                    t['track'] for t in
                    self._get_all_items(web_playlist['tracks'])]

        if web_playlist is None:
            logger.debug('Failed to lookup Spotify URI %s', uri)
            return

        username = self._backend._session.user_name
        playlist_ref = translator.web_to_playlist(
            web_playlist, username=username, bitrate=self._backend._bitrate,
            as_items=as_items)

        self._full_cache.update(playlist_ref, version=web_playlist['snapshot_id'])
        return playlist_ref

    def refresh(self):
        self._ref_cache.clear()

    def create(self, name):
        try:
            sp_playlist = (
                self._backend._session.playlist_container
                .add_new_playlist(name))
        except ValueError as exc:
            logger.warning(
                'Failed creating new Spotify playlist "%s": %s', name, exc)
        except spotify.Error:
            logger.warning('Failed creating new Spotify playlist "%s"', name)
        else:
            username = self._backend._session.user_name
            return translator.to_playlist(sp_playlist, username=username)

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO


def on_container_loaded(sp_playlist_container):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug('Spotify playlist container loaded')

    # This event listener is also called after playlists are added, removed and
    # moved, so since Mopidy currently only supports the "playlists_loaded"
    # event this is the only place we need to trigger a Mopidy backend event.
    backend.BackendListener.send('playlists_loaded')


def on_playlist_added(sp_playlist_container, sp_playlist, index):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug(
        'Spotify playlist "%s" added to index %d', sp_playlist.name, index)

    # XXX Should Mopidy support more fine grained playlist events which this
    # event can trigger?


def on_playlist_removed(sp_playlist_container, sp_playlist, index):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug(
        'Spotify playlist "%s" removed from index %d', sp_playlist.name, index)

    # XXX Should Mopidy support more fine grained playlist events which this
    # event can trigger?


def on_playlist_moved(
        sp_playlist_container, sp_playlist, old_index, new_index):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug(
        'Spotify playlist "%s" moved from index %d to %d',
        sp_playlist.name, old_index, new_index)

    # XXX Should Mopidy support more fine grained playlist events which this
    # event can trigger?
