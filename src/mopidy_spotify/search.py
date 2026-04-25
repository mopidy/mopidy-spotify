from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING

from mopidy.models import SearchResult
from mopidy.types import Uri

from mopidy_spotify import lookup, translator

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mopidy.types import Query, SearchField

    from mopidy_spotify.types import SpotifyConfig
    from mopidy_spotify.web import SpotifyOAuthClient

_SEARCH_TYPES = ["album", "artist", "track"]

logger = logging.getLogger(__name__)


def search(  # noqa: PLR0913
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    *,
    query: Query[SearchField] | None = None,
    uris: Iterable[Uri] | None = None,  # noqa: ARG001
    exact: bool = False,
    types: list[str] = _SEARCH_TYPES,
) -> SearchResult:
    # TODO: Respect `uris` argument

    if not query:
        logger.debug("Ignored search without query")
        return SearchResult(uri=Uri("spotify:search"))

    if "uri" in query:
        return _search_by_uri(config, web_client, query)

    sp_query = translator.sp_search_query(query, exact=exact)
    if not sp_query:
        logger.debug("Ignored search with empty query")
        return SearchResult(uri=Uri("spotify:search"))

    uri = Uri(f"spotify:search:{urllib.parse.quote(sp_query)}")
    logger.info(f"Searching Spotify for: {sp_query}")

    if not web_client.logged_in:
        logger.info("Spotify search aborted: Spotify is offline")
        return SearchResult(uri=uri)

    search_count = max(
        config["search_album_count"],
        config["search_artist_count"],
        config["search_track_count"],
    )

    if search_count > 50:  # noqa: PLR2004
        logger.warning(
            "Spotify currently allows maximum 50 search results of each type. "
            "Please set the config values spotify/search_album_count, "
            "spotify/search_artist_count and spotify/search_track_count "
            "to at most 50."
        )
        search_count = 50

    result = web_client.get(
        "search",
        params={
            "q": sp_query,
            "limit": search_count,
            "market": "from_token",
            "type": ",".join(types),
        },
    )

    albums = (
        [
            translator.web_to_album(web_album)
            for web_album in result["albums"]["items"][: config["search_album_count"]]
        ]
        if "albums" in result
        else []
    )
    albums = [x for x in albums if x]

    artists = (
        [
            translator.web_to_artist(web_artist)
            for web_artist in result["artists"]["items"][
                : config["search_artist_count"]
            ]
        ]
        if "artists" in result
        else []
    )
    artists = [x for x in artists if x]

    tracks = (
        [
            translator.web_to_track(web_track)
            for web_track in result["tracks"]["items"][: config["search_track_count"]]
        ]
        if "tracks" in result
        else []
    )
    tracks = [x for x in tracks if x]

    return SearchResult(
        uri=uri,
        albums=tuple(albums),
        artists=tuple(artists),
        tracks=tuple(tracks),
    )


def _search_by_uri(
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    query: Query[SearchField],
) -> SearchResult:
    uris = [Uri(uri) for uri in query["uri"] if isinstance(uri, str)]
    results = lookup.lookup(config, web_client, uris)
    tracks = []
    for uri in uris:
        tracks += results.get(uri, [])

    result_uri = uris[0] if len(uris) == 1 else Uri("spotify:search")

    return SearchResult(
        uri=result_uri,
        tracks=tuple(tracks),
    )
