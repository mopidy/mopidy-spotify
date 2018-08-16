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
            caplog.text)


@responses.activate
def test_spotify_returns_invalid_json(mock_time, oauth_client, caplog):
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        body='abc')
    mock_time.return_value = -1000

    result = oauth_client.get('tracks/abc')

    assert result == {}
    assert ('JSON decoding https://api.spotify.com/v1/tracks/abc failed' in
            caplog.text)


@responses.activate
def test_auth_offline(oauth_client, caplog):
    responses.add(
        responses.POST, 'https://auth.mopidy.com/spotify/token',
        json={"error": "not found"}, status=404)

    result = oauth_client.get('tracks/abc')

    assert result == {}
    assert ('Fetching https://auth.mopidy.com/spotify/token failed' in
            caplog.text)


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
            caplog.text)


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
    assert 'OAuth token refresh failed: missing access_token' in caplog.text


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
    assert 'OAuth token refresh failed: wrong token_type' in caplog.text


@pytest.mark.parametrize('header,expected', [
    ('no-store', 100),
    ('max-age=1', 101),
    ('max-age=2000', 2100),
    ('max-age=2000, foo', 2100),
    ('stuff, max-age=500', 600),
    ('max-age=junk', 100),
    ('', 100),
])
def test_parse_cache_control(mock_time, oauth_client, header, expected):
    mock_time.return_value = 100
    mock_response = mock.Mock(headers={'Cache-Control': header})

    expires = oauth_client._parse_cache_control(mock_response)
    assert expires == expected


@pytest.mark.parametrize('status_code,expected', [
    (200, True),
    (301, True),
    (400, False),
])
def test_web_response_is_valid(web_response_mock, status_code, expected):
    response = web.WebResponse(
        'https://api.spotify.com/v1/tracks/abc', {}, status_code=status_code)
    assert response.valid == expected


@pytest.mark.parametrize('cache,valid,expected', [
    (None, False, False),
    (None, True, False),
    ({}, False, False),
    ({}, True, True),
])
def test_should_cache_response(oauth_client, cache, valid, expected):
    response_mock = mock.Mock(valid=valid)
    result = oauth_client._should_cache_response(cache, response_mock)
    assert result == expected


@pytest.mark.parametrize('path,params,expected', [
    ('tracks/abc?foo=bar&foo=5', None, 'tracks/abc?foo=5'),
    ('tracks/abc?foo=bar&bar=9', None, 'tracks/abc?bar=9&foo=bar'),
    ('tracks/abc', {'foo': 'bar'}, 'tracks/abc?foo=bar'),
    ('tracks/abc?foo=bar', {'bar': 'foo'}, 'tracks/abc?bar=foo&foo=bar'),
    ('tracks/abc?foo=bar', {'foo': 'foo'}, 'tracks/abc?foo=foo'),
])
def test_normalise_query_string(oauth_client, path, params, expected):
    result = oauth_client._normalise_query_string(path, params)
    assert result == expected


@responses.activate
def test_web_response(web_track_mock, mock_time, oauth_client):
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json=web_track_mock, adding_headers={'Cache-Control': 'max-age=2001'},
        status=301)
    mock_time.return_value = -1000

    result = oauth_client.get('https://api.spotify.com/v1/tracks/abc')

    assert isinstance(result, web.WebResponse)
    assert result.url == 'https://api.spotify.com/v1/tracks/abc'
    assert result._status_code == 301
    assert result._expires == 1001
    assert not result.expired
    assert result.valid
    assert result['uri'] == 'spotify:track:abc'


@responses.activate
def test_cache_miss(web_track_mock, mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json=web_track_mock)
    mock_time.return_value = -1000

    result = oauth_client.get('https://api.spotify.com/v1/tracks/abc', cache)
    assert len(responses.calls) == 1
    assert result['uri'] == 'spotify:track:abc'
    assert oauth_client._should_cache_response(cache, result)
    assert cache['https://api.spotify.com/v1/tracks/abc'] == result


@responses.activate
def test_cache_hit_not_expired(web_response_mock, mock_time, oauth_client):
    cache = {'https://api.spotify.com/v1/tracks/abc': web_response_mock}
    oauth_client._expires = 2000
    mock_time.return_value = 999

    assert not web_response_mock.expired

    result = oauth_client.get('https://api.spotify.com/v1/tracks/abc', cache)
    assert len(responses.calls) == 0
    assert result['uri'] == 'spotify:track:abc'


@responses.activate
def test_cache_hit_expired(web_response_mock, oauth_client, mock_time):
    cache = {'https://api.spotify.com/v1/tracks/abc': web_response_mock}
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json={'uri': 'new'})
    oauth_client._expires = 2000
    mock_time.return_value = 1001

    assert web_response_mock.expired

    result = oauth_client.get('https://api.spotify.com/v1/tracks/abc', cache)
    assert len(responses.calls) == 1
    assert result['uri'] == 'new'


@responses.activate
def test_dont_cache_bad_status(web_track_mock, mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json=web_track_mock, status=404)
    mock_time.return_value = -1000

    result = oauth_client.get('https://api.spotify.com/v1/tracks/abc', cache)
    assert result._status_code == 404
    assert not oauth_client._should_cache_response(cache, result)
    assert 'https://api.spotify.com/v1/tracks/abc' not in cache


@responses.activate
def test_cache_key_uses_path(web_track_mock, mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc',
        json=web_track_mock)
    mock_time.return_value = -1000

    result = oauth_client.get('tracks/abc', cache)
    assert len(responses.calls) == 1
    assert cache['tracks/abc'] == result
    assert result.url == 'https://api.spotify.com/v1/tracks/abc'


@responses.activate
def test_cache_normalised_query_string(mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc?b=bar&f=foo',
        json={'uri': 'foobar'}, match_querystring=True)
    responses.add(
        responses.GET, 'https://api.spotify.com/v1/tracks/abc?b=bar&f=cat',
        json={'uri': 'cat'}, match_querystring=True)
    mock_time.return_value = -1000

    r1 = oauth_client.get('tracks/abc?f=foo&b=bar', cache)
    r2 = oauth_client.get('tracks/abc?b=bar&f=foo', cache)
    r3 = oauth_client.get('tracks/abc?b=bar&f=cat', cache)
    assert len(responses.calls) == 2
    assert r1['uri'] == 'foobar'
    assert r1 == r2
    assert r1 != r3
    assert 'tracks/abc?b=bar&f=foo' in cache
    assert 'tracks/abc?b=bar&f=cat' in cache
