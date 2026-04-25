import pathlib
from importlib.metadata import version
from typing import override

import cyclopts
from mopidy import config, ext

__version__ = version("mopidy-spotify")


class Extension(ext.Extension):
    dist_name = "mopidy-spotify"
    ext_name = "spotify"
    version = __version__

    @override
    def get_default_config(self) -> str:
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    @override
    def get_config_schema(self) -> config.ConfigSchema:
        schema = super().get_config_schema()

        schema["username"] = config.Deprecated()  # since 5.0
        schema["password"] = config.Deprecated()  # since 5.0

        schema["client_id"] = config.String()
        schema["client_secret"] = config.Secret()

        schema["bitrate"] = config.Integer(choices=(96, 160, 320))
        schema["volume_normalization"] = config.Boolean()
        schema["private_session"] = config.Deprecated()  # since 5.0

        schema["timeout"] = config.Integer(minimum=0)

        schema["cache_dir"] = config.Deprecated()  # since 2.0
        schema["settings_dir"] = config.Deprecated()  # since 2.0

        schema["allow_cache"] = config.Boolean()
        schema["cache_size"] = config.Integer(minimum=0)

        schema["allow_network"] = config.Deprecated()  # since 5.0
        schema["allow_playlists"] = config.Boolean()

        schema["search_album_count"] = config.Integer(minimum=0, maximum=200)
        schema["search_artist_count"] = config.Integer(minimum=0, maximum=200)
        schema["search_track_count"] = config.Integer(minimum=0, maximum=200)

        schema["toplist_countries"] = config.Deprecated()  # since 5.0

        return schema

    @override
    def setup(self, registry: ext.Registry) -> None:
        from mopidy_spotify.backend import SpotifyBackend  # noqa: PLC0415

        registry.add("backend", SpotifyBackend)

    @override
    def get_command(self) -> cyclopts.App:
        from .commands import app  # noqa: PLC0415

        return app

    @classmethod
    def get_credentials_dir(cls, config: config.Config) -> pathlib.Path:
        data_dir = cls.get_data_dir(config)
        credentials_dir = data_dir / "credentials-cache"
        credentials_dir.mkdir(mode=0o700, exist_ok=True)
        return credentials_dir
