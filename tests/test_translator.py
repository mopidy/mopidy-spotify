from __future__ import unicode_literals

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

    def test_caches_results(self, sp_artist_mock):
        artist1 = translator.to_artist(sp_artist_mock)
        artist2 = translator.to_artist(sp_artist_mock)

        assert artist1 is artist2

    def test_does_not_cache_none_results(self, sp_artist_mock):
        sp_artist_mock.is_loaded = False
        artist1 = translator.to_artist(sp_artist_mock)

        sp_artist_mock.is_loaded = True
        artist2 = translator.to_artist(sp_artist_mock)

        assert artist1 is None
        assert artist2 is not None


class TestToArtistRef(object):

    def test_returns_none_if_unloaded(self, sp_artist_mock):
        sp_artist_mock.is_loaded = False

        ref = translator.to_artist_ref(sp_artist_mock)

        assert ref is None

    def test_successful_translation(self, sp_artist_mock):
        ref = translator.to_artist_ref(sp_artist_mock)

        assert ref.type == 'artist'
        assert ref.uri == 'spotify:artist:abba'
        assert ref.name == 'ABBA'

    def test_caches_results(self, sp_artist_mock):
        ref1 = translator.to_artist_ref(sp_artist_mock)
        ref2 = translator.to_artist_ref(sp_artist_mock)

        assert ref1 is ref2


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

    def test_returns_unknown_date_if_year_is_zero(self, sp_album_mock):
        sp_album_mock.year = 0

        album = translator.to_album(sp_album_mock)

        assert album.date is None

    def test_caches_results(self, sp_album_mock):
        album1 = translator.to_album(sp_album_mock)
        album2 = translator.to_album(sp_album_mock)

        assert album1 is album2


class TestToAlbumRef(object):

    def test_returns_none_if_unloaded(self, sp_album_mock):
        sp_album_mock.is_loaded = False

        ref = translator.to_album_ref(sp_album_mock)

        assert ref is None

    def test_successful_translation(self, sp_album_mock):
        ref = translator.to_album_ref(sp_album_mock)

        assert ref.type == 'album'
        assert ref.uri == 'spotify:album:def'
        assert ref.name == 'ABBA - DEF 456'

    def test_if_artist_is_none(self, sp_album_mock):
        sp_album_mock.artist = None

        ref = translator.to_album_ref(sp_album_mock)

        assert ref.name == 'DEF 456'

    def test_if_artist_is_not_loaded(self, sp_album_mock):
        sp_album_mock.artist.is_loaded = False

        ref = translator.to_album_ref(sp_album_mock)

        assert ref.name == 'DEF 456'

    def test_caches_results(self, sp_album_mock):
        ref1 = translator.to_album_ref(sp_album_mock)
        ref2 = translator.to_album_ref(sp_album_mock)

        assert ref1 is ref2


class TestToTrack(object):

    def test_returns_none_if_unloaded(self, sp_track_mock):
        sp_track_mock.is_loaded = False

        track = translator.to_track(sp_track_mock)

        assert track is None

    def test_returns_none_if_error(self, sp_track_mock, caplog):
        sp_track_mock.error = spotify.ErrorType.OTHER_PERMANENT

        track = translator.to_track(sp_track_mock)

        assert track is None
        assert (
            'Error loading spotify:track:abc: <ErrorType.OTHER_PERMANENT: 10>'
            in caplog.text())

    def test_returns_none_if_not_available(self, sp_track_mock):
        sp_track_mock.availability = spotify.TrackAvailability.UNAVAILABLE

        track = translator.to_track(sp_track_mock)

        assert track is None

    def test_successful_translation(self, sp_track_mock):
        track = translator.to_track(sp_track_mock, bitrate=320)

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
        assert track.track_no == 7
        assert track.disc_no == 1
        assert track.date == '2001'
        assert track.length == 174300
        assert track.bitrate == 320

    def test_filters_out_none_artists(self, sp_artist_mock, sp_track_mock):
        sp_artist_mock.is_loaded = False

        track = translator.to_track(sp_track_mock)

        assert list(track.artists) == []

    def test_caches_results(self, sp_track_mock):
        track1 = translator.to_track(sp_track_mock)
        track2 = translator.to_track(sp_track_mock)

        assert track1 is track2


class TestToTrackRef(object):

    def test_returns_none_if_unloaded(self, sp_track_mock):
        sp_track_mock.is_loaded = False

        ref = translator.to_track_ref(sp_track_mock)

        assert ref is None

    def test_returns_none_if_error(self, sp_track_mock, caplog):
        sp_track_mock.error = spotify.ErrorType.OTHER_PERMANENT

        ref = translator.to_track_ref(sp_track_mock)

        assert ref is None
        assert (
            'Error loading spotify:track:abc: <ErrorType.OTHER_PERMANENT: 10>'
            in caplog.text())

    def test_returns_none_if_not_available(self, sp_track_mock):
        sp_track_mock.availability = spotify.TrackAvailability.UNAVAILABLE

        ref = translator.to_track_ref(sp_track_mock)

        assert ref is None

    def test_successful_translation(self, sp_track_mock):
        ref = translator.to_track_ref(sp_track_mock)

        assert ref.type == models.Ref.TRACK
        assert ref.uri == 'spotify:track:abc'
        assert ref.name == 'ABC 123'

    def test_caches_results(self, sp_track_mock):
        ref1 = translator.to_track_ref(sp_track_mock)
        ref2 = translator.to_track_ref(sp_track_mock)

        assert ref1 is ref2


class TestSpotifySearchQuery(object):

    def test_any_maps_to_no_field(self):
        query = translator.sp_search_query({'any': ['ABC', 'DEF']})

        assert query == '"ABC" "DEF"'

    def test_artist_maps_to_artist(self):
        query = translator.sp_search_query({'artist': ['ABBA', 'ACDC']})

        assert query == 'artist:"ABBA" artist:"ACDC"'

    def test_albumartist_maps_to_artist(self):
        # We don't know how to filter by albumartist in Spotify

        query = translator.sp_search_query({'albumartist': ['ABBA', 'ACDC']})

        assert query == 'artist:"ABBA" artist:"ACDC"'

    def test_album_maps_to_album(self):
        query = translator.sp_search_query({'album': ['Greatest Hits']})

        assert query == 'album:"Greatest Hits"'

    def test_track_name_maps_to_track(self):
        query = translator.sp_search_query({'track_name': ['ABC']})

        assert query == 'track:"ABC"'

    def test_track_number_is_not_supported(self):
        # We don't know how to filter by track number in Spotify

        query = translator.sp_search_query({'track_number': ['10']})

        assert query == ''

    def test_date_maps_to_year(self):
        query = translator.sp_search_query({'date': ['1970']})

        assert query == 'year:1970'

    def test_date_is_transformed_to_just_the_year(self):
        query = translator.sp_search_query({'date': ['1970-02-01']})

        assert query == 'year:1970'

    def test_date_is_ignored_if_not_parseable(self, caplog):
        query = translator.sp_search_query({'date': ['abc']})

        assert query == ''
        assert (
            'Excluded year from search query: Cannot parse date "abc"'
            in caplog.text())

    def test_anything_can_be_combined(self):
        query = translator.sp_search_query({
            'any': ['ABC', 'DEF'],
            'artist': ['ABBA'],
            'album': ['Greatest Hits'],
            'track_name': ['Dancing Queen'],
            'year': ['1970-01-02'],
        })

        assert '"ABC"' in query
        assert '"DEF"' in query
        assert 'artist:"ABBA"' in query
        assert 'album:"Greatest Hits"' in query
        assert 'track:"Dancing Queen"' in query
        assert 'year:1970' in query


class TestWebToArtist(object):

    def test_successful_translation(self, web_artist_mock):
        artist = translator.web_to_artist(web_artist_mock)

        assert artist.uri == 'spotify:artist:abba'
        assert artist.name == 'ABBA'


class TestWebToAlbum(object):

    def test_successful_translation(self, web_album_mock):
        album = translator.web_to_album(web_album_mock)

        artists = [models.Artist(uri='spotify:artist:abba', name='ABBA')]

        assert album.uri == 'spotify:album:def'
        assert album.name == 'DEF 456'
        assert list(album.artists) == artists


class TestWebToTrack(object):

    def test_successful_translation(self, web_track_mock):
        track = translator.web_to_track(web_track_mock)

        artists = [models.Artist(uri='spotify:artist:abba', name='ABBA')]

        assert track.uri == 'spotify:track:abc'
        assert track.name == 'ABC 123'
        assert list(track.artists) == artists
        assert track.album == models.Album(
            uri='spotify:album:def',
            name='DEF 456',
            artists=artists)
        assert track.track_no == 7
        assert track.disc_no == 1
        assert track.length == 174300


class TestWebToPlaylistRef(object):
    def test_successful_translation(
            self, web_playlist_mock):
        playlist = translator.web_to_playlist_ref(web_playlist_mock)

        assert playlist.uri == 'spotify:user:alice:playlist:foo'
        assert playlist.name == 'Foo'


class TestWebToPlaylist(object):
    def test_successful_translation_with_tracks(
            self, web_playlist_mock, web_track_mock):
        playlist = translator.web_to_playlist(
            web_playlist_mock, web_tracks=[{"track": web_track_mock}])

        assert playlist.uri == 'spotify:user:alice:playlist:foo'
        assert playlist.name == 'Foo'
        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].name == 'ABC 123'
        assert playlist.tracks[0].uri == 'spotify:track:abc'

    def test_successful_translation_without_tracks(
            self, web_playlist_mock):
        playlist = translator.web_to_playlist(web_playlist_mock)

        assert playlist.uri == 'spotify:user:alice:playlist:foo'
        assert playlist.name == 'Foo'
        assert len(playlist.tracks) == 0
