from __future__ import unicode_literals

import mock

import pytest

import responses

import mopidy_spotify
from mopidy_spotify import web


@pytest.fixture
def oauth_client(config):
    return web.OAuthClient(
        base_url='https://api.spotify.com/v1',
        refresh_url='https://auth.mopidy.com/spotify/token',
        client_id=config['spotify']['client_id'],
        client_secret=config['spotify']['client_secret'],
        proxy_config=None,
        expiry_margin=60)


@pytest.yield_fixture()
def mock_time():
    patcher = mock.patch.object(web.time, 'time')
    mock_time = patcher.start()
    yield mock_time
    patcher.stop()


def test_initial_refresh_token(oauth_client):
    assert oauth_client._should_refresh_token()


def test_expired_refresh_token(oauth_client, mock_time):
    oauth_client._expires = 1060
    mock_time.return_value = 1001
    assert oauth_client._should_refresh_token()


def test_still_valid_refresh_token(oauth_client, mock_time):
    oauth_client._expires = 1060
    mock_time.return_value = 1000
    assert not oauth_client._should_refresh_token()


def test_user_agent(oauth_client):
    assert oauth_client._session.headers['user-agent'].startswith(
        'Mopidy-Spotify/%s' % mopidy_spotify.__version__)


@responses.activate
def test_get_uses_new_access_token(
        web_oauth_mock, web_track_mock, mock_time, oauth_client):
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json=web_oauth_mock)
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json=web_track_mock)
    mock_time.return_value = 1000

    result = oauth_client.get('tracks/abc')

    assert len(responses.calls) == 2
    assert (responses.calls[0].request.url ==
            'https://auth.mopidy.com/spotify/token')
    assert (responses.calls[1].request.url ==
            'https://api.spotify.com/v1/tracks/abc')
    assert (responses.calls[1].request.headers['Authorization'] ==
            'Bearer NgCXRK...MzYjw')

    assert oauth_client._headers['Authorization'] == 'Bearer NgCXRK...MzYjw'
    assert oauth_client._expires == 4600

    assert result['uri'] == 'spotify:track:abc'


@responses.activate
def test_get_uses_existing_access_token(
        web_oauth_mock, web_track_mock, mock_time, oauth_client):
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json=web_oauth_mock)
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json=web_track_mock)
    mock_time.return_value = -1000

    oauth_client._headers['Authorization'] = 'Bearer 01234...abcde'

    result = oauth_client.get('tracks/abc')

    assert len(responses.calls) == 1
    assert (responses.calls[0].request.url ==
            'https://api.spotify.com/v1/tracks/abc')
    assert (responses.calls[0].request.headers['Authorization'] ==
            'Bearer 01234...abcde')

    assert oauth_client._headers['Authorization'] == 'Bearer 01234...abcde'
    assert result['uri'] == 'spotify:track:abc'


@responses.activate
def test_bad_client_credentials(oauth_client):
    bad_response = {
        'error': 'invalid_client',
        'error_description': 'Client not known.'}
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json=bad_response, status=401)

    result = oauth_client.get('tracks/abc')

    assert result == {}


@responses.activate
def test_auth_returns_invalid_json(oauth_client, caplog):
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token', body='scope')

    result = oauth_client.get('tracks/abc')

    assert result == {}
    assert ('JSON decoding https://auth.mopidy.com/spotify/token failed' in
            caplog.text())


@responses.activate
def test_spotify_returns_invalid_json(mock_time, oauth_client, caplog):
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        body='abc')
    mock_time.return_value = -1000

    result = oauth_client.get('tracks/abc')

    assert result == {}
    assert ('JSON decoding https://api.spotify.com/v1/tracks/abc failed' in
            caplog.text())


@responses.activate
def test_auth_offline(oauth_client, caplog):
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json={"error": "not found"}, status=404)

    result = oauth_client.get('tracks/abc')

    assert result == {}
    assert ('Fetching https://auth.mopidy.com/spotify/token failed' in
            caplog.text())


@responses.activate
def test_spotify_offline(web_oauth_mock, oauth_client, caplog):
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json=web_oauth_mock)
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json={"error": "not found"}, status=404)

    result = oauth_client.get('tracks/abc')

    assert result == {}
    assert ('Fetching https://api.spotify.com/v1/tracks/abc failed' in
            caplog.text())


@responses.activate
def test_auth_missing_access_token(web_oauth_mock, oauth_client, caplog):
    no_access_token = web_oauth_mock
    del(no_access_token['access_token'])
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json=no_access_token)

    oauth_client._headers['Authorization'] = 'Bearer 01234...abcde'

    result = oauth_client.get('tracks/abc')

    assert len(responses.calls) == 1
    assert oauth_client._headers['Authorization'] == 'Bearer 01234...abcde'
    assert result == {}
    assert 'OAuth token refresh failed: missing access_token' in caplog.text()


@responses.activate
def test_auth_wrong_token_type(web_oauth_mock, oauth_client, caplog):
    wrong_token_type = web_oauth_mock
    wrong_token_type['token_type'] = 'something'
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json=wrong_token_type)

    oauth_client._headers['Authorization'] = 'Bearer 01234...abcde'

    result = oauth_client.get('tracks/abc')

    assert len(responses.calls) == 1
    assert oauth_client._headers['Authorization'] == 'Bearer 01234...abcde'
    assert result == {}
    assert 'OAuth token refresh failed: wrong token_type' in caplog.text()
