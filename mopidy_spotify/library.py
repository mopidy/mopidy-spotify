from __future__ import unicode_literals

import logging
import urllib

from mopidy import backend, models

import spotify

from mopidy_spotify import countries, translator


logger = logging.getLogger(__name__)


VARIOUS_ARTISTS_URIS = [
    'spotify:artist:0LyfQWJT6nXafLPZqxe9Of',
]


class SpotifyLibraryProvider(backend.LibraryProvider):
    root_directory = models.Ref.directory(
        uri='spotify:directory', name='Spotify')

    def __init__(self, backend):
        self._backend = backend

        self._root_dir_contents = [
            models.Ref.directory(
                uri='spotify:top:tracks:user', name='Your top tracks'),
            models.Ref.directory(
                uri='spotify:top:tracks:user_country',
                name="Your country's top tracks"),
            models.Ref.directory(
                uri='spotify:top:tracks:everywhere', name='Global top tracks'),
        ]

        self._toplist_countries = [
            models.Ref.directory(
                uri='spotify:top:tracks:%s' % code.lower(),
                name=countries.COUNTRIES.get(code.upper(), code.upper()))
            for code in self._backend._config['spotify']['toplist_countries']]

        if self._toplist_countries:
            self._root_dir_contents.append(models.Ref.directory(
                uri='spotify:top:tracks:countries', name='Country top tracks'))

    def browse(self, uri):
        if uri == self.root_directory.uri:
            return self._root_dir_contents
        elif uri.startswith('spotify:top:tracks:'):
            return self._browse_toplist(uri)
        else:
            return []

    def _browse_toplist(self, uri):
        uri = uri.replace('spotify:top:tracks:', '')

        if uri == 'user':
            toplist = self._backend._session.get_toplist(
                type=spotify.ToplistType.TRACKS,
                region=spotify.ToplistRegion.USER)
            return list(self._get_toplist_track_refs(toplist))
        if uri == 'user_country':
            toplist = self._backend._session.get_toplist(
                type=spotify.ToplistType.TRACKS,
                region=self._backend._session.user_country)
            return list(self._get_toplist_track_refs(toplist))
        elif uri == 'everywhere':
            toplist = self._backend._session.get_toplist(
                type=spotify.ToplistType.TRACKS,
                region=spotify.ToplistRegion.EVERYWHERE)
            return list(self._get_toplist_track_refs(toplist))
        elif uri == 'countries':
            return self._toplist_countries
        elif uri.upper() in countries.COUNTRIES.keys():
            country_code = uri.upper()
            toplist = self._backend._session.get_toplist(
                type=spotify.ToplistType.TRACKS, region=country_code)
            return list(self._get_toplist_track_refs(toplist))
        else:
            return []

    def _get_toplist_track_refs(self, toplist):
        toplist.load()
        for sp_track in toplist.tracks:
            sp_track.load()
            track = translator.to_track_ref(sp_track)
            if track is not None:
                yield track

    def lookup(self, uri):
        try:
            sp_link = self._backend._session.get_link(uri)
        except ValueError as exc:
            logger.info('Failed to lookup "%s": %s', uri, exc)
            return []

        try:
            if sp_link.type is spotify.LinkType.TRACK:
                return list(self._lookup_track(sp_link))
            elif sp_link.type is spotify.LinkType.ALBUM:
                return list(self._lookup_album(sp_link))
            elif sp_link.type is spotify.LinkType.ARTIST:
                return list(self._lookup_artist(sp_link))
            elif sp_link.type is spotify.LinkType.PLAYLIST:
                return list(self._lookup_playlist(sp_link))
            else:
                logger.info(
                    'Failed to lookup "%s": Cannot handle %r',
                    uri, sp_link.type)
                return []
        except RuntimeError as exc:
            logger.info('Failed to lookup "%s": %s', uri, exc)
            return []

    def _lookup_track(self, sp_link):
        sp_track = sp_link.as_track()
        sp_track.load()
        track = translator.to_track(sp_track, bitrate=self._backend._bitrate)
        if track is not None:
            yield track

    def _lookup_album(self, sp_link):
        sp_album = sp_link.as_album()
        sp_album_browser = sp_album.browse()
        sp_album_browser.load()
        for sp_track in sp_album_browser.tracks:
            track = translator.to_track(
                sp_track, bitrate=self._backend._bitrate)
            if track is not None:
                yield track

    def _lookup_artist(self, sp_link):
        sp_artist = sp_link.as_artist()
        sp_artist_browser = sp_artist.browse(
            type=spotify.ArtistBrowserType.NO_TRACKS)
        sp_artist_browser.load()
        for sp_album in sp_artist_browser.albums:
            sp_album_browser = sp_album.browse()
            sp_album_browser.load()
            if sp_album.type is spotify.AlbumType.COMPILATION:
                continue
            if sp_album.artist.link.uri in VARIOUS_ARTISTS_URIS:
                continue
            for sp_track in sp_album_browser.tracks:
                track = translator.to_track(
                    sp_track, bitrate=self._backend._bitrate)
                if track is not None:
                    yield track

    def _lookup_playlist(self, sp_link):
        sp_playlist = sp_link.as_playlist()
        sp_playlist.load()
        for sp_track in sp_playlist.tracks:
            track = translator.to_track(
                sp_track, bitrate=self._backend._bitrate)
            if track is not None:
                yield track

    def search(self, query=None, uris=None):
        # TODO Respect `uris` argument

        if query is None:
            logger.debug('Ignored search without query')
            return models.SearchResult(uri='spotify:search')

        if 'uri' in query:
            return self._search_by_uri(query)

        sp_query = translator.sp_search_query(query)
        if not sp_query:
            logger.debug('Ignored search with empty query')
            return models.SearchResult(uri='spotify:search')

        uri = 'spotify:search:%s' % urllib.quote(sp_query.encode('utf-8'))
        logger.debug('Searching Spotify for: %s', sp_query)

        if not self._backend._online.is_set():
            logger.info('Search aborted: Spotify is offline')
            return models.SearchResult(uri=uri)

        spotify_config = self._backend._config['spotify']
        sp_search = self._backend._session.search(
            sp_query,
            album_count=spotify_config['search_album_count'],
            artist_count=spotify_config['search_artist_count'],
            track_count=spotify_config['search_track_count'])
        sp_search.load()

        albums = [
            translator.to_album(sp_album) for sp_album in sp_search.albums]
        artists = [
            translator.to_artist(sp_artist) for sp_artist in sp_search.artists]
        tracks = [
            translator.to_track(sp_track) for sp_track in sp_search.tracks]

        return models.SearchResult(
            uri=uri, albums=albums, artists=artists, tracks=tracks)

    def _search_by_uri(self, query):
        tracks = []
        for uri in query['uri']:
            tracks += self.lookup(uri)

        uri = 'spotify:search'
        if len(query['uri']) == 1:
            uri = query['uri'][0]

        return models.SearchResult(uri=uri, tracks=tracks)

    # Spotify doesn't support exact search
    find_exact = search
