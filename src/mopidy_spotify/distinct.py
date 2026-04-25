from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from mopidy_spotify import search

if TYPE_CHECKING:
    from collections.abc import Generator

    from mopidy.models import SearchResult, Track
    from mopidy.types import DistinctField, Query, SearchField

    from mopidy_spotify.playlists import SpotifyPlaylistsProvider
    from mopidy_spotify.types import SpotifyConfig
    from mopidy_spotify.web import SpotifyOAuthClient

logger = logging.getLogger(__name__)


def get_distinct(
    config: SpotifyConfig,
    playlists: SpotifyPlaylistsProvider,
    web_client: SpotifyOAuthClient,
    field: DistinctField,
    query: Query[SearchField] | None = None,
) -> set[str]:
    # To make the returned data as interesting as possible, we limit
    # ourselves to data extracted from the user's playlists when no search
    # query is included.
    # TODO: Perhaps should use tracks from My Music instead?
    if not web_client.logged_in:
        return set()

    match field:
        case "artist":
            result = _get_distinct_artists(config, playlists, web_client, query)
        case "albumartist":
            result = _get_distinct_albumartists(config, playlists, web_client, query)
        case "album":
            result = _get_distinct_albums(config, playlists, web_client, query)
        case "date":
            result = _get_distinct_dates(config, playlists, web_client, query)
        case _:
            result = set()

    return {x for x in result if isinstance(x, str)}


def _get_distinct_artists(
    config: SpotifyConfig,
    playlists: SpotifyPlaylistsProvider,
    web_client: SpotifyOAuthClient,
    query: Query[SearchField] | None,
) -> set[str]:
    logger.debug(f"Getting distinct artists: {query}")

    if query:
        search_result = _get_search(config, web_client, query, artist=True)
        return {
            artist.name for artist in search_result.artists if artist.name is not None
        }

    return {
        artist.name
        for track in _get_playlist_tracks(config, playlists, web_client)
        for artist in track.artists
        if artist.name is not None
    }


def _get_distinct_albumartists(
    config: SpotifyConfig,
    playlists: SpotifyPlaylistsProvider,
    web_client: SpotifyOAuthClient,
    query: Query[SearchField] | None,
) -> set[str]:
    logger.debug(f"Getting distinct albumartists: {query}")

    if query:
        search_result = _get_search(config, web_client, query, album=True)
        return {
            artist.name
            for album in search_result.albums
            for artist in album.artists
            if artist.name is not None
        }

    return {
        artist.name
        for track in _get_playlist_tracks(config, playlists, web_client)
        if track.album and track.album.artists
        for artist in track.album.artists
        if artist.name is not None
    }


def _get_distinct_albums(
    config: SpotifyConfig,
    playlists: SpotifyPlaylistsProvider,
    web_client: SpotifyOAuthClient,
    query: Query[SearchField] | None,
) -> set[str]:
    logger.debug(f"Getting distinct albums: {query}")

    if query:
        search_result = _get_search(config, web_client, query, album=True)
        return {album.name for album in search_result.albums if album.name is not None}

    return {
        track.album.name
        for track in _get_playlist_tracks(config, playlists, web_client)
        if track.album and track.album.name is not None
    }


def _get_distinct_dates(
    config: SpotifyConfig,
    playlists: SpotifyPlaylistsProvider,
    web_client: SpotifyOAuthClient,
    query: Query[SearchField] | None,
) -> set[str]:
    logger.debug(f"Getting distinct album years: {query}")

    if query:
        search_result = _get_search(config, web_client, query, album=True)
        return {
            album.date
            for album in search_result.albums
            if album.date not in (None, "0")
        }

    return {
        f"{track.album.date}"
        for track in _get_playlist_tracks(config, playlists, web_client)
        if track.album and track.album.date not in (None, 0)
    }


def _get_search(  # noqa: PLR0913
    config: SpotifyConfig,
    web_client: SpotifyOAuthClient,
    query: Query[SearchField],
    *,
    album: bool = False,
    artist: bool = False,
    track: bool = False,
) -> SearchResult:
    types = []
    if album:
        types.append("album")
    if artist:
        types.append("artist")
    if track:
        types.append("track")

    return search.search(
        config,
        web_client,
        query=query,
        types=types,
    )


def _get_playlist_tracks(
    config: SpotifyConfig,
    playlists: SpotifyPlaylistsProvider,
    web_client: SpotifyOAuthClient,  # noqa: ARG001
) -> Generator[Track]:
    if not config["allow_playlists"]:
        return

    for playlist_ref in playlists.as_list():
        playlist = playlists.lookup(playlist_ref.uri)
        if playlist:
            yield from playlist.tracks
