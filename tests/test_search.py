from __future__ import unicode_literals

import json

import re

from mopidy import models

import requests

import responses

import spotify

import mopidy_spotify
from mopidy_spotify import search


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


@responses.activate
def test_search_returns_albums_and_artists_and_tracks(
        web_search_mock, provider, caplog):
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body=json.dumps(web_search_mock))

    result = provider.search({'any': ['ABBA']})

    assert len(responses.calls) == 1

    uri_parts = sorted(re.split('[?&]', responses.calls[0].request.url))
    assert (uri_parts == [
        'https://api.spotify.com/v1/search',
        'limit=50',
        'q=%22ABBA%22',
        'type=album%2Cartist%2Ctrack'])

    assert responses.calls[0].request.headers['User-Agent'].startswith(
        'Mopidy-Spotify/%s' % mopidy_spotify.__version__)

    assert 'Searching Spotify for: "ABBA"' in caplog.text()

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'

    assert len(result.albums) == 1
    assert result.albums[0].uri == 'spotify:album:def'

    assert len(result.artists) == 1
    assert result.artists[0].uri == 'spotify:artist:abba'

    assert len(result.tracks) == 2
    assert result.tracks[0].uri == 'spotify:track:abc'


@responses.activate
def test_search_limits_number_of_results(
        web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 4
    config['spotify']['search_artist_count'] = 5
    config['spotify']['search_track_count'] = 6

    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body=json.dumps(web_search_mock_large))

    result = provider.search({'any': ['ABBA']})

    assert len(result.albums) == 4
    assert len(result.artists) == 5
    assert len(result.tracks) == 6


@responses.activate
def test_sets_api_limit_to_album_count_when_max(
        web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 6
    config['spotify']['search_artist_count'] = 2
    config['spotify']['search_track_count'] = 2

    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body=json.dumps(web_search_mock_large))

    result = provider.search({'any': ['ABBA']})

    assert len(responses.calls) == 1

    uri_parts = sorted(re.split('[?&]', responses.calls[0].request.url))
    assert (uri_parts == [
        'https://api.spotify.com/v1/search',
        'limit=6',
        'q=%22ABBA%22',
        'type=album%2Cartist%2Ctrack'])

    assert len(result.albums) == 6


@responses.activate
def test_sets_api_limit_to_artist_count_when_max(
        web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 2
    config['spotify']['search_artist_count'] = 6
    config['spotify']['search_track_count'] = 2

    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body=json.dumps(web_search_mock_large))

    result = provider.search({'any': ['ABBA']})

    assert len(responses.calls) == 1

    uri_parts = sorted(re.split('[?&]', responses.calls[0].request.url))
    assert (uri_parts == [
        'https://api.spotify.com/v1/search',
        'limit=6',
        'q=%22ABBA%22',
        'type=album%2Cartist%2Ctrack'])

    assert len(result.artists) == 6


@responses.activate
def test_sets_api_limit_to_track_count_when_max(
        web_search_mock_large, provider, config):
    config['spotify']['search_album_count'] = 2
    config['spotify']['search_artist_count'] = 2
    config['spotify']['search_track_count'] = 6

    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body=json.dumps(web_search_mock_large))

    result = provider.search({'any': ['ABBA']})

    assert len(responses.calls) == 1

    uri_parts = sorted(re.split('[?&]', responses.calls[0].request.url))
    assert (uri_parts == [
        'https://api.spotify.com/v1/search',
        'limit=6',
        'q=%22ABBA%22',
        'type=album%2Cartist%2Ctrack'])

    assert len(result.tracks) == 6


@responses.activate
def test_sets_types_parameter(
        web_search_mock_large, provider, config, session_mock):
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body=json.dumps(web_search_mock_large))

    search.search(
        config['spotify'], session_mock, requests.Session(),
        {'any': ['ABBA']}, types=['album', 'artist'])

    assert len(responses.calls) == 1

    uri_parts = sorted(re.split('[?&]', responses.calls[0].request.url))
    assert (uri_parts == [
        'https://api.spotify.com/v1/search',
        'limit=50',
        'q=%22ABBA%22',
        'type=album%2Cartist'])


@responses.activate
def test_handles_empty_response(
        web_search_mock_large, provider):
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/search',
        body={})

    result = provider.search({'any': ['ABBA']})

    assert isinstance(result, models.SearchResult)
    assert result.uri == 'spotify:search:%22ABBA%22'

    assert len(result.albums) == 0
    assert len(result.artists) == 0
    assert len(result.tracks) == 0


def test_exact_is_ignored(session_mock, sp_track_mock, provider):
    session_mock.get_link.return_value = sp_track_mock.link

    result1 = provider.search({'uri': ['spotify:track:abc']})
    result2 = provider.search({'uri': ['spotify:track:abc']}, exact=True)

    assert result1 == result2
