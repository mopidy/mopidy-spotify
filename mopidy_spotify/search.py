import logging
import urllib.parse

from mopidy import models

from mopidy_spotify import lookup, translator

_SEARCH_TYPES = ["album", "artist", "track"]

logger = logging.getLogger(__name__)


def search(
    config,
    web_client,
    query=None,
    uris=None,
    exact=False,
    types=_SEARCH_TYPES,
):
    # TODO Respect `uris` argument

    if query is None:
        logger.debug("Ignored search without query")
        return models.SearchResult(uri="spotify:search")

    if "uri" in query:
        return _search_by_uri(config, web_client, query)

    sp_query = translator.sp_search_query(query, exact)
    if not sp_query:
        logger.debug("Ignored search with empty query")
        return models.SearchResult(uri="spotify:search")

    uri = f"spotify:search:{urllib.parse.quote(sp_query)}"
    logger.info(f"Searching Spotify for: {sp_query}")

    if web_client is None or not web_client.logged_in:
        logger.info("Spotify search aborted: Spotify is offline")
        return models.SearchResult(uri=uri)

    search_count = max(
        config["search_album_count"],
        config["search_artist_count"],
        config["search_track_count"],
    )

    if search_count > 50:
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
            for web_album in result["albums"]["items"][
                : config["search_album_count"]
            ]
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
            for web_track in result["tracks"]["items"][
                : config["search_track_count"]
            ]
        ]
        if "tracks" in result
        else []
    )
    tracks = [x for x in tracks if x]

    return models.SearchResult(
        uri=uri, albums=albums, artists=artists, tracks=tracks
    )


def _search_by_uri(config, web_client, query):
    tracks = []
    for uri in query["uri"]:
        tracks += lookup.lookup(config, web_client, uri)

    uri = "spotify:search"
    if len(query["uri"]) == 1:
        uri = query["uri"][0]

    return models.SearchResult(uri=uri, tracks=tracks)
