import logging
import pathlib
import threading

import pykka
from mopidy import backend, httpclient

import spotify
from mopidy_spotify import Extension, library, playlists, web

logger = logging.getLogger(__name__)


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):

    def __init__(self, config, audio):
        super().__init__()

        self._config = config
        self._audio = audio
        self._actor_proxy = None
        self._bitrate = config["spotify"]["bitrate"]
        self._web_client = None

        self.library = library.SpotifyLibraryProvider(backend=self)
        self.playback = SpotifyPlaybackProvider(audio=audio, backend=self)
        if config["spotify"]["allow_playlists"]:
            self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)
        else:
            self.playlists = None
        self.uri_schemes = ["spotify"]

    def on_start(self):
        self._actor_proxy = self.actor_ref.proxy()

        self._web_client = web.SpotifyOAuthClient(
            client_id=self._config["spotify"]["client_id"],
            client_secret=self._config["spotify"]["client_secret"],
            proxy_config=self._config["proxy"],
        )
        self._web_client.login()

        if self.playlists is not None:
            self.playlists.refresh()

class SpotifyPlaybackProvider(backend.PlaybackProvider):
    def translate_uri(self, uri):
        username = self.backend._config["spotify"]["username"]
        password = self.backend._config["spotify"]["password"]
        return f"{uri}?username={username}&password={password}"
