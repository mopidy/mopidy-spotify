from __future__ import unicode_literals

import mock

from mopidy import backend as backend_api
from mopidy.models import Ref

import pytest

import spotify

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
        'type': 'bogus',
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
    playlists._cache.clear()
    playlists._sp_links.clear()
    provider = playlists.SpotifyPlaylistsProvider(backend_mock)
    provider._loaded = True
    return provider


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


def test_as_list_blocked_when_not_loaded(provider):
    provider._loaded = False

    result = provider.as_list()

    assert len(result) == 0


def test_as_list_when_playlist_wont_translate(provider, caplog):
    result = provider.as_list()

    assert len(result) == 2

    assert result[0] == Ref.playlist(
        uri='spotify:user:alice:playlist:foo', name='Foo')
    assert result[1] == Ref.playlist(
        uri='spotify:user:bob:playlist:baz', name='Baz (by bob)')


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


def test_get_items_blocked_when_not_loaded(provider):
    provider._loaded = False

    result = provider.get_items('spotify:user:alice:playlist:foo')

    assert len(result) == 0

    assert result == []


def test_get_items_when_playlist_wont_translate(provider, caplog):
    assert provider.get_items('spotify:user:alice:playlist:malformed') is None


def test_get_items_when_playlist_is_unknown(provider, caplog):
    assert provider.get_items('spotify:user:alice:playlist:unknown') is None
    assert (
        'Failed to lookup Spotify playlist URI '
        'spotify:user:alice:playlist:unknown' in caplog.text)


def test_refresh_loads_all_playlists(provider, web_client_mock):
    provider.refresh()

    web_client_mock.get_user_playlists.assert_called_once()
    assert web_client_mock.get_playlist.call_count == 2
    expected_calls = [
        mock.call('spotify:user:alice:playlist:foo', {}),
        mock.call('spotify:user:bob:playlist:baz', {}),
    ]
    web_client_mock.get_playlist.assert_has_calls(expected_calls)


def test_refresh_when_not_loaded(provider, web_client_mock):
    provider._loaded = False

    provider.refresh()

    web_client_mock.get_user_playlists.assert_called_once()
    web_client_mock.get_playlist.assert_called()
    assert provider._loaded


def test_refresh_counts_playlists(provider, caplog):
    provider.refresh()

    assert 'Refreshed 2 playlists' in caplog.text


def test_refresh_clears_web_cache(provider):
    playlists._cache = {'foo': 'foobar', 'foo2': 'foofoo'}

    provider.refresh()

    assert len(playlists._cache) == 0


def test_refresh_clears_link_cache(provider):
    playlists._sp_links = {'bar': 'foobar', 'bar2': 'foofoo'}

    provider.refresh()

    assert len(playlists._sp_links) == 1
    assert playlists._sp_links.keys() == ['spotify:track:abc']


def test_lookup(provider):
    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'
    assert playlist.tracks[0].bitrate == 160


def test_lookup_when_not_loaded(provider):
    provider._loaded = False

    playlist = provider.lookup('spotify:user:alice:playlist:foo')

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'


def test_lookup_when_playlist_is_empty(provider, caplog):
    assert provider.lookup('nothing') is None
    assert 'Failed to lookup Spotify playlist URI nothing' in caplog.text


def test_lookup_of_playlist_with_other_owner(provider):
    playlist = provider.lookup('spotify:user:bob:playlist:baz')

    assert playlist.uri == 'spotify:user:bob:playlist:baz'
    assert playlist.name == 'Baz (by bob)'


@pytest.mark.parametrize('as_items', [
    (False),
    (True),
])
def test_playlist_lookup_stores_track_link(
        session_mock, web_client_mock, sp_track_mock, web_playlist_mock,
        web_track_mock, as_items):
    session_mock.get_link.return_value = sp_track_mock.link
    web_playlist_mock['tracks']['items'] = [{'track': web_track_mock}] * 5
    web_client_mock.get_playlist.return_value = web_playlist_mock
    playlists._sp_links.clear()

    playlists.playlist_lookup(
        session_mock, web_client_mock, 'spotify:user:alice:playlist:foo', None,
        as_items)

    session_mock.get_link.assert_called_once_with(
        'spotify:track:abc')
    assert len(playlists._sp_links) == 1


@pytest.mark.parametrize('connection_state', [
    (spotify.ConnectionState.OFFLINE),
    (spotify.ConnectionState.DISCONNECTED),
    (spotify.ConnectionState.LOGGED_OUT),
])
def test_playlist_lookup_when_not_logged_in(
        session_mock, web_client_mock, web_playlist_mock, connection_state):
    web_client_mock.get_playlist.return_value = web_playlist_mock
    session_mock.connection.state = connection_state
    playlists._sp_links.clear()

    playlist = playlists.playlist_lookup(
        session_mock, web_client_mock, 'spotify:user:alice:playlist:foo', None)

    assert playlist.uri == 'spotify:user:alice:playlist:foo'
    assert playlist.name == 'Foo'
    assert len(playlists._sp_links) == 0


def test_playlist_lookup_when_playlist_is_empty(
        session_mock, web_client_mock, caplog):
    web_client_mock.get_playlist.return_value = {}
    playlists._sp_links.clear()

    playlist = playlists.playlist_lookup(
        session_mock, web_client_mock, 'nothing', None)

    assert playlist is None
    assert 'Failed to lookup Spotify playlist URI nothing' in caplog.text
    assert len(playlists._sp_links) == 0


def test_playlist_lookup_when_link_invalid(
        session_mock, web_client_mock, web_playlist_mock, caplog):
    session_mock.get_link.side_effect = ValueError('an error message')
    web_client_mock.get_playlist.return_value = web_playlist_mock
    playlists._sp_links.clear()

    playlist = playlists.playlist_lookup(
        session_mock, web_client_mock, 'spotify:user:alice:playlist:foo', None)

    assert len(playlist.tracks) == 1
    assert 'Failed to get link "spotify:track:abc"' in caplog.text


def test_playlist_lookup_uses_cache(session_mock, web_client_mock):
    playlists.playlist_lookup(
        session_mock, web_client_mock, 'spotify:user:alice:playlist:foo', None)

    web_client_mock.get_playlist.assert_called_once_with(
        'spotify:user:alice:playlist:foo', playlists._cache)


def test_on_playlists_loaded_triggers_playlists_loaded_event(
        caplog, backend_listener_mock):
    playlists.on_playlists_loaded()

    assert 'Spotify playlists loaded' in caplog.text
    backend_listener_mock.send.assert_called_once_with('playlists_loaded')
