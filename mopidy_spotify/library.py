from __future__ import unicode_literals

import logging

from mopidy import backend

import spotify

from mopidy_spotify import translator


logger = logging.getLogger(__name__)


class SpotifyLibraryProvider(backend.LibraryProvider):

    def __init__(self, backend):
        self._backend = backend

    def lookup(self, uri):
        try:
            sp_link = self._backend._session.get_link(uri)
        except ValueError as exc:
            logger.info('Failed to lookup "%s": %s', uri, exc)
            return []

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
                'Failed to lookup "%s": Cannot handle %r', uri, sp_link.type)
            return []

    def _lookup_track(self, sp_link):
        sp_track = sp_link.as_track()
        sp_track.load()
        yield translator.to_track(sp_track, bitrate=self._backend.bitrate)

    def _lookup_album(self, sp_link):
        sp_album = sp_link.as_album()
        sp_album_browser = sp_album.browse()
        sp_album_browser.load()
        for sp_track in sp_album_browser.tracks:
            yield translator.to_track(
                sp_track, bitrate=self._backend.bitrate)

    def _lookup_artist(self, sp_link):
        sp_artist = sp_link.as_artist()
        sp_artist_browser = sp_artist.browse(
            type=spotify.ArtistBrowserType.NO_TRACKS)
        sp_artist_browser.load()
        for sp_album in sp_artist_browser.albums:
            sp_album_browser = sp_album.browse()
            sp_album_browser.load()
            for sp_track in sp_album_browser.tracks:
                yield translator.to_track(
                    sp_track, bitrate=self._backend.bitrate)

    def _lookup_playlist(self, sp_link):
        sp_playlist = sp_link.as_playlist()
        sp_playlist.load()
        for sp_track in sp_playlist.tracks:
            yield translator.to_track(
                sp_track, bitrate=self._backend.bitrate)
