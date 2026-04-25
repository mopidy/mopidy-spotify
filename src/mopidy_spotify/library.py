from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast, override

from mopidy import backend

from mopidy_spotify import browse, distinct, images, lookup, search

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mopidy.models import Image, Ref, SearchResult, Track
    from mopidy.types import DistinctField, Query, SearchField, Uri

    from mopidy_spotify.backend import SpotifyBackend
    from mopidy_spotify.types import SpotifyConfig

logger = logging.getLogger(__name__)


class SpotifyLibraryProvider(backend.LibraryProvider):
    root_directory = browse.ROOT_DIR

    def __init__(self, backend: SpotifyBackend) -> None:
        self._backend = backend
        self._config = cast("SpotifyConfig", backend._config["spotify"])

    @override
    def browse(self, uri: Uri) -> list[Ref]:
        return browse.browse(
            config=self._config,
            web_client=self._backend._web_client,
            uri=uri,
        )

    @override
    def get_distinct(
        self,
        field: DistinctField,
        query: Query[SearchField] | None = None,
    ) -> set[str]:
        return distinct.get_distinct(
            self._config,
            self._backend.playlists,
            self._backend._web_client,
            field,
            query,
        )

    @override
    def get_images(self, uris: Iterable[Uri]) -> dict[Uri, list[Image]]:
        return images.get_images(self._backend._web_client, uris)

    @override
    def lookup_many(self, uris: Iterable[Uri]) -> dict[Uri, list[Track]]:
        return lookup.lookup(self._config, self._backend._web_client, uris)

    @override
    def search(
        self,
        query: Query[SearchField],
        uris: Iterable[Uri] | None = None,
        exact: bool = False,
    ) -> SearchResult | None:
        return search.search(
            self._config,
            self._backend._web_client,
            query=query,
            uris=uris,
            exact=exact,
        )
