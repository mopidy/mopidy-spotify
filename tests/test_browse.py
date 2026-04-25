from typing import Any
from unittest import mock

import pytest
from mopidy.models import Ref
from mopidy.types import Uri

from mopidy_spotify.browse import BROWSE_DIR_URIS
from mopidy_spotify.library import SpotifyLibraryProvider


def test_has_a_root_directory(provider: SpotifyLibraryProvider):
    assert provider.root_directory == Ref.directory(
        uri=Uri("spotify:directory"), name="Spotify"
    )


def test_browse_root_directory(provider: SpotifyLibraryProvider):
    results = provider.browse(Uri("spotify:directory"))

    assert len(results) == 3
    assert Ref.directory(uri=Uri("spotify:top"), name="Top lists") in results
    assert Ref.directory(uri=Uri("spotify:your"), name="Your music") in results
    assert Ref.directory(uri=Uri("spotify:playlists"), name="Playlists") in results


def test_browse_dir_uris(provider: SpotifyLibraryProvider):
    assert provider.root_directory.uri in BROWSE_DIR_URIS
    count = 1
    for u1 in provider.browse(provider.root_directory.uri):
        assert u1.uri in BROWSE_DIR_URIS
        count = count + 1
        for u2 in provider.browse(u1.uri):
            assert u2.uri in BROWSE_DIR_URIS
            count = count + 1

    assert len(BROWSE_DIR_URIS) == count


def test_browse_root_when_offline(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    web_client_mock.logged_in = False

    results = provider.browse(Uri("spotify:directory"))

    assert len(results) == 3


def test_browse_top_lists_directory(provider: SpotifyLibraryProvider):
    results = provider.browse(Uri("spotify:top"))

    assert len(results) == 2
    assert Ref.directory(uri=Uri("spotify:top:tracks"), name="Top tracks") in results
    assert Ref.directory(uri=Uri("spotify:top:artists"), name="Top artists") in results


def test_browse_your_music_directory(provider: SpotifyLibraryProvider):
    results = provider.browse(Uri("spotify:your"))

    assert len(results) == 2
    assert Ref.directory(uri=Uri("spotify:your:tracks"), name="Your tracks") in results
    assert Ref.directory(uri=Uri("spotify:your:albums"), name="Your albums") in results


def test_browse_playlists_directory(provider: SpotifyLibraryProvider):
    results = provider.browse(Uri("spotify:playlists"))

    assert len(results) == 1
    assert (
        Ref.directory(uri=Uri("spotify:playlists:featured"), name="Featured") in results
    )


def test_browse_playlist(
    web_client_mock: mock.MagicMock,
    web_playlist_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    results = provider.browse(Uri("spotify:user:alice:playlist:foo"))

    web_client_mock.get_playlist.assert_called_once_with(
        "spotify:user:alice:playlist:foo"
    )
    assert len(results) == 1
    assert results[0] == Ref.track(uri=Uri("spotify:track:abc"), name="ABC 123")


@pytest.mark.parametrize(
    "uri",
    [
        "album:def",
        "artist:abba",
        "user:alice:playlist:foo",
        "unknown",
        "top:tracks",
        "your:tracks",
    ],
)
def test_browse_item_when_offline(
    web_client_mock: mock.MagicMock,
    uri: str,
    provider: SpotifyLibraryProvider,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.logged_in = False

    results = provider.browse(Uri(f"spotify:{uri}"))

    assert len(results) == 0
    assert "Failed to browse" not in caplog.text


def test_browse_album(
    web_client_mock: mock.MagicMock,
    web_album_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_client_mock.get_albums.return_value = [web_album_mock]

    results = provider.browse(Uri("spotify:album:def"))

    assert len(results) == 10
    assert results[0] == Ref.track(uri=Uri("spotify:track:abc"), name="ABC 123")


def test_browse_album_bad_uri(
    web_client_mock: mock.MagicMock,
    web_album_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get_albums.return_value = [web_album_mock]

    results = provider.browse(Uri("spotify:album:def:xyz"))

    assert len(results) == 0
    assert "Failed to browse" in caplog.text


def test_browse_artist(
    web_client_mock: mock.MagicMock,
    web_album_mock_base: dict[str, Any],
    web_track_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_client_mock.get_artist_albums.return_value = [web_album_mock_base]
    web_client_mock.get_artist_top_tracks.return_value = [
        web_track_mock,
        web_track_mock,
        web_track_mock,
    ]

    results = provider.browse(Uri("spotify:artist:abba"))

    web_client_mock.get_artist_albums.assert_called_once_with(
        mock.ANY, all_tracks=False
    )
    assert len(results) == 4
    assert results[0] == Ref.track(uri=Uri("spotify:track:abc"), name="ABC 123")
    assert results[3] == Ref.album(uri=Uri("spotify:album:def"), name="ABBA - DEF 456")


def test_browse_artist_bad_uri(
    web_client_mock: mock.MagicMock,
    web_album_mock_base: dict[str, Any],
    web_track_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get_artist_albums.return_value = [web_album_mock_base]
    web_client_mock.get_artist_top_tracks.return_value = [
        web_track_mock,
        web_track_mock,
        web_track_mock,
    ]

    results = provider.browse(Uri("spotify:artist:def:xyz"))

    assert len(results) == 0
    assert "Failed to browse" in caplog.text


def test_browse_top_tracks_with_too_many_uri_parts(
    provider: SpotifyLibraryProvider,
):
    results = provider.browse(Uri("spotify:top:tracks:foo:bar"))

    assert len(results) == 0


def test_browse_unsupported_top_tracks(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    results = provider.browse(Uri("spotify:top:albums"))

    web_client_mock.get_one.assert_not_called()
    assert len(results) == 0


def test_browse_personal_top_tracks_empty(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    web_client_mock.get_all.return_value = [{}]

    results = provider.browse(Uri("spotify:top:tracks"))

    web_client_mock.get_all.assert_called_once_with(
        "me/top/tracks", params={"limit": 50}
    )
    assert len(results) == 0


def test_browse_personal_top_tracks(
    web_client_mock: mock.MagicMock,
    web_track_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    # The tracks from this endpoint are erroneously missing some fields:
    del web_track_mock["is_playable"]
    web_client_mock.get_all.return_value = [
        {"items": [web_track_mock, web_track_mock]},
        {"items": [web_track_mock, web_track_mock]},
    ]

    results = provider.browse(Uri("spotify:top:tracks"))

    web_client_mock.get_all.assert_called_once_with(
        "me/top/tracks", params={"limit": 50}
    )
    assert len(results) == 4
    assert results[0] == Ref.track(uri=Uri("spotify:track:abc"), name="ABC 123")


def test_browse_personal_top_artists(
    web_client_mock: mock.MagicMock,
    web_artist_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_client_mock.get_all.return_value = [
        {"items": [web_artist_mock, web_artist_mock]},
        {"items": [web_artist_mock, web_artist_mock]},
    ]

    results = provider.browse(Uri("spotify:top:artists"))

    web_client_mock.get_all.assert_called_once_with(
        "me/top/artists", params={"limit": 50}
    )
    assert len(results) == 4
    assert results[0] == Ref.artist(uri=Uri("spotify:artist:abba"), name="ABBA")


def test_browse_your_music_when_offline_web(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    web_client_mock.user_id = None

    results = provider.browse(Uri("spotify:your:tracks"))

    assert len(results) == 0


def test_browse_your_music_unknown(provider: SpotifyLibraryProvider):
    results = provider.browse(Uri("spotify:your:foobar"))

    assert len(results) == 0


def test_browse_your_music_tracks_unknown(
    provider: SpotifyLibraryProvider, caplog: pytest.LogCaptureFixture
):
    results = provider.browse(Uri("spotify:your:tracks:foobar"))

    assert len(results) == 0
    assert (
        "Failed to browse 'spotify:your:tracks:foobar': Unknown URI type" in caplog.text
    )


def test_browse_your_music_empty(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    web_client_mock.get_one.return_value = {}

    results = provider.browse(Uri("spotify:your:tracks"))

    assert len(results) == 0


def test_browse_your_music_tracks(
    web_client_mock: mock.MagicMock,
    web_track_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_saved_track_mock = {"track": web_track_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_track_mock, web_saved_track_mock]},
        {"items": [web_saved_track_mock, web_saved_track_mock]},
    ]

    results = provider.browse(Uri("spotify:your:tracks"))

    web_client_mock.get_all.assert_called_once_with(
        "me/tracks", params={"market": "from_token", "limit": 50}
    )
    assert results == [results[0]] * 4
    assert results[0] == Ref.track(uri=Uri("spotify:track:abc"), name="ABC 123")


def test_browse_your_music_albums(
    web_client_mock: mock.MagicMock,
    web_album_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_saved_album_mock = {"album": web_album_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_album_mock, web_saved_album_mock]},
        {"items": [web_saved_album_mock, web_saved_album_mock]},
    ]

    results = provider.browse(Uri("spotify:your:albums"))

    web_client_mock.get_all.assert_called_once_with(
        "me/albums", params={"market": "from_token", "limit": 50}
    )
    assert results == [results[0]] * 4
    assert results[0] == Ref.album(uri=Uri("spotify:album:def"), name="ABBA - DEF 456")


def test_browse_playlists_featured(
    web_client_mock: mock.MagicMock,
    web_playlist_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_client_mock.get_all.return_value = [
        {"playlists": {"items": [web_playlist_mock]}},
        {"playlists": {"items": [web_playlist_mock]}},
    ]

    results = provider.browse(Uri("spotify:playlists:featured"))

    web_client_mock.get_all.assert_called_once_with(
        "browse/featured-playlists", params={"limit": 50}
    )

    assert len(results) == 2
    assert results[0].name == "Foo"
    assert results[0].uri == "spotify:user:alice:playlist:foo"
