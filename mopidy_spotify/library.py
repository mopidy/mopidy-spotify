from __future__ import unicode_literals

import logging
import urllib

from mopidy import backend, models

import spotify
from mopidy_spotify import browse, distinct, images, lookup, translator, utils


logger = logging.getLogger(__name__)


class SpotifyLibraryProvider(backend.LibraryProvider):
    root_directory = browse.ROOT_DIR

    def __init__(self, backend):
        self._backend = backend
        self._config = self._backend._config['spotify']

    def browse(self, uri):
        return browse.browse(self._config, self._backend._session, uri)

    def get_distinct(self, field, query=None):
        return distinct.get_distinct(
            self._config, self._backend._session, field, query)

    def get_images(self, uris):
        return images.get_images(uris)

    def lookup(self, uri):
        return lookup.lookup(self._config, self._backend._session, uri)

    def search(self, query=None, uris=None, exact=False):
        # TODO Respect `uris` argument
        # TODO Support `exact` search

        if query is None:
            logger.debug('Ignored search without query')
            return models.SearchResult(uri='spotify:search')

        if 'uri' in query:
            return self._search_by_uri(query)

        sp_query = translator.sp_search_query(query)
        if not sp_query:
            logger.debug('Ignored search with empty query')
            return models.SearchResult(uri='spotify:search')

        uri = 'spotify:search:%s' % urllib.quote(sp_query.encode('utf-8'))
        logger.info('Searching Spotify for: %s', sp_query)

        if not self._backend._online.is_set():
            logger.info('Spotify search aborted: Spotify is offline')
            return models.SearchResult(uri=uri)

        sp_search = self._backend._session.search(
            sp_query,
            album_count=self._config['search_album_count'],
            artist_count=self._config['search_artist_count'],
            track_count=self._config['search_track_count'])
        sp_search.load()

        albums = [
            translator.to_album(sp_album) for sp_album in sp_search.albums]
        artists = [
            translator.to_artist(sp_artist) for sp_artist in sp_search.artists]
        tracks = [
            translator.to_track(sp_track) for sp_track in sp_search.tracks]

        return models.SearchResult(
            uri=uri, albums=albums, artists=artists, tracks=tracks)

    def _search_by_uri(self, query):
        tracks = []
        for uri in query['uri']:
            tracks += self.lookup(uri)

        uri = 'spotify:search'
        if len(query['uri']) == 1:
            uri = query['uri'][0]

        return models.SearchResult(uri=uri, tracks=tracks)
