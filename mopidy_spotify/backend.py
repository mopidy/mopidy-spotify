from __future__ import unicode_literals

import logging
import os
import threading

from mopidy import backend

import pykka

import spotify

from mopidy_spotify import library, playback, playlists


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
    _online = threading.Event()

    def __init__(self, config, audio):
        super(SpotifyBackend, self).__init__()

        self._config = config
        self._audio = audio
        self._session = None
        self._event_loop = None
        self._bitrate = None

        self.library = library.SpotifyLibraryProvider(backend=self)
        self.playback = playback.SpotifyPlaybackProvider(
            audio=audio, backend=self)
        if config['spotify']['allow_playlists']:
            self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)
        else:
            self.playlists = None
        self.uri_schemes = ['spotify']

    def on_start(self):
        self._session = self._get_session(self._config)

        self._event_loop = spotify.EventLoop(self._session)
        self._event_loop.start()

        self._session.login(
            self._config['spotify']['username'],
            self._config['spotify']['password'])

    def on_stop(self):
        logger.debug('Logging out of Spotify')
        self._session.logout()
        self._logged_out.wait()
        self._event_loop.stop()

    def _get_session(self, config):
        session = spotify.Session(self._get_spotify_config(config))

        session.connection.allow_network = config['spotify']['allow_network']

        self._bitrate = config['spotify']['bitrate']
        session.preferred_bitrate = BITRATES[self._bitrate]
        session.volume_normalization = (
            config['spotify']['volume_normalization'])

        session.on(
            spotify.SessionEvent.CONNECTION_STATE_UPDATED,
            on_connection_state_changed,
            self._logged_in, self._logged_out, self._online)

        # TODO Pause on PLAY_TOKEN_LOST, but only if this backend is currently
        # playing.

        return session

    def _get_spotify_config(self, config):
        spotify_config = spotify.Config()
        spotify_config.load_application_key_file(
            os.path.join(os.path.dirname(__file__), 'spotify_appkey.key'))
        spotify_config.cache_location = config['spotify']['cache_dir']
        spotify_config.settings_location = config['spotify']['settings_dir']
        return spotify_config


def on_connection_state_changed(
        session, logged_in_event, logged_out_event, online_event):

    # Called from the pyspotify event loop, and not in an actor context.
    if session.connection.state is spotify.ConnectionState.LOGGED_OUT:
        logger.debug('Logged out of Spotify')
        logged_in_event.clear()
        logged_out_event.set()
        online_event.clear()
    elif session.connection.state is spotify.ConnectionState.LOGGED_IN:
        logger.info('Logged in to Spotify in online mode')
        logged_in_event.set()
        logged_out_event.clear()
        online_event.set()
    elif session.connection.state is spotify.ConnectionState.DISCONNECTED:
        logger.info('Disconnected from Spotify')
        online_event.clear()
    elif session.connection.state is spotify.ConnectionState.OFFLINE:
        logger.info('Logged in to Spotify in offline mode')
        logged_in_event.set()
        logged_out_event.clear()
        online_event.clear()
