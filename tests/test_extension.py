from unittest import mock

from mopidy_spotify import Extension
from mopidy_spotify import backend as backend_lib


def test_get_default_config() -> None:
    ext = Extension()

    config = ext.get_default_config()

    assert "[spotify]" in config
    assert "enabled = true" in config


def test_get_config_schema() -> None:
    ext = Extension()

    schema = ext.get_config_schema()

    assert "username" in schema
    assert "password" in schema
    assert "bitrate" in schema
    assert "volume_normalization" in schema
    assert "timeout" in schema
    assert "cache_dir" in schema
    assert "settings_dir" in schema
    assert "allow_cache" in schema
    assert "cache_size" in schema
    assert "allow_playlists" in schema
    assert "search_album_count" in schema
    assert "search_artist_count" in schema
    assert "search_track_count" in schema


def test_setup() -> None:
    registry = mock.Mock()

    ext = Extension()
    ext.setup(registry)

    registry.add.assert_called_with("backend", backend_lib.SpotifyBackend)


def test_get_credentials_dir(tmp_path) -> None:
    config = {"core": {"data_dir": tmp_path}}

    ext = Extension()
    result = ext.get_credentials_dir(config)
    assert result == tmp_path / "spotify" / "credentials-cache"
    assert result.is_dir()
    assert result.stat().st_mode == 0o40700

    result2 = ext.get_credentials_dir(config)  # check exists_ok
    assert result == result2
