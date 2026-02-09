from unittest import mock

import pytest
from mopidy import models

from mopidy_spotify.browse import BROWSE_DIR_URIS


def test_has_a_root_directory(provider):
    assert provider.root_directory == models.Ref.directory(
        uri="spotify:directory", name="Spotify"
    )


def test_browse_root_directory(provider):
    results = provider.browse("spotify:directory")

    assert len(results) == 3
    assert models.Ref.directory(uri="spotify:top", name="Top lists") in results
    assert models.Ref.directory(uri="spotify:your", name="Your music") in results
    assert models.Ref.directory(uri="spotify:playlists", name="Playlists") in results


def test_browse_dir_uris(provider):
    assert provider.root_directory.uri in BROWSE_DIR_URIS
    count = 1
    for u1 in provider.browse(provider.root_directory.uri):
        assert u1.uri in BROWSE_DIR_URIS
        count = count + 1
        for u2 in provider.browse(u1.uri):
            assert u2.uri in BROWSE_DIR_URIS
            count = count + 1

    assert len(BROWSE_DIR_URIS) == count


def test_browse_root_when_offline(web_client_mock, provider):
    web_client_mock.logged_in = False

    results = provider.browse("spotify:directory")

    assert len(results) == 3


def test_browse_top_lists_directory(provider):
    results = provider.browse("spotify:top")

    assert len(results) == 2
    assert models.Ref.directory(uri="spotify:top:tracks", name="Top tracks") in results
    assert (
        models.Ref.directory(uri="spotify:top:artists", name="Top artists") in results
    )


def test_browse_your_music_directory(provider):
    results = provider.browse("spotify:your")

    assert len(results) == 2
    assert (
        models.Ref.directory(uri="spotify:your:tracks", name="Your tracks") in results
    )
    assert (
        models.Ref.directory(uri="spotify:your:albums", name="Your albums") in results
    )


def test_browse_playlists_directory(provider):
    """Test browsing the playlists directory returns all playlist categories."""
    results = provider.browse("spotify:playlists")

    assert len(results) == 2
    assert (
        models.Ref.directory(uri="spotify:playlists:featured", name="Featured")
        in results
    )
    assert (
        models.Ref.directory(uri="spotify:playlists:new-releases", name="New releases")
        in results
    )


def test_browse_playlist(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get_playlist.return_value = web_playlist_mock

    results = provider.browse("spotify:user:alice:playlist:foo")

    web_client_mock.get_playlist.assert_called_once_with(
        "spotify:user:alice:playlist:foo"
    )
    assert len(results) == 1
    assert results[0] == models.Ref.track(uri="spotify:track:abc", name="ABC 123")


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
def test_browse_item_when_offline(web_client_mock, uri, provider, caplog):
    web_client_mock.logged_in = False

    results = provider.browse(f"spotify:{uri}")

    assert len(results) == 0
    assert "Failed to browse" not in caplog.text


def test_browse_album(web_client_mock, web_album_mock, provider):
    web_client_mock.get_albums.return_value = [web_album_mock]

    results = provider.browse("spotify:album:def")

    assert len(results) == 10
    assert results[0] == models.Ref.track(uri="spotify:track:abc", name="ABC 123")


def test_browse_album_bad_uri(web_client_mock, web_album_mock, provider, caplog):
    web_client_mock.get_albums.return_value = [web_album_mock]

    results = provider.browse("spotify:album:def:xyz")

    assert len(results) == 0
    assert "Failed to browse" in caplog.text


def test_browse_artist(
    web_client_mock,
    web_album_mock_base,
    web_track_mock,
    provider,
):
    web_client_mock.get_artist_albums.return_value = [web_album_mock_base]
    web_client_mock.get_artist_top_tracks.return_value = [
        web_track_mock,
        web_track_mock,
        web_track_mock,
    ]

    results = provider.browse("spotify:artist:abba")

    web_client_mock.get_artist_albums.assert_called_once_with(
        mock.ANY, all_tracks=False
    )
    assert len(results) == 4
    assert results[0] == models.Ref.track(uri="spotify:track:abc", name="ABC 123")
    assert results[3] == models.Ref.album(
        uri="spotify:album:def", name="ABBA - DEF 456"
    )


def test_browse_artist_bad_uri(
    web_client_mock,
    web_album_mock_base,
    web_track_mock,
    provider,
    caplog,
):
    web_client_mock.get_artist_albums.return_value = [web_album_mock_base]
    web_client_mock.get_artist_top_tracks.return_value = [
        web_track_mock,
        web_track_mock,
        web_track_mock,
    ]

    results = provider.browse("spotify:artist:def:xyz")

    assert len(results) == 0
    assert "Failed to browse" in caplog.text


def test_browse_top_tracks_with_too_many_uri_parts(provider):
    results = provider.browse("spotify:top:tracks:foo:bar")

    assert len(results) == 0


def test_browse_unsupported_top_tracks(web_client_mock, provider):
    results = provider.browse("spotify:top:albums")

    web_client_mock.get_one.assert_not_called()
    assert len(results) == 0


def test_browse_personal_top_tracks_empty(web_client_mock, provider):
    web_client_mock.get_all.return_value = [{}]

    results = provider.browse("spotify:top:tracks")

    web_client_mock.get_all.assert_called_once_with(
        "me/top/tracks", params={"limit": 50}
    )
    assert len(results) == 0


def test_browse_personal_top_tracks(web_client_mock, web_track_mock, provider):
    # The tracks from this endpoint are erroneously missing some fields:
    del web_track_mock["is_playable"]
    web_client_mock.get_all.return_value = [
        {"items": [web_track_mock, web_track_mock]},
        {"items": [web_track_mock, web_track_mock]},
    ]

    results = provider.browse("spotify:top:tracks")

    web_client_mock.get_all.assert_called_once_with(
        "me/top/tracks", params={"limit": 50}
    )
    assert len(results) == 4
    assert results[0] == models.Ref.track(uri="spotify:track:abc", name="ABC 123")


def test_browse_personal_top_artists(web_client_mock, web_artist_mock, provider):
    web_client_mock.get_all.return_value = [
        {"items": [web_artist_mock, web_artist_mock]},
        {"items": [web_artist_mock, web_artist_mock]},
    ]

    results = provider.browse("spotify:top:artists")

    web_client_mock.get_all.assert_called_once_with(
        "me/top/artists", params={"limit": 50}
    )
    assert len(results) == 4
    assert results[0] == models.Ref.artist(uri="spotify:artist:abba", name="ABBA")


def test_browse_your_music_when_offline_web(web_client_mock, provider):
    web_client_mock.user_id = None

    results = provider.browse("spotify:your:tracks")

    assert len(results) == 0


def test_browse_your_music_unknown(provider):
    results = provider.browse("spotify:your:foobar")

    assert len(results) == 0


def test_browse_your_music_tracks_unknown(provider, caplog):
    results = provider.browse("spotify:your:tracks:foobar")

    assert len(results) == 0
    assert (
        "Failed to browse 'spotify:your:tracks:foobar': Unknown URI type" in caplog.text
    )


def test_browse_your_music_empty(web_client_mock, provider):
    web_client_mock.get_one.return_value = {}

    results = provider.browse("spotify:your:tracks")

    assert len(results) == 0


def test_browse_your_music_tracks(web_client_mock, web_track_mock, provider):
    web_saved_track_mock = {"track": web_track_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_track_mock, web_saved_track_mock]},
        {"items": [web_saved_track_mock, web_saved_track_mock]},
    ]

    results = provider.browse("spotify:your:tracks")

    web_client_mock.get_all.assert_called_once_with(
        "me/tracks", params={"market": "from_token", "limit": 50}
    )
    assert results == [results[0]] * 4
    assert results[0] == models.Ref.track(uri="spotify:track:abc", name="ABC 123")


def test_browse_your_music_albums(web_client_mock, web_album_mock, provider):
    web_saved_album_mock = {"album": web_album_mock}
    web_client_mock.get_all.return_value = [
        {"items": [web_saved_album_mock, web_saved_album_mock]},
        {"items": [web_saved_album_mock, web_saved_album_mock]},
    ]

    results = provider.browse("spotify:your:albums")

    web_client_mock.get_all.assert_called_once_with(
        "me/albums", params={"market": "from_token", "limit": 50}
    )
    assert results == [results[0]] * 4
    assert results[0] == models.Ref.album(
        uri="spotify:album:def", name="ABBA - DEF 456"
    )


def test_browse_playlists_featured(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get_all.return_value = [
        {"playlists": {"items": [web_playlist_mock]}},
        {"playlists": {"items": [web_playlist_mock]}},
    ]

    results = provider.browse("spotify:playlists:featured")

    web_client_mock.get_all.assert_called_once_with(
        "browse/featured-playlists", params={"limit": 50}
    )

    assert len(results) == 2
    assert results[0].name == "Foo"
    assert results[0].uri == "spotify:user:alice:playlist:foo"


def test_browse_new_releases(web_client_mock, web_album_mock_base, provider):
    """Test browsing new releases returns album refs.

    Verifies successful response handling per Spotify Web API reference:
    https://developer.spotify.com/documentation/web-api/reference/get-new-releases

    Response structure: { "albums": { "items": [SimplifiedAlbumObject, ...] } }
    """
    web_client_mock.get_all.return_value = [
        {"albums": {"items": [web_album_mock_base]}},
        {"albums": {"items": [web_album_mock_base]}},
    ]

    results = provider.browse("spotify:playlists:new-releases")

    web_client_mock.get_all.assert_called_once_with(
        "browse/new-releases", params={"limit": 50}
    )
    assert len(results) == 2
    assert results[0] == models.Ref.album(
        uri="spotify:album:def", name="ABBA - DEF 456"
    )


def test_browse_new_releases_empty(web_client_mock, provider):
    """Test browsing new releases when API returns empty results.

    Per Spotify API docs, albums.items may be an empty array when no new
    releases are available for the market.
    https://developer.spotify.com/documentation/web-api/reference/get-new-releases
    """
    web_client_mock.get_all.return_value = [{}]

    results = provider.browse("spotify:playlists:new-releases")

    web_client_mock.get_all.assert_called_once_with(
        "browse/new-releases", params={"limit": 50}
    )
    assert len(results) == 0


def test_browse_new_releases_when_offline(web_client_mock, provider):
    """Test browsing new releases when not logged in.

    Spotify API requires valid OAuth token. Error 401 (bad/expired token) and
    403 (bad OAuth request) are handled by web_client before reaching browse.
    https://developer.spotify.com/documentation/web-api/reference/get-new-releases
    """
    web_client_mock.logged_in = False

    results = provider.browse("spotify:playlists:new-releases")

    web_client_mock.get_all.assert_not_called()
    assert len(results) == 0


def test_browse_playlists_unknown_variant(web_client_mock, provider, caplog):
    """Test browsing unknown playlist variant logs warning and returns empty."""
    results = provider.browse("spotify:playlists:unknown")

    web_client_mock.get_all.assert_not_called()
    assert len(results) == 0
    assert "Unknown URI type" in caplog.text


# Defensive programming tests - verifying robust handling of edge cases
#
# These tests verify graceful handling of malformed or unexpected API responses.
# Per Spotify Web API reference, the expected response structure is:
# { "albums": { "href": str, "limit": int, "next": str|null, "offset": int,
#               "previous": str|null, "total": int, "items": [SimplifiedAlbumObject] } }
# https://developer.spotify.com/documentation/web-api/reference/get-new-releases
#
# However, pagination and network issues may produce partial/malformed responses.
# The translator.valid_web_data() validates each album object has type="album" and uri.


def test_browse_new_releases_handles_none_pages(web_client_mock, provider):
    """Test that None pages in the response are safely filtered out.

    Pagination via web_client.get_all() may yield None for failed page fetches
    (e.g., network timeouts, rate limiting via 429 status).
    """
    web_client_mock.get_all.return_value = [
        None,
        {"albums": {"items": []}},
        None,
    ]

    results = provider.browse("spotify:playlists:new-releases")

    assert len(results) == 0


def test_browse_new_releases_handles_missing_albums_key(web_client_mock, provider):
    """Test that pages missing the 'albums' key are handled gracefully.

    While the API spec defines 'albums' as required, defensive coding handles
    unexpected response shapes that may occur during API changes or errors.
    """
    web_client_mock.get_all.return_value = [
        {"unexpected_key": {"items": []}},
        {},
    ]

    results = provider.browse("spotify:playlists:new-releases")

    assert len(results) == 0


def test_browse_new_releases_handles_missing_items_key(
    web_client_mock, web_album_mock_base, provider
):
    """Test that pages with 'albums' but missing 'items' are handled gracefully.

    The API spec shows 'items' as required within 'albums', but we use .get()
    with empty list default to handle partial responses defensively.
    """
    web_client_mock.get_all.return_value = [
        {"albums": {}},
        {"albums": {"items": [web_album_mock_base]}},
    ]

    results = provider.browse("spotify:playlists:new-releases")

    assert len(results) == 1


def test_browse_new_releases_handles_mixed_valid_invalid_pages(
    web_client_mock, web_album_mock_base, provider
):
    """Test that valid data is extracted even when mixed with invalid pages.

    Real-world pagination may encounter intermittent failures. This verifies
    the implementation extracts all valid albums while gracefully skipping
    malformed pages, ensuring maximum data availability.
    """
    web_client_mock.get_all.return_value = [
        None,
        {"albums": {"items": [web_album_mock_base]}},
        {},
        {"albums": {}},
        {"albums": {"items": [web_album_mock_base, web_album_mock_base]}},
    ]

    results = provider.browse("spotify:playlists:new-releases")

    assert len(results) == 3
