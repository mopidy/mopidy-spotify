from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api

import pytest

import spotify

from mopidy_spotify import backend, playlists


@pytest.fixture
def session_mock(sp_playlist_mock, sp_user_mock, sp_starred_mock):
    sp_playlist_folder_start_mock = mock.Mock(spec=spotify.PlaylistFolder)
    sp_playlist_folder_start_mock.type = spotify.PlaylistType.START_FOLDER
    sp_playlist_folder_start_mock.name = 'Bar'
    sp_playlist_folder_start_mock.id = 17

    sp_playlist2_mock = mock.Mock(spec=spotify.Playlist)
    sp_playlist2_mock.is_loaded = True
    sp_playlist2_mock.owner = mock.Mock(spec=spotify.User)
    sp_playlist2_mock.owner.canonical_name = 'bob'
    sp_playlist2_mock.offline_status = spotify.PlaylistOfflineStatus.NO
    sp_playlist2_mock.link.uri = 'spotify:playlist:bob:baz'
    sp_playlist2_mock.name = 'Baz'
    sp_playlist2_mock.tracks = []

    sp_playlist_folder_end_mock = mock.Mock(spec=spotify.PlaylistFolder)
    sp_playlist_folder_end_mock.type = spotify.PlaylistType.END_FOLDER
    sp_playlist_folder_end_mock.id = 17

    sp_playlist3_mock = mock.Mock(spec=spotify.Playlist)
    sp_playlist3_mock.is_loaded = False

    sp_session_mock = mock.Mock(spec=spotify.Session)
    sp_session_mock.user = sp_user_mock
    sp_session_mock.user_name = 'alice'
    sp_session_mock.get_starred.return_value = sp_starred_mock
    sp_session_mock.playlist_container = [
        sp_playlist_mock,
        sp_playlist_folder_start_mock,
        sp_playlist2_mock,
        sp_playlist_folder_end_mock,
        sp_playlist3_mock,
    ]
    return sp_session_mock


@pytest.fixture
def backend_mock(session_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._session = session_mock
    backend_mock._bitrate = 160
    return backend_mock


@pytest.fixture
def provider(backend_mock):
    return playlists.SpotifyPlaylistsProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_create(session_mock, sp_playlist_mock, provider):
    session_mock.playlist_container = mock.Mock(
        spec=spotify.PlaylistContainer)
    session_mock.playlist_container.add_new_playlist.return_value = (
        sp_playlist_mock)

    playlist = provider.create('Foo')

    session_mock.playlist_container.add_new_playlist.assert_called_once_with(
        'Foo')
    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'


def test_create_with_invalid_name(session_mock, provider, caplog):
    session_mock.playlist_container = mock.Mock(
        spec=spotify.PlaylistContainer)
    session_mock.playlist_container.add_new_playlist.side_effect = ValueError(
        'Too long name')

    playlist = provider.create('Foo')

    assert playlist is None
    assert (
        'Failed creating new Spotify playlist "Foo": Too long name'
        in caplog.text())


def test_create_fails_in_libspotify(session_mock, provider, caplog):
    session_mock.playlist_container = mock.Mock(
        spec=spotify.PlaylistContainer)
    session_mock.playlist_container.add_new_playlist.side_effect = (
        spotify.Error)

    playlist = provider.create('Foo')

    assert playlist is None
    assert 'Failed creating new Spotify playlist "Foo"' in caplog.text()


def test_lookup(session_mock, sp_playlist_mock, provider):
    session_mock.get_playlist.return_value = sp_playlist_mock

    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'
    assert playlist.tracks[0].bitrate == 160


def test_lookup_loads_playlist_when_a_playlist_isnt_loaded(
        sp_playlist_mock, session_mock, provider):
    is_loaded_mock = mock.PropertyMock()
    type(sp_playlist_mock).is_loaded = is_loaded_mock
    is_loaded_mock.side_effect = [False, True]
    session_mock.get_playlist.return_value = sp_playlist_mock

    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    sp_playlist_mock.load.assert_called_once_with()
    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'


def test_lookup_when_playlist_is_unknown(session_mock, provider):
    session_mock.get_playlist.side_effect = spotify.Error

    assert provider.lookup('foo') is None


def test_lookup_of_playlist_with_other_owner(
        session_mock, sp_user_mock, sp_playlist_mock, provider):
    sp_user_mock.canonical_name = 'bob'
    sp_playlist_mock.owner = sp_user_mock
    session_mock.get_playlist.return_value = sp_playlist_mock

    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo (by bob)'


def test_playlists_when_not_logged_in(session_mock, provider, config):
    session_mock.get_starred.return_value = None
    session_mock.playlist_container = None
    session_mock.offline.time_left = 3600
    provider._backend._config = config

    assert len(provider.playlists) == 0


def test_playlists_when_playlist_container_isnt_loaded(
        session_mock, provider, config):
    session_mock.playlist_container = None
    session_mock.offline.time_left = 3600
    provider._backend._config = config
    assert len(provider.playlists) == 1

    assert provider.playlists[0].name == 'Starred'
    assert provider.playlists[0].uri == 'spotify:user:alice:starred'
    assert len(provider.playlists[0].tracks) == 2


def test_playlists_with_folders_and_ignored_unloaded_playlist(
        session_mock, provider, config):
    session_mock.offline.time_left = 3600
    provider._backend._config = config
    assert len(provider.playlists) == 3

    assert provider.playlists[0].name == 'Starred'
    assert provider.playlists[0].uri == 'spotify:user:alice:starred'
    assert len(provider.playlists[0].tracks) == 2

    assert provider.playlists[1].name == 'Foo'
    assert provider.playlists[1].uri == 'spotify:user:alice:playlist:foo'
    assert len(provider.playlists[1].tracks) == 1

    assert provider.playlists[2].name == 'Bar/Baz (by bob)'
    assert provider.playlists[2].uri == 'spotify:playlist:bob:baz'
    assert len(provider.playlists[2].tracks) == 0
