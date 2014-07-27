from __future__ import unicode_literals

import mock

import pytest

import spotify

import mopidy_spotify.backend


@pytest.yield_fixture
def spotify_mock():
    patcher = mock.patch.object(
        mopidy_spotify.backend, 'spotify', spec=spotify)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def config():
    return {
        'spotify': {
            'username': 'alice',
            'password': 'password',
            'cache_dir': '/my/cache/dir',
            'settings_dir': '/my/settings/dir',
        }
    }


def get_backend(config):
    return mopidy_spotify.backend.SpotifyBackend(config=config, audio=None)


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


def test_on_start_adds_connection_state_changed_handler_to_session(
        spotify_mock, config):
    session = spotify_mock.Session.return_value

    backend = get_backend(config)
    backend.on_start()

    session.on.assert_called_once_with(
        spotify_mock.SessionEvent.CONNECTION_STATE_UPDATED, mock.ANY)


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
        spotify_mock, config):
    backend = get_backend(config)
    backend._logged_out = mock.Mock()

    backend.on_stop()

    spotify_mock.Session.return_value.logout.assert_called_once_with()
    backend._logged_out.wait.assert_called_once_with()
    spotify_mock.EventLoop.return_value.stop.assert_called_once_with()
