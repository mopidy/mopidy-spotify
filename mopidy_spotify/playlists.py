import logging
import math
import time

from mopidy import backend

import spotify
from mopidy_spotify import translator, utils, web, Extension

_sp_links = {}

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    # Maximum number of items accepted by the Spotify Web API
    _chunk_size = 100

    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]
        self._loaded = False

    def as_list(self):
        with utils.time_logger("playlists.as_list()", logging.DEBUG):
            if not self._loaded:
                return []

            return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self):
        if not self._backend._web_client.logged_in:
            return []

        user_playlists = self._backend._web_client.get_user_playlists()
        return translator.to_playlist_refs(
            user_playlists, self._backend._web_client.user_id
        )

    def get_items(self, uri):
        with utils.time_logger(f"playlist.get_items({uri!r})", logging.DEBUG):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger(f"playlists.lookup({uri!r})", logging.DEBUG):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False, with_owner=False):
        return playlist_lookup(
            self._backend._session,
            self._backend._web_client,
            uri,
            self._backend._bitrate,
            as_items,
            with_owner,
        )

    @staticmethod
    def _split_ended_movs(value, movs):
        def _span(p, xs):
            # Returns a tuple where first element is the longest prefix
            # (possibly empty) of list xs of elements that satisfy predicate p
            # and second element is the remainder of the list.
            i = next((i for i, v in enumerate(xs) if not p(v)), len(xs))
            return xs[:i], xs[i:]

        return _span(lambda e: e[0] < value, movs)

    def _patch_playlist(self, playlist, operations):
        # Note: We need two distinct delta_f/t to be able to keep track of move
        # operations.  This is because when moving multiple (distinct) sections
        # so their old and new positions overlap, one bound can be inside the
        # range and the other outide. Then, only the inside bound must add
        # delta_f/t, while the outside one must not.
        delta_f = 0
        delta_t = 0
        unwind_f = []
        unwind_t = []
        for op in operations:
            # from the list of "active" mov-deltas, split off the ones newly
            # outside the range and neutralize them:
            ended_ranges_f, unwind_f = self._split_ended_movs(op.frm, unwind_f)
            ended_ranges_t, unwind_t = self._split_ended_movs(op.to, unwind_t)
            delta_f -= sum((amount for _, amount in ended_ranges_f))
            delta_t -= sum((amount for _, amount in ended_ranges_t))

            length = len(op.tracks)
            if op.op == "-":
                web.remove_tracks_from_playlist(
                    self._backend._web_client,
                    playlist,
                    op.tracks,
                    op.frm + delta_f,
                )
                delta_f -= length
                delta_t -= length
            elif op.op == "+":
                web.add_tracks_to_playlist(
                    self._backend._web_client,
                    playlist,
                    op.tracks,
                    op.frm + delta_f,
                )
                delta_f += length
                delta_t += length
            elif op.op == "m":
                web.move_tracks_in_playlist(
                    self._backend._web_client,
                    playlist,
                    range_start=op.frm + delta_f,
                    insert_before=op.to + delta_t,
                    range_length=length,
                )
                # if we move right, the delta is active in the range (op.frm, op.to),
                # when we move left, it's in the range (op.to, op.frm+length)
                position = op.to if op.frm < op.to else op.frm + length
                amount = length * (-1 if op.frm < op.to else 1)
                # While add/del deltas will be active for the rest of the
                # playlist, mov deltas only affect the range of tracks between
                # their old end new positions. We must undo them once we get
                # outside this range, so we store the position at which point
                # to subtract the amount again.
                unwind_f.append((position, amount))
                unwind_t.append((position, amount))
                delta_f += amount
                delta_t += amount

    def _replace_playlist(self, playlist, tracks):
        web.replace_playlist(
            self._backend._web_client, playlist, tracks, self._chunk_size
        )

    def refresh(self):
        if not self._backend._web_client.logged_in:
            return

        with utils.time_logger("playlists.refresh()", logging.DEBUG):
            _sp_links.clear()
            self._backend._web_client.clear_cache()
            count = 0
            for playlist_ref in self._get_flattened_playlist_refs():
                self._get_playlist(playlist_ref.uri)
                count = count + 1
            logger.info(f"Refreshed {count} Spotify playlists")

        self._loaded = True

    def create(self, name):
        if not name:
            return None
        web_playlist = web.create_playlist(self._backend._web_client, name)
        if web_playlist is None:
            logger.error(f"Failed to create Spotify playlist '{name}'")
            return
        logger.info(f"Created Spotify playlist '{name}'")
        return translator.to_playlist(
            web_playlist,
            username=self._backend._web_client.user_id,
            bitrate=self._backend._bitrate,
            # Note: we are not filtering out (currently) unplayable tracks;
            # otherwise they would be removed when editing the playlist.
            check_playable=False,
        )

    def delete(self, uri):
        logger.info(f"Deleting Spotify playlist {uri!r}")
        ok = web.delete_playlist(self._backend._web_client, uri)
        return ok

    @staticmethod
    def _len_replace(playlist_tracks, n=_chunk_size):
        return math.ceil(len(playlist_tracks) / n)

    @staticmethod
    def _is_spotify_track(track_uri):
        try:
            return web.WebLink.from_uri(track_uri).type == web.LinkType.TRACK
        except ValueError:
            return False  # not a valid spotify URI

    @staticmethod
    def _is_spotify_local(track_uri):
        return track_uri.startswith("spotify:local:")

    def save(self, playlist):
        saved_playlist = self._get_playlist(playlist.uri, with_owner=True)
        if not saved_playlist:
            return

        saved_playlist, owner = saved_playlist
        # We limit playlist editing to the user's own playlists, since mopidy
        # mangles the names of other people's playlists.
        if owner and owner != self._backend._web_client.user_id:
            logger.error(
                f"Cannot modify Spotify playlist {playlist.uri!r} owned by "
                f"other user {owner}"
            )
            return

        # We cannot add or (easily) remove spotify:local: tracks, so refuse
        # editing if the current playlist contains such tracks.
        if any((self._is_spotify_local(t.uri) for t in saved_playlist.tracks)):
            logger.error(
                "Cannot modify Spotify playlist containing Spotify 'local files'."
            )
            for t in saved_playlist.tracks:
                if t.uri.startswith("spotify:local:"):
                    logger.debug(
                        f"Unsupported Spotify local file: '{t.name}' ({t.uri!r})"
                    )
            return

        new_tracks = [track.uri for track in playlist.tracks]
        cur_tracks = [track.uri for track in saved_playlist.tracks]

        if any((not self._is_spotify_track(t) for t in new_tracks)):
            new_tracks = list(filter(self._is_spotify_track, new_tracks))
            logger.warning(
                f"Skipping adding non-Spotify tracks to Spotify playlist "
                f"{playlist.uri!r}"
            )

        operations = utils.diff(cur_tracks, new_tracks, self._chunk_size)

        # calculate number of operations required for each strategy:
        ops_patch = len(operations)
        ops_replace = self._len_replace(new_tracks)

        try:
            if ops_replace < ops_patch:
                self._replace_playlist(saved_playlist, new_tracks)
            else:
                self._patch_playlist(saved_playlist, operations)
        except web.OAuthClientError as e:
            logger.error(f"Failed to save Spotify playlist: {e}")
            # In the unlikely event that we used the replace strategy, and the
            # first PUT went through but the following POSTs didn't, we have
            # truncated the playlist. At this point, we still have the playlist
            # data available, so we write it to an m3u file as a last resort
            # effort for the user to recover from.
            if ops_replace < ops_patch:
                safe_name = playlist.name.translate(
                    str.maketrans(" @`!\"#$%&'()*+;[{<\\|]}>^~/?", "_" * 27)
                )
                filename = (
                    Extension.get_data_dir(self._backend._config)
                    / f"{safe_name}-{playlist.uri}-{time.time()}.m3u"
                )
                with open(filename, "wb") as f:
                    f.write(b"#EXTM3U\n#EXTENC: UTF-8\n\n")
                    for track in playlist.tracks:
                        length = int(track.length / 1000)
                        artists = ", ".join(a.name for a in track.artists)
                        f.write(
                            f"#EXTINF:{length},{artists} - {track.name}\n"
                            f"{track.uri}\n\n".encode("utf-8")
                        )
                logger.error(f'Created backup in "{filename}"')
            return None

        if playlist.name and playlist.name != saved_playlist.name:
            try:
                web.rename_playlist(
                    self._backend._web_client, playlist.uri, playlist.name
                )
                logger.info(
                    f"Renamed Spotify playlist '{saved_playlist.name}' to "
                    f"'{playlist.name}'"
                )
            except web.OAuthClientError as e:
                logger.error(
                    f"Renaming Spotify playlist '{saved_playlist.name}'"
                    f"to '{playlist.name}' failed with error {e}"
                )

        return self.lookup(saved_playlist.uri)


def playlist_lookup(
    session, web_client, uri, bitrate, as_items=False, with_owner=False
):
    if web_client is None or not web_client.logged_in:
        return

    logger.debug(f'Fetching Spotify playlist "{uri!r}"')
    web_playlist = web_client.get_playlist(uri)

    if web_playlist == {}:
        logger.error(f"Failed to lookup Spotify playlist URI {uri!r}")
        return

    playlist = translator.to_playlist(
        web_playlist,
        username=web_client.user_id,
        bitrate=bitrate,
        as_items=as_items,
        # Note: we are not filtering out (currently) unplayable tracks;
        # otherwise they would be removed when editing the playlist.
        check_playable=False,
    )
    if playlist is None:
        return
    # Store the libspotify Link for each track so they will be loaded in the
    # background ready for using later.
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
                logger.info(f"Failed to get link {track.uri!r}: {exc}")

    if with_owner:
        owner = web_playlist.get("owner", {}).get("id")
        return playlist, owner
    return playlist
