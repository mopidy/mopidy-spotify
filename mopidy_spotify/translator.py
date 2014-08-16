from __future__ import unicode_literals

from mopidy import models

import spotify


def to_track(sp_track):
    if not sp_track.is_loaded:
        return  # TODO Return placeholder "[loading]" track?

    if sp_track.error != spotify.ErrorType.OK:
        return  # TODO Return placeholder "[error]" track?

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return  # TODO Return placeholder "[unavailable]" track?

    # TODO artists
    # TODO album
    # TODO date from album
    # TODO bitrate

    return models.Track(
        uri=sp_track.link.uri,
        name=sp_track.name,
        length=sp_track.duration,
        track_no=sp_track.index)


def to_playlist(sp_playlist, folders=None, username=None):
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

    tracks = [to_track(sp_track) for sp_track in sp_playlist.tracks]
    tracks = filter(None, tracks)

    return models.Playlist(
        uri=sp_playlist.link.uri,
        name=name,
        tracks=tracks)
