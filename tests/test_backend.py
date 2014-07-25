from __future__ import unicode_literals

import unittest

import mock

import spotify

from mopidy_spotify import backend


@mock.patch.object(backend, 'spotify', spec=spotify)
class SpotifyBackendTest(unittest.TestCase):

    config = {
        'spotify': {
            'username': 'alice',
            'password': 'password',
            'cache_dir': '/my/cache/dir',
            'settings_dir': '/my/settings/dir',
        }
    }

    def get_backend(self):
        return backend.SpotifyBackend(config=self.config, audio=None)

    def test_uri_schemes(self, spotify):
        backend = self.get_backend()
        self.assertIn('spotify', backend.uri_schemes)

    def test_init_creates_configured_session(self, spotify):
        cache_location_mock = mock.PropertyMock()
        settings_location_mock = mock.PropertyMock()
        config_mock = spotify.Config.return_value
        type(config_mock).cache_location = cache_location_mock
        type(config_mock).settings_location = settings_location_mock

        self.get_backend()

        spotify.Config.assert_called_once_with()
        config_mock.load_application_key_file.assert_called_once_with(mock.ANY)
        cache_location_mock.assert_called_once_with('/my/cache/dir')
        settings_location_mock.assert_called_once_with('/my/settings/dir')
        spotify.Session.assert_called_once_with(config_mock)

    def test_on_start_adds_connection_state_changed_handler_to_session(
            self, spotify):
        session = spotify.Session.return_value

        backend = self.get_backend()
        backend.on_start()

        session.on.assert_called_once_with(
            spotify.SessionEvent.CONNECTION_STATE_UPDATED, mock.ANY)

    def test_on_start_starts_the_pyspotify_event_loop(self, spotify):
        backend = self.get_backend()
        backend.on_start()

        spotify.EventLoop.assert_called_once_with(backend._session)
        spotify.EventLoop.return_value.start.assert_called_once_with()

    def test_on_start_logs_in(self, spotify):
        backend = self.get_backend()

        backend.on_start()

        spotify.Session.return_value.login.assert_called_once_with(
            'alice', 'password')

    def test_on_stop_logs_out_and_waits_for_logout_to_complete(self, spotify):
        backend = self.get_backend()
        backend._logged_out = mock.Mock()

        backend.on_stop()

        spotify.Session.return_value.logout.assert_called_once_with()
        backend._logged_out.wait.assert_called_once_with()
