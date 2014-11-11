from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api, models

import pytest

import spotify

from mopidy_spotify import backend, library


@pytest.fixture
def session_mock():
    sp_session_mock = mock.Mock(spec=spotify.Session)
    return sp_session_mock


@pytest.fixture
def backend_mock(session_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._session = session_mock
    backend_mock.bitrate = 160
    return backend_mock


@pytest.fixture
def provider(backend_mock):
    return library.SpotifyLibraryProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.LibraryProvider)


def test_lookup_of_invalid_uri(session_mock, provider, caplog):
    session_mock.get_link.side_effect = ValueError('an error message')

    results = provider.lookup('invalid')

    assert len(results) == 0
    assert 'Failed to lookup "invalid": an error message' in caplog.text()


def test_lookup_of_unhandled_uri(session_mock, provider, caplog):
    sp_link_mock = mock.Mock(spec=spotify.Link)
    sp_link_mock.type = spotify.LinkType.INVALID
    session_mock.get_link.return_value = sp_link_mock

    results = provider.lookup('something')

    assert len(results) == 0
    assert (
        'Failed to lookup "something": Cannot handle <LinkType.INVALID: 0>'
        in caplog.text())


def test_lookup_of_track_uri(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    results = provider.lookup('spotify:track:abc')

    session_mock.get_link.assert_called_once_with('spotify:track:abc')
    sp_track_mock.link.as_track.assert_called_once_with()
    sp_track_mock.load.assert_called_once_with()

    assert len(results) == 1
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_lookup_of_album_uri(session_mock, sp_album_browser_mock, provider):
    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_album_mock.link

    results = provider.lookup('spotify:album:def')

    session_mock.get_link.assert_called_once_with('spotify:album:def')
    sp_album_mock.link.as_album.assert_called_once_with()

    sp_album_mock.browse.assert_called_once_with()
    sp_album_browser_mock.load.assert_called_once_with()

    assert len(results) == 2
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_lookup_of_artist_uri(
        session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider):
    sp_artist_mock = sp_artist_browser_mock.artist
    sp_album_mock = sp_album_browser_mock.album
    session_mock.get_link.return_value = sp_artist_mock.link

    results = provider.lookup('spotify:artist:abba')

    session_mock.get_link.assert_called_once_with('spotify:artist:abba')
    sp_artist_mock.link.as_artist.assert_called_once_with()

    sp_artist_mock.browse.assert_called_once_with(
        type=spotify.ArtistBrowserType.NO_TRACKS)
    sp_artist_browser_mock.load.assert_called_once_with()

    assert sp_album_mock.browse.call_count == 2
    assert sp_album_browser_mock.load.call_count == 2

    assert len(results) == 4
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_lookup_of_artist_uri_ignores_compilations(
        session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_mock = sp_album_browser_mock.album
    sp_album_mock.type = spotify.AlbumType.COMPILATION

    results = provider.lookup('spotify:artist:abba')

    assert len(results) == 0


def test_lookup_of_artist_uri_ignores_various_artists_albums(
        session_mock, sp_artist_browser_mock, sp_album_browser_mock, provider):
    sp_artist_mock = sp_artist_browser_mock.artist
    session_mock.get_link.return_value = sp_artist_mock.link
    sp_album_browser_mock.album.artist.link.uri = (
        'spotify:artist:0LyfQWJT6nXafLPZqxe9Of')

    results = provider.lookup('spotify:artist:abba')

    assert len(results) == 0


def test_lookup_of_playlist_uri(session_mock, sp_playlist_mock, provider):
    session_mock.get_link.return_value = sp_playlist_mock.link

    results = provider.lookup('spotify:playlist:alice:foo')

    session_mock.get_link.assert_called_once_with('spotify:playlist:alice:foo')
    sp_playlist_mock.link.as_playlist.assert_called_once_with()
    sp_playlist_mock.load.assert_called_once_with()

    assert len(results) == 1
    track = results[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_search_with_no_query_returns_nothing(provider, caplog):
    result = provider.search()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 0
    assert 'Ignored search without query' in caplog.text()


def test_search_with_empty_query_returns_nothing(provider, caplog):
    result = provider.search({'any': []})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 0
    assert 'Ignored search with empty query' in caplog.text()


def test_search_by_single_uri(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result = provider.search({'uri': ['spotify:track:abc']})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:track:abc'
    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_search_by_multiple_uris(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result = provider.search({
        'uri': ['spotify:track:abc', 'spotify:track:abc']
    })

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 2
    track = result.tracks[0]
    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.bitrate == 160


def test_search_when_offline_returns_nothing(provider, caplog):
    provider._backend._online.is_set.return_value = False

    result = provider.search({'any': ['ABBA']})

    assert 'Search aborted: Spotify is offline' in caplog.text()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'
    assert len(result.tracks) == 0


def test_search_returns_albums_and_artists_and_tracks(
        session_mock, sp_search_mock, provider, caplog):
    session_mock.search.return_value = sp_search_mock

    result = provider.search({'any': ['ABBA']})

    session_mock.search.assert_called_once_with('"ABBA"')
    sp_search_mock.load.assert_called_once_with()

    assert 'Searching Spotify for: "ABBA"' in caplog.text()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'

    assert len(result.albums) == 1
    assert result.albums[0].uri == 'spotify:album:def'

    assert len(result.artists) == 1
    assert result.artists[0].uri == 'spotify:artist:abba'

    assert len(result.tracks) == 2
    assert result.tracks[0].uri == 'spotify:track:abc'


def test_find_exact_is_the_same_as_search(provider):
    assert provider.find_exact == provider.search
