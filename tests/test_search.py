from typing import Any
from unittest import mock

import pytest
from mopidy.models import SearchResult

from mopidy_spotify import lookup, search, translator
from mopidy_spotify.library import SpotifyLibraryProvider


def test_search_with_no_query_returns_nothing(
    provider: SpotifyLibraryProvider, caplog: pytest.LogCaptureFixture
):
    result = provider.search(query={})

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search"
    assert len(result.tracks) == 0
    assert "Ignored search without query" in caplog.text


def test_search_with_empty_query_returns_nothing(
    provider: SpotifyLibraryProvider, caplog: pytest.LogCaptureFixture
):
    result = provider.search({"any": []})

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search"
    assert len(result.tracks) == 0
    assert "Ignored search with empty query" in caplog.text


def test_search_by_single_uri(
    web_track_mock: dict[str, Any], provider: SpotifyLibraryProvider
):
    track = translator.web_to_track(web_track_mock, 160)
    with mock.patch.object(lookup, "lookup") as mock_lookup:
        mock_lookup.return_value = {track.uri: [track]}
        result = provider.search({"uri": [track.uri]})

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:track:abc"
    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_search_by_multiple_uris(
    web_track_mock: dict[str, Any], provider: SpotifyLibraryProvider
):
    track = translator.web_to_track(web_track_mock, 160)
    with mock.patch.object(lookup, "lookup") as mock_lookup:
        mock_lookup.return_value = {track.uri: [track]}
        result = provider.search({"uri": [track.uri, track.uri]})

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search"
    assert len(result.tracks) == 2
    track = result.tracks[0]
    assert track.uri == "spotify:track:abc"
    assert track.name == "ABC 123"
    assert track.bitrate == 160


def test_search_when_offline_returns_nothing(
    web_client_mock: mock.MagicMock,
    provider: SpotifyLibraryProvider,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.logged_in = False

    result = provider.search({"any": ["ABBA"]})

    assert "Spotify search aborted: Spotify is offline" in caplog.text

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search:ABBA"
    assert len(result.tracks) == 0


def test_search_returns_albums_and_artists_and_tracks(
    web_client_mock: mock.MagicMock,
    web_search_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
    caplog: pytest.LogCaptureFixture,
):
    web_client_mock.get.return_value = web_search_mock
    result = provider.search({"any": ["ABBA"]})

    web_client_mock.get.assert_called_once_with(
        "search",
        params={
            "q": "ABBA",
            "limit": 50,
            "market": "from_token",
            "type": "album,artist,track",
        },
    )

    assert "Searching Spotify for: ABBA" in caplog.text

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search:ABBA"

    assert len(result.albums) == 1
    assert result.albums[0].uri == "spotify:album:def"

    assert len(result.artists) == 1
    assert result.artists[0].uri == "spotify:artist:abba"

    assert len(result.tracks) == 2
    assert result.tracks[0].uri == "spotify:track:abc"


def test_search_limits_number_of_results(
    web_client_mock: mock.MagicMock,
    web_search_mock_large: dict[str, Any],
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
):
    config["spotify"]["search_album_count"] = 4
    config["spotify"]["search_artist_count"] = 5
    config["spotify"]["search_track_count"] = 6

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({"any": ["ABBA"]})

    assert len(result.albums) == 4
    assert len(result.artists) == 5
    assert len(result.tracks) == 6


def test_sets_api_limit_to_album_count_when_max(
    web_client_mock: mock.MagicMock,
    web_search_mock_large: dict[str, Any],
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
):
    config["spotify"]["search_album_count"] = 6
    config["spotify"]["search_artist_count"] = 2
    config["spotify"]["search_track_count"] = 2

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({"any": ["ABBA"]})

    web_client_mock.get.assert_called_once_with(
        "search",
        params={
            "q": "ABBA",
            "limit": 6,
            "market": "from_token",
            "type": "album,artist,track",
        },
    )

    assert len(result.albums) == 6


def test_sets_api_limit_to_artist_count_when_max(
    web_client_mock: mock.MagicMock,
    web_search_mock_large: dict[str, Any],
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
):
    config["spotify"]["search_album_count"] = 2
    config["spotify"]["search_artist_count"] = 6
    config["spotify"]["search_track_count"] = 2

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({"any": ["ABBA"]})

    web_client_mock.get.assert_called_once_with(
        "search",
        params={
            "q": "ABBA",
            "limit": 6,
            "market": "from_token",
            "type": "album,artist,track",
        },
    )

    assert len(result.artists) == 6


def test_sets_api_limit_to_track_count_when_max(
    web_client_mock: mock.MagicMock,
    web_search_mock_large: dict[str, Any],
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
):
    config["spotify"]["search_album_count"] = 2
    config["spotify"]["search_artist_count"] = 2
    config["spotify"]["search_track_count"] = 6

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({"any": ["ABBA"]})

    web_client_mock.get.assert_called_once_with(
        "search",
        params={
            "q": "ABBA",
            "limit": 6,
            "market": "from_token",
            "type": "album,artist,track",
        },
    )

    assert len(result.tracks) == 6


def test_sets_types_parameter(
    web_client_mock: mock.MagicMock,
    web_search_mock_large: dict[str, Any],
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
):
    web_client_mock.get.return_value = web_search_mock_large

    search.search(
        config["spotify"],
        web_client_mock,
        query={"any": ["ABBA"]},
        types=["album", "artist"],
    )

    web_client_mock.get.assert_called_once_with(
        "search",
        params={
            "q": "ABBA",
            "limit": 50,
            "market": "from_token",
            "type": "album,artist",
        },
    )


def test_sets_market_parameter(
    web_client_mock: mock.MagicMock,
    web_search_mock_large: dict[str, Any],
    provider: SpotifyLibraryProvider,
):
    web_client_mock.get.return_value = web_search_mock_large

    provider.search({"any": ["ABBA"]})

    web_client_mock.get.assert_called_once_with(
        "search",
        params={
            "q": "ABBA",
            "limit": 50,
            "market": "from_token",
            "type": "album,artist,track",
        },
    )


def test_handles_empty_response(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    web_client_mock.get.return_value = {}

    result = provider.search({"any": ["ABBA"]})

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search:ABBA"

    assert len(result.albums) == 0
    assert len(result.artists) == 0
    assert len(result.tracks) == 0


def test_search_filters_bad_results(
    web_artist_mock: dict[str, Any],
    web_client_mock: mock.MagicMock,
    web_search_mock: dict[str, Any],
    provider: SpotifyLibraryProvider,
    caplog: pytest.LogCaptureFixture,
):
    good_track = {
        "uri": "spotify:track:good",
        "type": "track",
        "is_playable": True,
    }
    bad_track = {
        "uri": "spotify:track:bad",
        "type": "track",
        "is_playable": False,
    }
    web_search_mock["albums"]["items"] = [good_track]
    web_search_mock["artists"]["items"][0]["uri"] = None
    web_search_mock["tracks"]["items"] = [{}, good_track, bad_track]
    web_client_mock.get.return_value = web_search_mock
    result = provider.search({"any": ["ABBA"]})

    assert isinstance(result, SearchResult)
    assert result.uri == "spotify:search:ABBA"

    assert len(result.albums) == 0
    assert len(result.artists) == 0
    assert len(result.tracks) == 1
    assert result.tracks[0].uri == "spotify:track:good"
