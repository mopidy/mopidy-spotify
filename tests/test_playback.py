from unittest import mock

import pytest
from mopidy import audio
from mopidy import backend as backend_api

from mopidy_spotify import backend


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def backend_mock(config):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    return backend_mock


@pytest.fixture
def provider(audio_mock, backend_mock):
    return backend.SpotifyPlaybackProvider(
        audio=audio_mock, backend=backend_mock
    )


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_on_source_setup_sets_properties(config, provider):
    mock_source = mock.MagicMock()
    provider.on_source_setup(mock_source)
    spotify_cache_dir = backend.Extension.get_cache_dir(config)
    spotify_data_dir = backend.Extension.get_data_dir(config)
    cred_dir = spotify_data_dir / "credentials-cache"

    assert mock_source.set_property.mock_calls == [
        mock.call("username", "alice"),
        mock.call("password", "password"),
        mock.call("bitrate", "160"),
        mock.call("cache-credentials", cred_dir),
        mock.call("cache-files", spotify_cache_dir),
        mock.call("cache-max-size", 8589934592),
    ]


def test_on_source_setup_without_caching(config, provider):
    config["spotify"]["allow_cache"] = False
    mock_source = mock.MagicMock()
    provider.on_source_setup(mock_source)
    spotify_data_dir = backend.Extension.get_data_dir(config)
    cred_dir = spotify_data_dir / "credentials-cache"

    assert mock_source.set_property.mock_calls == [
        mock.call("username", "alice"),
        mock.call("password", "password"),
        mock.call("bitrate", "160"),
        mock.call("cache-credentials", cred_dir),
    ]


def test_on_source_setup_bitrate_string(config, provider):
    config["spotify"]["bitrate"] = 320
    mock_source = mock.MagicMock()
    provider.on_source_setup(mock_source)

    assert mock.call("bitrate", "320") in mock_source.set_property.mock_calls
