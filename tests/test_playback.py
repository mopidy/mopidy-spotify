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


def test_init_adds_music_delivery_handler_to_session(
        session_mock, audio_mock, backend_mock):

    playback_provider = provider(audio_mock, backend_mock)

    assert (mock.call(
        spotify.SessionEvent.MUSIC_DELIVERY,
        playback.music_delivery_callback,
        audio_mock,
        playback_provider._push_audio_data_event,
        playback_provider._buffer_timestamp)
        in session_mock.on.call_args_list)


def test_init_adds_end_of_track_handler_to_session(
        session_mock, audio_mock, backend_mock):

    provider(audio_mock, backend_mock)

    assert (mock.call(
        spotify.SessionEvent.END_OF_TRACK,
        playback.end_of_track_callback, audio_mock)
        in session_mock.on.call_args_list)


def test_resume_starts_spotify_playback(session_mock, provider):
    provider.resume()

    session_mock.player.play.assert_called_once_with()


def test_end_of_track_callback(session_mock, audio_mock):
    playback.end_of_track_callback(session_mock, audio_mock)

    audio_mock.emit_end_of_stream.assert_called_once_with()


def test_buffer_timestamp_wrapper():
    wrapper = playback.BufferTimestamp(0)
    assert wrapper.get() == 0

    wrapper.set(17)
    assert wrapper.get() == 17

    wrapper.increase(3)
    assert wrapper.get() == 20
