from __future__ import unicode_literals

import mock

import pytest

import spotify

from mopidy_spotify import backend


@pytest.fixture
def config():
    return {
        'spotify': {
            'username': 'alice',
            'password': 'password',
            'bitrate': 160,
            'volume_normalization': True,
            'private_session': False,
            'timeout': 10,
            'cache_dir': '/my/cache/dir',
            'settings_dir': '/my/settings/dir',
            'allow_network': True,
            'allow_playlists': True,
            'search_album_count': 20,
            'search_artist_count': 10,
            'search_track_count': 50,
            'offline_playlist': 'Playlist1, Playlist2, Regex.*',
        }
    }


@pytest.yield_fixture
def spotify_mock():
    patcher = mock.patch.object(backend, 'spotify', spec=spotify)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def sp_user_mock():
    sp_user = mock.Mock(spec=spotify.User)
    sp_user.is_loaded = True
    sp_user.canonical_name = 'alice'
    return sp_user


@pytest.fixture
def sp_artist_mock():
    sp_artist = mock.Mock(spec=spotify.Artist)
    sp_artist.is_loaded = True
    sp_artist.name = 'ABBA'

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:artist:abba'
    sp_link.type = spotify.LinkType.ARTIST
    sp_link.as_artist.return_value = sp_artist
    sp_artist.link = sp_link

    return sp_artist


@pytest.fixture
def sp_artist_browser_mock(sp_artist_mock, sp_album_mock):
    sp_artist_browser = mock.Mock(spec=spotify.ArtistBrowser)
    sp_artist_browser.artist = sp_artist_mock
    sp_artist_browser.albums = [sp_album_mock, sp_album_mock]

    sp_artist_mock.browse.return_value = sp_artist_browser

    return sp_artist_browser


@pytest.fixture
def sp_album_mock(sp_artist_mock):
    sp_album = mock.Mock(spec=spotify.Album)
    sp_album.is_loaded = True
    sp_album.name = 'DEF 456'
    sp_album.artist = sp_artist_mock
    sp_album.year = 2001

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:album:def'
    sp_link.type = spotify.LinkType.ALBUM
    sp_link.as_album.return_value = sp_album
    sp_album.link = sp_link

    return sp_album


@pytest.fixture
def sp_album_browser_mock(sp_album_mock, sp_track_mock):
    sp_album_browser = mock.Mock(spec=spotify.AlbumBrowser)
    sp_album_browser.album = sp_album_mock
    sp_album_browser.tracks = [sp_track_mock, sp_track_mock]
    sp_album_browser.load.return_value = sp_album_browser

    sp_album_mock.browse.return_value = sp_album_browser

    return sp_album_browser


@pytest.fixture
def sp_track_mock(sp_artist_mock, sp_album_mock):
    sp_track = mock.Mock(spec=spotify.Track)
    sp_track.is_loaded = True
    sp_track.error = spotify.ErrorType.OK
    sp_track.availability = spotify.TrackAvailability.AVAILABLE
    sp_track.name = 'ABC 123'
    sp_track.artists = [sp_artist_mock]
    sp_track.album = sp_album_mock
    sp_track.duration = 174300
    sp_track.disc = 1
    sp_track.index = 7

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:track:abc'
    sp_link.type = spotify.LinkType.TRACK
    sp_link.as_track.return_value = sp_track
    sp_track.link = sp_link

    return sp_track


@pytest.fixture
def sp_playlist_mock(sp_user_mock, sp_track_mock):
    sp_playlist = mock.Mock(spec=spotify.Playlist)
    sp_playlist.is_loaded = True
    sp_playlist.owner = sp_user_mock
    sp_playlist.name = 'Foo'
    sp_playlist.tracks = [sp_track_mock]

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:playlist:alice:foo'
    sp_link.type = spotify.LinkType.PLAYLIST
    sp_link.as_playlist.return_value = sp_playlist
    sp_playlist.link = sp_link

    return sp_playlist


@pytest.fixture
def sp_search_mock(sp_album_mock, sp_artist_mock, sp_track_mock):
    sp_search = mock.Mock(spec=spotify.Search)
    sp_search.is_loaded = True
    sp_search.albums = [sp_album_mock]
    sp_search.artists = [sp_artist_mock]
    sp_search.tracks = [sp_track_mock, sp_track_mock]
    return sp_search
