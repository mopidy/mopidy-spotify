import copy
from unittest import mock

import mopidy
import pytest

from mopidy_spotify import lookup


@pytest.fixture(autouse=True)
def clear_cache():
    return lookup._cache.clear()


@pytest.mark.parametrize(
    "uri,",
    [
        ("invalid"),
        ("spotify:playlist"),
        ("spotify:invalid:something"),
        ("spotify:your:tracks:invalid"),
    ],
)
def test_lookup_of_invalid_uri(provider, caplog, uri):
    results = provider.lookup_many([uri])

    assert len(results) == 0
    assert f"Could not parse '{uri}' as a Spotify URI" in caplog.text


def test_lookup_of_invalid_your_uri(provider, caplog):
    results = provider.lookup_many(["spotify:your:artists"])

    assert len(results) == 0
    assert "Your type 'artists' is not supported" in caplog.text


def test_lookup_of_unknown_track_uri(
    web_client_mock, provider, web_track_mock_link, caplog
):
    web_client_mock.get_batch.return_value = [(web_track_mock_link, {})]

    results = provider.lookup_many(["spotify:track:abc"])

    web_client_mock.get_batch.assert_called_once()
    assert len(results) == 1
    assert len(results["spotify:track:abc"]) == 0
    assert "Track 'spotify:track:abc' not found" in caplog.text


def test_lookup_when_offline(web_client_mock, provider, caplog):
    web_client_mock.logged_in = False

    results = provider.lookup_many(["spotify:invalid:something"])

    assert len(results) == 0
    assert "Not logged in" in caplog.text


def test_lookup_of_track_uri(
    web_client_mock, web_track_mock, web_track_mock_link, provider
):
    web_client_mock.get_batch.return_value = [(web_track_mock_link, web_track_mock)]

    results = provider.lookup_many(["spotify:track:abc"])

    web_client_mock.get_batch.assert_called_once()
    assert len(results) == 1
    track = results["spotify:track:abc"][0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160
    assert track.album.name == "DEF 456"


def test_lookup_of_album_uri(
    web_client_mock, web_album_mock, web_album_mock_link, provider
):
    web_client_mock.get_batch.return_value = [(web_album_mock_link, web_album_mock)]

    results = provider.lookup_many(["spotify:album:def"])

    web_client_mock.get_batch.assert_called_once()
    assert len(results) == 1
    assert len(results["spotify:album:def"]) == 10
    track = results["spotify:album:def"][0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160
    assert track.album.name == "DEF 456"


def test_lookup_of_album_uri_empty_response(
    web_client_mock, web_album_mock_link, provider, caplog
):
    web_client_mock.get_batch.return_value = [(web_album_mock_link, {})]

    results = provider.lookup_many(["spotify:album:def"])

    web_client_mock.get_batch.assert_called_once()
    assert len(results) == 1
    assert len(results["spotify:album:def"]) == 0


def test_lookup_of_artist_uri(
    web_track_mock, web_album_mock, web_client_mock, provider
):
    web_track_mock2 = copy.deepcopy(web_track_mock)
    web_track_mock2["name"] = "XYZ track"
    web_album_mock2 = copy.deepcopy(web_album_mock)
    web_album_mock2["name"] = "XYZ album"
    web_album_mock2["tracks"]["items"] = [web_track_mock2] * 3

    web_client_mock.get_artist_albums.return_value = [
        web_album_mock,
        web_album_mock2,
    ]
    results = provider.lookup_many(["spotify:artist:abba"])

    assert len(results) == 1
    assert len(results["spotify:artist:abba"]) == 13

    track = results["spotify:artist:abba"][0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.album.name == "DEF 456"
    assert track.bitrate == 160

    track = results["spotify:artist:abba"][10]
    assert track.uri == "spotify:track:abc"
    assert track.name == "XYZ track"
    assert track.album.name == "XYZ album"
    assert track.bitrate == 160


def test_lookup_of_artist_ignores_unavailable_albums(
    web_client_mock, web_album_mock, web_album_mock2, provider
):
    web_album_mock["is_playable"] = False
    web_client_mock.get_artist_albums.return_value = [
        web_album_mock,
        web_album_mock2,
    ]

    results = provider.lookup_many(["spotify:artist:abba"])

    assert len(results) == 1
    assert len(results["spotify:artist:abba"]) == 2


def test_lookup_of_artist_uri_ignores_compilations(
    web_client_mock, web_album_mock, provider
):
    web_album_mock["album_type"] = "compilation"
    web_client_mock.get_artist_albums.return_value = [web_album_mock]

    results = provider.lookup_many(["spotify:artist:abba"])

    assert len(results) == 1
    assert len(results["spotify:artist:abba"]) == 0


def test_lookup_of_artist_uri_ignores_various_artists_albums(
    web_client_mock, web_album_mock, provider
):
    web_album_mock["artists"][0]["uri"] = "spotify:artist:0LyfQWJT6nXafLPZqxe9Of"
    web_client_mock.get_artist_albums.return_value = [web_album_mock]

    results = provider.lookup_many(["spotify:artist:abba"])

    assert len(results) == 1
    assert len(results["spotify:artist:abba"]) == 0


def test_lookup_of_playlist_uri(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    playlist_uri = web_playlist_mock["uri"]
    results = provider.lookup_many([playlist_uri])

    web_client_mock.get_playlist.assert_called_once_with(playlist_uri)

    assert len(results) == 1
    track = results[playlist_uri][0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_lookup_of_playlist_uri_empty_response(
    web_client_mock, web_playlist_mock, provider, caplog
):
    web_client_mock.get_playlist.return_value = None

    playlist_uri = web_playlist_mock["uri"]
    results = provider.lookup_many([playlist_uri])

    assert len(results) == 0
    assert f"Playlist '{playlist_uri}' not found" in caplog.text


def test_lookup_of_yourtracks_uri(web_client_mock, web_track_mock, provider):
    web_saved_track_mock = {"track": web_track_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_track_mock, web_saved_track_mock]},
        {"items": [web_saved_track_mock, web_saved_track_mock]},
    ]

    results = provider.lookup_many(["spotify:your:tracks"])

    web_client_mock.get_all.assert_called_once()
    assert len(results) == 1
    assert len(results["spotify:your:tracks"]) == 4
    for track in results["spotify:your:tracks"]:
        assert track.uri == "spotify:track:abc"
        assert track.name == "ABC 123"
        assert track.bitrate == 160
        assert track.album.name == "DEF 456"

    assert results == provider.lookup_many(["spotify:your:tracks"])
    assert web_client_mock.get_all.call_count == 2  # Not cached

    results = provider.lookup_many(["spotify:track:abc"])
    assert len(results["spotify:track:abc"]) == 1


def test_lookup_of_youralbums_uri(
    web_client_mock, web_album_mock, web_album_mock_link, provider
):
    web_saved_album_mock = {"album": web_album_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_album_mock, web_saved_album_mock]},
        {"items": [web_saved_album_mock, web_saved_album_mock]},
    ]
    web_client_mock.get_batch.side_effect = [
        [(web_album_mock_link, web_album_mock)],
        [],
    ]

    results = provider.lookup_many(["spotify:your:albums"])

    web_client_mock.get_all.assert_called_once()
    web_client_mock.get_batch.assert_called_once()
    assert len(results) == 1
    assert len(results["spotify:your:albums"]) == 4 * 10
    for track in results["spotify:your:albums"]:
        assert track.uri == "spotify:track:abc"
        assert track.name == "ABC 123"
        assert track.album.uri == "spotify:album:def"
        assert track.bitrate == 160
        assert track.album.name == "DEF 456"

    assert results == provider.lookup_many(["spotify:your:albums"])
    assert web_client_mock.get_all.call_count == 2  # Not cached
    web_client_mock.get_batch.assert_called_once()  # Cached

    results = provider.lookup_many(["spotify:album:def"])
    assert len(results["spotify:album:def"]) == 10
    web_client_mock.get_batch.assert_called_once()  # Cached


def test_lookup_caches_tracks_albums(
    web_client_mock, web_album_mock, web_album_mock_link, provider
):
    web_client_mock.get_batch.return_value = [(web_album_mock_link, web_album_mock)]

    results1 = provider.lookup_many(["spotify:album:def"])
    results2 = provider.lookup_many(["spotify:album:def"])
    results3 = provider.lookup_many(["spotify:track:abc"])

    web_client_mock.get_batch.assert_called_once()
    assert len(results1) == 1
    assert len(results1["spotify:album:def"]) == 10
    track = results1["spotify:album:def"][0]
    assert track.uri == "spotify:track:abc"

    assert len(results2) == 1
    assert len(results2["spotify:album:def"]) == 10
    track = results2["spotify:album:def"][0]
    assert track.uri == "spotify:track:abc"

    assert len(results3) == 1
    assert len(results3["spotify:track:abc"]) == 1
    track = results3["spotify:track:abc"][0]
    assert track.uri == "spotify:track:abc"


def test_lookup_caches_no_cache_playlist(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    playlist_uri = web_playlist_mock["uri"]
    results1 = provider.lookup_many([playlist_uri])
    results2 = provider.lookup_many([playlist_uri])
    results3 = provider.lookup_many(["spotify:track:abc"])

    web_client_mock.get_playlist.assert_has_calls(
        [mock.call(playlist_uri), mock.call(playlist_uri)]
    )
    web_client_mock.get_batch.assert_not_called()

    assert len(results1) == 1
    assert results1[playlist_uri][0].uri == "spotify:track:abc"
    assert results1 == results2

    assert len(results3) == 1
    assert results3["spotify:track:abc"][0].uri == "spotify:track:abc"


def test_lookup_no_cache_artist(web_client_mock, web_album_mock, provider):
    web_client_mock.get_artist_albums.return_value = [web_album_mock]

    artist_uri = "spotify:artist:abba"
    results1 = provider.lookup_many([artist_uri])
    results2 = provider.lookup_many([artist_uri])
    results3 = provider.lookup_many(["spotify:album:def", "spotify:track:abc"])

    assert web_client_mock.get_artist_albums.call_count == 2
    web_client_mock.get_batch.assert_not_called()

    assert len(results1) == 1
    assert results1[artist_uri][0].uri == "spotify:track:abc"
    assert results1 == results2

    assert len(results3) == 2
    assert results3["spotify:album:def"][0].uri == "spotify:track:abc"
    assert results3["spotify:track:abc"][0].uri == "spotify:track:abc"


def test_lookup_v4_compatible(provider):
    # TODO: Remove this once we release the major version
    provider.lookup("foo")
    assert mopidy.__version__.startswith("4.0.0a")
