from typing import Any
from unittest import mock

import pytest
from mopidy import audio
from mopidy import backend as backend_api

from mopidy_spotify import backend, web


@pytest.fixture
def audio_mock() -> mock.Mock:
    return mock.Mock(spec=audio.Audio)


@pytest.fixture
def backend_mock(config: dict[str, Any]) -> mock.Mock:
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._web_client = mock.Mock(spec=web.OAuthClient)
    return backend_mock


@pytest.fixture
def provider(
    audio_mock: mock.Mock, backend_mock: mock.Mock
) -> backend.SpotifyPlaybackProvider:
    return backend.SpotifyPlaybackProvider(audio=audio_mock, backend=backend_mock)


def test_is_a_playback_provider(provider: backend.SpotifyPlaybackProvider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_on_source_setup_sets_properties(
    config: dict[str, Any], provider: backend.SpotifyPlaybackProvider
):
    mock_source = mock.MagicMock()
    provider.on_source_setup(mock_source)
    spotify_cache_dir = backend.Extension.get_cache_dir(config)
    spotify_data_dir = backend.Extension.get_data_dir(config)
    cred_dir = spotify_data_dir / "credentials-cache"

    assert mock_source.set_property.mock_calls == [
        mock.call("bitrate", "160"),
        mock.call("cache-credentials", cred_dir),
        mock.call("access-token", mock.ANY),
        mock.call("cache-files", spotify_cache_dir),
        mock.call("cache-max-size", 8589934592),
    ]


def test_on_source_setup_without_caching(
    config: dict[str, Any], provider: backend.SpotifyPlaybackProvider
):
    config["spotify"]["allow_cache"] = False
    mock_source = mock.MagicMock()
    provider.on_source_setup(mock_source)
    spotify_data_dir = backend.Extension.get_data_dir(config)
    cred_dir = spotify_data_dir / "credentials-cache"

    assert mock_source.set_property.mock_calls == [
        mock.call("bitrate", "160"),
        mock.call("cache-credentials", cred_dir),
        mock.call("access-token", mock.ANY),
    ]


def test_on_source_setup_bitrate_string(
    config: dict[str, Any], provider: backend.SpotifyPlaybackProvider
):
    config["spotify"]["bitrate"] = 320
    mock_source = mock.MagicMock()
    provider.on_source_setup(mock_source)

    assert mock.call("bitrate", "320") in mock_source.set_property.mock_calls
