from __future__ import unicode_literals

import logging
import threading
import time
import urllib

import pykka
from spotify import Link, SpotifyError, ToplistBrowser

from mopidy.backends import base
from mopidy.models import Ref, Track, SearchResult

from . import translator

logger = logging.getLogger(__name__)

SPOTIFY_COUNTRIES = {
    'AD': 'Andorra',
    'AR': 'Argentina',
    'AT': 'Austria',
    'AU': 'Australia',
    'BE': 'Belgium',
    'CH': 'Switzerland',
    'CO': 'Colombia',
    'CY': 'Cyprus',
    'DE': 'Germany',
    'DK': 'Denmark',
    'EE': 'Estonia',
    'ES': 'Spain',
    'FI': 'Finland',
    'FR': 'France',
    'GB': 'United Kingdom',
    'GR': 'Greece',
    'HK': 'Hong Kong',
    'IE': 'Ireland',
    'IS': 'Iceland',
    'IT': 'Italy',
    'LI': 'Liechtenstein',
    'LT': 'Lithuania',
    'LU': 'Luxembourg',
    'LV': 'Latvia',
    'MC': 'Monaco',
    'MX': 'Mexico',
    'MY': 'Malaysia',
    'NL': 'Netherlands',
    'NO': 'Norway',
    'NZ': 'New Zealand',
    'PT': 'Portugal',
    'SE': 'Sweden',
    'SG': 'Singapore',
    'TR': 'Turkey',
    'TW': 'Taiwan',
    'US': 'United States'}


class SpotifyTrack(Track):
    """Proxy object for unloaded Spotify tracks."""
    def __init__(self, uri=None, track=None):
        super(SpotifyTrack, self).__init__()
        if (uri and track) or (not uri and not track):
            raise AttributeError('uri or track must be provided')
        elif uri:
            self._spotify_track = Link.from_string(uri).as_track()
        elif track:
            self._spotify_track = track
        self._track = None

    @property
    def _proxy(self):
        if self._track is None:
            if not self._spotify_track.is_loaded():
                return translator.to_mopidy_track(self._spotify_track)
            self._track = translator.to_mopidy_track(self._spotify_track)
        return self._track

    def __getattribute__(self, name):
        if name.startswith('_'):
            return super(SpotifyTrack, self).__getattribute__(name)
        return self._proxy.__getattribute__(name)

    def __repr__(self):
        return self._proxy.__repr__()

    def __hash__(self):
        return hash(self._proxy.uri)

    def __eq__(self, other):
        if not isinstance(other, Track):
            return False
        return self._proxy.uri == other.uri

    def copy(self, **values):
        return self._proxy.copy(**values)


class SpotifyLibraryProvider(base.BaseLibraryProvider):
    root_directory = Ref.directory(uri='spotify:directory', name='Spotify')

    def __init__(self, *args, **kwargs):
        super(SpotifyLibraryProvider, self).__init__(*args, **kwargs)
        self._timeout = self.backend.config['spotify']['timeout']

        # TODO: add /artists/{top/tracks,albums/tracks} and /users?
        self._root = [Ref.directory(uri='spotify:toplist:current',
                                    name='Personal top tracks'),
                      Ref.directory(uri='spotify:toplist:all',
                                    name='Global top tracks')]
        self._countries = []

        if not self.backend.config['spotify']['toplist_countries']:
            return

        self._root.append(Ref.directory(uri='spotify:toplist:countries',
                                        name='Country top tracks'))
        for code in self.backend.config['spotify']['toplist_countries']:
            code = code.upper()
            self._countries.append(Ref.directory(
                uri='spotify:toplist:%s' % code.lower(),
                name=SPOTIFY_COUNTRIES.get(code, code)))

    def browse(self, uri):
        if uri == self.root_directory.uri:
            return self._root

        variant, identifier = translator.parse_uri(uri.lower())
        if variant != 'toplist':
            return []

        if identifier == 'countries':
            return self._countries

        if identifier not in ('all', 'current'):
            identifier = identifier.upper()
            if identifier not in SPOTIFY_COUNTRIES:
                return []

        result = []
        done = threading.Event()

        def callback(browser, userdata):
            for track in browser:
                result.append(translator.to_mopidy_track_ref(track))
            done.set()

        logger.debug('Performing toplist browse for %s', identifier)
        ToplistBrowser(b'tracks', bytes(identifier), callback, None)
        if not done.wait(self._timeout):
            logger.warning('%s toplist browse timed out.', identifier)

        return result

    def find_exact(self, query=None, uris=None):
        return self.search(query=query, uris=uris)

    def lookup(self, uri):
        try:
            link = Link.from_string(uri)
            if link.type() == Link.LINK_TRACK:
                return self._lookup_track(uri)
            if link.type() == Link.LINK_ALBUM:
                return self._lookup_album(uri)
            elif link.type() == Link.LINK_ARTIST:
                return self._lookup_artist(uri)
            elif link.type() == Link.LINK_PLAYLIST:
                return self._lookup_playlist(uri)
            else:
                return []
        except SpotifyError as error:
            logger.debug(u'Failed to lookup "%s": %s', uri, error)
            return []

    def _lookup_track(self, uri):
        track = Link.from_string(uri).as_track()
        self._wait_for_object_to_load(track)
        if track.is_loaded():
            return [SpotifyTrack(track=track)]
        else:
            return [SpotifyTrack(uri=uri)]

    def _lookup_album(self, uri):
        album = Link.from_string(uri).as_album()
        album_browser = self.backend.spotify.session.browse_album(album)
        self._wait_for_object_to_load(album_browser)
        return [SpotifyTrack(track=t) for t in album_browser]

    def _lookup_artist(self, uri):
        artist = Link.from_string(uri).as_artist()
        artist_browser = self.backend.spotify.session.browse_artist(artist)
        self._wait_for_object_to_load(artist_browser)
        return [SpotifyTrack(track=t) for t in artist_browser]

    def _lookup_playlist(self, uri):
        playlist = Link.from_string(uri).as_playlist()
        self._wait_for_object_to_load(playlist)
        return [SpotifyTrack(track=t) for t in playlist]

    def _wait_for_object_to_load(self, spotify_obj, timeout=None):
        # XXX Sleeping to wait for the Spotify object to load is an ugly hack,
        # but it works. We should look into other solutions for this.
        if timeout is None:
            timeout = self._timeout
        wait_until = time.time() + timeout
        while not spotify_obj.is_loaded():
            time.sleep(0.1)
            if time.time() > wait_until:
                logger.debug(
                    'Timeout: Spotify object did not load in %ds', timeout)
                return

    def refresh(self, uri=None):
        pass  # TODO

    def search(self, query=None, uris=None):
        # TODO Only return results within URI roots given by ``uris``

        if not query:
            return self._get_all_tracks()

        uris = query.get('uri', [])
        if uris:
            tracks = []
            for uri in uris:
                tracks += self.lookup(uri)
            if len(uris) == 1:
                uri = uris[0]
            else:
                uri = 'spotify:search'
            return SearchResult(uri=uri, tracks=tracks)

        spotify_query = self._translate_search_query(query)

        if not spotify_query:
            logger.debug('Spotify search aborted due to empty query')
            return SearchResult(uri='spotify:search')

        logger.debug('Spotify search query: %s' % spotify_query)

        future = pykka.ThreadingFuture()

        def callback(results, userdata=None):
            search_result = SearchResult(
                uri='spotify:search:%s' % (
                    urllib.quote(results.query().encode('utf-8'))),
                albums=[
                    translator.to_mopidy_album(a) for a in results.albums()],
                artists=[
                    translator.to_mopidy_artist(a) for a in results.artists()],
                tracks=[
                    translator.to_mopidy_track(t) for t in results.tracks()])
            future.set(search_result)

        if not self.backend.spotify.connected.is_set():
            logger.debug('Not connected: Spotify search cancelled')
            return SearchResult(uri='spotify:search')

        self.backend.spotify.session.search(
            spotify_query, callback,
            album_count=200, artist_count=200, track_count=200)

        try:
            return future.get(timeout=self._timeout)
        except pykka.Timeout:
            logger.debug(
                'Timeout: Spotify search did not return in %ds', self._timeout)
            return SearchResult(uri='spotify:search')

    def _get_all_tracks(self):
        # Since we can't search for the entire Spotify library, we return
        # all tracks in the playlists when the query is empty.
        tracks = []
        for playlist in self.backend.playlists.playlists:
            tracks += playlist.tracks
        return SearchResult(uri='spotify:search', tracks=tracks)

    def _translate_search_query(self, mopidy_query):
        spotify_query = []
        for (field, values) in mopidy_query.iteritems():
            if field == 'albumartist':
                # XXX Don't know of a way to search for the album's artist
                # instead of the track's artist on Spotify.
                field = 'artist'
            if field == 'track_name':
                field = 'track'
            if field == 'track_no':
                # Spotify does not support filtering by track number.
                continue
            if field == 'date':
                field = 'year'
            if not hasattr(values, '__iter__'):
                values = [values]
            for value in values:
                if field == 'any':
                    spotify_query.append(value)
                elif field == 'year':
                    value = int(value.split('-')[0])  # Extract year
                    spotify_query.append('%s:%d' % (field, value))
                else:
                    spotify_query.append('%s:"%s"' % (field, value))
        spotify_query = ' '.join(spotify_query)
        return spotify_query
