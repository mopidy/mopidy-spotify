from __future__ import unicode_literals

import threading

import mock

import spotify

from mopidy_spotify import backend, library, playback, playlists


def get_backend(config):
    return backend.SpotifyBackend(config=config, audio=None)


def test_uri_schemes(spotify_mock, config):
    backend = get_backend(config)

    assert 'spotify' in backend.uri_schemes


def test_init_creates_configured_session(spotify_mock, config):
    cache_location_mock = mock.PropertyMock()
    settings_location_mock = mock.PropertyMock()
    config_mock = spotify_mock.Config.return_value
    type(config_mock).cache_location = cache_location_mock
    type(config_mock).settings_location = settings_location_mock

    get_backend(config)

    spotify_mock.Config.assert_called_once_with()
    config_mock.load_application_key_file.assert_called_once_with(mock.ANY)
    cache_location_mock.assert_called_once_with('/my/cache/dir')
    settings_location_mock.assert_called_once_with('/my/settings/dir')
    spotify_mock.Session.assert_called_once_with(config_mock)


def test_init_disallows_network_if_config_is_set(spotify_mock, config):
    session = spotify_mock.Session.return_value
    allow_network_mock = mock.PropertyMock()
    type(session.connection).allow_network = allow_network_mock
    config['spotify']['allow_network'] = False

    get_backend(config)

    allow_network_mock.assert_called_once_with(False)


def test_init_configures_preferred_bitrate(spotify_mock, config):
    session = spotify_mock.Session.return_value
    preferred_bitrate_mock = mock.PropertyMock()
    type(session).preferred_bitrate = preferred_bitrate_mock
    config['spotify']['bitrate'] = 320

    get_backend(config)

    preferred_bitrate_mock.assert_called_once_with(
        spotify.Bitrate.BITRATE_320k)


def test_init_configures_volume_normalization(spotify_mock, config):
    session = spotify_mock.Session.return_value
    volume_normalization_mock = mock.PropertyMock()
    type(session).volume_normalization = volume_normalization_mock
    config['spotify']['volume_normalization'] = False

    get_backend(config)

    volume_normalization_mock.assert_called_once_with(False)


def test_init_adds_connection_state_changed_handler_to_session(
        spotify_mock, config):
    session = spotify_mock.Session.return_value

    get_backend(config)

    assert (mock.call(
        spotify_mock.SessionEvent.CONNECTION_STATE_UPDATED,
        backend.on_connection_state_changed,
        backend.SpotifyBackend._logged_in,
        backend.SpotifyBackend._logged_out,
        backend.SpotifyBackend._online)
        in session.on.call_args_list)


def test_init_sets_up_the_providers(spotify_mock, config):
    backend = get_backend(config)

    assert isinstance(backend.library, library.SpotifyLibraryProvider)
    assert isinstance(backend.playback, playback.SpotifyPlaybackProvider)
    assert isinstance(backend.playlists, playlists.SpotifyPlaylistsProvider)


def test_on_start_starts_the_pyspotify_event_loop(spotify_mock, config):
    backend = get_backend(config)
    backend.on_start()

    spotify_mock.EventLoop.assert_called_once_with(backend._session)
    spotify_mock.EventLoop.return_value.start.assert_called_once_with()


def test_on_start_logs_in(spotify_mock, config):
    backend = get_backend(config)
    backend.on_start()

    spotify_mock.Session.return_value.login.assert_called_once_with(
        'alice', 'password')


def test_on_stop_logs_out_and_waits_for_logout_to_complete(
        spotify_mock, config, caplog):
    backend = get_backend(config)
    backend._logged_out = mock.Mock()

    backend.on_stop()

    assert 'Logging out of Spotify' in caplog.text()
    spotify_mock.Session.return_value.logout.assert_called_once_with()
    backend._logged_out.wait.assert_called_once_with()
    spotify_mock.EventLoop.return_value.stop.assert_called_once_with()


def test_on_connection_state_changed_when_logged_out(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.LOGGED_OUT
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    online_event = threading.Event()

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, online_event)

    assert 'Logged out of Spotify' in caplog.text()
    assert not logged_in_event.is_set()
    assert logged_out_event.is_set()
    assert not online_event.is_set()


def test_on_connection_state_changed_when_logged_in(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.LOGGED_IN
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    online_event = threading.Event()

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, online_event)

    assert 'Logged in to Spotify in online mode' in caplog.text()
    assert logged_in_event.is_set()
    assert not logged_out_event.is_set()
    assert online_event.is_set()


def test_on_connection_state_changed_when_disconnected(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.DISCONNECTED
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    online_event = threading.Event()

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, online_event)

    assert 'Disconnected from Spotify' in caplog.text()
    assert not online_event.is_set()


def test_on_connection_state_changed_when_offline(spotify_mock, caplog):
    session_mock = spotify_mock.Session.return_value
    session_mock.connection.state = spotify_mock.ConnectionState.OFFLINE
    logged_in_event = threading.Event()
    logged_out_event = threading.Event()
    online_event = threading.Event()

    backend.on_connection_state_changed(
        session_mock, logged_in_event, logged_out_event, online_event)

    assert 'Logged in to Spotify in offline mode' in caplog.text()
    assert logged_in_event.is_set()
    assert not logged_out_event.is_set()
    assert not online_event.is_set()
