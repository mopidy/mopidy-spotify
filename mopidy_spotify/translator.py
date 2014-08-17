from __future__ import unicode_literals

import collections

from mopidy import models

import spotify


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
            self.cache[args] = value
            return value


@memoized
def to_artist(sp_artist):
    if not sp_artist.is_loaded:
        return  # TODO Return placeholder "[loading]" artist?

    return models.Artist(uri=sp_artist.link.uri, name=sp_artist.name)


@memoized
def to_album(sp_album):
    if not sp_album.is_loaded:
        return  # TODO Return placeholder "[loading]" album?

    if sp_album.artist is not None:
        artists = [to_artist(sp_album.artist)]
    else:
        artists = []

    if sp_album.year is not None:
        date = '%d' % sp_album.year
    else:
        date = None

    return models.Album(
        uri=sp_album.link.uri,
        name=sp_album.name,
        artists=artists,
        date=date)


@memoized
def to_track(sp_track, bitrate=None):
    if not sp_track.is_loaded:
        return  # TODO Return placeholder "[loading]" track?

    if sp_track.error != spotify.ErrorType.OK:
        return  # TODO Return placeholder "[error]" track?

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return  # TODO Return placeholder "[unavailable]" track?

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


def to_playlist(sp_playlist, folders=None, username=None, bitrate=None):
    if not isinstance(sp_playlist, spotify.Playlist):
        return

    if not sp_playlist.is_loaded:
        return  # TODO Return placeholder "[loading]" playlist?

    name = sp_playlist.name
    if name is None:
        name = 'Starred'
        # TODO Reverse order of tracks in starred playlists?
    if folders is not None:
        name = '/'.join(folders + [name])
    if username is not None and sp_playlist.owner.canonical_name != username:
        name = '%s by %s' % (name, sp_playlist.owner.canonical_name)

    tracks = [
        to_track(sp_track, bitrate=bitrate)
        for sp_track in sp_playlist.tracks]
    tracks = filter(None, tracks)

    return models.Playlist(
        uri=sp_playlist.link.uri,
        name=name,
        tracks=tracks)
