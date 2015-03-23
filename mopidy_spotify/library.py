from __future__ import unicode_literals

import logging
import urllib

from mopidy import backend, models

import spotify

from mopidy_spotify import countries, translator, utils


logger = logging.getLogger(__name__)

TOPLIST_TYPES = {
    'albums': spotify.ToplistType.ALBUMS,
    'artists': spotify.ToplistType.ARTISTS,
    'tracks': spotify.ToplistType.TRACKS,
}

TOPLIST_REGIONS = {
    'user': lambda session: spotify.ToplistRegion.USER,
    'country': lambda session: session.user_country,
    'everywhere': lambda session: spotify.ToplistRegion.EVERYWHERE,
}

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
                uri='spotify:top:tracks', name='Top tracks'),
            models.Ref.directory(
                uri='spotify:top:albums', name='Top albums'),
            models.Ref.directory(
                uri='spotify:top:artists', name='Top artists'),
        ]

    def browse(self, uri):
        if uri == self.root_directory.uri:
            return self._root_dir_contents
        elif uri.startswith('spotify:user:'):
            return self._browse_playlist(uri)
        elif uri.startswith('spotify:album:'):
            return self._browse_album(uri)
        elif uri.startswith('spotify:artist:'):
            return self._browse_artist(uri)
        elif uri.startswith('spotify:top:'):
            parts = uri.replace('spotify:top:', '').split(':')
            if len(parts) == 1:
                return self._browse_toplist_regions(variant=parts[0])
            elif len(parts) == 2:
                return self._browse_toplist(variant=parts[0], region=parts[1])
            else:
                logger.info(
                    'Failed to browse "%s": Toplist URI parsing failed', uri)
                return []
        else:
            logger.info('Failed to browse "%s": Unknown URI type', uri)
            return []

    def _browse_playlist(self, uri):
        sp_playlist = self._backend._session.get_playlist(uri)
        sp_playlist.load()
        return list(translator.to_track_refs(sp_playlist.tracks))

    def _browse_album(self, uri):
        sp_album_browser = self._backend._session.get_album(uri).browse()
        sp_album_browser.load()
        return list(translator.to_track_refs(sp_album_browser.tracks))

    def _browse_artist(self, uri):
        sp_artist_browser = self._backend._session.get_artist(uri).browse(
            type=spotify.ArtistBrowserType.NO_TRACKS)
        sp_artist_browser.load()
        top_tracks = list(translator.to_track_refs(
            sp_artist_browser.tophit_tracks))

        albums = list(translator.to_album_refs(sp_artist_browser.albums))
        return top_tracks + albums

    def _browse_toplist_regions(self, variant):
        return [
            models.Ref.directory(
                uri='spotify:top:%s:user' % variant, name='Personal'),
            models.Ref.directory(
                uri='spotify:top:%s:country' % variant, name='Country'),
            models.Ref.directory(
                uri='spotify:top:%s:countries' % variant,
                name='Other countries'),
            models.Ref.directory(
                uri='spotify:top:%s:everywhere' % variant, name='Global'),
        ]

    def _browse_toplist(self, variant, region):
        if region == 'countries':
            codes = self._backend._config['spotify']['toplist_countries']
            if not codes:
                codes = countries.COUNTRIES.keys()
            return [
                models.Ref.directory(
                    uri='spotify:top:%s:%s' % (variant, code.lower()),
                    name=countries.COUNTRIES.get(code.upper(), code.upper()))
                for code in codes]

        if region in ('user', 'country', 'everywhere'):
            sp_toplist = self._backend._session.get_toplist(
                type=TOPLIST_TYPES[variant],
                region=TOPLIST_REGIONS[region](self._backend._session))
        elif len(region) == 2:
            sp_toplist = self._backend._session.get_toplist(
                type=TOPLIST_TYPES[variant], region=region.upper())
        else:
            return []

        sp_toplist.load()

        if variant == 'tracks':
            return list(translator.to_track_refs(sp_toplist.tracks))
        elif variant == 'albums':
            return list(translator.to_album_refs(sp_toplist.albums))
        elif variant == 'artists':
            return list(translator.to_artist_refs(sp_toplist.artists))
        else:
            return []

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
                with utils.time_logger('Artist lookup'):
                    return list(self._lookup_artist(sp_link))
            elif sp_link.type is spotify.LinkType.PLAYLIST:
                return list(self._lookup_playlist(sp_link))
            elif sp_link.type is spotify.LinkType.STARRED:
                return list(reversed(list(self._lookup_playlist(sp_link))))
            else:
                logger.info(
                    'Failed to lookup "%s": Cannot handle %r',
                    uri, sp_link.type)
                return []
        except spotify.Error as exc:
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

        # Get all album browsers we need first, so they can start retrieving
        # data in the background.
        sp_album_browsers = []
        for sp_album in sp_artist_browser.albums:
            sp_album.load()
            if sp_album.type is spotify.AlbumType.COMPILATION:
                continue
            if sp_album.artist.link.uri in VARIOUS_ARTISTS_URIS:
                continue
            sp_album_browsers.append(sp_album.browse())

        for sp_album_browser in sp_album_browsers:
            sp_album_browser.load()
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

        # Collect albums
        albums = []
        for sp_album in sp_search.albums:
            cover = sp_album.cover(spotify.ImageSize.NORMAL).load()
            album = translator.to_album(sp_album, cover)
            albums.append(album)

        # Collect artists
        artists = [
            translator.to_artist(sp_artist) for sp_artist in sp_search.artists]

        # Collect tracks
        tracks = []
        for sp_track in sp_search.tracks:
            cover = sp_track.album.cover(spotify.ImageSize.NORMAL).load()
            track = translator.to_track(sp_track, None, cover)
            tracks.append(track)

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
