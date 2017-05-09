from __future__ import unicode_literals

import collections
import logging

from mopidy import models

import spotify


logger = logging.getLogger(__name__)


class memoized(object):
    def __init__(self, func):
        self.func = func
        self.cache = {}

    def __call__(self, *args, **kwargs):
        # NOTE Only args, not kwargs, are part of the memoization key.
        if not isinstance(args, collections.Hashable):
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


@memoized
def to_album(sp_album):
    if not sp_album.is_loaded:
        return

    if sp_album.artist is not None and sp_album.artist.is_loaded:
        artists = [to_artist(sp_album.artist)]
    else:
        artists = []

    if sp_album.year is not None and sp_album.year != 0:
        date = '%d' % sp_album.year
    else:
        date = None

    return models.Album(
        uri=sp_album.link.uri,
        name=sp_album.name,
        artists=artists,
        date=date)


@memoized
def to_album_ref(sp_album):
    if not sp_album.is_loaded:
        return

    if sp_album.artist is None or not sp_album.artist.is_loaded:
        name = sp_album.name
    else:
        name = '%s - %s' % (sp_album.artist.name, sp_album.name)

    return models.Ref.album(uri=sp_album.link.uri, name=name)


def to_album_refs(sp_albums, timeout=None):
    for sp_album in sp_albums:
        sp_album.load(timeout)
        ref = to_album_ref(sp_album)
        if ref is not None:
            yield ref


@memoized
def to_track(sp_track, bitrate=None):
    if not sp_track.is_loaded:
        return

    if sp_track.error != spotify.ErrorType.OK:
        logger.debug(
            'Error loading %s: %r', sp_track.link.uri, sp_track.error)
        return

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return

    artists = [to_artist(sp_artist) for sp_artist in sp_track.artists]
    artists = filter(None, artists)

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
        bitrate=bitrate)


@memoized
def to_track_ref(sp_track):
    if not sp_track.is_loaded:
        return

    if sp_track.error != spotify.ErrorType.OK:
        logger.debug(
            'Error loading %s: %r', sp_track.link.uri, sp_track.error)
        return

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return

    return models.Ref.track(uri=sp_track.link.uri, name=sp_track.name)


def to_track_refs(sp_tracks, timeout=None):
    for sp_track in sp_tracks:
        sp_track.load(timeout)
        ref = to_track_ref(sp_track)
        if ref is not None:
            yield ref


def to_playlist(
        sp_playlist, folders=None, username=None, bitrate=None,
        as_ref=False, as_items=False):
    if not isinstance(sp_playlist, spotify.Playlist):
        return

    if not sp_playlist.is_loaded:
        return

    if as_items:
        return list(to_track_refs(sp_playlist.tracks))

    name = sp_playlist.name

    if not as_ref:
        tracks = [
            to_track(sp_track, bitrate=bitrate)
            for sp_track in sp_playlist.tracks]
        tracks = filter(None, tracks)
        if name is None:
            # Use same starred order as the Spotify client
            tracks = list(reversed(tracks))

    if name is None:
        name = 'Starred'
    if folders is not None:
        name = '/'.join(folders + [name])
    if username is not None and sp_playlist.owner.canonical_name != username:
        name = '%s (by %s)' % (name, sp_playlist.owner.canonical_name)

    if as_ref:
        return models.Ref.playlist(uri=sp_playlist.link.uri, name=name)
    else:
        return models.Playlist(
            uri=sp_playlist.link.uri, name=name, tracks=tracks)


def to_playlist_ref(sp_playlist, folders=None, username=None):
    return to_playlist(
        sp_playlist, folders=folders, username=username, as_ref=True)


# Maps from Mopidy search query field to Spotify search query field.
# `None` if there is no matching concept.
SEARCH_FIELD_MAP = {
    'albumartist': 'artist',
    'date': 'year',
    'track_name': 'track',
    'track_number': None,
}


def sp_search_query(query):
    """Translate a Mopidy search query to a Spotify search query"""

    result = []

    for (field, values) in query.items():
        field = SEARCH_FIELD_MAP.get(field, field)
        if field is None:
            continue

        for value in values:
            if field == 'year':
                value = _transform_year(value)
                if value is not None:
                    result.append('%s:%d' % (field, value))
            elif field == 'any':
                result.append('"%s"' % value)
            else:
                result.append('%s:"%s"' % (field, value))

    return ' '.join(result)


def _transform_year(date):
    try:
        return int(date.split('-')[0])
    except ValueError:
        logger.debug(
            'Excluded year from search query: '
            'Cannot parse date "%s"', date)


def web_to_artist(web_artist):
    return models.Artist(uri=web_artist['uri'], name=web_artist['name'])


def web_to_album(web_album):
    artists = [
        web_to_artist(web_artist) for web_artist in web_album['artists']]

    return models.Album(
        uri=web_album['uri'],
        name=web_album['name'],
        artists=artists)


def web_to_track(web_track):
    artists = [
        web_to_artist(web_artist) for web_artist in web_track['artists']]
    album = web_to_album(web_track['album'])

    return models.Track(
        uri=web_track['uri'],
        name=web_track['name'],
        artists=artists,
        album=album,
        length=web_track['duration_ms'],
        disc_no=web_track['disc_number'],
        track_no=web_track['track_number'])
