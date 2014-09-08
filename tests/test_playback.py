from __future__ import unicode_literals

import mock

from mopidy import audio, backend as backend_api

import pytest

import spotify

from mopidy_spotify import backend, playback


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.fixture
def session_mock():
    sp_session_mock = mock.Mock(spec=spotify.Session)
    return sp_session_mock


@pytest.fixture
def backend_mock(config, session_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._session = session_mock
    return backend_mock


@pytest.fixture
def provider(audio_mock, backend_mock):
    return playback.SpotifyPlaybackProvider(
        audio=audio_mock, backend=backend_mock)


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)
