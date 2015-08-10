from __future__ import unicode_literals

import logging
import urllib

from mopidy import models

import spotify

from mopidy_spotify import lookup, translator


logger = logging.getLogger(__name__)


def search(config, session, query=None, uris=None, exact=False):
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

    sp_search = session.search(
        sp_query,
        album_count=config['search_album_count'],
        artist_count=config['search_artist_count'],
        track_count=config['search_track_count'])
    sp_search.load()

    albums = [
        translator.to_album(sp_album) for sp_album in sp_search.albums]
    artists = [
        translator.to_artist(sp_artist) for sp_artist in sp_search.artists]
    tracks = [
        translator.to_track(sp_track) for sp_track in sp_search.tracks]

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
