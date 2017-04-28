from __future__ import unicode_literals

import logging
import urllib

from mopidy import models

import requests

import spotify

from mopidy_spotify import lookup, translator


_API_BASE_URI = 'https://api.spotify.com/v1/search'
_SEARCH_TYPES = ['album', 'artist', 'track']

logger = logging.getLogger(__name__)


def search(config, session, web_client,
           query=None, uris=None, exact=False, types=_SEARCH_TYPES):
    # TODO Respect `uris` argument
    # TODO Support `exact` search

    if query is None:
        logger.debug('Ignored search without query')
        return models.SearchResult(uri='spotify:search')

    if 'uri' in query:
        return _search_by_uri(config, session, query)

    sp_query = translator.sp_search_query(query)
    if not sp_query:
        logger.debug('Ignored search with empty query')
        return models.SearchResult(uri='spotify:search')

    uri = 'spotify:search:%s' % urllib.quote(sp_query.encode('utf-8'))
    logger.info('Searching Spotify for: %s', sp_query)

    if session.connection.state is not spotify.ConnectionState.LOGGED_IN:
        logger.info('Spotify search aborted: Spotify is offline')
        return models.SearchResult(uri=uri)

    search_count = max(
        config['search_album_count'],
        config['search_artist_count'],
        config['search_track_count'])

    if search_count > 50:
        logger.warn(
            'Spotify currently allows maximum 50 search results of each type. '
            'Please set the config values spotify/search_album_count, '
            'spotify/search_artist_count and spotify/search_track_count '
            'to at most 50.')
        search_count = 50

    try:
        response = web_client.get(_API_BASE_URI, params={
            'q': sp_query,
            'limit': search_count,
            'type': ','.join(types)})
    except requests.RequestException as exc:
        logger.debug('Fetching %s failed: %s', uri, exc)
        return models.SearchResult(uri=uri)

    try:
        result = response.json()
    except ValueError as exc:
        logger.debug('JSON decoding failed for %s: %s', uri, exc)
        return models.SearchResult(uri=uri)

    albums = [
        translator.web_to_album(web_album) for web_album in
        result['albums']['items'][:config['search_album_count']]
    ] if 'albums' in result else []

    artists = [
        translator.web_to_artist(web_artist) for web_artist in
        result['artists']['items'][:config['search_artist_count']]
    ] if 'artists' in result else []

    tracks = [
        translator.web_to_track(web_track) for web_track in
        result['tracks']['items'][:config['search_track_count']]
    ] if 'tracks' in result else []

    return models.SearchResult(
        uri=uri, albums=albums, artists=artists, tracks=tracks)


def _search_by_uri(config, session, query):
    tracks = []
    for uri in query['uri']:
        tracks += lookup.lookup(config, session, uri)

    uri = 'spotify:search'
    if len(query['uri']) == 1:
        uri = query['uri'][0]

    return models.SearchResult(uri=uri, tracks=tracks)
