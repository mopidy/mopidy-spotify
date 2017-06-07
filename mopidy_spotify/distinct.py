from __future__ import unicode_literals

import logging

import spotify

from mopidy_spotify import search


logger = logging.getLogger(__name__)


def get_distinct(config, session, web_client, field, query=None):
    # To make the returned data as interesting as possible, we limit
    # ourselves to data extracted from the user's playlists when no search
    # query is included.

    if field == 'artist':
        result = _get_distinct_artists(
            config, session, web_client, query)
    elif field == 'albumartist':
        result = _get_distinct_albumartists(
            config, session, web_client, query)
    elif field == 'album':
        result = _get_distinct_albums(
            config, session, web_client, query)
    elif field == 'date':
        result = _get_distinct_dates(
            config, session, web_client, query)
    else:
        result = set()

    return result - {None}


def _get_distinct_artists(config, session, web_client, query):
    logger.debug('Getting distinct artists: %s', query)
    if query:
        search_result = _get_search(
            config, session, web_client, query, artist=True)
        return {artist.name for artist in search_result.artists}
    else:
        return {
            artist.name
            for track in _get_playlist_tracks(config, session)
            for artist in track.artists}


def _get_distinct_albumartists(config, session, web_client, query):
    logger.debug(
        'Getting distinct albumartists: %s', query)
    if query:
        search_result = _get_search(
            config, session, web_client, query, album=True)
        return {
            artist.name
            for album in search_result.albums
            for artist in album.artists
            if album.artists}
    else:
        return {
            track.album.artist.name
            for track in _get_playlist_tracks(config, session)
            if track.album and track.album.artist}


def _get_distinct_albums(config, session, web_client, query):
    logger.debug('Getting distinct albums: %s', query)
    if query:
        search_result = _get_search(
            config, session, web_client, query, album=True)
        return {album.name for album in search_result.albums}
    else:
        return {
            track.album.name
            for track in _get_playlist_tracks(config, session)
            if track.album}


def _get_distinct_dates(config, session, web_client, query):
    logger.debug('Getting distinct album years: %s', query)
    if query:
        search_result = _get_search(
            config, session, web_client, query, album=True)
        return {
            album.date
            for album in search_result.albums
            if album.date not in (None, '0')}
    else:
        return {
            '%s' % track.album.year
            for track in _get_playlist_tracks(config, session)
            if track.album and track.album.year not in (None, 0)}


def _get_search(
        config, session, web_client, query,
        album=False, artist=False, track=False):

    types = []
    if album:
        types.append('album')
    if artist:
        types.append('artist')
    if track:
        types.append('track')

    return search.search(
        config, session, web_client, query, types=types)


def _get_playlist_tracks(config, session):
    if not config['allow_playlists']:
        return

    for playlist in session.playlist_container:
        if not isinstance(playlist, spotify.Playlist):
            continue
        playlist.load()
        for track in playlist.tracks:
            try:
                track.load()
                yield track
            except spotify.Error:  # TODO Why did we get "General error"?
                continue
