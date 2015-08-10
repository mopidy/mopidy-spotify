from __future__ import unicode_literals

from mopidy import models

import spotify


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


def test_search_when_offline_returns_nothing(session_mock, provider, caplog):
    session_mock.connection.state = spotify.ConnectionState.OFFLINE

    result = provider.search({'any': ['ABBA']})

    assert 'Spotify search aborted: Spotify is offline' in caplog.text()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'
    assert len(result.tracks) == 0


def test_search_returns_albums_and_artists_and_tracks(
        session_mock, sp_search_mock, provider, caplog):
    session_mock.search.return_value = sp_search_mock

    result = provider.search({'any': ['ABBA']})

    session_mock.search.assert_called_once_with(
        '"ABBA"', album_count=20, artist_count=10, track_count=50)
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


def test_exact_is_ignored(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result1 = provider.search({'uri': ['spotify:track:abc']})
    result2 = provider.search({'uri': ['spotify:track:abc']}, exact=True)

    assert result1 == result2
