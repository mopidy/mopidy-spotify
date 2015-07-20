from __future__ import unicode_literals

import logging
import urllib

from mopidy import backend, models

import spotify

from mopidy_spotify import browse, images, translator, utils


logger = logging.getLogger(__name__)

VARIOUS_ARTISTS_URIS = [
    'spotify:artist:0LyfQWJT6nXafLPZqxe9Of',
]


class SpotifyLibraryProvider(backend.LibraryProvider):
    root_directory = browse.ROOT_DIR

    def __init__(self, backend):
        self._backend = backend

        spotify_config = self._backend._config['spotify']
        self._search_album_count = spotify_config['search_album_count']
        self._search_artist_count = spotify_config['search_artist_count']
        self._search_track_count = spotify_config['search_track_count']

    def browse(self, uri):
        return browse.browse(self._config, self._backend._session, uri)

    def get_distinct(self, field, query=None):
        # To make the returned data as interesting as possible, we limit
        # ourselves to data extracted from the user's playlists when no search
        # query is included.

        sp_query = translator.sp_search_query(query) if query else None

        if field == 'artist':
            return self._get_distinct_artists(sp_query)
        elif field == 'albumartist':
            return self._get_distinct_albumartists(sp_query)
        elif field == 'album':
            return self._get_distinct_albums(sp_query)
        elif field == 'date':
            return self._get_distinct_dates(sp_query)
        else:
            return set()

    def _get_distinct_artists(self, sp_query):
        logger.debug('Getting distinct artists: %s', sp_query)
        if sp_query:
            sp_search = self._get_sp_search(sp_query, artist=True)
            return {artist.name for artist in sp_search.artists}
        else:
            return {
                artist.name
                for track in self._get_playlist_tracks()
                for artist in track.artists}

    def _get_distinct_albumartists(self, sp_query):
        logger.debug(
            'Getting distinct albumartists: %s', sp_query)
        if sp_query:
            sp_search = self._get_sp_search(sp_query, album=True)
            return {album.artist.name for album in sp_search.albums}
        else:
            return {
                track.album.artist.name
                for track in self._get_playlist_tracks()}

    def _get_distinct_albums(self, sp_query):
        logger.debug('Getting distinct albums: %s', sp_query)
        if sp_query:
            sp_search = self._get_sp_search(sp_query, album=True)
            return {album.name for album in sp_search.albums}
        else:
            return {track.album.name for track in self._get_playlist_tracks()}

    def _get_distinct_dates(self, sp_query):
        logger.debug('Getting distinct album years: %s', sp_query)
        if sp_query:
            sp_search = self._get_sp_search(sp_query, album=True)
            return {
                '%s' % album.year
                for album in sp_search.albums
                if album.year != 0}
        else:
            return {
                '%s' % track.album.year
                for track in self._get_playlist_tracks()
                if track.album.year != 0}

    def _get_sp_search(self, sp_query, album=False, artist=False, track=False):
        sp_search = self._backend._session.search(
            sp_query,
            album_count=self._search_album_count if album else 0,
            artist_count=self._search_artist_count if artist else 0,
            track_count=self._search_track_count if track else 0)
        sp_search.load()
        return sp_search

    def _get_playlist_tracks(self):
        if not self._backend._config['spotify']['allow_playlists']:
            return

        for playlist in self._backend._session.playlist_container:
            if not isinstance(playlist, spotify.Playlist):
                continue
            playlist.load()
            for track in playlist.tracks:
                try:
                    track.load()
                    yield track
                except spotify.Error:  # TODO Why did we get "General error"?
                    continue

    def get_images(self, uris):
        return images.get_images(uris)

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

    def search(self, query=None, uris=None, exact=False):
        # TODO Respect `uris` argument
        # TODO Support `exact` search

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
        logger.info('Searching Spotify for: %s', sp_query)

        if not self._backend._online.is_set():
            logger.info('Spotify search aborted: Spotify is offline')
            return models.SearchResult(uri=uri)

        sp_search = self._backend._session.search(
            sp_query,
            album_count=self._search_album_count,
            artist_count=self._search_artist_count,
            track_count=self._search_track_count)
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
