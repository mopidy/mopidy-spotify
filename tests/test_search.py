from __future__ import unicode_literals

from mopidy import models

import spotify

from mopidy_spotify import search


def test_search_with_no_query_returns_nothing(provider, caplog):
    result = provider.search()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 0
    assert 'Ignored search without query' in caplog.text


def test_search_with_empty_query_returns_nothing(provider, caplog):
    result = provider.search({'any': []})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search'
    assert len(result.tracks) == 0
    assert 'Ignored search with empty query' in caplog.text


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

    assert 'Spotify search aborted: Spotify is offline' in caplog.text

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'
    assert len(result.tracks) == 0


def test_search_returns_albums_and_artists_and_tracks(
        web_client_mock, web_search_mock, provider, caplog):
    web_client_mock.get.return_value = web_search_mock
    result = provider.search({'any': ['ABBA']})

    web_client_mock.get.assert_called_once_with(
        'search',
        params={
            'q': '"ABBA"',
            'limit': 50,
            'market': 'GB',
            'type': 'album,artist,track'})

    assert 'Searching Spotify for: "ABBA"' in caplog.text

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'

    assert len(result.albums) == 1
    assert result.albums[0].uri == 'spotify:album:def'

    assert len(result.artists) == 1
    assert result.artists[0].uri == 'spotify:artist:abba'

    assert len(result.tracks) == 2
    assert result.tracks[0].uri == 'spotify:track:abc'


def test_search_limits_number_of_results(
        web_client_mock, web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 4
    config['spotify']['search_artist_count'] = 5
    config['spotify']['search_track_count'] = 6

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({'any': ['ABBA']})

    assert len(result.albums) == 4
    assert len(result.artists) == 5
    assert len(result.tracks) == 6


def test_sets_api_limit_to_album_count_when_max(
        web_client_mock, web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 6
    config['spotify']['search_artist_count'] = 2
    config['spotify']['search_track_count'] = 2

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({'any': ['ABBA']})

    web_client_mock.get.assert_called_once_with(
        'search',
        params={
            'q': '"ABBA"',
            'limit': 6,
            'market': 'GB',
            'type': 'album,artist,track'})

    assert len(result.albums) == 6


def test_sets_api_limit_to_artist_count_when_max(
        web_client_mock, web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 2
    config['spotify']['search_artist_count'] = 6
    config['spotify']['search_track_count'] = 2

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({'any': ['ABBA']})

    web_client_mock.get.assert_called_once_with(
        'search',
        params={
            'q': '"ABBA"',
            'limit': 6,
            'market': 'GB',
            'type': 'album,artist,track'})

    assert len(result.artists) == 6


def test_sets_api_limit_to_track_count_when_max(
        web_client_mock, web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 2
    config['spotify']['search_artist_count'] = 2
    config['spotify']['search_track_count'] = 6

    web_client_mock.get.return_value = web_search_mock_large

    result = provider.search({'any': ['ABBA']})

    web_client_mock.get.assert_called_once_with(
        'search',
        params={
            'q': '"ABBA"',
            'limit': 6,
            'market': 'GB',
            'type': 'album,artist,track'})

    assert len(result.tracks) == 6


def test_sets_types_parameter(
        web_client_mock, web_search_mock_large, provider, config,
        session_mock):
    web_client_mock.get.return_value = web_search_mock_large

    search.search(
        config['spotify'], session_mock, web_client_mock,
        {'any': ['ABBA']}, types=['album', 'artist'])

    web_client_mock.get.assert_called_once_with(
        'search',
        params={
            'q': '"ABBA"',
            'limit': 50,
            'market': 'GB',
            'type': 'album,artist'})


def test_sets_market_parameter_from_user_country(
        web_client_mock, web_search_mock_large, provider):
    web_client_mock.user_country = 'SE'
    web_client_mock.get.return_value = web_search_mock_large

    provider.search({'any': ['ABBA']})

    web_client_mock.get.assert_called_once_with(
        'search',
        params={
            'q': '"ABBA"',
            'limit': 50,
            'market': 'SE',
            'type': 'album,artist,track'})


def test_handles_empty_response(web_client_mock, provider):
    web_client_mock.get.return_value = {}

    result = provider.search({'any': ['ABBA']})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'

    assert len(result.albums) == 0
    assert len(result.artists) == 0
    assert len(result.tracks) == 0


def test_exact_is_ignored(
        session_mock, sp_track_mock, web_client_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result1 = provider.search({'uri': ['spotify:track:abc']})
    result2 = provider.search({'uri': ['spotify:track:abc']}, exact=True)

    assert result1 == result2
