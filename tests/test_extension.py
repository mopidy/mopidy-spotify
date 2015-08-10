from __future__ import unicode_literals

import mock

from mopidy_spotify import Extension, backend as backend_lib


def test_get_default_config():
    ext = Extension()

    config = ext.get_default_config()

    assert '[spotify]' in config
    assert 'enabled = true' in config


def test_get_config_schema():
    ext = Extension()

    schema = ext.get_config_schema()

    assert 'username' in schema
    assert 'password' in schema
    assert 'bitrate' in schema
    assert 'volume_normalization' in schema
    assert 'private_session' in schema
    assert 'timeout' in schema
    assert 'cache_dir' in schema
    assert 'settings_dir' in schema
    assert 'allow_cache' in schema
    assert 'allow_network' in schema
    assert 'allow_playlists' in schema
    assert 'search_album_count' in schema
    assert 'search_artist_count' in schema
    assert 'search_track_count' in schema
    assert 'toplist_countries' in schema


def test_setup():
    registry = mock.Mock()

    ext = Extension()
    ext.setup(registry)

    registry.add.assert_called_with('backend', backend_lib.SpotifyBackend)
