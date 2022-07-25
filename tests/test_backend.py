from unittest import mock
from unittest import skip

from mopidy import backend as backend_api

from mopidy_spotify import backend, library, playlists
from mopidy_spotify.backend import SpotifyPlaybackProvider


def get_backend(config):
    obj = backend.SpotifyBackend(config=config, audio=None)
    obj._web_client = mock.Mock()
    return obj


def test_uri_schemes(config):
    backend = get_backend(config)

    assert "spotify" in backend.uri_schemes


def test_init_sets_up_the_providers(config):
    backend = get_backend(config)

    assert isinstance(backend.library, library.SpotifyLibraryProvider)
    assert isinstance(backend.library, backend_api.LibraryProvider)

    assert isinstance(backend.playback, SpotifyPlaybackProvider)
    assert isinstance(backend.playback, backend_api.PlaybackProvider)

    assert isinstance(backend.playlists, playlists.SpotifyPlaylistsProvider)
    assert isinstance(backend.playlists, backend_api.PlaylistsProvider)


def test_init_disables_playlists_provider_if_not_allowed(config):
    config["spotify"]["allow_playlists"] = False

    backend = get_backend(config)

    assert backend.playlists is None


@skip("currently can't configure this")
def test_on_start_configures_preferred_bitrate(config):
    pass


@skip("support this with spotifyaudiosrc?")
def test_on_start_configures_volume_normalization(config):
    pass


@skip("support this with spotifyaudiosrc?")
def test_on_start_configures_proxy(web_mock, config):
    config["proxy"] = {
        "scheme": "https",
        "hostname": "my-proxy.example.com",
        "port": 8080,
        "username": "alice",
        "password": "s3cret",
    }
    backend = get_backend(config)
    backend.on_start()

    assert True

    web_mock.SpotifyOAuthClient.assert_called_once_with(
        client_id=mock.ANY,
        client_secret=mock.ANY,
        proxy_config=config["proxy"],
    )


def test_on_start_configures_web_client(web_mock, config):
    config["spotify"]["client_id"] = "1234567"
    config["spotify"]["client_secret"] = "AbCdEfG"

    backend = get_backend(config)
    backend.on_start()

    web_mock.SpotifyOAuthClient.assert_called_once_with(
        client_id="1234567",
        client_secret="AbCdEfG",
        proxy_config=mock.ANY,
    )


def test_on_start_logs_in(web_mock, config):
    backend = get_backend(config)
    backend.on_start()

    web_mock.SpotifyOAuthClient.return_value.login.assert_called_once()


def test_on_start_refreshes_playlists(web_mock, config, caplog):
    backend = get_backend(config)
    backend.on_start()

    client_mock = web_mock.SpotifyOAuthClient.return_value
    client_mock.get_user_playlists.assert_called_once()
    assert "Refreshed 0 Spotify playlists" in caplog.text
    assert backend.playlists._loaded


def test_on_start_doesnt_refresh_playlists_if_not_allowed(
    web_mock, config, caplog
):
    config["spotify"]["allow_playlists"] = False

    backend = get_backend(config)
    backend.on_start()

    client_mock = web_mock.SpotifyOAuthClient.return_value
    client_mock.get_user_playlists.assert_not_called()
    assert "Refreshed 0 playlists" not in caplog.text
