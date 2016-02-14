from __future__ import unicode_literals

import logging
import urllib

from mopidy import models

import requests

import spotify

from mopidy_spotify import lookup, translator


_API_BASE_URI = 'https://api.spotify.com/v1/search'
_SEARCH_TYPES = 'album,artist,track'

logger = logging.getLogger(__name__)


def search(config, session, requests_session,
           query=None, uris=None, exact=False):
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

    try:
        response = requests_session.get(_API_BASE_URI, params={
            'q': sp_query,
            'limit': config['search_track_count'],
            'type': _SEARCH_TYPES})
    except requests.RequestException as exc:
        logger.debug('Fetching %s failed: %s', uri, exc)
        return models.SearchResult(uri=uri)

    try:
        result = response.json()
    except ValueError as exc:
        logger.debug('JSON decoding failed for %s: %s', uri, exc)
        return models.SearchResult(uri=uri)

    albums = [
        translator.webapi_to_album(sp_album)
        for sp_album in result['albums']['items']]
    artists = [
        translator.webapi_to_artist(sp_artist)
        for sp_artist in result['artists']['items']]
    tracks = [
        translator.webapi_to_track(sp_track)
        for sp_track in result['tracks']['items']]

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
