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

        self._session = spotify.Session(self._get_spotify_config(config))

        if self._config['spotify']['offline']:
            self._session.connection.allow_network = False

        self.bitrate = self._config['spotify']['bitrate']
        self._session.preferred_bitrate = BITRATES[self.bitrate]

        self._session.on(
            spotify.SessionEvent.CONNECTION_STATE_UPDATED,
            on_connection_state_changed, self._logged_in, self._logged_out)

        self._event_loop = spotify.EventLoop(self._session)

        self.library = None
        self.playback = playback.SpotifyPlaybackProvider(
            audio=audio, backend=self)
        self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)

        self.uri_schemes = ['spotify']

    def _get_spotify_config(self, config):
        spotify_config = spotify.Config()
        spotify_config.load_application_key_file(
            os.path.join(os.path.dirname(__file__), 'spotify_appkey.key'))
        spotify_config.cache_location = config['spotify']['cache_dir']
        spotify_config.settings_location = config['spotify']['settings_dir']
        return spotify_config

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


def on_connection_state_changed(session, logged_in_event, logged_out_event):
    # NOTE Called from the pyspotify event loop, and not in an actor context.
    if session.connection.state is spotify.ConnectionState.LOGGED_OUT:
        logger.debug('Logged out of Spotify')
        logged_in_event.clear()
        logged_out_event.set()
    elif session.connection.state is spotify.ConnectionState.LOGGED_IN:
        logger.info('Logged in to Spotify in online mode')
        logged_in_event.set()
        logged_out_event.clear()
    elif session.connection.state is spotify.ConnectionState.DISCONNECTED:
        logger.info('Disconnected from Spotify')
    elif session.connection.state is spotify.ConnectionState.OFFLINE:
        logger.info('Logged in to Spotify in offline mode')
        logged_in_event.set()
        logged_out_event.clear()
