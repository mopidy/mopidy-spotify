from __future__ import unicode_literals

import logging

import pykka

from mopidy.backends import base
from mopidy_spotify.library import SpotifyLibraryProvider
from mopidy_spotify.playback import SpotifyPlaybackProvider
from mopidy_spotify.session_manager import SpotifySessionManager
from mopidy_spotify.playlists import SpotifyPlaylistsProvider

logger = logging.getLogger('mopidy_spotify')


class SpotifyBackend(pykka.ThreadingActor, base.Backend):
    def __init__(self, config, audio):
        super(SpotifyBackend, self).__init__()

        self.config = config

        self.library = SpotifyLibraryProvider(backend=self)
        self.playback = SpotifyPlaybackProvider(audio=audio, backend=self)
        self.playlists = SpotifyPlaylistsProvider(backend=self)

        self.uri_schemes = ['spotify']

        self.spotify = SpotifySessionManager(
            config, audio=audio, backend_ref=self.actor_ref)

    def on_start(self):
        logger.info('Mopidy uses SPOTIFY(R) CORE')
        logger.debug('Connecting to Spotify')
        self.spotify.start()

    def on_stop(self):
        self.spotify.logout()
