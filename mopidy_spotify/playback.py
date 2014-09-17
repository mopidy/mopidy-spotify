from __future__ import unicode_literals

import logging
import threading

from mopidy import backend

import spotify


logger = logging.getLogger(__name__)


class SpotifyPlaybackProvider(backend.PlaybackProvider):

    def __init__(self, *args, **kwargs):
        super(SpotifyPlaybackProvider, self).__init__(*args, **kwargs)

        self._buffer_timestamp = BufferTimestamp(0)
        self._push_audio_data_event = threading.Event()
        self._push_audio_data_event.set()

        self.backend._session.on(
            spotify.SessionEvent.MUSIC_DELIVERY, music_delivery_callback,
            self.audio, self._push_audio_data_event, self._buffer_timestamp)
        self.backend._session.on(
            spotify.SessionEvent.END_OF_TRACK, end_of_track_callback,
            self.audio)

    def resume(self):
        self.backend._session.player.play()
        return super(SpotifyPlaybackProvider, self).resume()


def music_delivery_callback(
        session, audio_format, frames, num_frames,
        audio_actor, push_audio_data_event, buffer_timestamp):
    # This is called from an internal libspotify thread.
    # Ideally, nothing here should block.

    return 0  # TODO Implement


def end_of_track_callback(session, audio_actor):
    # This callback is called from the pyspotify event loop.

    logger.debug('End of track reached')
    audio_actor.emit_end_of_stream()


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
