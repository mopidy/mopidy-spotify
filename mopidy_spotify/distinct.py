from __future__ import unicode_literals

import logging

import spotify

from mopidy_spotify import translator


logger = logging.getLogger(__name__)


def get_distinct(config, session, field, query=None):
    # To make the returned data as interesting as possible, we limit
    # ourselves to data extracted from the user's playlists when no search
    # query is included.

    sp_query = translator.sp_search_query(query) if query else None

    if field == 'artist':
        result = _get_distinct_artists(config, session, sp_query)
    elif field == 'albumartist':
        result = _get_distinct_albumartists(config, session, sp_query)
    elif field == 'album':
        result = _get_distinct_albums(config, session, sp_query)
    elif field == 'date':
        result = _get_distinct_dates(config, session, sp_query)
    else:
        result = set()

    return result - {None}


def _get_distinct_artists(config, session, sp_query):
    logger.debug('Getting distinct artists: %s', sp_query)
    if sp_query:
        sp_search = _get_sp_search(config, session, sp_query, artist=True)
        if sp_search is None:
            return set()
        return {artist.name for artist in sp_search.artists}
    else:
        return {
            artist.name
            for track in _get_playlist_tracks(config, session)
            for artist in track.artists}


def _get_distinct_albumartists(config, session, sp_query):
    logger.debug(
        'Getting distinct albumartists: %s', sp_query)
    if sp_query:
        sp_search = _get_sp_search(config, session, sp_query, album=True)
        if sp_search is None:
            return set()
        return {
            album.artist.name
            for album in sp_search.albums
            if album.artist}
    else:
        return {
            track.album.artist.name
            for track in _get_playlist_tracks(config, session)
            if track.album and track.album.artist}


def _get_distinct_albums(config, session, sp_query):
    logger.debug('Getting distinct albums: %s', sp_query)
    if sp_query:
        sp_search = _get_sp_search(config, session, sp_query, album=True)
        if sp_search is None:
            return set()
        return {album.name for album in sp_search.albums}
    else:
        return {
            track.album.name
            for track in _get_playlist_tracks(config, session)
            if track.album}


def _get_distinct_dates(config, session, sp_query):
    logger.debug('Getting distinct album years: %s', sp_query)
    if sp_query:
        sp_search = _get_sp_search(config, session, sp_query, album=True)
        if sp_search is None:
            return set()
        return {
            '%s' % album.year
            for album in sp_search.albums
            if album.year not in (None, 0)}
    else:
        return {
            '%s' % track.album.year
            for track in _get_playlist_tracks(config, session)
            if track.album and track.album.year not in (None, 0)}


def _get_sp_search(
        config, session, sp_query, album=False, artist=False, track=False):

    if session.connection.state is not spotify.ConnectionState.LOGGED_IN:
        logger.info('Spotify search aborted: Spotify is offline')
        return None

    sp_search = session.search(
        sp_query,
        album_count=config['search_album_count'] if album else 0,
        artist_count=config['search_artist_count'] if artist else 0,
        track_count=config['search_track_count'] if track else 0)
    sp_search.load()
    return sp_search


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
