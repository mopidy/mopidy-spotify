from __future__ import unicode_literals

import logging
import time

from mopidy import backend

import spotify

from mopidy_spotify import translator, utils, web


_sp_links = {}
logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend

    def as_list(self):
        with utils.time_logger('playlists.as_list()'):
            return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self):
        if not self._backend._web_session.playlists_loaded:
            return

        username = self._backend._web_session.user_name

        for web_playlist in self._backend._web_session.get_user_playlists(include_tracks=False):
            playlist_ref = translator.to_playlist_ref(web_playlist, username)
            if playlist_ref is not None:
                yield playlist_ref

    def get_items(self, uri):
        with utils.time_logger('playlist.get_items(%s)' % uri):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger('playlists.lookup(%s)' % uri):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False):
        return playlist_lookup(
                self._backend._session, self._backend._web_session, uri,
                self._backend._bitrate, as_items)

    def refresh(self):
        # TODO: Clear/invalidate memoize caches on refresh?
        _sp_links = {}
        with utils.time_logger('Refresh Playlists', logging.INFO):
            self._backend._web_session.load_playlists()

            # Allow libspotify to get track links so they load in the background.
            for playlist_ref in self.as_list():
                self.get_items(playlist_ref.uri)

        on_container_loaded(None)

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


def playlist_lookup(session, web_session, uri, bitrate, as_items=False):
    if not web_session.playlists_loaded:
        return

    web_playlist = web_session.get_playlist(uri)
    playlist = translator.to_playlist(
            web_playlist, username=web_session.user_name, bitrate=bitrate,
            as_items=as_items)
    if playlist is None:
        return

    if session.connection.state is spotify.ConnectionState.LOGGED_IN:
        if as_items:
            tracks = playlist
        else:
            tracks = playlist.tracks

        for track in tracks:
            if track.uri in _sp_links:
                continue
            try:
                _sp_links[track.uri] = session.get_link(track.uri)
            except ValueError as exc:
                logger.info('Failed to get link "%s": %s', track.uri, exc)

    return playlist


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
