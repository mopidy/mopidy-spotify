from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api, models

import pytest

import spotify

from mopidy_spotify import backend, playlists


@pytest.fixture
def session_mock(sp_track_mock):
    playlist1_mock = mock.Mock(spec=spotify.Playlist)
    playlist1_mock.is_loaded = True
    playlist1_mock.link.uri = 'spotify:playlist:alice:foo'
    playlist1_mock.name = 'Foo'
    playlist1_mock.tracks = [sp_track_mock]

    playlist_folder_start_mock = mock.Mock(spec=spotify.PlaylistFolder)
    playlist_folder_start_mock.type = spotify.PlaylistType.START_FOLDER
    playlist_folder_start_mock.name = 'Bar'
    playlist_folder_start_mock.id = 17

    playlist2_mock = mock.Mock(spec=spotify.Playlist)
    playlist2_mock.is_loaded = True
    playlist2_mock.link.uri = 'spotify:playlist:alice:baz'
    playlist2_mock.name = 'Baz'
    playlist2_mock.tracks = []

    playlist_folder_end_mock = mock.Mock(spec=spotify.PlaylistFolder)
    playlist_folder_end_mock.type = spotify.PlaylistType.END_FOLDER
    playlist_folder_end_mock.id = 17

    playlist3_mock = mock.Mock(spec=spotify.Playlist)
    playlist3_mock.is_loaded = False

    session_mock = mock.Mock(spec=spotify.Session)
    session_mock.playlist_container = [
        playlist1_mock,
        playlist_folder_start_mock,
        playlist2_mock,
        playlist_folder_end_mock,
        playlist3_mock,
    ]
    return session_mock


@pytest.fixture
def backend_mock(session_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._session = session_mock
    return backend_mock


@pytest.fixture
def provider(backend_mock):
    return playlists.SpotifyPlaylistsProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_playlists_when_playlist_container_isnt_loaded(session_mock, provider):
    session_mock.playlist_container = None

    assert provider.playlists == []


def test_playlists_with_folders_and_ignored_unloaded_playlist(provider):
    assert provider.playlists == [
        models.Playlist(
            name='Foo',
            uri='spotify:playlist:alice:foo',
            tracks=[
                models.Track(
                    uri='spotify:track:abc',
                    name='ABC 123',
                    length=174300,
                    track_no=7)
            ]),
        models.Playlist(
            name='Bar/Baz',
            uri='spotify:playlist:alice:baz',
            tracks=[]),
    ]
