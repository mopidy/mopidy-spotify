from __future__ import unicode_literals

import mock

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
        assert track.length == 174300
        assert track.track_no == 7


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
