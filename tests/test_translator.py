from __future__ import unicode_literals

import mock

from mopidy import models

import spotify

from mopidy_spotify import translator


class TestToArtist(object):

    def test_returns_none_if_unloaded(self, sp_artist_mock):
        sp_artist_mock.is_loaded = False

        artist = translator.to_artist(sp_artist_mock)

        assert artist is None

    def test_successful_translation(self, sp_artist_mock):
        artist = translator.to_artist(sp_artist_mock)

        assert artist.uri == 'spotify:artist:abba'
        assert artist.name == 'ABBA'


class TestToAlbum(object):

    def test_returns_none_if_unloaded(self, sp_album_mock):
        sp_album_mock.is_loaded = False

        album = translator.to_album(sp_album_mock)

        assert album is None

    def test_successful_translation(self, sp_album_mock):
        album = translator.to_album(sp_album_mock)

        assert album.uri == 'spotify:album:def'
        assert album.name == 'DEF 456'
        assert list(album.artists) == [
            models.Artist(uri='spotify:artist:abba', name='ABBA')]
        assert album.date == '2001'

    def test_returns_empty_artists_list_if_artist_is_none(self, sp_album_mock):
        sp_album_mock.artist = None

        album = translator.to_album(sp_album_mock)

        assert list(album.artists) == []

    def test_returns_unknown_date_if_year_is_none(self, sp_album_mock):
        sp_album_mock.year = None

        album = translator.to_album(sp_album_mock)

        assert album.date is None


class TestToTrack(object):

    def test_returns_none_if_unloaded(self, sp_track_mock):
        sp_track_mock.is_loaded = False

        track = translator.to_track(sp_track_mock)

        assert track is None

    def test_returns_none_if_error(self, sp_track_mock):
        sp_track_mock.error = spotify.ErrorType.OTHER_PERMANENT

        track = translator.to_track(sp_track_mock)

        assert track is None

    def test_returns_none_if_not_available(self, sp_track_mock):
        sp_track_mock.availability = spotify.TrackAvailability.UNAVAILABLE

        track = translator.to_track(sp_track_mock)

        assert track is None

    def test_successful_translation(self, sp_track_mock):
        track = translator.to_track(sp_track_mock)

        assert track.uri == 'spotify:track:abc'
        assert track.name == 'ABC 123'
        assert list(track.artists) == [
            models.Artist(uri='spotify:artist:abba', name='ABBA')]
        assert track.album == models.Album(
            uri='spotify:album:def',
            name='DEF 456',
            artists=[
                models.Artist(uri='spotify:artist:abba', name='ABBA')],
            date='2001')
        assert track.date == '2001'
        assert track.length == 174300
        assert track.track_no == 7

    def test_filters_out_none_artists(self, sp_artist_mock, sp_track_mock):
        sp_artist_mock.is_loaded = False

        track = translator.to_track(sp_track_mock)

        assert list(track.artists) == []


class TestToPlaylist(object):

    def test_returns_none_if_unloaded(self):
        sp_playlist = mock.Mock(spec=spotify.Playlist)
        sp_playlist.is_loaded = False

        playlist = translator.to_playlist(sp_playlist)

        assert playlist is None

    def test_returns_none_if_playlist_folder(self):
        sp_playlist_folder = mock.Mock(spec=spotify.PlaylistFolder)

        playlist = translator.to_playlist(sp_playlist_folder)

        assert playlist is None

    def test_successful_translation(self, sp_track_mock, sp_playlist_mock):
        track = translator.to_track(sp_track_mock)
        playlist = translator.to_playlist(sp_playlist_mock)

        assert playlist.uri == 'spotify:playlist:alice:foo'
        assert playlist.name == 'Foo'
        assert playlist.length == 1
        assert track in playlist.tracks
        assert playlist.last_modified is None

    def test_adds_name_for_starred_playlists(self, sp_playlist_mock):
        sp_playlist_mock.name = None

        playlist = translator.to_playlist(sp_playlist_mock)

        assert playlist.name == 'Starred'

    def test_includes_by_owner_in_name_if_owned_by_another_user(
            self, sp_playlist_mock, sp_user_mock):
        sp_user_mock.canonical_name = 'bob'
        sp_playlist_mock.user = sp_user_mock

        playlist = translator.to_playlist(sp_playlist_mock, username='alice')

        assert playlist.name == 'Foo by bob'

    def test_includes_folders_in_name(self, sp_playlist_mock):
        playlist = translator.to_playlist(
            sp_playlist_mock, folders=['Bar', 'Baz'])

        assert playlist.name == 'Bar/Baz/Foo'

    def test_filters_out_none_tracks(self, sp_track_mock, sp_playlist_mock):
        sp_track_mock.is_loaded = False

        playlist = translator.to_playlist(sp_playlist_mock)

        assert playlist.length == 0
        assert list(playlist.tracks) == []
