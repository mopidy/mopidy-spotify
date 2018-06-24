from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api
from mopidy.models import Ref

import pytest

import spotify

from mopidy_spotify import backend, playlists


@pytest.fixture
def session_mock(sp_user_mock):
    sp_session_mock = mock.Mock(spec=spotify.Session)
    sp_session_mock.user = sp_user_mock
    sp_session_mock.user_name = 'alice'
    return sp_session_mock


@pytest.fixture
def backend_mock(session_mock, web_client_mock, config):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._config = config
    backend_mock._session = session_mock
    backend_mock._web_client = web_client_mock
    return backend_mock


@pytest.fixture
def provider(backend_mock):
    return playlists.SpotifyPlaylistsProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_as_list(
        web_playlists_mock, web_client_mock, provider):

    web_client_mock.get.return_value = web_playlists_mock

    result = provider.as_list()

    assert len(result) == 2


def test_get_items_when_playlist_exists(
        web_client_mock, web_tracks_mock, provider):
    web_client_mock.get.return_value = web_tracks_mock

    result = provider.get_items('spotify:user:alice:playlist:foo')

    assert len(result) == 1

    assert result[0] == Ref.track(uri='spotify:track:abc', name='ABC 123')


def test_get_items_when_playlist_is_unknown(web_client_mock, provider):
    web_client_mock.get.return_value = {}

    result = provider.get_items('spotify:user:alice:playlist:unknown')

    assert result is None


def test_lookup(web_client_mock, web_playlist_mock, provider):
    web_client_mock.get.return_value = web_playlist_mock

    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'


def test_lookup_when_playlist_is_unknown(web_client_mock, provider):
    web_client_mock.get.return_value = {}

    assert provider.lookup('foo') is None


def test_lookup_of_playlist_with_other_owner(
        web_client_mock, web_user_mock, web_playlist_mock, provider):
    web_user_mock["id"] = 'bob'
    web_user_mock["display_name"] = 'Bob'
    web_playlist_mock["owner"] = web_user_mock
    web_client_mock.get.return_value = web_playlist_mock

    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo (by Bob)'
