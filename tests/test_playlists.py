from __future__ import unicode_literals

from mopidy import backend as backend_api
from mopidy.models import Ref

import pytest

from mopidy_spotify import playlists


@pytest.fixture
def web_client_mock(web_client_mock, web_track_mock):
    web_playlist1 = {
        'owner': {
            'id': 'alice',
        },
        'name': 'Foo',
        'tracks': {
            'items': [{'track': web_track_mock}]
        },
        'uri': 'spotify:user:alice:playlist:foo',
        'type': 'playlist',
    }
    web_playlist2 = {
        'owner': {
            'id': 'bob',
        },
        'name': 'Baz',
        'uri': 'spotify:user:bob:playlist:baz',
        'type': 'playlist',
    }
    web_playlist3 = {
        'owner': {
            'id': 'alice',
        },
        'name': 'Malformed',
        'tracks': {
            'items': []
        },
        'uri': 'spotify:user:alice:playlist:malformed',
    }
    web_playlists = [web_playlist1, web_playlist2, web_playlist3]
    web_playlists_map = {x['uri']: x for x in web_playlists}

    def get_playlist(*args, **kwargs):
        return web_playlists_map.get(args[0], {})

    web_client_mock.get_user_playlists.return_value = web_playlists
    web_client_mock.get_playlist.side_effect = get_playlist
    return web_client_mock


@pytest.fixture
def provider(backend_mock, web_client_mock):
    backend_mock._web_client = web_client_mock
    return playlists.SpotifyPlaylistsProvider(backend_mock)


def test_is_a_playlists_provider(provider):
    assert isinstance(provider, backend_api.PlaylistsProvider)


def test_as_list_when_not_logged_in(web_client_mock, provider):
    web_client_mock.user_id = None

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_offline(web_client_mock, provider):
    web_client_mock.get_user_playlists.return_value = {}

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_playlist_malformed(provider, caplog):
    result = provider.as_list()

    assert len(result) == 2

    assert result[0] == Ref.playlist(
        uri='spotify:user:alice:playlist:foo', name='Foo')
    assert result[1] == Ref.playlist(
        uri='spotify:user:bob:playlist:baz', name='Baz (by bob)')

    assert 'No playlist data present' in caplog.text


def test_as_list_uses_cache(provider, web_client_mock):
    provider.as_list()

    web_client_mock.get_user_playlists.assert_called_once_with(
        playlists._cache)


def test_get_items_when_playlist_exists(provider):
    result = provider.get_items('spotify:user:alice:playlist:foo')

    assert len(result) == 1

    assert result[0] == Ref.track(uri='spotify:track:abc', name='ABC 123')


def test_get_items_when_playlist_without_tracks(provider):
    result = provider.get_items('spotify:user:bob:playlist:baz')

    assert len(result) == 0

    assert result == []


def test_get_items_when_playlist_is_malformed(provider, caplog):
    assert provider.get_items('spotify:user:alice:playlist:malformed') is None
    assert 'No playlist data present' in caplog.text


def test_get_items_when_playlist_is_unknown(provider, caplog):
    assert provider.get_items('spotify:user:alice:playlist:unknown') is None
    assert (
        'Failed to lookup Spotify playlist URI '
        'spotify:user:alice:playlist:unknown' in caplog.text)


def test_as_get_items_uses_cache(provider, web_client_mock):
    provider.get_items('spotify:user:alice:playlist:foo')

    web_client_mock.get_playlist.assert_called_once_with(
        'spotify:user:alice:playlist:foo', playlists._cache)


def test_lookup(provider):
    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'
    assert playlist.tracks[0].bitrate == 160


def test_lookup_when_playlist_is_empty(provider, caplog):
    assert provider.lookup('nothing') is None
    assert 'Failed to lookup Spotify playlist URI nothing' in caplog.text


def test_lookup_of_playlist_with_other_owner(provider):
    playlist = provider.lookup('spotify:user:bob:playlist:baz')

    assert playlist.uri == 'spotify:user:bob:playlist:baz'
    assert playlist.name == 'Baz (by bob)'


def test_lookup_uses_cache(provider, web_client_mock):
    provider.lookup('spotify:user:alice:playlist:foo')

    web_client_mock.get_playlist.assert_called_once_with(
        'spotify:user:alice:playlist:foo', playlists._cache)


def test_on_playlists_loaded_triggers_playlists_loaded_event(
        caplog, backend_listener_mock):
    playlists.on_playlists_loaded()

    assert 'Spotify playlists loaded' in caplog.text
    backend_listener_mock.send.assert_called_once_with('playlists_loaded')
