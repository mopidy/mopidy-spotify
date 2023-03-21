import pytest
from mopidy import models
from unittest import mock
from unittest.mock import patch, sentinel

from mopidy_spotify import translator


class TestWebToArtistRef:
    @pytest.mark.parametrize(
        "web_data",
        [
            ({}),
            ({"type": "artist"}),
            ({"uri": "spotify:artist:abba", "type": "track"}),
        ],
    )
    def test_returns_none_if_bad_data(self, web_data):
        assert translator.web_to_artist_ref(web_data) is None

    def test_successful_translation(self, web_artist_mock):
        ref = translator.web_to_artist_ref(web_artist_mock)

        assert ref.type == "artist"
        assert ref.uri == "spotify:artist:abba"
        assert ref.name == "ABBA"

    def test_without_name_uses_uri(self, web_artist_mock):
        del web_artist_mock["name"]

        ref = translator.web_to_artist_ref(web_artist_mock)

        assert ref.name == "spotify:artist:abba"


class TestWebToArtistRefs:
    def test_bad_artists_filtered(self, web_artist_mock, web_track_mock):
        refs = list(
            translator.web_to_artist_refs([{}, web_artist_mock, web_track_mock])
        )

        assert len(refs) == 1

        assert refs[0].type == "artist"
        assert refs[0].uri == "spotify:artist:abba"
        assert refs[0].name == "ABBA"


class TestValidWebData(object):
    def test_returns_false_if_none(self):
        assert translator.valid_web_data(None, "track") is False

    def test_returns_false_if_empty(self):
        assert translator.valid_web_data({}, "track") is False

    def test_returns_false_if_missing_type(self, web_track_mock):
        del web_track_mock["type"]
        assert translator.valid_web_data(web_track_mock, "track") is False

    def test_returns_false_if_wrong_type(self, web_track_mock):
        assert translator.valid_web_data(web_track_mock, "playlist") is False

    def test_returns_false_if_missing_uri(self, web_track_mock):
        del web_track_mock["uri"]
        assert translator.valid_web_data(web_track_mock, "track") is False

    def test_return_false_if_uri_none(self, web_track_mock):
        web_track_mock["uri"] = None
        assert translator.valid_web_data(web_track_mock, "track") is False

    def test_returns_success(self, web_track_mock):
        assert translator.valid_web_data(web_track_mock, "track") is True


class TestWebToAlbumRef:
    def test_returns_none_if_invalid(self, web_album_mock):
        with patch.object(translator, "valid_web_data", return_value=False):
            assert translator.web_to_album_ref(web_album_mock) is None

    def test_returns_none_if_wrong_type(self, web_album_mock):
        web_album_mock["type"] = "playlist"

        assert translator.web_to_album_ref(web_album_mock) is None

    def test_successful_translation(self, web_album_mock):
        ref = translator.web_to_album_ref(web_album_mock)

        assert ref.type == models.Ref.ALBUM
        assert ref.uri == "spotify:album:def"
        assert ref.name == "ABBA - DEF 456"

    def test_without_artists_uses_name(self, web_album_mock):
        del web_album_mock["artists"]

        ref = translator.web_to_album_ref(web_album_mock)

        assert ref.name == "DEF 456"

    def test_without_name_uses_uri(self, web_album_mock):
        del web_album_mock["name"]

        ref = translator.web_to_album_ref(web_album_mock)

        assert ref.name == "spotify:album:def"


class TestWebToAlbumRefs:
    def test_returns_albums(self, web_album_mock):
        web_albums = [{"album": web_album_mock}] * 3
        refs = list(translator.web_to_album_refs(web_albums))

        assert refs == [refs[0], refs[0], refs[0]]

        assert refs[0].type == models.Ref.ALBUM
        assert refs[0].uri == "spotify:album:def"
        assert refs[0].name == "ABBA - DEF 456"

    def test_returns_bare_albums(self, web_album_mock):
        web_albums = [web_album_mock] * 3
        refs = list(translator.web_to_album_refs(web_albums))

        assert refs == [refs[0], refs[0], refs[0]]

        assert refs[0].type == models.Ref.ALBUM
        assert refs[0].uri == "spotify:album:def"
        assert refs[0].name == "ABBA - DEF 456"

    def test_bad_albums_filtered(self, web_album_mock, web_artist_mock):
        refs = list(
            translator.web_to_album_refs([{}, web_album_mock, web_artist_mock])
        )

        assert len(refs) == 1

        assert refs[0].type == models.Ref.ALBUM
        assert refs[0].uri == "spotify:album:def"


class TestWebToTrackRef:
    def test_returns_none_if_invalid(self, web_track_mock):
        with patch.object(translator, "valid_web_data", return_value=False):
            assert translator.web_to_track_ref(web_track_mock) is None

    def test_returns_none_if_wrong_type(self, web_track_mock):
        web_track_mock["type"] = "playlist"

        assert translator.web_to_track_ref(web_track_mock) is None

    def test_returns_none_if_not_playable(self, web_track_mock, caplog):
        web_track_mock["is_playable"] = False

        ref = translator.web_to_track_ref(web_track_mock)

        assert ref is None
        assert "'spotify:track:abc' is not playable" in caplog.text

    def test_ignore_missing_is_playable(self, web_track_mock):
        del web_track_mock["is_playable"]

        ref = translator.web_to_track_ref(web_track_mock, check_playable=False)

        assert ref.type == models.Ref.TRACK
        assert ref.uri == "spotify:track:abc"
        assert ref.name == "ABC 123"

    def test_successful_translation(self, web_track_mock):
        ref = translator.web_to_track_ref(web_track_mock)

        assert ref.type == models.Ref.TRACK
        assert ref.uri == "spotify:track:abc"
        assert ref.name == "ABC 123"

    def test_without_name_uses_uri(self, web_track_mock):
        del web_track_mock["name"]

        ref = translator.web_to_track_ref(web_track_mock)

        assert ref.name == "spotify:track:abc"

    def test_uri_uses_relinked_from_uri(self, web_track_mock):
        web_track_mock["linked_from"] = {"uri": "spotify:track:xyz"}

        ref = translator.web_to_track_ref(web_track_mock)

        assert ref.uri == "spotify:track:xyz"


class TestWebToTrackRefs:
    def test_returns_playlist_tracks(self, web_track_mock):
        web_tracks = [{"track": web_track_mock}] * 3
        refs = list(translator.web_to_track_refs(web_tracks))

        assert refs == [refs[0], refs[0], refs[0]]

        assert refs[0].type == models.Ref.TRACK
        assert refs[0].uri == "spotify:track:abc"
        assert refs[0].name == "ABC 123"

    def test_returns_top_list_tracks(self, web_track_mock):
        web_tracks = [web_track_mock] * 3
        refs = list(translator.web_to_track_refs(web_tracks))

        assert refs == [refs[0], refs[0], refs[0]]

        assert refs[0].type == models.Ref.TRACK
        assert refs[0].uri == "spotify:track:abc"
        assert refs[0].name == "ABC 123"

    def test_bad_tracks_filtered(self, web_artist_mock, web_track_mock):
        refs = list(
            translator.web_to_track_refs([{}, web_track_mock, web_artist_mock])
        )

        assert len(refs) == 1

        assert refs[0].type == models.Ref.TRACK
        assert refs[0].uri == "spotify:track:abc"

    def test_check_playable_default(self, web_track_mock):
        del web_track_mock["is_playable"]
        refs = list(translator.web_to_track_refs([web_track_mock]))

        assert refs == []

    def test_dont_check_playable(self, web_track_mock):
        del web_track_mock["is_playable"]
        refs = list(
            translator.web_to_track_refs([web_track_mock], check_playable=False)
        )

        assert len(refs) == 1

        assert refs[0].type == models.Ref.TRACK
        assert refs[0].uri == "spotify:track:abc"


class TestToPlaylist:
    def test_calls_to_playlist_ref(self, web_playlist_mock):
        ref_mock = mock.Mock(spec=models.Ref.playlist)
        ref_mock.uri = str(sentinel.uri)
        ref_mock.name = str(sentinel.name)

        with patch.object(
            translator, "to_playlist_ref", return_value=ref_mock
        ) as ref_func_mock:
            playlist = translator.to_playlist(web_playlist_mock)
            ref_func_mock.assert_called_once_with(web_playlist_mock, mock.ANY)

        assert playlist.uri == str(sentinel.uri)
        assert playlist.name == str(sentinel.name)

    def test_returns_none_if_invalid_ref(self, web_playlist_mock):
        with patch.object(translator, "to_playlist_ref", return_value=None):
            assert translator.to_playlist(web_playlist_mock) is None

    def test_successful_translation(self, web_track_mock, web_playlist_mock):
        track = translator.web_to_track(web_track_mock)
        playlist = translator.to_playlist(web_playlist_mock)

        assert playlist.uri == "spotify:user:alice:playlist:foo"
        assert playlist.name == "Foo"
        assert playlist.length == 1
        assert track in playlist.tracks
        assert playlist.last_modified is None

    def test_no_track_data(self, web_playlist_mock):
        del web_playlist_mock["tracks"]

        playlist = translator.to_playlist(web_playlist_mock)

        assert playlist.uri == "spotify:user:alice:playlist:foo"
        assert playlist.name == "Foo"
        assert playlist.length == 0

    def test_as_items(self, web_track_mock, web_playlist_mock):
        track_ref = translator.web_to_track_ref(web_track_mock)
        items = translator.to_playlist(web_playlist_mock, as_items=True)

        assert track_ref in items

    def test_as_items_no_track_data(self, web_playlist_mock):
        del web_playlist_mock["tracks"]

        items = translator.to_playlist(web_playlist_mock, as_items=True)

        assert len(items) == 0

    def test_filters_out_none_tracks(self, web_track_mock, web_playlist_mock):
        del web_track_mock["type"]

        playlist = translator.to_playlist(web_playlist_mock)

        assert playlist.length == 0
        assert list(playlist.tracks) == []


class TestToPlaylistRef:
    def test_returns_none_if_invalid(self, web_playlist_mock):
        with patch.object(translator, "valid_web_data", return_value=False):
            assert translator.to_playlist_ref(web_playlist_mock) is None

    def test_returns_none_if_wrong_type(self, web_playlist_mock):
        web_playlist_mock["type"] = "track"

        ref = translator.to_playlist_ref(web_playlist_mock)

        assert ref is None

    def test_successful_translation(self, web_playlist_mock):
        ref = translator.to_playlist_ref(web_playlist_mock)

        assert ref.uri == "spotify:user:alice:playlist:foo"
        assert ref.name == "Foo"

    def test_without_name_uses_uri(self, web_playlist_mock):
        del web_playlist_mock["name"]

        ref = translator.to_playlist_ref(web_playlist_mock)

        assert ref.name == "spotify:user:alice:playlist:foo"

    def test_success_without_track_data(self, web_playlist_mock):
        del web_playlist_mock["tracks"]

        ref = translator.to_playlist_ref(web_playlist_mock)

        assert ref.uri == "spotify:user:alice:playlist:foo"
        assert ref.name == "Foo"

    def test_includes_by_owner_in_name_if_owned_by_another_user(
        self, web_playlist_mock
    ):
        web_playlist_mock["owner"]["id"] = "bob"

        ref = translator.to_playlist_ref(web_playlist_mock, username="alice")

        assert ref.name == "Foo (by bob)"


class TestToPlaylistRefs:
    def test_returns_playlist_refs(self, web_playlist_mock):
        web_playlists = [web_playlist_mock] * 3
        refs = list(translator.to_playlist_refs(web_playlists))

        assert refs == [refs[0], refs[0], refs[0]]

        assert refs[0].type == models.Ref.PLAYLIST
        assert refs[0].uri == "spotify:user:alice:playlist:foo"
        assert refs[0].name == "Foo"

    def test_bad_playlist_filtered(self, web_playlist_mock):
        refs = list(
            translator.to_playlist_refs([{}, web_playlist_mock, {"foo": 1}])
        )

        assert len(refs) == 1

        assert refs[0].type == models.Ref.PLAYLIST
        assert refs[0].uri == "spotify:user:alice:playlist:foo"

    def test_passes_username(self, web_playlist_mock):
        refs = list(translator.to_playlist_refs([web_playlist_mock], "bob"))

        assert refs[0].name == "Foo (by alice)"


class TestSpotifySearchQuery:
    def test_any_maps_to_no_field(self):
        query = translator.sp_search_query({"any": ["ABC", "DEF"]})

        assert query == "ABC DEF"

    def test_any_maps_to_no_field_exact(self):
        query = translator.sp_search_query({"any": ["ABC", "DEF"]}, exact=True)

        assert query == '"ABC" "DEF"'

    def test_artist_maps_to_artist(self):
        query = translator.sp_search_query({"artist": ["ABBA", "ACDC"]})

        assert query == "artist:ABBA artist:ACDC"

    def test_artist_maps_to_artist_exact(self):
        query = translator.sp_search_query(
            {"artist": ["ABBA", "ACDC"]}, exact=True
        )

        assert query == 'artist:"ABBA" artist:"ACDC"'

    def test_albumartist_maps_to_artist(self):
        # We don't know how to filter by albumartist in Spotify

        query = translator.sp_search_query({"albumartist": ["ABBA", "ACDC"]})

        assert query == "artist:ABBA artist:ACDC"

    def test_albumartist_maps_to_artist_exact(self):
        # We don't know how to filter by albumartist in Spotify

        query = translator.sp_search_query(
            {"albumartist": ["ABBA", "ACDC"]}, exact=True
        )

        assert query == 'artist:"ABBA" artist:"ACDC"'

    def test_album_maps_to_album(self):
        query = translator.sp_search_query({"album": ["Greatest Hits"]})

        assert query == "album:Greatest album:Hits"

    def test_album_maps_to_album_exact(self):
        query = translator.sp_search_query(
            {"album": ["Greatest Hits"]}, exact=True
        )

        assert query == 'album:"Greatest Hits"'

    def test_track_name_maps_to_track(self):
        query = translator.sp_search_query({"track_name": ["ABC"]})

        assert query == "track:ABC"

    def test_track_name_maps_to_track_exact(self):
        query = translator.sp_search_query({"track_name": ["ABC"]}, exact=True)

        assert query == 'track:"ABC"'

    def test_track_number_is_not_supported(self):
        # We don't know how to filter by track number in Spotify

        query = translator.sp_search_query({"track_number": ["10"]})

        assert query == ""

    def test_date_maps_to_year(self):
        query = translator.sp_search_query({"date": ["1970"]})

        assert query == "year:1970"

    def test_date_is_transformed_to_just_the_year(self):
        query = translator.sp_search_query({"date": ["1970-02-01"]})

        assert query == "year:1970"

    def test_date_is_ignored_if_not_parseable(self, caplog):
        query = translator.sp_search_query({"date": ["abc"]})

        assert query == ""
        assert (
            'Excluded year from search query: Cannot parse date "abc"'
            in caplog.text
        )

    def test_anything_can_be_combined(self):
        query = translator.sp_search_query(
            {
                "any": ["ABC", "DEF"],
                "artist": ["ABBA"],
                "album": ["Greatest Hits"],
                "track_name": ["Dancing Queen"],
                "year": ["1970-01-02"],
            }
        )

        assert "ABC" in query
        assert "DEF" in query
        assert "artist:ABBA" in query
        assert "album:Greatest album:Hits" in query
        assert "track:Dancing track:Queen" in query
        assert "year:1970" in query

    def test_anything_can_be_combined_exact(self):
        query = translator.sp_search_query(
            {
                "any": ["ABC", "DEF"],
                "artist": ["ABBA"],
                "album": ["Greatest Hits"],
                "track_name": ["Dancing Queen"],
                "year": ["1970-01-02"],
            },
            exact=True,
        )

        assert '"ABC"' in query
        assert '"DEF"' in query
        assert 'artist:"ABBA"' in query
        assert 'album:"Greatest Hits"' in query
        assert 'track:"Dancing Queen"' in query
        assert "year:1970" in query


class TestWebToArtist:
    def test_calls_web_to_artist_ref(self, web_artist_mock):
        ref_mock = mock.Mock(spec=models.Ref.artist)
        ref_mock.uri = str(sentinel.uri)
        ref_mock.name = str(sentinel.name)

        with patch.object(
            translator, "web_to_artist_ref", return_value=ref_mock
        ) as ref_func_mock:
            artist = translator.web_to_artist(web_artist_mock)
            ref_func_mock.assert_called_once_with(web_artist_mock)

        assert artist.uri == str(sentinel.uri)
        assert artist.name == str(sentinel.name)

    def test_returns_none_if_invalid_ref(self, web_artist_mock):
        with patch.object(translator, "web_to_artist_ref", return_value=None):
            assert translator.to_playlist(web_artist_mock) is None

    def test_successful_translation(self, web_artist_mock):
        artist = translator.web_to_artist(web_artist_mock)

        assert artist.uri == "spotify:artist:abba"
        assert artist.name == "ABBA"


class TestWebToAlbum:
    def test_calls_web_to_album_ref(self, web_album_mock):
        ref_mock = mock.Mock(spec=models.Ref.album)
        ref_mock.uri = str(sentinel.uri)
        ref_mock.name = str(sentinel.name)

        with patch.object(
            translator, "web_to_album_ref", return_value=ref_mock
        ) as ref_func_mock:
            album = translator.web_to_album(web_album_mock)
            ref_func_mock.assert_called_once_with(web_album_mock)

        assert album.uri == str(sentinel.uri)
        assert album.name == "DEF 456"

    def test_returns_none_if_invalid_ref(self, web_album_mock):
        with patch.object(translator, "web_to_album_ref", return_value=None):
            assert translator.web_to_album(web_album_mock) is None

    def test_successful_translation(self, web_album_mock):
        album = translator.web_to_album(web_album_mock)

        artists = [models.Artist(uri="spotify:artist:abba", name="ABBA")]

        assert album.uri == "spotify:album:def"
        assert album.name == "DEF 456"
        assert list(album.artists) == artists

    def test_ignores_invalid_artists(self, web_album_mock, web_artist_mock):
        invalid_artist1 = {"name": "FOO", "uri": None, "type": "artist"}
        invalid_artist2 = {"name": "BAR", "type": "football"}
        web_album_mock["artists"] = [
            invalid_artist1,
            web_artist_mock,
            invalid_artist2,
        ]
        album = translator.web_to_album(web_album_mock)

        artists = [models.Artist(uri="spotify:artist:abba", name="ABBA")]

        assert album.uri == "spotify:album:def"
        assert album.name == "DEF 456"
        assert list(album.artists) == artists

    def test_returns_empty_artists_list_if_artist_is_empty(
        self, web_album_mock
    ):
        web_album_mock["artists"] = []

        album = translator.web_to_album(web_album_mock)

        assert list(album.artists) == []

    def test_caches_results(self, web_album_mock):
        album1 = translator.web_to_album(web_album_mock)
        album2 = translator.web_to_album(web_album_mock)

        assert album1 is album2

    def test_web_to_album_tracks(self, web_album_mock):
        tracks = translator.web_to_album_tracks(web_album_mock)

        assert len(tracks) == 10
        track = tracks[0]
        assert track.album.name == "DEF 456"
        assert track.album.artists == track.artists

    def test_web_to_album_tracks_empty(self, web_album_mock):
        web_album_mock["tracks"]["items"] = []

        tracks = translator.web_to_album_tracks(web_album_mock)

        assert len(tracks) == 0

    def test_web_to_album_tracks_unplayable(self, web_album_mock):
        web_album_mock["is_playable"] = False

        tracks = translator.web_to_album_tracks(web_album_mock)

        assert len(tracks) == 0

    def test_web_to_album_tracks_nolist(self, web_album_mock):
        web_album_mock["tracks"] = {"items": {}}

        tracks = translator.web_to_album_tracks(web_album_mock)

        assert isinstance(tracks, list)
        assert len(tracks) == 0

    def test_web_to_album_tracks_none(self):
        tracks = translator.web_to_album_tracks(None)

        assert isinstance(tracks, list)
        assert len(tracks) == 0


class TestWebToTrack:
    def test_calls_web_to_track_ref(self, web_track_mock):
        ref_mock = mock.Mock(spec=models.Ref.track)
        ref_mock.uri = str(sentinel.uri)
        ref_mock.name = str(sentinel.name)

        with patch.object(
            translator, "web_to_track_ref", return_value=ref_mock
        ) as ref_func_mock:
            track = translator.web_to_track(web_track_mock)
            ref_func_mock.assert_called_once_with(web_track_mock)

        assert track.uri == str(sentinel.uri)
        assert track.name == str(sentinel.name)

    def test_returns_none_if_invalid_ref(self, web_track_mock):
        with patch.object(translator, "web_to_track_ref", return_value=None):
            assert translator.web_to_track(web_track_mock) is None

    def test_successful_translation(self, web_track_mock):
        track = translator.web_to_track(web_track_mock)

        artists = [models.Artist(uri="spotify:artist:abba", name="ABBA")]

        assert track.uri == "spotify:track:abc"
        assert track.name == "ABC 123"
        assert list(track.artists) == artists
        assert track.album == models.Album(
            uri="spotify:album:def", name="DEF 456", artists=artists
        )
        assert track.track_no == 7
        assert track.disc_no == 1
        assert track.length == 174300

    def test_sets_bitrate(self, web_track_mock):
        track = translator.web_to_track(web_track_mock, bitrate=100)

        assert track.bitrate == 100

    def test_sets_specified_album(self, web_track_mock):
        alt_album = models.Album(uri="spotify:album:xyz", name="XYZ 789")

        track = translator.web_to_track(web_track_mock, album=alt_album)

        assert track.album.uri == "spotify:album:xyz"
        assert track.album.name == "XYZ 789"

    def test_filters_out_none_artists(self, web_track_mock):
        web_track_mock["artists"].insert(0, {})
        web_track_mock["artists"].insert(0, {"foo": "bar"})

        track = translator.web_to_track(web_track_mock)
        artists = [models.Artist(uri="spotify:artist:abba", name="ABBA")]

        assert list(track.artists) == artists

    def test_ignores_missing_album(self, web_track_mock):
        del web_track_mock["album"]

        track = translator.web_to_track(web_track_mock)

        assert track.name == "ABC 123"
        assert track.length == 174300
        assert track.album is None

    def test_ignores_invalid_album(self, web_track_mock):
        web_track_mock["album"]["uri"] = None

        track = translator.web_to_track(web_track_mock)

        assert track.name == "ABC 123"
        assert track.album is None
