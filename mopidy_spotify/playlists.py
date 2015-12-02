from __future__ import unicode_literals

import logging

from mopidy import backend

import spotify

from mopidy_spotify import translator, utils


logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend

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
            sp_playlist.load()

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
        try:
            sp_playlist = self._backend._session.get_playlist(playlist.uri)
        except spotify.Error as exc:
            logger.debug('Failed to lookup Spotify Playlist URI %s: %s',
                         playlist.uri, exc)
            return
        if not sp_playlist.is_loaded:
            logger.debug(
                'Waiting for Spotify playlist to load: %s', sp_playlist)
            sp_playlist.load()
        if sp_playlist.name != playlist.name:
            logger.debug("Renaming playlist %s to %s",
                         sp_playlist.name, playlist.name)
            sp_playlist.name = playlist.name
        if len(sp_playlist.tracks) < len(playlist.tracks):
            # item was added
            added_uri = None
            added_idx = None
            for idx, track in enumerate(playlist.tracks):
                try:
                    if sp_playlist.tracks[idx].link.uri != track.uri:
                        added_uri = track.uri
                        added_idx = idx
                except IndexError:  # item was added to the end
                    added_uri = track.uri
                    added_idx = idx
            try:
                added_track = self._backend._session.get_track(added_uri)
                added_track.load()
                sp_playlist.add_tracks(added_track, added_idx)
            except spotify.Error as exc:
                logger.debug('Failed to lookup Spotify URI %s: %s',
                             added_uri, exc)
                return
            logger.info('Added track %s to playlist', added_track)
        elif len(sp_playlist.tracks) > len(playlist.tracks):
            # item was removed
            removed_idx = None
            removed_track = None
            for idx, track in enumerate(sp_playlist.tracks):
                try:
                    if playlist.tracks[idx].uri != track.link.uri:
                        removed_idx = idx
                        removed_track = track
                        break
                except IndexError:  # last item was removed
                    removed_idx = idx
            try:
                sp_playlist.remove_tracks(removed_idx)
            except spotify.Error as exc:
                logger.debug('Failed to remove track from playlist %s', exc)
                return
            logger.info('Removed track %s from playlist', removed_track)
        else:
            # item was reordered
            source_idx = None
            target_idx = None
            changed_uri = None
            for idx, track in enumerate(playlist.tracks):
                if sp_playlist.tracks[idx].link.uri != track.uri:
                    target_idx = idx
                    changed_uri = track.uri
                    for spidx, sptrack in enumerate(sp_playlist.tracks):
                        if sptrack.link.uri == changed_uri:
                            source_idx = spidx
                    if not source_idx:  # something is wrong
                        logger.debug('Unable to find source object '
                                     'in playlist reorder')
                        return
            try:
                sp_playlist.reorder_tracks(source_idx, target_idx)
                logger.info('Reordered track %s in playlist',
                            sp_playlist.tracks[source_idx])
            except spotify.Error as exc:
                logger.debug('Failed to reorder tracks in playlist %s', exc)


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
