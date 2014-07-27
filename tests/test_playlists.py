from __future__ import unicode_literals

from mopidy import backend

from mopidy_spotify import playlists


def test_is_a_playlists_provider():
    assert issubclass(
        playlists.SpotifyPlaylistsProvider, backend.PlaylistsProvider)
