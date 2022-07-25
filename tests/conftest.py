from unittest import mock

import pytest
from mopidy import backend as backend_api
from mopidy import models

from mopidy_spotify import backend, library, utils, web


@pytest.fixture
def caplog(caplog):
    caplog.set_level(utils.TRACE)
    return caplog


@pytest.fixture
def config(tmp_path):
    return {
        "core": {
            "cache_dir": str(tmp_path / "cache"),
            "data_dir": str(tmp_path / "data"),
        },
        "proxy": {},
        "spotify": {
            "username": "alice",
            "password": "password",
            "bitrate": 160,
            "volume_normalization": True,
            "private_session": False,
            "timeout": 10,
            "allow_cache": True,
            "allow_network": True,
            "allow_playlists": True,
            "search_album_count": 20,
            "search_artist_count": 10,
            "search_track_count": 50,
            "toplist_countries": ["GB", "US"],
            "client_id": "abcd1234",
            "client_secret": "YWJjZDEyMzQ=",
        },
    }


@pytest.fixture
def web_mock():
    patcher = mock.patch.object(backend, "web", spec=web)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def web_search_mock(web_album_mock_base, web_artist_mock, web_track_mock):
    return {
        "albums": {"items": [web_album_mock_base]},
        "artists": {"items": [web_artist_mock]},
        "tracks": {"items": [web_track_mock, web_track_mock]},
    }


@pytest.fixture
def web_search_mock_large(web_album_mock, web_artist_mock, web_track_mock):
    return {
        "albums": {"items": [web_album_mock] * 10},
        "artists": {"items": [web_artist_mock] * 10},
        "tracks": {"items": [web_track_mock] * 10},
    }


@pytest.fixture
def web_artist_mock():
    return {"name": "ABBA", "uri": "spotify:artist:abba", "type": "artist"}


@pytest.fixture
def web_track_mock_base(web_artist_mock):
    return {
        "artists": [web_artist_mock],
        "disc_number": 1,
        "duration_ms": 174300,
        "name": "ABC 123",
        "track_number": 7,
        "uri": "spotify:track:abc",
        "type": "track",
        "is_playable": True,
    }


@pytest.fixture
def web_album_mock_base(web_artist_mock):
    return {
        "name": "DEF 456",
        "uri": "spotify:album:def",
        "type": "album",
        "album_type": "album",
        "artists": [web_artist_mock],
    }


@pytest.fixture
def web_album_mock(web_album_mock_base, web_track_mock_base):
    return {
        **web_album_mock_base,
        **{"tracks": {"items": [web_track_mock_base] * 10}},
        "is_playable": True,
    }


@pytest.fixture
def web_album_mock_base2(web_artist_mock):
    return {
        "name": "XYZ 789",
        "uri": "spotify:album:xyz",
        "type": "album",
        "album_type": "album",
        "artists": [web_artist_mock],
    }


@pytest.fixture
def web_album_mock2(web_album_mock_base2, web_track_mock_base):
    return {
        **web_album_mock_base2,
        **{"tracks": {"items": [web_track_mock_base] * 2}},
        "is_playable": True,
    }


@pytest.fixture
def web_track_mock(web_track_mock_base, web_album_mock_base):
    return {
        **web_track_mock_base,
        **{"album": web_album_mock_base},
    }


@pytest.fixture
def web_response_mock(web_track_mock):
    return web.WebResponse(
        "https://api.spotify.com/v1/tracks/abc",
        web_track_mock,
        expires=1000,
        status_code=200,
    )


@pytest.fixture
def web_response_mock_etag(web_response_mock):
    web_response_mock._etag = '"1234"'
    return web_response_mock


@pytest.fixture
def web_oauth_mock():
    return {
        "access_token": "NgCXRK...MzYjw",
        "token_type": "Bearer",
        "scope": "user-read-private user-read-email",
        "expires_in": 3600,
    }


@pytest.fixture
def web_playlist_mock(web_track_mock):
    return {
        "owner": {"id": "alice"},
        "name": "Foo",
        "tracks": {"items": [{"track": web_track_mock}]},
        "snapshot_id": "abcderfg12364",
        "uri": "spotify:user:alice:playlist:foo",
        "type": "playlist",
    }


@pytest.fixture
def mopidy_artist_mock():
    return models.Artist(name="ABBA", uri="spotify:artist:abba")


@pytest.fixture
def mopidy_album_mock(mopidy_artist_mock):
    return models.Album(
        artists=[mopidy_artist_mock],
        date="2001",
        name="DEF 456",
        uri="spotify:album:def",
    )


@pytest.fixture
def web_client_mock():
    web_client_mock = mock.MagicMock(spec=web.SpotifyOAuthClient)
    web_client_mock.user_id = "alice"
    web_client_mock.get_user_playlists.return_value = []
    return web_client_mock


@pytest.fixture
def backend_mock(config, web_client_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._bitrate = 160
    backend_mock._web_client = web_client_mock
    return backend_mock


@pytest.fixture
def backend_listener_mock():
    patcher = mock.patch.object(
        backend_api, "BackendListener", spec=backend_api.BackendListener
    )
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def provider(backend_mock):
    return library.SpotifyLibraryProvider(backend_mock)
