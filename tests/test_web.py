import urllib
from unittest import mock

import pytest
import requests
import responses

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


@pytest.yield_fixture()
def mock_time():
    patcher = mock.patch.object(web.time, "time")
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
    assert oauth_client._session.headers["user-agent"].startswith(
        f"Mopidy-Spotify/{mopidy_spotify.__version__}"
    )


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
    assert (
        "Fetching https://auth.mopidy.com/spotify/token failed: foo"
        in caplog.text
    )


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
    assert (
        responses.calls[0].request.url
        == "https://auth.mopidy.com/spotify/token"
    )
    assert (
        responses.calls[1].request.url
        == "https://api.spotify.com/v1/tracks/abc"
    )
    assert (
        responses.calls[1].request.headers["Authorization"]
        == "Bearer NgCXRK...MzYjw"
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
    assert (
        responses.calls[0].request.url
        == "https://api.spotify.com/v1/tracks/abc"
    )
    assert (
        responses.calls[0].request.headers["Authorization"]
        == "Bearer 01234...abcde"
    )

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
    responses.add(
        responses.POST, "https://auth.mopidy.com/spotify/token", body="scope"
    )

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert (
        "JSON decoding https://auth.mopidy.com/spotify/token failed"
        in caplog.text
    )


@responses.activate
def test_spotify_returns_invalid_json(mock_time, oauth_client, caplog):
    responses.add(
        responses.GET, "https://api.spotify.com/v1/tracks/abc", body="abc"
    )
    mock_time.return_value = -1000

    result = oauth_client.get("tracks/abc")

    assert result == {}
    assert (
        "JSON decoding https://api.spotify.com/v1/tracks/abc failed"
        in caplog.text
    )


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
    assert (
        "Fetching https://auth.mopidy.com/spotify/token failed" in caplog.text
    )


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
    assert (
        "Fetching https://api.spotify.com/v1/tracks/abc failed" in caplog.text
    )


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
    wrong_token_type["token_type"] = "something"
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
    "header,expected",
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
    "header,expected",
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
    "status_code,expected", [(200, True), (301, True), (400, False)]
)
def test_web_response_status_ok(status_code, expected):
    response = web.WebResponse("https://foo.com", {}, status_code=status_code)
    assert response.status_ok == expected


@pytest.mark.parametrize(
    "status_code,expected",
    [(200, False), (301, False), (304, True), (400, False)],
)
def test_web_response_status_unchanged(status_code, expected):
    response = web.WebResponse("https://foo.com", {}, status_code=status_code)
    assert not response._from_cache
    assert response.status_unchanged == expected


def test_web_response_status_unchanged_from_cache():
    response = web.WebResponse("https://foo.com", {})

    assert not response.status_unchanged

    response.still_valid(ignore_expiry=True)

    assert response.status_unchanged

    response.updated(response)

    assert not response.status_unchanged


@pytest.mark.parametrize(
    "etag,expected",
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
    "etag,status,expected,expected_etag,expected_msg",
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
    "cache,ok,expected",
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
    "path,params,expected",
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
def test_web_response(web_track_mock, mock_time, oauth_client):
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
        adding_headers={"Cache-Control": "max-age=2001", "ETag": '"12345"'},
        status=301,
    )
    mock_time.return_value = -1000

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc")

    assert isinstance(result, web.WebResponse)
    assert result.url == "https://api.spotify.com/v1/tracks/abc"
    assert result._status_code == 301
    assert result._expires == 1001
    assert result._etag == '"12345"'
    assert result.still_valid()
    assert result.status_ok
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_cache_miss(web_track_mock, mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
    )
    mock_time.return_value = -1000

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert len(responses.calls) == 1
    assert result["uri"] == "spotify:track:abc"
    assert oauth_client._should_cache_response(cache, result)
    assert cache["https://api.spotify.com/v1/tracks/abc"] == result


@responses.activate
def test_cache_response_still_valid(
    web_response_mock, mock_time, oauth_client, caplog
):
    cache = {"https://api.spotify.com/v1/tracks/abc": web_response_mock}
    oauth_client._expires = 2000
    mock_time.return_value = 999

    assert web_response_mock.still_valid()
    assert "Cached data fresh for" in caplog.text

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert len(responses.calls) == 0
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_cache_response_expired(
    web_response_mock, oauth_client, mock_time, caplog
):
    cache = {"https://api.spotify.com/v1/tracks/abc": web_response_mock}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json={"uri": "new"},
    )
    oauth_client._expires = 2000
    mock_time.return_value = 1001

    assert not web_response_mock.still_valid()
    assert "Cached data expired for" in caplog.text

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert len(responses.calls) == 1
    assert result["uri"] == "new"


@responses.activate
def test_cache_response_ignore_expiry(
    web_response_mock, oauth_client, mock_time, caplog
):
    cache = {"https://api.spotify.com/v1/tracks/abc": web_response_mock}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json={"uri": "new"},
    )
    oauth_client._expires = 2000
    mock_time.return_value = 1001

    assert web_response_mock.still_valid(True)
    assert "Cached data forced for" in caplog.text

    result = oauth_client.get(
        "https://api.spotify.com/v1/tracks/abc", cache, ignore_expiry=True
    )
    assert len(responses.calls) == 0
    assert result["uri"] == "spotify:track:abc"


@responses.activate
def test_dont_cache_bad_status(web_track_mock, mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
        status=404,
    )
    mock_time.return_value = -1000

    result = oauth_client.get("https://api.spotify.com/v1/tracks/abc", cache)
    assert result._status_code == 404
    assert not oauth_client._should_cache_response(cache, result)
    assert "https://api.spotify.com/v1/tracks/abc" not in cache


@responses.activate
def test_cache_key_uses_path(web_track_mock, mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json=web_track_mock,
    )
    mock_time.return_value = -1000

    result = oauth_client.get("tracks/abc", cache)
    assert len(responses.calls) == 1
    assert cache["tracks/abc"] == result
    assert result.url == "https://api.spotify.com/v1/tracks/abc"


@responses.activate
def test_cache_normalised_query_string(mock_time, oauth_client):
    cache = {}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc?b=bar&f=foo",
        json={"uri": "foobar"},
        match_querystring=True,
    )
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc?b=bar&f=cat",
        json={"uri": "cat"},
        match_querystring=True,
    )
    mock_time.return_value = -1000

    r1 = oauth_client.get("tracks/abc?f=foo&b=bar", cache)
    r2 = oauth_client.get("tracks/abc?b=bar&f=foo", cache)
    r3 = oauth_client.get("tracks/abc?b=bar&f=cat", cache)
    assert len(responses.calls) == 2
    assert r1["uri"] == "foobar"
    assert r1 == r2
    assert r1 != r3
    assert "tracks/abc?b=bar&f=foo" in cache
    assert "tracks/abc?b=bar&f=cat" in cache


@pytest.mark.parametrize(
    "status,expected", [(304, "spotify:track:abc"), (200, "spotify:track:xyz")]
)
@responses.activate
def test_cache_expired_with_etag(
    web_response_mock_etag, oauth_client, mock_time, status, expected
):
    cache = {"tracks/abc": web_response_mock_etag}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/abc",
        json={"uri": "spotify:track:xyz"},
        status=status,
    )
    oauth_client._expires = 2000
    mock_time.return_value = 1001

    result = oauth_client.get("tracks/abc", cache)
    assert len(responses.calls) == 1
    assert responses.calls[0].request.headers["If-None-Match"] == '"1234"'
    assert result["uri"] == expected
    assert cache["tracks/abc"] == result


@responses.activate
def test_cache_miss_no_etag(web_response_mock_etag, oauth_client, mock_time):
    cache = {"tracks/abc": web_response_mock_etag}
    responses.add(
        responses.GET,
        "https://api.spotify.com/v1/tracks/xyz",
        json={"uri": "spotify:track:xyz"},
    )
    oauth_client._expires = 2000
    mock_time.return_value = 1001

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
def test_fresh_response_changed(oauth_client, mock_time):
    cache = {}
    responses.add(responses.GET, "https://api.spotify.com/v1/foo", json={})
    oauth_client._expires = 2000
    mock_time.return_value = 1

    result = oauth_client.get("foo", cache)

    assert len(responses.calls) == 1
    assert not result.status_unchanged


@responses.activate
def test_cached_response_unchanged(web_response_mock, oauth_client, mock_time):
    cache = {"foo": web_response_mock}
    responses.add(responses.GET, "https://api.spotify.com/v1/foo", json={})
    oauth_client._expires = 2000
    mock_time.return_value = 1

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
    return web.SpotifyOAuthClient(
        client_id=config["spotify"]["client_id"],
        client_secret=config["spotify"]["client_secret"],
        proxy_config=None,
    )


@pytest.yield_fixture(scope="class")
def skip_refresh_token():
    patcher = mock.patch.object(web.OAuthClient, "_should_refresh_token")
    mock_refresh = patcher.start()
    mock_refresh.return_value = False
    yield mock_refresh
    patcher.stop()


@pytest.mark.usefixtures("skip_refresh_token")
class TestSpotifyOAuthClient:
    def url(self, endpoint):
        return f"https://api.spotify.com/v1/{endpoint}"

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
        [("name"), ("type"), ("uri"), ("name"), ("snapshot_id"), ("tracks")],
    )
    def test_playlist_required_fields(self, field):
        assert field in web.SpotifyOAuthClient.PLAYLIST_FIELDS

    def test_configures_auth(self):
        client = web.SpotifyOAuthClient(
            client_id="1234567", client_secret="AbCdEfG", proxy_config=None
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
        assert (
            spotify_client._refresh_url
            == "https://auth.mopidy.com/spotify/token"
        )

    @responses.activate
    def test_login_alice(self, spotify_client, caplog):
        responses.add(responses.GET, self.url("me"), json={"id": "alice"})

        assert spotify_client.login()
        assert spotify_client.user_id == "alice"
        assert "Logged into Spotify Web API as alice" in caplog.text

    @responses.activate
    def test_login_fails(self, spotify_client, caplog):
        responses.add(responses.GET, self.url("me"), json={})

        assert not spotify_client.login()
        assert spotify_client.user_id is None
        assert "Failed to load Spotify user profile" in caplog.text

    @responses.activate
    def test_get_one_error(self, spotify_client, caplog):
        responses.add(
            responses.GET, self.url("foo"), json={"error": "bar"},
        )

        result = spotify_client.get_one("foo", json={})

        assert result == {}
        assert "Spotify Web API request failed: bar" in caplog.text

    @responses.activate
    def test_get_one_cached(self, spotify_client):
        responses.add(responses.GET, self.url("foo"))

        spotify_client.get_one("foo")
        spotify_client.get_one("foo")

        assert len(responses.calls) == 1
        assert "foo" in spotify_client._cache

    @responses.activate
    def test_get_one_increased_expiry(self, mock_time, spotify_client):
        responses.add(responses.GET, self.url("foo"))
        mock_time.return_value = 1000

        result = spotify_client.get_one("foo")

        assert 1000 + spotify_client.DEFAULT_EXTRA_EXPIRY == result._expires

    @responses.activate
    def test_get_all(self, spotify_client):
        responses.add(
            responses.GET, self.url("page1"), json={"n": 1, "next": "page2"}
        )
        responses.add(responses.GET, self.url("page2"), json={"n": 2})

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
        responses.add(responses.GET, self.url("me/playlists"), json={})

        result = list(spotify_client.get_user_playlists())

        assert len(responses.calls) == 1
        assert len(result) == 0

    @responses.activate
    def test_get_user_playlists_sets_params(self, spotify_client):
        responses.add(responses.GET, self.url("me/playlists"), json={})

        list(spotify_client.get_user_playlists())

        assert len(responses.calls) == 1
        encoded_params = urllib.parse.urlencode({"limit": 50})
        assert responses.calls[0].request.url == self.url(
            f"me/playlists?{encoded_params}"
        )

    @responses.activate
    def test_get_user_playlists(self, spotify_client):
        responses.add(
            responses.GET,
            self.url("me/playlists?limit=50"),
            json={
                "next": self.url("me/playlists?offset=50"),
                "items": ["playlist0", "playlist1", "playlist2"],
            },
        )
        responses.add(
            responses.GET,
            self.url("me/playlists?limit=50&offset=50"),
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
    @pytest.mark.parametrize(
        "uri,success",
        [
            ("spotify:user:alice:playlist:foo", True),
            ("spotify:user:alice:playlist:fake", False),
            ("spotify:playlist:foo", True),
            ("spotify:track:foo", False),
            ("https://play.spotify.com/foo", False),
            ("total/junk", False),
        ],
    )
    def test_get_playlist(
        self, spotify_client, web_playlist_mock, uri, success
    ):
        responses.add(
            responses.GET, self.url("playlists/foo"), json=web_playlist_mock
        )
        responses.add(responses.GET, self.url("playlists/fake"), json=None)

        result = spotify_client.get_playlist(uri)

        if success:
            assert result == web_playlist_mock
        else:
            assert result == {}

    @responses.activate
    def test_get_playlist_sets_params_for_playlist(self, spotify_client):
        responses.add(responses.GET, self.url("playlists/foo"), json={})

        spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 1
        encoded_params = urllib.parse.urlencode(
            {"fields": spotify_client.PLAYLIST_FIELDS, "market": "from_token"}
        )
        assert responses.calls[0].request.url == self.url(
            f"playlists/foo?{encoded_params}"
        )

    @responses.activate
    def test_get_playlist_error(self, spotify_client, caplog):
        responses.add(
            responses.GET, self.url("playlists/foo"), json={"error": "bar"},
        )

        result = spotify_client.get_playlist("spotify:playlist:foo")

        assert result == {}
        assert "Spotify Web API request failed: bar" in caplog.text

    @responses.activate
    def test_get_playlist_tracks_error(self, spotify_client, caplog):
        responses.add(
            responses.GET,
            self.url("playlists/foo"),
            json={"tracks": {"next": "playlists/foo/tracks1"}},
        )
        responses.add(
            responses.GET,
            self.url("playlists/foo/tracks1"),
            json={"error": "baz"},
        )

        result = spotify_client.get_playlist("spotify:playlist:foo")

        assert result == {}
        assert "Spotify Web API request failed: baz" in caplog.text

    @responses.activate
    def test_get_playlist_sets_params_for_tracks(self, spotify_client):
        responses.add(
            responses.GET,
            self.url("playlists/foo"),
            json={"tracks": {"next": "playlists/foo/tracks1"}},
        )
        responses.add(
            responses.GET,
            self.url("playlists/foo/tracks1"),
            json={"next": "playlists/foo/tracks2", "items": []},
        )
        responses.add(responses.GET, self.url("playlists/foo/tracks2"), json={})

        spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 3
        encoded_params = urllib.parse.urlencode(
            {"fields": spotify_client.TRACK_FIELDS, "market": "from_token"}
        )
        assert responses.calls[1].request.url == self.url(
            f"playlists/foo/tracks1?{encoded_params}"
        )
        assert responses.calls[2].request.url == self.url(
            f"playlists/foo/tracks2?{encoded_params}"
        )

    @responses.activate
    def test_get_playlist_collates_tracks(self, spotify_client):
        responses.add(
            responses.GET,
            self.url("playlists/foo"),
            json={"tracks": {"items": [1, 2], "next": "playlists/foo/tracks"}},
        )
        responses.add(
            responses.GET,
            self.url("playlists/foo/tracks"),
            json={"items": [3, 4, 5]},
        )

        result = spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 2
        assert result["tracks"]["items"] == [1, 2, 3, 4, 5]

    @responses.activate
    def test_get_playlist_uses_cached_tracks_when_unchanged(
        self, mock_time, spotify_client
    ):
        responses.add(
            responses.GET,
            self.url("playlists/foo"),
            json={"tracks": {"items": [1, 2], "next": "playlists/foo/tracks"}},
            status=304,
        )
        responses.add(
            responses.GET,
            self.url("playlists/foo/tracks"),
            json={"items": [3, 4, 5]},
        )
        mock_time.return_value = -1000

        result1 = spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 2
        assert result1["tracks"]["items"] == [1, 2, 3, 4, 5]
        assert len(spotify_client._cache) == 2

        responses.calls.reset()
        mock_time.return_value = 1000

        result2 = spotify_client.get_playlist("spotify:playlist:foo")

        assert len(responses.calls) == 1
        assert result1["tracks"]["items"] == result2["tracks"]["items"]

    @pytest.mark.parametrize(
        "uri,msg",
        [
            ("spotify:artist:foo", "Spotify playlist"),
            ("my-bad-uri", "Spotify"),
        ],
    )
    def test_get_playlist_error_msg(self, spotify_client, caplog, uri, msg):
        assert spotify_client.get_playlist(uri) == {}
        assert f"Could not parse {uri!r} as a {msg} URI" in caplog.text

    def test_clear_cache(self, spotify_client):
        spotify_client._cache = {"foo": "bar"}

        spotify_client.clear_cache()

        assert {} == spotify_client._cache

    @pytest.mark.parametrize(
        "user_id,expected", [("alice", True), (None, False)]
    )
    def test_logged_in(self, spotify_client, user_id, expected):
        spotify_client.user_id = user_id

        assert spotify_client.logged_in is expected


@pytest.mark.parametrize(
    "uri,type_,id_",
    [
        ("spotify:playlist:foo", web.LinkType.PLAYLIST, "foo"),
        ("spotify:track:bar", web.LinkType.TRACK, "bar"),
        ("spotify:artist:blah", web.LinkType.ARTIST, "blah"),
        ("spotify:album:stuff", web.LinkType.ALBUM, "stuff"),
    ],
)
def test_weblink_from_uri_spotify_uri(uri, type_, id_):
    result = web.WebLink.from_uri(uri)

    assert result.uri == uri
    assert result.type == type_
    assert result.id == id_
    assert result.owner is None


@pytest.mark.parametrize(
    "uri,id_,owner",
    [
        ("spotify:user:alice:playlist:foo", "foo", "alice"),
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
        ("spotify:album:"),
        ("https://yahoo.com/playlist/foo"),
        ("https://play.spotify.com/foo"),
        ("total/junk"),
    ],
)
def test_weblink_from_uri_raises(uri):
    with pytest.raises(ValueError) as excinfo:
        result = web.WebLink.from_uri(uri)
        assert result is None

    assert f"Could not parse {uri!r} as a Spotify URI" in str(excinfo.value)
