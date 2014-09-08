from __future__ import unicode_literals

import logging
import os
import threading

from mopidy import backend

import pykka

import spotify

from mopidy_spotify import playback, playlists


logger = logging.getLogger(__name__)


BITRATES = {
    96: spotify.Bitrate.BITRATE_96k,
    160: spotify.Bitrate.BITRATE_160k,
    320: spotify.Bitrate.BITRATE_320k,
}


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):

    _logged_in = threading.Event()
    _logged_out = threading.Event()
    _logged_out.set()

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

        if self._config['spotify']['offline']:
            self._session.connection.allow_network = False

        self.bitrate = self._config['spotify']['bitrate']
        self._session.preferred_bitrate = BITRATES[self.bitrate]

        self._session.on(
            spotify.SessionEvent.CONNECTION_STATE_UPDATED,
            SpotifyBackend.on_connection_state_changed)

        self._event_loop = spotify.EventLoop(self._session)

        self.library = None
        self.playback = playback.SpotifyPlaybackProvider(
            audio=audio, backend=self)
        self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)

        self.uri_schemes = ['spotify']

    def on_start(self):
        self._event_loop.start()

        self._session.login(
            self._config['spotify']['username'],
            self._config['spotify']['password'])

    def on_stop(self):
        logger.debug('Logging out of Spotify')
        self._session.logout()
        self._logged_out.wait()
        self._event_loop.stop()

    @classmethod
    def on_connection_state_changed(cls, session):
        if session.connection.state is spotify.ConnectionState.LOGGED_OUT:
            logger.debug('Logged out of Spotify')
            cls._logged_in.clear()
            cls._logged_out.set()
        elif session.connection.state is spotify.ConnectionState.LOGGED_IN:
            logger.info('Logged in to Spotify in online mode')
            cls._logged_in.set()
            cls._logged_out.clear()
        elif session.connection.state is spotify.ConnectionState.DISCONNECTED:
            logger.info('Disconnected from Spotify')
        elif session.connection.state is spotify.ConnectionState.OFFLINE:
            logger.info('Logged in to Spotify in offline mode')
            cls._logged_in.set()
            cls._logged_out.clear()
