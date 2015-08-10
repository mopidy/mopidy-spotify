from __future__ import unicode_literals

import functools
import logging
import threading

from mopidy import audio, backend

import spotify


logger = logging.getLogger(__name__)


# These GStreamer caps matches the audio data provided by libspotify
LIBSPOTIFY_GST_CAPS = (
    'audio/x-raw-int, endianness=(int)1234, channels=(int)2, '
    'width=(int)16, depth=(int)16, signed=(boolean)true, '
    'rate=(int)44100')

# Extra log level with lower importance than DEBUG=10 for noisy debug logging
TRACE_LOG_LEVEL = 5


class SpotifyPlaybackProvider(backend.PlaybackProvider):

    def __init__(self, *args, **kwargs):
        super(SpotifyPlaybackProvider, self).__init__(*args, **kwargs)
        self._timeout = self.backend._config['spotify']['timeout']

        self._buffer_timestamp = BufferTimestamp(0)
        self._first_seek = False
        self._push_audio_data_event = threading.Event()
        self._push_audio_data_event.set()
        self._events_connected = False

    def _connect_events(self):
        if not self._events_connected:
            self._events_connected = True
            self.backend._session.on(
                spotify.SessionEvent.MUSIC_DELIVERY, music_delivery_callback,
                self.audio, self._push_audio_data_event,
                self._buffer_timestamp)
            self.backend._session.on(
                spotify.SessionEvent.END_OF_TRACK, end_of_track_callback,
                self.audio)

    def change_track(self, track):
        self._connect_events()

        if track.uri is None:
            return False

        need_data_callback_bound = functools.partial(
            need_data_callback, self._push_audio_data_event)
        enough_data_callback_bound = functools.partial(
            enough_data_callback, self._push_audio_data_event)

        seek_data_callback_bound = functools.partial(
            seek_data_callback, self.backend._actor_proxy)

        self._first_seek = True

        try:
            sp_track = self.backend._session.get_track(track.uri)
            sp_track.load(self._timeout)
            self.backend._session.player.load(sp_track)
            self.backend._session.player.play()

            self._buffer_timestamp.set(0)
            self.audio.set_appsrc(
                LIBSPOTIFY_GST_CAPS,
                need_data=need_data_callback_bound,
                enough_data=enough_data_callback_bound,
                seek_data=seek_data_callback_bound)
            self.audio.set_metadata(track)

            return True
        except spotify.Error as exc:
            logger.info('Playback of %s failed: %s', track.uri, exc)
            return False

    def resume(self):
        self.backend._session.player.play()
        return super(SpotifyPlaybackProvider, self).resume()

    def stop(self):
        self.backend._session.player.pause()
        return super(SpotifyPlaybackProvider, self).stop()

    def on_seek_data(self, time_position):
        logger.debug('Audio asked us to seek to %d', time_position)

        if time_position == 0 and self._first_seek:
            self._first_seek = False
            logger.debug('Skipping seek due to issue mopidy/mopidy#300')
            return

        self._buffer_timestamp.set(
            audio.millisecond_to_clocktime(time_position))
        self.backend._session.player.seek(time_position)


def need_data_callback(push_audio_data_event, length_hint):
    # This callback is called from GStreamer/the GObject event loop.
    logger.log(
        TRACE_LOG_LEVEL,
        'Audio asked for more data (hint=%d); accepting deliveries',
        length_hint)
    push_audio_data_event.set()


def enough_data_callback(push_audio_data_event):
    # This callback is called from GStreamer/the GObject event loop.
    logger.log(
        TRACE_LOG_LEVEL, 'Audio says it has enough data; rejecting deliveries')
    push_audio_data_event.clear()


def seek_data_callback(spotify_backend, time_position):
    # This callback is called from GStreamer/the GObject event loop.
    # It forwards the call to the backend actor.
    spotify_backend.playback.on_seek_data(time_position)


def music_delivery_callback(
        session, audio_format, frames, num_frames,
        audio_actor, push_audio_data_event, buffer_timestamp):
    # This is called from an internal libspotify thread.
    # Ideally, nothing here should block.

    if not push_audio_data_event.is_set():
        return 0

    known_format = (
        audio_format.sample_type == spotify.SampleType.INT16_NATIVE_ENDIAN)
    assert known_format, 'Expects 16-bit signed integer samples'

    capabilites = """
        audio/x-raw-int,
        endianness=(int)1234,
        channels=(int)%(channels)d,
        width=(int)16,
        depth=(int)16,
        signed=(boolean)true,
        rate=(int)%(sample_rate)d
    """ % {
        'channels': audio_format.channels,
        'sample_rate': audio_format.sample_rate,
    }

    duration = audio.calculate_duration(
        num_frames, audio_format.sample_rate)
    buffer_ = audio.create_buffer(
        bytes(frames), capabilites=capabilites,
        timestamp=buffer_timestamp.get(), duration=duration)

    buffer_timestamp.increase(duration)

    # We must block here to know if the buffer was consumed successfully.
    if audio_actor.emit_data(buffer_).get():
        return num_frames
    else:
        return 0


def end_of_track_callback(session, audio_actor):
    # This callback is called from the pyspotify event loop.

    logger.debug('End of track reached')
    audio_actor.emit_data(None)


class BufferTimestamp(object):
    """Wrapper around an int to serialize access by multiple threads.

    The value is used both from the backend actor and callbacks called by
    internal libspotify threads.
    """

    def __init__(self, value):
        self._value = value
        self._lock = threading.RLock()

    def get(self):
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = value

    def increase(self, value):
        with self._lock:
            self._value += value
