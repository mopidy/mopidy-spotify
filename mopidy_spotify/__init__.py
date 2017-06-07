from __future__ import unicode_literals

import os

from mopidy import config, ext


__version__ = '3.1.0'


class Extension(ext.Extension):

    dist_name = 'Mopidy-Spotify'
    ext_name = 'spotify'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()

        schema['username'] = config.String()
        schema['password'] = config.Secret()

        schema['client_id'] = config.String()
        schema['client_secret'] = config.Secret()

        schema['bitrate'] = config.Integer(choices=(96, 160, 320))
        schema['volume_normalization'] = config.Boolean()
        schema['private_session'] = config.Boolean()

        schema['timeout'] = config.Integer(minimum=0)

        schema['cache_dir'] = config.Deprecated()  # since 2.0
        schema['settings_dir'] = config.Deprecated()  # since 2.0

        schema['allow_cache'] = config.Boolean()
        schema['allow_network'] = config.Boolean()
        schema['allow_playlists'] = config.Boolean()

        schema['search_album_count'] = config.Integer(minimum=0, maximum=200)
        schema['search_artist_count'] = config.Integer(minimum=0, maximum=200)
        schema['search_track_count'] = config.Integer(minimum=0, maximum=200)

        schema['toplist_countries'] = config.List(optional=True)

        return schema

    def setup(self, registry):
        from mopidy_spotify.backend import SpotifyBackend

        registry.add('backend', SpotifyBackend)
