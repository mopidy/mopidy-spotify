from __future__ import unicode_literals

import mock

import spotify

from mopidy_spotify import translator


def test_to_track_returns_none_if_unloaded():
    sp_track = mock.Mock(spec=spotify.Track)
    sp_track.is_loaded = False
    sp_track.availability = spotify.TrackAvailability.AVAILABLE

    track = translator.to_track(sp_track)

    assert track is None


def test_to_track_returns_none_if_not_available():
    sp_track = mock.Mock(spec=spotify.Track)
    sp_track.availability = spotify.TrackAvailability.UNAVAILABLE

    track = translator.to_track(sp_track)

    assert track is None


def test_to_track(sp_track_mock):
    track = translator.to_track(sp_track_mock)

    assert track.uri == 'spotify:track:abc'
    assert track.name == 'ABC 123'
    assert track.length == 174300
    assert track.track_no == 7
