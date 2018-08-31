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

    def _get_key(self, args, kwargs):
        # NOTE Only args, not kwargs, are part of the memoization key.
        return args

    def __call__(self, *args, **kwargs):
        key = self._get_key(args, kwargs)
        if key is None or not isinstance(key, collections.Hashable):
            return self.func(*args, **kwargs)
        if key in self.cache:
            return self.cache[key]
        else:
            value = self.func(*args, **kwargs)
            if value is not None:
                self.cache[key] = value
            return value


class web_memoized(memoized):
    def _get_key(self, args, kwargs):
        if len(args) > 0 and args[0] is not None:
            data = args[0]
            return '%s.%s' % (data.get('uri'), data.get('name'))


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


@web_memoized
def web_to_track_ref(web_track):
    if web_track is None:
        return

    if web_track.get('type') != 'track':
        return

    if not web_track.get('is_playable'):
        return
    
    # Web API track relinking guide says to use original URI.
    # libspotfy will handle any relinking when track is loaded for playback.
    uri = web_track.get('linked_from', {}).get('uri') or web_track.get('uri')

    return models.Ref.track(
        uri=uri, name=web_track.get('name'))


def web_to_track_refs(web_tracks):
    for web_track in web_tracks:
        ref = web_to_track_ref(web_track.get('track'))
        if ref is not None:
            yield ref


def to_playlist(
        web_playlist, username=None, bitrate=None,
        as_ref=False, as_items=False):
    if web_playlist.get('type') != 'playlist':
        return

    web_tracks = web_playlist.get('tracks', {}).get('items')
    if (as_items or not as_ref) and not isinstance(web_tracks, list):
        logger.error('No playlist track data present') 
        return        

    if as_items:
        return list(web_to_track_refs(web_tracks))

    name = web_playlist.get('name')

    if not as_ref:
        tracks = [
            web_to_track(web_track.get('track', {}), bitrate=bitrate)
            for web_track in web_tracks]
        tracks = filter(None, tracks)
        if name is None:
            # FIX: Starred not supported by Web API
            # Use same starred order as the Spotify client
            tracks = list(reversed(tracks))

    if name is None:
        # FIX: Starred not supported by Web API
        name = 'Starred' 
    owner = web_playlist.get('owner', {}).get('id', username)
    if username is not None and owner != username:
        name = '%s (by %s)' % (name, owner)

    if as_ref:
        return models.Ref.playlist(uri=web_playlist.get('uri'), name=name)
    else:
        return models.Playlist(
            uri=web_playlist.get('uri'), name=name, tracks=tracks)


@web_memoized
def to_playlist_ref(web_playlist, username=None):
    return to_playlist(web_playlist, username=username, as_ref=True)


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


@web_memoized
def web_to_artist(web_artist):
    return models.Artist(uri=web_artist['uri'], name=web_artist['name'])


@web_memoized
def web_to_album(web_album):
    artists = [
        web_to_artist(web_artist) for web_artist in web_album['artists']]

    return models.Album(
        uri=web_album['uri'],
        name=web_album['name'],
        artists=artists)


@web_memoized
def web_to_track(web_track, bitrate=None):
    ref = web_to_track_ref(web_track)
    if ref is None:
        return

    artists = [
        web_to_artist(web_artist) for web_artist in web_track.get('artists', [])]
    artists = filter(None, artists)

    album = web_to_album(web_track.get('album', {}))
    
    artists = [
        web_to_artist(web_artist) for web_artist in web_track['artists']]
    album = web_to_album(web_track['album'])

    return models.Track(
        uri=ref.uri,
        name=web_track.get('name'),
        artists=artists,
        album=album,
        length=web_track.get('duration_ms'),
        disc_no=web_track.get('disc_number'),
        track_no=web_track.get('track_number'),
        bitrate=bitrate)

