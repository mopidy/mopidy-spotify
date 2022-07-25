from unittest import mock

import pytest
from mopidy import models

from mopidy_spotify import distinct, search, playlists


@pytest.fixture
def web_client_mock_with_playlists(
    web_client_mock,
    web_playlist_mock,
):
    web_client_mock.get_user_playlists.return_value = [
        web_playlist_mock,
        {},
        web_playlist_mock,
    ]
    web_client_mock.get_playlist.return_value = web_playlist_mock
    return web_client_mock


@pytest.fixture
def search_mock(mopidy_album_mock, mopidy_artist_mock):
    patcher = mock.patch.object(distinct, "search", spec=search)
    search_mock = patcher.start()
    search_mock.search.return_value = models.SearchResult(
        albums=[mopidy_album_mock], artists=[mopidy_artist_mock]
    )
    yield search_mock
    patcher.stop()


def test_get_distinct_when_offine(web_client_mock, provider):
    web_client_mock.logged_in = False

    results = provider.get_distinct("artist")

    assert results == set()


@pytest.mark.parametrize(
    "field", ["composer", "performer", "genre", "unknown-field-type"]
)
def test_get_distinct_unsupported_field_types_returns_nothing(provider, field):
    assert provider.get_distinct(field) == set()


@pytest.mark.parametrize(
    "field,expected",
    [
        ("artist", {"ABBA"}),
        ("albumartist", {"ABBA"}),
        ("album", {"DEF 456"}),
    ],
)
# ("date", {"2001"}),
def test_get_distinct_without_query_when_playlists_enabled(
    web_client_mock_with_playlists, provider, field, expected
):
    provider._backend.playlists = playlists.SpotifyPlaylistsProvider(
        backend=provider._backend
    )
    provider._backend.playlists._loaded = True

    assert provider.get_distinct(field) == expected


def test_get_distinct_without_query_returns_nothing_when_playlists_empty(
    web_client_mock_with_playlists, provider
):
    provider._backend.playlists = playlists.SpotifyPlaylistsProvider(
        backend=provider._backend
    )
    provider._backend.playlists._loaded = True
    web_client_mock_with_playlists.get_playlist.return_value = {}

    assert provider.get_distinct("artist") == set()


@pytest.mark.parametrize("field", ["artist", "albumartist", "album", "date"])
def test_get_distinct_without_query_returns_nothing_when_playlists_disabled(
    provider, config, field
):

    config["spotify"]["allow_playlists"] = False

    assert provider.get_distinct(field) == set()


@pytest.mark.parametrize(
    "field,query,expected,types",
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
    search_mock,
    provider,
    config,
    web_client_mock,
    field,
    query,
    expected,
    types,
):

    assert provider.get_distinct(field, query) == expected
    search_mock.search.assert_called_once_with(
        mock.ANY, mock.ANY, query, types=types
    )
