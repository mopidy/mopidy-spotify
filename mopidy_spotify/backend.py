from __future__ import unicode_literals

import logging
import os

from mopidy import backend

import pykka

import spotify


logger = logging.getLogger(__name__)


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super(SpotifyBackend, self).__init__()

        self._config = config
        self._audio = audio

        spotify_config = spotify.Config()
        spotify_config.load_application_key_file(
            os.path.join(os.path.dirname(__file__), 'spotify_appkey.key'))
        spotify_config.cache_location = self._config['spotify']['cache_dir']
        spotify_config.settings_location = (
            self._config['spotify']['settings_dir'])
        self._session = spotify.Session(spotify_config)

        self.library = None
        self.playback = None
        self.playlists = None

        self.uri_schemes = ['spotify']

    def on_start(self):
        actor_proxy = self.actor_ref.proxy()

        self._session.on(
            spotify.SessionEvent.CONNECTION_STATE_UPDATED,
            actor_proxy.on_connection_state_changed)

        self._event_loop = spotify.EventLoop(self._session)
        self._event_loop.start()

        self._session.login(
            self._config['spotify']['username'],
            self._config['spotify']['password'])

    def on_stop(self):
        # TODO Logout and wait for the logout to complete
        pass

    def on_connection_state_changed(self, session):
        if session.connection.state is spotify.ConnectionState.LOGGED_IN:
            logger.info('Connected to Spotify')
        elif session.connection.state is spotify.ConnectionState.LOGGED_OUT:
            logger.info('Logged out of Spotify')
