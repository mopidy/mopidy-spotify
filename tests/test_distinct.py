from typing import Any
from unittest import mock

import pytest
from mopidy.models import Album, Artist, SearchResult

from mopidy_spotify import distinct, playlists, search
from mopidy_spotify.library import SpotifyLibraryProvider


@pytest.fixture
def web_client_mock_with_playlists(
    web_client_mock: mock.MagicMock,
    web_playlist_mock: dict[str, Any],
) -> mock.MagicMock:
    web_client_mock.get_user_playlists.return_value = [
        web_playlist_mock,
        {},
        web_playlist_mock,
    ]
    web_client_mock.get_playlist.return_value = web_playlist_mock
    return web_client_mock


@pytest.fixture
def search_mock(mopidy_album_mock: Album, mopidy_artist_mock: Artist):
    patcher = mock.patch.object(distinct, "search", spec=search)
    search_mock = patcher.start()
    search_mock.search.return_value = SearchResult(
        albums=[mopidy_album_mock], artists=[mopidy_artist_mock]
    )
    yield search_mock
    patcher.stop()


def test_get_distinct_when_offline(
    web_client_mock: mock.MagicMock, provider: SpotifyLibraryProvider
):
    web_client_mock.logged_in = False

    results = provider.get_distinct("artist")

    assert results == set()


@pytest.mark.parametrize(
    "field", ["composer", "performer", "genre", "unknown-field-type"]
)
def test_get_distinct_unsupported_field_types_returns_nothing(
    provider: SpotifyLibraryProvider, field: str
):
    assert provider.get_distinct(field) == set()


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("artist", {"ABBA"}),
        ("albumartist", {"ABBA"}),
        ("album", {"DEF 456"}),
    ],
)
def test_get_distinct_without_query_when_playlists_enabled(
    web_client_mock_with_playlists: mock.MagicMock,
    provider: SpotifyLibraryProvider,
    field: str,
    expected: set[str],
):
    provider._backend.playlists = playlists.SpotifyPlaylistsProvider(
        backend=provider._backend
    )
    provider._backend.playlists._loaded = True

    assert provider.get_distinct(field) == expected


def test_get_distinct_without_query_returns_nothing_when_playlists_empty(
    web_client_mock_with_playlists: mock.MagicMock,
    provider: SpotifyLibraryProvider,
):
    provider._backend.playlists = playlists.SpotifyPlaylistsProvider(
        backend=provider._backend
    )
    provider._backend.playlists._loaded = True
    web_client_mock_with_playlists.get_playlist.return_value = {}

    assert provider.get_distinct("artist") == set()


@pytest.mark.parametrize("field", ["artist", "albumartist", "album", "date"])
def test_get_distinct_without_query_returns_nothing_when_playlists_disabled(
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
    field: str,
):
    config["spotify"]["allow_playlists"] = False

    assert provider.get_distinct(field) == set()


@pytest.mark.parametrize(
    ("field", "query", "expected", "types"),
    [
        (
            "artist",
            {"album": ["Foo"]},
            {"ABBA"},
            ["artist"],
        ),
        (
            "albumartist",
            {"album": ["Foo"]},
            {"ABBA"},
            ["album"],
        ),
        (
            "album",
            {"artist": ["Bar"]},
            {"DEF 456"},
            ["album"],
        ),
        (
            "date",
            {"artist": ["Bar"]},
            {"2001"},
            ["album"],
        ),
    ],
)
def test_get_distinct_with_query(
    search_mock: mock.MagicMock,
    provider: SpotifyLibraryProvider,
    config: dict[str, Any],
    web_client_mock: mock.MagicMock,
    field: str,
    query: dict[str, list[str]],
    expected: set[str],
    types: list[str],
):
    assert provider.get_distinct(field, query) == expected
    search_mock.search.assert_called_once_with(
        mock.ANY,
        mock.ANY,
        query=query,
        types=types,
    )
