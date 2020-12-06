import collections
import logging

from mopidy import models

import spotify

logger = logging.getLogger(__name__)


class memoized:  # noqa N801
    def __init__(self, func):
        self.func = func
        self.cache = {}

    def __call__(self, *args, **kwargs):
        # NOTE Only args, not kwargs, are part of the memoization key.
        if not isinstance(args, collections.abc.Hashable):
            return self.func(*args, **kwargs)
        if args in self.cache:
            return self.cache[args]
        else:
            value = self.func(*args, **kwargs)
            if value is not None:
                self.cache[args] = value
            return value


@memoized
def to_artist(sp_artist):
    if not sp_artist.is_loaded:
        return

    return models.Artist(uri=sp_artist.link.uri, name=sp_artist.name)


@memoized
def to_artist_ref(sp_artist):
    if not sp_artist.is_loaded:
        return

    return models.Ref.artist(uri=sp_artist.link.uri, name=sp_artist.name)


def to_artist_refs(sp_artists, timeout=None):
    for sp_artist in sp_artists:
        sp_artist.load(timeout)
        ref = to_artist_ref(sp_artist)
        if ref is not None:
            yield ref


def web_to_artist_ref(web_artist):
    if not valid_web_data(web_artist, "artist"):
        return

    uri = web_artist["uri"]
    return models.Ref.artist(uri=uri, name=web_artist.get("name", uri))


def web_to_artist_refs(web_artists):
    for web_artist in web_artists:
        ref = web_to_artist_ref(web_artist)
        if ref is not None:
            yield ref


@memoized
def to_album(sp_album):
    if not sp_album.is_loaded:
        return

    if sp_album.artist is not None and sp_album.artist.is_loaded:
        artists = [to_artist(sp_album.artist)]
    else:
        artists = []

    if sp_album.year is not None and sp_album.year != 0:
        date = f"{sp_album.year}"
    else:
        date = None

    return models.Album(
        uri=sp_album.link.uri, name=sp_album.name, artists=artists, date=date
    )


@memoized
def to_album_ref(sp_album):
    if not sp_album.is_loaded:
        return

    if sp_album.artist is None or not sp_album.artist.is_loaded:
        name = sp_album.name
    else:
        name = f"{sp_album.artist.name} - {sp_album.name}"

    return models.Ref.album(uri=sp_album.link.uri, name=name)


def to_album_refs(sp_albums, timeout=None):
    for sp_album in sp_albums:
        sp_album.load(timeout)
        ref = to_album_ref(sp_album)
        if ref is not None:
            yield ref


def web_to_album_ref(web_album):
    if not valid_web_data(web_album, "album"):
        return

    uri = web_album["uri"]
    return models.Ref.album(uri=uri, name=web_album.get("name", uri))


def web_to_album_refs(web_albums):
    for web_album in web_albums:
        # The extra level here is to also support "saved album objects".
        web_album = web_album.get("album", web_album)
        ref = web_to_album_ref(web_album)
        if ref is not None:
            yield ref


@memoized
def to_track(sp_track, bitrate=None):
    if not sp_track.is_loaded:
        return

    if sp_track.error != spotify.ErrorType.OK:
        logger.debug(f"Error loading {sp_track.link.uri!r}: {sp_track.error!r}")
        return

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return

    artists = [to_artist(sp_artist) for sp_artist in sp_track.artists]
    artists = [a for a in artists if a]

    album = to_album(sp_track.album)

    return models.Track(
        uri=sp_track.link.uri,
        name=sp_track.name,
        artists=artists,
        album=album,
        date=album.date,
        length=sp_track.duration,
        disc_no=sp_track.disc,
        track_no=sp_track.index,
        bitrate=bitrate,
    )


@memoized
def to_track_ref(sp_track):
    if not sp_track.is_loaded:
        return

    if sp_track.error != spotify.ErrorType.OK:
        logger.debug(f"Error loading {sp_track.link.uri!r}: {sp_track.error!r}")
        return

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return

    return models.Ref.track(uri=sp_track.link.uri, name=sp_track.name)


def valid_web_data(data, object_type):
    return (
        isinstance(data, dict)
        and data.get("type") == object_type
        and data.get("uri") is not None
    )


def to_track_refs(sp_tracks, timeout=None):
    for sp_track in sp_tracks:
        sp_track.load(timeout)
        ref = to_track_ref(sp_track)
        if ref is not None:
            yield ref


def web_to_track_ref(web_track, *, check_playable=True):
    if not valid_web_data(web_track, "track"):
        return

    # Web API track relinking guide says to use original URI.
    # libspotfy will handle any relinking when track is loaded for playback.
    uri = web_track.get("linked_from", {}).get("uri") or web_track["uri"]

    if check_playable and not web_track.get("is_playable", False):
        logger.debug(f"{uri!r} is not playable")
        return

    return models.Ref.track(uri=uri, name=web_track.get("name", uri))


def web_to_track_refs(web_tracks, *, check_playable=True):
    for web_track in web_tracks:
        # The extra level here is to also support "saved track objects".
        web_track = web_track.get("track", web_track)
        ref = web_to_track_ref(web_track, check_playable=check_playable)
        if ref is not None:
            yield ref


def to_playlist(
    web_playlist,
    username=None,
    bitrate=None,
    as_ref=False,
    as_items=False,
):
    ref = to_playlist_ref(web_playlist, username)
    if ref is None or as_ref:
        return ref

    web_tracks = web_playlist.get("tracks", {}).get("items", [])
    if as_items and not isinstance(web_tracks, list):
        return

    if as_items:
        return list(web_to_track_refs(web_tracks))

    tracks = [
        web_to_track(web_track.get("track", {}), bitrate=bitrate)
        for web_track in web_tracks
    ]
    tracks = [t for t in tracks if t]

    return models.Playlist(uri=ref.uri, name=ref.name, tracks=tracks)


def to_playlist_ref(web_playlist, username=None):
    if not valid_web_data(web_playlist, "playlist"):
        return

    name = web_playlist.get("name", web_playlist["uri"])

    owner = web_playlist.get("owner", {}).get("id", username)
    if username is not None and owner != username:
        name = f"{name} (by {owner})"

    return models.Ref.playlist(uri=web_playlist["uri"], name=name)


def to_playlist_refs(web_playlists, username=None):
    for web_playlist in web_playlists:
        ref = to_playlist_ref(web_playlist, username)
        if ref is not None:
            yield ref


# Maps from Mopidy search query field to Spotify search query field.
# `None` if there is no matching concept.
SEARCH_FIELD_MAP = {
    "albumartist": "artist",
    "date": "year",
    "track_name": "track",
    "track_number": None,
}


def sp_search_query(query):
    """Translate a Mopidy search query to a Spotify search query"""

    result = []

    for (field, values) in query.items():
        field = SEARCH_FIELD_MAP.get(field, field)
        if field is None:
            continue

        for value in values:
            if field == "year":
                value = _transform_year(value)
                if value is not None:
                    result.append(f"{field}:{value}")
            elif field == "any":
                result.append(f'"{value}"')
            else:
                result.append(f'{field}:"{value}"')

    return " ".join(result)


def _transform_year(date):
    try:
        return int(date.split("-")[0])
    except ValueError:
        logger.debug(
            f'Excluded year from search query: Cannot parse date "{date}"'
        )


def web_to_artist(web_artist):
    ref = web_to_artist_ref(web_artist)
    if ref is None:
        return

    return models.Artist(uri=ref.uri, name=ref.name)


def web_to_album(web_album):
    ref = web_to_album_ref(web_album)
    if ref is None:
        return

    artists = [
        web_to_artist(web_artist) for web_artist in web_album.get("artists", [])
    ]
    artists = [a for a in artists if a]

    return models.Album(uri=ref.uri, name=ref.name, artists=artists)


def web_to_track(web_track, bitrate=None):
    ref = web_to_track_ref(web_track)
    if ref is None:
        return

    artists = [
        web_to_artist(web_artist) for web_artist in web_track.get("artists", [])
    ]
    artists = [a for a in artists if a]

    album = web_to_album(web_track.get("album", {}))

    return models.Track(
        uri=ref.uri,
        name=ref.name,
        artists=artists,
        album=album,
        length=web_track.get("duration_ms"),
        disc_no=web_track.get("disc_number"),
        track_no=web_track.get("track_number"),
        bitrate=bitrate,
    )
