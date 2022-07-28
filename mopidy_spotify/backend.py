import pykka
from mopidy import backend

from mopidy_spotify import Extension, library, playlists, web


class SpotifyBackend(pykka.ThreadingActor, backend.Backend):
    def __init__(self, config, audio):
        super().__init__()

        self._config = config
        self._audio = audio
        self._bitrate = config["spotify"]["bitrate"]
        self._web_client = None

        if config["spotify"]["allow_cache"]:
            self._cache_location = Extension().get_cache_dir(config)

        self.library = library.SpotifyLibraryProvider(backend=self)
        self.playback = SpotifyPlaybackProvider(audio=audio, backend=self)
        if config["spotify"]["allow_playlists"]:
            self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)
        else:
            self.playlists = None
        self.uri_schemes = ["spotify"]

    def on_start(self):
        self._web_client = web.SpotifyOAuthClient(
            client_id=self._config["spotify"]["client_id"],
            client_secret=self._config["spotify"]["client_secret"],
            proxy_config=self._config["proxy"],
        )
        self._web_client.login()

        if self.playlists is not None:
            self.playlists.refresh()


class SpotifyPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache_location = Extension().get_cache_dir(self.backend._config)

    def on_source_setup(self, source):
        config = self.backend._config["spotify"]
        for prop in ["username", "password"]:
            source.set_property(prop, config[prop])
        if config["allow_cache"]:
            source.set_property("cache-credentials", self._cache_location)
