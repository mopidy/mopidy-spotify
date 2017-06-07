from __future__ import unicode_literals

import logging

from mopidy import backend

from mopidy_spotify import browse, distinct, images, lookup, search


logger = logging.getLogger(__name__)


class SpotifyLibraryProvider(backend.LibraryProvider):
    root_directory = browse.ROOT_DIR

    def __init__(self, backend):
        self._backend = backend
        self._config = backend._config['spotify']

    def browse(self, uri):
        return browse.browse(self._config, self._backend._session, uri)

    def get_distinct(self, field, query=None):
        return distinct.get_distinct(
            self._config, self._backend._session, self._backend._web_client,
            field, query)

    def get_images(self, uris):
        return images.get_images(self._backend._web_client, uris)

    def lookup(self, uri):
        return lookup.lookup(self._config, self._backend._session, uri)

    def search(self, query=None, uris=None, exact=False):
        return search.search(
            self._config, self._backend._session, self._backend._web_client,
            query, uris, exact)
