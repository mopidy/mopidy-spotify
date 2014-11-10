from __future__ import unicode_literals

from mopidy import backend

import spotify

from mopidy_spotify import translator


class SpotifyLibraryProvider(backend.LibraryProvider):

    def __init__(self, backend):
        self._backend = backend

    def lookup(self, uri):
        sp_link = self._backend._session.get_link(uri)

        if sp_link.type is spotify.LinkType.TRACK:
            sp_track = sp_link.as_track()
            sp_track.load()
            return [
                translator.to_track(sp_track, bitrate=self._backend.bitrate)]
        elif sp_link.type is spotify.LinkType.ALBUM:
            sp_album = sp_link.as_album()
            sp_album_browser = sp_album.browse()
            sp_album_browser.load()
            return [
                translator.to_track(sp_track, bitrate=self._backend.bitrate)
                for sp_track in sp_album_browser.tracks]
        elif sp_link.type is spotify.LinkType.ARTIST:
            sp_artist = sp_link.as_artist()
            sp_artist_browser = sp_artist.browse(
                type=spotify.ArtistBrowserType.NO_TRACKS)
            sp_artist_browser.load()
            return [
                translator.to_track(sp_track, bitrate=self._backend.bitrate)
                for sp_album in sp_artist_browser.albums
                for sp_track in sp_album.browse().load().tracks]
        else:
            return []
