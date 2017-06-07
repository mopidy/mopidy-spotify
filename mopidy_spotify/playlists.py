from __future__ import unicode_literals

import logging

from mopidy import backend

import spotify

from mopidy_spotify import translator, utils


logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config['spotify']['timeout']

    def as_list(self):
        with utils.time_logger('playlists.as_list()'):
            return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self):
        if self._backend._session is None:
            return

        if self._backend._session.playlist_container is None:
            return

        username = self._backend._session.user_name
        folders = []

        for sp_playlist in self._backend._session.playlist_container:
            if isinstance(sp_playlist, spotify.PlaylistFolder):
                if sp_playlist.type is spotify.PlaylistType.START_FOLDER:
                    folders.append(sp_playlist.name)
                elif sp_playlist.type is spotify.PlaylistType.END_FOLDER:
                    folders.pop()
                continue

            playlist_ref = translator.to_playlist_ref(
                sp_playlist, folders=folders, username=username)
            if playlist_ref is not None:
                yield playlist_ref

    def get_items(self, uri):
        with utils.time_logger('playlist.get_items(%s)' % uri):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger('playlists.lookup(%s)' % uri):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False):
        try:
            sp_playlist = self._backend._session.get_playlist(uri)
        except spotify.Error as exc:
            logger.debug('Failed to lookup Spotify URI %s: %s', uri, exc)
            return

        if not sp_playlist.is_loaded:
            logger.debug(
                'Waiting for Spotify playlist to load: %s', sp_playlist)
            sp_playlist.load(self._timeout)

        username = self._backend._session.user_name
        return translator.to_playlist(
            sp_playlist, username=username, bitrate=self._backend._bitrate,
            as_items=as_items)

    def refresh(self):
        pass  # Not needed as long as we don't cache anything.

    def create(self, name):
        try:
            sp_playlist = (
                self._backend._session.playlist_container
                .add_new_playlist(name))
        except ValueError as exc:
            logger.warning(
                'Failed creating new Spotify playlist "%s": %s', name, exc)
        except spotify.Error:
            logger.warning('Failed creating new Spotify playlist "%s"', name)
        else:
            username = self._backend._session.user_name
            return translator.to_playlist(sp_playlist, username=username)

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO


def on_container_loaded(sp_playlist_container):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug('Spotify playlist container loaded')

    # This event listener is also called after playlists are added, removed and
    # moved, so since Mopidy currently only supports the "playlists_loaded"
    # event this is the only place we need to trigger a Mopidy backend event.
    backend.BackendListener.send('playlists_loaded')


def on_playlist_added(sp_playlist_container, sp_playlist, index):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug(
        'Spotify playlist "%s" added to index %d', sp_playlist.name, index)

    # XXX Should Mopidy support more fine grained playlist events which this
    # event can trigger?


def on_playlist_removed(sp_playlist_container, sp_playlist, index):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug(
        'Spotify playlist "%s" removed from index %d', sp_playlist.name, index)

    # XXX Should Mopidy support more fine grained playlist events which this
    # event can trigger?


def on_playlist_moved(
        sp_playlist_container, sp_playlist, old_index, new_index):
    # Called from the pyspotify event loop, and not in an actor context.
    logger.debug(
        'Spotify playlist "%s" moved from index %d to %d',
        sp_playlist.name, old_index, new_index)

    # XXX Should Mopidy support more fine grained playlist events which this
    # event can trigger?
