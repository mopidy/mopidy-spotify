import logging

from mopidy_spotify import search

logger = logging.getLogger(__name__)


def get_distinct(config, playlists, web_client, field, query=None):
    # To make the returned data as interesting as possible, we limit
    # ourselves to data extracted from the user's playlists when no search
    # query is included.
    # TODO: Perhaps should use tracks from My Music instead?
    if web_client is None or not web_client.logged_in:
        return set()

    if field == "artist":
        result = _get_distinct_artists(config, playlists, web_client, query)
    elif field == "albumartist":
        result = _get_distinct_albumartists(
            config, playlists, web_client, query
        )
    elif field == "album":
        result = _get_distinct_albums(config, playlists, web_client, query)
    elif field == "date":
        result = _get_distinct_dates(config, playlists, web_client, query)
    else:
        result = set()

    return result - {None}


def _get_distinct_artists(config, playlists, web_client, query):
    logger.debug(f"Getting distinct artists: {query}")
    if query:
        search_result = _get_search(config, web_client, query, artist=True)
        return {artist.name for artist in search_result.artists}
    else:
        return {
            artist.name
            for track in _get_playlist_tracks(config, playlists, web_client)
            for artist in track.artists
        }


def _get_distinct_albumartists(config, playlists, web_client, query):
    logger.debug(f"Getting distinct albumartists: {query}")
    if query:
        search_result = _get_search(config, web_client, query, album=True)
        return {
            artist.name
            for album in search_result.albums
            for artist in album.artists
            if album.artists
        }
    else:
        return {
            artists.name
            for track in _get_playlist_tracks(config, playlists, web_client)
            for artists in track.album.artists
            if track.album and track.album.artists
        }


def _get_distinct_albums(config, playlists, web_client, query):
    logger.debug(f"Getting distinct albums: {query}")
    if query:
        search_result = _get_search(config, web_client, query, album=True)
        return {album.name for album in search_result.albums}
    else:
        return {
            track.album.name
            for track in _get_playlist_tracks(config, playlists, web_client)
            if track.album
        }


def _get_distinct_dates(config, playlists, web_client, query):
    logger.debug(f"Getting distinct album years: {query}")
    if query:
        search_result = _get_search(config, web_client, query, album=True)
        return {
            album.date
            for album in search_result.albums
            if album.date not in (None, "0")
        }
    else:
        return {
            f"{track.album.date}"
            for track in _get_playlist_tracks(config, playlists, web_client)
            if track.album and track.album.date not in (None, 0)
        }


def _get_search(
    config, web_client, query, album=False, artist=False, track=False
):

    types = []
    if album:
        types.append("album")
    if artist:
        types.append("artist")
    if track:
        types.append("track")

    return search.search(config, web_client, query, types=types)


def _get_playlist_tracks(config, playlists, web_client):
    if not playlists or not config["allow_playlists"]:
        return

    for playlist_ref in playlists.as_list():
        playlist = playlists.lookup(playlist_ref.uri)
        if playlist:
            for track in playlist.tracks:
                yield track
