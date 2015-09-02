from __future__ import unicode_literals

import threading

import mock

from mopidy import audio, backend as backend_api, models

import pytest

import spotify

from mopidy_spotify import backend, playback


@pytest.fixture
def audio_mock():
    audio_mock = mock.Mock(spec=audio.Audio)
    return audio_mock


@pytest.yield_fixture
def audio_lib_mock():
    patcher = mock.patch.object(playback, 'audio', spec=audio)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def session_mock():
    sp_session_mock = mock.Mock(spec=spotify.Session)
    return sp_session_mock


@pytest.fixture
def backend_mock(config, session_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._actor_proxy = None
    backend_mock._session = session_mock
    return backend_mock


@pytest.fixture
def provider(audio_mock, backend_mock):
    return playback.SpotifyPlaybackProvider(
        audio=audio_mock, backend=backend_mock)


def test_is_a_playback_provider(provider):
    assert isinstance(provider, backend_api.PlaybackProvider)


def test_connect_events_adds_music_delivery_handler_to_session(
        session_mock, audio_mock, backend_mock):

    playback_provider = provider(audio_mock, backend_mock)
    playback_provider._connect_events()

    assert (mock.call(
        spotify.SessionEvent.MUSIC_DELIVERY,
        playback.music_delivery_callback,
        audio_mock,
        playback_provider._seeking_event,
        playback_provider._push_audio_data_event,
        playback_provider._buffer_timestamp)
        in session_mock.on.call_args_list)


def test_connect_events_adds_end_of_track_handler_to_session(
        session_mock, audio_mock, backend_mock):

    playback_provider = provider(audio_mock, backend_mock)
    playback_provider._connect_events()

    assert (mock.call(
        spotify.SessionEvent.END_OF_TRACK,
        playback.end_of_track_callback,
        playback_provider._end_of_track_event, audio_mock)
        in session_mock.on.call_args_list)


def test_change_track_aborts_if_no_track_uri(provider):
    track = models.Track()

    assert provider.change_track(track) is False


def test_change_track_loads_and_plays_spotify_track(session_mock, provider):
    uri = 'spotify:track:test'
    track = models.Track(uri=uri)

    assert provider.change_track(track) is True

    session_mock.get_track.assert_called_once_with(uri)
    sp_track_mock = session_mock.get_track.return_value
    sp_track_mock.load.assert_called_once_with(10)
    session_mock.player.load.assert_called_once_with(sp_track_mock)
    session_mock.player.play.assert_called_once_with()


def test_change_track_aborts_on_spotify_error(session_mock, provider):
    track = models.Track(uri='spotfy:track:test')
    session_mock.get_track.side_effect = spotify.Error

    assert provider.change_track(track) is False


def test_change_track_sets_up_appsrc(audio_mock, provider):
    track = models.Track(uri='spotfy:track:test')

    assert provider.change_track(track) is True

    assert provider._buffer_timestamp.get() == 0
    assert audio_mock.prepare_change.call_count == 0
    audio_mock.set_appsrc.assert_called_once_with(
        playback.GST_CAPS,
        need_data=mock.ANY, enough_data=mock.ANY, seek_data=mock.ANY)
    assert audio_mock.start_playback.call_count == 0
    audio_mock.set_metadata.assert_called_once_with(track)


def test_resume_starts_spotify_playback(session_mock, provider):
    provider.resume()

    session_mock.player.play.assert_called_once_with()


def test_stop_pauses_spotify_playback(session_mock, provider):
    provider.stop()

    session_mock.player.pause.assert_called_once_with()


def test_on_seek_data_updates_timestamp_and_seeks_in_spotify(
        session_mock, provider):
    provider.on_seek_data(1780)

    assert provider._buffer_timestamp.get() == 1780000000
    session_mock.player.seek.assert_called_once_with(1780)


def test_on_seek_data_ignores_first_seek_to_zero_on_every_play(
        session_mock, provider):
    provider._seeking_event.set()
    track = models.Track(uri='spotfy:track:test')

    provider.change_track(track)
    provider.on_seek_data(0)

    assert not provider._seeking_event.is_set()
    assert session_mock.player.seek.call_count == 0


def test_need_data_callback():
    event = threading.Event()
    assert not event.is_set()

    playback.need_data_callback(event, 100)

    assert event.is_set()


def test_enough_data_callback():
    event = threading.Event()
    event.set()
    assert event.is_set()

    playback.enough_data_callback(event)

    assert not event.is_set()


def test_seek_data_callback():
    seeking_event = threading.Event()
    backend_mock = mock.Mock()

    playback.seek_data_callback(seeking_event, backend_mock, 1340)

    assert seeking_event.is_set()
    backend_mock.playback.on_seek_data.assert_called_once_with(1340)


def test_music_delivery_rejects_data_when_seeking(session_mock, audio_mock):
    audio_format = mock.Mock()
    frames = b'123'
    num_frames = 1
    seeking_event = threading.Event()
    seeking_event.set()
    push_audio_data_event = threading.Event()
    push_audio_data_event.set()
    buffer_timestamp = mock.Mock()
    assert seeking_event.is_set()

    result = playback.music_delivery_callback(
        session_mock, audio_format, frames, num_frames,
        audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    assert seeking_event.is_set()
    assert audio_mock.emit_data.call_count == 0
    assert result == num_frames


def test_music_delivery_when_seeking_accepts_data_after_empty_delivery(
        session_mock, audio_mock):

    audio_format = mock.Mock()
    frames = b''
    num_frames = 0
    seeking_event = threading.Event()
    seeking_event.set()
    push_audio_data_event = threading.Event()
    push_audio_data_event.set()
    buffer_timestamp = mock.Mock()
    assert seeking_event.is_set()

    result = playback.music_delivery_callback(
        session_mock, audio_format, frames, num_frames,
        audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    assert not seeking_event.is_set()
    assert audio_mock.emit_data.call_count == 0
    assert result == num_frames


def test_music_delivery_rejects_data_depending_on_push_audio_data_event(
        session_mock, audio_mock):

    audio_format = mock.Mock()
    frames = b'123'
    num_frames = 1
    seeking_event = threading.Event()
    push_audio_data_event = threading.Event()
    buffer_timestamp = mock.Mock()
    assert not push_audio_data_event.is_set()

    result = playback.music_delivery_callback(
        session_mock, audio_format, frames, num_frames,
        audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    assert audio_mock.emit_data.call_count == 0
    assert result == 0


def test_music_delivery_shortcuts_if_no_data_in_frames(
        session_mock, audio_lib_mock, audio_mock):

    audio_format = mock.Mock(channels=2, sample_rate=44100, sample_type=0)
    frames = b''
    num_frames = 1
    seeking_event = threading.Event()
    push_audio_data_event = threading.Event()
    push_audio_data_event.set()
    buffer_timestamp = mock.Mock()

    result = playback.music_delivery_callback(
        session_mock, audio_format, frames, num_frames,
        audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    assert result == 0
    assert audio_lib_mock.create_buffer.call_count == 0
    assert audio_mock.emit_data.call_count == 0


def test_music_delivery_rejects_unknown_audio_formats(
        session_mock, audio_mock):

    audio_format = mock.Mock(sample_type=17)
    frames = b'123'
    num_frames = 1
    seeking_event = threading.Event()
    push_audio_data_event = threading.Event()
    push_audio_data_event.set()
    buffer_timestamp = mock.Mock()

    with pytest.raises(AssertionError) as excinfo:
        playback.music_delivery_callback(
            session_mock, audio_format, frames, num_frames,
            audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    assert 'Expects 16-bit signed integer samples' in str(excinfo.value)


def test_music_delivery_creates_gstreamer_buffer_and_gives_it_to_audio(
        session_mock, audio_mock, audio_lib_mock):

    audio_lib_mock.calculate_duration.return_value = mock.sentinel.duration
    audio_lib_mock.create_buffer.return_value = mock.sentinel.gst_buffer

    audio_format = mock.Mock(channels=2, sample_rate=44100, sample_type=0)
    frames = b'\x00\x00'
    num_frames = 1
    seeking_event = threading.Event()
    push_audio_data_event = threading.Event()
    push_audio_data_event.set()
    buffer_timestamp = mock.Mock()
    buffer_timestamp.get.return_value = mock.sentinel.timestamp

    result = playback.music_delivery_callback(
        session_mock, audio_format, frames, num_frames,
        audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    audio_lib_mock.calculate_duration.assert_called_once_with(1, 44100)
    audio_lib_mock.create_buffer.assert_called_once_with(
        frames, timestamp=mock.sentinel.timestamp,
        duration=mock.sentinel.duration)
    buffer_timestamp.increase.assert_called_once_with(mock.sentinel.duration)
    audio_mock.emit_data.assert_called_once_with(mock.sentinel.gst_buffer)
    assert result == num_frames


def test_music_delivery_consumes_zero_frames_if_audio_fails(
        session_mock, audio_mock, audio_lib_mock):

    audio_mock.emit_data.return_value.get.return_value = False

    audio_format = mock.Mock(channels=2, sample_rate=44100, sample_type=0)
    frames = b'\x00\x00'
    num_frames = 1
    seeking_event = threading.Event()
    push_audio_data_event = threading.Event()
    push_audio_data_event.set()
    buffer_timestamp = mock.Mock()
    buffer_timestamp.get.return_value = mock.sentinel.timestamp

    result = playback.music_delivery_callback(
        session_mock, audio_format, frames, num_frames,
        audio_mock, seeking_event, push_audio_data_event, buffer_timestamp)

    assert buffer_timestamp.increase.call_count == 0
    assert result == 0


def test_end_of_track_callback(session_mock, audio_mock):
    end_of_track_event = threading.Event()

    playback.end_of_track_callback(
        session_mock, end_of_track_event, audio_mock)

    assert end_of_track_event.is_set()
    audio_mock.emit_data.assert_called_once_with(None)


def test_duplicate_end_of_track_callback_is_ignored(session_mock, audio_mock):
    end_of_track_event = threading.Event()
    end_of_track_event.set()

    playback.end_of_track_callback(
        session_mock, end_of_track_event, audio_mock)

    assert end_of_track_event.is_set()
    assert audio_mock.emit_data.call_count == 0


def test_buffer_timestamp_wrapper():
    wrapper = playback.BufferTimestamp(0)
    assert wrapper.get() == 0

    wrapper.set(17)
    assert wrapper.get() == 17

    wrapper.increase(3)
    assert wrapper.get() == 20
