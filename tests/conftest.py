from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api, models

import pytest

import spotify

from mopidy_spotify import backend, library, web


@pytest.fixture
def config(tmpdir):
    return {
        'core': {
            'cache_dir': '%s' % tmpdir.join('cache'),
            'data_dir': '%s' % tmpdir.join('data'),
        },
        'proxy': {
        },
        'spotify': {
            'username': 'alice',
            'password': 'password',
            'bitrate': 160,
            'volume_normalization': True,
            'private_session': False,
            'timeout': 10,
            'allow_cache': True,
            'allow_network': True,
            'allow_playlists': True,
            'search_album_count': 20,
            'search_artist_count': 10,
            'search_track_count': 50,
            'toplist_countries': ['GB', 'US'],
            'client_id': 'abcd1234',
            'client_secret': 'YWJjZDEyMzQ='
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
def sp_unloaded_artist_mock():
    sp_artist = mock.Mock(spec=spotify.Artist)
    sp_artist.is_loaded = False
    sp_artist.name = None

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
def sp_unloaded_album_mock(sp_unloaded_artist_mock):
    sp_album = mock.Mock(spec=spotify.Album)
    sp_album.is_loaded = True
    sp_album.is_loaded = False
    sp_album.name = None
    # Optimally, we should test with both None and sp_unloaded_artist_mock
    sp_album.artist = sp_unloaded_artist_mock
    sp_album.year = None

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
def sp_unloaded_track_mock(sp_unloaded_artist_mock, sp_unloaded_album_mock):
    sp_track = mock.Mock(spec=spotify.Track)
    sp_track.is_loaded = False
    sp_track.error = spotify.ErrorType.OK
    sp_track.availability = None
    sp_track.name = None
    # Optimally, we should test with both None and [sp_unloaded_artist_mock]
    sp_track.artists = [sp_unloaded_artist_mock]
    # Optimally, we should test with both None and sp_unloaded_album_mock
    sp_track.album = sp_unloaded_album_mock
    sp_track.duration = None
    sp_track.disc = None
    sp_track.index = None

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:track:abc'
    sp_link.type = spotify.LinkType.TRACK
    sp_link.as_track.return_value = sp_track
    sp_track.link = sp_link

    return sp_track


@pytest.fixture
def sp_starred_mock(sp_user_mock, sp_artist_mock, sp_album_mock):
    sp_track1 = sp_track_mock(sp_artist_mock, sp_album_mock)
    sp_track1.link.uri = 'spotify:track:oldest'
    sp_track1.name = 'Oldest'

    sp_track2 = sp_track_mock(sp_artist_mock, sp_album_mock)
    sp_track2.link.uri = 'spotify:track:newest'
    sp_track2.name = 'Newest'

    sp_starred = mock.Mock(spec=spotify.Playlist)
    sp_starred.is_loaded = True
    sp_starred.owner = sp_user_mock
    sp_starred.name = None
    sp_starred.tracks = [sp_track1, sp_track2]

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:user:alice:starred'
    sp_link.type = spotify.LinkType.STARRED
    sp_link.as_playlist.return_value = sp_starred
    sp_starred.link = sp_link

    return sp_starred


@pytest.fixture
def sp_playlist_mock(sp_user_mock, sp_track_mock):
    sp_playlist = mock.Mock(spec=spotify.Playlist)
    sp_playlist.is_loaded = True
    sp_playlist.owner = sp_user_mock
    sp_playlist.name = 'Foo'
    sp_playlist.tracks = [sp_track_mock]

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:user:alice:playlist:foo'
    sp_link.type = spotify.LinkType.PLAYLIST
    sp_link.as_playlist.return_value = sp_playlist
    sp_playlist.link = sp_link

    return sp_playlist


@pytest.fixture
def sp_unloaded_playlist_mock(sp_unloaded_track_mock):
    sp_playlist = mock.Mock(spec=spotify.Playlist)
    sp_playlist.is_loaded = False
    sp_playlist.owner = None
    sp_playlist.name = None
    # Optimally, we should test with both None and [sp_unloaded_track_mock]
    sp_playlist.tracks = [sp_unloaded_track_mock]

    sp_link = mock.Mock(spec=spotify.Link)
    sp_link.uri = 'spotify:user:alice:playlist:foo'
    sp_link.type = spotify.LinkType.PLAYLIST
    sp_link.as_playlist.return_value = sp_playlist
    sp_playlist.link = sp_link

    return sp_playlist


@pytest.fixture
def sp_playlist_folder_start_mock():
    sp_playlist_folder_start = mock.Mock(spec=spotify.PlaylistFolder)
    sp_playlist_folder_start.type = spotify.PlaylistType.START_FOLDER
    sp_playlist_folder_start.name = 'Bar'
    sp_playlist_folder_start.id = 17
    return sp_playlist_folder_start


@pytest.fixture
def sp_playlist_folder_end_mock():
    sp_playlist_folder_end = mock.Mock(spec=spotify.PlaylistFolder)
    sp_playlist_folder_end.type = spotify.PlaylistType.END_FOLDER
    sp_playlist_folder_end.id = 17
    return sp_playlist_folder_end


@pytest.fixture
def sp_playlist_container_mock():
    sp_playlist_container = mock.Mock(spec=spotify.PlaylistContainer)
    return sp_playlist_container


@pytest.fixture
def web_search_mock(
        web_album_mock, web_artist_mock, web_track_mock):
    return {
        'albums': {
            'items': [web_album_mock]
        },
        'artists': {
            'items': [web_artist_mock]
        },
        'tracks': {
            'items': [web_track_mock, web_track_mock]
        }
    }


@pytest.fixture
def web_search_mock_large(
        web_album_mock, web_artist_mock, web_track_mock):
    return {
        'albums': {
            'items': [web_album_mock] * 10
        },
        'artists': {
            'items': [web_artist_mock] * 10
        },
        'tracks': {
            'items': [web_track_mock] * 10
        }
    }


@pytest.fixture
def web_artist_mock():
    return {
        'name': 'ABBA',
        'uri': 'spotify:artist:abba'
    }


@pytest.fixture
def web_album_mock(web_artist_mock):
    return {
        'name': 'DEF 456',
        'uri': 'spotify:album:def',
        'artists': [web_artist_mock]
    }


@pytest.fixture
def web_track_mock(web_artist_mock, web_album_mock):
    return {
        'album': web_album_mock,
        'artists': [web_artist_mock],
        'disc_number': 1,
        'duration_ms': 174300,
        'name': 'ABC 123',
        'track_number': 7,
        'uri': 'spotify:track:abc',
    }


@pytest.fixture
def web_oauth_mock():
    return {
        'access_token': 'NgCXRK...MzYjw',
        'token_type': 'Bearer',
        'scope': 'user-read-private user-read-email',
        'expires_in': 3600,
    }


@pytest.fixture
def mopidy_artist_mock():
    return models.Artist(
        name='ABBA',
        uri='spotify:artist:abba')


@pytest.fixture
def mopidy_album_mock(mopidy_artist_mock):
    return models.Album(
        artists=[mopidy_artist_mock],
        date='2001',
        name='DEF 456',
        uri='spotify:album:def')


@pytest.fixture
def session_mock():
    sp_session_mock = mock.Mock(spec=spotify.Session)
    sp_session_mock.connection.state = spotify.ConnectionState.LOGGED_IN
    sp_session_mock.playlist_container = []
    sp_session_mock.user_country = 'GB'
    return sp_session_mock


@pytest.fixture
def web_client_mock():
    web_client_mock = mock.Mock(spec=web.OAuthClient)
    return web_client_mock


@pytest.fixture
def backend_mock(session_mock, config, web_client_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._session = session_mock
    backend_mock._bitrate = 160
    backend_mock._web_client = web_client_mock
    return backend_mock


@pytest.yield_fixture
def backend_listener_mock():
    patcher = mock.patch.object(
        backend_api, 'BackendListener', spec=backend_api.BackendListener)
    yield patcher.start()
    patcher.stop()


@pytest.fixture
def provider(backend_mock):
    return library.SpotifyLibraryProvider(backend_mock)
