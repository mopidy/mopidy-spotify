import urllib
from datetime import UTC, datetime
from unittest import mock

import pytest
import requests
import responses
from responses import matchers

import mopidy_spotify
from mopidy_spotify import web


@pytest.fixture
def oauth_client(config):
    return web.OAuthClient(
        base_url="https://api.spotify.com/v1",
        refresh_url="https://auth.mopidy.com/spotify/token",
        client_id=config["spotify"]["client_id"],
        client_secret=config["spotify"]["client_secret"],
        proxy_config=None,
        expiry_margin=60,
    )


@pytest.fixture
def mock_time():
    patcher = mock.patch.object(web.time, "time")
    mock_time = patcher.start()
    yield mock_time
    patcher.stop()


@pytest.fixture
def mock_now():
    patcher = mock.patch("mopidy_spotify.web.datetime")
    mock_datetime = patcher.start()
    mock_datetime.now = mock.Mock()
    mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw, tzinfo=UTC)
    yield mock_datetime.now
    patcher.stop()


@pytest.fixture
def skip_refresh_token():
    patcher = mock.patch.object(
        web.OAuthClient, "_should_refresh_token", return_value=False
    )
    yield patcher.start()
    patcher.stop()


def test_should_refresh_token_requires_lock(oauth_client):
    with pytest.raises(web.OAuthTokenRefreshError):
        oauth_client._should_refresh_token()


def test_refresh_token_requires_lock(oauth_client):
    with pytest.raises(web.OAuthTokenRefreshError):
        oauth_client._refresh_token()


def test_initial_refresh_token(oauth_client):
    with oauth_client._refresh_mutex:
        assert oauth_client._should_refresh_token()


def test_expired_refresh_token(oauth_client, mock_time):
    oauth_client._expires = 1060
    mock_time.return_value = 1001
    with oauth_client._refresh_mutex:
        assert oauth_client._should_refresh_token()


def test_still_valid_refresh_token(oauth_client, mock_time):
    oauth_client._expires = 1060
    mock_time.return_value = 1000
    with oauth_client._refresh_mutex:
        assert not oauth_client._should_refresh_token()


def test_user_agent(oauth_client):
    assert oauth_client._session.headers["user-agent"].startswith(
        f"Mopidy-Spotify/{mopidy_spotify.__version__}"
    )


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, 0),
        ("", 0),
        ("1", 1),
        ("-1", 0),
        (" 2 ", 2),
        (" 2 foo", 0),
        ("2 9", 0),
        ("foo", 0),
        ("Wed, 07 Dec 2022 11:24:16", 0),
        ("Wed, 07 Dec 2022 11:29:16", 110),
        ("Wed, 77 Dec 2022 11:29:16", 0),
        ("foobar", 0),
    ],
)
def test_parse_retry_after(oauth_client, mock_now, header, expected):
    mock_now.return_value = datetime(2022, 12, 7, 11, 27, 26, 0, tzinfo=UTC)
    mock_response = mock.Mock(headers={"Retry-After": header})
    result = oauth_client._parse_retry_after(mock_response)

    assert result == expected


@responses.activate
def test_request_exception(oauth_client, caplog):
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        body=requests.RequestException("foo"),
    )
    oauth_client._number_of_retries = 1

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert "Fetching https://auth.mopidy.com/spotify/token failed: foo" in caplog.text


@responses.activate
def test_get_uses_new_access_token(
    web_oauth_mock, web_track_mock, mock_time, oauth_client
):
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json=web_oauth_mock,
    )
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
    )
    mock_time.return_value = 1000

    result = oauth_client.get("tracks/abc")

    assert len(responses.calls) == 2
    assert responses.calls[0].request.url == "https://auth.mopidy.com/spotify/token"
    assert responses.calls[1].request.url == "https://api.spotify.com/v1/tracks/abc"
    assert (
        responses.calls[1].request.headers["Authorization"] == "Bearer NgCXRK...MzYjw"
    )

    assert oauth_client._headers["Authorization"] == "Bearer NgCXRK...MzYjw"
    assert oauth_client._expires == 4600

    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_get_uses_existing_access_token(
    web_oauth_mock, web_track_mock, mock_time, oauth_client
):
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json=web_oauth_mock,
    )
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
    )
    mock_time.return_value = -1000

    oauth_client._headers["Authorization"] = "Bearer 01234...abcde"

    result = oauth_client.get("tracks/abc")

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == "https://api.spotify.com/v1/tracks/abc"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer 01234...abcde"

    assert oauth_client._headers["Authorization"] == "Bearer 01234...abcde"
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_bad_client_credentials(oauth_client):
    bad_response = {
        "error": "invalid_client",
        "error_description": "Client not known.",
    }
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json=bad_response,
        status=401,
    )

    result = oauth_client.get("tracks/abc")

    assert result == {}


@responses.activate
def test_auth_returns_invalid_json(oauth_client, caplog):
    responses.add(responses.POST, "https://auth.mopidy.com/spotify/token", body="scope")

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert "JSON decoding https://auth.mopidy.com/spotify/token failed" in caplog.text


@responses.activate
def test_spotify_returns_invalid_json(skip_refresh_token, oauth_client, caplog):
    responses.add(responses.GET, "https://api.spotify.com/v1/tracks/abc", body="abc")

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert "JSON decoding https://api.spotify.com/v1/tracks/abc failed" in caplog.text


@responses.activate
def test_auth_offline(oauth_client, caplog):
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json={"error": "not found"},
        status=404,
    )

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert "Fetching https://auth.mopidy.com/spotify/token failed" in caplog.text


@responses.activate
def test_spotify_offline(web_oauth_mock, oauth_client, caplog):
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json=web_oauth_mock,
    )
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json={"error": "not found"},
        status=404,
    )

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert "Fetching https://api.spotify.com/v1/tracks/abc failed" in caplog.text


@responses.activate
def test_auth_missing_access_token(web_oauth_mock, oauth_client, caplog):
    no_access_token = web_oauth_mock
    del no_access_token["access_token"]
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json=no_access_token,
    )

    oauth_client._headers["Authorization"] = "Bearer 01234...abcde"

    result = oauth_client.get("tracks/abc")

    assert len(responses.calls) == 1
    assert oauth_client._headers["Authorization"] == "Bearer 01234...abcde"
    assert result == {}
    assert "OAuth token refresh failed: missing access_token" in caplog.text


@responses.activate
def test_auth_wrong_token_type(web_oauth_mock, oauth_client, caplog):
    wrong_token_type = web_oauth_mock
    wrong_token_type["token_type"] = "something"  # noqa: S105
    responses.add(
        responses.POST,
        "https://auth.mopidy.com/spotify/token",
        json=wrong_token_type,
    )

    oauth_client._headers["Authorization"] = "Bearer 01234...abcde"

    result = oauth_client.get("tracks/abc")

    assert len(responses.calls) == 1
    assert oauth_client._headers["Authorization"] == "Bearer 01234...abcde"
    assert result == {}
    assert "OAuth token refresh failed: wrong token_type" in caplog.text


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("no-store", 100),
        ("max-age=1", 101),
        ("max-age=2000", 2100),
        ("max-age=2000, foo", 2100),
        ("stuff, max-age=500", 600),
        ("max-age=junk", 100),
        ("", 100),
    ],
)
def test_parse_cache_control(mock_time, header, expected):
    mock_time.return_value = 100
    mock_response = mock.Mock(headers={"Cache-Control": header})

    expires = web.WebResponse._parse_cache_control(mock_response)
    assert expires == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("", None),
        ('" "', None),
        ("33a6ff", None),
        ('"33a6ff"', '"33a6ff"'),
        ('"33"a6ff"', None),
        ('"33\na6ff"', None),
        ('W/"33a6ff"', '"33a6ff"'),
        ('"#aa44-cc1-23==@!"', '"#aa44-cc1-23==@!"'),
    ],
)
def test_parse_etag(header, expected):
    mock_time.return_value = 100
    mock_response = mock.Mock(headers={"ETag": header})

    expires = web.WebResponse._parse_etag(mock_response)
    assert expires == expected


@pytest.mark.parametrize(
    ("status_code", "expected"), [(200, True), (301, True), (400, False)]
)
def test_web_response_status_ok(status_code, expected):
    response = web.WebResponse("https://foo.com", {}, status_code=status_code)
    assert response.status_ok == expected


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(200, False), (301, False), (304, True), (400, False)],
)
def test_web_response_status_unchanged(status_code, expected):
    response = web.WebResponse("https://foo.com", {}, status_code=status_code)
    assert not response._from_cache
    assert response.status_unchanged == expected


def test_web_response_status_unchanged_from_cache():
    response = web.WebResponse("https://foo.com", {})

    assert not response.status_unchanged

    response.still_valid(expiry_strategy=web.ExpiryStrategy.FORCE_FRESH)

    assert response.status_unchanged

    response.updated(response)

    assert not response.status_unchanged


@pytest.mark.parametrize(
    ("etag", "expected"),
    [
        ('"1234"', {"If-None-Match": '"1234"'}),
        ("fish", {"If-None-Match": "fish"}),
        (None, {}),
    ],
)
def test_web_response_etag_headers(etag, expected):
    response = web.WebResponse("https://foo.com", {}, etag=etag)
    assert response.etag_headers == expected


@pytest.mark.parametrize(
    ("etag", "status", "expected", "expected_etag", "expected_msg"),
    [
        ("abcd", 200, False, "abcd", "ETag mismatch"),
        ("abcd", 404, False, "abcd", "ETag mismatch"),
        ("abcd", 304, True, "efgh", "ETag match"),
        (None, 304, False, None, ""),
    ],
)
def test_web_response_etag_updated(
    etag, status, expected, expected_etag, expected_msg, caplog
):
    response = web.WebResponse("https://foo.com", {}, expires=1.0, etag=etag)
    new_response = web.WebResponse(
        "https://foo.com", {}, expires=2.0, etag="efgh", status_code=status
    )
    assert response.updated(new_response) == expected
    assert response._etag == expected_etag
    assert expected_msg in caplog.text


def test_web_response_etag_updated_different(web_response_mock_etag, caplog):
    new_response = web.WebResponse("https://foo.com", {}, status_code=304)
    assert not web_response_mock_etag.updated(new_response)
    assert "ETag mismatch (different URI) for" in caplog.text


@pytest.mark.parametrize(
    ("cache", "ok", "expected"),
    [
        (None, False, False),
        (None, True, False),
        ({}, False, False),
        ({}, True, True),
    ],
)
def test_should_cache_response(oauth_client, cache, ok, expected):
    response_mock = mock.Mock(status_ok=ok)
    result = oauth_client._should_cache_response(cache, response_mock)
    assert result == expected


@pytest.mark.parametrize(
    ("path", "params", "expected"),
    [
        ("tracks/abc?foo=bar&foo=5", None, "tracks/abc?foo=5"),
        ("tracks/abc?foo=bar&bar=9", None, "tracks/abc?bar=9&foo=bar"),
        ("tracks/abc", {"foo": "bar"}, "tracks/abc?foo=bar"),
        ("tracks/abc?foo=bar", {"bar": "foo"}, "tracks/abc?bar=foo&foo=bar"),
        ("tracks/abc?foo=bar", {"foo": "foo"}, "tracks/abc?foo=foo"),
    ],
)
def test_normalise_query_string(oauth_client, path, params, expected):
    result = oauth_client._normalise_query_string(path, params)
    assert result == expected


@responses.activate
def test_web_response(web_track_mock, mock_time, skip_refresh_token, oauth_client):
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
        adding_headers={"Cache-Control": "max-age=2001", "ETag": '"12345"'},
        status=301,
    )
    mock_time.return_value = 53

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc")

    assert isinstance(result, web.WebResponse)
    assert result.url == "https://api.spotify.com/v1/tracks/abc"
    assert result._status_code == 301
    assert result._expires == 2054
    assert result._etag == '"12345"'
    assert result.still_valid()
    assert result.status_ok
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_cache_miss(web_track_mock, skip_refresh_token, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
    )

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert len(responses.calls) == 1
    assert result["uri"] == "spotify:track:abc"
    assert oauth_client._should_cache_response(cache, result)
    assert cache["https://api.spotify.com/v1/tracks/abc"] == result


@responses.activate
def test_cache_response_still_valid(
    web_response_mock, mock_time, skip_refresh_token, oauth_client, caplog
):
    cache = {"https://api.spotify.com/v1/tracks/abc": web_response_mock}
    mock_time.return_value = 0

    assert web_response_mock.still_valid()
    assert "Cached data fresh for" in caplog.text

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert len(responses.calls) == 0
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_cache_response_expired(
    web_response_mock, skip_refresh_token, oauth_client, caplog
):
    cache = {"https://api.spotify.com/v1/tracks/abc": web_response_mock}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json={"uri": "new"},
    )

    assert not web_response_mock.still_valid()
    assert "Cached data expired for" in caplog.text

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert len(responses.calls) == 1
    assert result["uri"] == "new"


def test_cache_response_still_valid_strategy(mock_time):
    response = web.WebResponse("foo", {}, expires=9999 + 1)
    mock_time.return_value = 9999

    assert response.still_valid() is True
    assert response.still_valid(expiry_strategy=None) is True
    assert response.still_valid(expiry_strategy=web.ExpiryStrategy.FORCE_FRESH) is True
    assert (
        response.still_valid(expiry_strategy=web.ExpiryStrategy.FORCE_EXPIRED) is False
    )


@responses.activate
def test_cache_response_force_fresh(
    web_response_mock, skip_refresh_token, oauth_client, mock_time, caplog
):
    cache = {"https://api.spotify.com/v1/tracks/abc": web_response_mock}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json={"uri": "new"},
    )
    mock_time.return_value = 9999

    assert not web_response_mock.still_valid()
    assert "Cached data expired for" in caplog.text

    assert web_response_mock.still_valid(expiry_strategy=web.ExpiryStrategy.FORCE_FRESH)
    assert "Cached data force-fresh for" in caplog.text

    result = oauth_client.get(
        "https://api.spotify.com/v1/tracks/abc",
        cache,
        expiry_strategy=web.ExpiryStrategy.FORCE_FRESH,
    )
    assert len(responses.calls) == 0
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_dont_cache_bad_status(web_track_mock, skip_refresh_token, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
        status=404,
    )

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert result._status_code == 404
    assert not oauth_client._should_cache_response(cache, result)
    assert "https://api.spotify.com/v1/tracks/abc" not in cache


@responses.activate
def test_cache_key_uses_path(web_track_mock, skip_refresh_token, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
    )

    result = oauth_client.get("tracks/abc", cache)
    assert len(responses.calls) == 1
    assert cache["tracks/abc"] == result
    assert result.url == "https://api.spotify.com/v1/tracks/abc"


@responses.activate
def test_cache_normalised_query_string(mock_time, skip_refresh_token, oauth_client):
    cache = {}
    url = "https://api.spotify.com/v1/tracks/abc"
    responses.add(
        responses.GET,
        url,
        json={"uri": "foobar"},
        match=[matchers.query_string_matcher("b=bar&f=foo")],
    )
    responses.add(
        responses.GET,
        url,
        json={"uri": "cat"},
        match=[matchers.query_string_matcher("b=bar&f=cat")],
    )
    mock_time.return_value = 0

    r1 = oauth_client.get("tracks/abc?f=foo&b=bar", cache)
    r2 = oauth_client.get("tracks/abc?b=bar&f=foo", cache)
    r3 = oauth_client.get("tracks/abc?b=bar&f=cat", cache)
    assert len(responses.calls) == 2
    assert r1["uri"] == "foobar"
    assert r1 == r2
    assert r1 != r3
    assert "tracks/abc?b=bar&f=foo" in cache
    assert "tracks/abc?b=bar&f=cat" in cache


@pytest.mark.parametrize(("status", "unchanged"), [(304, True), (200, False)])
@responses.activate
def test_cache_expired_with_etag(
    web_response_mock_etag,
    mock_time,
    skip_refresh_token,
    oauth_client,
    status,
    unchanged,
    caplog,
):
    cache = {"tracks/abc": web_response_mock_etag}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        status=status,
    )
    mock_time.return_value = web_response_mock_etag._expires + 1
    assert not cache["tracks/abc"].still_valid()

    result = oauth_client.get("tracks/abc", cache)
    assert len(responses.calls) == 1
    assert responses.calls[0].request.headers["If-None-Match"] == '"1234"'
    assert cache["tracks/abc"] == result
    assert result.status_unchanged is unchanged
    assert (result.items() == web_response_mock_etag.items()) == unchanged


@responses.activate
def test_cache_miss_no_etag(web_response_mock_etag, skip_refresh_token, oauth_client):
    cache = {"tracks/abc": web_response_mock_etag}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/xyz",
        json={"uri": "spotify:track:xyz"},
    )

    result = oauth_client.get("tracks/xyz", cache)
    assert len(responses.calls) == 1
    assert "If-None-Match" not in responses.calls[0].request.headers
    assert result["uri"] == "spotify:track:xyz"
    assert cache["tracks/xyz"] == result


def test_increase_expiry(web_response_mock):
    web_response_mock.increase_expiry(30)

    assert web_response_mock._expires == 1030


def test_increase_expiry_skipped_for_bad_status(web_response_mock):
    web_response_mock._status_code = 404

    web_response_mock.increase_expiry(30)

    assert web_response_mock._expires == 1000


def test_increase_expiry_skipped_for_cached_response(web_response_mock):
    web_response_mock._from_cache = True

    web_response_mock.increase_expiry(30)

    assert web_response_mock._expires == 1000


@responses.activate
def test_fresh_response_changed(skip_refresh_token, oauth_client):
    cache = {}
    responses.add(responses.GET, "https://api.spotify.com/v1/foo", json={})

    result = oauth_client.get("foo", cache)

    assert len(responses.calls) == 1
    assert not result.status_unchanged


@responses.activate
def test_cached_response_unchanged(
    web_response_mock, skip_refresh_token, oauth_client, mock_time
):
    cache = {"foo": web_response_mock}
    responses.add(responses.GET, "https://api.spotify.com/v1/foo", json={})
    mock_time.return_value = 0

    result = oauth_client.get("foo", cache)

    assert len(responses.calls) == 0
    assert result.status_unchanged


@responses.activate
def test_updated_responses_changed(web_response_mock, oauth_client, mock_time):
    cache = {"foo": web_response_mock}
    responses.add(responses.GET, "https://api.spotify.com/v1/foo", json={})
    oauth_client._expires = 2000
    mock_time.return_value = 1001

    result = oauth_client.get("foo", cache)

    assert len(responses.calls) == 1
    assert not result.status_unchanged


@pytest.fixture
def spotify_client(config):
    client = web.SpotifyOAuthClient(
        client_id=config["spotify"]["client_id"],
        client_secret=config["spotify"]["client_secret"],
        proxy_config=None,
    )
    client.user_id = "alice"
    return client


def url(endpoint):
    return f"https://api.spotify.com/v1/{endpoint}"


@pytest.fixture(scope="module")
def playlist_parms():
    return urllib.parse.urlencode(
        {
            "fields": web.SpotifyOAuthClient.PLAYLIST_FIELDS,
            "market": "from_token",
        }
    )


@pytest.fixture(scope="module")
def playlist_tracks_parms():
    return urllib.parse.urlencode(
        {"fields": web.SpotifyOAuthClient.TRACK_FIELDS, "market": "from_token"}
    )


@pytest.fixture
def bar_playlist(playlist_parms):
    return {
        "href": url(f"playlists/bar?{playlist_parms}"),
        "tracks": {"items": [0]},
    }


@pytest.fixture
def foo_playlist_tracks(playlist_tracks_parms):
    return {
        "href": url(f"playlists/foo/tracks?{playlist_tracks_parms}"),
        "items": [3, 4, 5],
    }


@pytest.fixture
def foo_playlist(playlist_parms, foo_playlist_tracks):
    return {
        "href": url(f"playlists/foo?{playlist_parms}"),
        "tracks": {"items": [1, 2], "next": foo_playlist_tracks["href"]},
    }


@pytest.fixture
def foo_album_next_tracks():
    params = urllib.parse.urlencode({"market": "from_token", "offset": 3})
    return {
        "href": url(f"albums/foo/tracks?{params}"),
        "items": [6, 7, 8],
        "next": None,
    }


@pytest.fixture
def foo_album(foo_album_next_tracks):
    params = urllib.parse.urlencode({"market": "from_token"})
    return {
        "href": url(f"albums/foo?{params}"),
        "id": "foo",
        "tracks": {
            "href": url(f"albums/foo/tracks?{params}"),
            "items": [3, 4, 5],
            "next": foo_album_next_tracks["href"],
        },
    }


@pytest.fixture
def foo_album_response(foo_album):
    return web.WebResponse(foo_album["href"], foo_album)


@pytest.fixture
def artist_albums_mock(web_album_mock_base, web_album_mock_base2):
    params = urllib.parse.urlencode(
        {"market": "from_token", "include_groups": "single,album"}
    )
    return {
        "href": url(f"artists/abba/albums?{params}"),
        "items": [web_album_mock_base, web_album_mock_base2],
        "next": None,
    }


@pytest.mark.usefixtures("skip_refresh_token")
class TestSpotifyOAuthClient:
    @pytest.mark.parametrize(
        "field",
        [
            ("next"),
            ("items(track"),
            ("type"),
            ("uri"),
            ("name"),
            ("is_playable"),
            ("linked_from"),
        ],
    )
    def test_track_required_fields(self, field):
        assert field in web.SpotifyOAuthClient.TRACK_FIELDS

    @pytest.mark.parametrize(
        "field",
        [("name"), ("type"), ("uri"), ("snapshot_id"), ("tracks")],
    )
    def test_playlist_required_fields(self, field):
        assert field in web.SpotifyOAuthClient.PLAYLIST_FIELDS

    def test_configures_auth(self):
        client = web.SpotifyOAuthClient(
            client_id="1234567",
            client_secret="AbCdEfG",  # noqa: S106
            proxy_config=None,
        )

        assert client._auth == ("1234567", "AbCdEfG")

    def test_configures_proxy(self):
        proxy_config = {
            "scheme": "https",
            "hostname": "my-proxy.example.com",
            "port": 8080,
            "username": "alice",
            "password": "s3cret",
        }
        client = web.SpotifyOAuthClient(
            client_id=None, client_secret=None, proxy_config=proxy_config
        )

        assert (
            client._session.proxies["https"]
            == "https://alice:s3cret@my-proxy.example.com:8080"
        )

    def test_configures_urls(self, spotify_client):
        assert spotify_client._base_url == "https://api.spotify.com/v1"
        assert spotify_client._refresh_url == "https://auth.mopidy.com/spotify/token"

    @responses.activate
    def test_login_alice(self, spotify_client, caplog):
        spotify_client.user_id = None
        responses.add(responses.GET, url("me"), json={"id": "alice"})

        assert spotify_client.login()
        assert spotify_client.user_id == "alice"
        assert "Logged into Spotify Web API as alice" in caplog.text

    @responses.activate
    def test_login_fails(self, spotify_client, caplog):
        spotify_client.user_id = None
        responses.add(responses.GET, url("me"), json={})

        assert not spotify_client.login()
        assert spotify_client.user_id is None
        assert "Failed to load Spotify user profile" in caplog.text

    @responses.activate
    def test_get_one_error(self, spotify_client, caplog):
        responses.add(
            responses.GET,
            url("foo"),
            json={"error": "bar"},
        )

        result = spotify_client.get_one("foo", json={})

        assert result == {}
        assert "Spotify Web API request failed: bar" in caplog.text

    @responses.activate
    def test_get_one_cached(self, spotify_client):
        responses.add(responses.GET, url("foo"))

        spotify_client.get_one("foo")
        spotify_client.get_one("foo")

        assert len(responses.calls) == 1
        assert "foo" in spotify_client._cache

    @responses.activate
    def test_get_one_increased_expiry(self, mock_time, spotify_client):
        responses.add(responses.GET, url("foo"))
        mock_time.return_value = 1000

        result = spotify_client.get_one("foo")

        assert result._expires == 1000 + spotify_client.DEFAULT_EXTRA_EXPIRY

    @responses.activate
    def test_get_one_retry_header(self, spotify_client, caplog):
        spotify_client._timeout = 0
        responses.add(
            responses.GET,
            url("foo"),
            status=429,
            adding_headers={"Retry-After": "66"},
        )

        result = spotify_client.get_one("foo")

        assert result == {}
        assert (
            "Retrying https://api.spotify.com/v1/foo in 66.000 seconds." in caplog.text
        )

    @responses.activate
    def test_get_all(self, spotify_client):
        responses.add(responses.GET, url("page1"), json={"n": 1, "next": "page2"})
        responses.add(responses.GET, url("page2"), json={"n": 2})

        results = list(spotify_client.get_all("page1"))

        assert len(results) == 2
        assert results[0].get("n") == 1
        assert results[1].get("n") == 2

    @responses.activate
    def test_get_all_none(self, spotify_client):
        results = list(spotify_client.get_all(None))

        assert len(responses.calls) == 0
        assert len(results) == 0

    @responses.activate
    def test_get_user_playlists_empty(self, spotify_client):
        responses.add(responses.GET, url("users/alice/playlists"), json={})

        result = list(spotify_client.get_user_playlists())

        assert len(responses.calls) == 1
        assert len(result) == 0

    @pytest.mark.parametrize(
        ("refresh", "strategy"),
        [
            (True, web.ExpiryStrategy.FORCE_EXPIRED),
            (False, None),
        ],
    )
    def test_get_user_playlists_get_all(self, spotify_client, refresh, strategy):
        spotify_client.get_all = mock.Mock(return_value=[])

        result = list(spotify_client.get_user_playlists(refresh=refresh))

        spotify_client.get_all.assert_called_once_with(
            "users/alice/playlists",
            params={"limit": 50},
            expiry_strategy=strategy,
        )
        assert len(result) == 0

    @responses.activate
    def test_get_user_playlists_sets_params(self, spotify_client):
        responses.add(responses.GET, url("users/alice/playlists"), json={})

        list(spotify_client.get_user_playlists())

        assert len(responses.calls) == 1
        encoded_params = urllib.parse.urlencode({"limit": 50})
        assert responses.calls[0].request.url == url(
            f"users/alice/playlists?{encoded_params}"
        )

    @responses.activate
    def test_get_user_playlists(self, spotify_client):
        responses.add(
            responses.GET,
            url("users/alice/playlists?limit=50"),
            json={
                "next": url("users/alice/playlists?offset=50"),
                "items": ["playlist0", "playlist1", "playlist2"],
            },
        )
        responses.add(
            responses.GET,
            url("users/alice/playlists?limit=50&offset=50"),
            json={
                "next": None,
                "items": ["playlist3", "playlist4", "playlist5"],
            },
        )

        results = list(spotify_client.get_user_playlists())

        assert len(responses.calls) == 2
        assert len(results) == 6
        assert [f"playlist{i}" for i in range(6)] == results

    @responses.activate
    def test_with_all_tracks_error(self, spotify_client, foo_album_response, caplog):
        responses.add(
            responses.GET,
            foo_album_response["tracks"]["next"],
            json={"error": "baz"},
        )

        result = spotify_client._with_all_tracks(foo_album_response)

        assert result == {}
        assert "Spotify Web API request failed: baz" in caplog.text

    @responses.activate
    def test_with_all_tracks(
        self, spotify_client, foo_album_response, foo_album_next_tracks
    ):
        responses.add(
            responses.GET,
            foo_album_next_tracks["href"],
            json=foo_album_next_tracks,
        )

        result = spotify_client._with_all_tracks(foo_album_response)

        assert len(responses.calls) == 1
        assert result["tracks"]["items"] == [3, 4, 5, 6, 7, 8]

    @responses.activate
    def test_with_all_tracks_uses_cached_tracks_when_unchanged(
        self,
        mock_time,
        foo_album_response,
        foo_album_next_tracks,
        spotify_client,
    ):
        responses.add(
            responses.GET,
            foo_album_next_tracks["href"],
            json=foo_album_next_tracks,
        )
        mock_time.return_value = -1000

        result1 = spotify_client._with_all_tracks(foo_album_response)

        assert len(responses.calls) == 1
        cache_keys = list(spotify_client._cache.keys())
        assert len(cache_keys) == 1

        responses.calls.reset()
        mock_time.return_value = 1000

        foo_album_response._status_code = 304
        result2 = spotify_client._with_all_tracks(foo_album_response)

        assert len(responses.calls) == 0
        assert result1 == result2

    @responses.activate
    @pytest.mark.parametrize(
        ("uri", "success"),
        [
            ("spotify:user:alice:playlist:bar", True),
            ("spotify:user:alice:playlist:fake", False),
            ("spotify:playlist:bar", True),
            ("spotify:track:foo", False),
            ("https://play.spotify.com/foo", False),
            ("total/junk", False),
        ],
    )
    def test_get_playlist(self, spotify_client, bar_playlist, uri, success):
        responses.add(responses.GET, bar_playlist["href"], json=bar_playlist)
        responses.add(responses.GET, url("playlists/fake"), json=None)

        result = spotify_client.get_playlist(uri)

        if success:
            assert len(responses.calls) == 1
            assert result == bar_playlist
        else:
            assert result == {}

    @responses.activate
    def test_get_playlist_sets_params_for_playlist(
        self, spotify_client, playlist_parms
    ):
        responses.add(responses.GET, url("playlists/bar"), json={})

        spotify_client.get_playlist("spotify:playlist:bar")

        assert len(responses.calls) == 1
        assert responses.calls[0].request.url.endswith(playlist_parms)

    @responses.activate
    def test_get_playlist_error(self, foo_playlist, spotify_client, caplog):
        responses.add(
            responses.GET,
            foo_playlist["href"],
            json={"error": "bar"},
        )

        result = spotify_client.get_playlist("spotify:playlist:foo")

        assert result == {}
        assert "Spotify Web API request failed: bar" in caplog.text

    @responses.activate
    def test_get_playlist_sets_params_for_tracks(
        self,
        foo_playlist,
        foo_playlist_tracks,
        spotify_client,
        playlist_tracks_parms,
    ):
        foo_playlist_tracks["next"] = f"{foo_playlist_tracks['href']}&offset=10"
        responses.add(
            responses.GET,
            foo_playlist["href"],
            json=foo_playlist,
        )
        responses.add(
            responses.GET,
            foo_playlist_tracks["href"],
            json=foo_playlist_tracks,
        )
        responses.add(responses.GET, foo_playlist_tracks["next"], json={})

        spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 3
        assert responses.calls[1].request.url.endswith(playlist_tracks_parms)
        assert responses.calls[2].request.url.endswith(
            f"{playlist_tracks_parms}&offset=10"
        )

    @responses.activate
    def test_get_playlist_collates_tracks(
        self, foo_playlist, foo_playlist_tracks, spotify_client
    ):
        responses.add(
            responses.GET,
            foo_playlist["href"],
            json=foo_playlist,
        )
        responses.add(
            responses.GET,
            foo_playlist_tracks["href"],
            json=foo_playlist_tracks,
        )

        result = spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 2
        assert result["tracks"]["items"] == [1, 2, 3, 4, 5]

    @pytest.mark.parametrize(
        ("uri", "msg"),
        [
            ("spotify:artist:foo", "Spotify playlist"),
            ("my-bad-uri", "Spotify"),
        ],
    )
    def test_get_playlist_error_msg(self, spotify_client, caplog, uri, msg):
        assert spotify_client.get_playlist(uri) == {}
        assert f"Could not parse {uri!r} as a {msg} URI" in caplog.text

    @pytest.mark.parametrize(("user_id", "expected"), [("alice", True), (None, False)])
    def test_logged_in(self, spotify_client, user_id, expected):
        spotify_client.user_id = user_id

        assert spotify_client.logged_in is expected

    @responses.activate
    def test_get_albums(self, foo_album, foo_album_next_tracks, spotify_client):
        responses.add(
            responses.GET,
            url("albums"),
            match=[matchers.query_string_matcher("ids=foo&market=from_token")],
            json={"albums": [foo_album]},
        )
        responses.add(
            responses.GET,
            url("albums/foo/tracks"),
            json=foo_album_next_tracks,
        )

        link = web.WebLink.from_uri("spotify:album:foo")
        results = list(spotify_client.get_albums([link]))

        assert len(responses.calls) == 2
        assert len(results) == 1
        assert results[0]["tracks"]["items"] == [3, 4, 5, 6, 7, 8]

    @responses.activate
    def test_get_album_wrong_linktype(self, spotify_client, caplog):
        link = web.WebLink.from_uri("spotify:album:abba")
        link.type = "your"
        results = list(spotify_client.get_albums([link]))

        assert len(responses.calls) == 0
        assert len(results) == 0
        assert "Expecting Spotify album URI" in caplog.text

    @responses.activate
    @pytest.mark.parametrize(
        "all_tracks,",
        [(True), (False)],
    )
    def test_get_artist_albums(
        self,
        artist_albums_mock,
        web_album_mock,
        web_album_mock2,
        spotify_client,
        all_tracks,
    ):
        responses.add(
            responses.GET,
            url("artists/abba/albums"),
            json=artist_albums_mock,
            match=[
                matchers.query_string_matcher(
                    "market=from_token&include_groups=single%2Calbum"
                )
            ],
        )
        spotify_client.get_albums = mock.Mock(
            return_value=[web_album_mock, web_album_mock2]
        )

        link = web.WebLink.from_uri("spotify:artist:abba")
        results = list(spotify_client.get_artist_albums(link, all_tracks=all_tracks))

        assert len(responses.calls) == 1
        assert spotify_client.get_albums.call_count == (1 if all_tracks else 0)
        assert len(results) == 2
        assert results[0]["name"] == "DEF 456"
        assert results[1]["name"] == "XYZ 789"

        if all_tracks:
            assert results[0]["tracks"]
            assert results[1]["tracks"]
        else:
            assert "tracks" not in results[0]
            assert "tracks" not in results[1]

    @responses.activate
    def test_get_artist_albums_error(self, spotify_client, caplog):
        responses.add(
            responses.GET,
            url("artists/abba/albums"),
            json={"error": "bar"},
        )

        link = web.WebLink.from_uri("spotify:artist:abba")
        results = list(spotify_client.get_artist_albums(link))

        assert len(responses.calls) == 1
        assert len(results) == 0
        assert "Spotify Web API request failed" in caplog.text

    @responses.activate
    def test_get_artist_albums_wrong_linktype(self, spotify_client, caplog):
        link = web.WebLink.from_uri("spotify:artist:abba")
        link.type = "your"
        results = list(spotify_client.get_artist_albums(link))

        assert len(responses.calls) == 0
        assert len(results) == 0
        assert "Expecting Spotify artist URI" in caplog.text

    @responses.activate
    def test_get_artist_albums_value_error(
        self, web_album_mock, spotify_client, caplog
    ):
        responses.add(
            responses.GET,
            url("artists/abba/albums"),
            json={
                "href": url("artists/abba/albums"),
                "items": [{"uri": "BLOPP"}, web_album_mock],
                "next": None,
            },
        )
        spotify_client.get_albums = mock.Mock(return_value=[web_album_mock])

        link = web.WebLink.from_uri("spotify:artist:abba")
        results = list(spotify_client.get_artist_albums(link))

        album_link = web.WebLink.from_uri(web_album_mock["uri"])
        assert len(responses.calls) == 1
        assert spotify_client.get_albums.call_args == mock.call(
            [album_link],
        )
        assert len(results) == 1
        assert results[0]["name"] == "DEF 456"
        assert "Could not parse 'BLOPP' as a Spotify URI" in caplog.text

    @responses.activate
    @pytest.mark.parametrize(
        ("uri", "success"),
        [
            ("spotify:track:abc", True),
            ("spotify:track:xyz", False),
            ("spotify:user:alice:playlist:bar", False),
            ("spotify:playlist:bar", False),
            ("spotify:artist:baz", False),
            ("spotify:album:foo", False),
        ],
    )
    def test_get_track(self, web_track_mock, spotify_client, uri, success):
        responses.add(
            responses.GET,
            url("tracks/abc"),
            json=web_track_mock,
        )
        responses.add(
            responses.GET,
            url("tracks/xyz"),
            json={},
        )

        link = web.WebLink.from_uri(uri)
        result = spotify_client.get_track(link)

        if success:
            assert len(responses.calls) == 1
            assert result == web_track_mock
        else:
            assert result == {}

    @responses.activate
    def test_get_artist_top_tracks(self, web_track_mock, spotify_client):
        responses.add(
            responses.GET,
            url("artists/baz/top-tracks"),
            json={"tracks": [web_track_mock, web_track_mock]},
        )
        link = web.WebLink.from_uri("spotify:artist:baz")
        results = spotify_client.get_artist_top_tracks(link)

        assert len(responses.calls) == 1
        assert len(results) == 2
        assert results[0]["name"] == "ABC 123"

    @responses.activate
    def test_get_artist_top_tracks_invalid_uri(
        self, web_track_mock, spotify_client, caplog
    ):
        responses.add(
            responses.GET,
            url("artists/baz/top-tracks"),
            json={"tracks": [web_track_mock, web_track_mock]},
        )
        link = web.WebLink.from_uri("spotify:artist:baz")
        link.type = "your"
        results = spotify_client.get_artist_top_tracks(link)

        assert len(responses.calls) == 0
        assert len(results) == 0
        assert "Expecting Spotify artist URI" in caplog.text

    @pytest.mark.parametrize(
        ("link_type", "max_links"),
        [
            ("track", 50),
            ("artist", 50),
            ("album", 20),
        ],
    )
    def test_get_batch_max_ids_per_request(self, spotify_client, link_type, max_links):
        spotify_client.get_one = mock.Mock(return_value={})
        links = [
            web.WebLink.from_uri(f"spotify:{link_type}:{i}")
            for i in range(max_links + 1)
        ]

        dict(spotify_client.get_batch(web.LinkType(link_type), links))

        assert spotify_client.get_one.call_count == 2

        request_ids_1 = spotify_client.get_one.call_args_list[0][1]["params"]["ids"]
        assert len(request_ids_1.split(",")) == max_links

        request_ids_2 = spotify_client.get_one.call_args_list[1][1]["params"]["ids"]
        assert len(request_ids_2.split(",")) == 1
        assert set(request_ids_2.split(",")) == (
            {link.id for link in links} - set(request_ids_1.split(","))
        )

    def test_get_batch_removes_duplicates(self, spotify_client):
        spotify_client.get_one = mock.Mock(return_value={})
        links = [web.WebLink.from_uri(f"spotify:track:{0}") for i in range(100)]

        dict(spotify_client.get_batch(web.LinkType("track"), links))

        assert spotify_client.get_one.call_count == 1
        request_ids_1 = spotify_client.get_one.call_args_list[0][1]["params"]["ids"]
        assert request_ids_1 == links[0].id

    def test_get_batch_playlist(self, spotify_client, caplog):
        links = [web.WebLink.from_uri("spotify:playlist:foo")]

        results = dict(spotify_client.get_batch(web.LinkType.PLAYLIST, links))

        assert results == {}
        assert "Cannot handle batched playlists" in caplog.text

    def test_get_batch_empty_results(self, spotify_client):
        spotify_client.get_one = mock.Mock(return_value={"tracks": [None]})
        links = [
            web.WebLink.from_uri("spotify:track:foo"),
            web.WebLink.from_uri("spotify:track:bar"),
        ]

        results = dict(spotify_client.get_batch(web.LinkType("track"), links))
        assert results == {}

    @responses.activate
    @pytest.mark.parametrize(
        ("res_types"),
        [
            ("tracks"),
            ("albums"),
        ],
    )
    def test_get_batch_web_response(
        self, spotify_client, web_track_mock, web_album_mock, res_types
    ):
        mock_res = web_track_mock if res_types == "tracks" else web_album_mock
        mock_id = mock_res["id"]
        mock_type = mock_res["type"]
        responses.add(
            responses.GET,
            url(res_types),
            match=[
                matchers.query_string_matcher(f"ids={mock_id}%2Cbar&market=from_token")
            ],
            json={res_types: [mock_res]},
        )
        links = [
            web.WebLink.from_uri(f"spotify:{mock_type}:{mock_id}"),
            web.WebLink.from_uri(f"spotify:{mock_type}:bar"),  # Won't return result.
        ]

        results = dict(spotify_client.get_batch(links[0].type, links))

        assert len(results) == 1
        result = results[links[0]]
        assert type(result) is web.WebResponse
        assert result.copy() == mock_res

    @responses.activate
    def test_get_batch_error(self, spotify_client, web_album_mock, caplog):
        responses.add(
            responses.GET,
            url("albums"),
            match=[matchers.query_string_matcher("ids=def&market=from_token")],
            json={"albums": [web_album_mock, {"error": "bar"}, None]},
        )

        link = web.WebLink.from_uri(web_album_mock["uri"])
        results = dict(spotify_client.get_batch(link.type, [link]))

        assert len(responses.calls) == 1
        assert len(results) == 1
        assert results[link]["name"] == "DEF 456"
        assert "Invalid batch item" in caplog.text


@pytest.mark.parametrize(
    ("uri", "type_", "id_"),
    [
        ("spotify:playlist:foo", web.LinkType.PLAYLIST, "foo"),
        ("spotify:track:bar", web.LinkType.TRACK, "bar"),
        ("spotify:artist:blah", web.LinkType.ARTIST, "blah"),
        ("spotify:album:stuff", web.LinkType.ALBUM, "stuff"),
        ("spotify:your:albums", web.LinkType.YOUR, None),
    ],
)
def test_weblink_from_uri_spotify_uri(uri, type_, id_):
    result = web.WebLink.from_uri(uri)

    assert result.uri == uri
    assert result.type == type_
    assert result.id == id_
    assert result.owner is None


@pytest.mark.parametrize(
    ("uri", "id_", "owner"),
    [
        ("spotify:user:alice:playlist:foo", "foo", "alice"),
        ("spotify:user:alice:starred", None, "alice"),
        ("spotify:playlist:foo", "foo", None),
        ("http://open.spotify.com/playlist/foo", "foo", None),
        ("https://open.spotify.com/playlist/foo", "foo", None),
        ("https://play.spotify.com/playlist/foo", "foo", None),
    ],
)
def test_weblink_from_uri_playlist(uri, id_, owner):
    result = web.WebLink.from_uri(uri)

    assert result.uri == uri
    assert result.type == web.LinkType.PLAYLIST
    assert result.id == id_
    assert result.owner == owner


@pytest.mark.parametrize(
    "uri",
    [
        ("spotify:user:alice:track:foo"),
        ("local:user:alice:playlist:foo"),
        ("spotify:track:foo:bar"),
        ("https://yahoo.com/playlist/foo"),
        ("https://play.spotify.com/foo"),
        ("total/junk"),
        ("foo:bar"),
        ("spotify:baz"),
        ("spotify:artist"),
        ("spotify:album"),
        ("spotify:user"),
        ("spotify:playlist"),
        ("spotify:playlist:"),
    ],
)
def test_weblink_from_uri_raises(uri):
    with pytest.raises(ValueError, match=r"^Could not parse.*") as excinfo:
        web.WebLink.from_uri(uri)

    assert f"Could not parse {uri!r} as a Spotify URI" in str(excinfo.value)
