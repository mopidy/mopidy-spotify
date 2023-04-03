import ctypes
import logging
import os
import threading
import time

from mopidy import backend

from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality

logger = logging.getLogger(__name__)


class SpotifyPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._cleanup_lock = threading.Lock()
        self._pipe_writer_thread = None
        self._historic_pipes = []

    def login(self):
        username = self.backend._config["spotify"]["username"]
        password = self.backend._config["spotify"]["password"]
        session_builder = Session.Builder()
        session_builder.conf.stored_credentials_file = os.path.expanduser("~/.mopidy_spotify-credentials-cache.json")
        try:
            session = session_builder.stored_file(session_builder.conf.stored_credentials_file).create()
            logger.info("Logged into Spotify with cached credentials")
        except Exception:
            session = session_builder.user_pass(username, password).create()
            logger.info(f"Logged into Spotify as {username}")

        self._content_feeder = session.content_feeder()

        bitrate = int(self.backend._config["spotify"]["bitrate"])
        if bitrate > 0 and bitrate <= 96:
            self._quality = AudioQuality.NORMAL
        elif bitrate > 160:
            self._quality = AudioQuality.VERY_HIGH
        else:
            self._quality = AudioQuality.HIGH
        logger.info(f"Audio quality: {self._quality.name}")

    def translate_uri(self, uri):
        pipe_r, pipe_w = os.pipe()
        fd_url = f"fd://{pipe_r}"

        thread = threading.Thread(target=self._pipe_writer, args=(pipe_w, uri, fd_url))
        thread.start()
        self._cleanup_and_set(pipe_r, thread)
        logger.info(f"Track url {fd_url} for {uri}")
        return fd_url

    def _pipe_writer(self, pipe_w, uri, dest):
        try:
            logger.info(f"Pipe writer started for {dest}")
            stream = self._content_feeder.load(TrackId.from_uri(uri), VorbisOnlyAudioQuality(self._quality), False, None).input_stream.stream()
            stream_size = stream.size()
            bytes_requested = 0
            bytes_done = 0
            if self._quality == AudioQuality.VERY_HIGH:
                bytes_to_read = 16384
            else:
                bytes_to_read = 8192
            try:
                while bytes_done < stream_size:
                    bytes_requested += bytes_to_read
                    buffer = stream.read(bytes_to_read)
                    if buffer == -1 or len(buffer) < 1:
                        break
                    bytes_done += len(buffer)
                    os.writev(pipe_w, [buffer])
                    bytes_to_read = 2048
            except BrokenPipeError:
                time.sleep(0.1)
                logger.info("Pipe broken")
                pass
        except InterruptedError as e:
            logger.info(f"Interrupted (while handling {e.__context__})")
            pass
        finally:
            try:
                stream.close()
            finally:
                time.sleep(1)
                os.close(pipe_w)
        logger.info(f"Pipe writer finished. Bytes written: {bytes_done}, stream size: {stream_size}, total requested: {bytes_requested}")

    def _cleanup_and_set(self, pipe_r=None, thread=None):
        try:
            self._cleanup_lock.acquire()

            if pipe_r is not None:
                self._historic_pipes.append(pipe_r)
            while len(self._historic_pipes) > 3:
                os.close(self._historic_pipes.pop(0))

            if self._pipe_writer_thread is not None:
                for tid, tobj in threading._active.items():
                    if tobj is self._pipe_writer_thread:
                        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(InterruptedError))
                        break
            self._pipe_writer_thread = thread
        finally:
            self._cleanup_lock.release()

    def _close_all_pipes(self):
        while len(self._historic_pipes) > 0:
            try:
                os.close(self._historic_pipes.pop(0))
            except Exception:
                pass

    def handle_shutdown(self):
        self._cleanup_and_set()
        threading.Timer(2, self._close_all_pipes).start()

    def stop(self):
        self._cleanup_and_set()
        return super().stop()
