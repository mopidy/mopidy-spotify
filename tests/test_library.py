from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api

import pytest

import spotify

from mopidy_spotify import backend, library


@pytest.fixture
def session_mock(sp_playlist_mock, sp_user_mock):
    sp_session_mock = mock.Mock(spec=spotify.Session)
    return sp_session_mock


@pytest.fixture
def backend_mock(session_mock):
    backend_mock = mock.Mock(spec=backend.SpotifyBackend)
    backend_mock._session = session_mock
    backend_mock.bitrate = 160
    return backend_mock


@pytest.fixture
def provider(backend_mock):
    return library.SpotifyLibraryProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.LibraryProvider)
