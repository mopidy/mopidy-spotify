from __future__ import unicode_literals

from mopidy import models

import spotify


def to_track(sp_track):
    if not sp_track.is_loaded:
        return

    if sp_track.availability != spotify.TrackAvailability.AVAILABLE:
        return

    # TODO artists
    # TODO album
    # TODO date from album
    # TODO bitrate

    return models.Track(
        uri=sp_track.link.uri,
        name=sp_track.name,
        length=sp_track.duration,
        track_no=sp_track.index)
