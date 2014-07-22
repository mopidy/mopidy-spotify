from __future__ import unicode_literals

from mopidy import backend

import pykka


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super(SpotifyBackend, self).__init__()

        self._config = config
        self._audio = audio

        self.library = None
        self.playback = None
        self.playlists = None

        self.uri_schemes = ['spotify']
