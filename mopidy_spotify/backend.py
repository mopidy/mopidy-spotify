from __future__ import unicode_literals

import logging
import os
import threading

from mopidy import backend
from mopidy.config import keyring

import pykka

import spotify

from mopidy_spotify import Extension, library, playback, playlists


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
        self._actor_proxy = None
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
        self._actor_proxy = self.actor_ref.proxy()
        self._session = self._get_session(self._config)

        self._event_loop = spotify.EventLoop(self._session)
        self._event_loop.start()

        credentials = self._create_credentials()
        self._session.login(credentials['username'], credentials['password'])

    def _create_credentials(self):
        credentials = dict(
            username=self._config['spotify']['username'],
            password=self._config['spotify']['password'],
        )
        if not self._is_credential_info_provided():
            logger.info('credentials not found in config, trying keyring')
            credentials = fetch_credentials()
        return credentials

    def _is_credential_info_provided(self):
        config = self._config['spotify']
        return (config['username'] is not None
                and config['password'] is not None)

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

        backend_actor_proxy = self._actor_proxy
        session.on(
            spotify.SessionEvent.CONNECTION_STATE_UPDATED,
            on_connection_state_changed,
            self._logged_in, self._logged_out, backend_actor_proxy)
        session.on(
            spotify.SessionEvent.PLAY_TOKEN_LOST,
            on_play_token_lost, backend_actor_proxy)

        return session

    def _get_spotify_config(self, config):
        ext = Extension()
        spotify_config = spotify.Config()
        spotify_config.load_application_key_file(
            os.path.join(os.path.dirname(__file__), 'spotify_appkey.key'))
        if config['spotify']['allow_cache']:
            spotify_config.cache_location = ext.get_cache_dir(config)
        else:
            spotify_config.cache_location = None
        spotify_config.settings_location = ext.get_data_dir(config)
        return spotify_config

    def on_logged_in(self):
        if self._config['spotify']['private_session']:
            logger.info('Spotify private session activated')
            self._session.social.private_session = True

        self._session.playlist_container.on(
            spotify.PlaylistContainerEvent.CONTAINER_LOADED,
            playlists.on_container_loaded)
        self._session.playlist_container.on(
            spotify.PlaylistContainerEvent.PLAYLIST_ADDED,
            playlists.on_playlist_added)
        self._session.playlist_container.on(
            spotify.PlaylistContainerEvent.PLAYLIST_REMOVED,
            playlists.on_playlist_removed)
        self._session.playlist_container.on(
            spotify.PlaylistContainerEvent.PLAYLIST_MOVED,
            playlists.on_playlist_moved)

    def on_play_token_lost(self):
        if self._session.player.state == spotify.PlayerState.PLAYING:
            self.playback.pause()
            logger.warning(
                'Spotify has been paused because your account is '
                'being used somewhere else.')


def on_connection_state_changed(
        session, logged_in_event, logged_out_event, backend):

    # Called from the pyspotify event loop, and not in an actor context.
    if session.connection.state is spotify.ConnectionState.LOGGED_OUT:
        logger.debug('Logged out of Spotify')
        logged_in_event.clear()
        logged_out_event.set()
    elif session.connection.state is spotify.ConnectionState.LOGGED_IN:
        logger.info('Logged in to Spotify in online mode')
        logged_in_event.set()
        logged_out_event.clear()
        backend.on_logged_in()
    elif session.connection.state is spotify.ConnectionState.DISCONNECTED:
        logger.info('Disconnected from Spotify')
    elif session.connection.state is spotify.ConnectionState.OFFLINE:
        logger.info('Logged in to Spotify in offline mode')
        logged_in_event.set()
        logged_out_event.clear()


def on_play_token_lost(session, backend):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug('Spotify play token lost')
    backend.on_play_token_lost()


def fetch(wanted_key):
    for section, key, value in keyring.fetch():
        if section == 'mopidy-spotify' and key == wanted_key:
            return value


def fetch_credentials():
    return dict(username=fetch('username'), password=fetch('password'))
