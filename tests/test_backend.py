import threading
from unittest import mock

from mopidy import backend as backend_api

import spotify
from mopidy_spotify import backend, library, playback, playlists
from tests import ThreadJoiner


def get_backend(config, session_mock=None):
    obj = backend.SpotifyBackend(config=config, audio=None)
    if session_mock:
        obj._session = session_mock
    else:
        obj._session = mock.Mock()
        obj._web_client = mock.Mock()
    obj._event_loop = mock.Mock()
    return obj


def test_uri_schemes(spotify_mock, config):
    backend = get_backend(config)

    assert "spotify" in backend.uri_schemes


def test_init_sets_up_the_providers(spotify_mock, config):
    backend = get_backend(config)

    assert isinstance(backend.library, library.SpotifyLibraryProvider)
    assert isinstance(backend.library, backend_api.LibraryProvider)

    assert isinstance(backend.playback, playback.SpotifyPlaybackProvider)
    assert isinstance(backend.playback, backend_api.PlaybackProvider)

    assert isinstance(backend.playlists, playlists.SpotifyPlaylistsProvider)
    assert isinstance(backend.playlists, backend_api.PlaylistsProvider)


def test_init_disables_playlists_provider_if_not_allowed(spotify_mock, config):
    config["spotify"]["allow_playlists"] = False

    backend = get_backend(config)

    assert backend.playlists is None


def test_on_start_creates_configured_session(tmp_path, spotify_mock, config):
    cache_location_mock = mock.PropertyMock()
    settings_location_mock = mock.PropertyMock()
    config_mock = spotify_mock.Config.return_value
    type(config_mock).cache_location = cache_location_mock
    type(config_mock).settings_location = settings_location_mock

    with ThreadJoiner(timeout=1.0):
        get_backend(config).on_start()

    spotify_mock.Config.assert_called_once_with()
    config_mock.load_application_key_file.assert_called_once_with(mock.ANY)
    cache_location_mock.assert_called_once_with(
        bytes(tmp_path / "cache" / "spotify")
    )
    settings_location_mock.assert_called_once_with(
        bytes(tmp_path / "data" / "spotify")
    )
    spotify_mock.Session.assert_called_once_with(config_mock)


def test_on_start_disallows_network_if_config_is_set(spotify_mock, config):
    session = spotify_mock.Session.return_value
    allow_network_mock = mock.PropertyMock()
    type(session.connection).allow_network = allow_network_mock
    config["spotify"]["allow_network"] = False

    with ThreadJoiner(timeout=1.0):
        get_backend(config).on_start()

    allow_network_mock.assert_called_once_with(False)


def test_on_start_configures_preferred_bitrate(spotify_mock, config):
    session = spotify_mock.Session.return_value
    preferred_bitrate_mock = mock.PropertyMock()
    type(session).preferred_bitrate = preferred_bitrate_mock
    config["spotify"]["bitrate"] = 320

    with ThreadJoiner(timeout=1.0):
        get_backend(config).on_start()

    preferred_bitrate_mock.assert_called_once_with(spotify.Bitrate.BITRATE_320k)


def test_on_start_configures_volume_normalization(spotify_mock, config):
    session = spotify_mock.Session.return_value
    volume_normalization_mock = mock.PropertyMock()
    type(session).volume_normalization = volume_normalization_mock
    config["spotify"]["volume_normalization"] = False

    with ThreadJoiner(timeout=1.0):
        get_backend(config).on_start()

    volume_normalization_mock.assert_called_once_with(False)


def test_on_start_configures_proxy(spotify_mock, web_mock, config):
    config["proxy"] = {
        "scheme": "https",
        "hostname": "my-proxy.example.com",
        "port": 8080,
        "username": "alice",
        "password": "s3cret",
    }
    spotify_config = spotify_mock.Config.return_value

    backend = get_backend(config)
    with ThreadJoiner(timeout=1.0):
        backend.on_start()

    assert spotify_config.proxy == "https://my-proxy.example.com:8080"
    assert spotify_config.proxy_username == "alice"
    assert spotify_config.proxy_password == "s3cret"

    web_mock.SpotifyOAuthClient.assert_called_once_with(
        client_id=mock.ANY,
        client_secret=mock.ANY,
        proxy_config=config["proxy"],
    )


def test_on_start_configures_web_client(spotify_mock, web_mock, config):
    config["spotify"]["client_id"] = "1234567"
    config["spotify"]["client_secret"] = "AbCdEfG"

    backend = get_backend(config)
    with ThreadJoiner(timeout=1.0):
        backend.on_start()

    web_mock.SpotifyOAuthClient.assert_called_once_with(
        client_id="1234567",
        client_secret="AbCdEfG",
        proxy_config=mock.ANY,
    )


def test_on_start_adds_connection_state_changed_handler_to_session(
    spotify_mock, config
):
    session = spotify_mock.Session.return_value

    with ThreadJoiner(timeout=1.0):
        get_backend(config).on_start()

    session.on.assert_any_call(
        spotify_mock.SessionEvent.CONNECTION_STATE_UPDATED,
        backend.on_connection_state_changed,
        backend.SpotifyBackend._logged_in,
        backend.SpotifyBackend._logged_out,
        mock.ANY,
    )


def test_on_start_adds_play_token_lost_handler_to_session(spotify_mock, config):
    session = spotify_mock.Session.return_value

    obj = get_backend(config)
    with ThreadJoiner(timeout=1.0):
        obj.on_start()

    session.on.assert_any_call(
        spotify_mock.SessionEvent.PLAY_TOKEN_LOST,
        backend.on_play_token_lost,
        mock.ANY,
    )


def test_on_start_starts_the_pyspotify_event_loop(spotify_mock, config):
    backend = get_backend(config)
    with ThreadJoiner(timeout=1.0):
        backend.on_start()

    spotify_mock.EventLoop.assert_called_once_with(backend._session)
    spotify_mock.EventLoop.return_value.start.assert_called_once_with()


def test_on_start_logs_in(spotify_mock, web_mock, config):
    backend = get_backend(config)
    with ThreadJoiner(timeout=1.0):
        backend.on_start()

    spotify_mock.Session.return_value.login.assert_called_once_with(
        "alice", "password"
    )
    web_mock.SpotifyOAuthClient.return_value.login.assert_called_once()


def test_on_start_refreshes_playlists(spotify_mock, web_mock, config, caplog):
    backend = get_backend(config)
    with ThreadJoiner(timeout=1.0):
        backend.on_start()

    client_mock = web_mock.SpotifyOAuthClient.return_value
    client_mock.get_user_playlists.assert_called_once()
    assert "Refreshed 0 Spotify playlists" in caplog.text
    assert backend.playlists._loaded


def test_on_start_doesnt_refresh_playlists_if_not_allowed(
    spotify_mock, web_mock, config, caplog
):
    config["spotify"]["allow_playlists"] = False

    backend = get_backend(config)
    backend.on_start()

    client_mock = web_mock.SpotifyOAuthClient.return_value
    client_mock.get_user_playlists.assert_not_called()
    assert "Refreshed 0 playlists" not in caplog.text


def test_on_stop_logs_out_and_waits_for_logout_to_complete(
    spotify_mock, config, caplog
):
    backend = get_backend(config)
    backend._logged_out = mock.Mock()

    backend.on_stop()

    assert "Logging out of Spotify" in caplog.text
    backend._session.logout.assert_called_once_with()
    backend._logged_out.wait.assert_called_once_with()
    backend._event_loop.stop.assert_called_once_with()


def test_on_connection_state_changed_when_logged_out(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.LOGGED_OUT
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    actor_mock = mock.Mock(spec=backend.SpotifyBackend)

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, actor_mock
    )

    assert "Logged out of Spotify" in caplog.text
    assert not logged_in_event.is_set()
    assert logged_out_event.is_set()


def test_on_connection_state_changed_when_logged_in(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.LOGGED_IN
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    actor_mock = mock.Mock(spec=backend.SpotifyBackend)

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, actor_mock
    )

    assert "Logged in to Spotify in online mode" in caplog.text
    assert logged_in_event.is_set()
    assert not logged_out_event.is_set()
    actor_mock.on_logged_in.assert_called_once_with()


def test_on_connection_state_changed_when_disconnected(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.DISCONNECTED
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    actor_mock = mock.Mock(spec=backend.SpotifyBackend)

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, actor_mock
    )

    assert "Disconnected from Spotify" in caplog.text


def test_on_connection_state_changed_when_offline(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.OFFLINE
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    actor_mock = mock.Mock(spec=backend.SpotifyBackend)

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, actor_mock
    )

    assert "Logged in to Spotify in offline mode" in caplog.text
    assert logged_in_event.is_set()
    assert not logged_out_event.is_set()


def test_on_logged_in_event_activates_private_session(
    spotify_mock, config, caplog
):
    session_mock = spotify_mock.Session.return_value
    private_session_mock = mock.PropertyMock()
    type(session_mock.social).private_session = private_session_mock
    config["spotify"]["private_session"] = True
    backend = get_backend(config, session_mock)

    backend.on_logged_in()

    assert "Spotify private session activated" in caplog.text
    private_session_mock.assert_called_once_with(True)


def test_on_play_token_lost_messages_the_actor(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    actor_mock = mock.Mock(spec=backend.SpotifyBackend)

    backend.on_play_token_lost(session_mock, actor_mock)

    assert "Spotify play token lost" in caplog.text
    actor_mock.on_play_token_lost.assert_called_once_with()


def test_on_play_token_lost_event_when_playing(spotify_mock, config, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.player.state = spotify_mock.PlayerState.PLAYING
    backend = get_backend(config, session_mock)
    backend.playback = mock.Mock(spec=playback.SpotifyPlaybackProvider)

    backend.on_play_token_lost()

    assert (
        "Spotify has been paused because your account is "
        "being used somewhere else." in caplog.text
    )
    backend.playback.pause.assert_called_once_with()


def test_on_play_token_lost_event_when_not_playing(
    spotify_mock, config, caplog
):
    session_mock = spotify_mock.Session.return_value
    session_mock.player.state = spotify_mock.PlayerState.UNLOADED
    backend = get_backend(config, session_mock)
    backend.playback = mock.Mock(spec=playback.SpotifyPlaybackProvider)

    backend.on_play_token_lost()

    assert "Spotify has been paused" not in caplog.text
    assert backend.playback.pause.call_count == 0
